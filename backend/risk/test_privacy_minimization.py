from django.test import SimpleTestCase

from core.privacy_inventory import (
    PRIVACY_FIELD_INVENTORY,
    PRIVACY_MINIMIZATION_RULES,
    PrivacyDataCategory,
    inventory_record_families,
    sensitive_inventory_items,
)

from .models import CHVCoverageRequest, CHVMessage, PreparednessAction
from .serializers import (
    CHVCoverageRequestCreateSerializer,
    CHVMessageCreateSerializer,
    CHVSyncRequestSerializer,
    CHVTriageRequestSerializer,
    PreparednessActionCreateSerializer,
    PreparednessActionTransitionSerializer,
)


class PrivacyFieldInventoryTests(SimpleTestCase):
    def test_phase_0_inventory_covers_plan_surfaces_and_labels_sensitive_fields(self):
        required_families = {
            "users",
            "chvs",
            "households_or_contacts",
            "triage_submissions",
            "sync_payloads",
            "alerts",
            "facility_contacts",
            "message_deliveries",
            "exports",
        }

        self.assertTrue(required_families.issubset(inventory_record_families()))
        self.assertGreaterEqual(len(PRIVACY_FIELD_INVENTORY), 20)
        self.assertTrue(
            any(
                item.data_category == PrivacyDataCategory.CHILD_HEALTH
                and item.record_family == "triage_submissions"
                for item in PRIVACY_FIELD_INVENTORY
            )
        )
        self.assertTrue(
            any(
                item.data_category == PrivacyDataCategory.CONTACT
                and item.field_name in {"phone_number", "phone", "contact_phone"}
                for item in sensitive_inventory_items()
            )
        )

    def test_phase_0_inventory_flags_unnecessary_or_retention_limited_fields(self):
        flagged = [
            item
            for item in PRIVACY_FIELD_INVENTORY
            if "reject" in item.minimization_action.lower()
            or "do not collect" in item.minimization_action.lower()
            or "prunable" in item.retention_note.lower()
        ]

        self.assertTrue(any(item.field_name == "household_name" for item in flagged))
        self.assertTrue(any(item.model_label == "risk.SyncQueue" and item.field_name == "payload" for item in flagged))
        self.assertTrue(any(item.model_label == "risk.TriageSession" and item.field_name == "text_input" for item in flagged))

    def test_phase_1_minimization_rules_have_serializer_enforcement_surfaces(self):
        surfaces = " ".join(
            surface
            for rule in PRIVACY_MINIMIZATION_RULES
            for surface in rule.enforcement_surface
        )

        self.assertIn("serializer", surfaces.lower())
        self.assertTrue(
            any("household_name" in rule.rejected_by_default for rule in PRIVACY_MINIMIZATION_RULES)
        )
        self.assertTrue(
            any("extra_unknown_payload_keys" in rule.rejected_by_default for rule in PRIVACY_MINIMIZATION_RULES)
        )


class PrivacyMinimizationSerializerTests(SimpleTestCase):
    def assert_serializer_invalid(self, serializer, expected_field: str):
        self.assertFalse(serializer.is_valid(), serializer.validated_data)
        self.assertIn(expected_field, serializer.errors)

    def test_chv_message_rejects_direct_contact_details_in_free_text(self):
        serializer = CHVMessageCreateSerializer(
            data={
                "message_body": "Follow up with patient name Achieng on +254700111222.",
                "channel": CHVMessage.CHANNEL_SMS,
            }
        )

        self.assert_serializer_invalid(serializer, "message_body")

    def test_chv_message_accepts_operational_message_without_identifiers(self):
        serializer = CHVMessageCreateSerializer(
            data={
                "message_body": "Please confirm ORS stocks and attend the ward briefing.",
                "channel": CHVMessage.CHANNEL_SMS,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_coverage_request_rejects_unknown_household_identifier_field(self):
        serializer = CHVCoverageRequestCreateSerializer(
            data={
                "ward_id": 12,
                "priority": CHVCoverageRequest.PRIORITY_HIGH,
                "reason": "Coverage gap detected.",
                "requested_chv_count": 1,
                "household_name": "Otieno family",
            }
        )

        self.assert_serializer_invalid(serializer, "household_name")

    def test_coverage_request_rejects_household_names_in_notes(self):
        serializer = CHVCoverageRequestCreateSerializer(
            data={
                "ward_id": 12,
                "priority": CHVCoverageRequest.PRIORITY_HIGH,
                "reason": "Coverage gap detected.",
                "requested_chv_count": 1,
                "notes": "Household name: Otieno family.",
            }
        )

        self.assert_serializer_invalid(serializer, "notes")

    def test_preparedness_action_create_rejects_direct_identifier_lineage_metadata(self):
        serializer = PreparednessActionCreateSerializer(
            data={
                "ward_id": 12,
                "action_type": PreparednessAction.ACTION_FIELD_VERIFICATION,
                "source_trigger_type": PreparednessAction.SOURCE_SYSTEM,
                "source_trigger_ref": "system:privacy-test",
                "lineage_metadata": {
                    "child_name": "Achieng",
                    "source_kind": "operator_note",
                },
            }
        )

        self.assert_serializer_invalid(serializer, "lineage_metadata")

    def test_preparedness_action_transition_rejects_direct_identifier_evidence(self):
        serializer = PreparednessActionTransitionSerializer(
            data={
                "status": PreparednessAction.STATUS_COMPLETED,
                "detail": "Field verification completed.",
                "completion_evidence": {
                    "summary": "CHV report received.",
                    "patient_name": "Achieng",
                },
            }
        )

        self.assert_serializer_invalid(serializer, "completion_evidence")

    def test_preparedness_action_transition_accepts_safe_evidence_summary(self):
        serializer = PreparednessActionTransitionSerializer(
            data={
                "status": PreparednessAction.STATUS_COMPLETED,
                "detail": "Field verification completed.",
                "completion_evidence": {
                    "summary": "CHV report received and ward follow-up completed.",
                    "reference": "call-log-77",
                    "captured_via": "frontend_action_queue",
                },
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_triage_text_rejects_child_identifier_but_allows_explicit_phone_field(self):
        serializer = CHVTriageRequestSerializer(
            data={
                "ward_id": 12,
                "phone_number": "+254700111222",
                "text_input": "Child name: Achieng has diarrhea.",
                "diarrhea": True,
            }
        )

        self.assert_serializer_invalid(serializer, "text_input")

    def test_sync_payload_rejects_extra_household_payload_keys(self):
        serializer = CHVSyncRequestSerializer(
            data={
                "ward_id": 12,
                "phone_number": "+254700111222",
                "source_device_id": "device-1",
                "payloads": [
                    {
                        "client_submission_id": "submission-1",
                        "diarrhea": True,
                        "household_name": "Otieno family",
                    }
                ],
            }
        )

        self.assert_serializer_invalid(serializer, "payloads")
