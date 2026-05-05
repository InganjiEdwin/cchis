from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from risk.models import Alert, CHV, CHVMessage, ContactPreference, ContactPreferenceAuditEvent, MessageTemplate, RiskScore, Ward
from risk.ussd_governance import create_ussd_session_log


class MessageManagementSurfaceTests(APITestCase):
    def setUp(self):
        self.ward = Ward.objects.create(
            name="Message Surface Ward",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.9,
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username="message_admin",
            password="ChangeMe123!",
            role=User.ROLE_ADMIN,
            is_active=True,
        )
        self.analyst = User.objects.create_user(
            username="message_analyst",
            password="ChangeMe123!",
            role=User.ROLE_ANALYST,
            is_active=True,
        )
        self.chv = CHV.objects.create(
            name="Message CHV",
            phone_number="+254700222333",
            ward=self.ward,
            is_active=True,
        )
        self.risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.9,
            risk_level=Ward.RISK_HIGH,
            predicted_cases=9,
            source=RiskScore.SOURCE_MODEL,
            model_version="message-management-phase-6",
        )
        self.approved_template = MessageTemplate.objects.create(
            template_key="cholera.alert.chv.surface",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            language="en",
            version=1,
            title="CHV surface alert",
            body="CHVs: {ward_name} needs cholera prevention checks.",
            placeholders=["ward_name"],
            approval_status=MessageTemplate.APPROVAL_APPROVED,
            approved_by=self.admin,
            approved_at=timezone.now(),
            owner="county_public_health_operations",
            risk_level=MessageTemplate.RISK_HIGH,
            public_health_caveats="Use for operational public-health alerts.",
            created_by=self.admin,
        )
        for language, title, body in (
            ("sw", "CHV surface alert SW", "CHVs: {ward_name} inahitaji ukaguzi wa kuzuia kipindupindu."),
            ("luo", "CHV surface alert LUO", "CHVs: {ward_name} dwaro nonro mar geng'o cholera."),
        ):
            MessageTemplate.objects.create(
                template_key=self.approved_template.template_key,
                audience_type=MessageTemplate.AUDIENCE_CHV,
                channel=MessageTemplate.CHANNEL_SMS,
                language=language,
                version=self.approved_template.version,
                title=title,
                body=body,
                placeholders=["ward_name"],
                approval_status=MessageTemplate.APPROVAL_APPROVED,
                approved_by=self.admin,
                approved_at=timezone.now(),
                translation_status=MessageTemplate.TRANSLATION_APPROVED,
                source_template=self.approved_template,
                translation_reviewed_by=self.admin,
                translation_reviewed_at=timezone.now(),
                translation_review_notes="Reviewed test translation.",
                owner="county_public_health_operations",
                risk_level=MessageTemplate.RISK_HIGH,
                public_health_caveats="Use for operational public-health alerts.",
                created_by=self.admin,
            )
        self.pending_template = MessageTemplate.objects.create(
            template_key="cholera.household.surface",
            audience_type=MessageTemplate.AUDIENCE_HOUSEHOLD,
            channel=MessageTemplate.CHANNEL_SMS,
            language="en",
            version=1,
            title="Household surface message",
            body="Use treated water in {ward_name}.",
            placeholders=["ward_name"],
            approval_status=MessageTemplate.APPROVAL_PENDING_REVIEW,
            owner="county_health_promotion",
            risk_level=MessageTemplate.RISK_HIGH,
            public_health_caveats="Requires consent or approved lawful basis.",
            created_by=self.analyst,
        )
        self.sw_variant = MessageTemplate.objects.create(
            template_key=self.pending_template.template_key,
            audience_type=MessageTemplate.AUDIENCE_HOUSEHOLD,
            channel=MessageTemplate.CHANNEL_SMS,
            language="sw",
            version=1,
            title="Household surface message SW",
            body="Tumia maji salama {ward_name}.",
            placeholders=["ward_name"],
            approval_status=MessageTemplate.APPROVAL_DRAFT,
            source_template=self.pending_template,
            owner="county_health_promotion",
            risk_level=MessageTemplate.RISK_HIGH,
            public_health_caveats="Requires consent or approved lawful basis.",
            created_by=self.analyst,
        )
        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700222333",
            template=self.approved_template,
            template_key=self.approved_template.template_key,
            template_version=self.approved_template.version,
            requested_language="en",
            resolved_language="en",
            fallback_used=False,
            message="CHVs: Message Surface Ward needs cholera prevention checks.",
            status=Alert.STATUS_DELIVERED,
            sent_at=timezone.now(),
            governance_metadata={
                "schema_version": "message-audience-governance-phase-2-v1",
                "workflow": "risk_alert_sms",
                "template": {
                    "template_key": self.approved_template.template_key,
                    "template_version": self.approved_template.version,
                    "template_public_id": str(self.approved_template.public_id),
                    "language": "en",
                    "requested_language": "en",
                    "resolved_language": "en",
                    "fallback_used": False,
                    "rendered_placeholder_keys": ["ward_name"],
                },
                "language": {
                    "requested_language": "en",
                    "resolved_language": "en",
                    "fallback_used": False,
                    "template_language": "en",
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
                "risk_score_id": self.risk_score.id,
                "risk_level": self.risk_score.risk_level,
            },
        )
        CHVMessage.objects.create(
            chv=self.chv,
            ward=self.ward,
            template=self.approved_template,
            template_key=self.approved_template.template_key,
            template_version=self.approved_template.version,
            requested_language="en",
            resolved_language="en",
            fallback_used=False,
            message_body="CHVs: Message Surface Ward needs cholera prevention checks.",
            status=CHVMessage.STATUS_FAILED,
            governance_metadata={
                "schema_version": "message-audience-governance-phase-2-v1",
                "workflow": "chv_workflow_message",
                "template": {
                    "template_key": self.approved_template.template_key,
                    "template_version": self.approved_template.version,
                    "template_public_id": str(self.approved_template.public_id),
                    "language": "en",
                    "requested_language": "en",
                    "resolved_language": "en",
                    "fallback_used": False,
                    "rendered_placeholder_keys": ["ward_name"],
                },
                "language": {
                    "requested_language": "en",
                    "resolved_language": "en",
                    "fallback_used": False,
                    "template_language": "en",
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
        ContactPreference.objects.create(
            audience_type=ContactPreference.AUDIENCE_CHV,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="+254700222333",
            contact_reference=f"chv:{self.chv.public_id}",
            consent_status=ContactPreference.CONSENT_GRANTED,
            opt_out_status=ContactPreference.OPT_OUT_OPTED_OUT,
            source="reply_stop",
            source_reference="message-management-opt-out",
            recorded_by=self.admin,
        )
        ContactPreferenceAuditEvent.objects.create(
            action=ContactPreferenceAuditEvent.ACTION_BLOCKED_OPT_OUT,
            audience_type=ContactPreference.AUDIENCE_CHV,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="+254700222333",
            contact_reference=f"chv:{self.chv.public_id}",
            actor=self.admin,
            reason="contact_opted_out",
            metadata={"workflow": "risk_alert_sms"},
        )
        create_ussd_session_log(
            session_id="message-surface-ussd-complete",
            phone_number="+254700111001",
            service_code="*123#",
            text="2*1",
        )
        create_ussd_session_log(
            session_id="message-surface-ussd-invalid",
            phone_number="+254700111002",
            service_code="*123#",
            text="9",
        )

    def test_dashboard_exposes_templates_delivery_outcomes_and_ussd_analytics(self):
        self.client.force_authenticate(self.analyst)

        response = self.client.get(reverse("message-governance-dashboard"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["schema_version"], "message-management-phase-7-v1")
        self.assertGreaterEqual(response.data["summary"]["template_count"], 3)
        self.assertGreaterEqual(response.data["summary"]["delivery_record_count"], 2)
        self.assertGreaterEqual(response.data["summary"]["communication_reach_count"], 1)
        self.assertGreaterEqual(response.data["summary"]["delivery_failure_count"], 1)
        self.assertGreaterEqual(response.data["summary"]["opt_out_count"], 1)
        self.assertGreaterEqual(response.data["summary"]["ussd_total_sessions"], 2)
        self.assertEqual(response.data["summary"]["audit_status"], "pass")
        self.assertIn("templates", response.data)
        self.assertIn("template_language_coverage", response.data)
        self.assertIn("missing_translation_dashboard", response.data)
        self.assertIn("delivery_summary", response.data)
        self.assertIn("ussd_analytics", response.data)
        self.assertIn("ussd_route_tree_preview", response.data)
        self.assertIn("offline_guidance_preview", response.data)
        self.assertIn("localization_rollout", response.data["audit"])
        self.assertGreaterEqual(response.data["summary"]["missing_translation_count"], 1)
        self.assertIn("strict_localization_issue_count", response.data["summary"])
        self.assertGreaterEqual(len(response.data["delivery_summary"]["reach_by_audience_channel"]), 1)
        self.assertGreaterEqual(response.data["delivery_summary"]["opt_out_summary"]["total_current_opt_out_count"], 1)
        self.assertGreaterEqual(len(response.data["delivery_summary"]["template_usage_by_version"]), 1)
        template_keys = {record["template_key"] for record in response.data["templates"]}
        self.assertIn(self.pending_template.template_key, template_keys)
        outcomes = {
            row["session_outcome"]
            for row in response.data["ussd_analytics"]["by_outcome"]
        }
        self.assertIn("COMPLETED", outcomes)
        self.assertIn("INVALID_INPUT", outcomes)
        coverage_row = next(
            row
            for row in response.data["template_language_coverage"]["rows"]
            if row["template_key"] == self.pending_template.template_key and row["version"] == self.pending_template.version
        )
        self.assertIn("luo", coverage_row["missing_languages"])

    def test_template_detail_includes_version_history_language_variants_and_usage(self):
        self.client.force_authenticate(self.analyst)

        response = self.client.get(
            reverse("message-template-governance-detail", kwargs={"public_id": self.pending_template.public_id})
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["template"]["public_id"], str(self.pending_template.public_id))
        self.assertEqual(response.data["template"]["preview"]["context"]["ward_name"], "Kanyasa")
        self.assertEqual(response.data["template"]["audience_preview"]["consent_requirement"], "consent_or_approved_lawful_basis")
        languages = {record["language"] for record in response.data["language_variants"]}
        self.assertEqual(languages, {"en", "sw"})
        preview_languages = {record["language"] for record in response.data["side_by_side_preview"]}
        self.assertEqual(preview_languages, {"en", "sw", "luo"})
        sw_preview = next(record for record in response.data["side_by_side_preview"] if record["language"] == "sw")
        self.assertEqual(sw_preview["rendered_body"], "Tumia maji salama Kanyasa.")
        luo_preview = next(record for record in response.data["side_by_side_preview"] if record["language"] == "luo")
        self.assertFalse(luo_preview["exists"])
        self.assertTrue(luo_preview["fallback_used"])
        self.assertIn("version_history", response.data)
        self.assertIn("delivery_summary", response.data)

    def test_admin_can_approve_template_and_analyst_cannot(self):
        self.client.force_authenticate(self.analyst)
        forbidden = self.client.post(
            reverse("message-template-approval", kwargs={"public_id": self.pending_template.public_id}),
            {"action": "approve", "reason": "Reviewed by county health promotion."},
            format="json",
        )
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(self.admin)
        response = self.client.post(
            reverse("message-template-approval", kwargs={"public_id": self.pending_template.public_id}),
            {"action": "approve", "reason": "Reviewed by county health promotion."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.pending_template.refresh_from_db()
        self.assertEqual(self.pending_template.approval_status, MessageTemplate.APPROVAL_APPROVED)
        self.assertEqual(self.pending_template.approved_by, self.admin)
        self.assertIsNotNone(self.pending_template.approved_at)
        self.assertEqual(self.pending_template.lineage_metadata["approval_events"][-1]["action"], "approve")

    def test_admin_can_reject_translation_variant(self):
        self.client.force_authenticate(self.admin)

        response = self.client.post(
            reverse("message-template-approval", kwargs={"public_id": self.sw_variant.public_id}),
            {"action": "reject", "reason": "Needs safer public-health wording."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.sw_variant.refresh_from_db()
        self.assertEqual(self.sw_variant.approval_status, MessageTemplate.APPROVAL_REJECTED)
        self.assertEqual(self.sw_variant.translation_status, MessageTemplate.TRANSLATION_DRAFT)
        self.assertEqual(self.sw_variant.lineage_metadata["approval_events"][-1]["action"], "reject")
