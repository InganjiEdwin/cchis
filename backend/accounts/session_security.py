from __future__ import annotations

import hashlib
import hmac
import ipaddress
from datetime import timedelta
from uuid import UUID

import jwt
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.state import token_backend
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.utils import datetime_from_epoch

from .audit import get_client_ip, record_auth_event
from .models import AuthAuditEvent, UserSession


class RefreshTokenAlreadyRotated(AuthenticationFailed):
    default_detail = "Refresh token has already rotated. Retry with the latest session cookies."
    default_code = "session_already_rotated"


SESSION_EXPIRED_DETAIL = "Your session has expired. Please sign in again."
SESSION_IDLE_TIMEOUT_DETAIL = "Your session expired after a period of inactivity. Please sign in again."
SESSION_REPLAY_DETECTED_DETAIL = "We signed you out because this session looked unsafe. Please sign in again."

ROLE_SESSION_POLICY_SETTINGS = {
    "ADMIN": (
        "AUTH_SESSION_REFRESH_LIFETIME_ADMIN_HOURS",
        24,
        "AUTH_SESSION_IDLE_TIMEOUT_ADMIN_MINUTES",
        60,
    ),
    "SUPERVISOR": (
        "AUTH_SESSION_REFRESH_LIFETIME_SUPERVISOR_HOURS",
        24,
        "AUTH_SESSION_IDLE_TIMEOUT_SUPERVISOR_MINUTES",
        60,
    ),
    "ANALYST": (
        "AUTH_SESSION_REFRESH_LIFETIME_ANALYST_HOURS",
        72,
        "AUTH_SESSION_IDLE_TIMEOUT_ANALYST_MINUTES",
        120,
    ),
    "CHV": (
        "AUTH_SESSION_REFRESH_LIFETIME_CHV_HOURS",
        168,
        "AUTH_SESSION_IDLE_TIMEOUT_CHV_MINUTES",
        10080,
    ),
}


def hmac_sha256(value: str) -> str:
    return hmac.new(
        str(settings.SECRET_KEY).encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def normalize_ip_prefix(ip_address: str | None) -> str:
    if not ip_address:
        return ""

    try:
        parsed_address = ipaddress.ip_address(ip_address)
    except ValueError:
        return ip_address.strip()

    prefix_length = 24 if parsed_address.version == 4 else 64
    network = ipaddress.ip_network(f"{parsed_address}/{prefix_length}", strict=False)
    return f"{network.network_address}/{prefix_length}"


def hash_refresh_jti(jti: str) -> str:
    return hmac_sha256(f"refresh-jti:{jti}")


def hash_ip_prefix(ip_address: str | None) -> str:
    prefix = normalize_ip_prefix(ip_address)
    return hmac_sha256(f"ip-prefix:{prefix}") if prefix else ""


def hash_user_agent(user_agent: str) -> str:
    normalized_user_agent = user_agent.strip()
    return hmac_sha256(f"user-agent:{normalized_user_agent}") if normalized_user_agent else ""


def get_request_user_agent(request) -> str:
    if not request:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:1000]


def get_user_agent_label(user_agent: str) -> str:
    return user_agent.strip()[:255] or "Unknown device"


def get_request_context_hashes(request) -> dict:
    user_agent = get_request_user_agent(request)
    client_ip = get_client_ip(request) if request else None
    return {
        "ip_prefix_hash": hash_ip_prefix(client_ip),
        "user_agent_hash": hash_user_agent(user_agent),
        "user_agent_label": get_user_agent_label(user_agent),
    }


def get_refresh_jti_hash(refresh: RefreshToken) -> str:
    return hash_refresh_jti(str(refresh["jti"]))


def get_refresh_expires_at(refresh: RefreshToken):
    return datetime_from_epoch(refresh["exp"])


def get_refresh_token_max_age_seconds(refresh_token: str) -> int | None:
    try:
        refresh = RefreshToken(refresh_token, verify=False)
        expires_at = get_refresh_expires_at(refresh)
    except (KeyError, TokenError):
        return None

    return max(0, int((expires_at - timezone.now()).total_seconds()))


def token_has_session_claims(token) -> bool:
    return bool(token.payload.get("sid") and token.payload.get("family"))


def apply_session_claims(refresh: RefreshToken, session: UserSession, user) -> None:
    refresh["sid"] = str(session.public_id)
    refresh["family"] = str(session.token_family_id)
    refresh["role"] = user.role
    refresh["ward_id"] = user.ward_id


def get_session_role(user_or_role) -> str:
    return str(getattr(user_or_role, "role", user_or_role) or "").upper()


def get_session_refresh_lifetime(user_or_role) -> timedelta:
    role = get_session_role(user_or_role)
    lifetime_setting, lifetime_default, _, _ = ROLE_SESSION_POLICY_SETTINGS.get(
        role,
        ROLE_SESSION_POLICY_SETTINGS["CHV"],
    )
    hours = max(1, int(getattr(settings, lifetime_setting, lifetime_default)))
    return timedelta(hours=hours)


def get_session_idle_timeout(user_or_role) -> timedelta | None:
    role = get_session_role(user_or_role)
    _, _, idle_setting, idle_default = ROLE_SESSION_POLICY_SETTINGS.get(
        role,
        ROLE_SESSION_POLICY_SETTINGS["CHV"],
    )
    minutes = int(getattr(settings, idle_setting, idle_default))
    if minutes <= 0:
        return None
    return timedelta(minutes=minutes)


def get_policy_session_expires_at(user, *, from_time=None):
    return (from_time or timezone.now()) + get_session_refresh_lifetime(user)


def get_effective_session_expires_at(session: UserSession):
    policy_expires_at = session.created_at + get_session_refresh_lifetime(session.user)
    return min(session.expires_at, policy_expires_at)


def get_session_expiry_failure(session: UserSession, *, now=None) -> tuple[str, str] | None:
    current_time = now or timezone.now()
    if get_effective_session_expires_at(session) <= current_time:
        return "session_expired", SESSION_EXPIRED_DETAIL

    idle_timeout = get_session_idle_timeout(session.user)
    if idle_timeout and session.last_seen_at + idle_timeout <= current_time:
        return "session_idle_timeout", SESSION_IDLE_TIMEOUT_DETAIL

    return None


def raise_session_expiry_failure(session: UserSession) -> None:
    failure = get_session_expiry_failure(session)
    if not failure:
        return

    code, detail = failure
    raise AuthenticationFailed(detail, code=code)


def apply_role_refresh_lifetime(refresh: RefreshToken, user) -> None:
    refresh.set_exp(
        from_time=timezone.now(),
        lifetime=get_session_refresh_lifetime(user),
    )


def sync_refresh_expiry_to_session(refresh: RefreshToken, session: UserSession) -> None:
    expires_at = get_effective_session_expires_at(session)
    remaining_lifetime = expires_at - timezone.now()
    if remaining_lifetime.total_seconds() <= 0:
        raise_session_expiry_failure(session)
        raise AuthenticationFailed(SESSION_EXPIRED_DETAIL, code="session_expired")

    refresh.set_exp(from_time=timezone.now(), lifetime=remaining_lifetime)


def build_session_event_metadata(session: UserSession, extra: dict | None = None) -> dict:
    metadata = {
        "session_id": str(session.public_id),
        "token_family_id": str(session.token_family_id),
    }
    if extra:
        metadata.update(extra)
    return metadata


def session_queryset(*, for_update: bool = False):
    queryset = UserSession.objects.select_related("user")
    if for_update:
        queryset = queryset.select_for_update()
    return queryset


def create_session_for_refresh(user, refresh: RefreshToken, request=None) -> UserSession:
    context_hashes = get_request_context_hashes(request)
    now = timezone.now()
    session = UserSession.objects.create(
        user=user,
        current_refresh_jti_hash=get_refresh_jti_hash(refresh),
        expires_at=min(get_refresh_expires_at(refresh), get_policy_session_expires_at(user, from_time=now)),
        created_ip_prefix_hash=context_hashes["ip_prefix_hash"],
        last_ip_prefix_hash=context_hashes["ip_prefix_hash"],
        user_agent_hash=context_hashes["user_agent_hash"],
        user_agent_label=context_hashes["user_agent_label"],
        device_label=context_hashes["user_agent_label"],
    )
    apply_session_claims(refresh, session, user)
    if request is not None:
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_SESSION_CREATED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=user,
            target_user=user,
            metadata=build_session_event_metadata(session),
        )
        notify_admin_new_device_if_needed(user, session, context_hashes)
    return session


def get_session_from_refresh(refresh: RefreshToken, user=None, *, for_update: bool = False) -> UserSession | None:
    sid = refresh.payload.get("sid")
    family = refresh.payload.get("family")
    if not sid or not family:
        return None

    try:
        public_id = UUID(str(sid))
        family_id = UUID(str(family))
    except (TypeError, ValueError):
        return None

    queryset = session_queryset(for_update=for_update).filter(
        public_id=public_id,
        token_family_id=family_id,
    )
    if user is not None:
        queryset = queryset.filter(user=user)
    return queryset.first()


def get_session_from_refresh_jti(refresh: RefreshToken, user=None, *, for_update: bool = False) -> UserSession | None:
    jti = refresh.payload.get("jti")
    if not jti:
        return None

    queryset = session_queryset(for_update=for_update).filter(
        current_refresh_jti_hash=hash_refresh_jti(str(jti))
    )
    if user is not None:
        queryset = queryset.filter(user=user)
    return queryset.first()


def get_session_from_refresh_payload(refresh: RefreshToken, *, for_update: bool = False) -> UserSession | None:
    session = get_session_from_refresh(refresh, for_update=for_update)
    if session:
        return session

    user_id = refresh.payload.get("user_id")
    jti = refresh.payload.get("jti")
    if not user_id or not jti:
        return None

    jti_hash = hash_refresh_jti(str(jti))
    return (
        session_queryset(for_update=for_update)
        .filter(user_id=user_id)
        .filter(
            Q(current_refresh_jti_hash=jti_hash) | Q(previous_refresh_jti_hash=jti_hash)
        )
        .first()
    )


def ensure_session_for_refresh(user, refresh: RefreshToken, request=None) -> tuple[UserSession, bool]:
    session = get_session_from_refresh(refresh, user=user)
    if session:
        apply_session_claims(refresh, session, user)
        return session, False

    if token_has_session_claims(refresh):
        raise AuthenticationFailed("Refresh session is not recognized.", code="session_not_found")

    session = get_session_from_refresh_jti(refresh, user=user)
    if session:
        apply_session_claims(refresh, session, user)
        return session, False

    return create_session_for_refresh(user, refresh, request=request), True


def ensure_locked_session_for_refresh(
    user,
    refresh: RefreshToken,
    request=None,
    *,
    allow_create: bool = True,
) -> tuple[UserSession, bool]:
    session = get_session_from_refresh(refresh, user=user, for_update=True)
    if session:
        apply_session_claims(refresh, session, user)
        return session, False

    if token_has_session_claims(refresh):
        raise AuthenticationFailed("Refresh session is not recognized.", code="session_not_found")

    session = get_session_from_refresh_jti(refresh, user=user, for_update=True)
    if session:
        apply_session_claims(refresh, session, user)
        return session, False

    if not allow_create:
        raise AuthenticationFailed("Refresh session is not recognized.", code="session_not_found")

    return create_session_for_refresh(user, refresh, request=request), True


def update_session_context(session: UserSession, request) -> tuple[list[str], dict]:
    context_hashes = get_request_context_hashes(request)
    changed_fields: list[str] = []
    update_fields = ["last_seen_at", "last_ip_prefix_hash"]

    if (
        session.last_ip_prefix_hash
        and context_hashes["ip_prefix_hash"]
        and session.last_ip_prefix_hash != context_hashes["ip_prefix_hash"]
    ):
        changed_fields.append("ip_prefix")

    if (
        session.user_agent_hash
        and context_hashes["user_agent_hash"]
        and session.user_agent_hash != context_hashes["user_agent_hash"]
    ):
        changed_fields.append("user_agent")
        session.is_suspicious = True
        session.suspicion_reason = "user_agent_changed"
        update_fields.extend(["is_suspicious", "suspicion_reason"])

    session.last_seen_at = timezone.now()
    session.last_ip_prefix_hash = context_hashes["ip_prefix_hash"]
    session.save(update_fields=sorted(set(update_fields)))

    return changed_fields, context_hashes


def record_context_change_if_needed(session: UserSession, request, changed_fields: list[str]) -> None:
    if not changed_fields or request is None:
        return

    record_auth_event(
        request=request,
        event_type=AuthAuditEvent.EVENT_SESSION_CONTEXT_CHANGED,
        status=AuthAuditEvent.STATUS_SUCCESS,
        actor=session.user,
        target_user=session.user,
        metadata=build_session_event_metadata(
            session,
            {"changed_fields": changed_fields},
        ),
    )
    notify_session_context_changed(session, changed_fields=changed_fields)


def classify_session_refresh(session: UserSession, refresh: RefreshToken) -> tuple[str, str]:
    if str(session.user_id) != str(refresh.payload.get("user_id")):
        raise AuthenticationFailed("Refresh session user mismatch.", code="session_user_mismatch")

    if session.revoked_at:
        raise AuthenticationFailed("Refresh session has been revoked.", code="session_revoked")

    raise_session_expiry_failure(session)

    refresh_jti_hash = get_refresh_jti_hash(refresh)
    if session.current_refresh_jti_hash == refresh_jti_hash:
        return "current", refresh_jti_hash

    if (
        session.previous_refresh_jti_hash == refresh_jti_hash
        and session.previous_refresh_grace_until
        and session.previous_refresh_grace_until > timezone.now()
    ):
        return "previous_grace", refresh_jti_hash

    return "replay", refresh_jti_hash


def validate_session_for_refresh(session: UserSession, refresh: RefreshToken, request=None) -> None:
    refresh_match, refresh_jti_hash = classify_session_refresh(session, refresh)
    if refresh_match == "current":
        return
    if refresh_match == "previous_grace":
        raise RefreshTokenAlreadyRotated()

    mark_refresh_replay_detected(session, request, refresh_jti_hash, reason="refresh_jti_mismatch")
    raise AuthenticationFailed(SESSION_REPLAY_DETECTED_DETAIL, code="session_replay_detected")


def mark_session_seen(session: UserSession, refresh: RefreshToken, request=None) -> None:
    validate_session_for_refresh(session, refresh, request=request)
    changed_fields, _ = update_session_context(session, request)
    record_context_change_if_needed(session, request, changed_fields)


def mark_previous_refresh_grace_used(session: UserSession, request=None) -> None:
    changed_fields, _ = update_session_context(session, request)
    if request is not None:
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_SESSION_REFRESHED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=session.user,
            target_user=session.user,
            metadata=build_session_event_metadata(
                session,
                {"previous_refresh_grace": True, "rotated": False},
            ),
        )
        record_context_change_if_needed(session, request, changed_fields)


def mark_session_refreshed(
    session: UserSession,
    new_refresh: RefreshToken,
    request=None,
    *,
    previous_jti_hash: str,
) -> None:
    context_hashes = get_request_context_hashes(request)
    changed_fields = []
    if (
        session.last_ip_prefix_hash
        and context_hashes["ip_prefix_hash"]
        and session.last_ip_prefix_hash != context_hashes["ip_prefix_hash"]
    ):
        changed_fields.append("ip_prefix")
    if (
        session.user_agent_hash
        and context_hashes["user_agent_hash"]
        and session.user_agent_hash != context_hashes["user_agent_hash"]
    ):
        changed_fields.append("user_agent")
        session.is_suspicious = True
        session.suspicion_reason = "user_agent_changed"

    now = timezone.now()
    session.previous_refresh_jti_hash = previous_jti_hash
    session.previous_refresh_grace_until = now + timedelta(
        seconds=max(0, int(getattr(settings, "AUTH_REFRESH_PREVIOUS_JTI_GRACE_SECONDS", 30)))
    )
    session.current_refresh_jti_hash = get_refresh_jti_hash(new_refresh)
    session.last_seen_at = now
    session.last_rotated_at = now
    session.expires_at = min(get_refresh_expires_at(new_refresh), get_effective_session_expires_at(session))
    session.last_ip_prefix_hash = context_hashes["ip_prefix_hash"]
    session.save(
        update_fields=[
            "previous_refresh_jti_hash",
            "previous_refresh_grace_until",
            "current_refresh_jti_hash",
            "last_seen_at",
            "last_rotated_at",
            "expires_at",
            "last_ip_prefix_hash",
            "is_suspicious",
            "suspicion_reason",
        ]
    )
    if request is not None:
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_SESSION_REFRESHED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=session.user,
            target_user=session.user,
            metadata=build_session_event_metadata(session),
        )
        record_context_change_if_needed(session, request, changed_fields)


def revoke_session(
    session: UserSession,
    request=None,
    *,
    revoked_by=None,
    reason: str,
    event_type: str = AuthAuditEvent.EVENT_SESSION_REVOKED,
    status: str = AuthAuditEvent.STATUS_SUCCESS,
    metadata: dict | None = None,
) -> None:
    if not session.revoked_at:
        session.revoked_at = timezone.now()
        session.revoked_by = revoked_by
        session.revoked_reason = reason
        session.save(update_fields=["revoked_at", "revoked_by", "revoked_reason"])

    if request is not None:
        record_auth_event(
            request=request,
            event_type=event_type,
            status=status,
            actor=revoked_by or session.user,
            target_user=session.user,
            metadata=build_session_event_metadata(session, {"reason": reason, **(metadata or {})}),
        )


def blacklist_known_refresh_tokens_for_session(
    session: UserSession,
    extra_jti_hashes: list[str] | tuple[str, ...] | None = None,
) -> int:
    target_hashes = {
        value
        for value in [
            session.current_refresh_jti_hash,
            session.previous_refresh_jti_hash,
            *(extra_jti_hashes or ()),
        ]
        if value
    }
    if not target_hashes:
        return 0

    blacklisted_count = 0
    for outstanding_token in OutstandingToken.objects.filter(user=session.user):
        if hash_refresh_jti(str(outstanding_token.jti)) not in target_hashes:
            continue
        _, created = BlacklistedToken.objects.get_or_create(token=outstanding_token)
        if created:
            blacklisted_count += 1
    return blacklisted_count


def mark_session_family_compromised(session: UserSession, *, reason: str) -> None:
    if session.is_suspicious and session.suspicion_reason == reason:
        return

    session.is_suspicious = True
    session.suspicion_reason = reason
    session.save(update_fields=["is_suspicious", "suspicion_reason"])


def notify_session_replay_detected(session: UserSession, *, reason: str) -> None:
    try:
        from risk.notifications import notify_session_replay_detected as notify
    except Exception:
        return

    try:
        notify(session, reason=reason)
    except Exception:
        return


def notify_session_context_changed(session: UserSession, *, changed_fields: list[str]) -> None:
    try:
        from risk.notifications import notify_session_context_changed as notify
    except Exception:
        return

    try:
        notify(session, changed_fields=changed_fields)
    except Exception:
        return


def notify_admin_new_device_if_needed(user, session: UserSession, context_hashes: dict) -> None:
    if getattr(user, "role", None) != getattr(user, "ROLE_ADMIN", "ADMIN"):
        return

    user_agent_hash = context_hashes.get("user_agent_hash")
    if not user_agent_hash:
        return

    prior_same_device = (
        UserSession.objects.filter(user=user, user_agent_hash=user_agent_hash)
        .exclude(pk=session.pk)
        .exists()
    )
    if prior_same_device:
        return

    try:
        from risk.notifications import notify_admin_new_device as notify
    except Exception:
        return

    try:
        notify(session)
    except Exception:
        return


def parse_refresh_verified_allow_blacklisted(refresh_token: str) -> RefreshToken:
    try:
        payload = token_backend.decode(refresh_token, verify=True)
    except Exception as exc:
        raise TokenError("Token is invalid or expired.") from exc

    if payload.get("token_type") != RefreshToken.token_type:
        raise TokenError("Token has wrong type.")

    refresh = RefreshToken(refresh_token, verify=False)
    refresh.payload = payload
    return refresh


def parse_refresh_signature_verified_allow_expired(refresh_token: str) -> RefreshToken:
    try:
        decode_options = {"verify_exp": False}
        decode_kwargs = {
            "algorithms": [token_backend.algorithm],
            "options": decode_options,
        }
        audience = getattr(token_backend, "audience", None)
        issuer = getattr(token_backend, "issuer", None)
        if audience is not None:
            decode_kwargs["audience"] = audience
        else:
            decode_options["verify_aud"] = False
        if issuer is not None:
            decode_kwargs["issuer"] = issuer
        if hasattr(token_backend, "get_leeway"):
            decode_kwargs["leeway"] = token_backend.get_leeway()

        payload = jwt.decode(
            refresh_token,
            token_backend.get_verifying_key(refresh_token),
            **decode_kwargs,
        )
    except Exception as exc:
        raise TokenError("Token signature is invalid.") from exc

    if payload.get("token_type") != RefreshToken.token_type:
        raise TokenError("Token has wrong type.")

    refresh = RefreshToken(refresh_token, verify=False)
    refresh.payload = payload
    return refresh


def parse_refresh_verified_for_failure_handling(refresh_token: str) -> RefreshToken | None:
    try:
        return parse_refresh_verified_allow_blacklisted(refresh_token)
    except TokenError:
        try:
            return parse_refresh_signature_verified_allow_expired(refresh_token)
        except TokenError:
            return None


def mark_refresh_replay_detected(
    session: UserSession,
    request=None,
    refresh_jti_hash: str | None = None,
    *,
    reason: str,
) -> bool:
    now = timezone.now()
    if (
        refresh_jti_hash
        and session.previous_refresh_jti_hash == refresh_jti_hash
        and session.previous_refresh_grace_until
        and session.previous_refresh_grace_until > now
    ):
        return False

    mark_session_family_compromised(session, reason="refresh_replay_detected")
    blacklisted_count = blacklist_known_refresh_tokens_for_session(
        session,
        extra_jti_hashes=[refresh_jti_hash] if refresh_jti_hash else None,
    )
    revoke_session(
        session,
        request=request,
        revoked_by=session.user,
        reason="refresh_replay_detected",
        event_type=AuthAuditEvent.EVENT_SESSION_REPLAY_DETECTED,
        status=AuthAuditEvent.STATUS_FAILED,
        metadata={
            "detection_reason": reason,
            "blacklisted_tokens": blacklisted_count,
        },
    )
    transaction.on_commit(lambda: notify_session_replay_detected(session, reason=reason))
    return True


def handle_failed_refresh_token(
    refresh_token: str,
    request=None,
    *,
    reason: str,
    raise_session_policy_failure: bool = False,
) -> UserSession | None:
    refresh = parse_refresh_verified_for_failure_handling(refresh_token)
    if not refresh:
        return None

    with transaction.atomic():
        session = get_session_from_refresh_payload(refresh, for_update=True)
        if not session:
            return None

        try:
            refresh_match, refresh_jti_hash = classify_session_refresh(session, refresh)
        except AuthenticationFailed as exc:
            if raise_session_policy_failure:
                raise exc
            return session

        if refresh_match == "previous_grace":
            raise RefreshTokenAlreadyRotated()

        if refresh_match == "current":
            if raise_session_policy_failure:
                raise AuthenticationFailed("Invalid or expired refresh token.", code="invalid_refresh")
            return session

        replay_detected = mark_refresh_replay_detected(session, request, refresh_jti_hash, reason=reason)

    if not replay_detected:
        raise RefreshTokenAlreadyRotated()
    if raise_session_policy_failure:
        raise AuthenticationFailed(SESSION_REPLAY_DETECTED_DETAIL, code="session_replay_detected")
    return session


def revoke_session_from_refresh_token(refresh_token: str, request=None, *, revoked_by=None, reason: str) -> UserSession | None:
    refresh = parse_refresh_verified_for_failure_handling(refresh_token)
    if not refresh:
        return None

    session = get_session_from_refresh_payload(refresh)
    if not session:
        return None

    revoke_session(
        session,
        request=request,
        revoked_by=revoked_by,
        reason=reason,
    )
    return session


def revoke_sessions_for_user(user, request=None, *, revoked_by=None, reason: str) -> int:
    revoked_count = 0
    with transaction.atomic():
        sessions = UserSession.objects.select_for_update().filter(user=user, revoked_at__isnull=True)
        for session in sessions:
            blacklist_known_refresh_tokens_for_session(session)
            revoke_session(
                session,
                request=request,
                revoked_by=revoked_by,
                reason=reason,
            )
            revoked_count += 1
    return revoked_count


def validate_access_token_session(user, validated_token) -> UserSession | None:
    sid = validated_token.get("sid")
    family = validated_token.get("family")
    if not sid or not family:
        raise AuthenticationFailed("Access session is not recognized.", code="session_not_found")

    try:
        public_id = UUID(str(sid))
        family_id = UUID(str(family))
    except (TypeError, ValueError) as exc:
        raise AuthenticationFailed("Access session is not recognized.", code="session_not_found") from exc

    session = UserSession.objects.filter(
        public_id=public_id,
        token_family_id=family_id,
        user=user,
    ).first()
    if not session:
        raise AuthenticationFailed("Access session is not recognized.", code="session_not_found")
    if session.revoked_at:
        raise AuthenticationFailed("Access session has been revoked.", code="session_revoked")
    raise_session_expiry_failure(session)
    return session
