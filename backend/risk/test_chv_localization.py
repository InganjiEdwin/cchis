from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from risk.chv_offline import (
    OFFLINE_CHV_CONTRACT_VERSION,
    OFFLINE_CHV_DECISION_SUPPORT_RECOMMENDATION_TEMPLATE_KEYS,
    build_chv_offline_contract,
)
from risk.chv_localization import build_chv_localization_inventory_report, resolve_language_preference
from risk.message_governance import build_message_governance_audit, render_message_template
from risk.message_management import transition_message_template_approval
from risk.models import CHV, CHVDeviceRegistration, MessageTemplate, Ward


class CHVLocalizationPhaseZeroOneTests(APITestCase):
    def setUp(self):
        self.ward = Ward.objects.create(name="Localization Ward", county="Migori")
        self.chv_user = User.objects.create_user(
            username="localization-chv",
            password="StrongPass123!",
            role=User.ROLE_CHV,
            ward=self.ward,
            phone_number="+254700000111",
        )
        self.chv = CHV.objects.create(
            name="Localization CHV",
            phone_number="+254700000111",
            ward=self.ward,
            preferred_language="sw",
        )

    def _approved_template(self, *, channel: str, audience_type: str, template_key: str, language: str = "en"):
        approved_at = timezone.now()
        source_template = None
        if language != "en":
            source_template = MessageTemplate.objects.filter(
                template_key=template_key,
                version=1,
                language="en",
            ).first()
        template, _created = MessageTemplate.objects.update_or_create(
            template_key=template_key,
            language=language,
            version=1,
            defaults={
                "audience_type": audience_type,
                "channel": channel,
                "title": "Core guidance",
                "body": "Use safe water in {ward_name}.",
                "placeholders": ["ward_name"],
                "approval_status": MessageTemplate.APPROVAL_APPROVED,
                "approved_at": approved_at,
                "retired_at": None,
                "translation_status": MessageTemplate.TRANSLATION_APPROVED,
                "source_template": source_template,
                "translation_reviewed_at": approved_at,
                "owner": "county_health_promotion",
                "risk_level": MessageTemplate.RISK_HIGH,
                "public_health_caveats": "Approved cholera prevention copy.",
            },
        )
        return template

    def test_phase_zero_inventory_has_required_chv_language_surfaces(self):
        report = build_chv_localization_inventory_report()

        self.assertEqual(report["supported_languages"], ["en", "sw", "luo"])
        self.assertEqual(report["missing_required_fields"], [])
        self.assertGreaterEqual(report["surface_count"], 8)
        self.assertGreaterEqual(report["category_counts"]["ui_chrome"], 1)
        self.assertGreaterEqual(report["category_counts"]["public_health_copy"], 1)
        triage_recommendations = {
            surface["localization_key"]: surface
            for surface in report["surfaces"]
        }["chv.offline.triage_recommendations"]
        self.assertEqual(triage_recommendations["category"], "public_health_copy")
        self.assertEqual(triage_recommendations["management"], "governed_message_template")
        self.assertEqual(report["unmanaged_english_only_gaps"], [])

    def test_language_preference_resolution_keeps_requested_and_fallback_auditable(self):
        resolved = resolve_language_preference(requested_language="fr", chv=self.chv)

        self.assertEqual(resolved.requested_language, "fr")
        self.assertEqual(resolved.resolved_language, "en")
        self.assertTrue(resolved.fallback_used)
        self.assertEqual(resolved.preference_source, "request")

    def test_offline_contract_carries_language_metadata_and_guidance_fallback(self):
        self._approved_template(
            channel=MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE,
            audience_type=MessageTemplate.AUDIENCE_CHV,
            template_key="cholera.chv.test.english_only_guidance_fallback",
            language="en",
        )
        self.client.force_authenticate(self.chv_user)

        response = self.client.get(reverse("chv-offline-contract"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["requested_language"], "sw")
        self.assertEqual(response.data["resolved_language"], "sw")
        self.assertTrue(response.data["fallback_used"])
        guidance_bundle = response.data["download_bundle"]["guidance_bundle"]
        self.assertEqual(guidance_bundle["requested_language"], "sw")
        self.assertEqual(guidance_bundle["resolved_language"], "sw")
        self.assertTrue(guidance_bundle["fallback_used"])
        fallback_guidance_items = [
            item
            for item in guidance_bundle["items"]
            if item["template_key"] == "cholera.chv.test.english_only_guidance_fallback"
        ]
        self.assertEqual(len(fallback_guidance_items), 1)
        self.assertEqual(fallback_guidance_items[0]["resolved_language"], "en")
        self.assertTrue(fallback_guidance_items[0]["fallback_used"])
        task_bundle = response.data["download_bundle"]["task_bundle"]
        self.assertEqual(task_bundle["requested_language"], "sw")
        self.assertEqual(task_bundle["resolved_language"], "sw")
        self.assertFalse(task_bundle["fallback_used"])
        rule_bundle = response.data["download_bundle"]["decision_support_rule_bundle"]
        self.assertEqual(rule_bundle["requested_language"], "sw")
        recommendations_by_key = {
            item["recommendation_key"]: item
            for item in rule_bundle["recommendations"]
        }
        self.assertEqual(
            recommendations_by_key["urgent_referral"]["template_key"],
            "cholera.chv.triage.urgent_referral_offline",
        )
        self.assertEqual(recommendations_by_key["urgent_referral"]["source"], "governed_message_template")
        self.assertEqual(recommendations_by_key["urgent_referral"]["governance_status"], "approved")
        self.assertEqual(recommendations_by_key["urgent_referral"]["resolved_language"], "sw")
        self.assertFalse(recommendations_by_key["urgent_referral"]["fallback_used"])

    def test_unsupported_offline_language_request_falls_back_to_english(self):
        self.client.force_authenticate(self.chv_user)

        response = self.client.get(reverse("chv-offline-contract"), {"language": "fr"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["requested_language"], "fr")
        self.assertEqual(response.data["resolved_language"], "en")
        self.assertTrue(response.data["fallback_used"])

    def test_offline_contract_fails_closed_when_governed_content_is_missing(self):
        offline_templates = MessageTemplate.objects.filter(channel=MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE)
        MessageTemplate.objects.filter(source_template__in=offline_templates).delete()
        offline_templates.delete()

        contract = build_chv_offline_contract(self.chv_user, self.ward)

        self.assertEqual(contract["requested_language"], "sw")
        self.assertEqual(contract["resolved_language"], "en")
        self.assertTrue(contract["fallback_used"])
        guidance_bundle = contract["download_bundle"]["guidance_bundle"]
        self.assertEqual(guidance_bundle["items"], [])
        self.assertTrue(guidance_bundle["content_unavailable"])
        self.assertEqual(guidance_bundle["governance_status"], "no_approved_guidance_templates")
        self.assertEqual(guidance_bundle["resolved_language"], "en")
        self.assertTrue(guidance_bundle["fallback_used"])
        rule_bundle = contract["download_bundle"]["decision_support_rule_bundle"]
        self.assertEqual(rule_bundle["recommendations"], [])
        self.assertTrue(rule_bundle["content_unavailable"])
        self.assertEqual(rule_bundle["governance_status"], "missing_required_recommendation_templates")
        self.assertCountEqual(
            rule_bundle["missing_recommendation_keys"],
            list(OFFLINE_CHV_DECISION_SUPPORT_RECOMMENDATION_TEMPLATE_KEYS),
        )
        self.assertEqual(rule_bundle["resolved_language"], "en")
        self.assertTrue(rule_bundle["fallback_used"])

    def test_offline_contract_records_bundle_request_counts_on_registered_device(self):
        self._approved_template(
            channel=MessageTemplate.CHANNEL_OFFLINE_CHV_BUNDLE,
            audience_type=MessageTemplate.AUDIENCE_CHV,
            template_key="cholera.chv.registered_bundle_counter",
            language="en",
        )
        registration = CHVDeviceRegistration.objects.create(
            user=self.chv_user,
            chv=self.chv,
            ward=self.ward,
            device_id="registered-bundle-counter",
            contract_version=OFFLINE_CHV_CONTRACT_VERSION,
            preferred_language="sw",
            is_active=True,
            metadata={"language": {"requested_language": "sw", "resolved_language": "sw", "fallback_used": False}},
        )

        contract = build_chv_offline_contract(
            self.chv_user,
            self.ward,
            device_registration=registration,
        )

        registration.refresh_from_db()
        request_counts = registration.metadata["offline_bundle_request_counts"]
        self.assertEqual(contract["download_bundle"]["resolved_language"], "sw")
        self.assertEqual(len(request_counts), 1)
        self.assertEqual(request_counts[0]["requested_language"], "sw")
        self.assertEqual(request_counts[0]["resolved_language"], "sw")
        self.assertTrue(request_counts[0]["fallback_used"])
        self.assertEqual(request_counts[0]["count"], 1)

    def test_message_template_render_metadata_records_language_fallback(self):
        template = self._approved_template(
            channel=MessageTemplate.CHANNEL_SMS,
            audience_type=MessageTemplate.AUDIENCE_CHV,
            template_key="cholera.chv.language_fallback_probe_sms",
            language="en",
        )

        rendered = render_message_template(
            template_key=template.template_key,
            language="luo",
            context={"ward_name": "North Kanyamkago"},
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
        )

        self.assertEqual(rendered.template.language, "en")
        self.assertEqual(rendered.metadata["requested_language"], "luo")
        self.assertEqual(rendered.metadata["resolved_language"], "en")
        self.assertTrue(rendered.metadata["fallback_used"])

    def test_translated_template_cannot_be_used_before_translation_approval(self):
        source = self._approved_template(
            channel=MessageTemplate.CHANNEL_SMS,
            audience_type=MessageTemplate.AUDIENCE_CHV,
            template_key="cholera.chv.translation_gate_sms",
            language="en",
        )
        MessageTemplate.objects.create(
            template_key=source.template_key,
            audience_type=source.audience_type,
            channel=source.channel,
            language="sw",
            version=source.version,
            title="Swahili draft",
            body="Tumia maji salama {ward_name}.",
            placeholders=["ward_name"],
            approval_status=MessageTemplate.APPROVAL_APPROVED,
            approved_at=timezone.now(),
            translation_status=MessageTemplate.TRANSLATION_DRAFT,
            source_template=source,
            owner="county_health_promotion",
            risk_level=MessageTemplate.RISK_HIGH,
            public_health_caveats="Approved cholera prevention copy.",
        )

        rendered = render_message_template(
            template_key=source.template_key,
            language="sw",
            context={"ward_name": "North Kanyamkago"},
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
        )

        self.assertEqual(rendered.template.language, "en")
        self.assertTrue(rendered.metadata["fallback_used"])

        versioned_rendered = render_message_template(
            template_key=source.template_key,
            version=source.version,
            language="sw",
            context={"ward_name": "North Kanyamkago"},
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
        )

        self.assertEqual(versioned_rendered.template.language, "en")
        self.assertTrue(versioned_rendered.metadata["fallback_used"])

    def test_translation_approval_requires_source_link_and_placeholder_parity(self):
        source = self._approved_template(
            channel=MessageTemplate.CHANNEL_SMS,
            audience_type=MessageTemplate.AUDIENCE_CHV,
            template_key="cholera.chv.translation_parity_sms",
            language="en",
        )
        translated = MessageTemplate.objects.create(
            template_key=source.template_key,
            audience_type=source.audience_type,
            channel=source.channel,
            language="sw",
            version=source.version,
            title="Swahili parity drift",
            body="Tumia maji salama.",
            placeholders=[],
            approval_status=MessageTemplate.APPROVAL_PENDING_REVIEW,
            source_template=source,
            owner="county_health_promotion",
            risk_level=MessageTemplate.RISK_HIGH,
            public_health_caveats="Approved cholera prevention copy.",
        )

        with self.assertRaises(ValidationError):
            transition_message_template_approval(
                translated,
                action="approve",
                actor=self.chv_user,
                reason="Reviewed translated meaning.",
            )

    def test_approved_translation_renders_and_records_review_metadata(self):
        source = self._approved_template(
            channel=MessageTemplate.CHANNEL_SMS,
            audience_type=MessageTemplate.AUDIENCE_CHV,
            template_key="cholera.chv.translation_approved_sms",
            language="en",
        )
        translated = MessageTemplate.objects.create(
            template_key=source.template_key,
            audience_type=source.audience_type,
            channel=source.channel,
            language="sw",
            version=source.version,
            title="Swahili approved",
            body="Tumia maji salama {ward_name}.",
            placeholders=["ward_name"],
            approval_status=MessageTemplate.APPROVAL_PENDING_REVIEW,
            source_template=source,
            owner="county_health_promotion",
            risk_level=MessageTemplate.RISK_HIGH,
            public_health_caveats="Approved cholera prevention copy.",
        )

        transition_message_template_approval(
            translated,
            action="approve",
            actor=self.chv_user,
            reason="Reviewed translated meaning.",
        )
        translated.refresh_from_db()

        rendered = render_message_template(
            template_key=source.template_key,
            language="sw",
            context={"ward_name": "North Kanyamkago"},
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
        )

        self.assertEqual(rendered.template.language, "sw")
        self.assertFalse(rendered.metadata["fallback_used"])
        self.assertEqual(translated.translation_status, MessageTemplate.TRANSLATION_APPROVED)
        self.assertEqual(translated.translation_reviewed_by, self.chv_user)
        self.assertIsNotNone(translated.translation_reviewed_at)

    def test_retiring_english_source_blocks_stale_translations(self):
        source = self._approved_template(
            channel=MessageTemplate.CHANNEL_SMS,
            audience_type=MessageTemplate.AUDIENCE_CHV,
            template_key="cholera.chv.translation_retire_sms",
            language="en",
        )
        translated = MessageTemplate.objects.create(
            template_key=source.template_key,
            audience_type=source.audience_type,
            channel=source.channel,
            language="sw",
            version=source.version,
            title="Swahili stale",
            body="Tumia maji salama {ward_name}.",
            placeholders=["ward_name"],
            approval_status=MessageTemplate.APPROVAL_APPROVED,
            approved_at=timezone.now(),
            translation_status=MessageTemplate.TRANSLATION_APPROVED,
            source_template=source,
            translation_reviewed_at=timezone.now(),
            owner="county_health_promotion",
            risk_level=MessageTemplate.RISK_HIGH,
            public_health_caveats="Approved cholera prevention copy.",
        )

        transition_message_template_approval(source, action="retire", actor=self.chv_user, reason="New source version.")
        translated.refresh_from_db()

        self.assertEqual(translated.translation_status, MessageTemplate.TRANSLATION_BLOCKED_SOURCE_RETIRED)

        MessageTemplate.objects.filter(pk=translated.pk).update(
            translation_status=MessageTemplate.TRANSLATION_APPROVED,
            updated_at=timezone.now(),
        )
        replacement_source = MessageTemplate.objects.create(
            template_key=source.template_key,
            audience_type=source.audience_type,
            channel=source.channel,
            language="en",
            version=2,
            title="Replacement source",
            body="Use safe water in {ward_name}.",
            placeholders=["ward_name"],
            approval_status=MessageTemplate.APPROVAL_APPROVED,
            approved_at=timezone.now(),
            owner="county_health_promotion",
            risk_level=MessageTemplate.RISK_HIGH,
            public_health_caveats="Approved cholera prevention copy.",
        )
        rendered = render_message_template(
            template_key=source.template_key,
            language="sw",
            context={"ward_name": "North Kanyamkago"},
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
        )

        self.assertEqual(rendered.template.language, "en")
        self.assertEqual(rendered.template.version, replacement_source.version)
        self.assertTrue(rendered.metadata["fallback_used"])

    def test_translation_registry_audit_reports_missing_required_language_coverage(self):
        source = self._approved_template(
            channel=MessageTemplate.CHANNEL_SMS,
            audience_type=MessageTemplate.AUDIENCE_CHV,
            template_key="cholera.chv.translation_coverage_sms",
            language="en",
        )

        audit = build_message_governance_audit()
        checks = {check["id"]: check for check in audit["audit_checks"]}

        self.assertEqual(checks["phase_2_chv_template_translation_registry"]["status"], "fail")
        self.assertIn(
            source.template_key,
            {
                issue["template_key"]
                for issue in checks["phase_2_chv_template_translation_registry"]["evidence"]["issues"]
            },
        )
