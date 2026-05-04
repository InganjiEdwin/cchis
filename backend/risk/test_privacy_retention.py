import json
from datetime import timedelta
from io import StringIO

from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import User

from .models import (
    Alert,
    CHV,
    CHVMessage,
    ContactPreference,
    ContactPreferenceAuditEvent,
    PreparednessAction,
    PreparednessActionEvent,
    PrivacyRetentionAuditEvent,
    PrivacyRetentionHold,
    SyncQueue,
    TriageSession,
    UssdSessionLog,
    Ward,
)
from .privacy_retention import REDACTED_CONTACT_VALUE, REDACTED_TEXT_VALUE, apply_privacy_retention


class PrivacyRetentionTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.old_timestamp = self.now - timedelta(days=400)
        self.ward = Ward.objects.create(
            name="Retention Ward",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.91,
            is_active=True,
        )
        self.admin_user = User.objects.create_user(
            username="retention_admin",
            password="ChangeMe123!",
            email="retention-admin@example.com",
            role=User.ROLE_ADMIN,
            ward=self.ward,
            is_active=True,
        )
        self.chv = CHV.objects.create(
            name="Retention CHV",
            phone_number="+254700777001",
            ward=self.ward,
            language="en",
            is_active=True,
        )

    def _age(self, obj, **fields):
        values = {"created_at": self.old_timestamp}
        values.update(fields)
        obj.__class__.objects.filter(pk=obj.pk).update(**values)
        obj.refresh_from_db()
        return obj

    def test_retention_anonymizes_old_sensitive_records_but_keeps_aggregates(self):
        alert = self._age(
            Alert.objects.create(
                ward=self.ward,
                channel=Alert.CHANNEL_SMS,
                recipient="+254700777002",
                message="Household prevention SMS content.",
                status=Alert.STATUS_DELIVERED,
                delivery_backend="africastalking",
                attempt_count=2,
                max_attempts=3,
                sent_at=self.old_timestamp,
                external_id="provider-alert-1",
                guided_request_metadata={"preview_text": "Household prevention SMS content."},
            ),
            sent_at=self.old_timestamp,
        )
        triage = self._age(
            TriageSession.objects.create(
                channel="API",
                phone_number="+254700777003",
                ward=self.ward,
                text_input="Caller reports diarrhoea and vomiting.",
                diarrhea=True,
                vomiting=True,
                referral_needed=True,
            )
        )
        sync_item = self._age(
            SyncQueue.objects.create(
                source_device_id="retention-device",
                client_submission_id="retention-submission-1",
                phone_number="+254700777004",
                ward=self.ward,
                triage_session=triage,
                payload={"phone_number": "+254700777004", "diarrhea": True, "household_note": "follow up"},
                status=SyncQueue.STATUS_PROCESSED,
                processed_at=self.old_timestamp,
                error_message="raw processing note",
            ),
            processed_at=self.old_timestamp,
        )
        ussd_log = self._age(
            UssdSessionLog.objects.create(
                session_id="retention-ussd-1",
                phone_number="+254700777005",
                service_code="*123#",
                text="1*household follow up",
                response_text="Report received.",
                ward=self.ward,
                menu_level="triage",
            )
        )
        chv_message = self._age(
            CHVMessage.objects.create(
                chv=self.chv,
                ward=self.ward,
                sent_by=self.admin_user,
                message_body="Please visit the household and confirm prevention messages.",
                status=CHVMessage.STATUS_DELIVERED,
                delivery_kind=CHVMessage.DELIVERY_KIND_LIVE,
                delivery_backend="africastalking",
                provider_reference="provider-chv-msg-1",
            ),
            updated_at=self.old_timestamp,
        )
        action = self._age(
            PreparednessAction.objects.create(
                action_type=PreparednessAction.ACTION_HOUSEHOLD_PREVENTION_MESSAGE,
                source_trigger_type=PreparednessAction.SOURCE_SYSTEM,
                source_trigger_ref="retention-household-action",
                ward=self.ward,
                status=PreparednessAction.STATUS_COMPLETED,
                priority=PreparednessAction.PRIORITY_HIGH,
                created_by=self.admin_user,
                completion_evidence={"summary": "Household reached by CHV.", "contact_phone": "+254700777006"},
                lineage_metadata={"source": "manual_note", "household_ref": "HH-1"},
                notes="Household prevention message completed.",
                completed_at=self.old_timestamp,
            ),
            updated_at=self.old_timestamp,
            completed_at=self.old_timestamp,
        )
        action_event = self._age(
            PreparednessActionEvent.objects.create(
                preparedness_action=action,
                actor=self.admin_user,
                event_type=PreparednessActionEvent.EVENT_COMPLETED,
                detail="Household prevention action completed after call.",
                metadata={"contact_phone": "+254700777006"},
            )
        )
        preference = ContactPreference.objects.create(
            audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="+254700777007",
            consent_status=ContactPreference.CONSENT_EXPIRED,
            opt_out_status=ContactPreference.OPT_OUT_NOT_OPTED_OUT,
            source="household_consent",
            source_reference="consent-form-retention",
            recorded_by=self.admin_user,
            recorded_at=self.old_timestamp,
            expires_at=self.old_timestamp,
            metadata={"collector": "field-team"},
        )
        ContactPreference.objects.filter(pk=preference.pk).update(created_at=self.old_timestamp, updated_at=self.old_timestamp)
        audit_event = self._age(
            ContactPreferenceAuditEvent.objects.create(
                preference=preference,
                action=ContactPreferenceAuditEvent.ACTION_ALLOWED,
                audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
                channel=ContactPreference.CHANNEL_SMS,
                phone_number="+254700777007",
                contact_reference="household:retention",
                actor=self.admin_user,
                reason="consent checked",
                metadata={"recipient": "+254700777007"},
            )
        )

        summary = apply_privacy_retention(now=self.now, dry_run=False, actor=self.admin_user)

        self.assertEqual(summary["totals"]["anonymized"], 9)
        self.assertEqual(summary["totals"]["held"], 0)

        alert.refresh_from_db()
        self.assertEqual(alert.recipient, REDACTED_CONTACT_VALUE)
        self.assertEqual(alert.message, REDACTED_TEXT_VALUE)
        self.assertEqual(alert.channel, Alert.CHANNEL_SMS)
        self.assertEqual(alert.status, Alert.STATUS_DELIVERED)
        self.assertEqual(alert.attempt_count, 2)

        triage.refresh_from_db()
        self.assertEqual(triage.phone_number, "")
        self.assertEqual(triage.text_input, "")
        self.assertTrue(triage.diarrhea)
        self.assertTrue(triage.vomiting)
        self.assertTrue(triage.referral_needed)

        sync_item.refresh_from_db()
        self.assertEqual(sync_item.phone_number, "")
        self.assertTrue(sync_item.payload["retention_redacted"])
        self.assertEqual(sync_item.status, SyncQueue.STATUS_PROCESSED)
        self.assertEqual(sync_item.ward, self.ward)

        ussd_log.refresh_from_db()
        self.assertEqual(ussd_log.phone_number, "")
        self.assertEqual(ussd_log.text, REDACTED_TEXT_VALUE)
        self.assertEqual(ussd_log.menu_level, "triage")

        chv_message.refresh_from_db()
        self.assertEqual(chv_message.message_body, REDACTED_TEXT_VALUE)
        self.assertEqual(chv_message.provider_reference, "")
        self.assertEqual(chv_message.status, CHVMessage.STATUS_DELIVERED)

        action.refresh_from_db()
        self.assertEqual(action.notes, "")
        self.assertTrue(action.completion_evidence["retention_redacted"])
        self.assertEqual(action.status, PreparednessAction.STATUS_COMPLETED)
        self.assertEqual(action.ward, self.ward)

        action_event.refresh_from_db()
        self.assertEqual(action_event.detail, "")
        self.assertTrue(action_event.metadata["retention_redacted"])
        self.assertEqual(action_event.event_type, PreparednessActionEvent.EVENT_COMPLETED)

        preference.refresh_from_db()
        self.assertEqual(preference.phone_number, "")
        self.assertTrue(preference.metadata["retention_redacted"])
        self.assertEqual(preference.audience_type, ContactPreference.AUDIENCE_HOUSEHOLD)

        audit_event.refresh_from_db()
        self.assertEqual(audit_event.phone_number, "")
        self.assertEqual(audit_event.contact_reference, "")
        self.assertEqual(audit_event.action, ContactPreferenceAuditEvent.ACTION_ALLOWED)

        anonymized_events = PrivacyRetentionAuditEvent.objects.filter(
            action=PrivacyRetentionAuditEvent.ACTION_ANONYMIZED,
            dry_run=False,
        )
        self.assertEqual(anonymized_events.count(), 9)
        self.assertTrue(
            anonymized_events.filter(
                record_family="triage_field_details",
                aggregate_metrics__ward_id=self.ward.id,
            ).exists()
        )

    def test_active_retention_hold_blocks_anonymization_and_logs_decision(self):
        triage = self._age(
            TriageSession.objects.create(
                channel="API",
                phone_number="+254700888001",
                ward=self.ward,
                text_input="Investigation-linked triage note.",
                diarrhea=True,
            )
        )
        hold = PrivacyRetentionHold.objects.create(
            content_type=ContentType.objects.get_for_model(TriageSession),
            object_id=str(triage.pk),
            reason="Open public health investigation.",
            case_reference="CASE-RET-001",
            created_by=self.admin_user,
        )

        summary = apply_privacy_retention(
            now=self.now,
            dry_run=False,
            actor=self.admin_user,
            families=["triage_field_details"],
        )

        triage.refresh_from_db()
        self.assertEqual(triage.phone_number, "+254700888001")
        self.assertEqual(summary["totals"]["held"], 1)
        self.assertEqual(summary["totals"]["anonymized"], 0)
        self.assertTrue(
            PrivacyRetentionAuditEvent.objects.filter(
                action=PrivacyRetentionAuditEvent.ACTION_HELD,
                hold=hold,
                object_id=str(triage.pk),
                record_family="triage_field_details",
            ).exists()
        )

    def test_retention_command_defaults_to_dry_run_without_mutating_records(self):
        triage = self._age(
            TriageSession.objects.create(
                channel="API",
                phone_number="+254700999001",
                ward=self.ward,
                text_input="Dry-run triage text.",
                diarrhea=True,
            )
        )
        out = StringIO()

        call_command(
            "apply_privacy_retention",
            "--family",
            "triage_field_details",
            stdout=out,
        )

        triage.refresh_from_db()
        summary = json.loads(out.getvalue())
        self.assertTrue(summary["dry_run"])
        self.assertEqual(summary["totals"]["candidates"], 1)
        self.assertEqual(summary["totals"]["anonymized"], 0)
        self.assertEqual(triage.phone_number, "+254700999001")
        self.assertFalse(PrivacyRetentionAuditEvent.objects.exists())
