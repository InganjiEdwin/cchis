import hashlib
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from decouple import config
from django.conf import settings
from django.utils import timezone


alerts_logger = logging.getLogger("risk.alerts")


@dataclass(frozen=True)
class DeliveryResult:
    success: bool
    external_id: str
    error: str
    provider: str
    retryable: bool = False
    error_code: str = ""
    provider_acceptance_status: str = "not_applicable"
    provider_accepted_at: datetime | None = None
    request_metadata: dict = field(default_factory=dict)
    response_metadata: dict = field(default_factory=dict)
    external_delivery: bool = True


class SmsProvider(Protocol):
    provider_name: str

    def send(
        self,
        phone_number: str,
        message: str,
        *,
        idempotency_key: str = "",
        metadata: dict | None = None,
    ) -> DeliveryResult:
        ...


class StubSmsProvider:
    provider_name = "stub"

    def send(
        self,
        phone_number: str,
        message: str,
        *,
        idempotency_key: str = "",
        metadata: dict | None = None,
    ) -> DeliveryResult:
        alerts_logger.info(
            "sms_stub_sent",
            extra={"provider": self.provider_name},
        )
        return DeliveryResult(
            success=True,
            external_id="",
            error="",
            provider=self.provider_name,
            provider_acceptance_status="simulated",
            provider_accepted_at=timezone.now(),
            request_metadata=_safe_request_metadata(
                provider=self.provider_name,
                phone_number=phone_number,
                message=message,
                idempotency_key=idempotency_key,
            ),
            external_delivery=False,
        )


class AfricasTalkingSmsProvider:
    provider_name = "africastalking"

    def send(
        self,
        phone_number: str,
        message: str,
        *,
        idempotency_key: str = "",
        metadata: dict | None = None,
    ) -> DeliveryResult:
        username = config("AFRICASTALKING_USERNAME", default="")
        api_key = config("AFRICASTALKING_API_KEY", default="")
        sender_id = config("AFRICASTALKING_SENDER_ID", default="")
        sms_url = config(
            "AFRICASTALKING_SMS_URL",
            default="https://api.africastalking.com/version1/messaging",
        )

        if not username or not api_key:
            alerts_logger.error("sms_credentials_missing")
            return DeliveryResult(
                success=False,
                external_id="",
                error="Africa's Talking credentials are missing.",
                provider=self.provider_name,
            )

        payload = {
            "username": username,
            "to": phone_number,
            "message": message,
        }
        if sender_id:
            payload["from"] = sender_id

        encoded_payload = urllib.parse.urlencode(payload).encode("utf-8")
        request = urllib.request.Request(
            sms_url,
            data=encoded_payload,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "apiKey": api_key,
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                response_data = json.loads(response.read().decode("utf-8"))

            recipients = response_data.get("SMSMessageData", {}).get("Recipients", [])
            first_recipient = recipients[0] if recipients else {}
            status_text = str(first_recipient.get("status", "")).lower()
            external_id = str(first_recipient.get("messageId", ""))

            alerts_logger.info(
                "sms_provider_response",
                extra={
                    "provider": self.provider_name,
                    "recipient": phone_number,
                    "status": status_text,
                    "external_id": external_id,
                },
            )

            return DeliveryResult(
                success="success" in status_text or "sent" in status_text,
                external_id=external_id,
                error="",
                provider=self.provider_name,
            )
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            alerts_logger.error(
                "sms_http_error",
                extra={"recipient": phone_number, "code": exc.code},
            )
            return DeliveryResult(
                success=False,
                external_id="",
                error=f"HTTP {exc.code}: {error_body}",
                provider=self.provider_name,
            )
        except Exception as exc:
            alerts_logger.error(
                "sms_unknown_error",
                extra={"recipient": phone_number, "error": str(exc)},
            )
            return DeliveryResult(
                success=False,
                external_id="",
                error=str(exc),
                provider=self.provider_name,
            )


class ParkedAfricasTalkingSmsProvider:
    """Retain the Africa's Talking adapter without allowing it onto the active route."""

    provider_name = "africastalking"

    def send(
        self,
        phone_number: str,
        message: str,
        *,
        idempotency_key: str = "",
        metadata: dict | None = None,
    ) -> DeliveryResult:
        alerts_logger.warning(
            "sms_provider_parked",
            extra={"provider": self.provider_name},
        )
        return DeliveryResult(
            success=False,
            external_id="",
            error="Africa's Talking is parked and disabled in CCHIS.",
            provider=self.provider_name,
            error_code="provider_parked",
            request_metadata=_safe_request_metadata(
                provider=self.provider_name,
                phone_number=phone_number,
                message=message,
                idempotency_key=idempotency_key,
            ),
            external_delivery=False,
        )


class MobitechSmsProvider:
    """Mobitech bulk-SMS adapter aligned with the proven Linda Mwananchi request."""

    provider_name = "mobitech"

    def send(
        self,
        phone_number: str,
        message: str,
        *,
        idempotency_key: str = "",
        metadata: dict | None = None,
    ) -> DeliveryResult:
        api_key = str(getattr(settings, "MOBITECH_API_KEY", "") or "").strip()
        api_url = str(getattr(settings, "MOBITECH_API_URL", "") or "").strip()
        sender_id = str(getattr(settings, "MOBITECH_SENDER_ID", "") or "").strip()
        service_id = str(getattr(settings, "MOBITECH_SERVICE_ID", "0") or "0").strip() or "0"
        request_metadata = _safe_request_metadata(
            provider=self.provider_name,
            phone_number=phone_number,
            message=message,
            idempotency_key=idempotency_key,
            metadata=metadata,
            api_url=api_url,
            sender_id=sender_id,
            service_id=service_id,
            callback_url_configured=bool(
                str(getattr(settings, "MOBITECH_DELIVERY_CALLBACK_URL", "") or "").strip()
            ),
        )

        if not all([api_key, api_url, sender_id]):
            alerts_logger.error(
                "sms_credentials_missing",
                extra={"provider": self.provider_name},
            )
            return DeliveryResult(
                success=False,
                external_id="",
                error="Mobitech credentials/configuration are missing.",
                provider=self.provider_name,
                provider_acceptance_status="rejected",
                error_code="provider_not_configured",
                request_metadata=request_metadata,
                external_delivery=True,
            )

        mobile = _mobitech_msisdn(phone_number)
        if not mobile:
            return DeliveryResult(
                success=False,
                external_id="",
                error="A valid Kenyan mobile number is required for Mobitech.",
                provider=self.provider_name,
                provider_acceptance_status="rejected",
                error_code="invalid_phone_number",
                request_metadata=request_metadata,
                external_delivery=True,
            )

        payload = {
            "serviceId": service_id,
            "shortcode": sender_id,
            "messages": [
                {
                    "mobile": mobile,
                    "message": message,
                    "client_ref": _mobitech_client_ref(
                        idempotency_key=idempotency_key,
                        metadata=metadata,
                    ),
                }
            ],
        }
        timeout_seconds = int(getattr(settings, "MOBITECH_HTTP_TIMEOUT_SECONDS", 20) or 20)
        try:
            status_code, response_body = _post_mobitech_json(
                api_url,
                payload,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )
        except TimeoutError:
            return _mobitech_failure(
                request_metadata=request_metadata,
                error_code="timeout",
                error="Mobitech request timed out.",
                retryable=True,
            )
        except urllib.error.HTTPError as exc:
            status_code = int(exc.code)
            response_body = exc.read().decode("utf-8", errors="replace")
            return _mobitech_failure(
                request_metadata=request_metadata,
                error_code=f"http_{status_code}",
                error=_mobitech_http_error(status_code),
                retryable=status_code >= 500,
                status_code=status_code,
                response_body=response_body,
            )
        except (urllib.error.URLError, OSError):
            return _mobitech_failure(
                request_metadata=request_metadata,
                error_code="connection_error",
                error="Mobitech connection failed.",
                retryable=True,
            )

        response_hash = _sha256(response_body)
        data = _json_response(response_body)
        provider_reference, provider_error, provider_metadata = _mobitech_reference_and_error(data)
        response_metadata = {
            "http_status": status_code,
            "response_hash": response_hash,
            **provider_metadata,
        }
        if status_code >= 300:
            return DeliveryResult(
                success=False,
                external_id=provider_reference,
                error=_mobitech_http_error(status_code),
                provider=self.provider_name,
                retryable=status_code >= 500,
                provider_acceptance_status="rejected",
                error_code=f"http_{status_code}",
                request_metadata=request_metadata,
                response_metadata=response_metadata,
                external_delivery=True,
            )
        if provider_error:
            return DeliveryResult(
                success=False,
                external_id=provider_reference,
                error=provider_error,
                provider=self.provider_name,
                provider_acceptance_status="rejected",
                error_code="provider_rejected",
                request_metadata=request_metadata,
                response_metadata=response_metadata,
                external_delivery=True,
            )
        if not provider_reference:
            return DeliveryResult(
                success=False,
                external_id="",
                error="Mobitech returned no provider message identifier.",
                provider=self.provider_name,
                provider_acceptance_status="rejected",
                error_code="provider_response_missing_message_id",
                request_metadata=request_metadata,
                response_metadata=response_metadata,
                external_delivery=True,
            )

        accepted_at = timezone.now()
        alerts_logger.info(
            "sms_provider_accepted",
            extra={
                "provider": self.provider_name,
                "status_code": status_code,
                "provider_reference_hash": _sha256(provider_reference),
            },
        )
        return DeliveryResult(
            success=True,
            external_id=provider_reference,
            error="",
            provider=self.provider_name,
            provider_acceptance_status="accepted",
            provider_accepted_at=accepted_at,
            request_metadata=request_metadata,
            response_metadata=response_metadata,
            external_delivery=True,
        )


def _mobitech_failure(
    *,
    request_metadata: dict,
    error_code: str,
    error: str,
    retryable: bool,
    status_code: int | None = None,
    response_body: str = "",
) -> DeliveryResult:
    response_metadata = {}
    if status_code is not None:
        response_metadata["http_status"] = status_code
    if response_body:
        response_metadata["response_hash"] = _sha256(response_body)
    return DeliveryResult(
        success=False,
        external_id="",
        error=error,
        provider=MobitechSmsProvider.provider_name,
        retryable=retryable,
        error_code=error_code,
        provider_acceptance_status="rejected",
        request_metadata=request_metadata,
        response_metadata=response_metadata,
        external_delivery=True,
    )


def _post_mobitech_json(
    api_url: str,
    payload: dict,
    *,
    api_key: str,
    timeout_seconds: int,
) -> tuple[int, str]:
    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "h_api_key": api_key,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return int(response.status), response.read().decode("utf-8", errors="replace")


def _mobitech_reference_and_error(data: dict) -> tuple[str, str, dict]:
    if not isinstance(data, dict) or not data:
        return "", "Mobitech returned an invalid response.", {}
    schedule_details = data.get("schedule_details")
    first_item = {}
    if isinstance(schedule_details, list) and schedule_details:
        first_item = schedule_details[0] if isinstance(schedule_details[0], dict) else {}
    elif isinstance(schedule_details, dict):
        first_item = schedule_details
    message_id = str(first_item.get("message_id") or data.get("message_id") or "").strip()
    status_code = str(data.get("status_code") or "").strip()
    status_desc = str(data.get("status_desc") or "").strip()
    schedule_desc = str(first_item.get("schedule_desc") or "").strip()
    schedule_status = str(first_item.get("schedule_status") or "").strip().lower()
    metadata = {
        "provider_status_code": status_code,
        "provider_status_description_hash": _sha256(status_desc),
        "schedule_status": schedule_status,
        "schedule_description_hash": _sha256(schedule_desc),
    }
    if status_code and status_code != "1000":
        return message_id, "Mobitech rejected message.", metadata
    if schedule_status and schedule_status not in {"1", "success"}:
        return message_id, "Mobitech rejected message.", metadata
    return message_id, "", metadata


def _mobitech_http_error(status_code: int) -> str:
    return f"Mobitech request failed with HTTP {status_code}."


def _mobitech_msisdn(value: str) -> str:
    raw = str(value or "").strip()
    compact = raw.replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not compact.isdigit():
        return ""
    if compact.startswith("0") and len(compact) == 10 and compact[1] in {"1", "7"}:
        return f"+254{compact[1:]}"
    if compact.startswith("254") and len(compact) == 12 and compact[3] in {"1", "7"}:
        return f"+{compact}"
    if len(compact) == 9 and compact[0] in {"1", "7"}:
        return f"+254{compact}"
    return ""


def _mobitech_client_ref(*, idempotency_key: str, metadata: dict | None = None) -> str | int:
    """Use a provider-safe numeric reference when the alert supplies one."""

    metadata = metadata or {}
    for key in ("mobitech_client_ref", "client_ref"):
        value = metadata.get(key)
        if value is not None and str(value).strip():
            return value
    return idempotency_key or ""


def _safe_request_metadata(
    *,
    provider: str,
    phone_number: str,
    message: str,
    idempotency_key: str,
    metadata: dict | None = None,
    **extra,
) -> dict:
    return {
        "provider": provider,
        "destination_hash": _sha256(phone_number),
        "message_hash": _sha256(message),
        "idempotency_key": idempotency_key,
        **{key: value for key, value in extra.items() if value not in (None, "")},
        "caller_metadata_keys": sorted((metadata or {}).keys()),
    }


def _json_response(response_body: str) -> dict:
    try:
        value = json.loads(response_body or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def get_sms_provider(provider_name: str | None = None) -> SmsProvider:
    configured_provider = str(
        provider_name
        or getattr(settings, "SMS_PROVIDER", None)
        or config("SMS_PROVIDER", default="stub")
    ).strip().lower()

    if configured_provider == "africastalking":
        if not getattr(settings, "AFRICAS_TALKING_ENABLED", False):
            return ParkedAfricasTalkingSmsProvider()
        return AfricasTalkingSmsProvider()
    if configured_provider == "mobitech":
        return MobitechSmsProvider()
    if configured_provider == "stub":
        return StubSmsProvider()

    raise ValueError(f"Unsupported SMS provider: {configured_provider}")
