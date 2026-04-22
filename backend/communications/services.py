import logging

from .providers import EmailDeliveryResult, get_email_provider


email_logger = logging.getLogger("communications.email")


def send_email(
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str = "",
    reply_to: str = "",
    provider_name: str | None = None,
) -> EmailDeliveryResult:
    provider = get_email_provider(provider_name=provider_name)
    email_logger.info(
        "email_provider_resolved",
        extra={
            "provider": provider.provider_name,
            "recipient": to_email,
            "subject": subject,
        },
    )
    result = provider.send(
        to_email=to_email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        reply_to=reply_to,
    )
    email_logger.info(
        "email_delivery_summary",
        extra={
            "provider": result.provider,
            "recipient": to_email,
            "success": result.success,
            "status_code": result.status_code,
            "external_id": result.external_id,
        },
    )
    return result
