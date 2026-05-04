from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, Iterable

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, QuerySet
from django.utils import timezone

from .models import (
    Alert,
    CHVCoverageRequestEmailDelivery,
    CHVMessage,
    ContactPreference,
    ContactPreferenceAuditEvent,
    PreparednessAction,
    PreparednessActionEvent,
    PrivacyRetentionAuditEvent,
    PrivacyRetentionHold,
    SensitiveExportRequest,
    SyncQueue,
    TriageSession,
    UssdSessionLog,
)

logger = logging.getLogger(__name__)

REDACTED_CONTACT_VALUE = "retention-redacted"
REDACTED_TEXT_VALUE = "[redacted by privacy retention]"
REDACTED_EMAIL_VALUE = ""


@dataclass(frozen=True)
class RetentionRule:
    key: str
    model: type
    window_days: int
    date_field: str
    description: str
    queryset_factory: Callable[[timezone.datetime], QuerySet]
    anonymizer: Callable[[object, timezone.datetime], dict]

    @property
    def model_label(self) -> str:
        return self.model._meta.label


def _iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _value_summary(value) -> dict:
    if value in (None, "", {}, []):
        return {"present": False}
    return {"present": True, "length": len(str(value))}


def _json_summary(value) -> dict:
    if not value:
        return {"present": False, "keys": []}
    if isinstance(value, dict):
        return {"present": True, "keys": sorted(str(key) for key in value.keys())[:40]}
    if isinstance(value, list):
        return {"present": True, "items": len(value)}
    return _value_summary(value)


def _redacted_payload_summary(value, *, redacted_at) -> dict:
    summary = _json_summary(value)
    return {
        "retention_redacted": True,
        "redacted_at": _iso(redacted_at),
        "previous_shape": summary,
    }


def _save(obj, fields: Iterable[str]) -> None:
    update_fields = list(dict.fromkeys(fields))
    if hasattr(obj, "updated_at") and "updated_at" not in update_fields:
        update_fields.append("updated_at")
    obj.save(update_fields=update_fields)


def _already_redacted_json(value) -> bool:
    return isinstance(value, dict) and value.get("retention_redacted") is True


def _sync_queryset(cutoff):
    return SyncQueue.objects.filter(status=SyncQueue.STATUS_PROCESSED, processed_at__lt=cutoff)


def _anonymize_sync_queue(obj: SyncQueue, now) -> dict:
    before = {
        "phone_number": _value_summary(obj.phone_number),
        "payload": _json_summary(obj.payload),
        "error_message": _value_summary(obj.error_message),
    }
    if not obj.phone_number and _already_redacted_json(obj.payload) and not obj.error_message:
        return {"updated": False, "reason": "sync payload already redacted", "before_state": before}

    aggregate_metrics = {
        "ward_id": obj.ward_id,
        "status": obj.status,
        "processed_at": _iso(obj.processed_at),
        "triage_session_id": obj.triage_session_id,
    }
    obj.phone_number = ""
    obj.payload = _redacted_payload_summary(obj.payload, redacted_at=now)
    obj.error_message = "" if obj.error_message else obj.error_message
    _save(obj, ["phone_number", "payload", "error_message"])
    return {
        "updated": True,
        "before_state": before,
        "after_state": {
            "phone_number": _value_summary(obj.phone_number),
            "payload": _json_summary(obj.payload),
            "error_message": _value_summary(obj.error_message),
        },
        "aggregate_metrics": aggregate_metrics,
        "reason": "processed sync raw envelope redacted after retention window",
    }


def _triage_queryset(cutoff):
    return TriageSession.objects.filter(created_at__lt=cutoff).filter(Q(phone_number__gt="") | Q(text_input__gt=""))


def _anonymize_triage_session(obj: TriageSession, now) -> dict:
    before = {"phone_number": _value_summary(obj.phone_number), "text_input": _value_summary(obj.text_input)}
    aggregate_metrics = {
        "ward_id": obj.ward_id,
        "channel": obj.channel,
        "diarrhea": obj.diarrhea,
        "vomiting": obj.vomiting,
        "dehydration": obj.dehydration,
        "fever": obj.fever,
        "referral_needed": obj.referral_needed,
        "created_at": _iso(obj.created_at),
    }
    obj.phone_number = ""
    obj.text_input = ""
    _save(obj, ["phone_number", "text_input"])
    return {
        "updated": True,
        "before_state": before,
        "after_state": {"phone_number": _value_summary(obj.phone_number), "text_input": _value_summary(obj.text_input)},
        "aggregate_metrics": aggregate_metrics,
        "reason": "triage direct identifiers redacted after retention window",
    }


def _ussd_queryset(cutoff):
    return UssdSessionLog.objects.filter(created_at__lt=cutoff).filter(
        Q(phone_number__gt="") | Q(text__gt="") | Q(response_text__gt="")
    )


def _anonymize_ussd_log(obj: UssdSessionLog, now) -> dict:
    before = {
        "phone_number": _value_summary(obj.phone_number),
        "text": _value_summary(obj.text),
        "response_text": _value_summary(obj.response_text),
    }
    aggregate_metrics = {
        "ward_id": obj.ward_id,
        "menu_level": obj.menu_level,
        "service_code": obj.service_code,
        "created_at": _iso(obj.created_at),
    }
    obj.phone_number = ""
    obj.text = REDACTED_TEXT_VALUE if obj.text else ""
    obj.response_text = REDACTED_TEXT_VALUE if obj.response_text else ""
    _save(obj, ["phone_number", "text", "response_text"])
    return {
        "updated": True,
        "before_state": before,
        "after_state": {
            "phone_number": _value_summary(obj.phone_number),
            "text": _value_summary(obj.text),
            "response_text": _value_summary(obj.response_text),
        },
        "aggregate_metrics": aggregate_metrics,
        "reason": "USSD draft text and direct identifiers redacted after retention window",
    }


def _alert_queryset(cutoff):
    return Alert.objects.filter(
        status__in=[Alert.STATUS_DELIVERED, Alert.STATUS_FAILED],
        created_at__lt=cutoff,
    ).exclude(recipient=REDACTED_CONTACT_VALUE)


def _anonymize_alert(obj: Alert, now) -> dict:
    before = {
        "recipient": _value_summary(obj.recipient),
        "message": _value_summary(obj.message),
        "external_id": _value_summary(obj.external_id),
        "error_message": _value_summary(obj.error_message),
        "guided_request_metadata": _json_summary(obj.guided_request_metadata),
    }
    aggregate_metrics = {
        "ward_id": obj.ward_id,
        "channel": obj.channel,
        "status": obj.status,
        "attempt_count": obj.attempt_count,
        "max_attempts": obj.max_attempts,
        "created_at": _iso(obj.created_at),
        "sent_at": _iso(obj.sent_at),
    }
    obj.recipient = REDACTED_CONTACT_VALUE
    obj.message = REDACTED_TEXT_VALUE
    obj.external_id = ""
    obj.error_message = ""
    obj.guided_request_metadata = _redacted_payload_summary(obj.guided_request_metadata, redacted_at=now)
    _save(obj, ["recipient", "message", "external_id", "error_message", "guided_request_metadata"])
    return {
        "updated": True,
        "before_state": before,
        "after_state": {
            "recipient": _value_summary(obj.recipient),
            "message": _value_summary(obj.message),
            "external_id": _value_summary(obj.external_id),
            "error_message": _value_summary(obj.error_message),
            "guided_request_metadata": _json_summary(obj.guided_request_metadata),
        },
        "aggregate_metrics": aggregate_metrics,
        "reason": "alert delivery direct identifiers redacted after retention window",
    }


def _chv_message_queryset(cutoff):
    return CHVMessage.objects.filter(created_at__lt=cutoff).exclude(message_body=REDACTED_TEXT_VALUE)


def _anonymize_chv_message(obj: CHVMessage, now) -> dict:
    before = {
        "message_body": _value_summary(obj.message_body),
        "provider_reference": _value_summary(obj.provider_reference),
        "failure_reason": _value_summary(obj.failure_reason),
    }
    aggregate_metrics = {
        "ward_id": obj.ward_id,
        "chv_id": obj.chv_id,
        "channel": obj.channel,
        "status": obj.status,
        "delivery_kind": obj.delivery_kind,
        "created_at": _iso(obj.created_at),
    }
    obj.message_body = REDACTED_TEXT_VALUE
    obj.provider_reference = ""
    obj.failure_reason = ""
    _save(obj, ["message_body", "provider_reference", "failure_reason"])
    return {
        "updated": True,
        "before_state": before,
        "after_state": {
            "message_body": _value_summary(obj.message_body),
            "provider_reference": _value_summary(obj.provider_reference),
            "failure_reason": _value_summary(obj.failure_reason),
        },
        "aggregate_metrics": aggregate_metrics,
        "reason": "CHV delivery log content redacted after retention window",
    }


def _email_delivery_queryset(cutoff):
    return CHVCoverageRequestEmailDelivery.objects.filter(created_at__lt=cutoff).filter(
        Q(recipient_email__gt="") | Q(external_id__gt="") | Q(error_message__gt="") | ~Q(metadata={})
    )


def _anonymize_email_delivery(obj: CHVCoverageRequestEmailDelivery, now) -> dict:
    before = {
        "recipient_email": _value_summary(obj.recipient_email),
        "external_id": _value_summary(obj.external_id),
        "error_message": _value_summary(obj.error_message),
        "metadata": _json_summary(obj.metadata),
    }
    aggregate_metrics = {
        "coverage_request_id": obj.coverage_request_id,
        "status": obj.status,
        "delivery_backend": obj.delivery_backend,
        "created_at": _iso(obj.created_at),
    }
    obj.recipient_email = REDACTED_EMAIL_VALUE
    obj.external_id = ""
    obj.error_message = ""
    obj.metadata = _redacted_payload_summary(obj.metadata, redacted_at=now)
    _save(obj, ["recipient_email", "external_id", "error_message", "metadata"])
    return {
        "updated": True,
        "before_state": before,
        "after_state": {
            "recipient_email": _value_summary(obj.recipient_email),
            "external_id": _value_summary(obj.external_id),
            "error_message": _value_summary(obj.error_message),
            "metadata": _json_summary(obj.metadata),
        },
        "aggregate_metrics": aggregate_metrics,
        "reason": "coverage request email delivery identifiers redacted after retention window",
    }


def _household_action_queryset(cutoff):
    return PreparednessAction.objects.filter(
        action_type=PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE,
        status__in=PreparednessAction.CLOSED_STATUSES,
        updated_at__lt=cutoff,
    ).filter(Q(notes__gt="") | ~Q(completion_evidence={}) | ~Q(lineage_metadata={}) | ~Q(escalation_metadata={}))


def _anonymize_household_action(obj: PreparednessAction, now) -> dict:
    before = {
        "notes": _value_summary(obj.notes),
        "completion_evidence": _json_summary(obj.completion_evidence),
        "lineage_metadata": _json_summary(obj.lineage_metadata),
        "escalation_metadata": _json_summary(obj.escalation_metadata),
    }
    aggregate_metrics = {
        "ward_id": obj.ward_id,
        "status": obj.status,
        "priority": obj.priority,
        "completed_at": _iso(obj.completed_at),
        "source_trigger_type": obj.source_trigger_type,
    }
    obj.notes = ""
    obj.completion_evidence = _redacted_payload_summary(obj.completion_evidence, redacted_at=now)
    obj.lineage_metadata = _redacted_payload_summary(obj.lineage_metadata, redacted_at=now)
    obj.escalation_metadata = _redacted_payload_summary(obj.escalation_metadata, redacted_at=now)
    _save(obj, ["notes", "completion_evidence", "lineage_metadata", "escalation_metadata"])
    return {
        "updated": True,
        "before_state": before,
        "after_state": {
            "notes": _value_summary(obj.notes),
            "completion_evidence": _json_summary(obj.completion_evidence),
            "lineage_metadata": _json_summary(obj.lineage_metadata),
            "escalation_metadata": _json_summary(obj.escalation_metadata),
        },
        "aggregate_metrics": aggregate_metrics,
        "reason": "household prevention evidence redacted after retention window",
    }


def _household_action_event_queryset(cutoff):
    return PreparednessActionEvent.objects.filter(
        preparedness_action__action_type=PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE,
        preparedness_action__status__in=PreparednessAction.CLOSED_STATUSES,
        created_at__lt=cutoff,
    ).filter(Q(detail__gt="") | ~Q(metadata={}))


def _anonymize_household_action_event(obj: PreparednessActionEvent, now) -> dict:
    before = {"detail": _value_summary(obj.detail), "metadata": _json_summary(obj.metadata)}
    aggregate_metrics = {
        "preparedness_action_id": obj.preparedness_action_id,
        "event_type": obj.event_type,
        "old_status": obj.old_status,
        "new_status": obj.new_status,
        "created_at": _iso(obj.created_at),
    }
    obj.detail = ""
    obj.metadata = _redacted_payload_summary(obj.metadata, redacted_at=now)
    _save(obj, ["detail", "metadata"])
    return {
        "updated": True,
        "before_state": before,
        "after_state": {"detail": _value_summary(obj.detail), "metadata": _json_summary(obj.metadata)},
        "aggregate_metrics": aggregate_metrics,
        "reason": "household prevention event detail redacted after retention window",
    }


def _expired_contact_preference_queryset(cutoff):
    return ContactPreference.objects.filter(expires_at__lt=cutoff).filter(
        Q(phone_number__gt="") | Q(source_reference__gt="") | ~Q(metadata={})
    )


def _anonymize_expired_contact_preference(obj: ContactPreference, now) -> dict:
    before = {
        "phone_number": _value_summary(obj.phone_number),
        "contact_reference": _value_summary(obj.contact_reference),
        "source_reference": _value_summary(obj.source_reference),
        "metadata": _json_summary(obj.metadata),
    }
    aggregate_metrics = {
        "audience_type": obj.audience_type,
        "channel": obj.channel,
        "consent_status": obj.consent_status,
        "opt_out_status": obj.opt_out_status,
        "recorded_at": _iso(obj.recorded_at),
        "expires_at": _iso(obj.expires_at),
    }
    obj.phone_number = ""
    if not obj.contact_reference:
        obj.contact_reference = f"retention-redacted:{obj.public_id}"
    obj.source_reference = ""
    obj.metadata = _redacted_payload_summary(obj.metadata, redacted_at=now)
    _save(obj, ["phone_number", "contact_reference", "source_reference", "metadata"])
    return {
        "updated": True,
        "before_state": before,
        "after_state": {
            "phone_number": _value_summary(obj.phone_number),
            "contact_reference": _value_summary(obj.contact_reference),
            "source_reference": _value_summary(obj.source_reference),
            "metadata": _json_summary(obj.metadata),
        },
        "aggregate_metrics": aggregate_metrics,
        "reason": "expired contact preference identifiers redacted after retention window",
    }


def _contact_audit_queryset(cutoff):
    return ContactPreferenceAuditEvent.objects.filter(created_at__lt=cutoff).filter(
        Q(phone_number__gt="") | Q(contact_reference__gt="") | ~Q(metadata={})
    )


def _anonymize_contact_audit_event(obj: ContactPreferenceAuditEvent, now) -> dict:
    before = {
        "phone_number": _value_summary(obj.phone_number),
        "contact_reference": _value_summary(obj.contact_reference),
        "metadata": _json_summary(obj.metadata),
    }
    aggregate_metrics = {
        "action": obj.action,
        "audience_type": obj.audience_type,
        "channel": obj.channel,
        "created_at": _iso(obj.created_at),
    }
    obj.phone_number = ""
    obj.contact_reference = ""
    obj.metadata = _redacted_payload_summary(obj.metadata, redacted_at=now)
    _save(obj, ["phone_number", "contact_reference", "metadata"])
    return {
        "updated": True,
        "before_state": before,
        "after_state": {
            "phone_number": _value_summary(obj.phone_number),
            "contact_reference": _value_summary(obj.contact_reference),
            "metadata": _json_summary(obj.metadata),
        },
        "aggregate_metrics": aggregate_metrics,
        "reason": "contact preference audit identifiers redacted after retention window",
    }


def _sensitive_export_queryset(cutoff):
    return SensitiveExportRequest.objects.filter(
        expires_at__lt=cutoff,
        generated_payload__gt="",
    )


def _anonymize_sensitive_export(obj: SensitiveExportRequest, now) -> dict:
    before = {
        "generated_payload": _value_summary(obj.generated_payload),
        "generated_filename": _value_summary(obj.generated_filename),
    }
    aggregate_metrics = {
        "export_type": obj.export_type,
        "requester_id": obj.requester_id,
        "approval_state": obj.approval_state,
        "row_count": obj.row_count,
        "download_count": obj.download_count,
        "generated_at": _iso(obj.generated_at),
        "expires_at": _iso(obj.expires_at),
        "payload_sha256": obj.payload_sha256,
    }
    obj.generated_payload = ""
    obj.approval_state = SensitiveExportRequest.APPROVAL_EXPIRED
    obj.save(update_fields=["generated_payload", "approval_state", "updated_at"])
    return {
        "updated": True,
        "before_state": before,
        "after_state": {
            "generated_payload": _value_summary(obj.generated_payload),
            "generated_filename": _value_summary(obj.generated_filename),
        },
        "aggregate_metrics": aggregate_metrics,
        "reason": "expired sensitive export payload cleared after expiry",
    }


RETENTION_RULES: tuple[RetentionRule, ...] = (
    RetentionRule(
        key="sync_payload_raw_envelopes",
        model=SyncQueue,
        window_days=30,
        date_field="processed_at",
        description="Processed offline sync payloads keep processing state but lose raw envelope and phone fields.",
        queryset_factory=_sync_queryset,
        anonymizer=_anonymize_sync_queue,
    ),
    RetentionRule(
        key="triage_field_details",
        model=TriageSession,
        window_days=180,
        date_field="created_at",
        description="Triage records keep ward, channel, symptom flags, and referral outcome while losing direct identifiers.",
        queryset_factory=_triage_queryset,
        anonymizer=_anonymize_triage_session,
    ),
    RetentionRule(
        key="triage_draft_ussd_logs",
        model=UssdSessionLog,
        window_days=30,
        date_field="created_at",
        description="USSD draft/session text is short lived and redacted after troubleshooting usefulness expires.",
        queryset_factory=_ussd_queryset,
        anonymizer=_anonymize_ussd_log,
    ),
    RetentionRule(
        key="alert_delivery_logs",
        model=Alert,
        window_days=365,
        date_field="created_at",
        description="Terminal alert delivery rows retain channel/status/ward aggregates but lose recipient and message content.",
        queryset_factory=_alert_queryset,
        anonymizer=_anonymize_alert,
    ),
    RetentionRule(
        key="chv_message_delivery_logs",
        model=CHVMessage,
        window_days=365,
        date_field="created_at",
        description="CHV delivery rows retain operational delivery metrics but lose message and provider identifiers.",
        queryset_factory=_chv_message_queryset,
        anonymizer=_anonymize_chv_message,
    ),
    RetentionRule(
        key="coverage_email_delivery_logs",
        model=CHVCoverageRequestEmailDelivery,
        window_days=365,
        date_field="created_at",
        description="Coverage email delivery rows retain status/backend metrics but lose recipient email and provider identifiers.",
        queryset_factory=_email_delivery_queryset,
        anonymizer=_anonymize_email_delivery,
    ),
    RetentionRule(
        key="household_prevention_submissions",
        model=PreparednessAction,
        window_days=180,
        date_field="updated_at",
        description="Closed household-prevention actions retain ledger status but lose narrative evidence and lineage payloads.",
        queryset_factory=_household_action_queryset,
        anonymizer=_anonymize_household_action,
    ),
    RetentionRule(
        key="household_prevention_submission_events",
        model=PreparednessActionEvent,
        window_days=180,
        date_field="created_at",
        description="Closed household-prevention action events retain status transitions but lose narrative detail and metadata values.",
        queryset_factory=_household_action_event_queryset,
        anonymizer=_anonymize_household_action_event,
    ),
    RetentionRule(
        key="expired_contact_preferences",
        model=ContactPreference,
        window_days=365,
        date_field="expires_at",
        description="Expired contact preferences retain audience/channel consent state but lose phone and source reference details.",
        queryset_factory=_expired_contact_preference_queryset,
        anonymizer=_anonymize_expired_contact_preference,
    ),
    RetentionRule(
        key="contact_preference_audit_contacts",
        model=ContactPreferenceAuditEvent,
        window_days=365,
        date_field="created_at",
        description="Contact preference audit events retain decision counts while losing direct contact identifiers.",
        queryset_factory=_contact_audit_queryset,
        anonymizer=_anonymize_contact_audit_event,
    ),
    RetentionRule(
        key="sensitive_exports",
        model=SensitiveExportRequest,
        window_days=0,
        date_field="expires_at",
        description="Expired sensitive export payloads are cleared immediately while attribution, approval, hash, and counts remain.",
        queryset_factory=_sensitive_export_queryset,
        anonymizer=_anonymize_sensitive_export,
    ),
)

SENSITIVE_EXPORT_RETENTION_POLICY = {
    "key": "sensitive_exports",
    "window_days": 30,
    "date_field": "expires_at",
    "description": "Sensitive export payloads expire after 30 days and are cleared by the sensitive_exports retention rule.",
    "model_label": "risk.SensitiveExportRequest",
    "status": "implemented",
}


def retention_policy_summary() -> dict:
    return {
        "rules": [
            {
                "key": rule.key,
                "model_label": rule.model_label,
                "window_days": rule.window_days,
                "date_field": rule.date_field,
                "description": rule.description,
            }
            for rule in RETENTION_RULES
        ],
        "sensitive_exports": SENSITIVE_EXPORT_RETENTION_POLICY,
    }


def _active_holds_for_objects(model: type, object_ids: Iterable[str], now) -> dict[str, PrivacyRetentionHold]:
    ids = [str(object_id) for object_id in object_ids]
    if not ids:
        return {}
    content_type = ContentType.objects.get_for_model(model)
    holds = (
        PrivacyRetentionHold.objects.filter(
            content_type=content_type,
            object_id__in=ids,
            is_active=True,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .order_by("-created_at")
    )
    return {hold.object_id: hold for hold in holds}


def _audit_event(
    *,
    run_id,
    action,
    rule: RetentionRule | None,
    dry_run: bool,
    actor=None,
    obj=None,
    hold=None,
    cutoff_at=None,
    decision_reason="",
    before_state=None,
    after_state=None,
    aggregate_metrics=None,
    record_events: bool,
) -> None:
    model_label = rule.model_label if rule else ""
    object_id = str(obj.pk) if obj is not None else ""
    record_family = rule.key if rule else "privacy_retention_run"
    payload = {
        "run_id": str(run_id),
        "action": action,
        "record_family": record_family,
        "model_label": model_label,
        "object_id": object_id,
        "dry_run": dry_run,
        "decision_reason": decision_reason,
    }
    logger.info("privacy_retention_decision", extra=payload)
    if not record_events:
        return

    PrivacyRetentionAuditEvent.objects.create(
        run_id=run_id,
        action=action,
        record_family=record_family,
        model_label=model_label,
        object_id=object_id,
        cutoff_at=cutoff_at,
        window_days=rule.window_days if rule else None,
        dry_run=dry_run,
        hold=hold,
        actor=actor,
        decision_reason=decision_reason,
        before_state=before_state or {},
        after_state=after_state or {},
        aggregate_metrics=aggregate_metrics or {},
    )


def _apply_rule(
    rule: RetentionRule,
    *,
    run_id,
    now,
    dry_run: bool,
    actor=None,
    batch_size: int = 500,
    record_events: bool = True,
) -> dict:
    cutoff = now - timedelta(days=rule.window_days)
    candidates = list(rule.queryset_factory(cutoff).order_by("id")[:batch_size])
    holds = _active_holds_for_objects(rule.model, [str(obj.pk) for obj in candidates], now)
    summary = {
        "key": rule.key,
        "model_label": rule.model_label,
        "window_days": rule.window_days,
        "cutoff_at": _iso(cutoff),
        "candidates": len(candidates),
        "dry_run": dry_run,
        "anonymized": 0,
        "deleted": 0,
        "held": 0,
        "skipped": 0,
        "aggregate_metrics_preserved": [],
    }

    for obj in candidates:
        hold = holds.get(str(obj.pk))
        if hold:
            summary["held"] += 1
            _audit_event(
                run_id=run_id,
                action=PrivacyRetentionAuditEvent.ACTION_HELD,
                rule=rule,
                dry_run=dry_run,
                actor=actor,
                obj=obj,
                hold=hold,
                cutoff_at=cutoff,
                decision_reason="active legal or investigation hold",
                record_events=record_events,
            )
            continue

        if dry_run:
            summary["skipped"] += 1
            _audit_event(
                run_id=run_id,
                action=PrivacyRetentionAuditEvent.ACTION_DRY_RUN,
                rule=rule,
                dry_run=dry_run,
                actor=actor,
                obj=obj,
                cutoff_at=cutoff,
                decision_reason="dry run candidate identified",
                record_events=record_events,
            )
            continue

        result = rule.anonymizer(obj, now)
        action = (
            PrivacyRetentionAuditEvent.ACTION_ANONYMIZED
            if result.get("updated")
            else PrivacyRetentionAuditEvent.ACTION_SKIPPED
        )
        if result.get("updated"):
            summary["anonymized"] += 1
        else:
            summary["skipped"] += 1
        if result.get("aggregate_metrics"):
            summary["aggregate_metrics_preserved"].append(result["aggregate_metrics"])
        _audit_event(
            run_id=run_id,
            action=action,
            rule=rule,
            dry_run=dry_run,
            actor=actor,
            obj=obj,
            cutoff_at=cutoff,
            decision_reason=result.get("reason", ""),
            before_state=result.get("before_state", {}),
            after_state=result.get("after_state", {}),
            aggregate_metrics=result.get("aggregate_metrics", {}),
            record_events=record_events,
        )

    _audit_event(
        run_id=run_id,
        action=PrivacyRetentionAuditEvent.ACTION_SUMMARY,
        rule=rule,
        dry_run=dry_run,
        actor=actor,
        cutoff_at=cutoff,
        decision_reason="retention rule summary",
        aggregate_metrics={
            key: value
            for key, value in summary.items()
            if key not in {"aggregate_metrics_preserved"}
        },
        record_events=record_events,
    )
    return summary


def apply_privacy_retention(
    *,
    now=None,
    dry_run: bool = True,
    actor=None,
    batch_size: int = 500,
    families: Iterable[str] | None = None,
    record_events: bool | None = None,
) -> dict:
    now = now or timezone.now()
    run_id = uuid.uuid4()
    selected_families = set(families or [])
    rule_by_key = {rule.key: rule for rule in RETENTION_RULES}
    unknown = selected_families - set(rule_by_key.keys())
    if unknown:
        raise ValueError(f"Unknown retention family: {', '.join(sorted(unknown))}")
    rules = [rule for rule in RETENTION_RULES if not selected_families or rule.key in selected_families]
    should_record_events = (not dry_run) if record_events is None else record_events

    summary = {
        "run_id": str(run_id),
        "generated_at": _iso(now),
        "dry_run": dry_run,
        "batch_size": batch_size,
        "rules": [],
        "sensitive_exports": SENSITIVE_EXPORT_RETENTION_POLICY,
        "totals": {
            "candidates": 0,
            "anonymized": 0,
            "deleted": 0,
            "held": 0,
            "skipped": 0,
        },
    }
    for rule in rules:
        rule_summary = _apply_rule(
            rule,
            run_id=run_id,
            now=now,
            dry_run=dry_run,
            actor=actor,
            batch_size=batch_size,
            record_events=should_record_events,
        )
        summary["rules"].append(rule_summary)
        for key in summary["totals"]:
            summary["totals"][key] += rule_summary[key]

    _audit_event(
        run_id=run_id,
        action=PrivacyRetentionAuditEvent.ACTION_SUMMARY,
        rule=None,
        dry_run=dry_run,
        actor=actor,
        decision_reason="privacy retention run summary",
        aggregate_metrics=summary["totals"],
        record_events=should_record_events,
    )
    return summary
