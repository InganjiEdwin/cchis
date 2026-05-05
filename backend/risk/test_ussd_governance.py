from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from risk.models import UssdMenuVersion, UssdSessionLog
from risk.ussd_governance import (
    USSD_BUILTIN_VERSION_LABEL,
    USSD_LANGUAGE_SELECTION_MENU_LEVEL,
    USSD_LANGUAGE_SELECTION_VERSION_LABEL,
    USSD_MENU_GOVERNANCE_SCHEMA_VERSION,
    USSD_MENU_KEY,
    USSD_REQUIRED_MENU_LANGUAGES,
    USSD_RESPONSE_TEXT_MAX_CHARS,
    USSD_SESSION_OUTCOME_TAXONOMY,
    build_ussd_governance_audit,
    validate_ussd_menu_tree,
)


class UssdGovernanceTests(APITestCase):
    def _post_ussd(self, *, session_id: str, text: str, language: str = "en", include_language: bool = True):
        payload = {
            "sessionId": session_id,
            "serviceCode": "*123#",
            "phoneNumber": "+254700000001",
            "text": text,
        }
        if include_language:
            payload["language"] = language
        return self.client.post(
            reverse("ussd-menu"),
            payload,
            format="json",
        )

    def test_default_root_session_is_traced_to_version_and_language(self):
        response = self._post_ussd(session_id="root-001", text="")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["response"].startswith("CON Welcome to CCHIS Health Menu"))

        log = UssdSessionLog.objects.get(session_id="root-001")
        seeded_version = UssdMenuVersion.objects.get(
            menu_key=USSD_MENU_KEY,
            language="en",
            version_label=USSD_BUILTIN_VERSION_LABEL,
        )
        self.assertEqual(log.menu_version, seeded_version)
        self.assertEqual(log.menu_key, USSD_MENU_KEY)
        self.assertEqual(log.menu_version_label, USSD_BUILTIN_VERSION_LABEL)
        self.assertEqual(log.language, "en")
        self.assertEqual(log.requested_language, "en")
        self.assertEqual(log.resolved_language, "en")
        self.assertFalse(log.fallback_used)
        self.assertEqual(log.session_outcome, UssdSessionLog.OUTCOME_STARTED)
        self.assertFalse(log.invalid_option)
        self.assertFalse(log.is_terminal)
        self.assertEqual(log.governance_metadata["schema_version"], USSD_MENU_GOVERNANCE_SCHEMA_VERSION)
        self.assertEqual(log.governance_metadata["source"], "database")

    def test_invalid_option_uses_safe_fallback_and_taxonomy(self):
        response = self._post_ussd(session_id="invalid-001", text="9")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["response"], "END Invalid option. Please try again.")

        log = UssdSessionLog.objects.get(session_id="invalid-001")
        self.assertEqual(log.menu_level, "invalid")
        self.assertEqual(log.session_outcome, UssdSessionLog.OUTCOME_INVALID_INPUT)
        self.assertTrue(log.invalid_option)
        self.assertTrue(log.is_terminal)
        self.assertIn(UssdSessionLog.OUTCOME_INVALID_INPUT, log.governance_metadata["session_outcome_taxonomy"])

    def test_active_language_variant_is_used_and_linked_to_session(self):
        menu_version = UssdMenuVersion.objects.get(
            menu_key=USSD_MENU_KEY,
            language="sw",
            version_label=USSD_BUILTIN_VERSION_LABEL,
        )

        response = self._post_ussd(session_id="sw-001", text="", language="sw")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["response"].startswith("CON Karibu CCHIS Afya"))

        log = UssdSessionLog.objects.get(session_id="sw-001")
        self.assertEqual(log.menu_version, menu_version)
        self.assertEqual(log.menu_version_label, USSD_BUILTIN_VERSION_LABEL)
        self.assertEqual(log.language, "sw")
        self.assertEqual(log.requested_language, "sw")
        self.assertEqual(log.resolved_language, "sw")
        self.assertFalse(log.fallback_used)
        self.assertEqual(log.governance_metadata["source"], "database")
        self.assertEqual(log.governance_metadata["menu_version_public_id"], str(menu_version.public_id))

    def test_unsupported_language_request_falls_back_to_english_with_metadata(self):
        response = self._post_ussd(session_id="fr-unsupported-001", text="", language="fr")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["response"].startswith("CON Welcome to CCHIS Health Menu"))

        log = UssdSessionLog.objects.get(session_id="fr-unsupported-001")
        self.assertEqual(log.language, "en")
        self.assertEqual(log.requested_language, "fr")
        self.assertEqual(log.resolved_language, "en")
        self.assertTrue(log.fallback_used)
        self.assertTrue(log.governance_metadata["fallback_used"])

    def test_malformed_active_menu_uses_configured_safe_fallback(self):
        UssdMenuVersion.objects.filter(menu_key=USSD_MENU_KEY, language="sw", is_active=True).update(is_active=False)
        source_menu = UssdMenuVersion.objects.get(
            menu_key=USSD_MENU_KEY,
            language="en",
            version_label=USSD_BUILTIN_VERSION_LABEL,
        )
        menu_version = UssdMenuVersion.objects.create(
            menu_key=USSD_MENU_KEY,
            version_label="sw-bad-v1",
            language="sw",
            title="Broken Menu",
            menu_tree={"nodes": {}},
            safe_fallback_copy="END Huduma haipatikani kwa sasa.",
            approval_status=UssdMenuVersion.STATUS_APPROVED,
            approved_at=timezone.now(),
            translation_status=UssdMenuVersion.TRANSLATION_APPROVED,
            source_menu_version=source_menu,
            translation_reviewed_at=timezone.now(),
            is_active=True,
            lineage_metadata={"source": "test_malformed_menu"},
        )

        response = self._post_ussd(session_id="sw-bad-001", text="", language="sw")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["response"], "END Huduma haipatikani kwa sasa.")

        log = UssdSessionLog.objects.get(session_id="sw-bad-001")
        self.assertEqual(log.menu_version, menu_version)
        self.assertEqual(log.menu_level, "safe_fallback")
        self.assertEqual(log.session_outcome, UssdSessionLog.OUTCOME_SAFE_FALLBACK)
        self.assertTrue(log.is_terminal)
        self.assertIn("menu_validation_error", log.governance_metadata)

    def test_seeded_multilingual_menu_versions_are_active_and_route_equivalent(self):
        versions = {
            language: UssdMenuVersion.objects.get(
                menu_key=USSD_MENU_KEY,
                language=language,
                version_label=USSD_BUILTIN_VERSION_LABEL,
                is_active=True,
            )
            for language in USSD_REQUIRED_MENU_LANGUAGES
        }
        english_version = versions["en"]
        route_map = english_version.menu_tree["routes"]
        node_keys = set(english_version.menu_tree["nodes"])
        response_types = {
            node_key: node["response_type"]
            for node_key, node in english_version.menu_tree["nodes"].items()
        }

        for language, menu_version in versions.items():
            self.assertEqual(menu_version.approval_status, UssdMenuVersion.STATUS_APPROVED)
            self.assertTrue(menu_version.safe_fallback_copy.startswith("END "))
            self.assertEqual(menu_version.menu_tree["routes"], route_map)
            self.assertEqual(set(menu_version.menu_tree["nodes"]), node_keys)
            self.assertEqual(
                {
                    node_key: node["response_type"]
                    for node_key, node in menu_version.menu_tree["nodes"].items()
                },
                response_types,
            )
            if language != "en":
                self.assertEqual(menu_version.translation_status, UssdMenuVersion.TRANSLATION_APPROVED)
                self.assertEqual(menu_version.source_menu_version, english_version)

    def test_ussd_menu_translation_review_can_be_rejected_and_reapproved_outside_admin(self):
        admin = User.objects.create_user(
            username="ussd-reviewer",
            password="StrongPass123!",
            role=User.ROLE_ADMIN,
        )
        self.client.force_authenticate(admin)
        menu_version = UssdMenuVersion.objects.get(
            menu_key=USSD_MENU_KEY,
            language="sw",
            version_label=USSD_BUILTIN_VERSION_LABEL,
        )

        reject_response = self.client.post(
            reverse("ussd-menu-version-approval", kwargs={"public_id": menu_version.public_id}),
            {"action": "reject", "reason": "Translation wording needs review."},
            format="json",
        )

        self.assertEqual(reject_response.status_code, status.HTTP_200_OK)
        menu_version.refresh_from_db()
        self.assertEqual(menu_version.approval_status, UssdMenuVersion.STATUS_DRAFT)
        self.assertEqual(menu_version.translation_status, UssdMenuVersion.TRANSLATION_DRAFT)
        self.assertFalse(menu_version.is_active)

        approve_response = self.client.post(
            reverse("ussd-menu-version-approval", kwargs={"public_id": menu_version.public_id}),
            {"action": "approve", "reason": "Reviewed Kiswahili USSD copy."},
            format="json",
        )

        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        menu_version.refresh_from_db()
        self.assertEqual(menu_version.approval_status, UssdMenuVersion.STATUS_APPROVED)
        self.assertEqual(menu_version.translation_status, UssdMenuVersion.TRANSLATION_APPROVED)
        self.assertEqual(menu_version.translation_reviewed_by, admin)
        self.assertIsNotNone(menu_version.translation_reviewed_at)
        self.assertTrue(menu_version.is_active)

    def test_ussd_without_known_language_prompts_for_language_selection(self):
        response = self._post_ussd(session_id="select-language-001", text="", include_language=False)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["response"].startswith("CON Select language"))

        log = UssdSessionLog.objects.get(session_id="select-language-001")
        self.assertIsNone(log.menu_version)
        self.assertEqual(log.menu_version_label, USSD_LANGUAGE_SELECTION_VERSION_LABEL)
        self.assertEqual(log.menu_level, USSD_LANGUAGE_SELECTION_MENU_LEVEL)
        self.assertEqual(log.resolved_language, "en")
        self.assertTrue(log.governance_metadata["language_selection_required"])
        self.assertFalse(log.governance_metadata["language_selected"])

    def test_language_choice_persists_for_session_routes(self):
        prompt_response = self._post_ussd(session_id="persist-language-001", text="", include_language=False)
        select_response = self._post_ussd(session_id="persist-language-001", text="2", include_language=False)
        route_response = self._post_ussd(session_id="persist-language-001", text="1", include_language=False)

        self.assertTrue(prompt_response.data["response"].startswith("CON Select language"))
        self.assertTrue(select_response.data["response"].startswith("CON Karibu CCHIS Afya"))
        self.assertTrue(route_response.data["response"].startswith("END Usalama wa mafuriko"))

        logs = list(UssdSessionLog.objects.filter(session_id="persist-language-001").order_by("id"))
        self.assertEqual(logs[1].resolved_language, "sw")
        self.assertEqual(logs[1].governance_metadata["language_preference_source"], "language_selection")
        self.assertTrue(logs[1].governance_metadata["language_selected"])
        self.assertEqual(logs[2].resolved_language, "sw")
        self.assertEqual(logs[2].governance_metadata["language_preference_source"], "ussd_session")
        self.assertEqual(logs[2].session_outcome, UssdSessionLog.OUTCOME_COMPLETED)

    def test_invalid_option_uses_resolved_language_safe_fallback(self):
        response = self._post_ussd(session_id="sw-invalid-001", text="9", language="sw")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["response"], "END Chaguo si sahihi. Jaribu tena.")

        log = UssdSessionLog.objects.get(session_id="sw-invalid-001")
        self.assertEqual(log.resolved_language, "sw")
        self.assertEqual(log.session_outcome, UssdSessionLog.OUTCOME_INVALID_INPUT)
        self.assertTrue(log.invalid_option)

    def test_supported_languages_can_start_and_complete(self):
        cases = [
            ("en", "CON Welcome to CCHIS Health Menu", "END Flood safety"),
            ("sw", "CON Karibu CCHIS Afya", "END Usalama wa mafuriko"),
            ("luo", "CON Oyawore e CCHIS Afya", "END Puonj mar piny mopong'"),
        ]
        for language, root_prefix, terminal_prefix in cases:
            root_response = self._post_ussd(session_id=f"{language}-start-001", text="", language=language)
            terminal_response = self._post_ussd(session_id=f"{language}-complete-001", text="1", language=language)

            self.assertTrue(root_response.data["response"].startswith(root_prefix))
            self.assertTrue(terminal_response.data["response"].startswith(terminal_prefix))

            terminal_log = UssdSessionLog.objects.get(session_id=f"{language}-complete-001")
            self.assertEqual(terminal_log.resolved_language, language)
            self.assertEqual(terminal_log.session_outcome, UssdSessionLog.OUTCOME_COMPLETED)

    def test_ussd_response_length_budget_is_enforced(self):
        with self.assertRaises(ValidationError):
            validate_ussd_menu_tree(
                {
                    "routes": {"": "root"},
                    "nodes": {
                        "root": {
                            "response_type": "CON",
                            "body": "x" * USSD_RESPONSE_TEXT_MAX_CHARS,
                        },
                    },
                }
            )

    def test_new_root_request_infers_prior_non_terminal_abandonment(self):
        first_response = self._post_ussd(session_id="abandon-001", text="")
        second_response = self._post_ussd(session_id="abandon-001", text="")

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)

        logs = list(UssdSessionLog.objects.filter(session_id="abandon-001").order_by("id"))
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0].session_outcome, UssdSessionLog.OUTCOME_ABANDONED_INFERRED)
        self.assertEqual(logs[0].abandonment_reason, "new_root_request_after_non_terminal_step")
        self.assertTrue(logs[0].is_terminal)
        self.assertEqual(logs[1].session_outcome, UssdSessionLog.OUTCOME_STARTED)

    def test_ussd_governance_audit_passes_for_governed_logs(self):
        self._post_ussd(session_id="audit-complete-001", text="2*1")
        self._post_ussd(session_id="audit-invalid-001", text="9")
        self._post_ussd(session_id="audit-abandon-001", text="")
        self._post_ussd(session_id="audit-abandon-001", text="")

        audit = build_ussd_governance_audit()

        self.assertEqual(audit["overall_status"], "pass")
        checks = {check["id"]: check for check in audit["checks"]}
        self.assertEqual(checks["phase_4_multilingual_ussd_menu_coverage"]["status"], "pass")
        self.assertEqual(checks["phase_3_ussd_session_traceability"]["status"], "pass")
        taxonomy_evidence = checks["phase_3_ussd_outcome_taxonomy_available"]["evidence"]
        self.assertGreaterEqual(taxonomy_evidence["completed_log_count"], 1)
        self.assertGreaterEqual(taxonomy_evidence["invalid_input_log_count"], 1)
        self.assertGreaterEqual(taxonomy_evidence["abandoned_inferred_log_count"], 1)
        self.assertIn(
            {"resolved_language": "en", "session_outcome": UssdSessionLog.OUTCOME_COMPLETED, "count": 1},
            taxonomy_evidence["outcome_breakdown_by_language"],
        )
