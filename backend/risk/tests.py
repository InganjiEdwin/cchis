import os
import time
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.cache import cache
from django.test import RequestFactory
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.settings import api_settings

from accounts.audit import get_client_ip
from accounts.admin import AccessRequestAdmin
from accounts.models import AccessRequest, AuthAuditEvent, PasswordResetToken, PreAuthToken
from accounts.turnstile import TurnstileVerificationResult
from accounts.two_factor import generate_current_totp_code, generate_totp_secret
from communications.providers import MailgunEmailProvider, StubEmailProvider, get_email_provider
from communications.services import send_email
from accounts.views import (
    ChangePasswordAPIView,
    DeactivateUserAPIView,
    LoginAPIView,
    LogoutAPIView,
    ReactivateUserAPIView,
    RefreshAPIView,
    VerifyTwoFactorAPIView,
)
from core.observability import (
    DOMAIN_AUDIT_INVENTORY,
    EVENT_CLASSIFICATIONS,
    MINIMUM_RUNBOOK_INPUTS,
    OPERATIONAL_METRICS,
    RECOVERY_VISIBILITY_REQUIREMENTS,
)
from core.data_lifecycle import DATA_RETENTION_INVENTORY, FIELD_DATA_MINIMIZATION_RULES
from core.recovery_discipline import BACKUP_EXPECTATIONS, RESTORE_REHEARSAL_EXPECTATIONS
from risk.ml.ingestion import fetch_rainfall_for_ward
from risk.canonical import (
    alert_to_canonical_record,
    canonical_export_envelope,
    facility_to_canonical_ref,
    riskscore_to_canonical_record,
    ward_to_canonical_ref,
)
from risk.interoperability import (
    build_dhis2_org_unit_mapping_stub,
    build_dhis2_risk_score_export_stub,
    facility_location_crosswalk_key,
    ward_location_crosswalk_key,
)
from risk.providers import DeliveryResult, StubSmsProvider, get_sms_provider
from risk.services import create_alerts_for_riskscore, deliver_alert
from risk.tasks import deliver_alert_task, trigger_alerts_task


def started_at_ms(offset_ms: int = 2000) -> int:
    return int(time.time() * 1000) - offset_ms
from risk.views import USSDMenuAPIView

from .models import Alert, CHV, HealthFacility, IngestionRun, ModelRun, RiskScore, SyncQueue, TriageSession, UssdSessionLog, Ward


User = get_user_model()


def get_results(response):
    if isinstance(response.data, dict) and "results" in response.data:
        return response.data["results"]
    return response.data


class AuthenticatedAPITestCase(APITestCase):
    password = "ChangeMe123!"
    _client_counter = 1

    def setUp(self):
        octet = (self.__class__._client_counter % 250) + 1
        self.__class__._client_counter += 1
        self.client.defaults["REMOTE_ADDR"] = f"127.0.0.{octet}"

        self.ward = Ward.objects.create(
            name="North Kamagambo",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.86,
            is_active=True,
        )

        self.other_ward = Ward.objects.create(
            name="North Kadem",
            county="Migori",
            sub_county="Nyatike",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.62,
            is_active=True,
        )

        self.chv = CHV.objects.create(
            name="Jane CHV",
            phone_number="+254700000001",
            ward=self.ward,
            is_active=True,
            language="en",
        )
        self.health_facility = HealthFacility.objects.create(
            name="North Kamagambo Dispensary",
            facility_code="TEST-HF-001",
            ward=self.ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
            contact_phone="+254720100001",
        )
        self.model_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="v0-test",
            status=ModelRun.STATUS_SUCCESS,
            month=4,
            feature_schema_version="mock-v1",
            feature_keys=[
                "rainfall_mm",
                "flood_indicator",
                "historical_cases",
                "month",
                "seasonality",
                "population_proxy",
            ],
            training_dataset_ref="test-training-dataset:v1",
            inference_dataset_ref="test-inference-dataset:v1",
            training_row_count=8,
            inference_row_count=2,
            evaluation_metrics={"training_accuracy": 1.0},
            metadata={"source": "test"},
            completed_at=timezone.now(),
        )

        self.risk_score = RiskScore.objects.create(
            ward=self.ward,
            model_run=self.model_run,
            score=0.86,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=120.0,
            flood_indicator=0.8,
            predicted_cases=18,
            source=RiskScore.SOURCE_MODEL,
            model_version="v0-test",
        )

        self.other_risk_score = RiskScore.objects.create(
            ward=self.other_ward,
            model_run=self.model_run,
            score=0.62,
            risk_level=Ward.RISK_MEDIUM,
            rainfall_mm=65.0,
            flood_indicator=0.4,
            predicted_cases=7,
            source=RiskScore.SOURCE_MODEL,
            model_version="v0-test",
        )

        self.admin_user = self._create_user(
            username="admin",
            role=User.ROLE_ADMIN,
            ward=self.ward,
            is_staff=True,
            is_superuser=True,
        )
        self.supervisor_user = self._create_user(
            username="supervisor",
            role=User.ROLE_SUPERVISOR,
            ward=self.other_ward,
            is_staff=True,
        )
        self.chv_user = self._create_user(
            username="chv_demo",
            role=User.ROLE_CHV,
            ward=self.ward,
        )
        self.analyst_user = self._create_user(
            username="analyst_demo",
            role=User.ROLE_ANALYST,
            ward=self.other_ward,
        )

        self._enroll_user_for_totp(self.admin_user)
        self._enroll_user_for_totp(self.supervisor_user)

    def _create_user(
        self,
        username: str,
        role: str,
        ward: Ward | None = None,
        is_staff: bool = False,
        is_superuser: bool = False,
    ):
        user = User.objects.create_user(
            username=username,
            password=self.password,
            email=f"{username}@example.com",
        )
        user.full_name = username.replace("_", " ").title()
        user.phone_number = f"+254711{User.objects.count():06d}"
        user.role = role
        user.ward = ward
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.is_active = True
        user.save()
        return user

    def authenticate(self, username: str, password: str | None = None) -> str:
        self.client.credentials()
        response = self.client.post(
            reverse("auth-login"),
            {"username": username, "password": password or self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        if response.data.get("requires_2fa"):
            user = User.objects.get(username=username)
            verify_response = self.client.post(
                reverse("auth-verify-2fa"),
                {
                    "token": response.data["temp_token"],
                    "code": generate_current_totp_code(user.totp_secret),
                },
                format="json",
            )
            self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
            token = verify_response.data["access"]
        else:
            token = response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        return token

    def _enroll_user_for_totp(self, user: User):
        user.totp_secret = generate_totp_secret()
        user.is_totp_enabled = True
        user.save(update_fields=["totp_secret", "is_totp_enabled"])


class AuthEndpointsTestCase(AuthenticatedAPITestCase):
    def test_login_returns_tokens_and_user_profile(self):
        response = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertFalse(response.data["requires_2fa"])
        self.assertEqual(response.data["user"]["role"], User.ROLE_CHV)
        self.assertEqual(response.data["user"]["two_factor_policy"], "NONE")
        self.assertEqual(response.data["user"]["theme_preference"], User.THEME_SYSTEM)
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_LOGIN_SUCCESS,
                status=AuthAuditEvent.STATUS_SUCCESS,
                target_user=self.chv_user,
            ).exists()
        )

    def test_login_sets_refresh_cookie_for_direct_session(self):
        response = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cookie = response.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
        self.assertIsNotNone(cookie)
        self.assertEqual(cookie.value, response.data["refresh"])

    def test_login_exposes_optional_two_factor_policy_for_analyst(self):
        response = self.client.post(
            reverse("auth-login"),
            {"username": self.analyst_user.username, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["requires_2fa"])
        self.assertEqual(response.data["user"]["two_factor_policy"], "OPTIONAL")

    def test_login_returns_temp_token_for_enrolled_admin(self):
        response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["requires_2fa"])
        self.assertIn("temp_token", response.data)
        self.assertNotIn("access", response.data)
        self.assertNotIn("refresh", response.data)
        self.assertNotIn(settings.AUTH_REFRESH_COOKIE_NAME, response.cookies)
        self.assertTrue(
            PreAuthToken.objects.filter(
                user=self.admin_user,
                token=response.data["temp_token"],
            ).exists()
        )

    def test_verify_2fa_sets_refresh_cookie(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )

        verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": login_response.data["temp_token"],
                "code": generate_current_totp_code(self.admin_user.totp_secret),
            },
            format="json",
        )

        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        cookie = verify_response.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
        self.assertIsNotNone(cookie)
        self.assertEqual(cookie.value, verify_response.data["refresh"])
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_2FA_REQUIRED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                target_user=self.admin_user,
            ).exists()
        )

    def test_login_blocks_required_role_without_totp_enrollment(self):
        unenrolled_admin = self._create_user(
            username="pilot_admin_blocked",
            role=User.ROLE_ADMIN,
            ward=self.ward,
            is_staff=True,
            is_superuser=True,
        )

        response = self.client.post(
            reverse("auth-login"),
            {"username": unenrolled_admin.username, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["requires_2fa_enrollment"])
        self.assertFalse(response.data["requires_2fa"])
        self.assertIn("temp_token", response.data)
        self.assertNotIn(settings.AUTH_REFRESH_COOKIE_NAME, response.cookies)
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_2FA_ENROLLMENT_REQUIRED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                target_user=unenrolled_admin,
            ).exists()
        )

    def test_begin_two_factor_enrollment_returns_setup_details_for_pre_auth_token(self):
        unenrolled_admin = self._create_user(
            username="pilot_admin_setup",
            role=User.ROLE_ADMIN,
            ward=self.ward,
            is_staff=True,
            is_superuser=True,
        )

        login_response = self.client.post(
            reverse("auth-login"),
            {"username": unenrolled_admin.username, "password": self.password},
            format="json",
        )

        response = self.client.post(
            reverse("auth-2fa-setup"),
            {"token": login_response.data["temp_token"]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("manual_entry_key", response.data)
        self.assertIn("provisioning_uri", response.data)
        unenrolled_admin.refresh_from_db()
        self.assertTrue(unenrolled_admin.totp_secret)

    def test_confirm_two_factor_enrollment_issues_tokens_for_pre_auth_token(self):
        unenrolled_admin = self._create_user(
            username="pilot_admin_enroll",
            role=User.ROLE_ADMIN,
            ward=self.ward,
            is_staff=True,
            is_superuser=True,
        )

        login_response = self.client.post(
            reverse("auth-login"),
            {"username": unenrolled_admin.username, "password": self.password},
            format="json",
        )
        setup_response = self.client.post(
            reverse("auth-2fa-setup"),
            {"token": login_response.data["temp_token"]},
            format="json",
        )

        confirm_response = self.client.post(
            reverse("auth-2fa-setup-confirm"),
            {
                "token": login_response.data["temp_token"],
                "code": generate_current_totp_code(setup_response.data["manual_entry_key"]),
            },
            format="json",
        )

        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", confirm_response.data)
        self.assertIn("refresh", confirm_response.data)
        cookie = confirm_response.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
        self.assertIsNotNone(cookie)
        self.assertEqual(cookie.value, confirm_response.data["refresh"])
        unenrolled_admin.refresh_from_db()
        self.assertTrue(unenrolled_admin.is_totp_enabled)

    def test_authenticated_optional_user_can_complete_two_factor_enrollment(self):
        analyst = self._create_user(
            username="analyst_setup",
            role=User.ROLE_ANALYST,
            ward=self.ward,
        )
        self.authenticate(analyst.username)

        setup_response = self.client.post(reverse("auth-2fa-setup"), {}, format="json")
        self.assertEqual(setup_response.status_code, status.HTTP_200_OK)

        confirm_response = self.client.post(
            reverse("auth-2fa-setup-confirm"),
            {"code": generate_current_totp_code(setup_response.data["manual_entry_key"])},
            format="json",
        )

        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertTrue(confirm_response.data["enrollment_completed"])
        self.assertTrue(confirm_response.data["user"]["is_totp_enabled"])

    def test_verify_2fa_returns_tokens_for_valid_code(self):
        secret = self.admin_user.totp_secret

        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )

        verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": login_response.data["temp_token"],
                "code": generate_current_totp_code(secret),
            },
            format="json",
        )

        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", verify_response.data)
        self.assertIn("refresh", verify_response.data)
        self.assertFalse(verify_response.data["requires_2fa"])
        self.assertEqual(verify_response.data["user"]["role"], User.ROLE_ADMIN)
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_2FA_VERIFIED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                target_user=self.admin_user,
            ).exists()
        )

    def test_verify_2fa_rejects_invalid_code(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )

        verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": login_response.data["temp_token"],
                "code": "000000",
            },
            format="json",
        )

        self.assertEqual(verify_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(verify_response.data["detail"], "Invalid or expired code. Please try again.")
        token_record = PreAuthToken.objects.get(token=login_response.data["temp_token"])
        self.assertIsNone(token_record.used_at)
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_2FA_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                target_user=self.admin_user,
            ).exists()
        )

    @override_settings(
        AUTH_2FA_FAILURE_LIMIT=2,
        AUTH_2FA_FAILURE_WINDOW_SECONDS=300,
        AUTH_2FA_COOLDOWN_SECONDS=300,
    )
    def test_verify_2fa_enforces_temporary_cooldown_after_repeated_failures(self):
        cache.clear()
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )
        token = login_response.data["temp_token"]

        first_response = self.client.post(
            reverse("auth-verify-2fa"),
            {"token": token, "code": "000000"},
            format="json",
        )
        second_response = self.client.post(
            reverse("auth-verify-2fa"),
            {"token": token, "code": "000000"},
            format="json",
        )
        cooldown_response = self.client.post(
            reverse("auth-verify-2fa"),
            {"token": token, "code": generate_current_totp_code(self.admin_user.totp_secret)},
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(second_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(cooldown_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(cooldown_response.data["detail"], "Too many verification attempts. Please wait and try again.")

        cooldown_event = AuthAuditEvent.objects.filter(
            event_type=AuthAuditEvent.EVENT_2FA_FAILED,
            status=AuthAuditEvent.STATUS_FAILED,
            metadata__reason="cooldown_active",
        ).latest("created_at")
        self.assertEqual(cooldown_event.target_user, self.admin_user)

    def test_verify_2fa_rejects_invalid_or_expired_temp_token(self):
        response = self.client.post(
            reverse("auth-verify-2fa"),
            {"token": "not-a-real-token", "code": "123456"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Invalid or expired 2FA token.")

    def test_login_rejects_invalid_password(self):
        cache.clear()
        response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": "wrong-password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data["detail"], "Unable to sign in with those credentials.")
        event = AuthAuditEvent.objects.filter(
            event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
            status=AuthAuditEvent.STATUS_FAILED,
        ).latest("created_at")
        self.assertEqual(event.metadata["username"], self.admin_user.username)
        self.assertEqual(event.metadata["reason"], "invalid_credentials")

    @override_settings(
        AUTH_LOGIN_FAILURE_LIMIT=2,
        AUTH_LOGIN_FAILURE_WINDOW_SECONDS=300,
        AUTH_LOGIN_COOLDOWN_SECONDS=300,
    )
    def test_login_enforces_temporary_cooldown_after_repeated_failures(self):
        cache.clear()

        first_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": "wrong-password"},
            format="json",
        )
        second_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": "wrong-password"},
            format="json",
        )
        cooldown_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(second_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(cooldown_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(cooldown_response.data["detail"], "Too many sign-in attempts. Please wait and try again.")

        cooldown_event = AuthAuditEvent.objects.filter(
            event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
            status=AuthAuditEvent.STATUS_FAILED,
            metadata__reason="cooldown_active",
        ).latest("created_at")
        self.assertEqual(cooldown_event.metadata["username"], self.admin_user.username)

    @override_settings(
        AUTH_LOGIN_TURNSTILE_ENABLED=True,
        AUTH_LOGIN_TURNSTILE_THRESHOLD=1,
        AUTH_LOGIN_FAILURE_LIMIT=5,
        AUTH_LOGIN_FAILURE_WINDOW_SECONDS=300,
        AUTH_LOGIN_COOLDOWN_SECONDS=300,
    )
    def test_login_requires_turnstile_after_repeated_failures(self):
        cache.clear()

        first_response = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": "wrong-password"},
            format="json",
        )
        challenge_response = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )

        self.assertEqual(first_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(challenge_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            challenge_response.data["detail"],
            "Additional verification is required. Complete the challenge and try again.",
        )

        challenge_event = AuthAuditEvent.objects.filter(
            event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
            status=AuthAuditEvent.STATUS_FAILED,
            metadata__reason="turnstile_required",
        ).latest("created_at")
        self.assertEqual(challenge_event.metadata["username"], self.chv_user.username)

    @override_settings(
        AUTH_LOGIN_TURNSTILE_ENABLED=True,
        AUTH_LOGIN_TURNSTILE_THRESHOLD=1,
        AUTH_LOGIN_FAILURE_LIMIT=5,
        AUTH_LOGIN_FAILURE_WINDOW_SECONDS=300,
        AUTH_LOGIN_COOLDOWN_SECONDS=300,
    )
    @patch("accounts.views.verify_turnstile_token")
    def test_login_rejects_invalid_turnstile_after_repeated_failures(self, mock_verify_turnstile):
        cache.clear()
        mock_verify_turnstile.return_value = TurnstileVerificationResult(
            success=False,
            error_codes=("invalid-input-response",),
        )

        self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": "wrong-password"},
            format="json",
        )
        challenge_response = self.client.post(
            reverse("auth-login"),
            {
                "username": self.chv_user.username,
                "password": self.password,
                "turnstile_token": "bad-token",
            },
            format="json",
        )

        self.assertEqual(challenge_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            challenge_response.data["detail"],
            "Additional verification is required. Complete the challenge and try again.",
        )
        mock_verify_turnstile.assert_called_once()

        challenge_event = AuthAuditEvent.objects.filter(
            event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
            status=AuthAuditEvent.STATUS_FAILED,
            metadata__reason="turnstile_failed",
        ).latest("created_at")
        self.assertEqual(challenge_event.metadata["username"], self.chv_user.username)
        self.assertEqual(challenge_event.metadata["turnstile_error_codes"], ["invalid-input-response"])

    @override_settings(
        AUTH_LOGIN_TURNSTILE_ENABLED=True,
        AUTH_LOGIN_TURNSTILE_THRESHOLD=1,
        AUTH_LOGIN_FAILURE_LIMIT=5,
        AUTH_LOGIN_FAILURE_WINDOW_SECONDS=300,
        AUTH_LOGIN_COOLDOWN_SECONDS=300,
    )
    @patch("accounts.views.verify_turnstile_token")
    def test_login_accepts_valid_turnstile_after_repeated_failures(self, mock_verify_turnstile):
        cache.clear()
        mock_verify_turnstile.return_value = TurnstileVerificationResult(success=True, hostname="localhost")

        self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": "wrong-password"},
            format="json",
        )
        challenge_response = self.client.post(
            reverse("auth-login"),
            {
                "username": self.chv_user.username,
                "password": self.password,
                "turnstile_token": "good-token",
            },
            format="json",
        )

        self.assertEqual(challenge_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", challenge_response.data)
        mock_verify_turnstile.assert_called_once()

    def test_me_requires_authentication(self):
        response = self.client.get(reverse("auth-me"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_current_user(self):
        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("auth-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], self.admin_user.username)
        self.assertEqual(response.data["role"], User.ROLE_ADMIN)
        self.assertEqual(response.data["scope_type"], "BROAD")
        self.assertIsNone(response.data["scope_ward_id"])
        self.assertEqual(response.data["two_factor_policy"], "REQUIRED")
        self.assertTrue(response.data["is_totp_enabled"])
        self.assertEqual(response.data["theme_preference"], User.THEME_SYSTEM)

    def test_me_returns_ward_scope_for_supervisor(self):
        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("auth-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], User.ROLE_SUPERVISOR)
        self.assertEqual(response.data["scope_type"], "WARD")
        self.assertEqual(response.data["scope_ward_id"], self.other_ward.id)
        self.assertEqual(response.data["two_factor_policy"], "REQUIRED")

    def test_me_allows_authenticated_theme_preference_updates(self):
        self.authenticate(self.analyst_user.username)

        response = self.client.patch(
            reverse("auth-me"),
            {"theme_preference": User.THEME_DARK},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["theme_preference"], User.THEME_DARK)
        self.analyst_user.refresh_from_db()
        self.assertEqual(self.analyst_user.theme_preference, User.THEME_DARK)

    def test_me_rejects_invalid_theme_preference_updates(self):
        self.authenticate(self.analyst_user.username)

        response = self.client.patch(
            reverse("auth-me"),
            {"theme_preference": "MIDNIGHT"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("theme_preference", response.data)

    def test_me_returns_no_two_factor_requirement_for_chv(self):
        self.authenticate(self.chv_user.username)
        response = self.client.get(reverse("auth-me"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], User.ROLE_CHV)
        self.assertEqual(response.data["two_factor_policy"], "NONE")

    def test_session_returns_authenticated_user_for_valid_access_token(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")
        response = self.client.get(reverse("auth-session"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["authenticated"])
        self.assertEqual(response.data["session_source"], "access")
        self.assertEqual(response.data["user"]["id"], self.chv_user.id)
        self.assertIsNone(response.data["access"])

    def test_session_bootstraps_from_refresh_cookie(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )
        verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": login_response.data["temp_token"],
                "code": generate_current_totp_code(self.admin_user.totp_secret),
            },
            format="json",
        )

        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = verify_response.data["refresh"]
        response = self.client.get(reverse("auth-session"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["authenticated"])
        self.assertEqual(response.data["session_source"], "refresh")
        self.assertEqual(response.data["user"]["id"], self.admin_user.id)
        self.assertIn("access", response.data)
        self.assertTrue(response.data["access"])

    def test_session_returns_unauthenticated_without_session(self):
        response = self.client.get(reverse("auth-session"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["authenticated"])
        self.assertIsNone(response.data["user"])
        self.assertIsNone(response.data["access"])

    def test_session_clears_invalid_refresh_cookie(self):
        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = "bad-refresh-token"
        response = self.client.get(reverse("auth-session"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["authenticated"])
        self.assertEqual(response.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value, "")

    def test_logout_blacklists_refresh_token(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )
        verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": login_response.data["temp_token"],
                "code": generate_current_totp_code(self.admin_user.totp_secret),
            },
            format="json",
        )
        refresh = verify_response.data["refresh"]
        access = verify_response.data["access"]

        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        logout_response = self.client.post(reverse("auth-logout"), {}, format="json")
        self.assertEqual(logout_response.status_code, status.HTTP_205_RESET_CONTENT)

        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh
        refresh_response = self.client.post(reverse("auth-refresh"), {}, format="json")
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_LOGOUT,
                status=AuthAuditEvent.STATUS_SUCCESS,
                target_user=self.admin_user,
            ).exists()
        )

    def test_logout_accepts_refresh_cookie_and_clears_it(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )
        verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": login_response.data["temp_token"],
                "code": generate_current_totp_code(self.admin_user.totp_secret),
            },
            format="json",
        )
        access = verify_response.data["access"]
        refresh = verify_response.data["refresh"]

        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        logout_response = self.client.post(reverse("auth-logout"), {}, format="json")

        self.assertEqual(logout_response.status_code, status.HTTP_205_RESET_CONTENT)
        self.assertEqual(logout_response.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value, "")

        refresh_response = self.client.post(reverse("auth-refresh"), {}, format="json")
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_rotates_token(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )
        verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": login_response.data["temp_token"],
                "code": generate_current_totp_code(self.admin_user.totp_secret),
            },
            format="json",
        )
        refresh = verify_response.data["refresh"]
        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh

        refresh_response = self.client.post(reverse("auth-refresh"), {}, format="json")
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        self.assertIn("refresh", refresh_response.data)
        self.assertNotEqual(refresh_response.data["refresh"], refresh)

        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh
        replay_response = self.client.post(reverse("auth-refresh"), {}, format="json")
        self.assertEqual(replay_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_REFRESH_SUCCESS,
                status=AuthAuditEvent.STATUS_SUCCESS,
                target_user=self.admin_user,
            ).exists()
        )
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_REFRESH_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
            ).exists()
        )

    def test_refresh_accepts_refresh_cookie_without_request_body(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )
        verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": login_response.data["temp_token"],
                "code": generate_current_totp_code(self.admin_user.totp_secret),
            },
            format="json",
        )

        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = verify_response.data["refresh"]
        refresh_response = self.client.post(reverse("auth-refresh"), {}, format="json")

        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        self.assertIn("access", refresh_response.data)
        self.assertIn("refresh", refresh_response.data)
        cookie = refresh_response.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
        self.assertIsNotNone(cookie)
        self.assertEqual(cookie.value, refresh_response.data["refresh"])

    @override_settings(
        AUTH_REFRESH_FAILURE_LIMIT=2,
        AUTH_REFRESH_FAILURE_WINDOW_SECONDS=300,
        AUTH_REFRESH_COOLDOWN_SECONDS=300,
    )
    def test_refresh_enforces_temporary_cooldown_after_repeated_failures(self):
        cache.clear()

        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = "bad-refresh-token"
        first_response = self.client.post(reverse("auth-refresh"), {}, format="json")
        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = "bad-refresh-token"
        second_response = self.client.post(reverse("auth-refresh"), {}, format="json")
        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = "bad-refresh-token"
        cooldown_response = self.client.post(reverse("auth-refresh"), {}, format="json")

        self.assertEqual(first_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(second_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(cooldown_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(cooldown_response.data["detail"], "Too many token refresh attempts. Please wait and try again.")

        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_REFRESH_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                metadata__reason="cooldown_active",
            ).exists()
        )

    def test_register_requires_admin(self):
        self.authenticate(self.chv_user.username)
        response = self.client.post(
            reverse("auth-register"),
            {
                "username": "new_user",
                "email": "new_user@example.com",
                "full_name": "New User",
                "phone_number": "+254722000001",
                "role": User.ROLE_CHV,
                "ward": self.ward.id,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_register_user(self):
        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("auth-register"),
            {
                "username": "field_chv",
                "email": "field_chv@example.com",
                "full_name": "Field CHV",
                "phone_number": "+254722000002",
                "role": User.ROLE_CHV,
                "ward": self.ward.id,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="field_chv").exists())
        created_user = User.objects.get(username="field_chv")
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_USER_CREATED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                actor=self.admin_user,
                target_user=created_user,
            ).exists()
        )

    def test_admin_register_requires_strong_password(self):
        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("auth-register"),
            {
                "username": "weak_user",
                "email": "weak_user@example.com",
                "full_name": "Weak User",
                "phone_number": "+254722000003",
                "role": User.ROLE_ANALYST,
                "password": "12345678",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_admin_register_requires_ward_for_chv(self):
        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("auth-register"),
            {
                "username": "wardless_chv",
                "email": "wardless_chv@example.com",
                "full_name": "Wardless CHV",
                "phone_number": "+254722000004",
                "role": User.ROLE_CHV,
                "password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ward", response.data)

    def test_admin_register_normalizes_email(self):
        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("auth-register"),
            {
                "username": "email_user",
                "email": "Email_User@Example.COM",
                "full_name": "Email User",
                "phone_number": "+254722000005",
                "role": User.ROLE_ANALYST,
                "password": "StrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            User.objects.get(username="email_user").email,
            "email_user@example.com",
        )

    def test_change_password_updates_credentials_and_blacklists_refresh_tokens(self):
        response = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )
        refresh = response.data["refresh"]
        access = response.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        change_response = self.client.post(
            reverse("auth-change-password"),
            {
                "current_password": self.password,
                "new_password": "NewStrongPass123!",
            },
            format="json",
        )

        self.assertEqual(change_response.status_code, status.HTTP_200_OK)

        old_login = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )
        self.assertEqual(old_login.status_code, status.HTTP_401_UNAUTHORIZED)

        new_login = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": "NewStrongPass123!"},
            format="json",
        )
        self.assertEqual(new_login.status_code, status.HTTP_200_OK)

        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh
        refresh_response = self.client.post(
            reverse("auth-refresh"),
            {},
            format="json",
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_PASSWORD_CHANGED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                actor=self.chv_user,
                target_user=self.chv_user,
            ).exists()
        )

    def test_change_password_requires_correct_current_password(self):
        self.authenticate(self.chv_user.username)
        response = self.client.post(
            reverse("auth-change-password"),
            {
                "current_password": "wrong-password",
                "new_password": "NewStrongPass123!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Validation error.")
        self.assertIn("errors", response.data)
        self.assertIn("current_password", response.data)

    @patch("accounts.views.send_password_reset_email")
    def test_password_reset_request_returns_generic_success_and_sends_email_for_existing_user(self, mock_send):
        response = self.client.post(
            reverse("auth-password-reset-request"),
            {"identifier": self.chv_user.email},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("will be sent", response.data["detail"])
        self.assertEqual(PasswordResetToken.objects.filter(user=self.chv_user).count(), 1)
        token_record = PasswordResetToken.objects.get(user=self.chv_user)
        self.assertTrue(token_record.is_usable)
        mock_send.assert_called_once()

    @patch("accounts.views.send_password_reset_email")
    def test_password_reset_request_does_not_leak_unknown_account(self, mock_send):
        response = self.client.post(
            reverse("auth-password-reset-request"),
            {"identifier": "unknown-user@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("will be sent", response.data["detail"])
        self.assertEqual(PasswordResetToken.objects.count(), 0)
        mock_send.assert_not_called()

    def test_password_reset_confirm_changes_password_invalidates_refresh_and_marks_token_used(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )
        refresh = login_response.data["refresh"]
        token_record = PasswordResetToken.objects.create(
            user=self.chv_user,
            token="reset-token-123",
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            reverse("auth-password-reset-confirm"),
            {"token": token_record.token, "new_password": "ResetStrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        token_record.refresh_from_db()
        self.assertIsNotNone(token_record.used_at)

        old_login = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )
        self.assertEqual(old_login.status_code, status.HTTP_401_UNAUTHORIZED)

        new_login = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": "ResetStrongPass123!"},
            format="json",
        )
        self.assertEqual(new_login.status_code, status.HTTP_200_OK)

        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh
        refresh_response = self.client.post(
            reverse("auth-refresh"),
            {},
            format="json",
        )
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_PASSWORD_RESET_COMPLETED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                target_user=self.chv_user,
            ).exists()
        )

    def test_password_reset_confirm_get_validates_usable_token(self):
        token_record = PasswordResetToken.objects.create(
            user=self.chv_user,
            token="valid-reset-token-123",
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get(
            reverse("auth-password-reset-confirm"),
            {"token": token_record.token},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["valid"])

    def test_password_reset_confirm_rejects_invalid_or_expired_token(self):
        expired = PasswordResetToken.objects.create(
            user=self.chv_user,
            token="expired-token-123",
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        invalid_response = self.client.post(
            reverse("auth-password-reset-confirm"),
            {"token": "not-a-real-token", "new_password": "ResetStrongPass123!"},
            format="json",
        )
        self.assertEqual(invalid_response.status_code, status.HTTP_400_BAD_REQUEST)

        expired_response = self.client.post(
            reverse("auth-password-reset-confirm"),
            {"token": expired.token, "new_password": "ResetStrongPass123!"},
            format="json",
        )
        self.assertEqual(expired_response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_get_response = self.client.get(
            reverse("auth-password-reset-confirm"),
            {"token": "not-a-real-token"},
        )
        self.assertEqual(invalid_get_response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("accounts.views.send_access_request_acknowledgement")
    def test_access_request_submission_creates_record_and_sends_acknowledgement(self, mock_send):
        response = self.client.post(
            reverse("access-request"),
            {
                "full_name": "County Analyst",
                "phone_number": "+254711000321",
                "county": self.ward.county,
                "administrative_ward": self.ward.name,
                "organization": "Migori County Health Department",
                "desired_role": User.ROLE_ANALYST,
                "contact_email": "analyst@example.com",
                "message": "Requesting read-only county-wide dashboard access.",
                "website": "",
                "client_started_at_ms": started_at_ms(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["review_status"], AccessRequest.STATUS_PENDING)
        self.assertEqual(AccessRequest.objects.count(), 1)
        access_request = AccessRequest.objects.get()
        self.assertEqual(access_request.contact_email, "analyst@example.com")
        self.assertEqual(access_request.county, self.ward.county)
        self.assertEqual(access_request.administrative_ward, self.ward.name)
        self.assertEqual(access_request.review_status, AccessRequest.STATUS_PENDING)
        self.assertEqual(access_request.submitted_from_ip, self.client.defaults["REMOTE_ADDR"])
        self.assertFalse(access_request.challenge_verified)
        mock_send.assert_called_once_with(access_request)

    def test_access_request_submission_validates_required_fields(self):
        response = self.client.post(
            reverse("access-request"),
            {
                "full_name": "",
                "county": "",
                "administrative_ward": "",
                "desired_role": User.ROLE_ANALYST,
                "contact_email": "not-an-email",
                "website": "",
                "client_started_at_ms": started_at_ms(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("errors", response.data)

    def test_access_request_submission_rejects_invalid_phone_number(self):
        response = self.client.post(
            reverse("access-request"),
            {
                "full_name": "County Analyst",
                "phone_number": "12345",
                "county": self.ward.county,
                "administrative_ward": self.ward.name,
                "desired_role": User.ROLE_ANALYST,
                "contact_email": "analyst@example.com",
                "website": "",
                "client_started_at_ms": started_at_ms(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("errors", response.data)
        self.assertIn("phone_number", response.data["errors"])

    def test_access_request_submission_rejects_ward_county_mismatch(self):
        response = self.client.post(
            reverse("access-request"),
            {
                "full_name": "County Analyst",
                "phone_number": "+254711000321",
                "county": "Kisumu",
                "administrative_ward": self.ward.name,
                "desired_role": User.ROLE_ANALYST,
                "contact_email": "analyst@example.com",
                "website": "",
                "client_started_at_ms": started_at_ms(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("errors", response.data)
        self.assertIn("administrative_ward", response.data["errors"])

    @patch("accounts.views.send_access_request_acknowledgement")
    def test_access_request_duplicate_submission_is_suppressed(self, mock_send):
        AccessRequest.objects.create(
            full_name="County Analyst",
            phone_number="+254711000321",
            county=self.ward.county,
            administrative_ward=self.ward.name,
            organization="Migori County Health Department",
            desired_role=User.ROLE_ANALYST,
            contact_email="analyst@example.com",
            message="Requesting read-only county-wide dashboard access.",
        )

        response = self.client.post(
            reverse("access-request"),
            {
                "full_name": "County Analyst",
                "phone_number": "0711000321",
                "county": self.ward.county,
                "administrative_ward": self.ward.name,
                "organization": "Migori County Health Department",
                "desired_role": User.ROLE_ANALYST,
                "contact_email": "analyst@example.com",
                "message": "Requesting read-only county-wide dashboard access.",
                "website": "",
                "client_started_at_ms": started_at_ms(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(AccessRequest.objects.count(), 1)
        mock_send.assert_not_called()

    def test_access_request_submission_rejects_honeypot_population(self):
        response = self.client.post(
            reverse("access-request"),
            {
                "full_name": "County Analyst",
                "phone_number": "+254711000321",
                "county": self.ward.county,
                "administrative_ward": self.ward.name,
                "desired_role": User.ROLE_ANALYST,
                "contact_email": "analyst@example.com",
                "website": "https://spam.example.com",
                "client_started_at_ms": started_at_ms(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_access_request_submission_rejects_suspiciously_fast_post(self):
        response = self.client.post(
            reverse("access-request"),
            {
                "full_name": "County Analyst",
                "phone_number": "+254711000321",
                "county": self.ward.county,
                "administrative_ward": self.ward.name,
                "desired_role": User.ROLE_ANALYST,
                "contact_email": "analyst@example.com",
                "website": "",
                "client_started_at_ms": started_at_ms(offset_ms=100),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    @override_settings(ACCESS_REQUEST_TURNSTILE_ENABLED=True, TURNSTILE_SECRET_KEY="test-secret")
    @patch("accounts.views.send_access_request_acknowledgement")
    @patch("accounts.views.verify_turnstile_token")
    def test_access_request_submission_accepts_valid_turnstile_token(self, mock_verify_turnstile, mock_send):
        mock_verify_turnstile.return_value = TurnstileVerificationResult(success=True, hostname="localhost")

        response = self.client.post(
            reverse("access-request"),
            {
                "full_name": "County Analyst",
                "phone_number": "+254711000321",
                "county": self.ward.county,
                "administrative_ward": self.ward.name,
                "desired_role": User.ROLE_ANALYST,
                "contact_email": "analyst@example.com",
                "website": "",
                "client_started_at_ms": started_at_ms(),
                "turnstile_token": "test-token",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_verify_turnstile.assert_called_once()
        mock_send.assert_called_once()
        self.assertTrue(AccessRequest.objects.get().challenge_verified)

    @override_settings(ACCESS_REQUEST_TURNSTILE_ENABLED=True, TURNSTILE_SECRET_KEY="test-secret")
    def test_access_request_submission_rejects_missing_turnstile_token_when_enabled(self):
        response = self.client.post(
            reverse("access-request"),
            {
                "full_name": "County Analyst",
                "phone_number": "+254711000321",
                "county": self.ward.county,
                "administrative_ward": self.ward.name,
                "desired_role": User.ROLE_ANALYST,
                "contact_email": "analyst@example.com",
                "website": "",
                "client_started_at_ms": started_at_ms(),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Challenge verification failed. Please try again.")

    @override_settings(ACCESS_REQUEST_TURNSTILE_ENABLED=True, TURNSTILE_SECRET_KEY="test-secret")
    @patch("accounts.views.verify_turnstile_token")
    def test_access_request_submission_rejects_invalid_turnstile_token(self, mock_verify_turnstile):
        mock_verify_turnstile.return_value = TurnstileVerificationResult(
            success=False,
            error_codes=("invalid-input-response",),
            hostname="localhost",
        )

        response = self.client.post(
            reverse("access-request"),
            {
                "full_name": "County Analyst",
                "phone_number": "+254711000321",
                "county": self.ward.county,
                "administrative_ward": self.ward.name,
                "desired_role": User.ROLE_ANALYST,
                "contact_email": "analyst@example.com",
                "website": "",
                "client_started_at_ms": started_at_ms(),
                "turnstile_token": "bad-token",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Challenge verification failed. Please try again.")

    def test_access_request_list_requires_admin(self):
        AccessRequest.objects.create(
            full_name="County Analyst",
            county="Migori",
            administrative_ward="Suna East",
            organization="Migori County",
            desired_role=User.ROLE_ANALYST,
            contact_email="analyst@example.com",
            message="Need read-only dashboard access.",
        )

        self.authenticate(self.chv_user.username)
        response = self.client.get(reverse("access-request-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_access_requests(self):
        AccessRequest.objects.create(
            full_name="County Analyst",
            county="Migori",
            administrative_ward="Suna East",
            organization="Migori County",
            desired_role=User.ROLE_ANALYST,
            contact_email="analyst@example.com",
            message="Need read-only dashboard access.",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("access-request-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["review_status"], AccessRequest.STATUS_PENDING)
        self.assertEqual(results[0]["county"], "Migori")
        self.assertEqual(results[0]["duplicate_email_count"], 0)
        self.assertEqual(results[0]["duplicate_phone_count"], 0)
        self.assertEqual(results[0]["duplicate_ip_count"], 0)
        self.assertEqual(results[0]["pending_related_count"], 0)
        self.assertEqual(results[0]["review_flags"], [])

    def test_admin_list_exposes_duplicate_review_signals(self):
        AccessRequest.objects.create(
            full_name="County Analyst",
            phone_number="+254711000321",
            county="Migori",
            administrative_ward="Suna East",
            organization="Migori County",
            desired_role=User.ROLE_ANALYST,
            contact_email="analyst@example.com",
            message="Need read-only dashboard access.",
            submitted_from_ip="127.0.0.50",
        )
        AccessRequest.objects.create(
            full_name="County Analyst Repeat",
            phone_number="+254711000321",
            county="Migori",
            administrative_ward="North Kamagambo",
            organization="Migori County",
            desired_role=User.ROLE_ANALYST,
            contact_email="analyst@example.com",
            message="Following up on my request.",
            submitted_from_ip="127.0.0.50",
            challenge_verified=True,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("access-request-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(item["duplicate_email_count"] >= 1 for item in results))
        self.assertTrue(all(item["duplicate_phone_count"] >= 1 for item in results))
        self.assertTrue(all(item["duplicate_ip_count"] >= 1 for item in results))
        self.assertTrue(all(item["pending_related_count"] >= 1 for item in results))
        self.assertTrue(all("email_reuse" in item["review_flags"] for item in results))
        self.assertTrue(all("phone_reuse" in item["review_flags"] for item in results))
        self.assertTrue(all("ip_reuse" in item["review_flags"] for item in results))
        self.assertTrue(all("related_pending_requests" in item["review_flags"] for item in results))
        self.assertTrue(any("challenge_verified" in item["review_flags"] for item in results))

    @patch("accounts.views.send_access_request_decision")
    def test_admin_can_approve_access_request(self, mock_send):
        access_request = AccessRequest.objects.create(
            full_name="County Analyst",
            county="Migori",
            administrative_ward="Suna East",
            organization="Migori County",
            desired_role=User.ROLE_ANALYST,
            contact_email="analyst@example.com",
            message="Need read-only dashboard access.",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("access-request-approve", kwargs={"request_id": access_request.id}),
            {"message": "Your request has been approved for onboarding."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        access_request.refresh_from_db()
        self.assertEqual(access_request.review_status, AccessRequest.STATUS_APPROVED)
        self.assertEqual(access_request.decision_message, "Your request has been approved for onboarding.")
        self.assertIsNotNone(access_request.reviewed_at)
        mock_send.assert_called_once()

    @patch("accounts.views.send_access_request_decision")
    def test_admin_can_reject_access_request(self, mock_send):
        access_request = AccessRequest.objects.create(
            full_name="County Analyst",
            county="Migori",
            administrative_ward="Suna East",
            organization="Migori County",
            desired_role=User.ROLE_ANALYST,
            contact_email="analyst@example.com",
            message="Need read-only dashboard access.",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("access-request-reject", kwargs={"request_id": access_request.id}),
            {"message": "We cannot approve this request at this time."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        access_request.refresh_from_db()
        self.assertEqual(access_request.review_status, AccessRequest.STATUS_REJECTED)
        self.assertEqual(access_request.decision_message, "We cannot approve this request at this time.")
        self.assertIsNotNone(access_request.reviewed_at)
        mock_send.assert_called_once()

    @patch("accounts.admin.send_access_request_decision")
    def test_django_admin_sends_decision_email_when_ops_reviews_request(self, mock_send):
        access_request = AccessRequest.objects.create(
            full_name="County Analyst",
            county="Migori",
            administrative_ward="Suna East",
            organization="Migori County",
            desired_role=User.ROLE_ANALYST,
            contact_email="analyst@example.com",
            message="Need read-only dashboard access.",
        )
        admin_site = AdminSite()
        model_admin = AccessRequestAdmin(AccessRequest, admin_site)
        request = RequestFactory().post("/admin/accounts/accessrequest/")
        request.user = self.admin_user

        access_request.review_status = AccessRequest.STATUS_APPROVED
        access_request.decision_message = "Approved for onboarding."
        form = SimpleNamespace(changed_data=["review_status", "decision_message"])

        model_admin.save_model(request, access_request, form, change=True)

        access_request.refresh_from_db()
        self.assertEqual(access_request.review_status, AccessRequest.STATUS_APPROVED)
        self.assertEqual(access_request.decision_message, "Approved for onboarding.")
        self.assertIsNotNone(access_request.reviewed_at)
        mock_send.assert_called_once_with(
            access_request,
            approved=True,
            decision_message="Approved for onboarding.",
        )

    def test_access_request_options_returns_counties_and_wards_for_public_form(self):
        response = self.client.get(reverse("access-request-options"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("counties", response.data)
        self.assertIn("wards", response.data)
        self.assertTrue(any(ward["name"] == self.ward.name for ward in response.data["wards"]))

    @override_settings(
        REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {
                **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
                "access_request": "1/hour",
                "access_request_options": "10/hour",
            },
        }
    )
    def test_access_request_options_are_not_throttled_by_submission_scope(self):
        submit_payload = {
            "full_name": "County Analyst",
            "county": self.ward.county,
            "administrative_ward": self.ward.name,
            "organization": "Migori County",
            "desired_role": User.ROLE_ANALYST,
            "contact_email": "analyst@example.com",
            "message": "Need access.",
        }

        first_submit = self.client.post(reverse("access-request"), submit_payload, format="json")
        self.assertEqual(first_submit.status_code, status.HTTP_201_CREATED)

        second_submit = self.client.post(
            reverse("access-request"),
            {
                **submit_payload,
                "contact_email": "second-analyst@example.com",
            },
            format="json",
        )
        self.assertEqual(second_submit.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        options_response = self.client.get(reverse("access-request-options"))
        self.assertEqual(options_response.status_code, status.HTTP_200_OK)

    def test_admin_can_deactivate_and_reactivate_user(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )
        refresh = login_response.data["refresh"]
        access = login_response.data["access"]

        self.authenticate(self.admin_user.username)
        deactivate_response = self.client.post(
            reverse("auth-user-deactivate", kwargs={"user_id": self.chv_user.id}),
            format="json",
        )
        self.assertEqual(deactivate_response.status_code, status.HTTP_200_OK)

        self.chv_user.refresh_from_db()
        self.assertFalse(self.chv_user.is_active)

        login_after_deactivate = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )
        self.assertEqual(login_after_deactivate.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh
        refresh_after_deactivate = self.client.post(
            reverse("auth-refresh"),
            {},
            format="json",
        )
        self.assertEqual(refresh_after_deactivate.status_code, status.HTTP_401_UNAUTHORIZED)

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        me_after_deactivate = self.client.get(reverse("auth-me"))
        self.assertEqual(me_after_deactivate.status_code, status.HTTP_401_UNAUTHORIZED)

        self.authenticate(self.admin_user.username)
        reactivate_response = self.client.post(
            reverse("auth-user-reactivate", kwargs={"user_id": self.chv_user.id}),
            format="json",
        )
        self.assertEqual(reactivate_response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_USER_DEACTIVATED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                actor=self.admin_user,
                target_user=self.chv_user,
            ).exists()
        )
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_USER_REACTIVATED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                actor=self.admin_user,
                target_user=self.chv_user,
            ).exists()
        )

        reactivated_login = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )
        self.assertEqual(reactivated_login.status_code, status.HTTP_200_OK)

    def test_non_admin_cannot_manage_user_activation(self):
        self.authenticate(self.supervisor_user.username)
        deactivate_response = self.client.post(
            reverse("auth-user-deactivate", kwargs={"user_id": self.chv_user.id}),
            format="json",
        )
        reactivate_response = self.client.post(
            reverse("auth-user-reactivate", kwargs={"user_id": self.chv_user.id}),
            format="json",
        )

        self.assertEqual(deactivate_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(reactivate_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_list_auth_audit_events(self):
        self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("auth-audit-events"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)
        results = get_results(response)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["event_type"], AuthAuditEvent.EVENT_LOGIN_SUCCESS)

    def test_admin_can_filter_auth_audit_events(self):
        self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )
        self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": "wrong-password"},
            format="json",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(
            reverse("auth-audit-events"),
            {"status": AuthAuditEvent.STATUS_FAILED},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(all(item["status"] == AuthAuditEvent.STATUS_FAILED for item in results))

    def test_non_admin_cannot_list_auth_audit_events(self):
        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("auth-audit-events"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_get_auth_audit_summary(self):
        self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )
        self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": "wrong-password"},
            format="json",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("auth-audit-summary"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["total_events"], 2)
        self.assertGreaterEqual(response.data["failed_events"], 1)
        self.assertTrue(any(item["event_type"] == AuthAuditEvent.EVENT_LOGIN_SUCCESS for item in response.data["by_type"]))
        self.assertTrue(any(item["event_type"] == AuthAuditEvent.EVENT_LOGIN_FAILED for item in response.data["by_type"]))


class RateLimitTestCase(AuthenticatedAPITestCase):
    def test_scoped_throttling_is_enabled_globally(self):
        throttle_class_names = {
            f"{klass.__module__}.{klass.__name__}" for klass in api_settings.DEFAULT_THROTTLE_CLASSES
        }
        self.assertIn("rest_framework.throttling.ScopedRateThrottle", throttle_class_names)

    def test_auth_and_ussd_views_have_expected_throttle_scopes(self):
        self.assertEqual(LoginAPIView.throttle_scope, "auth_login")
        self.assertEqual(RefreshAPIView.throttle_scope, "auth_refresh")
        self.assertEqual(LogoutAPIView.throttle_scope, "auth_write")
        self.assertEqual(ChangePasswordAPIView.throttle_scope, "auth_write")
        self.assertEqual(DeactivateUserAPIView.throttle_scope, "auth_write")
        self.assertEqual(ReactivateUserAPIView.throttle_scope, "auth_write")
        self.assertEqual(USSDMenuAPIView.throttle_scope, "public_ussd")


class ApiSchemaTestCase(APITestCase):
    def test_openapi_renderer_is_available(self):
        self.assertEqual(JSONOpenAPIRenderer.media_type, "application/vnd.oai.openapi+json")

    def test_versioned_schema_endpoint_returns_openapi_document(self):
        response = self.client.get(reverse("api-schema-v1"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["info"]["title"], "CCHIS Backend API")
        self.assertIn("/api/v1/wards/", response.data["paths"])
        self.assertIn("/api/v1/auth/login/", response.data["paths"])
        self.assertIn("/api/v1/ussd/menu/", response.data["paths"])

    def test_route_names_resolve_to_v1_paths(self):
        self.assertEqual(reverse("ward-list"), "/api/v1/wards/")
        self.assertEqual(reverse("auth-login"), "/api/v1/auth/login/")

    def test_legacy_unversioned_paths_are_not_available(self):
        self.assertEqual(self.client.get("/api/wards/").status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.post("/api/auth/login/", {}, format="json").status_code, status.HTTP_404_NOT_FOUND)


class ProxyBoundarySafetyTestCase(APITestCase):
    @override_settings(TRUST_X_FORWARDED_FOR=False)
    def test_client_ip_defaults_to_remote_addr_when_forwarded_for_not_trusted(self):
        request = SimpleNamespace(
            META={
                "REMOTE_ADDR": "10.0.0.5",
                "HTTP_X_FORWARDED_FOR": "198.51.100.24, 10.0.0.5",
            }
        )

        self.assertEqual(get_client_ip(request), "10.0.0.5")

    @override_settings(TRUST_X_FORWARDED_FOR=True)
    def test_client_ip_uses_forwarded_for_when_proxy_is_trusted(self):
        request = SimpleNamespace(
            META={
                "REMOTE_ADDR": "10.0.0.5",
                "HTTP_X_FORWARDED_FOR": "198.51.100.24, 10.0.0.5",
            }
        )

        self.assertEqual(get_client_ip(request), "198.51.100.24")


class IdentifierPolicyTestCase(AuthenticatedAPITestCase):
    def test_ward_and_facility_receive_public_ids(self):
        self.assertIsNotNone(self.ward.public_id)
        self.assertIsNotNone(self.other_ward.public_id)
        self.assertNotEqual(self.ward.public_id, self.other_ward.public_id)
        self.assertIsNotNone(self.health_facility.public_id)

    def test_ward_maps_to_canonical_reference(self):
        canonical = ward_to_canonical_ref(self.ward)

        self.assertEqual(canonical.entity_type, "ward")
        self.assertEqual(canonical.public_id, str(self.ward.public_id))
        self.assertEqual(canonical.name, self.ward.name)
        self.assertEqual(canonical.county, self.ward.county)

    def test_facility_maps_to_canonical_reference(self):
        canonical = facility_to_canonical_ref(self.health_facility)

        self.assertEqual(canonical.entity_type, "health_facility")
        self.assertEqual(canonical.public_id, str(self.health_facility.public_id))
        self.assertEqual(canonical.facility_code, self.health_facility.facility_code)
        self.assertEqual(canonical.ward_public_id, str(self.ward.public_id))

    def test_riskscore_maps_to_canonical_record(self):
        canonical = riskscore_to_canonical_record(self.risk_score)

        self.assertEqual(canonical.entity_type, "risk_score")
        self.assertEqual(canonical.ward_public_id, str(self.ward.public_id))
        self.assertEqual(canonical.model_run_id, self.model_run.id)
        self.assertEqual(canonical.risk_level, self.risk_score.risk_level)
        self.assertEqual(canonical.model_version, self.risk_score.model_version)

    def test_alert_maps_to_canonical_record(self):
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Dashboard alert",
            status=Alert.STATUS_DELIVERED,
            delivery_backend="internal-dashboard",
            attempt_count=1,
            max_attempts=1,
            sent_at=timezone.now(),
        )

        canonical = alert_to_canonical_record(alert)

        self.assertEqual(canonical.entity_type, "alert")
        self.assertEqual(canonical.ward_public_id, str(self.ward.public_id))
        self.assertEqual(canonical.delivery_backend, "internal-dashboard")
        self.assertEqual(canonical.risk_score_id, self.risk_score.id)

    def test_canonical_export_envelope_wraps_internal_record(self):
        record = ward_to_canonical_ref(self.ward)

        envelope = canonical_export_envelope(
            source_system="dhis2",
            entity_name="ward",
            record=record,
        )

        self.assertEqual(envelope["source_system"], "dhis2")
        self.assertEqual(envelope["entity_name"], "ward")
        self.assertEqual(envelope["schema_version"], "cchis.v1")
        self.assertEqual(envelope["record"]["public_id"], str(self.ward.public_id))

    def test_ward_location_crosswalk_uses_stable_identifiers(self):
        canonical = ward_to_canonical_ref(self.ward)
        crosswalk = ward_location_crosswalk_key(canonical)

        self.assertEqual(crosswalk.entity_type, "ward")
        self.assertEqual(crosswalk.cchis_public_id, str(self.ward.public_id))
        self.assertEqual(crosswalk.local_reference_code, self.ward.ward_code)

    def test_facility_location_crosswalk_uses_stable_identifiers(self):
        canonical = facility_to_canonical_ref(self.health_facility)
        crosswalk = facility_location_crosswalk_key(canonical)

        self.assertEqual(crosswalk.entity_type, "health_facility")
        self.assertEqual(crosswalk.cchis_public_id, str(self.health_facility.public_id))
        self.assertEqual(crosswalk.local_reference_code, self.health_facility.facility_code)

    def test_dhis2_org_unit_mapping_stub_uses_crosswalk_inputs(self):
        canonical = ward_to_canonical_ref(self.ward)
        crosswalk = ward_location_crosswalk_key(canonical)

        mapping_stub = build_dhis2_org_unit_mapping_stub(
            source_system="dhis2",
            location_key=crosswalk,
            external_org_unit_id="DHIS2-OU-001",
        )

        self.assertEqual(mapping_stub["source_system"], "dhis2")
        self.assertEqual(mapping_stub["entity_type"], "ward")
        self.assertEqual(mapping_stub["cchis_public_id"], str(self.ward.public_id))
        self.assertEqual(mapping_stub["local_reference_code"], self.ward.ward_code)
        self.assertEqual(mapping_stub["external_org_unit_id"], "DHIS2-OU-001")

    def test_dhis2_risk_score_export_stub_uses_canonical_record(self):
        canonical = riskscore_to_canonical_record(self.risk_score)

        payload = build_dhis2_risk_score_export_stub(
            canonical,
            external_org_unit_id="DHIS2-OU-001",
            data_element_id="DE-RISK-SCORE",
        )

        self.assertEqual(payload["orgUnit"], "DHIS2-OU-001")
        self.assertEqual(payload["metadata"]["ward_public_id"], str(self.ward.public_id))
        self.assertEqual(payload["metadata"]["ward_code"], self.ward.ward_code)
        self.assertEqual(payload["metadata"]["model_version"], self.risk_score.model_version)
        self.assertEqual(payload["dataValues"][0]["dataElement"], "DE-RISK-SCORE")
        self.assertEqual(payload["dataValues"][0]["value"], self.risk_score.score)


class ObservabilityInventoryTestCase(APITestCase):
    def test_operational_metric_inventory_covers_core_domains(self):
        categories = {metric.category for metric in OPERATIONAL_METRICS}
        names = {metric.name for metric in OPERATIONAL_METRICS}

        self.assertTrue({"api", "auth", "sync", "triage", "ussd", "forecasting", "alerts"}.issubset(categories))
        self.assertIn("http_requests_total", names)
        self.assertIn("auth_login_attempts_total", names)
        self.assertIn("auth_login_cooldowns_total", names)
        self.assertIn("access_request_submissions_total", names)
        self.assertIn("access_request_duplicates_suppressed_total", names)
        self.assertIn("access_request_suspicious_rejections_total", names)
        self.assertIn("sync_payload_replays_total", names)
        self.assertIn("risk_model_runs_total", names)
        self.assertIn("alert_delivery_attempts_total", names)

    def test_event_taxonomy_distinguishes_logs_metrics_and_audit_events(self):
        classifications = {item.classification for item in EVENT_CLASSIFICATIONS}
        event_names = {item.event_name for item in EVENT_CLASSIFICATIONS}

        self.assertEqual(classifications, {"log", "metric", "audit_event"})
        self.assertIn("request_complete", event_names)
        self.assertIn("auth_audit_event", event_names)
        self.assertIn("future_operational_metric", event_names)

    def test_auth_audit_event_is_marked_durable(self):
        auth_event = next(item for item in EVENT_CLASSIFICATIONS if item.event_name == "auth_audit_event")
        request_log = next(item for item in EVENT_CLASSIFICATIONS if item.event_name == "request_complete")

        self.assertTrue(auth_event.durable)
        self.assertFalse(request_log.durable)

    def test_domain_audit_inventory_covers_future_non_auth_operational_actions(self):
        action_names = {item.action_name for item in DOMAIN_AUDIT_INVENTORY}
        domain_areas = {item.domain_area for item in DOMAIN_AUDIT_INVENTORY}

        self.assertTrue({"forecasting", "operations", "messaging", "surveillance"}.issubset(domain_areas))
        self.assertIn("risk_score_manual_override", action_names)
        self.assertIn("alert_manual_trigger", action_names)
        self.assertIn("ingestion_run_manual_correction", action_names)
        self.assertIn("sync_queue_manual_replay", action_names)
        self.assertIn("response_action_state_override", action_names)

    def test_manual_override_audit_inventory_requires_actor_reason_and_minimum_metadata(self):
        override_actions = [
            item for item in DOMAIN_AUDIT_INVENTORY if "override" in item.action_name or "manual" in item.action_name
        ]

        self.assertTrue(override_actions)

        for action in override_actions:
            self.assertTrue(action.actor_required)
            self.assertTrue(action.reason_required)
            self.assertTrue(action.minimum_metadata)

        risk_override = next(
            item for item in DOMAIN_AUDIT_INVENTORY if item.action_name == "risk_score_manual_override"
        )
        intervention_override = next(
            item for item in DOMAIN_AUDIT_INVENTORY if item.action_name == "response_action_state_override"
        )

        self.assertIn("override_reason", risk_override.minimum_metadata)
        self.assertIn("previous_status", intervention_override.minimum_metadata)
        self.assertIn("new_status", intervention_override.minimum_metadata)

    def test_runbook_input_inventory_covers_core_incident_domains(self):
        incident_areas = {item.incident_area for item in MINIMUM_RUNBOOK_INPUTS}
        input_names = {item.input_name for item in MINIMUM_RUNBOOK_INPUTS}

        self.assertTrue({"api", "security", "sync", "triage", "ussd", "forecasting", "alerts", "operations"}.issubset(incident_areas))
        self.assertIn("request_trace_logs", input_names)
        self.assertIn("auth_audit_events", input_names)
        self.assertIn("ingestion_run_records", input_names)
        self.assertIn("alert_delivery_state", input_names)
        self.assertIn("sync_queue_state", input_names)

    def test_recovery_visibility_expectations_cover_backup_restore_and_validation(self):
        workflows = {item.workflow_name for item in RECOVERY_VISIBILITY_REQUIREMENTS}
        stages = {item.stage for item in RECOVERY_VISIBILITY_REQUIREMENTS}

        self.assertEqual(
            workflows,
            {"database_backup", "database_restore", "post_restore_validation", "recovery_rehearsal"},
        )
        self.assertEqual(
            stages,
            {"backup_execution", "restore_execution", "verification", "drill_review"},
        )

        restore_visibility = next(
            item for item in RECOVERY_VISIBILITY_REQUIREMENTS if item.workflow_name == "database_restore"
        )
        post_restore_validation = next(
            item for item in RECOVERY_VISIBILITY_REQUIREMENTS if item.workflow_name == "post_restore_validation"
        )

        self.assertIn("restore_source_artifact_reference", restore_visibility.required_signals)
        self.assertIn("applied_migration_state", restore_visibility.required_records)
        self.assertIn("api_smoke_test_result", post_restore_validation.required_signals)
        self.assertIn("critical_model_count_summary", post_restore_validation.required_records)


class DataLifecyclePolicyTestCase(APITestCase):
    def test_data_retention_inventory_covers_current_sensitive_and_provenance_records(self):
        record_names = {item.record_name for item in DATA_RETENTION_INVENTORY}
        system_areas = {item.system_area for item in DATA_RETENTION_INVENTORY}

        self.assertTrue({"accounts", "messaging", "surveillance", "operations", "forecasting", "platform"}.issubset(system_areas))
        self.assertIn("auth_audit_events", record_names)
        self.assertIn("ussd_session_logs", record_names)
        self.assertIn("sync_queue_payloads", record_names)
        self.assertIn("triage_sessions", record_names)
        self.assertIn("model_runs_and_risk_scores", record_names)

    def test_sensitive_operational_records_are_not_treated_like_disposable_logs(self):
        auth_audit = next(item for item in DATA_RETENTION_INVENTORY if item.record_name == "auth_audit_events")
        triage_sessions = next(item for item in DATA_RETENTION_INVENTORY if item.record_name == "triage_sessions")
        request_logs = next(item for item in DATA_RETENTION_INVENTORY if item.record_name == "request_trace_logs")

        self.assertTrue(auth_audit.contains_sensitive_data)
        self.assertTrue(triage_sessions.contains_sensitive_data)
        self.assertEqual(request_logs.retention_class, "short_lived_operations")
        self.assertNotEqual(auth_audit.retention_class, request_logs.retention_class)
        self.assertNotEqual(triage_sessions.retention_class, request_logs.retention_class)

    def test_field_data_minimization_rules_prefer_structured_and_least_identifying_records(self):
        record_families = {item.record_family for item in FIELD_DATA_MINIMIZATION_RULES}

        self.assertIn("triage_and_case_intake", record_families)
        self.assertIn("sync_payloads", record_families)
        self.assertIn("future_household_or_case_follow_up", record_families)

        intake_rule = next(item for item in FIELD_DATA_MINIMIZATION_RULES if item.record_family == "triage_and_case_intake")
        follow_up_rule = next(
            item for item in FIELD_DATA_MINIMIZATION_RULES if item.record_family == "future_household_or_case_follow_up"
        )

        self.assertIn("symptom_flags", intake_rule.allowed_by_default)
        self.assertIn("patient_full_name", intake_rule.avoid_by_default)
        self.assertIn("purpose_limited_collection", intake_rule.required_controls)
        self.assertIn("precise_gps_coordinates", follow_up_rule.avoid_by_default)
        self.assertIn("explicit_justification_for_direct_identifiers", follow_up_rule.required_controls)


class RecoveryDisciplineTestCase(APITestCase):
    def test_backup_expectations_cover_backup_restore_and_post_restore_records(self):
        workflow_names = {item.workflow_name for item in BACKUP_EXPECTATIONS}
        scopes = {item.target_scope for item in BACKUP_EXPECTATIONS}

        self.assertEqual(
            workflow_names,
            {"database_backup_artifact", "restore_execution_record", "post_restore_validation_record"},
        )
        self.assertIn("primary_postgres_database", scopes)
        self.assertIn("restore_attempt", scopes)
        self.assertIn("restored_application_state", scopes)

    def test_backup_and_restore_expectations_require_traceable_artifacts_and_schema_state(self):
        backup_record = next(item for item in BACKUP_EXPECTATIONS if item.workflow_name == "database_backup_artifact")
        restore_record = next(item for item in BACKUP_EXPECTATIONS if item.workflow_name == "restore_execution_record")
        validation_record = next(item for item in BACKUP_EXPECTATIONS if item.workflow_name == "post_restore_validation_record")

        self.assertIn("backup_artifact_reference", backup_record.required_evidence)
        self.assertIn("schema_migration_state", backup_record.required_evidence)
        self.assertIn("restore_source_artifact_reference", restore_record.required_evidence)
        self.assertIn("applied_migration_state", restore_record.required_evidence)
        self.assertIn("api_smoke_test_result", validation_record.required_evidence)
        self.assertIn("critical_record_counts_look_plausible", validation_record.minimum_validation)

    def test_restore_rehearsal_expectation_requires_gap_capture_and_follow_up_actions(self):
        rehearsal = next(
            item for item in RESTORE_REHEARSAL_EXPECTATIONS if item.rehearsal_name == "shared_environment_restore_rehearsal"
        )

        self.assertEqual(rehearsal.target_environment_class, "staging")
        self.assertIn("perform_restore", rehearsal.required_steps)
        self.assertIn("run_post_restore_validation", rehearsal.required_steps)
        self.assertIn("tested_backup_artifact_reference", rehearsal.success_evidence)
        self.assertIn("observed_gaps", rehearsal.success_evidence)
        self.assertIn("follow_up_actions", rehearsal.success_evidence)


class RiskPermissionsTestCase(AuthenticatedAPITestCase):
    def test_ward_list_requires_authentication(self):
        response = self.client.get(reverse("ward-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_chv_cannot_list_wards(self):
        self.authenticate(self.chv_user.username)
        response = self.client.get(reverse("ward-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_supervisor_only_sees_assigned_ward_in_ward_list(self):
        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("ward-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.other_ward.id)

    def test_analyst_can_list_all_wards(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("ward-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_results(response)), 2)

    def test_analyst_can_search_wards_by_partial_name(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("ward-list"), {"q": "kamag"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "North Kamagambo")

    def test_analyst_can_filter_wards_by_risk_label(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("ward-list"), {"risk": "HIGH"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "North Kamagambo")

    def test_analyst_can_view_ward_detail_summary(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("ward-detail", kwargs={"pk": self.ward.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.ward.id)
        self.assertEqual(response.data["name"], "North Kamagambo")
        self.assertEqual(response.data["predicted_cases"], 18)
        self.assertEqual(response.data["latest_source"], RiskScore.SOURCE_MODEL)
        self.assertEqual(response.data["latest_model_version"], "v0-test")

    def test_supervisor_cannot_view_out_of_scope_ward_detail(self):
        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("ward-detail", kwargs={"pk": self.ward.id}))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_supervisor_can_view_in_scope_ward_detail(self):
        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("ward-detail", kwargs={"pk": self.other_ward.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], self.other_ward.id)
        self.assertEqual(response.data["name"], "North Kadem")

    def test_latest_ward_risk_supports_search_and_sub_county_filters(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("latest-ward-risk"), {"q": "kadem", "sub_county": "Nyatike"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["ward_name"], "North Kadem")

    def test_chv_list_requires_admin_or_supervisor(self):
        self.authenticate(self.chv_user.username)
        response = self.client.get(reverse("chv-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_supervisor_can_list_chvs(self):
        CHV.objects.create(
            name="Other Ward CHV",
            phone_number="+254700000010",
            ward=self.other_ward,
            is_active=True,
            language="en",
        )

        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("chv-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ward"], self.other_ward.id)

    def test_risk_scores_require_authentication(self):
        response = self.client.get(reverse("risk-score-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_supervisor_can_filter_risk_scores_for_assigned_ward(self):
        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("risk-score-list"), {"ward_id": self.other_ward.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ward"], self.other_ward.id)

    def test_chv_cannot_read_risk_scores(self):
        self.authenticate(self.chv_user.username)
        response = self.client.get(reverse("risk-score-list"), {"ward_id": self.ward.id})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_analyst_can_view_alerts(self):
        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Test alert",
            status=Alert.STATUS_DELIVERED,
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("alert-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_results(response)), 1)

    def test_alert_list_requires_admin_or_supervisor(self):
        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Test alert",
            status=Alert.STATUS_DELIVERED,
        )

        self.authenticate(self.chv_user.username)
        response = self.client.get(reverse("alert-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_supervisor_can_view_alerts(self):
        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Test alert",
            status=Alert.STATUS_DELIVERED,
        )

        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("alert-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_results(response)), 0)

    def test_supervisor_only_sees_alerts_for_assigned_ward(self):
        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Ward one alert",
            status=Alert.STATUS_DELIVERED,
        )
        Alert.objects.create(
            ward=self.other_ward,
            risk_score=self.other_risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Ward two alert",
            status=Alert.STATUS_DELIVERED,
        )

        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("alert-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ward"], self.other_ward.id)

    @patch("risk.views.trigger_alerts_task.delay", return_value=SimpleNamespace(id="task-123"))
    def test_supervisor_can_queue_alert_trigger(self, mock_delay):
        self.authenticate(self.supervisor_user.username)
        response = self.client.post(
            reverse("trigger-alerts"),
            {"ward_id": self.other_ward.id, "send_sms": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["task_id"], "task-123")
        mock_delay.assert_called_once()

    @patch("risk.views.trigger_alerts_task.delay", return_value=SimpleNamespace(id="task-123"))
    def test_supervisor_cannot_trigger_alerts_outside_assigned_ward(self, mock_delay):
        self.authenticate(self.supervisor_user.username)
        response = self.client.post(
            reverse("trigger-alerts"),
            {"ward_id": self.ward.id, "send_sms": True},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        mock_delay.assert_not_called()

    def test_trigger_alerts_returns_404_when_no_matching_risk_score(self):
        empty_ward = Ward.objects.create(
            name="No Score Ward",
            county="Migori",
            sub_county="Suna",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.10,
            is_active=True,
        )

        self.authenticate(self.supervisor_user.username)
        response = self.client.post(
            reverse("trigger-alerts"),
            {"ward_id": empty_ward.id, "send_sms": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "No matching risk score found.")

    def test_create_alerts_for_riskscore_creates_dashboard_and_queued_sms_alerts(self):
        alerts = create_alerts_for_riskscore(self.risk_score, send_sms_enabled=True)

        self.assertEqual(len(alerts), 2)
        dashboard_alert = next(alert for alert in alerts if alert.channel == Alert.CHANNEL_DASHBOARD)
        sms_alert = next(alert for alert in alerts if alert.channel == Alert.CHANNEL_SMS)

        self.assertEqual(dashboard_alert.status, Alert.STATUS_DELIVERED)
        self.assertEqual(dashboard_alert.delivery_backend, "internal-dashboard")
        self.assertEqual(dashboard_alert.attempt_count, 1)
        self.assertEqual(sms_alert.status, Alert.STATUS_QUEUED)
        self.assertEqual(sms_alert.delivery_backend, "stub")
        self.assertEqual(sms_alert.attempt_count, 0)
        self.assertEqual(sms_alert.max_attempts, 3)

    @patch("risk.services.send_sms")
    def test_deliver_alert_marks_sms_delivered_on_success(self, mock_send_sms):
        mock_send_sms.return_value = DeliveryResult(
            success=True,
            external_id="msg-001",
            error="",
            provider="stub",
        )
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient=self.chv.phone_number,
            message="Escalate immediately",
            status=Alert.STATUS_QUEUED,
            delivery_backend="africastalking",
            max_attempts=3,
        )

        deliver_alert(alert)
        alert.refresh_from_db()

        self.assertEqual(alert.status, Alert.STATUS_DELIVERED)
        self.assertEqual(alert.attempt_count, 1)
        self.assertEqual(alert.external_id, "msg-001")
        self.assertEqual(alert.delivery_backend, "stub")
        self.assertIsNotNone(alert.sent_at)
        self.assertIsNone(alert.next_retry_at)

    @patch("risk.services.send_sms")
    def test_deliver_alert_marks_retry_pending_before_max_attempts(self, mock_send_sms):
        mock_send_sms.return_value = DeliveryResult(
            success=False,
            external_id="",
            error="provider timeout",
            provider="stub",
        )
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient=self.chv.phone_number,
            message="Escalate immediately",
            status=Alert.STATUS_QUEUED,
            delivery_backend="africastalking",
            max_attempts=3,
        )

        deliver_alert(alert)
        alert.refresh_from_db()

        self.assertEqual(alert.status, Alert.STATUS_RETRY_PENDING)
        self.assertEqual(alert.attempt_count, 1)
        self.assertEqual(alert.error_message, "provider timeout")
        self.assertEqual(alert.delivery_backend, "stub")
        self.assertIsNotNone(alert.next_retry_at)

    @patch("risk.tasks.deliver_alert_task.apply_async")
    @patch("risk.services.send_sms")
    def test_deliver_alert_task_marks_failed_when_max_attempts_reached(self, mock_send_sms, mock_apply_async):
        mock_send_sms.return_value = DeliveryResult(
            success=False,
            external_id="",
            error="provider down",
            provider="stub",
        )
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient=self.chv.phone_number,
            message="Escalate immediately",
            status=Alert.STATUS_RETRY_PENDING,
            delivery_backend="africastalking",
            max_attempts=2,
            attempt_count=1,
        )

        status_value = deliver_alert_task.run(alert.id)
        alert.refresh_from_db()

        self.assertEqual(status_value, Alert.STATUS_FAILED)
        self.assertEqual(alert.status, Alert.STATUS_FAILED)
        self.assertEqual(alert.attempt_count, 2)
        self.assertEqual(alert.delivery_backend, "stub")
        self.assertIsNone(alert.next_retry_at)
        mock_apply_async.assert_not_called()

    def test_get_sms_provider_defaults_to_stub(self):
        provider = get_sms_provider("stub")
        self.assertIsInstance(provider, StubSmsProvider)

    def test_get_sms_provider_raises_for_unknown_provider(self):
        with self.assertRaisesMessage(ValueError, "Unsupported SMS provider: unknown-provider"):
            get_sms_provider("unknown-provider")


class EmailProviderFoundationTestCase(AuthenticatedAPITestCase):
    def test_get_email_provider_defaults_to_stub(self):
        with override_settings(EMAIL_PROVIDER="stub"):
            provider = get_email_provider()

        self.assertIsInstance(provider, StubEmailProvider)

    def test_get_email_provider_returns_mailgun_provider(self):
        with override_settings(EMAIL_PROVIDER="mailgun"):
            provider = get_email_provider()

        self.assertIsInstance(provider, MailgunEmailProvider)

    def test_get_email_provider_raises_for_unknown_provider(self):
        with self.assertRaisesMessage(ValueError, "Unsupported email provider: unknown-provider"):
            get_email_provider("unknown-provider")

    @override_settings(EMAIL_PROVIDER="stub")
    def test_send_email_uses_stub_provider_successfully(self):
        result = send_email(
            to_email="ops@example.com",
            subject="Test message",
            text_body="Mailgun phase 1 foundation test.",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.provider, "stub")
        self.assertTrue(result.external_id.startswith("stub-ops@example.com-"))

    @override_settings(
        EMAIL_PROVIDER="mailgun",
        MAILGUN_API_KEY="",
        MAILGUN_DOMAIN="",
        MAILGUN_FROM_EMAIL="",
    )
    def test_mailgun_provider_returns_safe_failure_when_credentials_missing(self):
        provider = MailgunEmailProvider()

        result = provider.send(
            to_email="ops@example.com",
            subject="Credential test",
            text_body="This should fail safely.",
        )

        self.assertFalse(result.success)
        self.assertEqual(result.provider, "mailgun")
        self.assertIn("credentials are missing", result.error.lower())

    @patch("communications.providers.requests.post")
    @override_settings(
        EMAIL_PROVIDER="mailgun",
        MAILGUN_API_KEY="key-test",
        MAILGUN_DOMAIN="mg.example.org",
        MAILGUN_FROM_EMAIL="Kodi Alerts <alerts@mg.example.org>",
        MAILGUN_HOST="postmaster@mg.example.org",
        MAILGUN_BASE_URL="https://api.mailgun.net/v3",
        MAILGUN_REPLY_TO="",
    )
    def test_mailgun_provider_sends_email_with_expected_payload(self, mock_post):
        mock_response = SimpleNamespace(
            status_code=200,
            json=lambda: {"id": "<mailgun-message-id>"},
            raise_for_status=lambda: None,
        )
        mock_post.return_value = mock_response

        result = send_email(
            to_email="ops@example.com",
            subject="Alert test",
            text_body="Plaintext body",
            html_body="<p>HTML body</p>",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.provider, "mailgun")
        self.assertEqual(result.external_id, "<mailgun-message-id>")
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["auth"], ("api", "key-test"))
        self.assertEqual(kwargs["data"]["from"], "Kodi Alerts <alerts@mg.example.org>")
        self.assertEqual(kwargs["data"]["to"], ["ops@example.com"])
        self.assertEqual(kwargs["data"]["subject"], "Alert test")
        self.assertEqual(kwargs["headers"]["h:Reply-To"], "postmaster@mg.example.org")

    @patch("risk.tasks.deliver_alert_task.delay")
    def test_trigger_alerts_task_queues_delivery_for_sms_alerts(self, mock_delay):
        dashboard_alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Dashboard alert",
            status=Alert.STATUS_DELIVERED,
            delivery_backend="internal-dashboard",
            attempt_count=1,
            max_attempts=1,
            sent_at=timezone.now(),
            last_attempted_at=timezone.now(),
        )
        sms_alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient=self.chv.phone_number,
            message="SMS alert",
            status=Alert.STATUS_QUEUED,
            delivery_backend="africastalking",
            max_attempts=3,
        )

        with patch("risk.tasks.trigger_alerts_for_riskscore", return_value=[dashboard_alert, sms_alert]):
            created_count = trigger_alerts_task.run(self.risk_score.id, send_sms=True)

        self.assertEqual(created_count, 2)
        mock_delay.assert_called_once_with(sms_alert.id)

    def test_chv_can_submit_triage(self):
        self.authenticate(self.chv_user.username)
        response = self.client.post(
            reverse("chv-triage"),
            {
                "ward_id": self.ward.id,
                "phone_number": "+254711111111",
                "channel": "API",
                "diarrhea": True,
                "vomiting": True,
                "dehydration": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(TriageSession.objects.count(), 1)
        self.assertTrue(response.data["referral_needed"])

    def test_chv_cannot_submit_triage_for_other_ward(self):
        self.authenticate(self.chv_user.username)
        response = self.client.post(
            reverse("chv-triage"),
            {
                "ward_id": self.other_ward.id,
                "phone_number": "+254711111111",
                "channel": "API",
                "diarrhea": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_analyst_cannot_submit_triage(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.post(
            reverse("chv-triage"),
            {
                "ward_id": self.other_ward.id,
                "phone_number": "+254711111111",
                "channel": "API",
                "diarrhea": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_submit_triage(self):
        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("chv-triage"),
            {
                "ward_id": self.ward.id,
                "phone_number": "+254711111111",
                "channel": "API",
                "diarrhea": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_chv_sync_requires_authenticated_role(self):
        response = self.client.post(
            reverse("chv-sync"),
            {
                "ward_id": self.ward.id,
                "phone_number": "+254700000009",
                "source_device_id": "device-001",
                "payloads": [{"client_submission_id": "submission-001", "diarrhea": True}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_chv_can_sync_payloads(self):
        self.authenticate(self.chv_user.username)
        response = self.client.post(
            reverse("chv-sync"),
            {
                "ward_id": self.ward.id,
                "phone_number": "+254700000009",
                "source_device_id": "device-001",
                "payloads": [
                    {
                        "client_submission_id": "submission-001",
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
        self.assertEqual(SyncQueue.objects.count(), 1)
        self.assertEqual(TriageSession.objects.count(), 1)
        self.assertEqual(response.data["processed_count"], 1)
        self.assertFalse(response.data["results"][0]["replayed"])

    def test_chv_cannot_sync_other_ward_payloads(self):
        self.authenticate(self.chv_user.username)
        response = self.client.post(
            reverse("chv-sync"),
            {
                "ward_id": self.other_ward.id,
                "phone_number": "+254700000009",
                "source_device_id": "device-001",
                "payloads": [{"client_submission_id": "submission-001", "diarrhea": True}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_analyst_cannot_sync_payloads(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.post(
            reverse("chv-sync"),
            {
                "ward_id": self.other_ward.id,
                "phone_number": "+254700000009",
                "source_device_id": "device-001",
                "payloads": [{"client_submission_id": "submission-001", "diarrhea": True}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_sync_payloads(self):
        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("chv-sync"),
            {
                "ward_id": self.ward.id,
                "phone_number": "+254700000009",
                "source_device_id": "device-001",
                "payloads": [{"client_submission_id": "submission-001", "diarrhea": True}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_chv_sync_replays_duplicate_submission_without_creating_duplicates(self):
        self.authenticate(self.chv_user.username)
        payload = {
            "ward_id": self.ward.id,
            "phone_number": "+254700000009",
            "source_device_id": "device-001",
            "payloads": [
                {
                    "client_submission_id": "submission-dup-001",
                    "diarrhea": True,
                    "vomiting": False,
                    "dehydration": False,
                    "fever": False,
                    "text_input": "retry me safely",
                }
            ],
        }

        first_response = self.client.post(reverse("chv-sync"), payload, format="json")
        second_response = self.client.post(reverse("chv-sync"), payload, format="json")

        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SyncQueue.objects.count(), 1)
        self.assertEqual(TriageSession.objects.count(), 1)
        self.assertFalse(first_response.data["results"][0]["replayed"])
        self.assertTrue(second_response.data["results"][0]["replayed"])

    def test_chv_sync_requires_unique_submission_ids_within_request(self):
        self.authenticate(self.chv_user.username)
        response = self.client.post(
            reverse("chv-sync"),
            {
                "ward_id": self.ward.id,
                "phone_number": "+254700000009",
                "source_device_id": "device-001",
                "payloads": [
                    {"client_submission_id": "duplicate-001", "diarrhea": True},
                    {"client_submission_id": "duplicate-001", "vomiting": True},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("client_submission_id", str(response.data))

    def test_ussd_stays_public(self):
        response = self.client.post(
            reverse("ussd-menu"),
            {
                "sessionId": "abc123",
                "serviceCode": "*123#",
                "phoneNumber": "+254700000001",
                "text": "2*1",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(UssdSessionLog.objects.count(), 1)
        self.assertTrue(response.data["response"].startswith("END Give ORS immediately"))

    def test_ussd_invalid_option(self):
        response = self.client.post(
            reverse("ussd-menu"),
            {
                "sessionId": "bad001",
                "serviceCode": "*123#",
                "phoneNumber": "+254700000001",
                "text": "9",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(UssdSessionLog.objects.count(), 1)
        self.assertEqual(response.data["response"], "END Invalid option. Please try again.")
        self.assertEqual(UssdSessionLog.objects.first().menu_level, "invalid")

    def test_ussd_logs_require_admin_or_supervisor(self):
        UssdSessionLog.objects.create(
            session_id="log-001",
            phone_number="+254700000001",
            service_code="*123#",
            text="2",
            response_text="CON Child diarrhea support",
            menu_level="diarrhea_menu",
        )

        self.authenticate(self.chv_user.username)
        response = self.client.get(reverse("ussd-log-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_view_ussd_logs(self):
        UssdSessionLog.objects.create(
            session_id="log-001",
            phone_number="+254700000001",
            service_code="*123#",
            text="2",
            response_text="CON Child diarrhea support",
            menu_level="diarrhea_menu",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("ussd-log-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(get_results(response)), 1)

    def test_supervisor_only_sees_ussd_logs_for_assigned_ward(self):
        UssdSessionLog.objects.create(
            session_id="log-001",
            phone_number="+254700000001",
            service_code="*123#",
            text="2",
            response_text="CON Child diarrhea support",
            menu_level="diarrhea_menu",
            ward=self.ward,
        )
        UssdSessionLog.objects.create(
            session_id="log-002",
            phone_number="+254700000002",
            service_code="*123#",
            text="2",
            response_text="CON Child diarrhea support",
            menu_level="diarrhea_menu",
            ward=self.other_ward,
        )

        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("ussd-log-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ward"], self.other_ward.id)

    def test_latest_risk_requires_authentication(self):
        response = self.client.get(reverse("latest-ward-risk"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_analyst_can_view_latest_risk(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("latest-ward-risk"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_supervisor_only_sees_latest_risk_for_assigned_ward(self):
        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("latest-ward-risk"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["ward_id"], self.other_ward.id)

    def test_chv_cannot_view_latest_risk(self):
        self.authenticate(self.chv_user.username)
        response = self.client.get(reverse("latest-ward-risk"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_triage_assigns_referral_facility_when_referral_needed(self):
        self.authenticate(self.chv_user.username)
        response = self.client.post(
            reverse("chv-triage"),
            {
                "ward_id": self.ward.id,
                "phone_number": "+254700000099",
                "channel": "API",
                "diarrhea": True,
                "vomiting": True,
                "dehydration": True,
                "fever": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["referral_facility"], self.health_facility.id)
        self.assertEqual(response.data["referral_facility_name"], self.health_facility.name)

    def test_paginated_list_endpoints_return_count_and_results(self):
        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("ward-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 2)

    def test_list_endpoint_supports_ordering_parameter(self):
        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("ward-list"), {"ordering": "-name"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertEqual(results[0]["name"], "North Kamagambo")


class SeedAndModelCommandTestCase(APITestCase):
    def test_seed_demo_data_command_runs_and_creates_demo_users(self):
        call_command("seed_demo_data")

        self.assertGreaterEqual(Ward.objects.count(), 4)
        self.assertFalse(Ward.objects.exclude(county="Migori").exists())
        self.assertGreaterEqual(HealthFacility.objects.count(), 4)
        self.assertGreaterEqual(CHV.objects.count(), 4)
        self.assertGreaterEqual(RiskScore.objects.count(), 4)
        self.assertTrue(User.objects.filter(username="superuser", is_superuser=True).exists())
        self.assertTrue(User.objects.filter(username="admin", role=User.ROLE_ADMIN).exists())
        self.assertTrue(User.objects.filter(username="chv_demo", role=User.ROLE_CHV).exists())
        self.assertFalse(Ward.objects.filter(ward_code="").exists())
        self.assertFalse(HealthFacility.objects.filter(facility_code="").exists())

    def test_seed_demo_data_command_is_idempotent(self):
        call_command("seed_demo_data")
        first_counts = {
            "wards": Ward.objects.count(),
            "health_facilities": HealthFacility.objects.count(),
            "chvs": CHV.objects.count(),
            "risk_scores": RiskScore.objects.count(),
            "users": User.objects.count(),
        }

        call_command("seed_demo_data")
        second_counts = {
            "wards": Ward.objects.count(),
            "health_facilities": HealthFacility.objects.count(),
            "chvs": CHV.objects.count(),
            "risk_scores": RiskScore.objects.count(),
            "users": User.objects.count(),
        }

        self.assertEqual(second_counts, first_counts)

    @patch.dict(
        os.environ,
        {
            "SEED_ENABLE_SUPERUSER": "False",
            "SEED_ENABLE_DEMO_USERS": "False",
        },
        clear=False,
    )
    def test_seed_demo_data_command_can_skip_seeded_accounts(self):
        call_command("seed_demo_data")

        self.assertEqual(User.objects.count(), 0)
        self.assertGreaterEqual(Ward.objects.count(), 4)
        self.assertGreaterEqual(HealthFacility.objects.count(), 4)
        self.assertGreaterEqual(CHV.objects.count(), 4)

    @override_settings(CCHIS_ENVIRONMENT="staging")
    def test_seed_demo_data_command_blocks_non_local_environment_by_default(self):
        with self.assertRaisesMessage(CommandError, "seed_demo_data is blocked outside local environments."):
            call_command("seed_demo_data")

        self.assertEqual(Ward.objects.count(), 0)
        self.assertEqual(User.objects.count(), 0)

    @patch.dict(os.environ, {"SEED_ALLOW_NON_LOCAL": "True"}, clear=False)
    @override_settings(CCHIS_ENVIRONMENT="staging")
    def test_seed_demo_data_command_can_run_in_non_local_environment_with_explicit_override(self):
        call_command("seed_demo_data")

        self.assertGreaterEqual(Ward.objects.count(), 4)
        self.assertFalse(Ward.objects.exclude(county="Migori").exists())
        self.assertTrue(User.objects.filter(username="admin", role=User.ROLE_ADMIN).exists())

    def test_run_risk_model_creates_scores(self):
        ward_one = Ward.objects.create(
            name="Ward One",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.20,
            is_active=True,
        )
        ward_two = Ward.objects.create(
            name="Ward Two",
            county="Migori",
            sub_county="Nyatike",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.55,
            is_active=True,
        )
        CHV.objects.create(
            name="CHV One",
            phone_number="+254700010001",
            ward=ward_one,
            is_active=True,
            language="en",
        )
        CHV.objects.create(
            name="CHV Two",
            phone_number="+254700010002",
            ward=ward_two,
            is_active=True,
            language="en",
        )

        call_command("run_risk_model", "--month=4", "--model-version=lr-test-v1")
        self.assertEqual(RiskScore.objects.count(), 2)
        self.assertEqual(ModelRun.objects.filter(model_version="lr-test-v1", status=ModelRun.STATUS_SUCCESS).count(), 1)
        self.assertEqual(RiskScore.objects.filter(model_run__isnull=False, source=RiskScore.SOURCE_MODEL).count(), 2)
        model_run = ModelRun.objects.get(model_version="lr-test-v1")
        self.assertIsNotNone(model_run.rainfall_ingestion_run)
        self.assertEqual(model_run.rainfall_ingestion_run.run_type, IngestionRun.RUN_TYPE_RAINFALL)
        self.assertEqual(model_run.evaluation_metrics["training_row_count"], 8)
        self.assertEqual(model_run.feature_schema_version, "mock-v1")
        self.assertEqual(model_run.training_dataset_ref, "mock-training-dataset:v1")
        self.assertEqual(model_run.inference_dataset_ref, "mock-inference-dataset:month-4")

    def test_seed_demo_data_assigns_model_run_to_seeded_model_scores(self):
        call_command("seed_demo_data")

        self.assertTrue(ModelRun.objects.filter(model_version="v0-demo", status=ModelRun.STATUS_SUCCESS).exists())
        self.assertFalse(RiskScore.objects.filter(source=RiskScore.SOURCE_MODEL, model_run__isnull=True).exists())


class RainfallIngestionTestCase(APITestCase):
    @patch("risk.ml.ingestion.fetch_open_meteo_daily_precipitation")
    def test_fetch_rainfall_for_known_ward_uses_live_source_when_available(self, mock_fetch):
        mock_fetch.return_value.rainfall_mm = 84.5
        mock_fetch.return_value.ward_name = "North Kamagambo"
        mock_fetch.return_value.source = "open-meteo-forecast"
        mock_fetch.return_value.latitude = -0.9876
        mock_fetch.return_value.longitude = 34.6410

        result = fetch_rainfall_for_ward("North Kamagambo")
        self.assertEqual(result.rainfall_mm, 84.5)
        self.assertEqual(result.source, "open-meteo-forecast")
        run = IngestionRun.objects.get()
        self.assertEqual(run.status, IngestionRun.STATUS_SUCCESS)
        self.assertEqual(run.requested_wards, ["North Kamagambo"])
        self.assertEqual(run.results[0]["source"], "open-meteo-forecast")

    @patch("risk.ml.ingestion.fetch_open_meteo_daily_precipitation", side_effect=Exception("network down"))
    def test_fetch_rainfall_falls_back_to_static(self, mock_fetch):
        result = fetch_rainfall_for_ward("North Kamagambo")
        self.assertGreater(result.rainfall_mm, 0)
        self.assertIn(result.source, ["static-csv", "static-default", "static-fallback"])
        run = IngestionRun.objects.get()
        self.assertEqual(run.status, IngestionRun.STATUS_PARTIAL)
        self.assertEqual(run.results[0]["fallback_reason"], "live-fetch-failed")

    @override_settings()
    @patch("risk.ml.ingestion.fetch_open_meteo_daily_precipitation")
    def test_fetch_rainfall_prefers_ward_centroid_when_available(self, mock_fetch):
        ward = Ward.objects.create(
            name="Centroid Ward",
            county="Migori",
            sub_county="Test",
            ward_code="CENTROID-001",
            centroid=Point(36.8219, -1.2921, srid=4326),
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.12,
            is_active=True,
        )
        mock_fetch.return_value.rainfall_mm = 42.0
        mock_fetch.return_value.ward_name = ward.name
        mock_fetch.return_value.source = "open-meteo-forecast"
        mock_fetch.return_value.latitude = -1.2921
        mock_fetch.return_value.longitude = 36.8219

        result = fetch_rainfall_for_ward(ward.name, ward=ward)

        self.assertEqual(result.coordinate_source, "ward-centroid")
        run = IngestionRun.objects.get()
        self.assertEqual(run.results[0]["coordinate_source"], "ward-centroid")
