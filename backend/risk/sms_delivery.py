from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from core.mobitech_config import is_valid_mobitech_polling_configuration

from .models import Alert, AlertDeliveryEvent


logger = logging.getLogger("risk.sms")
MOBITECH_PROVIDER = "mobitech"


def process_mobitech_delivery_callback(
    payload: dict[str, Any],
    *,
    reconciliation_method: str = "callback",
) -> dict[str, Any]:
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
    status = _delivery_status_from_payload(normalized_payload)
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
        reconciliation_method=reconciliation_method,
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


def poll_mobitech_delivery_status(alert: Alert) -> dict[str, Any]:
    """Poll an explicitly configured official Mobitech receipts/stats endpoint."""

    message_id = str(getattr(alert, "provider_message_id", "") or "").strip()
    status_url = str(getattr(settings, "MOBITECH_STATUS_API_URL", "") or "").strip()
    api_key = str(getattr(settings, "MOBITECH_API_KEY", "") or "").strip()
    auth_scheme = str(getattr(settings, "MOBITECH_STATUS_AUTH_SCHEME", "bearer") or "").strip()
    if not message_id:
        return {"status": "ignored", "reason": "missing_provider_message_id"}
    if not is_valid_mobitech_polling_configuration(status_url, api_key, auth_scheme):
        return {"status": "blocked", "reason": "polling_not_configured"}

    request_url = status_url.replace("{message_id}", quote(message_id, safe=""))
    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="GET",
    )
    try:
        with urlopen(
            request,
            timeout=max(int(getattr(settings, "MOBITECH_STATUS_HTTP_TIMEOUT_SECONDS", 20)), 1),
        ) as response:
            response_code = int(response.getcode() or 0)
            response_body = response.read()
    except HTTPError as error:
        return {"status": "error", "reason": f"http_{error.code}"}
    except (URLError, TimeoutError, OSError, ValueError):
        return {"status": "error", "reason": "transport_error"}

    response_hash = _sha256(response_body.decode("utf-8", errors="replace"))
    if response_code < 200 or response_code >= 300:
        return {
            "status": "error",
            "reason": f"http_{response_code}",
            "response_hash": response_hash,
        }
    try:
        response_payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {
            "status": "ignored",
            "reason": "malformed_response",
            "response_hash": response_hash,
        }

    receipt = _select_mobitech_receipt(response_payload, message_id=message_id)
    if not receipt and status_url.rstrip("/").rsplit("/", 1)[-1].lower() == "stats":
        receipt = _stats_response_as_receipt(response_payload, message_id=message_id)
    if not receipt:
        return {
            "status": "ignored",
            "reason": "receipt_not_found",
            "response_hash": response_hash,
        }
    delivery_status = _delivery_status_from_payload(receipt)
    if not delivery_status:
        return {
            "status": "ignored",
            "reason": "unsupported_status",
            "response_hash": response_hash,
        }

    # A polling response may have one stable provider message id across status
    # transitions. Make the status plus response hash the event identity so a
    # repeated poll is idempotent while a later status is still reconciled.
    provider_event_id = f"poll-{_sha256(f'{message_id}:{delivery_status}:{response_hash}')[:40]}"
    callback_payload = {
        "provider_event_id": provider_event_id,
        "provider_message_id": message_id,
        "client_ref": _first_value(receipt, "client_ref", "clientRef", "idempotency_key"),
        "status": delivery_status,
        "status_code": _first_value(receipt, "status", "status_code", "statusCode"),
        "statusDescription": _first_value(receipt, "statusDescription", "status_description", "description"),
        "subscriber": _first_value(receipt, "subscriber", "mobile", "phone", "to", "destination"),
        "dateModified": _first_value(receipt, "dateModified", "date_modified", "timestamp"),
    }
    result = process_mobitech_delivery_callback(
        callback_payload,
        reconciliation_method="polling",
    )
    result["response_hash"] = response_hash
    return result


def _find_alert(*, provider_message_id: str, client_ref: str) -> Alert | None:
    clauses = []
    if provider_message_id:
        clauses.extend([Q(provider_message_id=provider_message_id), Q(external_id=provider_message_id)])
    if client_ref:
        try:
            clauses.append(Q(idempotency_key=uuid.UUID(client_ref)))
        except (ValueError, AttributeError):
            try:
                clauses.append(Q(pk=int(client_ref)))
            except (TypeError, ValueError):
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
    reconciliation_method: str,
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
        "reconciliation_method": reconciliation_method if reconciliation_method in {"callback", "polling"} else "callback",
        "status_code": status_code,
        "status_description_hash": _sha256(status_description),
        "destination_hash": _sha256(destination),
        "timestamp": timestamp,
    }


def _normalise_delivery_status(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    if normalized in {
        "delivered",
        "delivered_to_terminal",
        "deliveredterminal",
        "delivery_success",
        "success",
        "successful",
        "dlvrd",
        "1",
    }:
        return Alert.PROVIDER_DELIVERY_DELIVERED
    if normalized in {
        "failed",
        "failure",
        "undelivered",
        "not_delivered",
        "notdelivered",
        "delivery_failed",
        "failed_to_deliver",
        "undeliverable",
        "rejected",
        "expired",
        "blocked",
        "0",
    }:
        return Alert.PROVIDER_DELIVERY_FAILED
    if normalized in {
        "pending",
        "queued",
        "scheduled",
        "sent",
        "submitted",
        "accepted",
        "in_progress",
        "2",
    }:
        return Alert.PROVIDER_DELIVERY_PENDING
    return ""


def _delivery_status_from_payload(payload: dict[str, Any]) -> str:
    for key in (
        "status",
        "delivery_status",
        "statusDescription",
        "status_description",
        "schedule_status",
    ):
        status = _normalise_delivery_status(payload.get(key))
        if status:
            return status
    return ""


def _select_mobitech_receipt(payload: Any, *, message_id: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return
        if any(
            key in value
            for key in (
                "status",
                "delivery_status",
                "statusDescription",
                "status_description",
                "schedule_status",
            )
        ):
            candidates.append(value)
        for key in ("receipts", "receipt", "data", "results", "messages"):
            nested = value.get(key)
            if isinstance(nested, (dict, list)):
                visit(nested)

    visit(payload)
    matching = [
        item
        for item in candidates
        if _first_value(item, "smsId", "sms_id", "message_id", "messageId", "id") == message_id
    ]
    if len(matching) == 1:
        return matching[0]
    return candidates[0] if len(candidates) == 1 else {}


def _stats_response_as_receipt(payload: Any, *, message_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    try:
        delivered = int(payload.get("delivered"))
        total_sent = int(payload.get("totalSent"))
    except (TypeError, ValueError):
        return {}
    if total_sent <= 0 or delivered < 0:
        return {}
    status = Alert.PROVIDER_DELIVERY_DELIVERED if delivered >= total_sent else Alert.PROVIDER_DELIVERY_PENDING
    return {
        "smsId": message_id,
        "status": status,
        "statusDescription": "Delivered" if status == Alert.PROVIDER_DELIVERY_DELIVERED else "Pending",
    }


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
