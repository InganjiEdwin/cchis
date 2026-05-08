from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import StepUpGrant, User
from accounts.permissions import IsAdminOrSupervisor

from .models import (
    Alert,
    CHV,
    CHVCoverageRequest,
    FacilityReadinessReview,
    HealthFacility,
    MessageTemplate,
    PreparednessAction,
    RiskScore,
    SourceDataUploadBatch,
    SourceDataValidationIssue,
    Ward,
)
from .test_step_up_utils import force_authenticate_with_step_up
from .views import (
    AlertPreparednessActionCreateAPIView,
    AlertWorkflowPreparednessActionCreateAPIView,
    CHVCoverageRequestPreparednessActionCreateAPIView,
    FacilityReadinessEscalationPreparednessActionCreateAPIView,
    FacilityReadinessReviewPreparednessActionCreateAPIView,
)


class BackendRoleAuthorizationMatrixTests(APITestCase):
    password = "ChangeMe123!"

    def setUp(self):
        self.upload_root = TemporaryDirectory()
        self.addCleanup(self.upload_root.cleanup)
        self.settings_override = override_settings(
            SOURCE_DATA_UPLOAD_ROOT=Path(self.upload_root.name),
            SOURCE_DATA_MAX_UPLOAD_SIZE_BYTES=1024 * 1024,
            SOURCE_DATA_MAX_UPLOAD_ROWS=20,
            SOURCE_DATA_ASYNC_IMPORT_SIZE_BYTES=1024 * 1024,
            SOURCE_DATA_LARGE_DELTA_APPROVAL_ROW_THRESHOLD=1,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.ward = Ward.objects.create(
            name="Matrix Supervisor Ward",
            county="Migori",
            sub_county="Rongo",
            ward_code="MIG-WARD-001",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.91,
            is_active=True,
        )
        self.other_ward = Ward.objects.create(
            name="Matrix Other Ward",
            county="Migori",
            sub_county="Nyatike",
            ward_code="MIG-WARD-002",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.52,
            is_active=True,
        )
        self.admin = self.create_user("matrix_admin", User.ROLE_ADMIN, self.ward)
        self.supervisor = self.create_user("matrix_supervisor", User.ROLE_SUPERVISOR, self.ward)
        self.other_supervisor = self.create_user("matrix_other_supervisor", User.ROLE_SUPERVISOR, self.other_ward)
        self.analyst = self.create_user("matrix_analyst", User.ROLE_ANALYST, self.other_ward)
        self.chv_user = self.create_user("matrix_chv_user", User.ROLE_CHV, self.ward)

        self.risk_score = RiskScore.objects.create(
            ward=self.ward,
            score=0.91,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=142,
            flood_indicator=0.7,
            predicted_cases=18,
            decision_policy={"policy_version": "matrix-policy-v1", "decision": "urgent_alert"},
        )
        self.other_risk_score = RiskScore.objects.create(
            ward=self.other_ward,
            score=0.52,
            risk_level=Ward.RISK_MEDIUM,
            rainfall_mm=72,
            flood_indicator=0.2,
            predicted_cases=6,
            decision_policy={"policy_version": "matrix-policy-v1", "decision": "monitor"},
        )
        self.alert = self.create_alert(self.ward, self.risk_score, "+254700111222")
        self.other_alert = self.create_alert(self.other_ward, self.other_risk_score, "+254700333444")
        self.facility = self.create_facility("Matrix Supervisor Dispensary", "MATRIX-FAC-001", self.ward)
        self.other_facility = self.create_facility("Matrix Other Dispensary", "MATRIX-FAC-002", self.other_ward)
        self.chv = CHV.objects.create(
            name="Matrix CHV",
            phone_number="+254700555001",
            ward=self.ward,
            is_active=True,
        )
        self.other_chv = CHV.objects.create(
            name="Matrix Other CHV",
            phone_number="+254700555002",
            ward=self.other_ward,
            is_active=True,
        )
        self.review = FacilityReadinessReview.objects.create(
            facility=self.facility,
            ward=self.ward,
            severity=FacilityReadinessReview.SEVERITY_MEDIUM,
            reason_codes=["ors_stock_watch"],
            created_by=self.admin,
            notes="Review own ward readiness.",
        )
        self.other_review = FacilityReadinessReview.objects.create(
            facility=self.other_facility,
            ward=self.other_ward,
            severity=FacilityReadinessReview.SEVERITY_HIGH,
            reason_codes=["staffing_gap"],
            created_by=self.admin,
            notes="Review other ward readiness.",
        )
        self.preparedness_action = PreparednessAction.objects.create(
            ward=self.ward,
            action_type=PreparednessAction.ACTION_FIELD_VERIFICATION,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            priority=PreparednessAction.PRIORITY_HIGH,
            created_by=self.admin,
            notes="Own ward action.",
        )
        self.other_preparedness_action = PreparednessAction.objects.create(
            ward=self.other_ward,
            action_type=PreparednessAction.ACTION_SURVEILLANCE_FOLLOW_UP,
            source_trigger_type=PreparednessAction.SOURCE_MANUAL,
            priority=PreparednessAction.PRIORITY_MEDIUM,
            created_by=self.admin,
            notes="Other ward action.",
        )
        self.coverage_request = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.supervisor,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Need field coverage for own ward.",
            requested_chv_count=1,
        )
        self.other_coverage_request = CHVCoverageRequest.objects.create(
            ward=self.other_ward,
            requested_by=self.other_supervisor,
            priority=CHVCoverageRequest.PRIORITY_MEDIUM,
            reason="Need field coverage for other ward.",
            requested_chv_count=1,
        )
        self.source_batch = self.create_source_batch(
            created_by=self.supervisor,
            status_value=SourceDataUploadBatch.STATUS_READY_FOR_CONFIRMATION,
            approval_status=SourceDataUploadBatch.APPROVAL_PENDING,
            approval_requested_by=self.supervisor,
        )
        SourceDataValidationIssue.objects.create(
            upload_batch=self.source_batch,
            row_number=2,
            severity=SourceDataValidationIssue.SEVERITY_ERROR,
            code="matrix_validation_error",
            column_name="ward_code",
            message="Ward code needs review.",
            safe_context={"ward_code": "MIG-WARD-001"},
        )
        self.message_template = MessageTemplate.objects.create(
            template_key="matrix.chv.workflow_check_in_sms",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            language="en",
            version=1,
            title="Matrix CHV workflow",
            body="Please confirm readiness for {ward_name}.",
            placeholders=["ward_name"],
            approval_status=MessageTemplate.APPROVAL_PENDING_REVIEW,
            owner="county_public_health_operations",
            risk_level=MessageTemplate.RISK_HIGH,
            created_by=self.admin,
        )

    def create_user(self, username: str, role: str, ward: Ward | None = None) -> User:
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password=self.password,
            role=role,
            ward=ward,
            is_active=True,
        )

    def create_alert(self, ward: Ward, risk_score: RiskScore, recipient: str) -> Alert:
        return Alert.objects.create(
            ward=ward,
            risk_score=risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient=recipient,
            message=f"High cholera risk follow-up for {recipient}.",
            status=Alert.STATUS_DELIVERED,
            delivery_backend="matrix-provider",
            external_id=f"provider-{ward.id}",
            sent_at=timezone.now(),
        )

    def create_facility(self, name: str, code: str, ward: Ward) -> HealthFacility:
        return HealthFacility.objects.create(
            name=name,
            facility_code=code,
            ward=ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
            contact_phone="+254711000111",
        )

    def create_source_batch(
        self,
        *,
        created_by: User,
        status_value: str = SourceDataUploadBatch.STATUS_UPLOADED,
        approval_status: str = SourceDataUploadBatch.APPROVAL_NOT_REQUIRED,
        approval_requested_by: User | None = None,
    ) -> SourceDataUploadBatch:
        return SourceDataUploadBatch.objects.create(
            feed_key="surveillance_weekly_aggregate",
            domain="health_surveillance",
            source_type="weekly_aggregate",
            source_name="Matrix DHIS2 weekly aggregate",
            source_ref="matrix-dhis2-row-1",
            source_timestamp=timezone.now(),
            reporting_period_start="2026-04-27",
            reporting_period_end="2026-05-03",
            status=status_value,
            validation_status=SourceDataUploadBatch.VALIDATION_PASSED,
            import_status=SourceDataUploadBatch.IMPORT_NOT_STARTED,
            row_count=2,
            accepted_count=2,
            rejected_count=0,
            approval_status=approval_status,
            approval_risk_category="large_delta_or_volume" if approval_status == SourceDataUploadBatch.APPROVAL_PENDING else "",
            approval_requested_by=approval_requested_by,
            approval_requested_at=timezone.now() if approval_requested_by else None,
            approval_expires_at=timezone.now() + timedelta(hours=2) if approval_requested_by else None,
            approval_reason="Matrix maker-checker request." if approval_requested_by else "",
            created_by=created_by,
        )

    def authenticate(self, user: User, *purposes: str) -> None:
        if purposes:
            force_authenticate_with_step_up(self.client, user, *purposes)
        else:
            self.client.force_authenticate(user=user)

    def results(self, response):
        return response.data.get("results", response.data)

    def ids_from_results(self, response, key: str = "id") -> set:
        return {item[key] for item in self.results(response)}

    def assert_step_up_required(self, response, purpose: str) -> None:
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(str(response.data["code"]), "step_up_required")
        self.assertEqual(response.data["purpose"], purpose)

    def preparedness_payload(self, ward_id: int | None = None) -> dict:
        return {
            "ward_id": ward_id or self.ward.id,
            "action_type": PreparednessAction.ACTION_FIELD_VERIFICATION,
            "source_trigger_type": PreparednessAction.SOURCE_MANUAL,
            "priority": PreparednessAction.PRIORITY_HIGH,
            "notes": "Matrix action write.",
        }

    def upload_payload(self, filename: str = "matrix-weekly.csv") -> dict:
        csv_text = "\n".join(
            [
                "ward_code,reporting_period_start,reporting_period_end,suspected_cases,confirmed_cases,diarrheal_count,reporting_granularity,notes,source_ref",
                "MIG-WARD-001,2026-04-27,2026-05-03,3,1,8,week,Matrix upload,dhis2-weekly-export:row-1",
            ]
        )
        return {
            "feed_key": "surveillance_weekly_aggregate",
            "source_name": "Matrix DHIS2 weekly export",
            "source_timestamp": "2026-05-05T08:00:00Z",
            "reporting_period_start": "2026-04-27",
            "reporting_period_end": "2026-05-03",
            "file": SimpleUploadedFile(filename, csv_text.encode("utf-8"), content_type="text/csv"),
        }

    def test_dashboard_read_scope_matrix_for_wards_alerts_preparedness_and_facility_reviews(self):
        read_cases = [
            (self.admin, {self.ward.id, self.other_ward.id}, status.HTTP_200_OK),
            (self.supervisor, {self.ward.id}, status.HTTP_200_OK),
            (self.analyst, {self.ward.id, self.other_ward.id}, status.HTTP_200_OK),
            (self.chv_user, set(), status.HTTP_403_FORBIDDEN),
        ]

        for user, expected_ward_ids, expected_status in read_cases:
            with self.subTest(endpoint="wards", role=user.role):
                self.authenticate(user)
                response = self.client.get(reverse("ward-list"))
                self.assertEqual(response.status_code, expected_status)
                if response.status_code == status.HTTP_200_OK:
                    self.assertEqual(self.ids_from_results(response), expected_ward_ids)

            with self.subTest(endpoint="alerts", role=user.role):
                self.authenticate(user)
                response = self.client.get(reverse("alert-list"))
                self.assertEqual(response.status_code, expected_status)
                if response.status_code == status.HTTP_200_OK:
                    self.assertEqual(self.ids_from_results(response, "ward"), expected_ward_ids)

            with self.subTest(endpoint="preparedness", role=user.role):
                self.authenticate(user)
                response = self.client.get(reverse("preparedness-action-list-create"))
                self.assertEqual(response.status_code, expected_status)
                if response.status_code == status.HTTP_200_OK:
                    self.assertEqual(self.ids_from_results(response, "ward"), expected_ward_ids)

            with self.subTest(endpoint="facility-readiness", role=user.role):
                self.authenticate(user)
                response = self.client.get(reverse("facility-readiness-review-list"))
                self.assertEqual(response.status_code, expected_status)
                if response.status_code == status.HTTP_200_OK:
                    self.assertEqual(self.ids_from_results(response, "ward"), expected_ward_ids)

        self.authenticate(self.supervisor)
        self.assertEqual(self.client.get(reverse("ward-detail", args=[self.other_ward.id])).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(reverse("alert-detail", args=[self.other_alert.id])).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            self.client.get(reverse("preparedness-action-detail", args=[self.other_preparedness_action.public_id])).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(reverse("facility-readiness-review-detail", args=[self.other_review.public_id])).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_analyst_read_access_masks_direct_alert_identifiers(self):
        self.authenticate(self.analyst)
        response = self.client.get(reverse("alert-detail", args=[self.alert.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["recipient"], "+254******1222")
        self.assertNotIn("+254700111222", response.data["message"])
        self.assertTrue(response.data["privacy_context"]["redacted"])

    def test_trigger_alerts_are_admin_or_ward_scoped_supervisor_only(self):
        payload = {"ward_id": self.ward.id, "send_sms": False, "trigger_type": "HIGH_RISK_ESCALATION"}
        other_payload = {**payload, "ward_id": self.other_ward.id}

        self.authenticate(self.admin)
        response = self.client.post(reverse("trigger-alerts"), payload, format="json")
        self.assert_step_up_required(response, StepUpGrant.PURPOSE_ALERT_DELIVERY)

        with patch("risk.views.trigger_alerts_task.delay", return_value=SimpleNamespace(id="matrix-alert-task")):
            self.authenticate(self.admin, StepUpGrant.PURPOSE_ALERT_DELIVERY)
            response = self.client.post(reverse("trigger-alerts"), payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

            self.authenticate(self.supervisor, StepUpGrant.PURPOSE_ALERT_DELIVERY)
            response = self.client.post(reverse("trigger-alerts"), payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

            self.authenticate(self.supervisor, StepUpGrant.PURPOSE_ALERT_DELIVERY)
            response = self.client.post(reverse("trigger-alerts"), other_payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        for user in (self.analyst, self.chv_user):
            with self.subTest(role=user.role):
                self.authenticate(user)
                response = self.client.post(reverse("trigger-alerts"), payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
                self.assertNotEqual(str(response.data.get("code", "")), "step_up_required")

    def test_preparedness_writes_are_admin_or_ward_scoped_supervisor_and_preserve_step_up_payloads(self):
        self.authenticate(self.admin)
        response = self.client.post(reverse("preparedness-action-list-create"), self.preparedness_payload(), format="json")
        self.assert_step_up_required(response, StepUpGrant.PURPOSE_OPERATIONAL_DATA)

        for user in (self.admin, self.supervisor):
            with self.subTest(role=user.role):
                self.authenticate(user, StepUpGrant.PURPOSE_OPERATIONAL_DATA)
                response = self.client.post(
                    reverse("preparedness-action-list-create"),
                    self.preparedness_payload(),
                    format="json",
                )
                self.assertIn(response.status_code, {status.HTTP_200_OK, status.HTTP_201_CREATED})

        self.authenticate(self.supervisor, StepUpGrant.PURPOSE_OPERATIONAL_DATA)
        response = self.client.post(
            reverse("preparedness-action-list-create"),
            self.preparedness_payload(self.other_ward.id),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.authenticate(self.analyst)
        response = self.client.post(reverse("preparedness-action-list-create"), self.preparedness_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.analyst)
        response = self.client.patch(
            reverse("preparedness-action-detail", args=[self.preparedness_action.public_id]),
            {"status": PreparednessAction.STATUS_ASSIGNED, "detail": "Analyst must remain read-only."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_chv_operations_are_not_available_to_analysts_and_remain_ward_scoped_for_supervisors(self):
        for user, expected_status in (
            (self.admin, status.HTTP_200_OK),
            (self.supervisor, status.HTTP_200_OK),
            (self.analyst, status.HTTP_403_FORBIDDEN),
            (self.chv_user, status.HTTP_403_FORBIDDEN),
        ):
            with self.subTest(endpoint="chv-list", role=user.role):
                self.authenticate(user)
                response = self.client.get(reverse("chv-list"))
                self.assertEqual(response.status_code, expected_status)
                if user == self.supervisor:
                    self.assertEqual(self.ids_from_results(response, "ward"), {self.ward.id})

            with self.subTest(endpoint="coverage-requests", role=user.role):
                self.authenticate(user)
                response = self.client.get(reverse("chv-coverage-request-list-create"))
                self.assertEqual(response.status_code, expected_status)
                if user == self.supervisor:
                    self.assertEqual(self.ids_from_results(response, "ward"), {self.ward.id})

        self.authenticate(self.supervisor)
        response = self.client.get(reverse("chv-coverage-request-detail", args=[self.other_coverage_request.public_id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_facility_readiness_writes_are_admin_or_ward_scoped_supervisor_and_analyst_view_only(self):
        self.authenticate(self.admin)
        response = self.client.post(reverse("facility-readiness-review-create", args=[self.facility.id]), {"notes": "Review now."})
        self.assert_step_up_required(response, StepUpGrant.PURPOSE_OPERATIONAL_DATA)

        for user in (self.admin, self.supervisor):
            with self.subTest(role=user.role):
                facility = self.other_facility if user == self.admin else self.facility
                FacilityReadinessReview.objects.filter(facility=facility).update(status=FacilityReadinessReview.STATUS_RESOLVED)
                self.authenticate(user, StepUpGrant.PURPOSE_OPERATIONAL_DATA)
                response = self.client.post(
                    reverse("facility-readiness-review-create", args=[facility.id]),
                    {"notes": "Matrix readiness review."},
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.authenticate(self.supervisor, StepUpGrant.PURPOSE_OPERATIONAL_DATA)
        response = self.client.post(
            reverse("facility-readiness-review-create", args=[self.other_facility.id]),
            {"notes": "Cross-ward attempt."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.authenticate(self.analyst)
        response = self.client.patch(
            reverse("facility-readiness-review-detail", args=[self.review.public_id]),
            {"status": FacilityReadinessReview.STATUS_ACKNOWLEDGED, "notes": "Analyst cannot mutate."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_sensitive_export_request_approval_and_download_matrix(self):
        request_payload = {
            "export_type": "ALERT_LIST_CSV",
            "purpose": "Matrix sensitive alert delivery reconciliation.",
            "filters": {"alert_ids": [self.alert.id, self.other_alert.id]},
        }

        self.authenticate(self.admin, StepUpGrant.PURPOSE_SENSITIVE_EXPORTS)
        response = self.client.post(reverse("sensitive-export-list-create"), request_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        admin_export_public_id = response.data["public_id"]

        self.authenticate(self.supervisor, StepUpGrant.PURPOSE_SENSITIVE_EXPORTS)
        response = self.client.post(reverse("sensitive-export-list-create"), request_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["approval_state"], "PENDING")
        supervisor_export_public_id = response.data["public_id"]

        self.authenticate(self.analyst)
        response = self.client.post(reverse("sensitive-export-list-create"), request_payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.supervisor, StepUpGrant.PURPOSE_SENSITIVE_EXPORTS)
        response = self.client.post(reverse("sensitive-export-approve", args=[supervisor_export_public_id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.admin, StepUpGrant.PURPOSE_SENSITIVE_EXPORTS)
        response = self.client.post(reverse("sensitive-export-approve", args=[supervisor_export_public_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.authenticate(self.supervisor, StepUpGrant.PURPOSE_SENSITIVE_EXPORT_DOWNLOAD)
        response = self.client.get(reverse("sensitive-export-download", args=[supervisor_export_public_id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("+254700111222", response.data["payload"])
        self.assertNotIn("+254700333444", response.data["payload"])

        self.authenticate(self.supervisor, StepUpGrant.PURPOSE_SENSITIVE_EXPORT_DOWNLOAD)
        response = self.client.get(reverse("sensitive-export-download", args=[admin_export_public_id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.analyst)
        response = self.client.get(reverse("sensitive-export-download", args=[admin_export_public_id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_source_data_read_write_and_risky_approval_matrix(self):
        for user, expected_status in (
            (self.admin, status.HTTP_200_OK),
            (self.supervisor, status.HTTP_200_OK),
            (self.analyst, status.HTTP_200_OK),
            (self.chv_user, status.HTTP_403_FORBIDDEN),
        ):
            with self.subTest(endpoint="feed-types", role=user.role):
                self.authenticate(user)
                self.assertEqual(self.client.get(reverse("source-data-feed-types")).status_code, expected_status)

            with self.subTest(endpoint="template", role=user.role):
                self.authenticate(user)
                response = self.client.get(reverse("source-data-template-file", args=["surveillance_weekly_aggregate"]))
                self.assertEqual(response.status_code, expected_status)

            with self.subTest(endpoint="errors-file", role=user.role):
                self.authenticate(user)
                response = self.client.get(reverse("source-data-upload-errors-file", args=[self.source_batch.public_id]))
                self.assertEqual(response.status_code, expected_status)

        self.authenticate(self.supervisor, StepUpGrant.PURPOSE_SOURCE_DATA)
        response = self.client.post(
            reverse("source-data-upload-list-create"),
            self.upload_payload(),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.authenticate(self.admin)
        response = self.client.post(reverse("source-data-upload-validate", args=[self.source_batch.public_id]), {}, format="json")
        self.assert_step_up_required(response, StepUpGrant.PURPOSE_SOURCE_DATA)

        for user in (self.analyst, self.chv_user):
            with self.subTest(write_endpoint="upload", role=user.role):
                self.authenticate(user)
                response = self.client.post(
                    reverse("source-data-upload-list-create"),
                    self.upload_payload(f"{user.username}.csv"),
                    format="multipart",
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.supervisor, StepUpGrant.PURPOSE_SOURCE_DATA)
        response = self.client.post(
            reverse("source-data-upload-approval", args=[self.source_batch.public_id]),
            {"action": "approve", "reason": "Supervisor cannot approve risky imports."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.admin, StepUpGrant.PURPOSE_SOURCE_DATA)
        response = self.client.post(
            reverse("source-data-upload-approval", args=[self.source_batch.public_id]),
            {"action": "approve", "reason": "Admin maker-checker approval."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_message_governance_read_and_approval_matrix(self):
        for user, expected_status in (
            (self.admin, status.HTTP_200_OK),
            (self.supervisor, status.HTTP_200_OK),
            (self.analyst, status.HTTP_200_OK),
            (self.chv_user, status.HTTP_403_FORBIDDEN),
        ):
            with self.subTest(endpoint="message-governance", role=user.role):
                self.authenticate(user)
                self.assertEqual(self.client.get(reverse("message-governance-dashboard")).status_code, expected_status)

        for user in (self.supervisor, self.analyst, self.chv_user):
            with self.subTest(approval_role=user.role):
                self.authenticate(user)
                response = self.client.post(
                    reverse("message-template-approval", args=[self.message_template.public_id]),
                    {"action": "approve", "reason": "Matrix approval attempt."},
                    format="json",
                )
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.admin)
        response = self.client.post(
            reverse("message-template-approval", args=[self.message_template.public_id]),
            {"action": "approve", "reason": "Admin approval requires step-up first."},
            format="json",
        )
        self.assert_step_up_required(response, StepUpGrant.PURPOSE_MESSAGE_GOVERNANCE)

        self.authenticate(self.admin, StepUpGrant.PURPOSE_MESSAGE_GOVERNANCE)
        response = self.client.post(
            reverse("message-template-approval", args=[self.message_template.public_id]),
            {"action": "approve", "reason": "Admin approved governed template."},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_system_read_status_is_shared_but_write_controls_are_admin_only(self):
        for user, expected_status, expected_can_write in (
            (self.admin, status.HTTP_200_OK, True),
            (self.supervisor, status.HTTP_200_OK, False),
            (self.analyst, status.HTTP_200_OK, False),
            (self.chv_user, status.HTTP_403_FORBIDDEN, None),
        ):
            with self.subTest(endpoint="system-controls", role=user.role):
                self.authenticate(user)
                response = self.client.get(reverse("system-control-status"))
                self.assertEqual(response.status_code, expected_status)
                if expected_can_write is not None:
                    self.assertEqual(response.data["can_retry_background_jobs"], expected_can_write)
                    self.assertEqual(response.data["can_run_manual_risk_scoring"], expected_can_write)
                    self.assertEqual(response.data["can_pause_alert_delivery"], expected_can_write)

            with self.subTest(endpoint="system-readiness", role=user.role):
                self.authenticate(user)
                response = self.client.get(reverse("system-readiness"))
                self.assertEqual(response.status_code, expected_status)

        for user in (self.supervisor, self.analyst, self.chv_user):
            with self.subTest(write_role=user.role):
                self.authenticate(user)
                response = self.client.post(reverse("system-control-retry"), {"limit": 1}, format="json")
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.admin)
        response = self.client.post(reverse("system-control-retry"), {"limit": 1}, format="json")
        self.assert_step_up_required(response, StepUpGrant.PURPOSE_SYSTEM_CONTROLS)

    def test_superuser_with_non_admin_profile_role_is_admin_equivalent_without_a_fifth_policy(self):
        break_glass_user = User.objects.create_user(
            username="matrix_break_glass_superuser",
            email="matrix_break_glass_superuser@example.com",
            password=self.password,
            role=User.ROLE_CHV,
            ward=self.ward,
            is_superuser=True,
            is_staff=True,
        )

        self.authenticate(break_glass_user)

        ward_response = self.client.get(reverse("ward-list"))
        chv_response = self.client.get(reverse("chv-list"))
        trigger_context_response = self.client.get(
            reverse("trigger-alert-context"),
            {"risk_level": Ward.RISK_MEDIUM},
        )
        system_status_response = self.client.get(reverse("system-control-status"))
        system_write_response = self.client.post(reverse("system-control-retry"), {"limit": 1}, format="json")

        self.assertEqual(ward_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.ids_from_results(ward_response), {self.ward.id, self.other_ward.id})
        self.assertEqual(chv_response.status_code, status.HTTP_200_OK)
        self.assertEqual(trigger_context_response.status_code, status.HTTP_200_OK)
        self.assertEqual(trigger_context_response.data["ward"]["id"], self.other_ward.id)
        self.assertEqual(system_status_response.status_code, status.HTTP_200_OK)
        self.assertTrue(system_status_response.data["can_retry_background_jobs"])
        self.assert_step_up_required(system_write_response, StepUpGrant.PURPOSE_SYSTEM_CONTROLS)

        sensitive_export_payload = {
            "export_type": "ALERT_LIST_CSV",
            "purpose": "Break-glass export audit verification.",
            "filters": {"alert_ids": [self.alert.id, self.other_alert.id]},
        }
        self.authenticate(break_glass_user, StepUpGrant.PURPOSE_SENSITIVE_EXPORTS)
        export_response = self.client.post(
            reverse("sensitive-export-list-create"),
            sensitive_export_payload,
            format="json",
        )
        self.assertEqual(export_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(export_response.data["approval_state"], "APPROVED")

        self.authenticate(break_glass_user, StepUpGrant.PURPOSE_SENSITIVE_EXPORT_DOWNLOAD)
        download_response = self.client.get(reverse("sensitive-export-download", args=[export_response.data["public_id"]]))
        self.assertEqual(download_response.status_code, status.HTTP_200_OK)
        self.assertIn("+254700111222", download_response.data["payload"])
        self.assertIn("+254700333444", download_response.data["payload"])

        break_glass_batch = self.create_source_batch(
            created_by=self.supervisor,
            status_value=SourceDataUploadBatch.STATUS_READY_FOR_CONFIRMATION,
            approval_status=SourceDataUploadBatch.APPROVAL_NOT_REQUIRED,
        )
        self.authenticate(break_glass_user, StepUpGrant.PURPOSE_SOURCE_DATA)
        source_approval_response = self.client.post(
            reverse("source-data-upload-approval", args=[break_glass_batch.public_id]),
            {"action": "request", "reason": "Break-glass source-data request path."},
            format="json",
        )
        self.assertEqual(source_approval_response.status_code, status.HTTP_200_OK)

    def test_preparedness_action_source_trigger_children_inherit_high_risk_permissions(self):
        child_views = [
            AlertPreparednessActionCreateAPIView,
            AlertWorkflowPreparednessActionCreateAPIView,
            CHVCoverageRequestPreparednessActionCreateAPIView,
            FacilityReadinessReviewPreparednessActionCreateAPIView,
            FacilityReadinessEscalationPreparednessActionCreateAPIView,
        ]

        for view_class in child_views:
            with self.subTest(view=view_class.__name__):
                permission_names = [permission.__name__ for permission in view_class.permission_classes]
                self.assertIs(view_class.permission_classes[0], IsAdminOrSupervisor)
                self.assertIn(
                    f"RequireFreshStepUp_{StepUpGrant.PURPOSE_OPERATIONAL_DATA}",
                    permission_names,
                )

        self.authenticate(self.analyst)
        response = self.client.post(
            reverse("alert-preparedness-action-create", args=[self.alert.id]),
            {
                "action_type": PreparednessAction.ACTION_FIELD_VERIFICATION,
                "priority": PreparednessAction.PRIORITY_HIGH,
                "notes": "Analyst cannot trigger source action.",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        self.authenticate(self.admin)
        response = self.client.post(
            reverse("alert-preparedness-action-create", args=[self.alert.id]),
            {
                "action_type": PreparednessAction.ACTION_FIELD_VERIFICATION,
                "priority": PreparednessAction.PRIORITY_HIGH,
                "notes": "Admin still needs step-up.",
            },
            format="json",
        )
        self.assert_step_up_required(response, StepUpGrant.PURPOSE_OPERATIONAL_DATA)


class OperationalAPIViewPermissionDeclarationTests(APITestCase):
    def test_operational_api_views_declare_permissions_or_dynamic_permissions(self):
        from accounts import urls as account_urls
        from risk import urls as risk_urls

        failures = []
        for pattern in [*risk_urls.urlpatterns, *account_urls.urlpatterns]:
            view_class = getattr(pattern.callback, "view_class", None)
            if view_class is None:
                continue
            if not view_class.__module__.startswith(("risk.views", "accounts.views")):
                continue

            project_mro = [
                cls
                for cls in view_class.mro()
                if cls.__module__.startswith(("risk.views", "accounts.views"))
            ]
            declares_permissions = any("permission_classes" in cls.__dict__ for cls in project_mro)
            declares_dynamic_permissions = any("get_permissions" in cls.__dict__ for cls in project_mro)
            if not declares_permissions and not declares_dynamic_permissions:
                failures.append(f"{view_class.__module__}.{view_class.__name__}")

        self.assertEqual(
            failures,
            [],
            "Operational API views must declare permission_classes or get_permissions().",
        )
