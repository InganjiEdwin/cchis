from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import (
    Alert,
    CHV,
    CHVAssignment,
    CHVCoverageRequest,
    ContactPreference,
    HealthFacility,
    RiskScore,
    SyncQueue,
    TriageSession,
    UssdSessionLog,
    Ward,
)
from .serializers import AlertSerializer, CHVAssignmentSerializer, CHVTriageResponseSerializer


def get_results(response):
    if isinstance(response.data, dict) and "results" in response.data:
        return response.data["results"]
    return response.data


class PrivacyAccessSafeViewTests(APITestCase):
    password = "ChangeMe123!"

    def setUp(self):
        self.ward = Ward.objects.create(
            name="Privacy Access Ward",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.86,
            is_active=True,
        )
        self.other_ward = Ward.objects.create(
            name="Other Privacy Access Ward",
            county="Migori",
            sub_county="Nyatike",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.53,
            is_active=True,
        )
        self.admin_user = self._create_user("privacy_access_admin", User.ROLE_ADMIN)
        self.supervisor_user = self._create_user("privacy_access_supervisor", User.ROLE_SUPERVISOR, self.ward)
        self.analyst_user = self._create_user("privacy_access_analyst", User.ROLE_ANALYST)
        self.chv_user = self._create_user("privacy_access_chv_user", User.ROLE_CHV, self.ward)
        self.chv = CHV.objects.create(
            name="Privacy Access CHV",
            phone_number="+254700111001",
            ward=self.ward,
            is_active=True,
            language="en",
        )
        self.risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.86,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=122.0,
            flood_indicator=0.72,
            predicted_cases=15,
            source=RiskScore.SOURCE_MODEL,
            model_version="privacy-access-v1",
        )
        self.alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700111001",
            message="High cholera risk requires field follow-up. Call +254700111099 only if escalated.",
            status=Alert.STATUS_QUEUED,
            delivery_backend="stub",
            external_id="provider-alert-privacy-access",
            error_message="Provider retry path mentions +254700111098.",
        )

    def _create_user(self, username: str, role: str, ward: Ward | None = None) -> User:
        return User.objects.create_user(
            username=username,
            password=self.password,
            email=f"{username}@example.com",
            role=role,
            ward=ward,
            is_active=True,
        )

    def test_analyst_alert_views_mask_direct_recipient_and_mark_privacy_context(self):
        self.client.force_authenticate(self.analyst_user)

        list_response = self.client.get(reverse("alert-list"))
        detail_response = self.client.get(reverse("alert-detail", args=[self.alert.id]))

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        list_alert = get_results(list_response)[0]
        self.assertEqual(list_alert["recipient"], "+254******1001")
        self.assertNotIn("+254700111099", list_alert["message"])
        self.assertIn("[redacted phone]", list_alert["message"])
        self.assertEqual(list_alert["external_id"], "")
        self.assertNotIn("+254700111098", list_alert["error_message"])
        self.assertTrue(list_alert["privacy_context"]["redacted"])
        self.assertEqual(detail_response.data["recipient"], "+254******1001")
        self.assertNotIn("+254700111099", detail_response.data["message"])
        self.assertEqual(detail_response.data["external_id"], "")
        self.assertEqual(detail_response.data["privacy_context"]["classification"], "sensitive_contact_data")

    def test_admin_alert_views_keep_direct_recipient_with_privacy_label(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(reverse("alert-detail", args=[self.alert.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["recipient"], "+254700111001")
        self.assertIn("+254700111099", response.data["message"])
        self.assertEqual(response.data["external_id"], "provider-alert-privacy-access")
        self.assertIn("+254700111098", response.data["error_message"])
        self.assertFalse(response.data["privacy_context"]["redacted"])

    def test_chv_triage_response_is_assigned_scope_and_redacts_sensitive_echo(self):
        self.client.force_authenticate(self.chv_user)

        response = self.client.post(
            reverse("chv-triage"),
            {
                "ward_id": self.ward.id,
                "phone_number": "+254711111111",
                "channel": "API",
                "diarrhea": True,
                "vomiting": True,
                "text_input": "Child has loose stool and vomiting",
            },
            format="json",
        )
        other_ward_response = self.client.post(
            reverse("chv-triage"),
            {
                "ward_id": self.other_ward.id,
                "phone_number": "+254711111111",
                "channel": "API",
                "diarrhea": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(other_ward_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["phone_number"], "+254******1111")
        self.assertEqual(response.data["text_input"], "")
        self.assertEqual(response.data["privacy_context"]["classification"], "sensitive_field_health_data")
        self.assertTrue(response.data["privacy_context"]["redacted"])
        self.assertEqual(TriageSession.objects.get().phone_number, "+254711111111")

    def test_chv_sync_response_redacts_nested_triage_echo_but_stores_raw_submission(self):
        self.client.force_authenticate(self.chv_user)

        response = self.client.post(
            reverse("chv-sync"),
            {
                "ward_id": self.ward.id,
                "phone_number": "+254700000009",
                "source_device_id": "device-privacy-access",
                "payloads": [
                    {
                        "client_submission_id": "privacy-access-sync-001",
                        "diarrhea": True,
                        "vomiting": True,
                        "dehydration": False,
                        "fever": False,
                        "text_input": "Child has loose stool and vomiting",
                    }
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        nested = response.data["results"][0]["triage_session"]
        self.assertEqual(nested["phone_number"], "+254******0009")
        self.assertEqual(nested["text_input"], "")
        self.assertTrue(nested["privacy_context"]["redacted"])
        self.assertEqual(SyncQueue.objects.count(), 1)
        self.assertEqual(TriageSession.objects.get().text_input, "Child has loose stool and vomiting")

    def test_analyst_coverage_request_masks_assignment_phone_by_default(self):
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_APPROVED,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_MANUAL,
            reason="Coverage gap detected.",
            requested_chv_count=1,
            expected_response_by=timezone.now(),
        )
        CHVAssignment.objects.create(
            coverage_request=request_record,
            ward=self.ward,
            chv=self.chv,
            assigned_by=self.admin_user,
            status=CHVAssignment.STATUS_ACTIVE,
        )
        self.client.force_authenticate(self.analyst_user)

        analyst_response = self.client.get(reverse("chv-coverage-request-detail", args=[request_record.public_id]))
        self.client.force_authenticate(self.admin_user)
        admin_response = self.client.get(reverse("chv-coverage-request-detail", args=[request_record.public_id]))

        self.assertEqual(analyst_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertEqual(analyst_response.data["assignments"][0]["chv_phone_number"], "+254******1001")
        self.assertEqual(admin_response.data["assignments"][0]["chv_phone_number"], "+254700111001")

    def test_facility_intelligence_masks_linked_alert_recipients_for_analyst(self):
        facility = HealthFacility.objects.create(
            name="Privacy Access Dispensary",
            facility_code="PRIV-ACCESS-FAC",
            ward=self.ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
            contact_phone="+254720111001",
        )
        self.client.force_authenticate(self.analyst_user)

        facility_detail_response = self.client.get(reverse("facility-detail", args=[facility.id]))
        response = self.client.get(reverse("facility-intelligence", args=[facility.id]))
        self.client.force_authenticate(self.admin_user)
        admin_facility_response = self.client.get(reverse("facility-detail", args=[facility.id]))
        admin_intelligence_response = self.client.get(reverse("facility-intelligence", args=[facility.id]))

        self.assertEqual(facility_detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_facility_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_intelligence_response.status_code, status.HTTP_200_OK)
        self.assertEqual(facility_detail_response.data["contact_phone"], "+254******1001")
        self.assertEqual(response.data["facility"]["contact_phone"], "+254******1001")
        self.assertEqual(admin_facility_response.data["contact_phone"], "+254720111001")
        self.assertEqual(admin_intelligence_response.data["facility"]["contact_phone"], "+254720111001")
        self.assertEqual(response.data["linked_alerts"][0]["recipient"], "+254******1001")
        alert_timeline = next(item for item in response.data["timeline"] if item["category"] == "alert")
        self.assertIn("+254******1001", alert_timeline["meta"])
        self.assertNotIn("+254700111001", alert_timeline["meta"])

    def test_sensitive_serializers_redact_when_request_context_is_missing(self):
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_APPROVED,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_MANUAL,
            reason="Coverage gap detected.",
            requested_chv_count=1,
        )
        assignment = CHVAssignment.objects.create(
            coverage_request=request_record,
            ward=self.ward,
            chv=self.chv,
            assigned_by=self.admin_user,
            status=CHVAssignment.STATUS_ACTIVE,
        )
        triage = TriageSession.objects.create(
            channel="API",
            phone_number="+254700111002",
            ward=self.ward,
            text_input="Child has loose stool and vomiting",
            diarrhea=True,
        )

        alert_payload = AlertSerializer(self.alert).data
        assignment_payload = CHVAssignmentSerializer(assignment).data
        triage_payload = CHVTriageResponseSerializer(triage).data

        self.assertEqual(alert_payload["recipient"], "+254******1001")
        self.assertNotIn("+254700111099", alert_payload["message"])
        self.assertEqual(alert_payload["external_id"], "")
        self.assertTrue(alert_payload["privacy_context"]["redacted"])
        self.assertEqual(assignment_payload["chv_phone_number"], "+254******1001")
        self.assertEqual(triage_payload["phone_number"], "+254******1002")
        self.assertEqual(triage_payload["text_input"], "")
        self.assertTrue(triage_payload["privacy_context"]["redacted"])

    def test_supervisor_cannot_enumerate_global_contact_preferences(self):
        ContactPreference.objects.create(
            audience_type=ContactPreference.AUDIENCE_HOUSEHOLD,
            channel=ContactPreference.CHANNEL_SMS,
            phone_number="+254700111003",
            consent_status=ContactPreference.CONSENT_GRANTED,
            opt_out_status=ContactPreference.OPT_OUT_NOT_OPTED_OUT,
            source="household_sms_consent",
            source_reference="privacy-access-consent",
            recorded_by=self.admin_user,
        )

        self.client.force_authenticate(self.supervisor_user)
        supervisor_response = self.client.get(reverse("contact-preference-list-create"))
        self.client.force_authenticate(self.admin_user)
        admin_response = self.client.get(reverse("contact-preference-list-create"))

        self.assertEqual(supervisor_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertEqual(get_results(admin_response)[0]["phone_number"], "+254700111003")

    def test_supervisor_ussd_log_view_is_ward_scoped_but_masks_direct_identifiers(self):
        UssdSessionLog.objects.create(
            session_id="privacy-access-ussd-1",
            phone_number="+254700111004",
            service_code="*123#",
            text="2*+254700111005",
            response_text="END Follow-up sent to +254700111006.",
            ward=self.ward,
            menu_level="diarrhea_menu",
        )

        self.client.force_authenticate(self.supervisor_user)
        supervisor_response = self.client.get(reverse("ussd-log-list"))
        supervisor_phone_filter_response = self.client.get(
            reverse("ussd-log-list"),
            {"phone_number": "+254700111004"},
        )
        self.client.force_authenticate(self.admin_user)
        admin_response = self.client.get(reverse("ussd-log-list"))
        admin_phone_filter_response = self.client.get(
            reverse("ussd-log-list"),
            {"phone_number": "+254700111004"},
        )

        self.assertEqual(supervisor_response.status_code, status.HTTP_200_OK)
        self.assertEqual(supervisor_phone_filter_response.status_code, status.HTTP_403_FORBIDDEN)
        supervisor_log = get_results(supervisor_response)[0]
        self.assertEqual(supervisor_log["phone_number"], "+254******1004")
        self.assertNotIn("+254700111005", supervisor_log["text"])
        self.assertNotIn("+254700111006", supervisor_log["response_text"])
        self.assertIn("[redacted phone]", supervisor_log["text"])

        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_phone_filter_response.status_code, status.HTTP_200_OK)
        admin_log = get_results(admin_response)[0]
        self.assertEqual(admin_log["phone_number"], "+254700111004")
        self.assertEqual(get_results(admin_phone_filter_response)[0]["phone_number"], "+254700111004")
        self.assertIn("+254700111005", admin_log["text"])
        self.assertIn("+254700111006", admin_log["response_text"])
