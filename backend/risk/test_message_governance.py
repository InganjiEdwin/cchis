from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from risk import message_governance
from risk.message_governance import build_message_governance_audit, build_message_inventory_report, render_message_template
from risk.models import (
    Alert,
    CHV,
    CHVOfflineRejectedSubmissionAudit,
    CHVMessage,
    ContactPreference,
    MessageTemplate,
    RiskScore,
    SyncQueue,
    UssdMenuVersion,
    UssdSessionLog,
    Ward,
)
from risk.providers import DeliveryResult
from risk.services import create_alerts_for_riskscore, create_chv_message
from risk.ussd_governance import USSD_BUILTIN_VERSION_LABEL, USSD_MENU_KEY


class MessageGovernancePhaseZeroOneTests(TestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="Message Governance Ward",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.87,
            is_active=True,
        )

    def _approved_template(
        self,
        *,
        template_key: str,
        audience_type: str,
        channel: str,
        body: str,
        placeholders: list[str] | None = None,
        version: int = 1,
        language: str = "en",
    ) -> MessageTemplate:
        approved_at = timezone.now()
        source_template = None
        if language != "en":
            source_template = MessageTemplate.objects.filter(
                template_key=template_key,
                version=version,
                language="en",
            ).first()
        template, _created = MessageTemplate.objects.update_or_create(
            template_key=template_key,
            language=language,
            version=version,
            defaults={
                "audience_type": audience_type,
                "channel": channel,
                "title": template_key,
                "body": body,
                "placeholders": placeholders or [],
                "approval_status": MessageTemplate.APPROVAL_APPROVED,
                "approved_at": approved_at,
                "retired_at": None,
                "translation_status": MessageTemplate.TRANSLATION_APPROVED,
                "source_template": source_template,
                "translation_reviewed_at": approved_at,
                "owner": "county_public_health_operations",
                "risk_level": MessageTemplate.RISK_HIGH,
                "public_health_caveats": "Use only for approved cholera response workflows.",
                "lineage_metadata": {"test": "message-governance"},
            },
        )
        return template

    def test_phase_zero_inventory_covers_required_governance_fields(self):
        report = build_message_inventory_report()

        self.assertGreaterEqual(report["inventory_count"], 6)
        self.assertEqual(report["missing_required_fields"], [])
        self.assertIn(
            "risk.serializers.CHVMessageCreateSerializer.message_body",
            {item["path"] for item in report["unmanaged_free_text_paths"]},
        )
        self.assertTrue(report["emergency_override_cases"])

    def test_template_rendering_validates_placeholder_context(self):
        template = self._approved_template(
            template_key="cholera.alert.chv.high_risk_sms",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            body="CHVs: {ward_name} is high risk. Predicted cases: {predicted_cases}.",
            placeholders=["ward_name", "predicted_cases"],
        )

        rendered = render_message_template(
            template_key=template.template_key,
            version=template.version,
            context={"ward_name": "Kanyasa", "predicted_cases": 12},
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
        )

        self.assertEqual(rendered.body, "CHVs: Kanyasa is high risk. Predicted cases: 12.")
        self.assertEqual(rendered.metadata["template_key"], template.template_key)
        with self.assertRaisesMessage(ValueError, "missing placeholders: predicted_cases"):
            render_message_template(
                template_key=template.template_key,
                version=template.version,
                context={"ward_name": "Kanyasa"},
                audience_type=MessageTemplate.AUDIENCE_CHV,
                channel=MessageTemplate.CHANNEL_SMS,
            )

    def test_unapproved_household_broadcast_template_is_blocked(self):
        template = MessageTemplate.objects.create(
            template_key="cholera.household.prevention_sms",
            audience_type=MessageTemplate.AUDIENCE_HOUSEHOLD,
            channel=MessageTemplate.CHANNEL_SMS,
            language="en",
            version=1,
            title="Household prevention",
            body="Use treated water and seek care quickly for dehydration.",
            placeholders=[],
            approval_status=MessageTemplate.APPROVAL_DRAFT,
            owner="county_health_promotion",
            risk_level=MessageTemplate.RISK_HIGH,
        )

        with self.assertRaisesMessage(ValueError, "Unapproved household broadcast templates"):
            render_message_template(
                template_key=template.template_key,
                version=template.version,
                context={},
                household_broadcast=True,
            )

    @patch("risk.services.send_sms")
    def test_chv_delivery_can_reference_template_key_and_version(self, mock_send_sms):
        mock_send_sms.return_value = DeliveryResult(
            success=True,
            external_id="sms-template-1",
            error="",
            provider="stub",
        )
        chv = CHV.objects.create(
            name="Template CHV",
            phone_number="+254700440001",
            ward=self.ward,
            is_active=True,
            language="en",
        )
        template = self._approved_template(
            template_key="cholera.chv.workflow_check_in_sms",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            body="Please confirm field readiness for {ward_name}.",
            placeholders=["ward_name"],
        )

        with patch("risk.services.resolve_chv_message_mode", return_value="SEND"), patch(
            "risk.services.resolve_chv_message_delivery_kind",
            return_value=CHVMessage.DELIVERY_KIND_SIMULATED,
        ):
            message = create_chv_message(
                chv,
                message_body="",
                template_key=template.template_key,
                template_version=template.version,
            )

        self.assertEqual(message.template, template)
        self.assertEqual(message.template_key, template.template_key)
        self.assertEqual(message.template_version, 1)
        self.assertEqual(message.message_body, "Please confirm field readiness for Message Governance Ward.")
        self.assertEqual(message.requested_language, "en")
        self.assertEqual(message.resolved_language, "en")
        self.assertFalse(message.fallback_used)
        self.assertEqual(message.governance_metadata["schema_version"], "message-audience-governance-phase-2-v1")
        self.assertEqual(message.governance_metadata["template"]["template_key"], template.template_key)
        self.assertEqual(message.governance_metadata["template"]["resolved_language"], "en")
        self.assertFalse(message.governance_metadata["template"]["fallback_used"])
        self.assertTrue(message.governance_metadata["audience_decision"]["allowed"])
        mock_send_sms.assert_called_once_with(chv.phone_number, message.message_body)

    def test_chv_message_scope_blocks_supervisor_outside_assigned_ward(self):
        other_ward = Ward.objects.create(
            name="Other Message Governance Ward",
            county="Migori",
            sub_county="Awendo",
            is_active=True,
        )
        supervisor = User.objects.create_user(
            username="message_scope_supervisor",
            password="ChangeMe123!",
            email="message_scope_supervisor@example.com",
            role=User.ROLE_SUPERVISOR,
            ward=other_ward,
            is_active=True,
        )
        chv = CHV.objects.create(
            name="Scoped CHV",
            phone_number="+254700440002",
            ward=self.ward,
            is_active=True,
            language="en",
        )

        with self.assertRaisesMessage(ValueError, "assigned ward contact scope"):
            create_chv_message(
                chv,
                message_body="Please confirm field readiness.",
                sent_by=supervisor,
            )

    def test_alert_delivery_can_reference_template_key_and_version(self):
        risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.87,
            risk_level=Ward.RISK_HIGH,
            predicted_cases=11,
            source=RiskScore.SOURCE_MODEL,
            model_version="message-template-v1",
        )
        template = self._approved_template(
            template_key="cholera.alert.chv.high_risk_sms",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            body="CHVs: {ward_name} is high risk with {predicted_cases} predicted cases.",
            placeholders=["ward_name", "predicted_cases"],
        )
        chv = CHV.objects.create(
            name="Alert Template CHV",
            phone_number="+254700440003",
            ward=self.ward,
            is_active=True,
            language="en",
        )

        alerts = create_alerts_for_riskscore(
            risk_score,
            send_sms_enabled=True,
            template_key=template.template_key,
            template_version=template.version,
        )

        self.assertEqual(len(alerts), 2)
        dashboard_alert = next(alert for alert in alerts if alert.channel == Alert.CHANNEL_DASHBOARD)
        sms_alert = next(alert for alert in alerts if alert.channel == Alert.CHANNEL_SMS)
        self.assertIsNone(dashboard_alert.template)
        self.assertEqual(dashboard_alert.template_key, "")
        self.assertIsNone(dashboard_alert.template_version)
        self.assertEqual(
            dashboard_alert.guided_request_metadata["message_template"]["template_key"],
            template.template_key,
        )
        self.assertEqual(dashboard_alert.governance_metadata["template"], {})
        self.assertTrue(dashboard_alert.governance_metadata["audience_decision"]["allowed"])
        self.assertEqual(sms_alert.recipient, chv.phone_number)
        self.assertEqual(sms_alert.template, template)
        self.assertEqual(sms_alert.requested_language, "en")
        self.assertEqual(sms_alert.resolved_language, "en")
        self.assertFalse(sms_alert.fallback_used)
        self.assertEqual(sms_alert.governance_metadata["template"]["template_key"], template.template_key)
        self.assertEqual(sms_alert.governance_metadata["template"]["resolved_language"], "en")
        self.assertEqual(sms_alert.governance_metadata["audience_decision"]["audience_type"], ContactPreference.AUDIENCE_CHV)
        self.assertTrue(sms_alert.governance_metadata["audience_decision"]["allowed"])

    def test_seeded_chv_sms_templates_cover_supported_languages(self):
        for template_key in ("cholera.alert.chv.high_risk_sms", "cholera.chv.workflow_check_in_sms"):
            english_template = MessageTemplate.objects.get(template_key=template_key, language="en", version=1)
            variants = {
                template.language: template
                for template in MessageTemplate.objects.filter(template_key=template_key, version=1)
            }

            self.assertEqual(set(variants), {"en", "sw", "luo"})
            for language, template in variants.items():
                self.assertEqual(template.approval_status, MessageTemplate.APPROVAL_APPROVED)
                self.assertEqual(sorted(template.placeholders), sorted(english_template.placeholders))
                if language != "en":
                    self.assertEqual(template.translation_status, MessageTemplate.TRANSLATION_APPROVED)
                    self.assertEqual(template.source_template, english_template)
                    self.assertIsNotNone(template.translation_reviewed_at)

    @patch("risk.services.send_sms")
    def test_chv_workflow_message_uses_preferred_language_and_records_traceability(self, mock_send_sms):
        mock_send_sms.return_value = DeliveryResult(
            success=True,
            external_id="sms-template-sw",
            error="",
            provider="stub",
        )
        chv = CHV.objects.create(
            name="Swahili Template CHV",
            phone_number="+254700440004",
            ward=self.ward,
            is_active=True,
            preferred_language="sw",
        )

        with patch("risk.services.resolve_chv_message_mode", return_value="SEND"), patch(
            "risk.services.resolve_chv_message_delivery_kind",
            return_value=CHVMessage.DELIVERY_KIND_SIMULATED,
        ):
            message = create_chv_message(
                chv,
                message_body="",
                template_key="cholera.chv.workflow_check_in_sms",
            )

        self.assertEqual(message.template.language, "sw")
        self.assertEqual(message.requested_language, "sw")
        self.assertEqual(message.resolved_language, "sw")
        self.assertFalse(message.fallback_used)
        self.assertIn("Tafadhali thibitisha", message.message_body)
        self.assertEqual(message.governance_metadata["template"]["resolved_language"], "sw")
        mock_send_sms.assert_called_once_with(chv.phone_number, message.message_body)

    @patch("risk.services.send_sms")
    def test_chv_workflow_message_falls_back_to_english_with_metadata(self, mock_send_sms):
        mock_send_sms.return_value = DeliveryResult(
            success=True,
            external_id="sms-template-fallback",
            error="",
            provider="stub",
        )
        template = self._approved_template(
            template_key="cholera.chv.fallback_probe_sms",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            body="Please confirm fallback readiness for {ward_name}.",
            placeholders=["ward_name"],
        )
        chv = CHV.objects.create(
            name="Dholuo Fallback CHV",
            phone_number="+254700440005",
            ward=self.ward,
            is_active=True,
            preferred_language="luo",
        )

        with patch("risk.services.resolve_chv_message_mode", return_value="SEND"), patch(
            "risk.services.resolve_chv_message_delivery_kind",
            return_value=CHVMessage.DELIVERY_KIND_SIMULATED,
        ):
            message = create_chv_message(
                chv,
                message_body="",
                template_key=template.template_key,
            )

        self.assertEqual(message.template.language, "en")
        self.assertEqual(message.requested_language, "luo")
        self.assertEqual(message.resolved_language, "en")
        self.assertTrue(message.fallback_used)
        self.assertEqual(message.governance_metadata["template"]["requested_language"], "luo")
        self.assertEqual(message.governance_metadata["template"]["resolved_language"], "en")
        self.assertTrue(message.governance_metadata["template"]["fallback_used"])

    def test_alert_sms_uses_each_recipient_resolved_language(self):
        risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.91,
            risk_level=Ward.RISK_HIGH,
            predicted_cases=14,
            source=RiskScore.SOURCE_MODEL,
            model_version="message-template-v1",
        )
        CHV.objects.create(
            name="English Alert CHV",
            phone_number="+254700440006",
            ward=self.ward,
            is_active=True,
            preferred_language="en",
        )
        CHV.objects.create(
            name="Swahili Alert CHV",
            phone_number="+254700440007",
            ward=self.ward,
            is_active=True,
            preferred_language="sw",
        )
        CHV.objects.create(
            name="Dholuo Alert CHV",
            phone_number="+254700440008",
            ward=self.ward,
            is_active=True,
            preferred_language="luo",
        )

        alerts = create_alerts_for_riskscore(
            risk_score,
            send_sms_enabled=True,
            template_key="cholera.alert.chv.high_risk_sms",
            template_version=1,
        )

        sms_alerts = [alert for alert in alerts if alert.channel == Alert.CHANNEL_SMS]
        self.assertEqual(len(sms_alerts), 3)
        alerts_by_language = {alert.resolved_language: alert for alert in sms_alerts}
        self.assertEqual(set(alerts_by_language), {"en", "sw", "luo"})
        self.assertIn("CHVs:", alerts_by_language["en"].message)
        self.assertIn("iko hatari kubwa", alerts_by_language["sw"].message)
        self.assertIn("nitie e chandruok", alerts_by_language["luo"].message)
        for language, alert in alerts_by_language.items():
            self.assertEqual(alert.requested_language, language)
            self.assertEqual(alert.template.language, language)
            self.assertFalse(alert.fallback_used)
            self.assertEqual(alert.governance_metadata["template"]["resolved_language"], language)

    def test_unapproved_translated_public_health_sms_copy_is_not_used(self):
        source = self._approved_template(
            template_key="cholera.chv.translation_gate_phase5_sms",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            body="Use approved guidance in {ward_name}.",
            placeholders=["ward_name"],
        )
        MessageTemplate.objects.create(
            template_key=source.template_key,
            audience_type=source.audience_type,
            channel=source.channel,
            language="sw",
            version=source.version,
            title="Unapproved Swahili CHV copy",
            body="Tumia ujumbe ambao haujaidhinishwa {ward_name}.",
            placeholders=["ward_name"],
            approval_status=MessageTemplate.APPROVAL_APPROVED,
            approved_at=timezone.now(),
            translation_status=MessageTemplate.TRANSLATION_DRAFT,
            source_template=source,
            owner=source.owner,
            risk_level=MessageTemplate.RISK_HIGH,
            public_health_caveats="Approved cholera response copy.",
        )

        rendered = render_message_template(
            template_key=source.template_key,
            version=source.version,
            language="sw",
            context={"ward_name": self.ward.name},
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
        )

        self.assertEqual(rendered.template.language, "en")
        self.assertTrue(rendered.metadata["fallback_used"])

    def test_message_governance_audit_and_command_report_pass(self):
        english_menu = UssdMenuVersion.objects.get(
            menu_key=USSD_MENU_KEY,
            language="en",
            version_label=USSD_BUILTIN_VERSION_LABEL,
        )
        for language in ("sw", "luo"):
            variant = UssdMenuVersion.objects.get(
                menu_key=USSD_MENU_KEY,
                language=language,
                version_label=USSD_BUILTIN_VERSION_LABEL,
                is_active=True,
            )
            self.assertEqual(variant.source_menu_version, english_menu)
            self.assertEqual(variant.translation_status, UssdMenuVersion.TRANSLATION_APPROVED)

        audit = build_message_governance_audit()
        self.assertEqual(audit["overall_status"], "pass")
        self.assertEqual(audit["schema_version"], "message-governance-phase-7-v1")
        self.assertEqual(audit["strict_localization_issue_count"], 0)
        self.assertEqual(audit["localization_rollout"]["schema_version"], "chv-localization-rollout-phase-7-v1")
        checks = {check["id"]: check for check in audit["audit_checks"]}
        self.assertEqual(checks["phase_7_strict_localization_audit"]["status"], "pass")
        self.assertIn("fallback_rate_pct", audit["localization_rollout"])

        stdout = StringIO()
        call_command("audit_message_governance", stdout=stdout)
        self.assertIn("Message governance audit: pass", stdout.getvalue())
        self.assertIn("Strict localization issues: 0", stdout.getvalue())

    def test_phase_7_audit_catches_ussd_language_mismatch_without_fallback_flag(self):
        UssdSessionLog.objects.create(
            session_id="phase-7-fallback-gap",
            phone_number="+254700449901",
            service_code="*123#",
            text="",
            response_text="END Invalid option.",
            ward=self.ward,
            menu_key=USSD_MENU_KEY,
            menu_version_label=USSD_BUILTIN_VERSION_LABEL,
            language="en",
            requested_language="sw",
            resolved_language="en",
            fallback_used=False,
            session_outcome=UssdSessionLog.OUTCOME_SAFE_FALLBACK,
            governance_metadata={"fallback_used": False},
        )

        audit = build_message_governance_audit()
        checks = {check["id"]: check for check in audit["audit_checks"]}

        self.assertEqual(checks["phase_7_fallback_metadata_complete"]["status"], "fail")
        self.assertEqual(checks["phase_7_strict_localization_audit"]["status"], "fail")
        self.assertIn(
            "USSD session resolved a different language without marking fallback_used.",
            {
                issue["message"]
                for issue in checks["phase_7_fallback_metadata_complete"]["evidence"]["issues"]
            },
        )

    def test_phase_2_audit_requires_active_approved_ussd_translation_variant(self):
        UssdMenuVersion.objects.filter(
            menu_key=USSD_MENU_KEY,
            language="sw",
            is_active=True,
        ).update(is_active=False)

        audit = build_message_governance_audit()
        checks = {check["id"]: check for check in audit["audit_checks"]}

        self.assertEqual(checks["phase_2_ussd_translation_registry"]["status"], "fail")
        self.assertEqual(checks["phase_7_strict_localization_audit"]["status"], "fail")
        self.assertIn(
            "Required active approved USSD menu language variant is missing.",
            {
                issue["message"]
                for issue in checks["phase_2_ussd_translation_registry"]["evidence"]["issues"]
            },
        )

    def test_phase_7_audit_catches_static_frontend_health_fallback_items(self):
        frontend_page = """
        function buildFallbackBundle() {
          return {
            guidance_bundle: {
              schema_version: "chv-guidance-bundle-v1",
              content_unavailable: false,
              items: [{ body: "Use treated water." }],
            },
            decision_support_rule_bundle: {
              content_unavailable: true,
              recommendations: [],
            },
          };
        }
        """

        def fake_read_text(path, encoding="utf-8"):
            if str(path).endswith("frontend/app/chv/page.tsx"):
                return frontend_page
            return ""

        with (
            patch("risk.message_governance.Path.exists", return_value=True),
            patch("risk.message_governance.Path.read_text", fake_read_text),
        ):
            issues = message_governance._static_public_health_fallback_issues()

        self.assertIn(
            "Local CHV PWA fallback guidance bundle contains static guidance items instead of failing closed.",
            {issue["message"] for issue in issues},
        )
        self.assertIn(
            "Local CHV PWA fallback guidance bundle does not explicitly mark governed content as unavailable.",
            {issue["message"] for issue in issues},
        )

    def test_phase_7_audit_catches_frontend_api_raw_error_detail_propagation(self):
        frontend_api = """
        async function readErrorDetail(response) {
          const body = await response.json();
          return body.detail;
        }
        """

        def fake_read_text(path, encoding="utf-8"):
            if str(path).endswith("frontend/lib/chv-offline-api.ts"):
                return frontend_api
            return ""

        with (
            patch("risk.message_governance.Path.exists", return_value=True),
            patch("risk.message_governance.Path.read_text", fake_read_text),
        ):
            issues = message_governance._sync_error_sensitive_copy_issues()

        self.assertIn(
            "CHV frontend offline API can propagate raw server error detail into sync error objects.",
            {issue["message"] for issue in issues},
        )

    def test_phase_7_audit_catches_approved_ussd_node_length_budget_drift(self):
        UssdMenuVersion.objects.create(
            menu_key="phase_7_length_budget_probe",
            version_label="v1",
            language="en",
            title="Length budget probe",
            menu_tree={
                "routes": {"": "root"},
                "nodes": {
                    "root": {
                        "response_type": "END",
                        "body": "A" * 220,
                    }
                },
            },
            approval_status=UssdMenuVersion.STATUS_APPROVED,
            approved_at=timezone.now(),
            safe_fallback_copy="END Invalid option.",
            translation_status=UssdMenuVersion.TRANSLATION_APPROVED,
            translation_reviewed_at=timezone.now(),
        )

        audit = build_message_governance_audit()
        checks = {check["id"]: check for check in audit["audit_checks"]}

        self.assertEqual(checks["phase_7_ussd_node_length_budget"]["status"], "fail")
        self.assertEqual(checks["phase_7_strict_localization_audit"]["status"], "fail")
        self.assertIn("ussd_node_exceeds_length_budget", checks["phase_7_ussd_node_length_budget"]["gaps"])

    def test_phase_7_audit_catches_sync_error_echoing_sensitive_payload_value(self):
        SyncQueue.objects.create(
            source_device_id="phase-7-sync-copy",
            client_submission_id="phase-7-sensitive-copy",
            idempotency_key="phase-7-sensitive-copy",
            upload_type=SyncQueue.UPLOAD_SYMPTOM_TRIAGE,
            ward=self.ward,
            payload={"text_input": "Jane Doe lives near the river"},
            status=SyncQueue.STATUS_FAILED,
            error_message="Unable to sync Jane Doe lives near the river.",
        )

        audit = build_message_governance_audit()
        checks = {check["id"]: check for check in audit["audit_checks"]}

        self.assertEqual(checks["phase_7_sync_error_copy_pii_safe"]["status"], "fail")
        self.assertEqual(checks["phase_7_strict_localization_audit"]["status"], "fail")
        self.assertIn("sync_error_copy_exposes_sensitive_payload", checks["phase_7_sync_error_copy_pii_safe"]["gaps"])

    def test_phase_7_audit_catches_sync_receipt_explanation_echoing_sensitive_payload_value(self):
        SyncQueue.objects.create(
            source_device_id="phase-7-receipt-copy",
            client_submission_id="phase-7-sensitive-receipt-copy",
            idempotency_key="phase-7-sensitive-receipt-copy",
            upload_type=SyncQueue.UPLOAD_SYMPTOM_TRIAGE,
            ward=self.ward,
            payload={"notes": "Exact home behind the market"},
            status=SyncQueue.STATUS_FAILED,
            server_receipt={
                "status": "REJECTED",
                "explanation": "Exact home behind the market could not be synced.",
            },
        )

        audit = build_message_governance_audit()
        checks = {check["id"]: check for check in audit["audit_checks"]}

        self.assertEqual(checks["phase_7_sync_error_copy_pii_safe"]["status"], "fail")
        self.assertEqual(checks["phase_7_strict_localization_audit"]["status"], "fail")
        self.assertIn("sync_error_copy_exposes_sensitive_payload", checks["phase_7_sync_error_copy_pii_safe"]["gaps"])

    def test_phase_7_audit_allows_safe_payload_schema_error_without_raw_values(self):
        CHVOfflineRejectedSubmissionAudit.objects.create(
            ward=self.ward,
            rejection_stage=CHVOfflineRejectedSubmissionAudit.STAGE_PAYLOAD_SCHEMA,
            error_code="chv_offline_payload_schema_failed",
            safe_error_summary="Rejected before sync persistence during payload schema validation.",
            status_code=400,
        )

        audit = build_message_governance_audit()
        checks = {check["id"]: check for check in audit["audit_checks"]}

        self.assertEqual(checks["phase_7_sync_error_copy_pii_safe"]["status"], "pass")

    def test_audit_fails_delivery_records_missing_governance_metadata(self):
        Alert.objects.create(
            ward=self.ward,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700440006",
            message="Ungoverned delivery record.",
            status=Alert.STATUS_DELIVERED,
        )

        audit = build_message_governance_audit()
        checks = {check["id"]: check for check in audit["audit_checks"]}

        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(checks["phase_2_delivery_records_include_audience_decisions"]["status"], "fail")
        self.assertIn(
            "invalid_message_audience_governance_metadata",
            checks["phase_2_delivery_records_include_audience_decisions"]["gaps"],
        )

    def test_audit_catches_uppercase_household_decision_without_consent_or_lawful_basis(self):
        Alert.objects.create(
            ward=self.ward,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700440007",
            message="Household prevention message.",
            status=Alert.STATUS_DELIVERED,
            governance_metadata={
                "schema_version": "message-audience-governance-phase-2-v1",
                "workflow": "household_prevention_sms",
                "audience_decision": {
                    "allowed": True,
                    "audience_type": ContactPreference.AUDIENCE_HOUSEHOLD,
                    "channel": ContactPreference.CHANNEL_SMS,
                    "opt_out_status": ContactPreference.OPT_OUT_NOT_OPTED_OUT,
                },
            },
        )

        audit = build_message_governance_audit()
        phase_two = {check["id"]: check for check in audit["audit_checks"]}[
            "phase_2_delivery_records_include_audience_decisions"
        ]

        self.assertEqual(phase_two["status"], "fail")
        self.assertIn("invalid_message_audience_governance_metadata", phase_two["gaps"])

    def test_audit_fails_template_snapshots_without_concrete_template_link(self):
        chv = CHV.objects.create(
            name="Unlinked Template CHV",
            phone_number="+254700440008",
            ward=self.ward,
            is_active=True,
            language="en",
        )
        template = self._approved_template(
            template_key="cholera.chv.unlinked_template_sms",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            body="Please confirm field readiness for {ward_name}.",
            placeholders=["ward_name"],
        )
        CHVMessage.objects.create(
            chv=chv,
            ward=self.ward,
            template_key=template.template_key,
            template_version=template.version,
            message_body="Please confirm field readiness for Message Governance Ward.",
            status=CHVMessage.STATUS_SENT,
            governance_metadata={
                "schema_version": "message-audience-governance-phase-2-v1",
                "workflow": "chv_workflow_message",
                "template": {
                    "template_key": template.template_key,
                    "template_version": template.version,
                    "template_public_id": str(template.public_id),
                },
                "audience_decision": {
                    "allowed": True,
                    "audience_type": ContactPreference.AUDIENCE_CHV,
                    "channel": ContactPreference.CHANNEL_SMS,
                    "consent_status": ContactPreference.CONSENT_GRANTED,
                    "opt_out_status": ContactPreference.OPT_OUT_NOT_OPTED_OUT,
                },
                "audience_scope": {"scope_kind": "test_fixture", "scope_allowed": True},
            },
        )

        audit = build_message_governance_audit()
        phase_one = {check["id"]: check for check in audit["audit_checks"]}[
            "phase_1_delivery_records_reference_templates"
        ]

        self.assertEqual(phase_one["status"], "fail")
        self.assertIn("unsafe_template_delivery_reference", phase_one["gaps"])

    def test_audit_fails_delivery_metadata_template_version_mismatch(self):
        chv = CHV.objects.create(
            name="Metadata Mismatch CHV",
            phone_number="+254700440009",
            ward=self.ward,
            is_active=True,
            language="en",
        )
        template = self._approved_template(
            template_key="cholera.chv.metadata_mismatch_sms",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            body="Please confirm field readiness for {ward_name}.",
            placeholders=["ward_name"],
        )
        CHVMessage.objects.create(
            chv=chv,
            ward=self.ward,
            template=template,
            template_key=template.template_key,
            template_version=template.version,
            message_body="Please confirm field readiness for Message Governance Ward.",
            status=CHVMessage.STATUS_SENT,
            governance_metadata={
                "schema_version": "message-audience-governance-phase-2-v1",
                "workflow": "chv_workflow_message",
                "template": {
                    "template_key": template.template_key,
                    "template_version": 999,
                    "template_public_id": str(template.public_id),
                },
                "audience_decision": {
                    "schema_version": "message-audience-governance-phase-2-v1",
                    "allowed": True,
                    "audience_type": ContactPreference.AUDIENCE_CHV,
                    "channel": ContactPreference.CHANNEL_SMS,
                    "consent_status": ContactPreference.CONSENT_GRANTED,
                    "opt_out_status": ContactPreference.OPT_OUT_NOT_OPTED_OUT,
                },
                "audience_scope": {"scope_kind": "test_fixture", "scope_allowed": True},
            },
        )

        audit = build_message_governance_audit()
        phase_two = {check["id"]: check for check in audit["audit_checks"]}[
            "phase_2_delivery_records_include_audience_decisions"
        ]

        self.assertEqual(phase_two["status"], "fail")
        self.assertIn("invalid_message_audience_governance_metadata", phase_two["gaps"])

    def test_audit_fails_delivery_metadata_audience_and_channel_mismatch(self):
        Alert.objects.create(
            ward=self.ward,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700440010",
            message="CHV alert with forged operator metadata.",
            status=Alert.STATUS_DELIVERED,
            governance_metadata={
                "schema_version": "message-audience-governance-phase-2-v1",
                "workflow": "risk_alert_sms",
                "audience_decision": {
                    "schema_version": "message-audience-governance-phase-2-v1",
                    "allowed": True,
                    "audience_type": MessageTemplate.AUDIENCE_COUNTY_OPERATOR,
                    "channel": MessageTemplate.CHANNEL_DASHBOARD,
                    "decision": "internal_dashboard_delivery_allowed",
                },
                "audience_scope": {"scope_kind": "forged_test_fixture", "scope_allowed": True},
            },
        )

        audit = build_message_governance_audit()
        phase_two = {check["id"]: check for check in audit["audit_checks"]}[
            "phase_2_delivery_records_include_audience_decisions"
        ]

        self.assertEqual(phase_two["status"], "fail")
        self.assertIn("invalid_message_audience_governance_metadata", phase_two["gaps"])

    def test_audit_fails_delivery_template_channel_and_audience_mismatch(self):
        template = self._approved_template(
            template_key="cholera.alert.chv.dashboard_mismatch_sms",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            body="CHVs: {ward_name} is high risk.",
            placeholders=["ward_name"],
        )
        Alert.objects.create(
            ward=self.ward,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            template=template,
            template_key=template.template_key,
            template_version=template.version,
            message="CHVs: Message Governance Ward is high risk.",
            status=Alert.STATUS_DELIVERED,
            governance_metadata={
                "schema_version": "message-audience-governance-phase-2-v1",
                "workflow": "risk_alert_dashboard",
                "template": {
                    "template_key": template.template_key,
                    "template_version": template.version,
                    "template_public_id": str(template.public_id),
                },
                "audience_decision": {
                    "schema_version": "message-audience-governance-phase-2-v1",
                    "allowed": True,
                    "audience_type": MessageTemplate.AUDIENCE_COUNTY_OPERATOR,
                    "channel": MessageTemplate.CHANNEL_DASHBOARD,
                    "decision": "internal_dashboard_delivery_allowed",
                },
                "audience_scope": {"scope_kind": "internal_dashboard", "scope_allowed": True},
            },
        )

        audit = build_message_governance_audit()
        phase_one = {check["id"]: check for check in audit["audit_checks"]}[
            "phase_1_delivery_records_reference_templates"
        ]

        self.assertEqual(phase_one["status"], "fail")
        self.assertIn("unsafe_template_delivery_reference", phase_one["gaps"])

    def test_phase_five_audit_catches_unsafe_message_monitoring_cases(self):
        chv = CHV.objects.create(
            name="Audit CHV",
            phone_number="+254700440004",
            ward=self.ward,
            is_active=True,
            language="en",
        )
        household_template = MessageTemplate.objects.create(
            template_key="cholera.household.unsafe_sms",
            audience_type=MessageTemplate.AUDIENCE_HOUSEHOLD,
            channel=MessageTemplate.CHANNEL_SMS,
            language="en",
            version=1,
            title="Unsafe household SMS",
            body="Use treated water.",
            placeholders=[],
            approval_status=MessageTemplate.APPROVAL_DRAFT,
            owner="county_health_promotion",
            risk_level=MessageTemplate.RISK_HIGH,
        )
        Alert.objects.create(
            ward=self.ward,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700440005",
            template=household_template,
            template_key=household_template.template_key,
            template_version=household_template.version,
            message="Use treated water.",
            status=Alert.STATUS_DELIVERED,
            governance_metadata={
                "schema_version": "message-audience-governance-phase-2-v1",
                "workflow": "risk_alert_sms",
                "audience_decision": {
                    "allowed": True,
                    "audience_type": ContactPreference.AUDIENCE_HOUSEHOLD,
                    "channel": ContactPreference.CHANNEL_SMS,
                    "consent_status": ContactPreference.CONSENT_GRANTED,
                    "opt_out_status": ContactPreference.OPT_OUT_NOT_OPTED_OUT,
                },
            },
        )
        retired_at = timezone.now() - timedelta(minutes=1)
        retired_template = MessageTemplate.objects.create(
            template_key="cholera.chv.retired_alert_sms",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            language="en",
            version=1,
            title="Retired CHV alert",
            body="Retired alert copy.",
            placeholders=[],
            approval_status=MessageTemplate.APPROVAL_RETIRED,
            retired_at=retired_at,
            owner="county_public_health_operations",
            risk_level=MessageTemplate.RISK_HIGH,
        )
        CHVMessage.objects.create(
            chv=chv,
            ward=self.ward,
            template=retired_template,
            template_key=retired_template.template_key,
            template_version=retired_template.version,
            message_body="Retired alert copy.",
            status=CHVMessage.STATUS_SENT,
            governance_metadata={
                "schema_version": "message-audience-governance-phase-2-v1",
                "audience_decision": {
                    "allowed": True,
                    "audience_type": ContactPreference.AUDIENCE_CHV,
                    "channel": ContactPreference.CHANNEL_SMS,
                    "opt_out_status": ContactPreference.OPT_OUT_OPTED_OUT,
                    "emergency_override": False,
                },
            },
        )
        MessageTemplate.objects.create(
            template_key="cholera.household.sw_only",
            audience_type=MessageTemplate.AUDIENCE_HOUSEHOLD,
            channel=MessageTemplate.CHANNEL_SMS,
            language="sw",
            version=1,
            title="Swahili-only household message",
            body="Tumia maji salama.",
            placeholders=[],
            approval_status=MessageTemplate.APPROVAL_DRAFT,
            owner="county_health_promotion",
            risk_level=MessageTemplate.RISK_MEDIUM,
        )

        audit = build_message_governance_audit()
        checks = {check["id"]: check for check in audit["audit_checks"]}

        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(checks["phase_5_household_messages_use_approved_templates"]["status"], "fail")
        self.assertEqual(checks["phase_5_templates_not_used_after_retirement"]["status"], "fail")
        self.assertEqual(checks["phase_5_language_fallbacks_present"]["status"], "fail")
        self.assertEqual(checks["phase_5_opt_outs_not_ignored"]["status"], "fail")
        self.assertEqual(checks["phase_5_high_risk_alerts_have_source_references"]["status"], "fail")
        self.assertEqual(checks["phase_7_strict_localization_audit"]["status"], "fail")
