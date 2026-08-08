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
    DashboardNotification,
    FacilityContact,
    FacilityReadinessReview,
    FacilityReadinessReviewEvent,
    FacilityReadinessUpdateRequest,
    HealthFacility,
    RiskScore,
    SourceDataUploadArtifact,
    SourceDataUploadBatch,
    SourceDataUploadEvent,
    SourceDataValidationIssue,
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
            provider_message_id="provider-message-privacy-access",
            error_message="Provider retry path mentions +254700111098.",
            governance_metadata={
                "schema_version": "message-audience-governance-phase-2-v1",
                "workflow": "risk_alert_sms",
                "audience_decision": {
                    "allowed": True,
                    "contact_reference": f"chv:{self.chv.public_id}",
                    "phone_number_present": True,
                    "preference_public_id": "f7d2c92e-8d02-4516-ae4b-57672db3b09b",
                    "audit_event_public_id": "3193a6f7-5927-4723-a7d8-cf0decd985ab",
                    "source_reference": "privacy-access-consent-source",
                },
                "audience_scope": {
                    "scope_kind": "assigned_ward",
                    "scope_allowed": True,
                    "actor_id": self.supervisor_user.id,
                    "actor_role": User.ROLE_SUPERVISOR,
                    "actor_ward_id": self.ward.id,
                    "target_ward_id": self.ward.id,
                },
            },
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
        self.assertEqual(list_alert["provider_message_id"], "")
        self.assertNotIn("+254700111098", list_alert["error_message"])
        self.assertNotIn(str(self.chv.public_id), str(list_alert["governance_metadata"]))
        self.assertNotIn("privacy-access-consent-source", str(list_alert["governance_metadata"]))
        self.assertEqual(list_alert["governance_metadata"]["audience_decision"]["contact_reference"], "")
        self.assertEqual(list_alert["governance_metadata"]["audience_decision"]["preference_public_id"], "")
        self.assertEqual(list_alert["governance_metadata"]["audience_scope"]["actor_id"], "")
        self.assertTrue(list_alert["privacy_context"]["redacted"])
        self.assertEqual(detail_response.data["recipient"], "+254******1001")
        self.assertNotIn("+254700111099", detail_response.data["message"])
        self.assertEqual(detail_response.data["external_id"], "")
        self.assertEqual(detail_response.data["provider_message_id"], "")
        self.assertNotIn(str(self.chv.public_id), str(detail_response.data["governance_metadata"]))
        self.assertEqual(detail_response.data["privacy_context"]["classification"], "sensitive_contact_data")

    def test_admin_alert_views_keep_direct_recipient_with_privacy_label(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(reverse("alert-detail", args=[self.alert.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["recipient"], "+254700111001")
        self.assertIn("+254700111099", response.data["message"])
        self.assertEqual(response.data["external_id"], "provider-alert-privacy-access")
        self.assertEqual(response.data["provider_message_id"], "provider-message-privacy-access")
        self.assertIn("+254700111098", response.data["error_message"])
        self.assertEqual(
            response.data["governance_metadata"]["audience_decision"]["contact_reference"],
            f"chv:{self.chv.public_id}",
        )
        self.assertEqual(response.data["governance_metadata"]["audience_scope"]["actor_id"], self.supervisor_user.id)
        self.assertFalse(response.data["privacy_context"]["redacted"])

    def test_analyst_notifications_do_not_expose_alert_delivery_recipients(self):
        self.alert.status = Alert.STATUS_FAILED
        self.alert.save(update_fields=["status"])
        self.client.force_authenticate(self.analyst_user)

        response = self.client.get(reverse("notification-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = next(
            item for item in response.data["results"]
            if item["type"] == DashboardNotification.TYPE_ALERT_FAILED
        )
        self.assertNotIn("+254700111001", notification["body"])
        self.assertNotIn("+254700111001", str(notification["metadata"]))
        self.assertNotIn("recipient", notification["metadata"])
        self.assertTrue(notification["privacy_context"]["redacted"])

        stored_notification = DashboardNotification.objects.get(
            type=DashboardNotification.TYPE_ALERT_FAILED,
            source_object_id=str(self.alert.id),
        )
        self.assertNotIn("+254700111001", stored_notification.body)
        self.assertNotIn("+254700111001", str(stored_notification.metadata))

    def test_legacy_notification_metadata_is_redacted_for_analyst_but_visible_to_admin(self):
        notification = DashboardNotification.objects.create(
            type=DashboardNotification.TYPE_ALERT_FAILED,
            severity=DashboardNotification.SEVERITY_CRITICAL,
            title="Legacy alert failure",
            body="SMS alert delivery failed for +254700111001. Provider mentioned +254700111099.",
            source_system="alerts",
            source_object_type="alert",
            source_object_id=str(self.alert.id),
            href=f"/alerts/{self.alert.id}",
            recipient_scope=DashboardNotification.SCOPE_WARD,
            ward=self.ward,
            metadata={
                "recipient": "+254700111001",
                "failure": "Provider path for +254700111099 failed.",
            },
        )

        self.client.force_authenticate(self.analyst_user)
        analyst_response = self.client.get(reverse("notification-detail", args=[notification.public_id]))
        self.client.force_authenticate(self.admin_user)
        admin_response = self.client.get(reverse("notification-detail", args=[notification.public_id]))

        self.assertEqual(analyst_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertNotIn("+254700111001", analyst_response.data["body"])
        self.assertNotIn("+254700111099", analyst_response.data["body"])
        self.assertEqual(analyst_response.data["metadata"]["recipient"], "+254******1001")
        self.assertNotIn("+254700111099", analyst_response.data["metadata"]["failure"])
        self.assertTrue(analyst_response.data["privacy_context"]["redacted"])
        self.assertIn("+254700111001", admin_response.data["body"])
        self.assertEqual(admin_response.data["metadata"]["recipient"], "+254700111001")
        self.assertFalse(admin_response.data["privacy_context"]["redacted"])

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

    def test_analyst_cannot_access_chv_coverage_request_detail_and_serializer_masks_by_default(self):
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
        assignment = CHVAssignment.objects.create(
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

        self.assertEqual(analyst_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_response.data["assignments"][0]["chv_phone_number"], "+254700111001")
        self.assertEqual(CHVAssignmentSerializer(assignment).data["chv_phone_number"], "+254******1001")

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

    def test_facility_intelligence_hides_contact_level_data_from_analyst(self):
        facility = HealthFacility.objects.create(
            name="Privacy Access Contact Dispensary",
            facility_code="PRIV-CONTACT-FAC",
            ward=self.ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
        )
        FacilityContact.objects.create(
            facility=facility,
            name="Facility In-Charge",
            role="Nurse in charge",
            phone="+254720111777",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="privacy-access-facility-contact",
            verified_at=timezone.now(),
        )

        self.client.force_authenticate(self.analyst_user)
        analyst_response = self.client.get(reverse("facility-intelligence", args=[facility.id]))
        self.client.force_authenticate(self.admin_user)
        admin_response = self.client.get(reverse("facility-intelligence", args=[facility.id]))

        self.assertEqual(analyst_response.status_code, status.HTTP_200_OK)
        self.assertIsNone(analyst_response.data["contact"])
        self.assertTrue(analyst_response.data["capabilities"]["has_verified_contact"])
        self.assertFalse(analyst_response.data["capabilities"]["can_view_contacts"])
        self.assertFalse(analyst_response.data["capabilities"]["can_request_facility_update"])
        self.assertNotIn("+254720111777", str(analyst_response.data))
        self.assertNotIn("Facility In-Charge", str(analyst_response.data))

        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_response.data["contact"]["display_label"], "Facility In-Charge")
        self.assertEqual(admin_response.data["contact"]["phone_last4"], "1777")
        self.assertTrue(admin_response.data["capabilities"]["can_view_contacts"])

    def test_facility_readiness_review_hides_contact_workflow_identifiers_from_analyst(self):
        facility = HealthFacility.objects.create(
            name="Privacy Access Readiness Dispensary",
            facility_code="PRIV-READINESS-FAC",
            ward=self.ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
        )
        contact = FacilityContact.objects.create(
            facility=facility,
            name="Facility In-Charge",
            role="Nurse in charge",
            phone="+254720111888",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="privacy-access-readiness-contact",
            verified_at=timezone.now(),
        )
        review = FacilityReadinessReview.objects.create(
            facility=facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_MEDIUM,
            reason_codes=["STALE_INPUTS"],
            created_by=self.admin_user,
        )
        update_request = FacilityReadinessUpdateRequest.objects.create(
            review=review,
            facility=facility,
            contact=contact,
            requested_by=self.admin_user,
            channel=FacilityReadinessUpdateRequest.CHANNEL_SMS,
            message_body="Please ask Facility In-Charge to call +254720111888 with readiness.",
            governance_metadata={
                "workflow": "facility_readiness_update_request",
                "contact_public_id": str(contact.public_id),
                "recipient_phone": contact.phone,
                "operator_note": "Facility In-Charge handles ORS stock.",
            },
            status=FacilityReadinessUpdateRequest.STATUS_QUEUED,
        )
        FacilityReadinessReviewEvent.objects.create(
            review=review,
            action=FacilityReadinessReviewEvent.ACTION_UPDATE_REQUEST_CREATED,
            old_status=review.status,
            new_status=review.status,
            detail="Facility update request queued for +254720111888.",
            actor=self.admin_user,
            metadata={
                "workflow": "facility_readiness_update_request",
                "update_request_public_id": str(update_request.public_id),
                "contact_public_id": str(contact.public_id),
                "recipient_phone": contact.phone,
                "operator_note": "Facility In-Charge handles ORS stock.",
            },
        )

        self.client.force_authenticate(self.analyst_user)
        analyst_response = self.client.get(reverse("facility-readiness-review-detail", args=[review.public_id]))
        self.client.force_authenticate(self.admin_user)
        admin_response = self.client.get(reverse("facility-readiness-review-detail", args=[review.public_id]))

        self.assertEqual(analyst_response.status_code, status.HTTP_200_OK)
        analyst_payload_text = str(analyst_response.data)
        analyst_update_request = analyst_response.data["update_requests"][0]
        self.assertIsNone(analyst_update_request["contact"])
        self.assertEqual(analyst_update_request["contact_display_label"], "Facility contact")
        self.assertEqual(analyst_update_request["governance_metadata"], {"workflow": "facility_readiness_update_request"})
        self.assertNotIn(str(contact.public_id), analyst_payload_text)
        self.assertNotIn(contact.phone, analyst_payload_text)
        self.assertNotIn("Facility In-Charge", analyst_payload_text)
        self.assertNotIn("operator_note", analyst_payload_text)
        self.assertNotIn("contact_public_id", analyst_payload_text)
        self.assertIn("[redacted phone]", analyst_response.data["events"][0]["detail"])

        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        admin_update_request = admin_response.data["update_requests"][0]
        self.assertEqual(admin_update_request["contact"], contact.id)
        self.assertEqual(admin_update_request["contact_display_label"], "Facility In-Charge")
        self.assertEqual(admin_update_request["governance_metadata"]["contact_public_id"], str(contact.public_id))

    def test_source_data_upload_reads_redact_legacy_direct_identifiers_for_analyst(self):
        batch = SourceDataUploadBatch.objects.create(
            feed_key="surveillance_weekly_aggregate",
            domain="health_surveillance",
            source_type="weekly_aggregate",
            source_name="DHIS2 extract for +254700111010",
            source_ref="source-row:+254700111011",
            status=SourceDataUploadBatch.STATUS_UPLOADED,
            validation_status=SourceDataUploadBatch.VALIDATION_FAILED,
            import_status=SourceDataUploadBatch.IMPORT_NOT_STARTED,
            row_count=1,
            rejected_count=1,
            operator_note="Caller +254700111012 asked for correction.",
            metadata={
                "validation_summary": {
                    "contact_phone": "+254700111013",
                    "note": "Follow up with +254700111014.",
                },
                "legacy_contact": "+254700111015",
            },
            created_by=self.admin_user,
        )
        SourceDataUploadArtifact.objects.create(
            upload_batch=batch,
            original_filename="household-+254700111016.csv",
            content_type="text/csv",
            size_bytes=24,
            sha256="a" * 64,
            storage_path="source-data/household-+254700111016.csv",
        )
        SourceDataUploadEvent.objects.create(
            upload_batch=batch,
            actor=self.admin_user,
            event_type=SourceDataUploadEvent.EVENT_UPLOAD_CREATED,
            metadata={
                "recipient": "+254700111017",
                "detail": "Upload mentioned +254700111018.",
            },
        )
        SourceDataValidationIssue.objects.create(
            upload_batch=batch,
            row_number=2,
            severity=SourceDataValidationIssue.SEVERITY_ERROR,
            code="legacy_direct_identifier",
            column_name="notes",
            message="Legacy diagnostic mentioned +254700111019.",
            safe_context={
                "phone_number": "+254700111020",
                "patient_name": "Jane Example",
                "national_id": "12345678",
                "contact_public_id": str(self.chv.public_id),
                "filename": "legacy-+254700111021.csv",
            },
        )

        self.client.force_authenticate(self.analyst_user)
        analyst_list_response = self.client.get(reverse("source-data-upload-list-create"))
        analyst_actor_filter_response = self.client.get(
            reverse("source-data-upload-list-create"),
            {"actor": self.admin_user.username},
        )
        analyst_source_name_filter_response = self.client.get(
            reverse("source-data-upload-list-create"),
            {"source_name": "+254700111010"},
        )
        analyst_detail_response = self.client.get(reverse("source-data-upload-detail", args=[batch.public_id]))
        analyst_errors_response = self.client.get(reverse("source-data-upload-errors-file", args=[batch.public_id]))
        self.client.force_authenticate(self.admin_user)
        admin_actor_filter_response = self.client.get(
            reverse("source-data-upload-list-create"),
            {"actor": self.admin_user.username},
        )
        admin_source_name_filter_response = self.client.get(
            reverse("source-data-upload-list-create"),
            {"source_name": "+254700111010"},
        )
        admin_detail_response = self.client.get(reverse("source-data-upload-detail", args=[batch.public_id]))
        admin_errors_response = self.client.get(reverse("source-data-upload-errors-file", args=[batch.public_id]))

        self.assertEqual(analyst_list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(analyst_actor_filter_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(analyst_source_name_filter_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(analyst_detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(analyst_errors_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_actor_filter_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_source_name_filter_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_errors_response.status_code, status.HTTP_200_OK)

        analyst_payload = analyst_detail_response.data
        self.assertNotIn("+254700111010", str(analyst_payload))
        self.assertNotIn("+254700111011", str(analyst_payload))
        self.assertNotIn("+254700111012", str(analyst_payload))
        self.assertNotIn("+254700111013", str(analyst_payload))
        self.assertNotIn("+254700111014", str(analyst_payload))
        self.assertNotIn("+254700111015", str(analyst_payload))
        self.assertNotIn("+254700111016", str(analyst_payload))
        self.assertNotIn("+254700111017", str(analyst_payload))
        self.assertNotIn("+254700111018", str(analyst_payload))
        self.assertNotIn("+254700111019", str(analyst_payload))
        self.assertNotIn("+254700111020", str(analyst_payload))
        self.assertNotIn("+254700111021", str(analyst_payload))
        self.assertNotIn("Jane Example", str(analyst_payload))
        self.assertNotIn("12345678", str(analyst_payload))
        self.assertNotIn(self.admin_user.username, str(analyst_payload))
        self.assertNotIn(str(self.chv.public_id), str(analyst_payload))
        self.assertEqual(analyst_payload["artifacts"][0]["original_filename"], "redacted-source-data-file")
        self.assertEqual(analyst_payload["metadata"]["validation_summary"]["contact_phone"], "+254******1013")
        self.assertIn("[redacted phone]", analyst_payload["events"][0]["metadata"]["detail"])
        self.assertIn("[redacted phone]", analyst_payload["validation_issues"][0]["message"])
        self.assertEqual(analyst_payload["validation_issues"][0]["safe_context"]["phone_number"], "+254******1020")
        self.assertEqual(analyst_payload["validation_issues"][0]["safe_context"]["patient_name"], "")
        self.assertEqual(analyst_payload["validation_issues"][0]["safe_context"]["national_id"], "")
        self.assertEqual(analyst_payload["validation_issues"][0]["safe_context"]["contact_public_id"], "")
        self.assertNotIn("+254700111010", str(analyst_list_response.data))
        self.assertNotIn(self.admin_user.username, str(analyst_list_response.data))
        self.assertNotIn("+254700111019", analyst_errors_response.data["payload"])
        self.assertNotIn("+254700111020", analyst_errors_response.data["payload"])
        self.assertNotIn("+254700111021", analyst_errors_response.data["payload"])
        self.assertNotIn("Jane Example", analyst_errors_response.data["payload"])
        self.assertNotIn("12345678", analyst_errors_response.data["payload"])
        self.assertNotIn(str(self.chv.public_id), analyst_errors_response.data["payload"])
        self.assertIn("[redacted phone]", analyst_errors_response.data["payload"])
        self.assertIn("+254******1020", analyst_errors_response.data["payload"])

        admin_payload = admin_detail_response.data
        self.assertIn("+254700111010", admin_payload["source_name"])
        self.assertIn(self.admin_user.username, str(admin_payload))
        self.assertIn(self.admin_user.username, str(admin_actor_filter_response.data))
        self.assertIn("+254700111010", str(admin_source_name_filter_response.data))
        self.assertEqual(admin_payload["artifacts"][0]["original_filename"], "household-+254700111016.csv")
        admin_upload_event = next(
            event
            for event in admin_payload["events"]
            if event["event_type"] == SourceDataUploadEvent.EVENT_UPLOAD_CREATED
        )
        self.assertEqual(admin_upload_event["metadata"]["recipient"], "+254700111017")
        self.assertIn("+254700111019", admin_errors_response.data["payload"])
        self.assertIn("+254700111020", admin_errors_response.data["payload"])
        self.assertIn("+254700111021", admin_errors_response.data["payload"])
        self.assertIn("Jane Example", admin_errors_response.data["payload"])
        self.assertIn("12345678", admin_errors_response.data["payload"])
        self.assertIn(str(self.chv.public_id), admin_errors_response.data["payload"])

    def test_source_data_overview_recent_uploads_redact_identifiers_for_analyst(self):
        SourceDataUploadBatch.objects.create(
            feed_key="surveillance_weekly_aggregate",
            domain="health_surveillance",
            source_type="weekly_aggregate",
            source_name="DHIS2 extract for +254700111019",
            status=SourceDataUploadBatch.STATUS_IMPORTED,
            validation_status=SourceDataUploadBatch.VALIDATION_PASSED,
            import_status=SourceDataUploadBatch.IMPORT_IMPORTED,
            row_count=1,
            accepted_count=1,
            created_by=self.admin_user,
            confirmed_by=self.admin_user,
            confirmed_at=timezone.now(),
        )

        self.client.force_authenticate(self.analyst_user)
        analyst_response = self.client.get(reverse("source-data-overview"))
        self.client.force_authenticate(self.admin_user)
        admin_response = self.client.get(reverse("source-data-overview"))

        self.assertEqual(analyst_response.status_code, status.HTTP_200_OK)
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        analyst_upload = analyst_response.data["recent_uploads"][0]
        admin_upload = admin_response.data["recent_uploads"][0]
        self.assertNotIn("+254700111019", str(analyst_upload))
        self.assertIn("[redacted phone]", analyst_upload["source_name"])
        self.assertEqual(admin_upload["source_name"], "DHIS2 extract for +254700111019")

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
        self.assertEqual(alert_payload["provider_message_id"], "")
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
