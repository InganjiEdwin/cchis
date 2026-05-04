from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from risk.message_governance import build_message_governance_audit, build_message_inventory_report, render_message_template
from risk.models import Alert, CHV, CHVMessage, ContactPreference, MessageTemplate, RiskScore, Ward
from risk.providers import DeliveryResult
from risk.services import create_alerts_for_riskscore, create_chv_message


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
        return MessageTemplate.objects.create(
            template_key=template_key,
            audience_type=audience_type,
            channel=channel,
            language=language,
            version=version,
            title=template_key,
            body=body,
            placeholders=placeholders or [],
            approval_status=MessageTemplate.APPROVAL_APPROVED,
            approved_at=timezone.now(),
            owner="county_public_health_operations",
            risk_level=MessageTemplate.RISK_HIGH,
            public_health_caveats="Use only for approved cholera response workflows.",
            lineage_metadata={"test": "message-governance"},
        )

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
        self.assertEqual(message.governance_metadata["schema_version"], "message-audience-governance-phase-2-v1")
        self.assertEqual(message.governance_metadata["template"]["template_key"], template.template_key)
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
        self.assertEqual(sms_alert.governance_metadata["template"]["template_key"], template.template_key)
        self.assertEqual(sms_alert.governance_metadata["audience_decision"]["audience_type"], ContactPreference.AUDIENCE_CHV)
        self.assertTrue(sms_alert.governance_metadata["audience_decision"]["allowed"])

    def test_message_governance_audit_and_command_report_pass(self):
        audit = build_message_governance_audit()
        self.assertEqual(audit["overall_status"], "pass")

        stdout = StringIO()
        call_command("audit_message_governance", stdout=stdout)
        self.assertIn("Message governance audit: pass", stdout.getvalue())

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
