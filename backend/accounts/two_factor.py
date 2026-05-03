from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import struct
import time
import uuid
from urllib.parse import quote
from datetime import timedelta

from django.contrib.auth.hashers import check_password, make_password
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import PreAuthToken, TwoFactorRecoveryCode


TWO_FACTOR_POLICY_REQUIRED = "REQUIRED"
TWO_FACTOR_POLICY_OPTIONAL = "OPTIONAL"
TWO_FACTOR_POLICY_NONE = "NONE"
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
RECOVERY_CODE_PREFIX = "CCHIS"


def get_two_factor_policy_for_role(role: str) -> str:
    if role in settings.TOTP_REQUIRED_ROLES:
        return TWO_FACTOR_POLICY_REQUIRED
    if role in settings.TOTP_OPTIONAL_ROLES:
        return TWO_FACTOR_POLICY_OPTIONAL
    return TWO_FACTOR_POLICY_NONE


def get_two_factor_policy_for_user(user) -> str:
    return get_two_factor_policy_for_role(user.role)


def is_totp_enrolled(user) -> bool:
    return bool(getattr(user, "totp_secret", "")) and bool(getattr(user, "is_totp_enabled", False))


def user_must_enroll_two_factor(user) -> bool:
    return get_two_factor_policy_for_user(user) == TWO_FACTOR_POLICY_REQUIRED and not is_totp_enrolled(user)


def user_requires_two_factor(user) -> bool:
    """
    Enforced only for users who are actually enrolled. Required-role users become
    fully gated once enrollment exists, while optional-role users can opt in later.
    """

    if not is_totp_enrolled(user):
        return False
    return get_two_factor_policy_for_user(user) in {
        TWO_FACTOR_POLICY_REQUIRED,
        TWO_FACTOR_POLICY_OPTIONAL,
    }


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def build_totp_provisioning_uri(*, secret: str, username: str, issuer: str = "CCHIS") -> str:
    label = quote(f"{issuer}:{username}")
    issuer_param = quote(issuer)
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer_param}&algorithm=SHA1&digits=6&period=30"


def _decode_base32_secret(secret: str) -> bytes:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    try:
        return base64.b32decode(normalized + padding, casefold=True)
    except binascii.Error as exc:
        raise ValueError("Invalid TOTP secret encoding.") from exc


def _totp_at(secret: str, counter: int, digits: int = 6) -> str:
    key = _decode_base32_secret(secret)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10**digits)).zfill(digits)


def verify_totp_code(secret: str, code: str, *, valid_window: int = 1, interval: int = 30) -> bool:
    normalized_code = "".join(ch for ch in str(code).strip() if ch.isdigit())
    if len(normalized_code) != 6:
        return False

    current_counter = int(time.time() // interval)
    for offset in range(-valid_window, valid_window + 1):
        if hmac.compare_digest(_totp_at(secret, current_counter + offset), normalized_code):
            return True
    return False


def generate_current_totp_code(secret: str, *, interval: int = 30) -> str:
    return _totp_at(secret, int(time.time() // interval))


def normalize_recovery_code(code: str) -> str:
    return "".join(ch for ch in str(code).strip().upper() if ch.isalnum())


def _generate_plain_recovery_code() -> str:
    body = "".join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(12))
    return f"{RECOVERY_CODE_PREFIX}-{body[:4]}-{body[4:8]}-{body[8:]}"


def _recovery_code_hint(code: str) -> str:
    normalized = normalize_recovery_code(code)
    return normalized[-4:]


def hash_recovery_code(code: str) -> str:
    return make_password(normalize_recovery_code(code))


def generate_recovery_codes(user, count: int = RECOVERY_CODE_COUNT) -> list[str]:
    if count < 1:
        raise ValueError("Recovery code count must be at least 1.")

    batch_id = uuid.uuid4()
    invalidated_at = timezone.now()
    plain_codes = [_generate_plain_recovery_code() for _ in range(count)]
    recovery_code_records = [
        TwoFactorRecoveryCode(
            user=user,
            code_hash=hash_recovery_code(plain_code),
            code_hint=_recovery_code_hint(plain_code),
            batch_id=batch_id,
        )
        for plain_code in plain_codes
    ]

    with transaction.atomic():
        user.two_factor_recovery_codes.filter(
            used_at__isnull=True,
            invalidated_at__isnull=True,
        ).update(invalidated_at=invalidated_at)
        TwoFactorRecoveryCode.objects.bulk_create(recovery_code_records)

    return plain_codes


def verify_recovery_code(user, code: str) -> TwoFactorRecoveryCode | None:
    normalized_code = normalize_recovery_code(code)
    if not normalized_code:
        return None

    recovery_codes = user.two_factor_recovery_codes.filter(
        used_at__isnull=True,
        invalidated_at__isnull=True,
    ).order_by("-created_at", "-id")

    for recovery_code in recovery_codes:
        if check_password(normalized_code, recovery_code.code_hash):
            return recovery_code

    return None


def consume_recovery_code(code_record: TwoFactorRecoveryCode) -> TwoFactorRecoveryCode | None:
    with transaction.atomic():
        locked_record = TwoFactorRecoveryCode.objects.select_for_update().get(pk=code_record.pk)
        if not locked_record.is_usable:
            return None

        locked_record.used_at = timezone.now()
        locked_record.save(update_fields=["used_at"])
        return locked_record


def get_recovery_code_status(user) -> dict:
    recovery_codes = user.two_factor_recovery_codes.all()
    latest_batch_id = recovery_codes.order_by("-created_at", "-id").values_list("batch_id", flat=True).first()
    latest_batch_codes = recovery_codes.filter(batch_id=latest_batch_id) if latest_batch_id else recovery_codes.none()
    last_generated_code = latest_batch_codes.order_by("-created_at", "-id").first()
    last_used_code = recovery_codes.filter(used_at__isnull=False).order_by("-used_at", "-id").first()

    return {
        "remaining_count": latest_batch_codes.filter(
            used_at__isnull=True,
            invalidated_at__isnull=True,
        ).count(),
        "total_count": latest_batch_codes.count(),
        "last_generated_at": last_generated_code.created_at if last_generated_code else None,
        "last_used_at": last_used_code.used_at if last_used_code else None,
        "can_regenerate": is_totp_enrolled(user),
    }


def create_pre_auth_token(user) -> PreAuthToken:
    user.pre_auth_tokens.filter(used_at__isnull=True).update(used_at=timezone.now())
    return PreAuthToken.objects.create(
        user=user,
        token=secrets.token_urlsafe(32),
        expires_at=timezone.now() + timedelta(minutes=settings.PRE_AUTH_TOKEN_LIFETIME_MINUTES),
    )


def get_pre_auth_token(token_value: str) -> PreAuthToken | None:
    token_record = (
        PreAuthToken.objects.select_related("user").filter(token=token_value.strip()).first()
    )
    if not token_record or not token_record.is_usable:
        return None
    return token_record


def consume_pre_auth_token(token_record: PreAuthToken) -> PreAuthToken:
    token_record.used_at = timezone.now()
    token_record.save(update_fields=["used_at"])
    return token_record
