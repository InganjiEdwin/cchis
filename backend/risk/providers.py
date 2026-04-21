import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from decouple import config
from django.utils import timezone


alerts_logger = logging.getLogger("risk.alerts")


@dataclass(frozen=True)
class DeliveryResult:
    success: bool
    external_id: str
    error: str
    provider: str


class SmsProvider(Protocol):
    provider_name: str

    def send(self, phone_number: str, message: str) -> DeliveryResult:
        ...


class StubSmsProvider:
    provider_name = "stub"

    def send(self, phone_number: str, message: str) -> DeliveryResult:
        alerts_logger.info(
            "sms_stub_sent",
            extra={"provider": self.provider_name, "recipient": phone_number},
        )
        return DeliveryResult(
            success=True,
            external_id=f"stub-{phone_number}-{timezone.now().timestamp()}",
            error="",
            provider=self.provider_name,
        )


class AfricasTalkingSmsProvider:
    provider_name = "africastalking"

    def send(self, phone_number: str, message: str) -> DeliveryResult:
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


def get_sms_provider(provider_name: str | None = None) -> SmsProvider:
    configured_provider = (provider_name or config("SMS_PROVIDER", default="stub")).strip().lower()

    if configured_provider == "africastalking":
        return AfricasTalkingSmsProvider()
    if configured_provider == "stub":
        return StubSmsProvider()

    raise ValueError(f"Unsupported SMS provider: {configured_provider}")
