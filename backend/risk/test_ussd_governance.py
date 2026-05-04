from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from risk.models import UssdMenuVersion, UssdSessionLog
from risk.ussd_governance import (
    USSD_BUILTIN_VERSION_LABEL,
    USSD_MENU_GOVERNANCE_SCHEMA_VERSION,
    USSD_MENU_KEY,
    USSD_SESSION_OUTCOME_TAXONOMY,
    build_ussd_governance_audit,
)


class UssdGovernanceTests(APITestCase):
    def _post_ussd(self, *, session_id: str, text: str, language: str = "en"):
        return self.client.post(
            reverse("ussd-menu"),
            {
                "sessionId": session_id,
                "serviceCode": "*123#",
                "phoneNumber": "+254700000001",
                "text": text,
                "language": language,
            },
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
        menu_version = UssdMenuVersion.objects.create(
            menu_key=USSD_MENU_KEY,
            version_label="sw-v1",
            language="sw",
            title="Menyu ya Afya",
            menu_tree={
                "routes": {"": "root", "1": "safe_water"},
                "nodes": {
                    "root": {
                        "response_type": "CON",
                        "body": "Karibu CCHIS\n1. Maji salama",
                    },
                    "safe_water": {
                        "response_type": "END",
                        "body": "Tumia maji yaliyotibiwa na osha mikono mara kwa mara.",
                    },
                },
            },
            safe_fallback_copy="END Chaguo si sahihi. Jaribu tena.",
            session_outcome_taxonomy=USSD_SESSION_OUTCOME_TAXONOMY,
            approval_status=UssdMenuVersion.STATUS_APPROVED,
            approved_at=timezone.now(),
            is_active=True,
            lineage_metadata={"source": "test_language_variant"},
        )

        response = self._post_ussd(session_id="sw-001", text="", language="sw")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["response"], "CON Karibu CCHIS\n1. Maji salama")

        log = UssdSessionLog.objects.get(session_id="sw-001")
        self.assertEqual(log.menu_version, menu_version)
        self.assertEqual(log.menu_version_label, "sw-v1")
        self.assertEqual(log.language, "sw")
        self.assertEqual(log.governance_metadata["source"], "database")
        self.assertEqual(log.governance_metadata["menu_version_public_id"], str(menu_version.public_id))

    def test_malformed_active_menu_uses_configured_safe_fallback(self):
        menu_version = UssdMenuVersion.objects.create(
            menu_key=USSD_MENU_KEY,
            version_label="sw-bad-v1",
            language="sw",
            title="Broken Menu",
            menu_tree={"nodes": {}},
            safe_fallback_copy="END Huduma haipatikani kwa sasa.",
            approval_status=UssdMenuVersion.STATUS_APPROVED,
            approved_at=timezone.now(),
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
        self.assertEqual(checks["phase_3_ussd_session_traceability"]["status"], "pass")
        taxonomy_evidence = checks["phase_3_ussd_outcome_taxonomy_available"]["evidence"]
        self.assertGreaterEqual(taxonomy_evidence["completed_log_count"], 1)
        self.assertGreaterEqual(taxonomy_evidence["invalid_input_log_count"], 1)
        self.assertGreaterEqual(taxonomy_evidence["abandoned_inferred_log_count"], 1)
