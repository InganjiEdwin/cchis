from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests
from django.conf import settings


turnstile_logger = logging.getLogger("accounts.security")


@dataclass(frozen=True)
class TurnstileVerificationResult:
    success: bool
    error_codes: tuple[str, ...] = ()
    hostname: str | None = None


def is_turnstile_enabled() -> bool:
    return bool(getattr(settings, "ACCESS_REQUEST_TURNSTILE_ENABLED", False))


def expected_turnstile_hostname() -> str | None:
    explicit_hostname = getattr(settings, "TURNSTILE_EXPECTED_HOSTNAME", "").strip()
    if explicit_hostname:
        return explicit_hostname

    frontend_url = getattr(settings, "FRONTEND_APP_URL", "").strip()
    if not frontend_url:
        return None

    parsed = urlparse(frontend_url)
    return parsed.hostname


def verify_turnstile_token(token: str, *, remote_ip: str | None = None) -> TurnstileVerificationResult:
    response = requests.post(
        settings.TURNSTILE_SITEVERIFY_URL,
        data={
            "secret": settings.TURNSTILE_SECRET_KEY,
            "response": token,
            "remoteip": remote_ip or "",
        },
        timeout=5,
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()

    success = bool(payload.get("success"))
    error_codes = tuple(payload.get("error-codes") or ())
    hostname = payload.get("hostname")
    expected_hostname = expected_turnstile_hostname()

    if success and expected_hostname and hostname and hostname != expected_hostname:
        turnstile_logger.warning(
            "access_request_turnstile_hostname_mismatch",
            extra={
                "event_type": "access_request_turnstile_hostname_mismatch",
                "expected_hostname": expected_hostname,
                "hostname": hostname,
            },
        )
        return TurnstileVerificationResult(
            success=False,
            error_codes=("hostname-mismatch",),
            hostname=hostname,
        )

    return TurnstileVerificationResult(
        success=success,
        error_codes=error_codes,
        hostname=hostname,
    )
