from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import Alert, SensitiveExportDownloadAudit, SensitiveExportRequest, Ward


class SensitiveExportGovernanceTests(APITestCase):
    password = "ChangeMe123!"

    def setUp(self):
        self.ward = Ward.objects.create(
            name="Export Ward",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.87,
            is_active=True,
        )
        self.other_ward = Ward.objects.create(
            name="Other Export Ward",
            county="Migori",
            sub_county="Awendo",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.18,
            is_active=True,
        )
        self.admin_user = User.objects.create_user(
            username="export_admin",
            password=self.password,
            email="export-admin@example.com",
            role=User.ROLE_ADMIN,
            ward=self.ward,
            is_active=True,
        )
        self.supervisor_user = User.objects.create_user(
            username="export_supervisor",
            password=self.password,
            email="export-supervisor@example.com",
            role=User.ROLE_SUPERVISOR,
            ward=self.ward,
            is_active=True,
        )
        self.analyst_user = User.objects.create_user(
            username="export_analyst",
            password=self.password,
            email="export-analyst@example.com",
            role=User.ROLE_ANALYST,
            is_active=True,
        )
        self.alert = Alert.objects.create(
            ward=self.ward,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700111222",
            message="Sensitive prevention delivery message.",
            status=Alert.STATUS_DELIVERED,
            delivery_backend="africastalking",
            attempt_count=1,
            max_attempts=3,
            external_id="provider-export-1",
            sent_at=timezone.now(),
        )
        self.other_alert = Alert.objects.create(
            ward=self.other_ward,
            channel=Alert.CHANNEL_SMS,
            recipient="+254700333444",
            message="Other ward message.",
            status=Alert.STATUS_DELIVERED,
            delivery_backend="africastalking",
            attempt_count=1,
            max_attempts=3,
        )

    def test_admin_export_is_attributable_approved_and_download_audited(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(
            reverse("sensitive-export-list-create"),
            {
                "export_type": SensitiveExportRequest.EXPORT_ALERT_DETAIL_REPORT,
                "purpose": "Operational delivery review for alert follow-up.",
                "filters": {"alert_id": self.alert.id},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["approval_state"], SensitiveExportRequest.APPROVAL_APPROVED)
        self.assertEqual(response.data["requester"], self.admin_user.id)
        self.assertEqual(response.data["sensitive_fields_included"][0], "alert.recipient")
        self.assertTrue(response.data["generated_at"])
        self.assertTrue(response.data["expires_at"])
        self.assertTrue(response.data["has_payload"])

        export_request = SensitiveExportRequest.objects.get(public_id=response.data["public_id"])
        download_response = self.client.get(reverse("sensitive-export-download", args=[export_request.public_id]))

        self.assertEqual(download_response.status_code, status.HTTP_200_OK)
        self.assertIn("+254700111222", download_response.data["payload"])
        self.assertEqual(download_response.data["payload_sha256"], export_request.payload_sha256)
        export_request.refresh_from_db()
        self.assertEqual(export_request.download_count, 1)
        self.assertTrue(
            SensitiveExportDownloadAudit.objects.filter(
                export_request=export_request,
                downloader=self.admin_user,
                outcome=SensitiveExportDownloadAudit.OUTCOME_DOWNLOADED,
            ).exists()
        )

    def test_supervisor_direct_identifier_export_requires_admin_approval_and_stays_ward_scoped(self):
        self.client.force_authenticate(self.supervisor_user)

        response = self.client.post(
            reverse("sensitive-export-list-create"),
            {
                "export_type": SensitiveExportRequest.EXPORT_ALERT_LIST_CSV,
                "purpose": "Ward alert delivery reconciliation for response handoff.",
                "filters": {"alert_ids": [self.alert.id, self.other_alert.id]},
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["approval_state"], SensitiveExportRequest.APPROVAL_PENDING)
        self.assertTrue(response.data["requires_approval"])
        self.assertFalse(response.data["has_payload"])

        export_request = SensitiveExportRequest.objects.get(public_id=response.data["public_id"])
        blocked_download = self.client.get(reverse("sensitive-export-download", args=[export_request.public_id]))
        self.assertEqual(blocked_download.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(
            SensitiveExportDownloadAudit.objects.filter(
                export_request=export_request,
                outcome=SensitiveExportDownloadAudit.OUTCOME_BLOCKED_NOT_APPROVED,
            ).exists()
        )

        self.client.force_authenticate(self.admin_user)
        approval_response = self.client.post(reverse("sensitive-export-approve", args=[export_request.public_id]))
        self.assertEqual(approval_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approval_response.data["approval_state"], SensitiveExportRequest.APPROVAL_APPROVED)
        self.assertEqual(approval_response.data["row_count"], 1)

        self.client.force_authenticate(self.supervisor_user)
        download_response = self.client.get(reverse("sensitive-export-download", args=[export_request.public_id]))
        self.assertEqual(download_response.status_code, status.HTTP_200_OK)
        self.assertIn("+254700111222", download_response.data["payload"])
        self.assertNotIn("+254700333444", download_response.data["payload"])

    def test_analyst_cannot_request_sensitive_export_and_alert_intelligence_remains_masked(self):
        self.client.force_authenticate(self.analyst_user)

        response = self.client.post(
            reverse("sensitive-export-list-create"),
            {
                "export_type": SensitiveExportRequest.EXPORT_ALERT_DETAIL_REPORT,
                "purpose": "Analytical review that should not include direct identifiers.",
                "filters": {"alert_id": self.alert.id},
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        intelligence_response = self.client.get(reverse("alert-intelligence", args=[self.alert.id]))
        self.assertEqual(intelligence_response.status_code, status.HTTP_200_OK)
        self.assertEqual(intelligence_response.data["alert"]["recipient"], "+254******1222")
        self.assertTrue(intelligence_response.data["alert"]["privacy_context"]["redacted"])

    def test_expired_export_is_blocked_cleared_and_audited(self):
        self.client.force_authenticate(self.admin_user)
        response = self.client.post(
            reverse("sensitive-export-list-create"),
            {
                "export_type": SensitiveExportRequest.EXPORT_ALERT_DETAIL_REPORT,
                "purpose": "Operational delivery review for expiry handling.",
                "filters": {"alert_id": self.alert.id},
            },
            format="json",
        )
        export_request = SensitiveExportRequest.objects.get(public_id=response.data["public_id"])
        SensitiveExportRequest.objects.filter(pk=export_request.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        expired_response = self.client.get(reverse("sensitive-export-download", args=[export_request.public_id]))

        self.assertEqual(expired_response.status_code, status.HTTP_400_BAD_REQUEST)
        export_request.refresh_from_db()
        self.assertEqual(export_request.approval_state, SensitiveExportRequest.APPROVAL_EXPIRED)
        self.assertEqual(export_request.generated_payload, "")
        self.assertTrue(
            SensitiveExportDownloadAudit.objects.filter(
                export_request=export_request,
                outcome=SensitiveExportDownloadAudit.OUTCOME_BLOCKED_EXPIRED,
            ).exists()
        )

    def test_export_rejects_unsafe_or_invalid_filters_before_ledger_creation(self):
        self.client.force_authenticate(self.admin_user)

        unsafe_response = self.client.post(
            reverse("sensitive-export-list-create"),
            {
                "export_type": SensitiveExportRequest.EXPORT_ALERT_LIST_CSV,
                "purpose": "Operational delivery review for unsafe filter handling.",
                "filters": {"status": "+254700111222"},
            },
            format="json",
        )
        missing_detail_response = self.client.post(
            reverse("sensitive-export-list-create"),
            {
                "export_type": SensitiveExportRequest.EXPORT_ALERT_DETAIL_REPORT,
                "purpose": "Operational delivery review for missing alert filter.",
                "filters": {},
            },
            format="json",
        )

        self.assertEqual(unsafe_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(missing_detail_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(SensitiveExportRequest.objects.exists())
