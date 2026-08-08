"""Validation helpers for Mobitech delivery reconciliation configuration."""

from __future__ import annotations

import hmac
from urllib.parse import unquote, urlparse


def is_valid_mobitech_callback_configuration(
    callback_url: str,
    callback_token: str,
    *,
    require_https: bool = False,
) -> bool:
    """Return whether a callback URL embeds the configured secret route token."""

    normalized_url = str(callback_url or "").strip()
    normalized_token = str(callback_token or "").strip()
    if not normalized_url or not normalized_token or any(char.isspace() for char in normalized_token):
        return False

    parsed = urlparse(normalized_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if require_https and parsed.scheme != "https":
        return False
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False

    path_segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
    return bool(
        path_segments
        and hmac.compare_digest(path_segments[-1], normalized_token)
    )


def is_valid_mobitech_polling_configuration(
    status_url: str,
    api_key: str,
    auth_scheme: str = "bearer",
    *,
    require_https: bool = False,
) -> bool:
    """Return whether an official Mobitech bearer-receipts/stats URL is configured."""

    normalized_url = str(status_url or "").strip()
    normalized_key = str(api_key or "").strip()
    normalized_scheme = str(auth_scheme or "").strip().lower()
    if not normalized_url or not normalized_key or normalized_scheme != "bearer":
        return False

    parsed = urlparse(normalized_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    if require_https and parsed.scheme != "https":
        return False
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False

    path_segments = [segment for segment in parsed.path.split("/") if segment]
    return bool(
        len(path_segments) >= 3
        and path_segments[-2] == "{message_id}"
        and path_segments[-1].lower() in {"receipts", "stats"}
    )


def collect_mobitech_reconciliation_configuration_errors(
    *,
    shared_environment: bool,
    callback_url: str,
    callback_token: str,
    api_key: str,
    status_url: str,
    status_auth_scheme: str,
) -> list[str]:
    """Return startup validation errors without exposing configuration values."""

    if not shared_environment:
        return []

    callback_ready = is_valid_mobitech_callback_configuration(
        callback_url,
        callback_token,
        require_https=True,
    )
    polling_ready = is_valid_mobitech_polling_configuration(
        status_url,
        api_key,
        status_auth_scheme,
        require_https=True,
    )
    if callback_ready or polling_ready:
        return []

    return [
        "Mobitech SMS delivery requires either an HTTPS provider-reachable callback URL containing the callback token or an authenticated official status polling URL."
    ]
