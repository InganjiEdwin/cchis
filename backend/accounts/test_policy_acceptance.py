from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AuthAuditEvent, UserPolicyAcceptance
from .services import create_current_policy_acceptances


User = get_user_model()


class PolicyAcceptanceApiTests(APITestCase):
    password = "ChangeMe123!"

    def setUp(self):
        self.user = User.objects.create_user(
            username="policy_user",
            password=self.password,
            email="policy_user@example.com",
        )
        self.user.full_name = "Policy User"
        self.user.role = User.ROLE_ANALYST
        self.user.save(update_fields=["full_name", "role"])

    def _authenticate(self):
        self.client.force_authenticate(user=self.user)

    def _authenticate_with_jwt(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")

    def _current_acceptance_payload(self, **overrides):
        payload = {
            "accepted_terms": True,
            "accepted_privacy": True,
            "accepted_cookie_notice": True,
            "terms_version": settings.CURRENT_TERMS_VERSION,
            "privacy_version": settings.CURRENT_PRIVACY_VERSION,
            "cookie_notice_version": settings.CURRENT_COOKIE_NOTICE_VERSION,
        }
        payload.update(overrides)
        return payload

    def test_user_serializer_reports_missing_current_policy_acceptance(self):
        self._authenticate()

        response = self.client.get(reverse("auth-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        policy_acceptance = response.data["policy_acceptance"]
        self.assertTrue(policy_acceptance["required"])
        self.assertFalse(policy_acceptance["is_current"])
        self.assertEqual(policy_acceptance["terms_version"], settings.CURRENT_TERMS_VERSION)
        self.assertEqual(policy_acceptance["privacy_version"], settings.CURRENT_PRIVACY_VERSION)
        self.assertEqual(
            policy_acceptance["cookie_notice_version"],
            settings.CURRENT_COOKIE_NOTICE_VERSION,
        )
        self.assertIsNone(policy_acceptance["accepted_terms_version"])
        self.assertIsNone(policy_acceptance["accepted_privacy_version"])
        self.assertIsNone(policy_acceptance["accepted_cookie_notice_version"])
        self.assertEqual(
            policy_acceptance["missing_documents"],
            [
                UserPolicyAcceptance.DOCUMENT_TERMS,
                UserPolicyAcceptance.DOCUMENT_PRIVACY,
                UserPolicyAcceptance.DOCUMENT_COOKIE_NOTICE,
            ],
        )
        self.assertEqual(policy_acceptance["terms_url"], "/terms")
        self.assertEqual(policy_acceptance["privacy_url"], "/privacy")
        self.assertEqual(policy_acceptance["cookie_notice_url"], "/privacy#cookies")

    def test_policy_acceptance_get_records_required_audit_event(self):
        self._authenticate()

        response = self.client.get(
            reverse("auth-policy-acceptance"),
            REMOTE_ADDR="10.10.0.10",
            HTTP_USER_AGENT="PolicyTest/required",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_current"])
        event = AuthAuditEvent.objects.get(
            event_type=AuthAuditEvent.EVENT_POLICY_ACCEPTANCE_REQUIRED,
            target_user=self.user,
        )
        self.assertEqual(event.status, AuthAuditEvent.STATUS_SUCCESS)
        self.assertEqual(event.ip_address, "10.10.0.10")
        self.assertEqual(
            event.metadata,
            {
                "terms_version": settings.CURRENT_TERMS_VERSION,
                "privacy_version": settings.CURRENT_PRIVACY_VERSION,
                "cookie_notice_version": settings.CURRENT_COOKIE_NOTICE_VERSION,
                "acceptance_context": UserPolicyAcceptance.CONTEXT_FIRST_SIGN_IN,
                "missing_documents": [
                    UserPolicyAcceptance.DOCUMENT_TERMS,
                    UserPolicyAcceptance.DOCUMENT_PRIVACY,
                    UserPolicyAcceptance.DOCUMENT_COOKIE_NOTICE,
                ],
            },
        )

    def test_policy_acceptance_status_marks_version_update_required(self):
        UserPolicyAcceptance.objects.create(
            user=self.user,
            document_type=UserPolicyAcceptance.DOCUMENT_TERMS,
            version="terms-2026-04",
        )
        UserPolicyAcceptance.objects.create(
            user=self.user,
            document_type=UserPolicyAcceptance.DOCUMENT_PRIVACY,
            version=settings.CURRENT_PRIVACY_VERSION,
        )
        UserPolicyAcceptance.objects.create(
            user=self.user,
            document_type=UserPolicyAcceptance.DOCUMENT_COOKIE_NOTICE,
            version=settings.CURRENT_COOKIE_NOTICE_VERSION,
        )
        self._authenticate()

        response = self.client.get(reverse("auth-policy-acceptance"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_current"])
        self.assertEqual(response.data["accepted_terms_version"], "terms-2026-04")
        self.assertEqual(
            response.data["missing_documents"],
            [UserPolicyAcceptance.DOCUMENT_TERMS],
        )
        event = AuthAuditEvent.objects.get(
            event_type=AuthAuditEvent.EVENT_POLICY_ACCEPTANCE_REQUIRED,
            target_user=self.user,
        )
        self.assertEqual(
            event.metadata["acceptance_context"],
            UserPolicyAcceptance.CONTEXT_VERSION_UPDATE,
        )
        self.assertEqual(
            event.metadata["missing_documents"],
            [UserPolicyAcceptance.DOCUMENT_TERMS],
        )

    def test_policy_acceptance_post_creates_idempotent_ledger_and_audit_event(self):
        self._authenticate()
        url = reverse("auth-policy-acceptance")

        response = self.client.post(
            url,
            self._current_acceptance_payload(),
            format="json",
            REMOTE_ADDR="10.10.0.20",
            HTTP_USER_AGENT="PolicyTest/accepted",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_current"])
        self.assertEqual(response.data["missing_documents"], [])
        self.assertEqual(UserPolicyAcceptance.objects.filter(user=self.user).count(), 3)

        acceptances = {
            acceptance.document_type: acceptance
            for acceptance in UserPolicyAcceptance.objects.filter(user=self.user)
        }
        self.assertEqual(
            set(acceptances.keys()),
            {
                UserPolicyAcceptance.DOCUMENT_TERMS,
                UserPolicyAcceptance.DOCUMENT_PRIVACY,
                UserPolicyAcceptance.DOCUMENT_COOKIE_NOTICE,
            },
        )
        for acceptance in acceptances.values():
            self.assertEqual(acceptance.ip_address, "10.10.0.20")
            self.assertEqual(acceptance.user_agent, "PolicyTest/accepted")
            self.assertEqual(
                acceptance.acceptance_context,
                UserPolicyAcceptance.CONTEXT_FIRST_SIGN_IN,
            )
            self.assertEqual(
                acceptance.metadata,
                {"accepted_via": "auth_policy_acceptance_endpoint"},
            )

        event = AuthAuditEvent.objects.get(
            event_type=AuthAuditEvent.EVENT_POLICY_ACCEPTED,
            target_user=self.user,
        )
        self.assertEqual(event.status, AuthAuditEvent.STATUS_SUCCESS)
        self.assertEqual(event.ip_address, "10.10.0.20")
        self.assertEqual(
            event.metadata["missing_documents"],
            [
                UserPolicyAcceptance.DOCUMENT_TERMS,
                UserPolicyAcceptance.DOCUMENT_PRIVACY,
                UserPolicyAcceptance.DOCUMENT_COOKIE_NOTICE,
            ],
        )
        self.assertEqual(
            set(event.metadata["created_documents"]),
            {
                UserPolicyAcceptance.DOCUMENT_TERMS,
                UserPolicyAcceptance.DOCUMENT_PRIVACY,
                UserPolicyAcceptance.DOCUMENT_COOKIE_NOTICE,
            },
        )

        second_response = self.client.post(
            url,
            self._current_acceptance_payload(),
            format="json",
            REMOTE_ADDR="10.10.0.21",
            HTTP_USER_AGENT="PolicyTest/repeated",
        )

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertTrue(second_response.data["is_current"])
        self.assertEqual(UserPolicyAcceptance.objects.filter(user=self.user).count(), 3)

    def test_policy_acceptance_post_rejects_stale_versions(self):
        self._authenticate()

        response = self.client.post(
            reverse("auth-policy-acceptance"),
            self._current_acceptance_payload(terms_version="terms-old"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("terms_version", response.data)
        self.assertFalse(UserPolicyAcceptance.objects.filter(user=self.user).exists())

    def test_policy_acceptance_endpoint_requires_authenticated_user(self):
        get_response = self.client.get(reverse("auth-policy-acceptance"))
        post_response = self.client.post(
            reverse("auth-policy-acceptance"),
            self._current_acceptance_payload(),
            format="json",
        )

        self.assertEqual(get_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(post_response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(POLICY_ACCEPTANCE_REQUIRED=False)
    def test_policy_acceptance_status_can_be_disabled(self):
        self._authenticate()

        response = self.client.get(reverse("auth-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        policy_acceptance = response.data["policy_acceptance"]
        self.assertFalse(policy_acceptance["required"])
        self.assertTrue(policy_acceptance["is_current"])
        self.assertEqual(policy_acceptance["missing_documents"], [])

    def test_policy_missing_user_cannot_bypass_gate_with_direct_operational_api(self):
        self._authenticate_with_jwt()

        response = self.client.get(reverse("ward-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data["code"], "policy_acceptance_required")
        self.assertEqual(
            response.data["policy_acceptance"]["missing_documents"],
            [
                UserPolicyAcceptance.DOCUMENT_TERMS,
                UserPolicyAcceptance.DOCUMENT_PRIVACY,
                UserPolicyAcceptance.DOCUMENT_COOKIE_NOTICE,
            ],
        )

    def test_current_policy_acceptance_allows_direct_operational_api(self):
        create_current_policy_acceptances(self.user)
        self._authenticate_with_jwt()

        response = self.client.get(reverse("ward-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_policy_missing_user_can_still_read_auth_me_with_jwt(self):
        self._authenticate_with_jwt()

        response = self.client.get(reverse("auth-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["policy_acceptance"]["is_current"])
