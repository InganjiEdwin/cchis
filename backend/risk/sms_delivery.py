from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from .models import Alert, AlertDeliveryEvent


logger = logging.getLogger("risk.sms")
MOBITECH_PROVIDER = "mobitech"


def process_mobitech_delivery_callback(payload: dict[str, Any]) -> dict[str, Any]:
    """Reconcile one Mobitech delivery report without persisting sensitive payload data."""

    normalized_payload = _normalise_callback_payload(payload)
    payload_hash = _sha256(_canonical_json(payload))
    provider_event_id = _first_value(
        normalized_payload,
        "provider_event_id",
        "event_id",
        "eventId",
        "id",
    )
    provider_message_id = _first_value(
        normalized_payload,
        "provider_message_id",
        "message_id",
        "messageId",
        "sms_id",
        "smsId",
    )
    client_ref = _first_value(normalized_payload, "client_ref", "clientRef", "idempotency_key")
    status = _normalise_delivery_status(
        _first_value(normalized_payload, "status", "delivery_status", "schedule_status")
    )
    if not status:
        return {
            "status": "ignored",
            "reason": "unsupported_status",
            "payload_hash": payload_hash,
        }

    alert = _find_alert(
        provider_message_id=provider_message_id,
        client_ref=client_ref,
    )
    if alert is None:
        logger.warning(
            "mobitech_callback_unmatched",
            extra={
                "provider": MOBITECH_PROVIDER,
                "provider_message_id_hash": _sha256(provider_message_id),
                "client_ref_hash": _sha256(client_ref),
                "payload_hash": payload_hash,
            },
        )
        return {
            "status": "unmatched",
            "reason": "no_matching_alert",
            "payload_hash": payload_hash,
        }

    event_key = _event_key(
        provider_event_id=provider_event_id,
        provider_message_id=provider_message_id,
        status=status,
        payload_hash=payload_hash,
    )
    sanitized_payload = _sanitized_callback_payload(
        normalized_payload,
        provider_event_id=provider_event_id,
        provider_message_id=provider_message_id,
        client_ref=client_ref,
        status=status,
    )

    with transaction.atomic():
        locked_alert = Alert.objects.select_for_update().get(pk=alert.pk)
        try:
            event, created = AlertDeliveryEvent.objects.get_or_create(
                event_key=event_key,
                defaults={
                    "alert": locked_alert,
                    "provider": MOBITECH_PROVIDER,
                    "provider_event_id": provider_event_id,
                    "provider_message_id": provider_message_id,
                    "status": status,
                    "payload_hash": payload_hash,
                    "sanitized_payload": sanitized_payload,
                },
            )
        except IntegrityError:
            event = AlertDeliveryEvent.objects.get(event_key=event_key)
            created = False

        if created:
            _apply_delivery_status(
                locked_alert,
                status=status,
                payload_hash=payload_hash,
            )

    if created:
        logger.info(
            "mobitech_callback_reconciled",
            extra={
                "provider": MOBITECH_PROVIDER,
                "alert_id": locked_alert.id,
                "status": status,
                "payload_hash": payload_hash,
            },
        )
        return {
            "status": "processed",
            "alert_id": locked_alert.id,
            "delivery_status": status,
            "payload_hash": payload_hash,
        }
    return {
        "status": "duplicate",
        "alert_id": locked_alert.id,
        "delivery_status": event.status,
        "payload_hash": event.payload_hash,
    }


def _find_alert(*, provider_message_id: str, client_ref: str) -> Alert | None:
    clauses = []
    if provider_message_id:
        clauses.extend([Q(provider_message_id=provider_message_id), Q(external_id=provider_message_id)])
    if client_ref:
        try:
            clauses.append(Q(idempotency_key=uuid.UUID(client_ref)))
        except (ValueError, AttributeError):
            pass
    if not clauses:
        return None
    query = clauses[0]
    for clause in clauses[1:]:
        query |= clause
    return (
        Alert.objects.filter(
            query,
            channel=Alert.CHANNEL_SMS,
            delivery_backend=MOBITECH_PROVIDER,
        )
        .order_by("-created_at", "-id")
        .first()
    )


def _apply_delivery_status(alert: Alert, *, status: str, payload_hash: str) -> None:
    update_fields = ["callback_payload_hash"]
    alert.callback_payload_hash = payload_hash
    # Final delivery is monotonic. A late provider failure must not downgrade an
    # alert that CCHIS has already reconciled as delivered.
    if status == Alert.PROVIDER_DELIVERY_FAILED and alert.status == Alert.STATUS_DELIVERED:
        alert.save(update_fields=update_fields)
        return

    alert.provider_delivery_status = status
    update_fields.insert(0, "provider_delivery_status")
    if status == Alert.PROVIDER_DELIVERY_DELIVERED:
        if alert.status != Alert.STATUS_FAILED:
            alert.status = Alert.STATUS_DELIVERED
            alert.sent_at = timezone.now()
            update_fields.extend(["status", "sent_at"])
        alert.provider_delivered_at = timezone.now()
        update_fields.append("provider_delivered_at")
    elif status == Alert.PROVIDER_DELIVERY_FAILED:
        if alert.status != Alert.STATUS_DELIVERED:
            alert.status = Alert.STATUS_FAILED
            alert.error_message = "Mobitech delivery report indicated a failed delivery."
            alert.last_error_classification = "provider_delivery_failed"
            alert.next_retry_at = None
            update_fields.extend(["status", "error_message", "last_error_classification", "next_retry_at"])
    alert.save(update_fields=update_fields)


def _event_key(*, provider_event_id: str, provider_message_id: str, status: str, payload_hash: str) -> str:
    basis = provider_event_id or f"{provider_message_id}:{status}:{payload_hash}"
    return _sha256(f"{MOBITECH_PROVIDER}:{basis}")


def _normalise_callback_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    result: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, (list, tuple)):
            result[str(key)] = value[0] if value else ""
        else:
            result[str(key)] = value
    return result


def _sanitized_callback_payload(
    payload: dict[str, Any],
    *,
    provider_event_id: str,
    provider_message_id: str,
    client_ref: str,
    status: str,
) -> dict[str, Any]:
    timestamp = _first_value(payload, "timestamp", "dateModified", "date_modified", "delivery_date")
    status_code = _first_value(payload, "status_code", "statusCode", "code")
    status_description = _first_value(payload, "status_description", "statusDescription", "description")
    destination = _first_value(payload, "subscriber", "mobile", "phone", "to", "destination")
    return {
        "provider": MOBITECH_PROVIDER,
        "provider_event_id": provider_event_id,
        "provider_message_id": provider_message_id,
        "client_ref": client_ref,
        "status": status,
        "status_code": status_code,
        "status_description_hash": _sha256(status_description),
        "destination_hash": _sha256(destination),
        "timestamp": timestamp,
    }


def _normalise_delivery_status(value: Any) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_")
    if normalized in {"delivered", "delivery_success", "success", "successful", "dlvrd", "1"}:
        return Alert.PROVIDER_DELIVERY_DELIVERED
    if normalized in {
        "failed",
        "failure",
        "undelivered",
        "rejected",
        "expired",
        "blocked",
        "0",
    }:
        return Alert.PROVIDER_DELIVERY_FAILED
    if normalized in {"pending", "queued", "scheduled", "sent", "accepted", "in_progress", "2"}:
        return Alert.PROVIDER_DELIVERY_PENDING
    return ""


def _first_value(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()
