import logging
from dataclasses import dataclass
from typing import Protocol

import requests
from django.conf import settings
from django.utils import timezone


email_logger = logging.getLogger("communications.email")


@dataclass(frozen=True)
class EmailDeliveryResult:
    success: bool
    external_id: str
    error: str
    provider: str
    status_code: int | None = None


class EmailProvider(Protocol):
    provider_name: str

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str = "",
        reply_to: str = "",
    ) -> EmailDeliveryResult:
        ...


class StubEmailProvider:
    provider_name = "stub"

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str = "",
        reply_to: str = "",
    ) -> EmailDeliveryResult:
        email_logger.info(
            "email_stub_sent",
            extra={
                "provider": self.provider_name,
                "recipient": to_email,
                "subject": subject,
                "has_html": bool(html_body),
                "has_reply_to": bool(reply_to),
            },
        )
        return EmailDeliveryResult(
            success=True,
            external_id=f"stub-{to_email}-{timezone.now().timestamp()}",
            error="",
            provider=self.provider_name,
            status_code=200,
        )


class MailgunEmailProvider:
    provider_name = "mailgun"

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        text_body: str,
        html_body: str = "",
        reply_to: str = "",
    ) -> EmailDeliveryResult:
        if not settings.MAILGUN_API_KEY or not settings.MAILGUN_DOMAIN or not settings.MAILGUN_FROM_EMAIL:
            email_logger.error(
                "email_credentials_missing",
                extra={"provider": self.provider_name, "recipient": to_email},
            )
            return EmailDeliveryResult(
                success=False,
                external_id="",
                error="Mailgun credentials are missing.",
                provider=self.provider_name,
                status_code=None,
            )

        effective_reply_to = reply_to or settings.MAILGUN_REPLY_TO or settings.MAILGUN_HOST
        payload = {
            "from": settings.MAILGUN_FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "text": text_body,
        }
        if html_body:
            payload["html"] = html_body

        headers = {}
        if effective_reply_to:
            headers["h:Reply-To"] = effective_reply_to

        endpoint = f"{settings.MAILGUN_BASE_URL.rstrip('/')}/{settings.MAILGUN_DOMAIN}/messages"

        try:
            response = requests.post(
                endpoint,
                auth=("api", settings.MAILGUN_API_KEY),
                data=payload,
                headers=headers,
                timeout=20,
            )
            response.raise_for_status()
            response_data = response.json()
            external_id = str(response_data.get("id", ""))

            email_logger.info(
                "email_provider_response",
                extra={
                    "provider": self.provider_name,
                    "recipient": to_email,
                    "status_code": response.status_code,
                    "external_id": external_id,
                },
            )

            return EmailDeliveryResult(
                success=True,
                external_id=external_id,
                error="",
                provider=self.provider_name,
                status_code=response.status_code,
            )
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            error_body = exc.response.text if exc.response is not None else str(exc)
            email_logger.error(
                "email_http_error",
                extra={
                    "provider": self.provider_name,
                    "recipient": to_email,
                    "status_code": status_code,
                },
            )
            return EmailDeliveryResult(
                success=False,
                external_id="",
                error=f"HTTP {status_code}: {error_body}" if status_code else error_body,
                provider=self.provider_name,
                status_code=status_code,
            )
        except requests.RequestException as exc:
            email_logger.error(
                "email_request_exception",
                extra={
                    "provider": self.provider_name,
                    "recipient": to_email,
                    "error": str(exc),
                },
            )
            return EmailDeliveryResult(
                success=False,
                external_id="",
                error=str(exc),
                provider=self.provider_name,
                status_code=None,
            )


def get_email_provider(provider_name: str | None = None) -> EmailProvider:
    configured_provider = (provider_name or settings.EMAIL_PROVIDER).strip().lower()

    if configured_provider == "mailgun":
        return MailgunEmailProvider()
    if configured_provider == "stub":
        return StubEmailProvider()

    raise ValueError(f"Unsupported email provider: {configured_provider}")
