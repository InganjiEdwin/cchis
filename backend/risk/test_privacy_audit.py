import json
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.models import User

from .models import (
    Alert,
    CHV,
    CHVAssignment,
    CHVCoverageRequest,
    CHVMessage,
    ContactPreference,
    ContactPreferenceAuditEvent,
    HealthFacility,
    PreparednessAction,
    SensitiveExportRequest,
    SyncQueue,
    TriageSession,
    UssdSessionLog,
    Ward,
)
from .privacy_audit import build_privacy_controls_audit


class PrivacyControlsAuditTests(TestCase):
    password = "ChangeMe123!"

    def setUp(self):
        self.now = timezone.now()
        self.ward = Ward.objects.create(
            name="Privacy Audit Ward",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.88,
            is_active=True,
        )
        self.other_ward = Ward.objects.create(
            name="Other Privacy Audit Ward",
            county="Migori",
            sub_county="Nyatike",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.54,
            is_active=True,
        )
        self.admin_user = User.objects.create_user(
            username="privacy_audit_admin",
            password=self.password,
            email="privacy-audit-admin@example.com",
            role=User.ROLE_ADMIN,
            ward=self.ward,
            is_active=True,
        )
        self.chv = CHV.objects.create(
            name="Privacy Audit CHV",
            phone_number="+254700555001",
            ward=self.ward,
            is_active=True,
            language="en",
        )

    def _old_processed_sync(self, **overrides):
        defaults = {
            "source_device_id": "privacy-audit-device",
            "client_submission_id": "privacy-audit-sync",
            "phone_number": "",
            "ward": self.ward,
            "payload": {"retention_redacted": True},
            "status": SyncQueue.STATUS_PROCESSED,
            "processed_at": self.now - timedelta(days=45),
            "error_message": "",
        }
        defaults.update(overrides)
        return SyncQueue.objects.create(**defaults)

    def test_privacy_controls_audit_passes_with_current_controls(self):
        coverage_request = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_APPROVED,
            priority=CHVCoverageRequest.PRIORITY_MEDIUM,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_MANUAL,
            reason="Coverage gap detected for ward response.",
            requested_chv_count=1,
        )
        CHVAssignment.objects.create(
            coverage_request=coverage_request,
            ward=self.ward,
            chv=self.chv,
            assigned_by=self.admin_user,
            status=CHVAssignment.STATUS_ACTIVE,
        )
        CHVMessage.objects.create(
            chv=self.chv,
            ward=self.ward,
            sent_by=self.admin_user,
            message_body="Please confirm ward readiness supplies.",
            status=CHVMessage.STATUS_QUEUED,
            delivery_kind=CHVMessage.DELIVERY_KIND_SIMULATED,
        )
        preference = ContactPreference.objects.create(
            audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="+254700555002",
            consent_status=ContactPreference.CONSENT_GRANTED,
            opt_out_status=ContactPreference.OPT_OUT_NOT_OPTED_OUT,
            source="household_sms_consent",
            source_reference="privacy-audit-consent",
            recorded_by=self.admin_user,
        )
        ContactPreferenceAuditEvent.objects.create(
            preference=preference,
            action=ContactPreferenceAuditEvent.ACTION_ALLOWED,
            audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="+254700555002",
            actor=self.admin_user,
            reason="contact_message_allowed",
        )
        self._old_processed_sync()
        Alert.objects.create(
            ward=self.ward,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700555003",
            message="Ward alert delivery message.",
            status=Alert.STATUS_QUEUED,
            delivery_backend="stub",
        )

        audit = build_privacy_controls_audit(now=self.now)

        self.assertEqual(audit["overall_status"], "pass")
        self.assertEqual(audit["high_risk_finding_count"], 0)
        self.assertEqual(
            {check["id"]: check["status"] for check in audit["audit_checks"]}["frontend_role_response_pii"],
            "pass",
        )

    def test_privacy_controls_audit_detects_high_risk_gaps(self):
        coverage_request = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_APPROVED,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_MANUAL,
            reason="Coverage gap detected.",
            requested_chv_count=1,
        )
        CHVAssignment.objects.create(
            coverage_request=coverage_request,
            ward=self.other_ward,
            chv=self.chv,
            assigned_by=self.admin_user,
            status=CHVAssignment.STATUS_ACTIVE,
        )
        CHVMessage.objects.create(
            chv=self.chv,
            ward=self.other_ward,
            sent_by=self.admin_user,
            message_body="Please confirm ward readiness.",
            status=CHVMessage.STATUS_SENT,
            delivery_kind=CHVMessage.DELIVERY_KIND_SIMULATED,
        )
        ContactPreferenceAuditEvent.objects.create(
            action=ContactPreferenceAuditEvent.ACTION_ALLOWED,
            audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="+254700555004",
            actor=self.admin_user,
            reason="contact_message_allowed",
        )
        SensitiveExportRequest.objects.create(
            export_type=SensitiveExportRequest.EXPORT_ALERT_LIST_CSV,
            requester=self.admin_user,
            purpose="Operational review of alert delivery recipients.",
            filters={"status": "+254700555005"},
            sensitive_fields_included=["alert.recipient"],
            approval_state=SensitiveExportRequest.APPROVAL_APPROVED,
            requires_approval=True,
            generated_at=self.now,
            expires_at=self.now + timedelta(days=7),
            approved_by=self.admin_user,
            approved_at=self.now,
            generated_filename="privacy-audit.csv",
            generated_payload="recipient\n+254700555005\n",
            payload_sha256="a" * 64,
            row_count=1,
            download_count=1,
            last_downloaded_at=self.now,
        )
        self._old_processed_sync(
            client_submission_id="privacy-audit-sync-raw",
            phone_number="+254700555006",
            payload={"phone_number": "+254700555006", "text_input": "raw field note"},
            error_message="raw processing error",
        )
        PreparednessAction.objects.create(
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            source_trigger_ref="privacy-audit-unsafe-note",
            ward=self.ward,
            status=PreparednessAction.STATUS_QUEUED,
            priority=PreparednessAction.PRIORITY_HIGH,
            created_by=self.admin_user,
            notes="Clinical notes: patient history should not be stored in this workflow.",
        )

        audit = build_privacy_controls_audit(now=self.now)
        statuses = {check["id"]: check["status"] for check in audit["audit_checks"]}

        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(statuses["chv_data_outside_assignment"], "fail")
        self.assertEqual(statuses["household_message_consent_or_override"], "fail")
        self.assertEqual(statuses["sensitive_export_download_audit"], "fail")
        self.assertEqual(statuses["stale_raw_sync_payload_retained"], "fail")
        self.assertEqual(statuses["unsupported_free_text_medical_notes"], "fail")

    def test_privacy_audit_passes_when_embedded_phone_is_redacted_from_analyst_response(self):
        Alert.objects.create(
            ward=self.ward,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700555008",
            message="Call +254700555009 before dispatch.",
            status=Alert.STATUS_QUEUED,
            delivery_backend="stub",
        )

        audit = build_privacy_controls_audit(now=self.now)
        frontend_check = next(check for check in audit["audit_checks"] if check["id"] == "frontend_role_response_pii")

        self.assertEqual(frontend_check["status"], "pass")
        self.assertEqual(frontend_check["gaps"], [])

    def test_privacy_audit_samples_non_alert_role_safe_response_surfaces(self):
        coverage_request = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_APPROVED,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_MANUAL,
            reason="Coverage gap detected for ward response.",
            requested_chv_count=1,
        )
        CHVAssignment.objects.create(
            coverage_request=coverage_request,
            ward=self.ward,
            chv=self.chv,
            assigned_by=self.admin_user,
            status=CHVAssignment.STATUS_ACTIVE,
        )
        HealthFacility.objects.create(
            name="Privacy Audit Facility",
            facility_code="PRIV-AUDIT-FAC",
            ward=self.ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
            contact_phone="+254700555010",
        )
        UssdSessionLog.objects.create(
            session_id="privacy-audit-ussd",
            phone_number="+254700555011",
            service_code="*123#",
            text="1*+254700555012",
            response_text="END Follow-up queued for +254700555013.",
            ward=self.ward,
            menu_level="diarrhea_menu",
        )

        audit = build_privacy_controls_audit(now=self.now)
        frontend_check = next(check for check in audit["audit_checks"] if check["id"] == "frontend_role_response_pii")

        self.assertEqual(frontend_check["status"], "pass")
        self.assertEqual(frontend_check["gaps"], [])
        self.assertGreaterEqual(frontend_check["evidence"]["facility_sample_count"], 1)
        self.assertGreaterEqual(frontend_check["evidence"]["coverage_request_sample_count"], 1)
        self.assertGreaterEqual(frontend_check["evidence"]["ussd_log_sample_count"], 1)

    def test_privacy_audit_flags_stale_triage_and_ussd_raw_identifiers(self):
        triage = TriageSession.objects.create(
            channel="API",
            phone_number="+254700555014",
            ward=self.ward,
            text_input="Raw triage note that should have aged out.",
            diarrhea=True,
        )
        TriageSession.objects.filter(pk=triage.pk).update(created_at=self.now - timedelta(days=181))
        ussd_log = UssdSessionLog.objects.create(
            session_id="privacy-audit-stale-ussd",
            phone_number="+254700555015",
            service_code="*123#",
            text="1*raw draft",
            response_text="END Raw response text.",
            ward=self.ward,
            menu_level="diarrhea_menu",
        )
        UssdSessionLog.objects.filter(pk=ussd_log.pk).update(created_at=self.now - timedelta(days=31))

        audit = build_privacy_controls_audit(now=self.now)
        retention_check = next(check for check in audit["audit_checks"] if check["id"] == "stale_raw_sync_payload_retained")
        models = {gap["model"] for gap in retention_check["gaps"]}

        self.assertEqual(retention_check["status"], "fail")
        self.assertIn("risk.TriageSession", models)
        self.assertIn("risk.UssdSessionLog", models)

    def test_privacy_audit_flags_invalid_stored_contact_preference_phone_values(self):
        ContactPreference.objects.create(
            audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="caregiver-one",
            consent_status=ContactPreference.CONSENT_GRANTED,
            opt_out_status=ContactPreference.OPT_OUT_NOT_OPTED_OUT,
            source="legacy_import",
            source_reference="privacy-audit-invalid-phone",
            recorded_by=self.admin_user,
        )

        audit = build_privacy_controls_audit(now=self.now)
        integrity_check = next(
            check for check in audit["audit_checks"] if check["id"] == "contact_preference_phone_integrity"
        )

        self.assertEqual(integrity_check["status"], "fail")
        self.assertEqual(integrity_check["gaps"][0]["model"], "risk.ContactPreference")

    def test_strict_privacy_audit_command_fails_on_high_risk_findings(self):
        self._old_processed_sync(
            client_submission_id="privacy-audit-strict-raw",
            phone_number="+254700555007",
            payload={"phone_number": "+254700555007"},
        )

        with self.assertRaises(CommandError):
            call_command("audit_privacy_controls", "--strict", stdout=StringIO())

    def test_privacy_audit_json_command_outputs_structured_report(self):
        output = StringIO()

        call_command("audit_privacy_controls", "--format", "json", stdout=output)

        payload = json.loads(output.getvalue())
        self.assertIn(payload["overall_status"], {"pass", "warning", "fail"})
        self.assertIn("audit_checks", payload)
        self.assertIn("operator_handling", payload)
