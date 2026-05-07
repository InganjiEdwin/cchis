import json
import os
import tempfile
import time
import uuid
from io import StringIO
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from asgiref.sync import async_to_sync, sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.renderers import JSONOpenAPIRenderer
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.settings import api_settings

from accounts.audit import get_client_ip
from accounts.admin import AccessRequestAdmin
from accounts.models import AccessRequest, AuthAuditEvent, PasswordResetToken, PreAuthToken, TwoFactorRecoveryCode
from accounts.services import create_current_policy_acceptances
from accounts.turnstile import TurnstileVerificationResult
from accounts.two_factor import (
    consume_recovery_code,
    generate_current_totp_code,
    generate_recovery_codes,
    generate_totp_secret,
    get_recovery_code_status,
    normalize_recovery_code,
    verify_recovery_code,
)
from communications.providers import EmailDeliveryResult, MailgunEmailProvider, StubEmailProvider, get_email_provider
from communications.services import send_email
from accounts.views import (
    ChangePasswordAPIView,
    DeactivateUserAPIView,
    LoginAPIView,
    LogoutAPIView,
    ReactivateUserAPIView,
    RegenerateTwoFactorRecoveryCodesAPIView,
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
from core.settings import collect_shared_environment_security_errors
from core.data_lifecycle import DATA_RETENTION_INVENTORY, FIELD_DATA_MINIMIZATION_RULES
from core.recovery_discipline import BACKUP_EXPECTATIONS, RESTORE_REHEARSAL_EXPECTATIONS
from risk.ml.ingestion import fetch_rainfall_for_ward
from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.ml.data import InferenceDataset, TrainingDataset, WardFeatureRow
from risk.ml.comparison import build_model_comparison_summary
from risk.ml.readiness import build_boosting_readiness_summary
from risk.ml.trust import (
    ALERT_STATE_ALLOWED,
    ALERT_STATE_BLOCKED,
    ALERT_STATE_REVIEW_ONLY,
    TRUST_STATE_BLOCKED,
    TRUST_STATE_DEGRADED,
    TRUST_STATE_NORMAL,
    build_operational_trust_snapshot,
)
from risk.etl_records import (
    ETL_SCHEMA_VERSION,
    chv_response_record_from_sync_queue,
    chv_response_record_from_triage_session,
    facility_readiness_record_from_intelligence_snapshot,
    surveillance_record_from_sync_queue,
    surveillance_record_from_triage_session,
)
from risk.facility_forecasting import run_facility_burden_forecast_pipeline
from risk.map_data import MIGORI_WARD_GEOMETRY_PATH
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
from risk.admin import CHVCoverageRequestAdmin, CHVCoverageRequestAlertLinkInline
from risk.population_exposure_features import POPULATION_EXPOSURE_FEATURE_SCHEMA_VERSION
from risk.serializers import IngestionRunSerializer
from risk.services import create_alerts_for_riskscore, deliver_alert
from risk.services import build_facility_intelligence_snapshot, build_facility_readiness_decision_summary
from risk.tasks import deliver_alert_task, trigger_alerts_task
from rest_framework_simplejwt.tokens import AccessToken


def started_at_ms(offset_ms: int = 2000) -> int:
    return int(time.time() * 1000) - offset_ms
from risk.views import USSDMenuAPIView
from core.asgi import application

from .models import (
    Alert,
    AlertWorkflowState,
    CHV,
    CHVAssignment,
    CHVCoverageRequest,
    CHVCoverageRequestAlertLink,
    CHVCoverageRequestEmailDelivery,
    CHVCoverageRequestEvent,
    CHVMessage,
    DashboardNotification,
    DashboardNotificationEvent,
    ETLHeartbeat,
    FacilityContact,
    FacilityReadinessEscalation,
    FacilityReadinessReview,
    FacilityReadinessReviewEvent,
    FacilityReadinessUpdateRequest,
    FeatureDataset,
    FeatureDatasetRow,
    FacilityForecast,
    FacilityForecastRun,
    HealthFacility,
    IngestionRun,
    MessageTemplate,
    ModelRun,
    RiskScore,
    SyncQueue,
    SystemControlState,
    TriageSession,
    UssdSessionLog,
    Ward,
    WardGeometryDataset,
    WardGeometryDatasetVersion,
    WardGeometryFeature,
)


User = get_user_model()


def get_results(response):
    if isinstance(response.data, dict) and "results" in response.data:
        return response.data["results"]
    return response.data


class SharedEnvironmentSecuritySettingsTestCase(SimpleTestCase):
    def test_shared_environment_security_rejects_local_transport_defaults(self):
        errors = collect_shared_environment_security_errors(
            environment="production",
            auth_refresh_cookie_secure=False,
            auth_access_cookie_secure=False,
            session_cookie_secure=False,
            csrf_cookie_secure=False,
            secure_ssl_redirect=False,
            secure_ssl_redirect_reverse_proxy_exemption=False,
            secure_hsts_seconds=0,
            allowed_hosts=["*"],
            cors_allow_all_origins=True,
            cors_allowed_origins=["*"],
            auth_refresh_cookie_name="__Host-cchis_refresh",
            auth_refresh_cookie_path="/auth",
            auth_access_cookie_name="__Host-cchis_access",
            auth_access_cookie_path="/api",
        )

        self.assertTrue(any("AUTH_REFRESH_COOKIE_SECURE" in error for error in errors))
        self.assertTrue(any("AUTH_ACCESS_COOKIE_SECURE" in error for error in errors))
        self.assertTrue(any("SECURE_SSL_REDIRECT" in error for error in errors))
        self.assertTrue(any("SECURE_HSTS_SECONDS" in error for error in errors))
        self.assertTrue(any("ALLOWED_HOSTS" in error for error in errors))
        self.assertTrue(any("CORS" in error for error in errors))
        self.assertTrue(any("__Host- refresh" in error for error in errors))
        self.assertTrue(any("__Host- access" in error for error in errors))

    def test_shared_environment_security_allows_documented_proxy_redirect_exception(self):
        errors = collect_shared_environment_security_errors(
            environment="staging",
            auth_refresh_cookie_secure=True,
            auth_access_cookie_secure=True,
            session_cookie_secure=True,
            csrf_cookie_secure=True,
            secure_ssl_redirect=False,
            secure_ssl_redirect_reverse_proxy_exemption=True,
            secure_hsts_seconds=3600,
            allowed_hosts=["staging.cchis.example"],
            cors_allow_all_origins=False,
            cors_allowed_origins=["https://staging.cchis.example"],
            auth_refresh_cookie_name="__Host-cchis_refresh",
            auth_refresh_cookie_path="/",
            auth_access_cookie_name="__Host-cchis_access",
            auth_access_cookie_path="/",
        )

        self.assertEqual(errors, [])


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
            feature_schema_version="baseline-v1",
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
            metadata={
                "source": "test",
                "algorithm": "logistic_regression",
                "promotion_target": "live_baseline",
                "promotion_state": "promoted",
                "phase_4_promotion_gates_passed": True,
                "run_purpose": "live_scoring",
                "execution_context": "test_fixture",
                "alert_eligible": True,
                "retraining_policy": "manual_promotion_only",
            },
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

    def import_active_migori_geometry(self, version_label: str = "test-managed-v1"):
        call_command("seed_kenya_administrative_areas", counties=["Migori"])
        call_command(
            "import_ward_geometry",
            version_label=version_label,
            activate=True,
            strict=True,
        )

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
        create_current_policy_acceptances(
            user,
            metadata={"accepted_via": "authenticated_api_test_fixture"},
        )
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


class TwoFactorRecoveryCodeServiceTestCase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="recovery_user",
            password="ChangeMe123!",
            email="recovery_user@example.com",
        )
        self.user.role = User.ROLE_ADMIN
        self.user.totp_secret = generate_totp_secret()
        self.user.is_totp_enabled = True
        self.user.save(update_fields=["role", "totp_secret", "is_totp_enabled"])

    def test_generate_recovery_codes_stores_hashes_not_plaintext(self):
        codes = generate_recovery_codes(self.user)

        self.assertEqual(len(codes), 10)
        self.assertEqual(TwoFactorRecoveryCode.objects.filter(user=self.user).count(), 10)
        first_code_record = TwoFactorRecoveryCode.objects.filter(user=self.user).first()

        self.assertNotEqual(first_code_record.code_hash, normalize_recovery_code(codes[0]))
        self.assertEqual(first_code_record.code_hint, normalize_recovery_code(first_code_record.code_hint))
        self.assertTrue(verify_recovery_code(self.user, codes[0]))

    def test_recovery_code_verification_normalizes_case_spaces_and_hyphens(self):
        code = generate_recovery_codes(self.user, count=1)[0]
        normalized = normalize_recovery_code(code)
        spaced_lower_code = f"{normalized[:5].lower()} {normalized[5:9].lower()}-{normalized[9:].lower()}"

        code_record = verify_recovery_code(self.user, spaced_lower_code)

        self.assertIsNotNone(code_record)
        self.assertEqual(code_record.user, self.user)

    def test_consume_recovery_code_makes_it_one_time_use(self):
        code = generate_recovery_codes(self.user, count=1)[0]
        code_record = verify_recovery_code(self.user, code)

        consumed_record = consume_recovery_code(code_record)

        self.assertIsNotNone(consumed_record)
        self.assertIsNotNone(consumed_record.used_at)
        self.assertIsNone(verify_recovery_code(self.user, code))

    def test_regenerating_recovery_codes_invalidates_old_unused_codes(self):
        old_code = generate_recovery_codes(self.user, count=1)[0]
        old_record = verify_recovery_code(self.user, old_code)
        new_code = generate_recovery_codes(self.user, count=1)[0]

        old_record.refresh_from_db()
        self.assertIsNotNone(old_record.invalidated_at)
        self.assertIsNone(verify_recovery_code(self.user, old_code))
        self.assertTrue(verify_recovery_code(self.user, new_code))

    def test_recovery_code_status_reports_latest_batch_counts(self):
        used_code = generate_recovery_codes(self.user, count=2)[0]
        consume_recovery_code(verify_recovery_code(self.user, used_code))

        status_payload = get_recovery_code_status(self.user)

        self.assertEqual(status_payload["remaining_count"], 1)
        self.assertEqual(status_payload["total_count"], 2)
        self.assertIsNotNone(status_payload["last_generated_at"])
        self.assertIsNotNone(status_payload["last_used_at"])
        self.assertTrue(status_payload["can_regenerate"])


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

    def test_login_sets_auth_cookies_for_direct_session(self):
        response = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        refresh_cookie = response.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
        access_cookie = response.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
        self.assertIsNotNone(refresh_cookie)
        self.assertIsNotNone(access_cookie)
        self.assertEqual(refresh_cookie.value, response.data["refresh"])
        self.assertEqual(access_cookie.value, response.data["access"])

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

    def test_verify_2fa_sets_auth_cookies(self):
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
        refresh_cookie = verify_response.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
        access_cookie = verify_response.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
        self.assertIsNotNone(refresh_cookie)
        self.assertIsNotNone(access_cookie)
        self.assertEqual(refresh_cookie.value, verify_response.data["refresh"])
        self.assertEqual(access_cookie.value, verify_response.data["access"])
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
        self.assertTrue(confirm_response.data["recovery_codes_generated"])
        self.assertEqual(len(confirm_response.data["recovery_codes"]), 10)
        cookie = confirm_response.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
        access_cookie = confirm_response.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
        self.assertIsNotNone(cookie)
        self.assertIsNotNone(access_cookie)
        self.assertEqual(cookie.value, confirm_response.data["refresh"])
        self.assertEqual(access_cookie.value, confirm_response.data["access"])
        unenrolled_admin.refresh_from_db()
        self.assertTrue(unenrolled_admin.is_totp_enabled)
        self.assertEqual(TwoFactorRecoveryCode.objects.filter(user=unenrolled_admin).count(), 10)

    def test_authenticated_optional_user_can_complete_two_factor_enrollment(self):
        analyst = self._create_user(
            username="analyst_setup",
            role=User.ROLE_ANALYST,
            ward=self.ward,
        )
        self.authenticate(analyst.username)
        self.client.credentials()

        setup_response = self.client.post(reverse("auth-2fa-setup"), {}, format="json")

        self.assertEqual(setup_response.status_code, status.HTTP_200_OK)
        self.assertIn("manual_entry_key", setup_response.data)

        confirm_response = self.client.post(
            reverse("auth-2fa-setup-confirm"),
            {"code": generate_current_totp_code(setup_response.data["manual_entry_key"])},
            format="json",
        )

        self.assertEqual(confirm_response.status_code, status.HTTP_200_OK)
        self.assertTrue(confirm_response.data["enrollment_completed"])
        self.assertTrue(confirm_response.data["recovery_codes_generated"])
        self.assertEqual(len(confirm_response.data["recovery_codes"]), 10)
        analyst.refresh_from_db()
        self.assertTrue(analyst.is_totp_enabled)

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

    def test_verify_2fa_accepts_unused_recovery_code_once(self):
        recovery_code = generate_recovery_codes(self.admin_user, count=2)[0]

        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )

        verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": login_response.data["temp_token"],
                "code": recovery_code,
            },
            format="json",
        )

        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_response.data["second_factor_method"], "recovery_code")
        self.assertEqual(verify_response.data["recovery_codes_remaining"], 1)
        self.assertFalse(verify_response.data["requires_2fa"])
        self.assertIsNone(verify_recovery_code(self.admin_user, recovery_code))
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_2FA_RECOVERY_CODE_USED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                target_user=self.admin_user,
                metadata__purpose="login",
            ).exists()
        )

    def test_verify_2fa_rejects_replayed_recovery_code(self):
        recovery_code = generate_recovery_codes(self.admin_user, count=2)[0]
        first_login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )

        first_verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": first_login_response.data["temp_token"],
                "code": recovery_code,
            },
            format="json",
        )

        self.assertEqual(first_verify_response.status_code, status.HTTP_200_OK)

        second_login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )
        replay_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": second_login_response.data["temp_token"],
                "code": recovery_code,
            },
            format="json",
        )

        self.assertEqual(replay_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(replay_response.data["detail"], "Invalid or expired code. Please try again.")
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_2FA_RECOVERY_CODE_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                target_user=self.admin_user,
                metadata__purpose="login",
                metadata__reason="invalid_code",
            ).exists()
        )

    def test_verify_2fa_records_invalid_recovery_code_failure_event(self):
        generate_recovery_codes(self.admin_user, count=2)
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )

        verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": login_response.data["temp_token"],
                "code": "CCHIS-NOT-A-REAL-CODE",
            },
            format="json",
        )

        self.assertEqual(verify_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_2FA_RECOVERY_CODE_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                target_user=self.admin_user,
                metadata__purpose="login",
                metadata__reason="invalid_code",
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

    def test_recovery_code_status_returns_counts_without_plaintext_codes(self):
        self.authenticate(self.admin_user.username)
        recovery_codes = generate_recovery_codes(self.admin_user, count=3)
        consume_recovery_code(verify_recovery_code(self.admin_user, recovery_codes[0]))

        response = self.client.get(reverse("auth-2fa-recovery-codes"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["remaining_count"], 2)
        self.assertEqual(response.data["total_count"], 3)
        self.assertTrue(response.data["can_regenerate"])
        self.assertNotIn("recovery_codes", response.data)

    def test_recovery_code_regeneration_requires_password_and_second_factor(self):
        self.authenticate(self.admin_user.username)
        old_recovery_code = generate_recovery_codes(self.admin_user, count=1)[0]
        old_record = verify_recovery_code(self.admin_user, old_recovery_code)

        response = self.client.post(
            reverse("auth-2fa-recovery-codes-regenerate"),
            {
                "current_password": self.password,
                "code": generate_current_totp_code(self.admin_user.totp_secret),
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["recovery_codes_generated"])
        self.assertEqual(len(response.data["recovery_codes"]), 10)
        self.assertEqual(response.data["remaining_count"], 10)
        old_record.refresh_from_db()
        self.assertIsNotNone(old_record.invalidated_at)
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_2FA_RECOVERY_CODES_REGENERATED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                target_user=self.admin_user,
            ).exists()
        )

    def test_recovery_code_regeneration_accepts_existing_recovery_code(self):
        self.authenticate(self.admin_user.username)
        authorizing_code = generate_recovery_codes(self.admin_user, count=2)[0]

        response = self.client.post(
            reverse("auth-2fa-recovery-codes-regenerate"),
            {
                "current_password": self.password,
                "code": authorizing_code,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["recovery_codes"]), 10)
        self.assertIsNone(verify_recovery_code(self.admin_user, authorizing_code))
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_2FA_RECOVERY_CODE_USED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                target_user=self.admin_user,
                metadata__purpose="recovery_code_regeneration",
            ).exists()
        )

    def test_invalid_recovery_code_regeneration_records_recovery_failure_event(self):
        self.authenticate(self.admin_user.username)
        generate_recovery_codes(self.admin_user, count=2)

        response = self.client.post(
            reverse("auth-2fa-recovery-codes-regenerate"),
            {
                "current_password": self.password,
                "code": "CCHIS-NOT-A-REAL-CODE",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_2FA_RECOVERY_CODE_FAILED,
                status=AuthAuditEvent.STATUS_FAILED,
                target_user=self.admin_user,
                metadata__purpose="recovery_code_regeneration",
                metadata__reason="invalid_code",
            ).exists()
        )

    def test_recovery_code_login_low_remaining_records_low_warning(self):
        recovery_code = generate_recovery_codes(self.admin_user, count=1)[0]

        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )

        verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": login_response.data["temp_token"],
                "code": recovery_code,
            },
            format="json",
        )

        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertEqual(verify_response.data["second_factor_method"], "recovery_code")
        self.assertEqual(verify_response.data["recovery_codes_remaining"], 0)
        self.assertTrue(verify_response.data["recovery_codes_low"])
        self.assertTrue(
            AuthAuditEvent.objects.filter(
                event_type=AuthAuditEvent.EVENT_2FA_RECOVERY_CODES_LOW,
                status=AuthAuditEvent.STATUS_SUCCESS,
                target_user=self.admin_user,
                metadata__purpose="login",
                metadata__remaining_count=0,
            ).exists()
        )

    def test_recovery_code_audit_metadata_excludes_secret_material(self):
        recovery_code = generate_recovery_codes(self.admin_user, count=1)[0]

        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.admin_user.username, "password": self.password},
            format="json",
        )

        verify_response = self.client.post(
            reverse("auth-verify-2fa"),
            {
                "token": login_response.data["temp_token"],
                "code": recovery_code,
            },
            format="json",
        )

        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        event = AuthAuditEvent.objects.filter(
            event_type=AuthAuditEvent.EVENT_2FA_RECOVERY_CODE_USED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            target_user=self.admin_user,
        ).latest("created_at")
        metadata_text = json.dumps(event.metadata)
        stored_hash = TwoFactorRecoveryCode.objects.get(user=self.admin_user).code_hash
        self.assertNotIn(recovery_code, metadata_text)
        self.assertNotIn(normalize_recovery_code(recovery_code), metadata_text)
        self.assertNotIn(stored_hash, metadata_text)
        self.assertNotIn("code_hash", metadata_text)

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
        self.assertIn("account_created_at", response.data)
        self.assertIn("last_login_at", response.data)
        self.assertEqual(
            response.data["profile_capabilities"],
            {
                "can_change_password": True,
                "can_update_appearance": True,
                "can_manage_totp": True,
                "can_view_own_activity": True,
                "can_update_identity": True,
                "can_review_sessions": False,
                "can_generate_profile_report": False,
                "identity_update_mode": "totp_step_up",
                "mode": "auth_contract_backed_profile",
            },
        )

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
        self.assertFalse(response.data["profile_capabilities"]["can_manage_totp"])
        self.assertTrue(response.data["profile_capabilities"]["can_change_password"])
        self.assertFalse(response.data["profile_capabilities"]["can_update_identity"])

    def test_me_activity_requires_authentication(self):
        response = self.client.get(reverse("auth-me-activity"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_activity_returns_only_current_user_events(self):
        self.authenticate(self.admin_user.username)
        own_event = AuthAuditEvent.objects.create(
            event_type=AuthAuditEvent.EVENT_PASSWORD_CHANGED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=self.admin_user,
            target_user=self.admin_user,
            ip_address="10.0.0.10",
            user_agent="sensitive-browser-fingerprint",
            metadata={"sensitive": "do-not-expose"},
        )
        other_user_event = AuthAuditEvent.objects.create(
            event_type=AuthAuditEvent.EVENT_LOGIN_SUCCESS,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=self.chv_user,
            target_user=self.chv_user,
        )

        response = self.client.get(reverse("auth-me-activity"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["capabilities"],
            {
                "can_view_own_activity": True,
                "mode": "self_scoped_auth_activity",
            },
        )
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)
        self.assertIn("filters", response.data)
        self.assertEqual(response.data["filters"]["security_only"], True)
        self.assertEqual(response.data["filters"]["include_refresh_events"], False)
        event_ids = {event["id"] for event in response.data["results"]}
        self.assertIn(own_event.id, event_ids)
        self.assertNotIn(other_user_event.id, event_ids)

        unsafe_fields = {
            "actor",
            "actor_username",
            "target_user",
            "target_username",
            "ward",
            "ward_name",
            "ip_address",
            "user_agent",
            "metadata",
        }
        for event in response.data["results"]:
            self.assertFalse(unsafe_fields.intersection(event.keys()))
            self.assertIn("title", event)
            self.assertIn("description", event)

        own_payload = next(
            event for event in response.data["results"] if event["id"] == own_event.id
        )
        self.assertEqual(own_payload["title"], "Password changed")
        self.assertEqual(own_payload["description"], "Your account password was changed.")

    def test_me_activity_paginates_and_caps_requested_page_size(self):
        self.authenticate(self.chv_user.username)
        for _ in range(55):
            AuthAuditEvent.objects.create(
                event_type=AuthAuditEvent.EVENT_PASSWORD_CHANGED,
                status=AuthAuditEvent.STATUS_SUCCESS,
                actor=self.chv_user,
                target_user=self.chv_user,
            )

        response = self.client.get(reverse("auth-me-activity"), {"page_size": "100"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["filters"]["page"], 1)
        self.assertEqual(response.data["filters"]["page_size"], 50)
        self.assertLessEqual(len(response.data["results"]), 50)
        self.assertGreaterEqual(response.data["count"], 55)
        self.assertIsNotNone(response.data["next"])

    def test_me_activity_hides_refresh_success_by_default(self):
        self.authenticate(self.chv_user.username)
        refresh_success = AuthAuditEvent.objects.create(
            event_type=AuthAuditEvent.EVENT_REFRESH_SUCCESS,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=self.chv_user,
            target_user=self.chv_user,
        )
        refresh_failed = AuthAuditEvent.objects.create(
            event_type=AuthAuditEvent.EVENT_REFRESH_FAILED,
            status=AuthAuditEvent.STATUS_FAILED,
            actor=self.chv_user,
            target_user=self.chv_user,
        )

        default_response = self.client.get(reverse("auth-me-activity"))

        self.assertEqual(default_response.status_code, status.HTTP_200_OK)
        default_ids = {event["id"] for event in default_response.data["results"]}
        self.assertNotIn(refresh_success.id, default_ids)
        self.assertIn(refresh_failed.id, default_ids)

        expanded_response = self.client.get(
            reverse("auth-me-activity"),
            {"include_refresh_events": "true"},
        )

        self.assertEqual(expanded_response.status_code, status.HTTP_200_OK)
        expanded_ids = {event["id"] for event in expanded_response.data["results"]}
        self.assertIn(refresh_success.id, expanded_ids)

    def test_me_activity_filters_by_event_status_and_dates(self):
        self.authenticate(self.admin_user.username)
        older_event = AuthAuditEvent.objects.create(
            event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
            status=AuthAuditEvent.STATUS_FAILED,
            actor=self.admin_user,
            target_user=self.admin_user,
        )
        matching_event = AuthAuditEvent.objects.create(
            event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
            status=AuthAuditEvent.STATUS_FAILED,
            actor=self.admin_user,
            target_user=self.admin_user,
        )
        other_status_event = AuthAuditEvent.objects.create(
            event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=self.admin_user,
            target_user=self.admin_user,
        )
        other_user_event = AuthAuditEvent.objects.create(
            event_type=AuthAuditEvent.EVENT_LOGIN_FAILED,
            status=AuthAuditEvent.STATUS_FAILED,
            actor=self.chv_user,
            target_user=self.chv_user,
        )
        now = timezone.now()
        today = timezone.localdate(now)
        yesterday = today - timedelta(days=1)
        AuthAuditEvent.objects.filter(pk=older_event.pk).update(created_at=timezone.now() - timedelta(days=5))
        AuthAuditEvent.objects.filter(pk=matching_event.pk).update(created_at=now)
        AuthAuditEvent.objects.filter(pk=other_status_event.pk).update(created_at=now)
        AuthAuditEvent.objects.filter(pk=other_user_event.pk).update(created_at=now)

        response = self.client.get(
            reverse("auth-me-activity"),
            {
                "event_type": AuthAuditEvent.EVENT_LOGIN_FAILED,
                "status": AuthAuditEvent.STATUS_FAILED,
                "date_from": yesterday.isoformat(),
                "date_to": today.isoformat(),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event_ids = {event["id"] for event in response.data["results"]}
        self.assertIn(matching_event.id, event_ids)
        self.assertNotIn(older_event.id, event_ids)
        self.assertNotIn(other_status_event.id, event_ids)
        self.assertNotIn(other_user_event.id, event_ids)
        self.assertEqual(response.data["filters"]["event_type"], AuthAuditEvent.EVENT_LOGIN_FAILED)
        self.assertEqual(response.data["filters"]["status"], AuthAuditEvent.STATUS_FAILED)
        self.assertEqual(response.data["filters"]["date_from"], yesterday.isoformat())
        self.assertEqual(response.data["filters"]["date_to"], today.isoformat())

    def test_me_activity_rejects_invalid_filters(self):
        self.authenticate(self.admin_user.username)

        response = self.client.get(
            reverse("auth-me-activity"),
            {"event_type": "NOT_REAL"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("event_type", response.data)

        response = self.client.get(
            reverse("auth-me-activity"),
            {"date_from": "2026-05-03", "date_to": "2026-05-02"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("date_to", response.data)

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

    def test_session_returns_authenticated_user_for_valid_access_cookie(self):
        login_response = self.client.post(
            reverse("auth-login"),
            {"username": self.chv_user.username, "password": self.password},
            format="json",
        )

        self.client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = login_response.data["access"]
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

        self.client.cookies.pop(settings.AUTH_ACCESS_COOKIE_NAME, None)
        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = verify_response.data["refresh"]
        response = self.client.get(reverse("auth-session"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["authenticated"])
        self.assertEqual(response.data["session_source"], "refresh")
        self.assertEqual(response.data["user"]["id"], self.admin_user.id)
        self.assertIsNone(response.data["access"])
        access_cookie = response.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
        self.assertIsNotNone(access_cookie)
        self.assertTrue(access_cookie.value)

    @override_settings(
        AUTH_REFRESH_COOKIE_NAME="__Host-cchis_refresh",
        AUTH_REFRESH_COOKIE_LEGACY_NAMES=("cchis_refresh",),
        AUTH_REFRESH_COOKIE_SECURE=True,
    )
    def test_session_bootstrap_migrates_legacy_refresh_cookie_name(self):
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

        self.client.cookies.pop(settings.AUTH_REFRESH_COOKIE_NAME, None)
        self.client.cookies.pop(settings.AUTH_ACCESS_COOKIE_NAME, None)
        self.client.cookies["cchis_refresh"] = verify_response.data["refresh"]
        response = self.client.get(reverse("auth-session"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["authenticated"])
        self.assertEqual(response.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value, verify_response.data["refresh"])
        self.assertEqual(response.cookies["cchis_refresh"].value, "")

    def test_session_returns_unauthenticated_without_session(self):
        response = self.client.get(reverse("auth-session"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["authenticated"])
        self.assertIsNone(response.data["user"])
        self.assertIsNone(response.data["access"])

    def test_session_clears_invalid_refresh_cookie(self):
        self.client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = "bad-refresh-token"
        self.client.cookies[settings.AUTH_ACCESS_COOKIE_NAME] = "bad-access-token"
        response = self.client.get(reverse("auth-session"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["authenticated"])
        self.assertEqual(response.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value, "")
        self.assertEqual(response.cookies[settings.AUTH_ACCESS_COOKIE_NAME].value, "")

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
        self.assertEqual(logout_response.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value, "")
        self.assertEqual(logout_response.cookies[settings.AUTH_ACCESS_COOKIE_NAME].value, "")

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
        self.assertEqual(logout_response.cookies[settings.AUTH_ACCESS_COOKIE_NAME].value, "")

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
        refresh_cookie = refresh_response.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
        access_cookie = refresh_response.cookies.get(settings.AUTH_ACCESS_COOKIE_NAME)
        self.assertIsNotNone(refresh_cookie)
        self.assertIsNotNone(access_cookie)
        self.assertEqual(refresh_cookie.value, refresh_response.data["refresh"])
        self.assertEqual(access_cookie.value, refresh_response.data["access"])

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

    def test_change_password_requires_strong_new_password(self):
        self.authenticate(self.chv_user.username)
        response = self.client.post(
            reverse("auth-change-password"),
            {
                "current_password": self.password,
                "new_password": "longpasswordonly",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Validation error.")
        self.assertIn("new_password", response.data["errors"])
        self.assertIn("uppercase", " ".join(response.data["errors"]["new_password"]).lower())

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

    def test_password_reset_confirm_requires_strong_new_password(self):
        token_record = PasswordResetToken.objects.create(
            user=self.chv_user,
            token="weak-reset-token-123",
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(
            reverse("auth-password-reset-confirm"),
            {"token": token_record.token, "new_password": "longpasswordonly"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Validation error.")
        self.assertIn("new_password", response.data["errors"])
        self.assertIn("uppercase", " ".join(response.data["errors"]["new_password"]).lower())

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
        self.assertEqual(VerifyTwoFactorAPIView.throttle_scope, "auth_2fa")
        self.assertEqual(LogoutAPIView.throttle_scope, "auth_write")
        self.assertEqual(ChangePasswordAPIView.throttle_scope, "auth_write")
        self.assertEqual(DeactivateUserAPIView.throttle_scope, "auth_write")
        self.assertEqual(ReactivateUserAPIView.throttle_scope, "auth_write")
        self.assertEqual(RegenerateTwoFactorRecoveryCodesAPIView.throttle_scope, "auth_2fa")
        self.assertEqual(RegenerateTwoFactorRecoveryCodesAPIView.secondary_throttle_scope, "auth_write")
        throttle_class_names = {
            klass.__name__ for klass in RegenerateTwoFactorRecoveryCodesAPIView.throttle_classes
        }
        self.assertIn("AuthScopedRateThrottle", throttle_class_names)
        self.assertIn("SecondaryAuthScopedRateThrottle", throttle_class_names)
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

    def test_analyst_can_view_ward_intelligence_summary(self):
        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Ward intelligence alert",
            status=Alert.STATUS_DELIVERED,
        )
        RiskScore.objects.create(
            ward=self.ward,
            model_run=self.model_run,
            score=0.72,
            risk_level=Ward.RISK_MEDIUM,
            rainfall_mm=78.0,
            flood_indicator=0.3,
            predicted_cases=11,
            source=RiskScore.SOURCE_MODEL,
            model_version="v0-test",
            generated_at=timezone.now() - timedelta(hours=6),
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("ward-intelligence", kwargs={"pk": self.ward.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["ward"]["id"], self.ward.id)
        self.assertEqual(response.data["current_risk"]["risk_level"], Ward.RISK_HIGH)
        self.assertEqual(response.data["trend"]["mode"], "derived_from_recent_history")
        self.assertEqual(response.data["driver_summary"]["mode"], "derived_from_latest_record")
        self.assertEqual(response.data["guidance_summary"]["mode"], "static_risk_playbook")
        self.assertEqual(response.data["workflow"]["status"], "TRIGGER_ACTIVE")
        self.assertEqual(response.data["workflow"]["status_label"], "Trigger active")
        self.assertEqual(response.data["decision_summary"]["action_required"], False)
        self.assertEqual(response.data["decision_summary"]["primary_cta_kind"], "REVIEW_TRIGGER")
        self.assertEqual(response.data["header_context"]["trigger_state"], "TRIGGER_ACTIVE")
        self.assertEqual(response.data["header_context"]["freshness_state"], "FRESH")
        self.assertGreaterEqual(len(response.data["risk_history"]), 2)
        self.assertEqual(response.data["freshness"]["alert_count"], 1)

    def test_ward_intelligence_marks_review_pending_workflow_as_action_required(self):
        self.ward.alerts.all().delete()
        self.ward.current_risk_level = Ward.RISK_HIGH
        self.ward.current_risk_score = 0.87
        self.ward.save(update_fields=["current_risk_level", "current_risk_score", "updated_at"])

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("ward-intelligence", kwargs={"pk": self.ward.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["workflow"]["status"], "REVIEW_PENDING")
        self.assertEqual(response.data["workflow"]["status_label"], "Awaiting review")
        self.assertEqual(response.data["workflow"]["eligible_actions"][0], "REVIEW_TRIGGER")
        self.assertEqual(response.data["decision_summary"]["action_required"], True)
        self.assertEqual(response.data["decision_summary"]["headline"], "Action required. Review active alerts and trigger status.")
        self.assertEqual(response.data["decision_summary"]["primary_cta_kind"], "REVIEW_TRIGGER")
        self.assertEqual(response.data["decision_summary"]["next_steps"][0], "Review trigger")
        self.assertEqual(response.data["header_context"]["trigger_state"], "REVIEW_PENDING")
        self.assertEqual(response.data["header_context"]["expected_cases_7d"], self.risk_score.predicted_cases)

    def test_ward_intelligence_exposes_none_state_when_no_trigger_is_active(self):
        self.ward.alerts.all().delete()
        self.ward.current_risk_level = Ward.RISK_LOW
        self.ward.current_risk_score = 0.22
        self.ward.save(update_fields=["current_risk_level", "current_risk_score", "updated_at"])
        RiskScore.objects.create(
            ward=self.ward,
            model_run=self.model_run,
            score=0.22,
            risk_level=Ward.RISK_LOW,
            rainfall_mm=18.0,
            flood_indicator=0.0,
            predicted_cases=1,
            source=RiskScore.SOURCE_MODEL,
            model_version="v0-test",
            generated_at=timezone.now() + timedelta(minutes=1),
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("ward-intelligence", kwargs={"pk": self.ward.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["workflow"]["status"], "NONE")
        self.assertEqual(response.data["workflow"]["status_label"], "No active trigger")
        self.assertIn("OPEN_TRIGGER_FLOW", response.data["workflow"]["eligible_actions"])
        self.assertEqual(response.data["decision_summary"]["action_required"], False)
        self.assertEqual(response.data["decision_summary"]["primary_cta_kind"], "OPEN_TRIGGER_FLOW")
        self.assertEqual(response.data["decision_summary"]["next_steps"][0], "Open Trigger Flow")
        self.assertEqual(response.data["header_context"]["trigger_state"], "NONE")

    def test_supervisor_cannot_view_out_of_scope_ward_intelligence(self):
        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("ward-intelligence", kwargs={"pk": self.ward.id}))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_latest_ward_risk_supports_search_and_sub_county_filters(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("latest-ward-risk"), {"q": "kadem", "sub_county": "Nyatike"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["ward_name"], "North Kadem")

    def test_admin_can_view_migori_ward_map_with_backend_counts_and_hardened_metadata(self):
        self.import_active_migori_geometry("test-admin-map-v1")
        RiskScore.objects.create(
            ward=self.ward,
            model_run=self.model_run,
            score=0.72,
            risk_level=Ward.RISK_MEDIUM,
            rainfall_mm=88.0,
            flood_indicator=0.5,
            predicted_cases=11,
            source=RiskScore.SOURCE_MODEL,
            model_version="v0-test",
            generated_at=self.risk_score.generated_at - timedelta(hours=12),
        )
        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Map alert",
            status=Alert.STATUS_DELIVERED,
        )
        HealthFacility.objects.create(
            name="North Kadem Dispensary",
            facility_code="TEST-HF-002",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
        )
        CHV.objects.create(
            name="Kadem CHV",
            phone_number="+254700000002",
            ward=self.other_ward,
            is_active=True,
            language="sw",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("migori-ward-map"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["type"], "FeatureCollection")
        self.assertEqual(response.data["metadata"]["geometry_feature_count"], 40)
        self.assertEqual(response.data["metadata"]["expected_ward_count"], 40)
        self.assertEqual(response.data["metadata"]["returned_feature_count"], 40)
        self.assertEqual(response.data["metadata"]["missing_source_wards"], [])
        self.assertEqual(response.data["metadata"]["matching_strategy"], "ward_code_then_name")
        self.assertFalse(response.data["metadata"]["placeholder_geometry_detected"])
        self.assertEqual(response.data["metadata"]["geometry_source"], "managed:migori-ward-boundaries:test-admin-map-v1")
        self.assertEqual(response.data["metadata"]["dataset_slug"], "migori-ward-boundaries")
        self.assertEqual(response.data["metadata"]["dataset_version_label"], "test-admin-map-v1")
        self.assertEqual(
            response.data["metadata"]["model_alignment"]["current_live_baseline"]["algorithm"],
            "logistic_regression",
        )
        self.assertEqual(
            response.data["metadata"]["model_alignment"]["dashboard_policy"]["surface_only_promoted_outputs"],
            True,
        )

        north_kamagambo = next(
            feature for feature in response.data["features"] if feature["properties"]["name"] == self.ward.name
        )
        self.assertEqual(north_kamagambo["properties"]["backend_ward_id"], self.ward.id)
        self.assertEqual(north_kamagambo["properties"]["matching_source"], "ward_code")
        self.assertEqual(north_kamagambo["properties"]["chv_count"], 1)
        self.assertEqual(north_kamagambo["properties"]["active_chv_count"], 1)
        self.assertEqual(north_kamagambo["properties"]["alert_count"], 1)
        self.assertEqual(north_kamagambo["properties"]["facility_count"], 1)
        self.assertEqual(north_kamagambo["properties"]["current_risk_level"], self.ward.current_risk_level)
        self.assertEqual(north_kamagambo["properties"]["current_risk_score"], self.ward.current_risk_score)
        self.assertEqual(north_kamagambo["properties"]["risk_level"], Ward.RISK_HIGH)
        self.assertTrue(north_kamagambo["properties"]["prediction"]["available"])
        self.assertEqual(north_kamagambo["properties"]["prediction"]["horizon_days"], 7)
        self.assertEqual(
            north_kamagambo["properties"]["prediction"]["predicted_risk_level"],
            self.risk_score.risk_level,
        )
        self.assertEqual(
            north_kamagambo["properties"]["prediction"]["predicted_risk_score"],
            self.risk_score.score,
        )
        self.assertEqual(
            north_kamagambo["properties"]["prediction"]["predicted_cases"],
            self.risk_score.predicted_cases,
        )
        self.assertEqual(
            north_kamagambo["properties"]["prediction"]["prediction_model_version"],
            self.risk_score.model_version,
        )
        self.assertEqual(north_kamagambo["properties"]["trend"]["direction"], "up")
        self.assertEqual(north_kamagambo["properties"]["trend"]["delta_points"], 14)
        self.assertEqual(
            north_kamagambo["properties"]["trend"]["label"],
            "+14 points vs previous run",
        )

    def test_supervisor_map_scope_is_limited_to_assigned_ward_geometry(self):
        self.import_active_migori_geometry("test-supervisor-map-v1")
        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("migori-ward-map"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["metadata"]["returned_feature_count"], 1)
        self.assertEqual(response.data["features"][0]["properties"]["name"], self.other_ward.name)
        self.assertEqual(response.data["features"][0]["properties"]["backend_ward_id"], self.other_ward.id)

    def test_ward_detail_prefers_promoted_model_output_over_newer_benchmark_output(self):
        benchmark_run = ModelRun.objects.create(
            algorithm_name="random-forest-benchmark",
            model_version="rf-shadow-v1",
            status=ModelRun.STATUS_SUCCESS,
            month=4,
            feature_schema_version="baseline-v1",
            feature_keys=self.model_run.feature_keys,
            training_dataset_ref="rf-shadow-training",
            inference_dataset_ref="rf-shadow-inference",
            training_row_count=8,
            inference_row_count=2,
            evaluation_metrics={"training_accuracy": 0.95},
            metadata={
                "algorithm": "random_forest",
                "promotion_target": "benchmark_only",
                "execution_context": "manual_command",
                "run_purpose": "benchmark_scoring",
            },
            completed_at=timezone.now(),
        )
        RiskScore.objects.create(
            ward=self.ward,
            model_run=benchmark_run,
            score=0.97,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=150.0,
            flood_indicator=0.9,
            predicted_cases=20,
            source=RiskScore.SOURCE_MODEL,
            model_version="rf-shadow-v1",
            generated_at=timezone.now(),
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("ward-detail", kwargs={"pk": self.ward.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["latest_model_version"], "v0-test")

    def test_ward_detail_rejects_ungated_live_baseline_metadata(self):
        ungated_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="lr-ungated-live-v1",
            status=ModelRun.STATUS_SUCCESS,
            month=4,
            feature_schema_version="baseline-v1",
            feature_keys=self.model_run.feature_keys,
            training_dataset_ref="ungated-training",
            inference_dataset_ref="ungated-inference",
            training_row_count=8,
            inference_row_count=2,
            evaluation_metrics={"training_accuracy": 0.99},
            metadata={
                "algorithm": "logistic_regression",
                "promotion_target": "live_baseline",
                "promotion_state": "promoted",
                "alert_eligible": True,
                "execution_context": "manual_command",
                "run_purpose": "live_scoring",
            },
            completed_at=timezone.now(),
        )
        RiskScore.objects.create(
            ward=self.ward,
            model_run=ungated_run,
            score=0.99,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=160.0,
            flood_indicator=0.95,
            predicted_cases=22,
            source=RiskScore.SOURCE_MODEL,
            model_version="lr-ungated-live-v1",
            generated_at=timezone.now() + timedelta(minutes=5),
        )

        self.authenticate(self.analyst_user.username)
        detail_response = self.client.get(reverse("ward-detail", kwargs={"pk": self.ward.id}))
        alignment_response = self.client.get(reverse("model-alignment"))

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["latest_model_version"], "v0-test")
        self.assertEqual(alignment_response.status_code, status.HTTP_200_OK)
        self.assertEqual(alignment_response.data["current_live_baseline"]["model_version"], "v0-test")

    def test_model_alignment_endpoint_exposes_backend_truth_surface(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("model-alignment"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["current_live_baseline"]["algorithm"], "logistic_regression")
        self.assertEqual(response.data["current_benchmark_model"]["algorithm"], None)
        self.assertIn("xgboost", response.data["future_candidate_models"])
        self.assertTrue(response.data["dashboard_policy"]["surface_only_promoted_outputs"])

    def test_model_alignment_endpoint_exposes_current_benchmark_model_when_present(self):
        benchmark_run = ModelRun.objects.create(
            algorithm_name="random-forest-benchmark",
            model_version="rf-alignment-v1",
            status=ModelRun.STATUS_SUCCESS,
            month=4,
            feature_schema_version="baseline-v1",
            feature_keys=self.model_run.feature_keys,
            training_dataset_ref="rf-alignment-training",
            inference_dataset_ref="rf-alignment-inference",
            training_row_count=8,
            inference_row_count=2,
            evaluation_metrics={"training_accuracy": 0.93},
            metadata={
                "algorithm": "random_forest",
                "promotion_target": "benchmark_only",
                "execution_context": "manual_command",
                "run_purpose": "benchmark_scoring",
            },
            completed_at=timezone.now(),
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("model-alignment"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["current_benchmark_model"]["algorithm"], "random_forest")
        self.assertEqual(response.data["current_benchmark_model"]["model_version"], benchmark_run.model_version)

    def test_latest_ward_risk_prefers_promoted_output_over_newer_benchmark_output(self):
        benchmark_run = ModelRun.objects.create(
            algorithm_name="random-forest-benchmark",
            model_version="rf-latest-risk-v1",
            status=ModelRun.STATUS_SUCCESS,
            month=4,
            feature_schema_version="baseline-v1",
            feature_keys=self.model_run.feature_keys,
            training_dataset_ref="rf-latest-risk-training",
            inference_dataset_ref="rf-latest-risk-inference",
            training_row_count=8,
            inference_row_count=2,
            evaluation_metrics={"training_accuracy": 0.94},
            metadata={
                "algorithm": "random_forest",
                "promotion_target": "benchmark_only",
                "execution_context": "manual_command",
                "run_purpose": "benchmark_scoring",
            },
            completed_at=timezone.now(),
        )
        RiskScore.objects.create(
            ward=self.ward,
            model_run=benchmark_run,
            score=0.98,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=160.0,
            flood_indicator=0.95,
            predicted_cases=22,
            source=RiskScore.SOURCE_MODEL,
            model_version="rf-latest-risk-v1",
            generated_at=timezone.now(),
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("latest-ward-risk"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ward_payload = next(item for item in response.data if item["ward_id"] == self.ward.id)
        self.assertEqual(ward_payload["risk_score"], self.risk_score.score)
        self.assertEqual(ward_payload["predicted_cases"], self.risk_score.predicted_cases)

    def test_ward_intelligence_prefers_promoted_output_over_newer_benchmark_output(self):
        benchmark_run = ModelRun.objects.create(
            algorithm_name="random-forest-benchmark",
            model_version="rf-ward-intel-v1",
            status=ModelRun.STATUS_SUCCESS,
            month=4,
            feature_schema_version="baseline-v1",
            feature_keys=self.model_run.feature_keys,
            training_dataset_ref="rf-ward-intel-training",
            inference_dataset_ref="rf-ward-intel-inference",
            training_row_count=8,
            inference_row_count=2,
            evaluation_metrics={"training_accuracy": 0.96},
            metadata={
                "algorithm": "random_forest",
                "promotion_target": "benchmark_only",
                "execution_context": "manual_command",
                "run_purpose": "benchmark_scoring",
            },
            completed_at=timezone.now(),
        )
        RiskScore.objects.create(
            ward=self.ward,
            model_run=benchmark_run,
            score=0.99,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=170.0,
            flood_indicator=0.99,
            predicted_cases=24,
            source=RiskScore.SOURCE_MODEL,
            model_version="rf-ward-intel-v1",
            generated_at=timezone.now(),
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("ward-intelligence", kwargs={"pk": self.ward.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["current_risk"]["model_version"], self.risk_score.model_version)
        self.assertEqual(response.data["current_risk"]["predicted_cases"], self.risk_score.predicted_cases)

    def test_facility_intelligence_prefers_promoted_output_over_newer_benchmark_output(self):
        benchmark_run = ModelRun.objects.create(
            algorithm_name="random-forest-benchmark",
            model_version="rf-facility-v1",
            status=ModelRun.STATUS_SUCCESS,
            month=4,
            feature_schema_version="baseline-v1",
            feature_keys=self.model_run.feature_keys,
            training_dataset_ref="rf-facility-training",
            inference_dataset_ref="rf-facility-inference",
            training_row_count=8,
            inference_row_count=2,
            evaluation_metrics={"training_accuracy": 0.92},
            metadata={
                "algorithm": "random_forest",
                "promotion_target": "benchmark_only",
                "execution_context": "manual_command",
                "run_purpose": "benchmark_scoring",
            },
            completed_at=timezone.now(),
        )
        RiskScore.objects.create(
            ward=self.ward,
            model_run=benchmark_run,
            score=0.97,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=155.0,
            flood_indicator=0.88,
            predicted_cases=21,
            source=RiskScore.SOURCE_MODEL,
            model_version="rf-facility-v1",
            generated_at=timezone.now(),
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-intelligence", kwargs={"pk": self.health_facility.id}))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["readiness"]["projected_cases"], self.risk_score.predicted_cases)
        self.assertEqual(response.data["context"]["ward_risk_score"], self.risk_score.score)

    def test_migori_ward_map_exposes_recent_history_trend_when_multiple_runs_exist(self):
        self.import_active_migori_geometry("test-admin-map-history-v1")
        RiskScore.objects.create(
            ward=self.ward,
            model_run=self.model_run,
            score=0.79,
            risk_level=Ward.RISK_MEDIUM,
            rainfall_mm=83.0,
            flood_indicator=0.5,
            predicted_cases=12,
            source=RiskScore.SOURCE_MODEL,
            model_version="v0-test",
            generated_at=self.risk_score.generated_at - timedelta(hours=8),
        )
        RiskScore.objects.create(
            ward=self.ward,
            model_run=self.model_run,
            score=0.68,
            risk_level=Ward.RISK_MEDIUM,
            rainfall_mm=74.0,
            flood_indicator=0.4,
            predicted_cases=9,
            source=RiskScore.SOURCE_MODEL,
            model_version="v0-test",
            generated_at=self.risk_score.generated_at - timedelta(hours=16),
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("migori-ward-map"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        north_kamagambo = next(
            feature for feature in response.data["features"] if feature["properties"]["name"] == self.ward.name
        )
        self.assertEqual(
            north_kamagambo["properties"]["trend"]["label"],
            "Escalating across recent runs (+18 points)",
        )
        self.assertEqual(north_kamagambo["properties"]["trend"]["direction"], "up")
        self.assertEqual(north_kamagambo["properties"]["trend"]["delta_points"], 18)
        self.assertEqual(
            north_kamagambo["properties"]["trend"]["mode"],
            "derived_from_recent_history_window",
        )

    def test_migori_ward_map_exposes_facility_forecast_dashboard_summary_honestly(self):
        self.import_active_migori_geometry("test-admin-map-forecast-v1")
        run_facility_burden_forecast_pipeline(
            model_version="fnb-v1",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("migori-ward-map"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["metadata"]["facility_forecasting"]["source_kind"], "preview_available_but_blocked")
        self.assertEqual(response.data["metadata"]["facility_forecasting"]["governance_mode"], "preview_only_not_promoted")
        self.assertEqual(
            response.data["metadata"]["facility_forecasting"]["dashboard_truth_state"],
            "blocked_until_promotion",
        )
        self.assertIn(self.ward.id, response.data["metadata"]["facility_forecasting"]["preview_driving_ward_ids"])
        self.assertEqual(response.data["metadata"]["facility_forecasting"]["driving_ward_ids"], [])

        north_kamagambo = next(
            feature for feature in response.data["features"] if feature["properties"]["name"] == self.ward.name
        )
        self.assertFalse(north_kamagambo["properties"]["drives_promoted_facility_pressure"])
        self.assertTrue(north_kamagambo["properties"]["drives_facility_pressure_preview"])
        self.assertEqual(
            north_kamagambo["properties"]["facility_forecast_dashboard_truth_state"],
            "blocked_until_promotion",
        )

    def test_migori_ward_map_uses_promoted_facility_forecast_outputs_when_available(self):
        self.import_active_migori_geometry("test-admin-map-forecast-promoted-v1")
        run = run_facility_burden_forecast_pipeline(
            model_version="fnb-promoted-v1",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )
        call_command(
            "promote_facility_burden_forecast",
            run_id=run.id,
            promoted_by="audit",
            note="External audit promotion test",
            allow_blocked_promotion=True,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("migori-ward-map"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["metadata"]["facility_forecasting"]["source_kind"], "promoted_forecast")
        self.assertEqual(response.data["metadata"]["facility_forecasting"]["governance_mode"], "promoted")
        self.assertEqual(response.data["metadata"]["facility_forecasting"]["dashboard_truth_state"], "promoted")
        self.assertEqual(response.data["metadata"]["facility_forecasting"]["blocked_product_surfaces"], [])
        self.assertIn(self.ward.id, response.data["metadata"]["facility_forecasting"]["driving_ward_ids"])

        north_kamagambo = next(
            feature for feature in response.data["features"] if feature["properties"]["name"] == self.ward.name
        )
        self.assertTrue(north_kamagambo["properties"]["drives_promoted_facility_pressure"])
        self.assertTrue(north_kamagambo["properties"]["drives_facility_pressure_preview"])
        self.assertEqual(north_kamagambo["properties"]["facility_forecast_dashboard_truth_state"], "promoted")

    def test_migori_ward_map_prefers_promoted_facility_forecast_over_newer_preview_run(self):
        self.import_active_migori_geometry("test-admin-map-forecast-promoted-precedence-v1")
        promoted_run = run_facility_burden_forecast_pipeline(
            model_version="fnb-promoted-map-v1",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )
        call_command(
            "promote_facility_burden_forecast",
            run_id=promoted_run.id,
            promoted_by="audit",
            note="Map promotion precedence test",
            allow_blocked_promotion=True,
        )
        run_facility_burden_forecast_pipeline(
            model_version="fnb-preview-map-v2",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("migori-ward-map"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["metadata"]["facility_forecasting"]["source_kind"], "promoted_forecast")
        self.assertEqual(response.data["metadata"]["facility_forecasting"]["dashboard_truth_state"], "promoted")
        self.assertEqual(response.data["metadata"]["facility_forecasting"]["blocked_product_surfaces"], [])
        self.assertIn(self.ward.id, response.data["metadata"]["facility_forecasting"]["driving_ward_ids"])

        north_kamagambo = next(
            feature for feature in response.data["features"] if feature["properties"]["name"] == self.ward.name
        )
        self.assertTrue(north_kamagambo["properties"]["drives_promoted_facility_pressure"])
        self.assertTrue(north_kamagambo["properties"]["drives_facility_pressure_preview"])
        self.assertEqual(north_kamagambo["properties"]["facility_forecast_dashboard_truth_state"], "promoted")

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

    def test_admin_can_view_chv_operations_snapshot(self):
        UssdSessionLog.objects.create(
            session_id="sess-001",
            phone_number=self.chv.phone_number,
            ward=self.ward,
            text="1*2",
            response_text="OK",
            menu_level="advice",
        )
        TriageSession.objects.create(
            channel="API",
            phone_number=self.chv.phone_number,
            ward=self.ward,
            referral_facility=self.health_facility,
            recommendation="Refer now",
            referral_needed=True,
        )
        SyncQueue.objects.create(
            source_device_id="device-1",
            client_submission_id="sync-001",
            phone_number=self.chv.phone_number,
            ward=self.ward,
            payload={"client_submission_id": "sync-001"},
            status=SyncQueue.STATUS_PROCESSED,
            processed_at=timezone.now(),
        )
        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Ward alert",
            status=Alert.STATUS_DELIVERED,
        )

        self.authenticate(self.admin_user.username)
        with patch("risk.services.resolve_chv_message_mode", return_value="SEND"), patch(
            "risk.services.resolve_chv_message_delivery_kind", return_value="SIMULATED"
        ):
            response = self.client.get(reverse("chv-operations"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        row = response.data[0]
        self.assertEqual(row["id"], self.chv.id)
        self.assertEqual(str(row["public_id"]), str(self.chv.public_id))
        self.assertEqual(row["operational_status"], "ACTIVE")
        self.assertEqual(row["sync_health"], "ONLINE")
        self.assertEqual(row["triage_sessions_24h"], 1)
        self.assertEqual(row["referrals_24h"], 1)
        self.assertEqual(row["sync_payloads_24h"], 1)
        self.assertEqual(row["ussd_sessions_24h"], 1)
        self.assertEqual(row["ward_alerts_total"], 1)
        self.assertEqual(row["ward_alerts_delivered"], 1)
        self.assertTrue(row["can_message"])
        self.assertEqual(row["message_mode"], "SEND")
        self.assertEqual(row["message_delivery_kind"], "SIMULATED")
        self.assertTrue(row["can_view_activity"])

    def test_supervisor_chv_operations_snapshot_is_scoped_to_assigned_ward(self):
        CHV.objects.create(
            name="Other Ward CHV",
            phone_number="+254700000010",
            ward=self.other_ward,
            is_active=True,
            language="en",
        )

        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("chv-operations"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["ward"], self.other_ward.id)

    def test_admin_can_view_chv_activity_history(self):
        CHVMessage.objects.create(
            chv=self.chv,
            ward=self.ward,
            sent_by=self.admin_user,
            channel=CHVMessage.CHANNEL_SMS,
            message_body="Simulated message",
            status=CHVMessage.STATUS_SENT,
            delivery_kind=CHVMessage.DELIVERY_KIND_SIMULATED,
            delivery_backend="stub",
            provider_reference="stub-123",
        )
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_APPROVED,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Coverage request ready for assignment.",
            requested_chv_count=1,
        )
        assignment = CHVAssignment.objects.create(
            coverage_request=request_record,
            ward=self.ward,
            chv=self.chv,
            assigned_by=self.admin_user,
            status=CHVAssignment.STATUS_ACTIVE,
        )
        CHVCoverageRequestEvent.objects.create(
            coverage_request=request_record,
            assignment=assignment,
            actor=self.admin_user,
            action=CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CREATED,
            new_status=CHVCoverageRequest.STATUS_APPROVED,
            detail="Assigned to North Kamagambo coverage request.",
        )
        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Ward alert",
            status=Alert.STATUS_DELIVERED,
        )
        SyncQueue.objects.create(
            source_device_id="device-1",
            client_submission_id="sync-001",
            phone_number=self.chv.phone_number,
            ward=self.ward,
            payload={"client_submission_id": "sync-001"},
            status=SyncQueue.STATUS_PROCESSED,
            processed_at=timezone.now(),
        )
        TriageSession.objects.create(
            channel="API",
            phone_number=self.chv.phone_number,
            ward=self.ward,
            referral_facility=self.health_facility,
            recommendation="Refer now",
            referral_needed=True,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("chv-activity", args=[self.chv.public_id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 4)
        categories = {event["category"] for event in response.data}
        self.assertIn("MESSAGE", categories)
        self.assertIn("ASSIGNMENT", categories)
        self.assertIn("ALERT", categories)
        self.assertIn("SYNC", categories)
        message_event = next(event for event in response.data if event["category"] == "MESSAGE")
        self.assertEqual(message_event["metadata"]["delivery_kind"], "SIMULATED")
        self.assertEqual(message_event["metadata"]["delivery_backend"], "stub")
        assignment_event = next(event for event in response.data if event["category"] == "ASSIGNMENT")
        self.assertEqual(assignment_event["title"], "Assigned to coverage request")
        self.assertEqual(assignment_event["source"], "Coverage request workflow")

    @patch("risk.services.send_sms")
    def test_admin_can_send_chv_message_via_existing_sms_service(self, mock_send_sms):
        mock_send_sms.return_value = DeliveryResult(
            success=True,
            external_id="sms-123",
            error="",
            provider="stub",
        )

        self.authenticate(self.admin_user.username)
        with patch("risk.services.resolve_chv_message_mode", return_value="SEND"):
            response = self.client.post(
                reverse("chv-message-list-create", args=[self.chv.public_id]),
                {"message_body": "Please check in with the ward team.", "channel": "SMS"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "SENT")
        self.assertEqual(response.data["delivery_kind"], "SIMULATED")
        self.assertEqual(response.data["delivery_backend"], "stub")
        self.assertEqual(response.data["provider_reference"], "sms-123")
        self.assertEqual(CHVMessage.objects.count(), 1)
        message_record = CHVMessage.objects.get()
        self.assertEqual(message_record.sent_by, self.admin_user)
        self.assertEqual(message_record.status, CHVMessage.STATUS_SENT)
        self.assertEqual(message_record.delivery_kind, CHVMessage.DELIVERY_KIND_SIMULATED)
        self.assertEqual(message_record.delivery_backend, "stub")
        mock_send_sms.assert_called_once_with(self.chv.phone_number, "Please check in with the ward team.")

    def test_admin_can_queue_chv_message_when_live_send_is_unavailable(self):
        self.authenticate(self.admin_user.username)
        with patch("risk.services.resolve_chv_message_mode", return_value="QUEUE_ONLY"):
            response = self.client.post(
                reverse("chv-message-list-create", args=[self.chv.public_id]),
                {"message_body": "Please check in with the ward team.", "channel": "SMS"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "QUEUED")
        self.assertEqual(response.data["delivery_kind"], "QUEUE_ONLY")
        self.assertEqual(response.data["delivery_backend"], "")
        self.assertEqual(response.data["provider_reference"], "")
        self.assertEqual(CHVMessage.objects.count(), 1)
        self.assertEqual(CHVMessage.objects.get().status, CHVMessage.STATUS_QUEUED)
        self.assertEqual(CHVMessage.objects.get().delivery_kind, CHVMessage.DELIVERY_KIND_QUEUE_ONLY)

    def test_admin_cannot_create_chv_message_when_messaging_is_unavailable(self):
        self.authenticate(self.admin_user.username)
        with patch("risk.services.resolve_chv_message_mode", return_value="UNAVAILABLE"):
            response = self.client.post(
                reverse("chv-message-list-create", args=[self.chv.public_id]),
                {"message_body": "Please check in with the ward team.", "channel": "SMS"},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CHVMessage.objects.count(), 0)
        self.assertEqual(str(response.data["detail"]), "Messaging is not available in this environment.")

    def test_field_operator_cannot_access_chv_activity_or_messaging_endpoints(self):
        self.authenticate(self.chv_user.username)

        activity_response = self.client.get(reverse("chv-activity", args=[self.chv.public_id]))
        messages_response = self.client.get(reverse("chv-message-list-create", args=[self.chv.public_id]))

        self.assertEqual(activity_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(messages_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_access_activity_and_messages_for_inactive_chv_visible_in_registry_scope(self):
        inactive_chv = CHV.objects.create(
            name="Inactive CHV",
            phone_number="+254700000222",
            ward=self.ward,
            is_active=False,
            language="en",
        )
        CHVMessage.objects.create(
            chv=inactive_chv,
            ward=self.ward,
            sent_by=self.admin_user,
            channel=CHVMessage.CHANNEL_SMS,
            message_body="Historical message",
            status=CHVMessage.STATUS_QUEUED,
            delivery_kind=CHVMessage.DELIVERY_KIND_QUEUE_ONLY,
        )

        self.authenticate(self.admin_user.username)
        activity_response = self.client.get(reverse("chv-activity", args=[inactive_chv.public_id]))
        messages_response = self.client.get(reverse("chv-message-list-create", args=[inactive_chv.public_id]))

        self.assertEqual(activity_response.status_code, status.HTTP_200_OK)
        self.assertEqual(messages_response.status_code, status.HTTP_200_OK)
        self.assertEqual(messages_response.data[0]["message_body"], "Historical message")

    def test_analyst_can_list_facilities(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.health_facility.id)
        self.assertEqual(results[0]["ward_name"], self.ward.name)
        self.assertIn("decision_summary", response.data)
        self.assertEqual(response.data["decision_summary"]["state"], "DEGRADED_CONFIDENCE")
        self.assertEqual(response.data["decision_summary"]["confidence"], "DEGRADED")
        self.assertIn("top_priorities", response.data["decision_summary"])
        self.assertNotIn("primary_cta_kind", response.data["decision_summary"])
        self.assertNotIn("can_dispatch", response.data["decision_summary"])
        self.assertIn("workflow_states", response.data)
        self.assertEqual(response.data["workflow_states"][0]["facility_id"], self.health_facility.id)
        self.assertFalse(response.data["workflow_states"][0]["has_active_review"])
        self.assertEqual(response.data["workflow_states"][0]["label"], "No review signals")

    def test_facility_list_exposes_compact_workflow_states(self):
        contact = FacilityContact.objects.create(
            facility=self.health_facility,
            name="Facility In-Charge",
            role="Nurse in charge",
            phone="+254720100001",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-list-workflow-contact",
            verified_at=timezone.now(),
        )
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.health_facility.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_MEDIUM,
            reason_codes=["STALE_INPUTS"],
            decision_summary_snapshot={"state": "DEGRADED_CONFIDENCE"},
            created_by=self.admin_user,
        )
        update_request = FacilityReadinessUpdateRequest.objects.create(
            review=review,
            facility=self.health_facility,
            contact=contact,
            requested_by=self.admin_user,
            channel=FacilityReadinessUpdateRequest.CHANNEL_SMS,
            message_body="Please send updated readiness information.",
            status=FacilityReadinessUpdateRequest.STATUS_QUEUED,
        )
        escalation = FacilityReadinessEscalation.objects.create(
            review=review,
            facility=self.health_facility,
            ward=self.health_facility.ward,
            status=FacilityReadinessEscalation.STATUS_OPEN,
            severity=FacilityReadinessEscalation.SEVERITY_MEDIUM,
            reason="County review requested.",
            created_by=self.admin_user,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("facility-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        workflow_state = response.data["workflow_states"][0]
        self.assertEqual(workflow_state["facility_id"], self.health_facility.id)
        self.assertTrue(workflow_state["has_active_review"])
        self.assertEqual(workflow_state["review_public_id"], str(review.public_id))
        self.assertEqual(workflow_state["review_status"], FacilityReadinessReview.STATUS_OPEN)
        self.assertTrue(workflow_state["has_active_update_request"])
        self.assertEqual(workflow_state["update_request_public_id"], str(update_request.public_id))
        self.assertEqual(workflow_state["update_request_status"], FacilityReadinessUpdateRequest.STATUS_QUEUED)
        self.assertTrue(workflow_state["has_active_escalation"])
        self.assertEqual(workflow_state["escalation_public_id"], str(escalation.public_id))
        self.assertEqual(workflow_state["escalation_status"], FacilityReadinessEscalation.STATUS_OPEN)
        self.assertEqual(workflow_state["label"], "Escalated")
        self.assertEqual(workflow_state["tone"], "warning")

    @patch("risk.services.build_facility_intelligence_snapshot")
    def test_facility_list_decision_summary_uses_full_filtered_queryset_not_current_page(self, snapshot_mock):
        second_facility = HealthFacility.objects.create(
            name="Zulu Review Health Centre",
            facility_code="TEST-HF-003B",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )

        snapshot_map = {
            self.health_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 94,
                    "staffing_percent": 94,
                    "surge_risk": "LOW",
                    "projected_cases": 1,
                    "backing_source": "promoted_forecast",
                },
                "context": {"ward_risk_score": 0.14, "ward_alert_count": 0},
                "forecasting": {"source_kind": "promoted_forecast"},
                "freshness": {"is_stale": False},
            },
            second_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 18,
                    "staffing_percent": 35,
                    "surge_risk": "EXTREME",
                    "projected_cases": 19,
                    "backing_source": "forecast_preview",
                },
                "context": {"ward_risk_score": 0.83, "ward_alert_count": 2},
                "forecasting": {"source_kind": "forecast_preview"},
                "freshness": {"is_stale": False},
            },
        }

        snapshot_mock.side_effect = lambda facility, stale_threshold_minutes=120: snapshot_map[facility.id]

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-list"), {"page_size": 1, "ordering": "name"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = get_results(response)
        self.assertEqual(len(results), 1)
        self.assertNotEqual(results[0]["id"], second_facility.id)
        self.assertEqual(response.data["decision_summary"]["state"], "REVIEW")
        self.assertEqual(response.data["decision_summary"]["top_priorities"][0]["facility_id"], second_facility.id)

    def test_supervisor_only_sees_facilities_for_assigned_ward(self):
        other_facility = HealthFacility.objects.create(
            name="North Kadem Health Centre",
            facility_code="TEST-HF-003",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )

        self.authenticate(self.supervisor_user.username)
        list_response = self.client.get(reverse("facility-list"))
        detail_response = self.client.get(reverse("facility-detail", args=[other_facility.id]))
        out_of_scope_detail_response = self.client.get(reverse("facility-detail", args=[self.health_facility.id]))

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        results = get_results(list_response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], other_facility.id)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(out_of_scope_detail_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_analyst_can_view_facility_intelligence(self):
        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Facility-linked alert",
            status=Alert.STATUS_DELIVERED,
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["facility"]["id"], self.health_facility.id)
        self.assertEqual(response.data["readiness"]["mode"], "unavailable_until_direct_snapshot_or_promoted_forecast")
        self.assertEqual(response.data["readiness"]["backing_source"], "unavailable")
        self.assertEqual(response.data["readiness"]["dashboard_truth_state"], "unavailable")
        self.assertEqual(response.data["context"]["map_mode"], "shared_ward_geometry_contract")
        self.assertEqual(response.data["context"]["driving_ward_ids"], [self.ward.id])
        self.assertEqual(response.data["forecasting"]["source_kind"], "unavailable")
        self.assertEqual(response.data["forecasting"]["dashboard_truth_state"], "unavailable")
        self.assertEqual(response.data["decision_summary"]["state"], "DEGRADED_CONFIDENCE")
        self.assertEqual(response.data["decision_summary"]["confidence"], "DEGRADED")
        self.assertEqual(response.data["decision_summary"]["confidence_reason"], "weak_proxy_inputs")
        self.assertEqual(response.data["decision_summary"]["top_priorities"][0]["facility_id"], self.health_facility.id)
        self.assertIn("WEAK_PROXY_INPUTS", response.data["decision_summary"]["top_priorities"][0]["reason_codes"])
        self.assertGreaterEqual(len(response.data["timeline"]), 2)
        self.assertNotIn("can_dispatch", response.data["capabilities"])
        self.assertNotIn("can_open_chat", response.data["capabilities"])
        self.assertNotIn("can_notify_chvs", response.data["capabilities"])
        self.assertNotIn("can_escalate_county", response.data["capabilities"])
        self.assertNotIn("can_view_dispatch_history", response.data["capabilities"])
        self.assertIsNone(response.data["contact"])
        self.assertFalse(response.data["capabilities"]["has_verified_contact"])
        self.assertFalse(response.data["capabilities"]["can_open_readiness_review"])
        self.assertFalse(response.data["capabilities"]["can_request_facility_update"])
        self.assertEqual(response.data["capabilities"]["mode"], "contract_backed_readiness_workflows")

    def test_facility_intelligence_does_not_treat_legacy_contact_phone_as_verified_contact(self):
        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.health_facility.contact_phone, "+254720100001")
        self.assertIsNone(response.data["contact"])
        self.assertFalse(response.data["capabilities"]["has_verified_contact"])
        self.assertTrue(response.data["capabilities"]["can_open_readiness_review"])
        self.assertFalse(response.data["capabilities"]["can_request_facility_update"])

    def test_facility_intelligence_exposes_verified_contact_capability_for_admin(self):
        contact = FacilityContact.objects.create(
            facility=self.health_facility,
            name="Facility In-Charge",
            role="Nurse in charge",
            phone="+254720100001",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-contact-test-001",
            verified_at=timezone.now(),
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["contact"]["public_id"], str(contact.public_id))
        self.assertEqual(response.data["contact"]["display_label"], "Facility In-Charge")
        self.assertEqual(response.data["contact"]["phone_last4"], "0001")
        self.assertNotIn("phone", response.data["contact"])
        self.assertTrue(response.data["capabilities"]["has_verified_contact"])
        self.assertTrue(response.data["capabilities"]["can_view_contacts"])
        self.assertFalse(response.data["capabilities"]["has_active_review"])
        self.assertTrue(response.data["capabilities"]["can_open_readiness_review"])
        self.assertFalse(response.data["capabilities"]["can_request_facility_update"])
        self.assertFalse(response.data["capabilities"]["has_active_update_request"])

    def test_facility_intelligence_exposes_active_review_and_unlocks_update_capability(self):
        FacilityContact.objects.create(
            facility=self.health_facility,
            name="Facility In-Charge",
            role="Nurse in charge",
            phone="+254720100001",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-contact-test-review",
            verified_at=timezone.now(),
        )
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.health_facility.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_MEDIUM,
            reason_codes=["STALE_INPUTS"],
            decision_summary_snapshot={"state": "DEGRADED_CONFIDENCE"},
            created_by=self.admin_user,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["active_review"]["public_id"], str(review.public_id))
        self.assertTrue(response.data["capabilities"]["has_active_review"])
        self.assertFalse(response.data["capabilities"]["can_open_readiness_review"])
        self.assertIsNone(response.data["active_update_request"])
        self.assertFalse(response.data["capabilities"]["has_active_update_request"])
        self.assertTrue(response.data["capabilities"]["can_request_facility_update"])

    def test_facility_intelligence_keeps_update_request_locked_for_unverified_contact(self):
        FacilityContact.objects.create(
            facility=self.health_facility,
            name="Unverified Contact",
            role="Facility contact",
            phone="+254720100001",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=False,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-contact-test-unverified",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["contact"])
        self.assertFalse(response.data["capabilities"]["has_verified_contact"])
        self.assertFalse(response.data["capabilities"]["can_request_facility_update"])

    def test_facility_intelligence_keeps_update_request_read_only_for_analyst_even_with_verified_contact(self):
        FacilityContact.objects.create(
            facility=self.health_facility,
            name="Facility In-Charge",
            role="Nurse in charge",
            phone="+254720100001",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-contact-test-analyst",
            verified_at=timezone.now(),
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(response.data["contact"])
        self.assertTrue(response.data["capabilities"]["has_verified_contact"])
        self.assertFalse(response.data["capabilities"]["can_request_facility_update"])

    def test_facility_intelligence_exposes_linked_alert_navigation_metadata(self):
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="ops-dashboard",
            message="Review Got Kachola readiness pressure.",
            status=Alert.STATUS_RETRY_PENDING,
            delivery_backend="dashboard",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["capabilities"]["can_open_linked_alert"])
        self.assertEqual(len(response.data["linked_alerts"]), 1)
        linked_alert = response.data["linked_alerts"][0]
        self.assertEqual(linked_alert["id"], alert.id)
        self.assertEqual(linked_alert["public_id"], str(alert.public_id))
        self.assertEqual(linked_alert["ward_id"], self.ward.id)
        self.assertEqual(linked_alert["dashboard_url"], f"/alerts/{alert.id}")
        self.assertEqual(linked_alert["api_url"], f"/api/v1/alerts/{alert.id}/")
        self.assertEqual(linked_alert["intelligence_api_url"], f"/api/v1/alerts/{alert.id}/intelligence/")
        self.assertEqual(linked_alert["filtered_alerts_url"], f"/alerts?ward_id={self.ward.id}")

    def test_facility_intelligence_exposes_chv_operations_deep_link_for_active_ward_chvs(self):
        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        chv_operations = response.data["chv_operations"]
        self.assertTrue(chv_operations["available"])
        self.assertEqual(chv_operations["ward_id"], self.ward.id)
        self.assertEqual(chv_operations["ward_name"], self.ward.name)
        self.assertEqual(chv_operations["active_chv_count"], 1)
        self.assertEqual(chv_operations["total_chv_count"], 1)
        self.assertEqual(chv_operations["api_url"], f"/api/v1/chvs/operations/?ward_id={self.ward.id}")
        self.assertEqual(chv_operations["dashboard_url"], f"/chvs?ward_id={self.ward.id}#chv-registry")
        self.assertEqual(chv_operations["mode"], "chv_operations_deep_link_only")
        self.assertTrue(response.data["capabilities"]["can_open_chv_operations"])
        self.assertNotIn("can_notify_ward_chvs", response.data["capabilities"])

    def test_facility_intelligence_keeps_chv_operations_unavailable_without_active_ward_chvs(self):
        self.chv.is_active = False
        self.chv.save(update_fields=["is_active"])

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["chv_operations"]["available"])
        self.assertEqual(response.data["chv_operations"]["active_chv_count"], 0)
        self.assertEqual(response.data["chv_operations"]["total_chv_count"], 1)
        self.assertFalse(response.data["capabilities"]["can_open_chv_operations"])
        self.assertNotIn("can_notify_ward_chvs", response.data["capabilities"])

    def test_chv_operations_api_accepts_reuse_ward_filter(self):
        CHV.objects.create(
            name="Other Ward CHV",
            phone_number="+254700000077",
            ward=self.other_ward,
            is_active=True,
            language="en",
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("chv-operations"), {"ward_id": self.ward.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["ward"], self.ward.id)

    def test_admin_can_create_facility_readiness_review(self):
        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("facility-readiness-review-create", args=[self.health_facility.id]),
            {"notes": "Review stale readiness inputs."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["facility"], self.health_facility.id)
        self.assertEqual(response.data["ward"], self.ward.id)
        self.assertEqual(response.data["status"], FacilityReadinessReview.STATUS_OPEN)
        self.assertIn("WEAK_PROXY_INPUTS", response.data["reason_codes"])
        self.assertEqual(FacilityReadinessReview.objects.count(), 1)
        review = FacilityReadinessReview.objects.get()
        self.assertEqual(review.created_by, self.admin_user)
        self.assertEqual(review.notes, "Review stale readiness inputs.")
        self.assertEqual(review.events.count(), 1)
        self.assertEqual(review.events.first().action, FacilityReadinessReviewEvent.ACTION_CREATED)

    def test_duplicate_active_facility_readiness_review_is_rejected(self):
        FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("facility-readiness-review-create", args=[self.health_facility.id]),
            {"notes": "Duplicate review"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FacilityReadinessReview.objects.count(), 1)

    def test_analyst_cannot_create_facility_readiness_review(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.post(
            reverse("facility-readiness-review-create", args=[self.health_facility.id]),
            {"notes": "Analyst should not mutate reviews."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(FacilityReadinessReview.objects.count(), 0)

    def test_supervisor_can_create_facility_readiness_review_for_assigned_ward_only(self):
        other_facility = HealthFacility.objects.create(
            name="North Kadem Health Centre",
            facility_code="TEST-HF-REVIEW-002",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )

        self.authenticate(self.supervisor_user.username)
        in_scope_response = self.client.post(
            reverse("facility-readiness-review-create", args=[other_facility.id]),
            {"notes": "Supervisor ward review."},
            format="json",
        )
        out_of_scope_response = self.client.post(
            reverse("facility-readiness-review-create", args=[self.health_facility.id]),
            {"notes": "Out of scope review."},
            format="json",
        )

        self.assertEqual(in_scope_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(out_of_scope_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(FacilityReadinessReview.objects.count(), 1)
        self.assertEqual(FacilityReadinessReview.objects.get().facility, other_facility)

    def test_admin_can_mark_facility_readiness_review_as_reviewed(self):
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("facility-readiness-review-acknowledge", args=[review.public_id]),
            {"notes": "Reviewed during morning check."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], FacilityReadinessReview.STATUS_ACKNOWLEDGED)
        review.refresh_from_db()
        self.assertIsNotNone(review.acknowledged_at)
        self.assertEqual(review.notes, "Reviewed during morning check.")
        self.assertEqual(review.events.count(), 1)
        self.assertEqual(review.events.first().action, FacilityReadinessReviewEvent.ACTION_ACKNOWLEDGED)

    def test_admin_can_resolve_facility_readiness_review(self):
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_ACKNOWLEDGED,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
            acknowledged_at=timezone.now(),
        )

        self.authenticate(self.admin_user.username)
        response = self.client.patch(
            reverse("facility-readiness-review-detail", args=[review.public_id]),
            {"status": FacilityReadinessReview.STATUS_RESOLVED, "notes": "No further review needed."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], FacilityReadinessReview.STATUS_RESOLVED)
        review.refresh_from_db()
        self.assertIsNotNone(review.resolved_at)
        self.assertEqual(review.events.count(), 1)
        self.assertEqual(review.events.first().action, FacilityReadinessReviewEvent.ACTION_RESOLVED)

        intelligence_response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))
        self.assertEqual(intelligence_response.status_code, status.HTTP_200_OK)
        self.assertIsNone(intelligence_response.data["active_review"])
        self.assertFalse(intelligence_response.data["capabilities"]["has_active_review"])

    def test_analyst_can_view_but_not_update_facility_readiness_review(self):
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
        )

        self.authenticate(self.analyst_user.username)
        detail_response = self.client.get(reverse("facility-readiness-review-detail", args=[review.public_id]))
        patch_response = self.client.patch(
            reverse("facility-readiness-review-detail", args=[review.public_id]),
            {"status": FacilityReadinessReview.STATUS_RESOLVED},
            format="json",
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.status_code, status.HTTP_403_FORBIDDEN)
        review.refresh_from_db()
        self.assertEqual(review.status, FacilityReadinessReview.STATUS_OPEN)

    def test_admin_can_create_facility_update_request_for_active_review_with_verified_contact(self):
        FacilityContact.objects.create(
            facility=self.health_facility,
            name="Facility In-Charge",
            role="Nurse in charge",
            phone="+254720100001",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-contact-update-request",
            verified_at=timezone.now(),
        )
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            reason_codes=["STALE_INPUTS"],
            created_by=self.admin_user,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("facility-readiness-update-request-create", args=[review.public_id]),
            {"message_body": "Please update ORS and staffing status."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["review"], review.id)
        self.assertEqual(response.data["facility"], self.health_facility.id)
        self.assertEqual(response.data["status"], FacilityReadinessUpdateRequest.STATUS_QUEUED)
        self.assertEqual(response.data["message_body"], "Please update ORS and staffing status.")
        self.assertEqual(FacilityReadinessUpdateRequest.objects.count(), 1)
        update_request = FacilityReadinessUpdateRequest.objects.get()
        self.assertEqual(update_request.requested_by, self.admin_user)
        self.assertEqual(update_request.channel, FacilityReadinessUpdateRequest.CHANNEL_SMS)
        self.assertEqual(review.events.count(), 1)
        self.assertEqual(review.events.first().action, FacilityReadinessReviewEvent.ACTION_UPDATE_REQUEST_CREATED)
        self.assertEqual(
            review.events.first().metadata["update_request_public_id"],
            str(update_request.public_id),
        )

        intelligence_response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))
        self.assertEqual(intelligence_response.status_code, status.HTTP_200_OK)
        self.assertEqual(intelligence_response.data["active_update_request"]["public_id"], str(update_request.public_id))
        self.assertTrue(intelligence_response.data["capabilities"]["has_active_update_request"])
        self.assertFalse(intelligence_response.data["capabilities"]["can_request_facility_update"])

    def test_facility_update_request_uses_default_body_and_queued_status(self):
        FacilityContact.objects.create(
            facility=self.health_facility,
            name="Facility In-Charge",
            phone="+254720100001",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-contact-default-request",
            verified_at=timezone.now(),
        )
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            reason_codes=["STALE_INPUTS"],
            created_by=self.admin_user,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("facility-readiness-update-request-create", args=[review.public_id]),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], FacilityReadinessUpdateRequest.STATUS_QUEUED)
        self.assertIn(self.health_facility.name, response.data["message_body"])
        self.assertIn("ORS stock", response.data["message_body"])

    def test_facility_update_request_requires_verified_contact(self):
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("facility-readiness-update-request-create", args=[review.public_id]),
            {"message_body": "Please update readiness inputs."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FacilityReadinessUpdateRequest.objects.count(), 0)

    def test_facility_update_request_requires_active_review(self):
        FacilityContact.objects.create(
            facility=self.health_facility,
            name="Facility In-Charge",
            phone="+254720100001",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-contact-closed-review",
            verified_at=timezone.now(),
        )
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_RESOLVED,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
            resolved_at=timezone.now(),
        )

        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("facility-readiness-update-request-create", args=[review.public_id]),
            {"message_body": "Closed reviews cannot request updates."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FacilityReadinessUpdateRequest.objects.count(), 0)

    def test_duplicate_active_facility_update_request_is_rejected(self):
        contact = FacilityContact.objects.create(
            facility=self.health_facility,
            name="Facility In-Charge",
            phone="+254720100001",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-contact-duplicate-request",
            verified_at=timezone.now(),
        )
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
        )
        FacilityReadinessUpdateRequest.objects.create(
            review=review,
            facility=self.health_facility,
            contact=contact,
            requested_by=self.admin_user,
            channel=FacilityReadinessUpdateRequest.CHANNEL_SMS,
            message_body="Existing active request.",
            status=FacilityReadinessUpdateRequest.STATUS_QUEUED,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("facility-readiness-update-request-create", args=[review.public_id]),
            {"message_body": "Duplicate request."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FacilityReadinessUpdateRequest.objects.count(), 1)

    def test_analyst_cannot_create_facility_update_request(self):
        FacilityContact.objects.create(
            facility=self.health_facility,
            name="Facility In-Charge",
            phone="+254720100001",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-contact-analyst-update-request",
            verified_at=timezone.now(),
        )
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.post(
            reverse("facility-readiness-update-request-create", args=[review.public_id]),
            {"message_body": "Analyst should not mutate update requests."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(FacilityReadinessUpdateRequest.objects.count(), 0)

    def test_supervisor_can_create_facility_update_request_for_assigned_ward_only(self):
        other_facility = HealthFacility.objects.create(
            name="North Kadem Update Facility",
            facility_code="TEST-HF-UPDATE-002",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )
        FacilityContact.objects.create(
            facility=other_facility,
            name="North Kadem Facility In-Charge",
            phone="+254720100002",
            preferred_channel=FacilityContact.CHANNEL_SMS,
            is_verified=True,
            is_active=True,
            source="trusted_facility_registry",
            source_reference="facility-contact-supervisor-update",
            verified_at=timezone.now(),
        )
        in_scope_review = FacilityReadinessReview.objects.create(
            facility=other_facility,
            ward=self.other_ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
        )
        out_of_scope_review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
        )

        self.authenticate(self.supervisor_user.username)
        in_scope_response = self.client.post(
            reverse("facility-readiness-update-request-create", args=[in_scope_review.public_id]),
            {"message_body": "Supervisor ward update request."},
            format="json",
        )
        out_of_scope_response = self.client.post(
            reverse("facility-readiness-update-request-create", args=[out_of_scope_review.public_id]),
            {"message_body": "Out of scope update request."},
            format="json",
        )

        self.assertEqual(in_scope_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(out_of_scope_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(FacilityReadinessUpdateRequest.objects.count(), 1)
        self.assertEqual(FacilityReadinessUpdateRequest.objects.get().facility, other_facility)

    def test_facility_intelligence_exposes_county_escalation_capability_for_admin(self):
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_MEDIUM,
            reason_codes=["STALE_INPUTS"],
            created_by=self.admin_user,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["active_review"]["public_id"], str(review.public_id))
        self.assertIsNone(response.data["active_escalation"])
        self.assertTrue(response.data["capabilities"]["has_county_review_queue"])
        self.assertTrue(response.data["capabilities"]["can_escalate_county_review"])
        self.assertFalse(response.data["capabilities"]["has_active_escalation"])

    def test_supervisor_cannot_create_county_review_escalation(self):
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_MEDIUM,
            created_by=self.admin_user,
        )

        self.authenticate(self.supervisor_user.username)
        response = self.client.post(
            reverse("facility-readiness-escalation-create", args=[review.public_id]),
            {"reason": "Supervisor should not escalate county review."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(FacilityReadinessEscalation.objects.count(), 0)

    def test_admin_can_create_county_review_escalation_for_active_review(self):
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_MEDIUM,
            reason_codes=["STALE_INPUTS"],
            created_by=self.admin_user,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("facility-readiness-escalation-create", args=[review.public_id]),
            {"reason": "County should review stale readiness inputs."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["review"], review.id)
        self.assertEqual(response.data["facility"], self.health_facility.id)
        self.assertEqual(response.data["ward"], self.ward.id)
        self.assertEqual(response.data["status"], FacilityReadinessEscalation.STATUS_OPEN)
        self.assertEqual(response.data["severity"], FacilityReadinessEscalation.SEVERITY_MEDIUM)
        self.assertEqual(FacilityReadinessEscalation.objects.count(), 1)
        escalation = FacilityReadinessEscalation.objects.get()
        self.assertEqual(escalation.created_by, self.admin_user)
        self.assertEqual(escalation.reason, "County should review stale readiness inputs.")
        self.assertEqual(review.events.count(), 1)
        self.assertEqual(review.events.first().action, FacilityReadinessReviewEvent.ACTION_ESCALATION_CREATED)
        self.assertEqual(review.events.first().metadata["escalation_public_id"], str(escalation.public_id))

        intelligence_response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))
        self.assertEqual(intelligence_response.status_code, status.HTTP_200_OK)
        self.assertEqual(intelligence_response.data["active_escalation"]["public_id"], str(escalation.public_id))
        self.assertTrue(intelligence_response.data["capabilities"]["has_active_escalation"])
        self.assertFalse(intelligence_response.data["capabilities"]["can_escalate_county_review"])

    def test_county_review_escalation_requires_active_review(self):
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_RESOLVED,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
            resolved_at=timezone.now(),
        )

        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("facility-readiness-escalation-create", args=[review.public_id]),
            {"reason": "Closed reviews cannot be escalated."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FacilityReadinessEscalation.objects.count(), 0)

    def test_duplicate_active_county_review_escalation_is_rejected(self):
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
        )
        FacilityReadinessEscalation.objects.create(
            review=review,
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessEscalation.STATUS_OPEN,
            severity=FacilityReadinessEscalation.SEVERITY_LOW,
            reason="Existing active county review escalation.",
            created_by=self.admin_user,
        )

        self.authenticate(self.admin_user.username)
        response = self.client.post(
            reverse("facility-readiness-escalation-create", args=[review.public_id]),
            {"reason": "Duplicate escalation."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(FacilityReadinessEscalation.objects.count(), 1)

    def test_admin_can_acknowledge_and_resolve_county_review_escalation(self):
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_HIGH,
            created_by=self.admin_user,
        )
        escalation = FacilityReadinessEscalation.objects.create(
            review=review,
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessEscalation.STATUS_OPEN,
            severity=FacilityReadinessEscalation.SEVERITY_HIGH,
            reason="County review needed.",
            created_by=self.admin_user,
        )

        self.authenticate(self.admin_user.username)
        acknowledge_response = self.client.patch(
            reverse("facility-readiness-escalation-detail", args=[escalation.public_id]),
            {"status": FacilityReadinessEscalation.STATUS_ACKNOWLEDGED, "notes": "County desk has taken this."},
            format="json",
        )
        resolve_response = self.client.patch(
            reverse("facility-readiness-escalation-detail", args=[escalation.public_id]),
            {"status": FacilityReadinessEscalation.STATUS_RESOLVED, "notes": "County review completed."},
            format="json",
        )

        self.assertEqual(acknowledge_response.status_code, status.HTTP_200_OK)
        self.assertEqual(acknowledge_response.data["status"], FacilityReadinessEscalation.STATUS_ACKNOWLEDGED)
        self.assertEqual(acknowledge_response.data["assigned_to"], self.admin_user.id)
        self.assertEqual(resolve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(resolve_response.data["status"], FacilityReadinessEscalation.STATUS_RESOLVED)
        escalation.refresh_from_db()
        self.assertEqual(escalation.assigned_to, self.admin_user)
        self.assertEqual(escalation.acknowledged_by, self.admin_user)
        self.assertIsNotNone(escalation.acknowledged_at)
        self.assertIsNotNone(escalation.resolved_at)
        self.assertEqual(
            list(review.events.values_list("action", flat=True)),
            [
                FacilityReadinessReviewEvent.ACTION_ESCALATION_ACKNOWLEDGED,
                FacilityReadinessReviewEvent.ACTION_ESCALATION_RESOLVED,
            ],
        )

    def test_analyst_can_view_county_review_queue_but_not_mutate(self):
        review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
        )
        escalation = FacilityReadinessEscalation.objects.create(
            review=review,
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessEscalation.STATUS_OPEN,
            severity=FacilityReadinessEscalation.SEVERITY_LOW,
            reason="Visible county review queue item.",
            created_by=self.admin_user,
        )

        self.authenticate(self.analyst_user.username)
        list_response = self.client.get(reverse("facility-readiness-escalation-list"))
        detail_response = self.client.get(reverse("facility-readiness-escalation-detail", args=[escalation.public_id]))
        patch_response = self.client.patch(
            reverse("facility-readiness-escalation-detail", args=[escalation.public_id]),
            {"status": FacilityReadinessEscalation.STATUS_ACKNOWLEDGED},
            format="json",
        )

        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        list_results = get_results(list_response)
        self.assertEqual(len(list_results), 1)
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_county_review_queue_filters_assignment_state(self):
        in_scope_review = FacilityReadinessReview.objects.create(
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
        )
        other_facility = HealthFacility.objects.create(
            name="County Queue Assigned Facility",
            facility_code="TEST-HF-ESC-002",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )
        assigned_review = FacilityReadinessReview.objects.create(
            facility=other_facility,
            ward=self.other_ward,
            status=FacilityReadinessReview.STATUS_OPEN,
            severity=FacilityReadinessReview.SEVERITY_LOW,
            created_by=self.admin_user,
        )
        FacilityReadinessEscalation.objects.create(
            review=in_scope_review,
            facility=self.health_facility,
            ward=self.ward,
            status=FacilityReadinessEscalation.STATUS_OPEN,
            severity=FacilityReadinessEscalation.SEVERITY_LOW,
            reason="Unassigned county review queue item.",
            created_by=self.admin_user,
        )
        FacilityReadinessEscalation.objects.create(
            review=assigned_review,
            facility=other_facility,
            ward=self.other_ward,
            status=FacilityReadinessEscalation.STATUS_ACKNOWLEDGED,
            severity=FacilityReadinessEscalation.SEVERITY_LOW,
            reason="Assigned county review queue item.",
            created_by=self.admin_user,
            assigned_to=self.admin_user,
            acknowledged_by=self.admin_user,
            acknowledged_at=timezone.now(),
        )

        self.authenticate(self.admin_user.username)
        all_response = self.client.get(reverse("facility-readiness-escalation-list"))
        unassigned_response = self.client.get(
            reverse("facility-readiness-escalation-list"),
            {"assignment": "unassigned"},
        )
        mine_response = self.client.get(
            reverse("facility-readiness-escalation-list"),
            {"assignment": "mine"},
        )

        self.assertEqual(all_response.status_code, status.HTTP_200_OK)
        all_results = get_results(all_response)
        self.assertEqual(len(all_results), 2)
        self.assertEqual(unassigned_response.status_code, status.HTTP_200_OK)
        unassigned_results = get_results(unassigned_response)
        self.assertEqual(len(unassigned_results), 1)
        self.assertIsNone(unassigned_results[0]["assigned_to"])
        self.assertEqual(mine_response.status_code, status.HTTP_200_OK)
        mine_results = get_results(mine_response)
        self.assertEqual(len(mine_results), 1)
        self.assertEqual(mine_results[0]["assigned_to"], self.admin_user.id)

    def test_facility_intelligence_distinguishes_forecast_preview_from_proxy_readiness(self):
        run_facility_burden_forecast_pipeline(
            model_version="fnb-v1",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["readiness"]["mode"], "forecast_preview_backed_facility_burden_not_promoted")
        self.assertEqual(response.data["readiness"]["backing_source"], "forecast_preview")
        self.assertEqual(response.data["readiness"]["dashboard_truth_state"], "blocked_until_promotion")
        self.assertEqual(response.data["forecasting"]["source_kind"], "forecast_preview")
        self.assertEqual(response.data["forecasting"]["governance_mode"], "preview_only")
        self.assertEqual(response.data["forecasting"]["model_version"], "fnb-v1")
        self.assertEqual(response.data["forecasting"]["dashboard_truth_state"], "blocked_until_promotion")
        self.assertEqual(response.data["context"]["driving_ward_ids"], [self.ward.id])
        self.assertGreaterEqual(len(response.data["context"]["action_reasoning"]), 2)
        self.assertEqual(response.data["freshness"]["mode"], "derived_from_forecast_or_facility_timestamp")
        self.assertEqual(response.data["decision_summary"]["confidence"], "NORMAL")
        self.assertIsNone(response.data["decision_summary"]["confidence_reason"])
        self.assertEqual(response.data["timeline"][0]["id"].startswith("facility-forecast-"), True)

    def test_facility_intelligence_prefers_promoted_facility_forecast_over_newer_preview_run(self):
        promoted_run = run_facility_burden_forecast_pipeline(
            model_version="fnb-promoted-fi-v1",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )
        call_command(
            "promote_facility_burden_forecast",
            run_id=promoted_run.id,
            promoted_by="auditor",
            note="facility-intelligence-promotion-test",
            allow_blocked_promotion=True,
        )
        newer_preview_run = run_facility_burden_forecast_pipeline(
            model_version="fnb-preview-fi-v2",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["readiness"]["mode"], "promoted_facility_burden_forecast")
        self.assertEqual(response.data["readiness"]["backing_source"], "forecast_promoted")
        self.assertEqual(response.data["readiness"]["dashboard_truth_state"], "promoted")
        self.assertEqual(response.data["forecasting"]["source_kind"], "promoted_forecast")
        self.assertEqual(response.data["forecasting"]["governance_mode"], "promoted")
        self.assertEqual(response.data["forecasting"]["model_version"], promoted_run.model_version)
        self.assertNotEqual(response.data["forecasting"]["model_version"], newer_preview_run.model_version)
        self.assertEqual(response.data["timeline"][0]["tone"], "success")

    def test_supervisor_can_view_facility_intelligence_for_assigned_ward_only(self):
        other_facility = HealthFacility.objects.create(
            name="North Kadem Health Centre",
            facility_code="TEST-HF-004",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )

        self.authenticate(self.supervisor_user.username)
        in_scope_response = self.client.get(reverse("facility-intelligence", args=[other_facility.id]))
        out_of_scope_response = self.client.get(reverse("facility-intelligence", args=[self.health_facility.id]))

        self.assertEqual(in_scope_response.status_code, status.HTTP_200_OK)
        self.assertEqual(in_scope_response.data["facility"]["id"], other_facility.id)
        self.assertEqual(out_of_scope_response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("risk.services.build_facility_intelligence_snapshot")
    def test_facility_readiness_decision_summary_ranks_stale_high_difference_first(self, snapshot_mock):
        second_facility = HealthFacility.objects.create(
            name="North Kadem Health Centre",
            facility_code="TEST-HF-004",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )
        calm_ward = Ward.objects.create(
            name="Got Kachola",
            county="Migori",
            sub_county="Nyatike",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.18,
            is_active=True,
        )
        calm_facility = HealthFacility.objects.create(
            name="Got Kachola Dispensary",
            facility_code="TEST-HF-005",
            ward=calm_ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
        )

        snapshot_map = {
            self.health_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 22,
                    "staffing_percent": 40,
                    "surge_risk": "EXTREME",
                    "projected_cases": 21,
                    "backing_source": "forecast_preview",
                },
                "context": {"ward_risk_score": 0.86, "ward_alert_count": 2},
                "forecasting": {"source_kind": "forecast_preview"},
                "freshness": {"is_stale": True},
            },
            second_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 58,
                    "staffing_percent": 72,
                    "surge_risk": "MODERATE",
                    "projected_cases": 9,
                    "backing_source": "forecast_preview",
                },
                "context": {"ward_risk_score": 0.62, "ward_alert_count": 1},
                "forecasting": {"source_kind": "forecast_preview"},
                "freshness": {"is_stale": False},
            },
            calm_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 90,
                    "staffing_percent": 90,
                    "surge_risk": "LOW",
                    "projected_cases": 2,
                    "backing_source": "forecast_preview",
                },
                "context": {"ward_risk_score": 0.18, "ward_alert_count": 0},
                "forecasting": {"source_kind": "promoted_forecast"},
                "freshness": {"is_stale": False},
            },
        }

        snapshot_mock.side_effect = lambda facility, stale_threshold_minutes=120: snapshot_map[facility.id]

        summary = build_facility_readiness_decision_summary(
            [self.health_facility, second_facility, calm_facility]
        )

        self.assertEqual(summary["state"], "DEGRADED_CONFIDENCE")
        self.assertEqual(summary["confidence"], "DEGRADED")
        self.assertEqual(summary["confidence_reason"], "stale_inputs")
        self.assertEqual([item["facility_id"] for item in summary["top_priorities"]], [self.health_facility.id, second_facility.id])
        self.assertIn("HIGH_READINESS_DIFFERENCE", summary["top_priorities"][0]["reason_codes"])
        self.assertIn("STALE_INPUTS", summary["top_priorities"][0]["reason_codes"])
        self.assertIn("MODERATE_READINESS_DIFFERENCE", summary["top_priorities"][1]["reason_codes"])

    @patch("risk.services.build_facility_intelligence_snapshot")
    def test_facility_readiness_decision_summary_returns_review_state_when_confidence_is_normal(self, snapshot_mock):
        second_facility = HealthFacility.objects.create(
            name="North Kadem Health Centre",
            facility_code="TEST-HF-006",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )

        snapshot_map = {
            self.health_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 60,
                    "staffing_percent": 74,
                    "surge_risk": "MODERATE",
                    "projected_cases": 10,
                    "backing_source": "forecast_preview",
                },
                "context": {"ward_risk_score": 0.86, "ward_alert_count": 1},
                "forecasting": {"source_kind": "forecast_preview"},
                "freshness": {"is_stale": False},
            },
            second_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 88,
                    "staffing_percent": 92,
                    "surge_risk": "LOW",
                    "projected_cases": 3,
                    "backing_source": "promoted_forecast",
                },
                "context": {"ward_risk_score": 0.18, "ward_alert_count": 0},
                "forecasting": {"source_kind": "promoted_forecast"},
                "freshness": {"is_stale": False},
            },
        }

        snapshot_mock.side_effect = lambda facility, stale_threshold_minutes=120: snapshot_map[facility.id]

        summary = build_facility_readiness_decision_summary([self.health_facility, second_facility])

        self.assertEqual(summary["state"], "REVIEW")
        self.assertEqual(summary["confidence"], "NORMAL")
        self.assertIsNone(summary["confidence_reason"])
        self.assertEqual(summary["total_review_facility_count"], 1)
        self.assertEqual(summary["top_priorities"][0]["facility_id"], self.health_facility.id)
        self.assertIn("MODERATE_READINESS_DIFFERENCE", summary["top_priorities"][0]["reason_codes"])

    @patch("risk.services.build_facility_intelligence_snapshot")
    def test_facility_readiness_decision_summary_returns_calm_state_when_no_review_priority_exists(self, snapshot_mock):
        calm_ward = Ward.objects.create(
            name="South Sakwa",
            county="Migori",
            sub_county="Nyatike",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.14,
            is_active=True,
        )
        calm_facility = HealthFacility.objects.create(
            name="South Sakwa Dispensary",
            facility_code="TEST-HF-007",
            ward=calm_ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
        )

        snapshot_mock.return_value = {
            "readiness": {
                "ors_estimate_percent": 94,
                "staffing_percent": 94,
                "surge_risk": "LOW",
                "projected_cases": 1,
                "backing_source": "promoted_forecast",
            },
            "context": {"ward_risk_score": 0.14, "ward_alert_count": 0},
            "forecasting": {"source_kind": "promoted_forecast"},
            "freshness": {"is_stale": False},
        }

        summary = build_facility_readiness_decision_summary([calm_facility])

        self.assertEqual(summary["state"], "CALM")
        self.assertEqual(summary["confidence"], "NORMAL")
        self.assertIsNone(summary["confidence_reason"])
        self.assertEqual(summary["total_review_facility_count"], 0)
        self.assertEqual(summary["top_priorities"], [])
        self.assertEqual(summary["related_surfaces"]["has_linked_alerts"], False)

    @patch("risk.services.build_facility_intelligence_snapshot")
    def test_facility_readiness_decision_summary_counts_unique_linked_alerts_across_loaded_scope(self, snapshot_mock):
        same_ward_facility = HealthFacility.objects.create(
            name="North Kamagambo Annex Dispensary",
            facility_code="TEST-HF-007B",
            ward=self.ward,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
        )

        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="ops",
            message="Ward alert one",
            status=Alert.STATUS_DELIVERED,
        )
        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient="254700000001",
            message="Ward alert two",
            status=Alert.STATUS_QUEUED,
        )

        snapshot_map = {
            self.health_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 94,
                    "staffing_percent": 94,
                    "surge_risk": "LOW",
                    "projected_cases": 1,
                    "backing_source": "promoted_forecast",
                },
                "context": {"ward_risk_score": 0.14, "ward_alert_count": 2},
                "forecasting": {"source_kind": "promoted_forecast"},
                "freshness": {"is_stale": False},
            },
            same_ward_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 92,
                    "staffing_percent": 91,
                    "surge_risk": "LOW",
                    "projected_cases": 1,
                    "backing_source": "promoted_forecast",
                },
                "context": {"ward_risk_score": 0.14, "ward_alert_count": 2},
                "forecasting": {"source_kind": "promoted_forecast"},
                "freshness": {"is_stale": False},
            },
        }

        snapshot_mock.side_effect = lambda facility, stale_threshold_minutes=120: snapshot_map[facility.id]

        summary = build_facility_readiness_decision_summary([self.health_facility, same_ward_facility])

        self.assertTrue(summary["related_surfaces"]["has_linked_alerts"])
        self.assertEqual(summary["related_surfaces"]["linked_alert_count"], 2)

    @patch("risk.services.build_facility_intelligence_snapshot")
    def test_facility_readiness_decision_summary_exposes_total_review_count_beyond_top_priority_cap(self, snapshot_mock):
        second_facility = HealthFacility.objects.create(
            name="Beta Review Facility",
            facility_code="TEST-HF-008B",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )
        third_ward = Ward.objects.create(
            name="Suna East",
            county="Migori",
            sub_county="Suna East",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.8,
            is_active=True,
        )
        third_facility = HealthFacility.objects.create(
            name="Gamma Review Facility",
            facility_code="TEST-HF-008C",
            ward=third_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )

        snapshot_map = {
            self.health_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 18,
                    "staffing_percent": 35,
                    "surge_risk": "EXTREME",
                    "projected_cases": 19,
                    "backing_source": "forecast_preview",
                },
                "context": {"ward_risk_score": 0.83, "ward_alert_count": 2},
                "forecasting": {"source_kind": "forecast_preview"},
                "freshness": {"is_stale": False},
            },
            second_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 22,
                    "staffing_percent": 42,
                    "surge_risk": "EXTREME",
                    "projected_cases": 17,
                    "backing_source": "forecast_preview",
                },
                "context": {"ward_risk_score": 0.79, "ward_alert_count": 1},
                "forecasting": {"source_kind": "forecast_preview"},
                "freshness": {"is_stale": False},
            },
            third_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 27,
                    "staffing_percent": 48,
                    "surge_risk": "MODERATE",
                    "projected_cases": 13,
                    "backing_source": "forecast_preview",
                },
                "context": {"ward_risk_score": 0.76, "ward_alert_count": 0},
                "forecasting": {"source_kind": "forecast_preview"},
                "freshness": {"is_stale": False},
            },
        }

        snapshot_mock.side_effect = lambda facility, stale_threshold_minutes=120: snapshot_map[facility.id]

        summary = build_facility_readiness_decision_summary([self.health_facility, second_facility, third_facility])

        self.assertEqual(summary["total_review_facility_count"], 3)
        self.assertEqual(len(summary["top_priorities"]), 2)

    @patch("risk.services.build_facility_intelligence_snapshot")
    def test_facility_readiness_decision_summary_downgrades_for_stale_and_weak_proxy_inputs(self, snapshot_mock):
        weak_facility = HealthFacility.objects.create(
            name="Weak Proxy Facility",
            facility_code="TEST-HF-008",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )

        snapshot_map = {
            self.health_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 25,
                    "staffing_percent": 45,
                    "surge_risk": "EXTREME",
                    "projected_cases": 17,
                    "backing_source": "unavailable",
                },
                "context": {"ward_risk_score": 0.86, "ward_alert_count": 1},
                "forecasting": {"source_kind": "unavailable"},
                "freshness": {"is_stale": True},
            },
            weak_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 80,
                    "staffing_percent": 82,
                    "surge_risk": "LOW",
                    "projected_cases": 3,
                    "backing_source": "forecast_preview",
                },
                "context": {"ward_risk_score": 0.22, "ward_alert_count": 0},
                "forecasting": {"source_kind": "forecast_preview"},
                "freshness": {"is_stale": False},
            },
        }

        snapshot_mock.side_effect = lambda facility, stale_threshold_minutes=120: snapshot_map[facility.id]

        summary = build_facility_readiness_decision_summary([self.health_facility, weak_facility])

        self.assertEqual(summary["state"], "DEGRADED_CONFIDENCE")
        self.assertEqual(summary["confidence"], "DEGRADED")
        self.assertEqual(summary["confidence_reason"], "stale_and_weak_proxy_inputs")
        self.assertEqual(summary["top_priorities"][0]["facility_id"], self.health_facility.id)
        self.assertIn("STALE_INPUTS", summary["top_priorities"][0]["reason_codes"])
        self.assertIn("WEAK_PROXY_INPUTS", summary["top_priorities"][0]["reason_codes"])

    @patch("risk.services.build_facility_intelligence_snapshot")
    def test_facility_readiness_decision_summary_preserves_priority_bucket_order(self, snapshot_mock):
        high_difference = HealthFacility.objects.create(
            name="High Difference Facility",
            facility_code="TEST-HF-009",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )
        forecast_pressure = HealthFacility.objects.create(
            name="Forecast Pressure Facility",
            facility_code="TEST-HF-010",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )
        ward_risk_only = HealthFacility.objects.create(
            name="Ward Risk Only Facility",
            facility_code="TEST-HF-011",
            ward=self.other_ward,
            facility_type=HealthFacility.TYPE_HEALTH_CENTER,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_3,
            is_active=True,
        )

        snapshot_map = {
            self.health_facility.id: {
                "readiness": {
                    "ors_estimate_percent": 22,
                    "staffing_percent": 44,
                    "surge_risk": "EXTREME",
                    "projected_cases": 19,
                    "backing_source": "forecast_preview",
                },
                "context": {"ward_risk_score": 0.86, "ward_alert_count": 2},
                "forecasting": {"source_kind": "forecast_preview"},
                "freshness": {"is_stale": True},
            },
            high_difference.id: {
                "readiness": {
                    "ors_estimate_percent": 28,
                    "staffing_percent": 52,
                    "surge_risk": "EXTREME",
                    "projected_cases": 15,
                    "backing_source": "forecast_preview",
                },
                "context": {"ward_risk_score": 0.55, "ward_alert_count": 0},
                "forecasting": {"source_kind": "forecast_preview"},
                "freshness": {"is_stale": False},
            },
            forecast_pressure.id: {
                "readiness": {
                    "ors_estimate_percent": 72,
                    "staffing_percent": 86,
                    "surge_risk": "MODERATE",
                    "projected_cases": 11,
                    "backing_source": "forecast_preview",
                },
                "context": {"ward_risk_score": 0.32, "ward_alert_count": 0},
                "forecasting": {"source_kind": "forecast_preview"},
                "freshness": {"is_stale": False},
            },
            ward_risk_only.id: {
                "readiness": {
                    "ors_estimate_percent": 92,
                    "staffing_percent": 94,
                    "surge_risk": "LOW",
                    "projected_cases": 4,
                    "backing_source": "promoted_forecast",
                },
                "context": {"ward_risk_score": 0.63, "ward_alert_count": 0},
                "forecasting": {"source_kind": "promoted_forecast"},
                "freshness": {"is_stale": False},
            },
        }

        snapshot_mock.side_effect = lambda facility, stale_threshold_minutes=120: snapshot_map[facility.id]

        summary = build_facility_readiness_decision_summary(
            [self.health_facility, high_difference, forecast_pressure, ward_risk_only],
            max_priorities=4,
        )

        self.assertEqual(
            [item["facility_id"] for item in summary["top_priorities"]],
            [self.health_facility.id, high_difference.id, forecast_pressure.id, ward_risk_only.id],
        )
        self.assertEqual(
            [item["priority_label"] for item in summary["top_priorities"]],
            ["Top review priority", "Next review priority", "Next review priority", "Next review priority"],
        )

    @patch("risk.services.build_facility_intelligence_snapshot")
    def test_facility_readiness_decision_summary_reason_codes_are_stable_and_deduplicated(self, snapshot_mock):
        snapshot_mock.return_value = {
            "readiness": {
                "ors_estimate_percent": 24,
                "staffing_percent": 40,
                "surge_risk": "EXTREME",
                "projected_cases": 20,
                "backing_source": "unavailable",
            },
            "context": {"ward_risk_score": 0.86, "ward_alert_count": 3},
            "forecasting": {"source_kind": "unavailable"},
            "freshness": {"is_stale": True},
        }

        first = build_facility_readiness_decision_summary([self.health_facility])
        second = build_facility_readiness_decision_summary([self.health_facility])

        expected_codes = [
            "HIGH_READINESS_DIFFERENCE",
            "STALE_INPUTS",
            "WEAK_PROXY_INPUTS",
            "ELEVATED_WARD_RISK",
            "MULTIPLE_ALERTS_IN_WARD",
        ]
        self.assertEqual(first["top_priorities"][0]["reason_codes"], expected_codes)
        self.assertEqual(second["top_priorities"][0]["reason_codes"], expected_codes)

    def test_analyst_can_view_facility_forecasting_status(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-forecasting-status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["forecasting_state"], "phase_0_truth_audited_phase_1_contract_defined")
        self.assertEqual(response.data["planned_baseline_model"], "negative_binomial_regression")
        self.assertIsNone(response.data["current_baseline_model"])
        self.assertEqual(response.data["current_baseline_state"], "not_yet_implemented")
        self.assertIn("facility master record", response.data["truth_sources"]["direct_operational_truth"])
        self.assertIn(
            "negative_binomial_is_live",
            response.data["contract_definition"]["dashboard_not_allowed_to_imply_yet"],
        )
        self.assertEqual(response.data["promotion_summary"]["decision"]["promotion_readiness"], "not_ready_for_promotion")
        self.assertIn("baseline_run_missing", response.data["promotion_summary"]["decision"]["promotion_blockers"])

    def test_analyst_can_view_facility_forecast_preview(self):
        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-forecast-preview", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["facility_id"], self.health_facility.id)
        self.assertEqual(response.data["horizon_days"], 7)
        self.assertEqual(response.data["projected_case_burden"], self.risk_score.predicted_cases)
        self.assertEqual(response.data["forecast_mode"], "proxy_preforecast_from_current_readiness_contract")
        self.assertEqual(response.data["model_version"], None)
        self.assertEqual(response.data["baseline_model_status"], "negative_binomial_not_yet_implemented")
        self.assertEqual(response.data["driving_ward_ids"], [self.ward.id])
        self.assertGreaterEqual(len(response.data["forecast_factors"]), 3)

    def test_facility_forecast_preview_prefers_persisted_negative_binomial_forecast(self):
        run = run_facility_burden_forecast_pipeline(
            model_version="fnb-v1",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-forecast-preview", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["forecast_mode"], "negative_binomial_baseline_preview")
        self.assertEqual(response.data["model_version"], "fnb-v1")
        self.assertEqual(response.data["baseline_model_status"], "negative_binomial_implemented_not_promoted")
        self.assertGreaterEqual(response.data["projected_case_burden"], 1)
        self.assertEqual(
            FacilityForecast.objects.filter(forecast_run=run, facility=self.health_facility).count(),
            1,
        )

    def test_facility_forecast_preview_reflects_promoted_baseline_status(self):
        run = run_facility_burden_forecast_pipeline(
            model_version="fnb-vpreview-promoted",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )
        call_command(
            "promote_facility_burden_forecast",
            run_id=run.id,
            promoted_by="auditor",
            note="preview-promotion-test",
            allow_blocked_promotion=True,
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-forecast-preview", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["baseline_model_status"],
            "negative_binomial_promoted_for_dashboard_readiness",
        )

    def test_facility_forecast_preview_prefers_promoted_run_over_newer_preview_run(self):
        promoted_run = run_facility_burden_forecast_pipeline(
            model_version="fnb-preview-promoted-v1",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )
        call_command(
            "promote_facility_burden_forecast",
            run_id=promoted_run.id,
            promoted_by="auditor",
            note="preview-precedence-test",
            allow_blocked_promotion=True,
        )
        run_facility_burden_forecast_pipeline(
            model_version="fnb-preview-newer-v2",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-forecast-preview", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["model_version"], "fnb-preview-promoted-v1")
        self.assertEqual(
            response.data["baseline_model_status"],
            "negative_binomial_promoted_for_dashboard_readiness",
        )

    def test_facility_forecasting_status_reflects_successful_baseline_run(self):
        run_facility_burden_forecast_pipeline(
            model_version="fnb-v1",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-forecasting-status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["forecasting_state"], "phase_2_baseline_implemented_not_promoted")
        self.assertEqual(response.data["current_baseline_model"], "negative-binomial-baseline")
        self.assertEqual(response.data["current_baseline_state"], "implemented_not_promoted")
        self.assertEqual(response.data["promotion_summary"]["decision"]["governance_mode"], "preview_only")
        self.assertIn("proxy_training_target_only", response.data["promotion_summary"]["decision"]["promotion_blockers"])

    def test_facility_forecasting_status_reflects_promoted_baseline_run(self):
        run = run_facility_burden_forecast_pipeline(
            model_version="fnb-vpromoted-status",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )
        call_command(
            "promote_facility_burden_forecast",
            run_id=run.id,
            promoted_by="auditor",
            note="status-promotion-test",
            allow_blocked_promotion=True,
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-forecasting-status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["forecasting_state"], "phase_4_promoted_dashboard_forecast_available")
        self.assertEqual(response.data["current_baseline_state"], "promoted")
        self.assertFalse(response.data["honesty_rules"]["negative_binomial_not_yet_promoted"])
        self.assertFalse(response.data["honesty_rules"]["current_readiness_is_proxy_backed"])
        self.assertEqual(response.data["promotion_summary"]["decision"]["governance_mode"], "promoted")
        self.assertEqual(response.data["promotion_summary"]["decision"]["promotion_readiness"], "promoted_with_manual_review")
        self.assertEqual(response.data["promotion_summary"]["decision"]["promotion_blockers"], [])

    def test_analyst_can_view_facility_forecasting_evaluation(self):
        run_facility_burden_forecast_pipeline(
            model_version="fnb-v1",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-forecasting-evaluation"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["current_run"]["model_version"], "fnb-v1")
        self.assertEqual(response.data["decision"]["promotion_readiness"], "not_ready_for_promotion")
        self.assertEqual(response.data["decision"]["governance_mode"], "preview_only")
        self.assertIn("dashboard_readiness_warning", response.data["decision"]["blocked_product_surfaces"])

    def test_facility_forecasting_evaluation_reflects_promoted_run(self):
        run = run_facility_burden_forecast_pipeline(
            model_version="fnb-vpromoted-eval",
            execution_context="test_case",
            run_purpose="forecast_scoring",
        )
        call_command(
            "promote_facility_burden_forecast",
            run_id=run.id,
            promoted_by="auditor",
            note="evaluation-promotion-test",
            allow_blocked_promotion=True,
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("facility-forecasting-evaluation"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["current_run"]["model_version"], "fnb-vpromoted-eval")
        self.assertEqual(response.data["decision"]["promotion_readiness"], "promoted_with_manual_review")
        self.assertEqual(response.data["decision"]["governance_mode"], "promoted")
        self.assertEqual(response.data["decision"]["promotion_blockers"], [])
        self.assertIn("dashboard_readiness_warning", response.data["decision"]["allowed_product_surfaces"])

    def test_supervisor_cannot_view_out_of_scope_facility_forecast_preview(self):
        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("facility-forecast-preview", args=[self.health_facility.id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

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

    def test_analyst_can_view_alert_detail(self):
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Test alert detail",
            status=Alert.STATUS_DELIVERED,
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("alert-detail", args=[alert.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], alert.id)
        self.assertEqual(response.data["ward"], self.ward.id)

    def test_analyst_can_view_alert_intelligence(self):
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Test alert intelligence",
            status=Alert.STATUS_DELIVERED,
            delivery_backend="internal-dashboard",
            attempt_count=1,
            max_attempts=1,
            sent_at=timezone.now(),
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("alert-intelligence", args=[alert.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["alert"]["id"], alert.id)
        self.assertEqual(response.data["classification"]["mode"], "derived_from_record_text")
        self.assertEqual(response.data["delivery"]["mode"], "backend_record_fields")
        self.assertEqual(response.data["message_source"]["mode"], "unavailable")
        self.assertEqual(response.data["lifecycle"]["status"], "active")
        self.assertEqual(response.data["delivery_summary"]["attempt_count"], 1)
        self.assertIn("coverage_label", response.data["chv_response_summary"])
        self.assertIn("coverage_label", response.data["facility_response_summary"])
        self.assertIn("label", response.data["recommended_next_action"])
        self.assertEqual(response.data["timeline"][2]["category"], "communication")
        self.assertGreaterEqual(len(response.data["timeline"]), 4)
        self.assertFalse(response.data["capabilities"]["can_resend"])

    def test_alert_intelligence_surfaces_operator_edited_message_source(self):
        alert = Alert.objects.create(
            ward=self.other_ward,
            risk_score=self.other_risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Please visit households in Alpha Ward today.",
            status=Alert.STATUS_DELIVERED,
            delivery_backend="internal-dashboard",
            guided_request_metadata={
                "selected_trigger_type": "FOLLOW_UP_REVIEW",
                "message_mode": "operator_edited",
                "message_preview_used": "Please visit households in Alpha Ward today.",
            },
            attempt_count=1,
            max_attempts=1,
            sent_at=timezone.now(),
        )

        self.authenticate(self.analyst_user.username)
        response = self.client.get(reverse("alert-intelligence", args=[alert.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message_source"]["mode"], "operator_edited")
        self.assertEqual(response.data["message_source"]["label"], "Edited by operator")
        self.assertEqual(response.data["message_source"]["trigger_type"], "FOLLOW_UP_REVIEW")

    def test_supervisor_can_view_alert_detail_for_assigned_ward_only(self):
        in_scope_alert = Alert.objects.create(
            ward=self.other_ward,
            risk_score=self.other_risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Ward two alert",
            status=Alert.STATUS_DELIVERED,
        )
        out_of_scope_alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Ward one alert",
            status=Alert.STATUS_DELIVERED,
        )

        self.authenticate(self.supervisor_user.username)

        in_scope_response = self.client.get(reverse("alert-detail", args=[in_scope_alert.id]))
        self.assertEqual(in_scope_response.status_code, status.HTTP_200_OK)
        self.assertEqual(in_scope_response.data["id"], in_scope_alert.id)

        out_of_scope_response = self.client.get(reverse("alert-detail", args=[out_of_scope_alert.id]))
        self.assertEqual(out_of_scope_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_supervisor_can_view_alert_intelligence_for_assigned_ward_only(self):
        in_scope_alert = Alert.objects.create(
            ward=self.other_ward,
            risk_score=self.other_risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Ward two alert intelligence",
            status=Alert.STATUS_DELIVERED,
        )
        out_of_scope_alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="dashboard",
            message="Ward one alert intelligence",
            status=Alert.STATUS_DELIVERED,
        )

        self.authenticate(self.supervisor_user.username)

        in_scope_response = self.client.get(reverse("alert-intelligence", args=[in_scope_alert.id]))
        self.assertEqual(in_scope_response.status_code, status.HTTP_200_OK)
        self.assertEqual(in_scope_response.data["alert"]["id"], in_scope_alert.id)

        out_of_scope_response = self.client.get(reverse("alert-intelligence", args=[out_of_scope_alert.id]))
        self.assertEqual(out_of_scope_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_notification_list_materializes_backend_owned_notifications(self):
        self.authenticate(self.analyst_user.username)

        response = self.client.get(reverse("notification-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["unread_count"], 1)
        self.assertEqual(response.data["highest_unread_severity"], DashboardNotification.SEVERITY_CRITICAL)
        self.assertEqual(response.data["system_status"], "ACTION_REQUIRED")
        high_risk_notification = next(
            item for item in response.data["results"] if item["type"] == DashboardNotification.TYPE_WARD_RISK_HIGH
        )
        self.assertEqual(high_risk_notification["category"], "trigger_review")
        self.assertIsNone(high_risk_notification["group_key"])
        self.assertEqual(high_risk_notification["href"], f"/overview?trigger_review={self.ward.id}")
        feed_notification = next(
            item for item in response.data["results"] if item["type"] == DashboardNotification.TYPE_FEED_STALE
        )
        self.assertEqual(feed_notification["category"], "system_health")
        self.assertEqual(feed_notification["group_key"], "data_freshness")
        self.assertTrue(any(item["state"] == DashboardNotification.STATE_NEW for item in response.data["results"]))

        page_size_response = self.client.get(reverse("notification-list"), {"page_size": 100})
        self.assertEqual(page_size_response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(page_size_response.data["results"]), 100)

    def test_notification_seen_transition_persists_and_records_audit_event(self):
        self.authenticate(self.analyst_user.username)
        list_response = self.client.get(reverse("notification-list"))
        notification = next(
            item for item in list_response.data["results"] if item["type"] == DashboardNotification.TYPE_WARD_RISK_HIGH
        )

        response = self.client.post(
            reverse("notification-seen", kwargs={"public_id": notification["public_id"]}),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["state"], DashboardNotification.STATE_SEEN)
        stored = DashboardNotification.objects.get(public_id=notification["public_id"])
        self.assertEqual(stored.state, DashboardNotification.STATE_SEEN)
        self.assertTrue(
            DashboardNotificationEvent.objects.filter(
                notification=stored,
                action=DashboardNotificationEvent.ACTION_SEEN,
                actor=self.analyst_user,
            ).exists()
        )

    def test_supervisor_notification_list_honors_ward_scope(self):
        RiskScore.objects.create(
            ward=self.other_ward,
            model_run=self.model_run,
            score=0.88,
            risk_level=Ward.RISK_HIGH,
            rainfall_mm=99.0,
            flood_indicator=0.7,
            predicted_cases=14,
            source=RiskScore.SOURCE_MODEL,
            model_version="v0-test",
            generated_at=timezone.now() + timedelta(minutes=1),
        )

        self.authenticate(self.supervisor_user.username)
        response = self.client.get(reverse("notification-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [item["title"] for item in response.data["results"]]
        self.assertIn("North Kadem: action required", titles)
        self.assertNotIn("North Kamagambo: action required", titles)

    def test_notification_stream_token_endpoint_issues_short_lived_stream_token(self):
        self.authenticate(self.analyst_user.username)

        response = self.client.get(reverse("notification-stream-token"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["websocket_path"], "/ws/notifications/stream/")
        self.assertEqual(response.data["expires_in_seconds"], 300)

        validated = AccessToken(response.data["token"])
        self.assertEqual(validated["purpose"], "dashboard_notifications_stream")
        self.assertEqual(validated["role"], self.analyst_user.role)

    def test_model_run_list_exposes_latest_runs(self):
        self.authenticate(self.analyst_user.username)

        response = self.client.get(reverse("model-run-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.model_run.id)
        self.assertEqual(response.data["results"][0]["model_version"], self.model_run.model_version)

    def test_risk_score_list_supports_generated_time_filters(self):
        self.authenticate(self.analyst_user.username)
        older_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="v0-older",
            status=ModelRun.STATUS_SUCCESS,
            completed_at=timezone.now() - timedelta(days=2),
        )
        older_score = RiskScore.objects.create(
            ward=self.other_ward,
            model_run=older_run,
            score=0.41,
            risk_level=Ward.RISK_LOW,
            rainfall_mm=20.0,
            flood_indicator=0.1,
            predicted_cases=2,
            source=RiskScore.SOURCE_MODEL,
            model_version="v0-older",
            generated_at=timezone.now() - timedelta(days=2),
        )

        response = self.client.get(
            reverse("risk-score-list"),
            {"generated_before": (timezone.now() - timedelta(days=1)).isoformat()},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["id"] for item in response.data["results"]}
        self.assertIn(older_score.id, returned_ids)
        self.assertNotIn(self.other_risk_score.id, returned_ids)

    def test_alert_list_supports_created_time_filters(self):
        self.authenticate(self.analyst_user.username)
        recent_alert = Alert.objects.create(
            ward=self.other_ward,
            risk_score=self.other_risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="Ops desk",
            message="Recent alert window",
            status=Alert.STATUS_QUEUED,
            delivery_backend="dashboard",
            external_id="recent-alert",
        )
        older_alert = Alert.objects.create(
            ward=self.other_ward,
            risk_score=self.other_risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="Ops desk",
            message="Older alert window",
            status=Alert.STATUS_DELIVERED,
            delivery_backend="dashboard",
            external_id="older-alert",
            sent_at=timezone.now() - timedelta(days=2),
        )
        older_created_at = timezone.now() - timedelta(days=2)
        Alert.objects.filter(pk=older_alert.pk).update(created_at=older_created_at)
        older_alert.refresh_from_db()

        response = self.client.get(
            reverse("alert-list"),
            {"created_before": (timezone.now() - timedelta(days=1)).isoformat()},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_ids = {item["id"] for item in response.data["results"]}
        self.assertIn(older_alert.id, returned_ids)
        self.assertNotIn(recent_alert.id, returned_ids)

    @override_settings(
        CHANNEL_LAYERS={
            "default": {
                "BACKEND": "channels.layers.InMemoryChannelLayer",
            }
        }
    )
    async def _exercise_notification_websocket_lifecycle(self):
        list_response = await sync_to_async(self.client.get)(reverse("notification-list"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        notification = next(
            item for item in list_response.data["results"] if item["type"] == DashboardNotification.TYPE_WARD_RISK_HIGH
        )

        token = AccessToken.for_user(self.analyst_user)
        token["purpose"] = "dashboard_notifications_stream"
        token["role"] = self.analyst_user.role
        token["ward_id"] = self.analyst_user.ward_id

        communicator = WebsocketCommunicator(
            application,
            f"/ws/notifications/stream/?token={token}",
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        initial = await communicator.receive_json_from()
        self.assertEqual(initial["event"], "notification.connected")
        self.assertEqual(initial["highest_unread_severity"], DashboardNotification.SEVERITY_CRITICAL)
        self.assertEqual(initial["system_status"], "ACTION_REQUIRED")
        self.assertTrue(any(feed["id"] == "risks" for feed in initial["feeds"]))
        self.assertEqual(initial["freshness"]["last_model_run_at"], self.model_run.completed_at.isoformat())
        self.assertEqual(initial["freshness"]["freshness_state"], "fresh")

        seen_response = await sync_to_async(self.client.post)(
            reverse("notification-seen", kwargs={"public_id": notification["public_id"]}),
            format="json",
        )
        self.assertEqual(seen_response.status_code, status.HTTP_200_OK)

        event = await communicator.receive_json_from()
        self.assertEqual(event["event"], "notification.updated")
        self.assertEqual(event["notification"]["public_id"], notification["public_id"])
        self.assertEqual(event["notification"]["state"], DashboardNotification.STATE_SEEN)
        self.assertEqual(event["highest_unread_severity"], DashboardNotification.SEVERITY_WARNING)
        self.assertEqual(event["system_status"], "DATA_FRESHNESS_DEGRADED")
        self.assertTrue(any(feed["id"] == "risks" for feed in event["feeds"]))
        self.assertIn("freshness", event)

        await communicator.disconnect()

    def test_alert_workflow_list_materializes_persisted_workflow_state(self):
        self.authenticate(self.analyst_user.username)

        response = self.client.get(reverse("alert-workflow-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(response.data["count"], 1)
        workflow = next(item for item in response.data["results"] if item["ward_id"] == self.ward.id)
        self.assertIn(workflow["decision_mode"], {"risk_only", "triggered"})
        self.assertIn("rules_basis", workflow)
        self.assertTrue(AlertWorkflowState.objects.filter(ward=self.ward).exists())

    def test_scenario_simulation_run_endpoint_creates_non_production_run(self):
        self.authenticate(self.analyst_user.username)

        response = self.client.post(
            reverse("scenario-simulation-run"),
            {"scenario_id": "RAINFALL_INCREASE", "rainfall_uplift_percent": 20},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["scenario_id"], "RAINFALL_INCREASE")
        self.assertEqual(response.data["summary"]["non_production"], True)
        self.assertGreaterEqual(len(response.data["ward_results"]), 1)

    def test_trigger_alert_context_returns_guided_backend_context(self):
        self.authenticate(self.supervisor_user.username)

        response = self.client.get(reverse("trigger-alert-context"), {"ward_id": self.other_ward.id}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["ward"]["id"], self.other_ward.id)
        self.assertEqual(response.data["risk"]["level"], self.other_risk_score.risk_level)
        self.assertIn("why_this_might_need_an_alert", response.data["system_context"])
        self.assertIn("recommended_trigger_type", response.data["system_context"])
        self.assertIn("confidence_label", response.data["system_context"])
        expected_labels = {
            "NONE": "No active trigger",
            "TRIGGER_ACTIVE": "Trigger active",
            "REVIEW_PENDING": "Awaiting review",
            "ACTION_IN_PROGRESS": "Action in progress",
            "RESOLVED": "Resolved",
        }
        self.assertEqual(
            response.data["system_context"]["trigger_status_label"],
            expected_labels[response.data["workflow"]["status"]],
        )
        self.assertEqual(response.data["recipient_preview"]["chv_count"], CHV.objects.filter(ward=self.other_ward, is_active=True).count())

    def test_trigger_alert_context_uses_no_active_delivery_for_resolved_no_alert_state(self):
        self.authenticate(self.supervisor_user.username)
        self.other_ward.current_risk_level = Ward.RISK_LOW
        self.other_ward.current_risk_score = 0.18
        self.other_ward.save(update_fields=["current_risk_level", "current_risk_score", "updated_at"])
        RiskScore.objects.create(
            ward=self.other_ward,
            model_run=self.model_run,
            score=0.18,
            risk_level=Ward.RISK_LOW,
            rainfall_mm=12.0,
            flood_indicator=0.05,
            predicted_cases=0,
            source=RiskScore.SOURCE_MODEL,
            model_version="v0-test",
        )

        response = self.client.get(reverse("trigger-alert-context"), {"ward_id": self.other_ward.id}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["workflow"]["status"], "RESOLVED")
        self.assertEqual(response.data["workflow"]["alert_delivery_state"], "no_active_delivery")
        self.assertEqual(response.data["workflow"]["alert_delivery_label"], "No active delivery")
        self.assertEqual(response.data["system_context"]["trigger_status_label"], "No active trigger")

    def test_trigger_alert_preview_returns_backend_generated_message(self):
        self.authenticate(self.supervisor_user.username)

        response = self.client.post(
            reverse("trigger-alert-preview"),
            {"ward_id": self.other_ward.id, "trigger_type": "FOLLOW_UP_REVIEW"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message_mode"], "backend_generated")
        self.assertTrue(response.data["supports_editing"])
        self.assertIn(self.other_ward.name, response.data["message_preview"])
        self.assertEqual(response.data["recipient_preview"]["chv_count"], CHV.objects.filter(ward=self.other_ward, is_active=True).count())

    def test_trigger_alert_preview_accepts_message_override(self):
        self.authenticate(self.supervisor_user.username)

        response = self.client.post(
            reverse("trigger-alert-preview"),
            {
                "ward_id": self.other_ward.id,
                "trigger_type": "FOLLOW_UP_REVIEW",
                "message_override": "  Custom field review message for Alpha team.  ",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message_mode"], "operator_edited")
        self.assertEqual(response.data["message_preview"], "Custom field review message for Alpha team.")

    def test_trigger_alert_preview_can_render_template_key_and_version(self):
        template = MessageTemplate.objects.create(
            template_key="cholera.alert.chv.guided_template_sms",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            language="en",
            version=1,
            title="Guided alert template",
            body="CHVs: {ward_name} has {predicted_cases} predicted cases. Confirm field conditions.",
            placeholders=["ward_name", "predicted_cases"],
            approval_status=MessageTemplate.APPROVAL_APPROVED,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
            owner="county_public_health_operations",
            risk_level=MessageTemplate.RISK_HIGH,
            public_health_caveats="Use only for governed cholera alert workflows.",
        )
        self.authenticate(self.supervisor_user.username)

        response = self.client.post(
            reverse("trigger-alert-preview"),
            {
                "ward_id": self.other_ward.id,
                "trigger_type": "FOLLOW_UP_REVIEW",
                "template_key": template.template_key,
                "template_version": template.version,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message_mode"], "template_rendered")
        self.assertFalse(response.data["supports_editing"])
        self.assertEqual(
            response.data["message_preview"],
            "CHVs: North Kadem has 7 predicted cases. Confirm field conditions.",
        )
        self.assertEqual(response.data["message_template"]["template_key"], template.template_key)
        self.assertEqual(response.data["message_template"]["template_version"], template.version)

    @patch("risk.views.trigger_alerts_task.delay", return_value=SimpleNamespace(id="task-123"))
    def test_supervisor_can_queue_alert_trigger(self, mock_delay):
        self.authenticate(self.supervisor_user.username)
        response = self.client.post(
            reverse("trigger-alerts"),
            {
                "ward_id": self.other_ward.id,
                "send_sms": True,
                "trigger_type": "FOLLOW_UP_REVIEW",
                "message_override": "Please visit households in Alpha Ward today.",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["task_id"], "task-123")
        self.assertIsNotNone(response.data["request_id"])
        self.assertIsNone(response.data["alert_id"])
        self.assertEqual(response.data["ward_id"], self.other_ward.id)
        self.assertEqual(response.data["ward_name"], self.other_ward.name)
        self.assertEqual(response.data["risk_level"], self.other_risk_score.risk_level)
        self.assertEqual(response.data["risk_score"], self.other_risk_score.score)
        self.assertEqual(response.data["predicted_cases"], self.other_risk_score.predicted_cases)
        self.assertTrue(response.data["send_sms"])
        self.assertEqual(response.data["trigger_type"], "FOLLOW_UP_REVIEW")
        self.assertEqual(response.data["message_mode"], "operator_edited")
        self.assertEqual(response.data["last_risk_update_at"], self.other_risk_score.generated_at)
        self.assertEqual(response.data["trigger_linkage_state"], "linked_existing_workflow")
        self.assertEqual(
            response.data["estimated_chv_recipient_count"],
            CHV.objects.filter(ward=self.other_ward, is_active=True).count(),
        )
        self.assertEqual(response.data["message"], "Alert request queued successfully.")
        self.assertIsNotNone(response.data["queued_at"])
        workflow = AlertWorkflowState.objects.get(ward=self.other_ward)
        event = workflow.events.first()
        self.assertIsNotNone(event)
        self.assertEqual(event.metadata["selected_trigger_type"], "FOLLOW_UP_REVIEW")
        self.assertEqual(event.metadata["send_sms"], True)
        self.assertEqual(event.metadata["message_mode"], "operator_edited")
        self.assertEqual(event.metadata["message_preview_used"], "Please visit households in Alpha Ward today.")
        self.assertEqual(event.metadata["request_id"], response.data["request_id"])
        mock_delay.assert_called_once()
        _, kwargs = mock_delay.call_args
        self.assertEqual(kwargs["trigger_type"], "FOLLOW_UP_REVIEW")
        self.assertEqual(kwargs["message_override"], "Please visit households in Alpha Ward today.")
        self.assertEqual(kwargs["guided_request_metadata"]["message_mode"], "operator_edited")
        self.assertEqual(kwargs["guided_request_metadata"]["request_id"], response.data["request_id"])

    @patch("risk.views.trigger_alerts_task.delay", return_value=SimpleNamespace(id="task-template-123"))
    def test_supervisor_can_queue_template_alert_trigger(self, mock_delay):
        template = MessageTemplate.objects.create(
            template_key="cholera.alert.chv.guided_queue_sms",
            audience_type=MessageTemplate.AUDIENCE_CHV,
            channel=MessageTemplate.CHANNEL_SMS,
            language="en",
            version=1,
            title="Guided queued alert template",
            body="CHVs: {ward_name} needs review for {predicted_cases} predicted cases.",
            placeholders=["ward_name", "predicted_cases"],
            approval_status=MessageTemplate.APPROVAL_APPROVED,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
            owner="county_public_health_operations",
            risk_level=MessageTemplate.RISK_HIGH,
            public_health_caveats="Use only for governed cholera alert workflows.",
        )
        self.authenticate(self.supervisor_user.username)

        response = self.client.post(
            reverse("trigger-alerts"),
            {
                "ward_id": self.other_ward.id,
                "send_sms": True,
                "trigger_type": "FOLLOW_UP_REVIEW",
                "template_key": template.template_key,
                "template_version": template.version,
                "template_language": "en",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["task_id"], "task-template-123")
        self.assertEqual(response.data["message_mode"], "template_rendered")
        workflow = AlertWorkflowState.objects.get(ward=self.other_ward)
        event = workflow.events.first()
        self.assertEqual(event.metadata["message_mode"], "template_rendered")
        self.assertEqual(event.metadata["message_template"]["template_key"], template.template_key)
        mock_delay.assert_called_once()
        _, kwargs = mock_delay.call_args
        self.assertEqual(kwargs["template_key"], template.template_key)
        self.assertEqual(kwargs["template_version"], template.version)
        self.assertEqual(kwargs["template_language"], "en")
        self.assertEqual(kwargs["template_context"], {})
        self.assertEqual(kwargs["guided_request_metadata"]["message_template"]["template_key"], template.template_key)

    def test_trigger_alert_requires_explicit_ward_context(self):
        self.authenticate(self.supervisor_user.username)
        response = self.client.post(
            reverse("trigger-alerts"),
            {"send_sms": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ward_id", response.data)

    @patch("risk.views.trigger_alerts_task.delay", return_value=SimpleNamespace(id="task-123"))
    def test_trigger_request_status_returns_pending_before_alert_materialization(self, mock_delay):
        self.authenticate(self.supervisor_user.username)
        response = self.client.post(
            reverse("trigger-alerts"),
            {"ward_id": self.other_ward.id, "send_sms": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        request_id = response.data["request_id"]

        status_response = self.client.get(
            reverse("trigger-alert-request-status", kwargs={"request_id": request_id})
        )

        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(status_response.data["status"], "PENDING_CREATION")
        self.assertIsNone(status_response.data["alert_id"])
        self.assertEqual(status_response.data["ward_id"], self.other_ward.id)
        self.assertEqual(status_response.data["created_alert_count"], 0)

    def test_trigger_request_status_returns_materialized_alert_after_creation(self):
        request_id = "11111111-1111-1111-1111-111111111111"
        create_alerts_for_riskscore(
            self.other_risk_score,
            send_sms_enabled=True,
            trigger_type="FOLLOW_UP_REVIEW",
            guided_request_metadata={
                "request_id": request_id,
                "selected_trigger_type": "FOLLOW_UP_REVIEW",
                "message_mode": "backend_generated",
            },
        )

        self.authenticate(self.supervisor_user.username)
        status_response = self.client.get(
            reverse("trigger-alert-request-status", kwargs={"request_id": request_id})
        )

        matching_alerts = Alert.objects.filter(guided_request_metadata__request_id=request_id)
        self.assertEqual(status_response.status_code, status.HTTP_200_OK)
        self.assertEqual(status_response.data["status"], "MATERIALIZED")
        self.assertIsNotNone(status_response.data["alert_id"])
        self.assertEqual(status_response.data["ward_id"], self.other_ward.id)
        self.assertEqual(status_response.data["created_alert_count"], matching_alerts.count())
        self.assertEqual(
            status_response.data["sms_alert_count"],
            matching_alerts.filter(channel=Alert.CHANNEL_SMS).count(),
        )

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
        alerts = create_alerts_for_riskscore(
            self.risk_score,
            send_sms_enabled=True,
            trigger_type="FOLLOW_UP_REVIEW",
            message_override="Please review field conditions in Ward One.",
        )

        self.assertEqual(len(alerts), 2)
        dashboard_alert = next(alert for alert in alerts if alert.channel == Alert.CHANNEL_DASHBOARD)
        sms_alert = next(alert for alert in alerts if alert.channel == Alert.CHANNEL_SMS)

        self.assertEqual(dashboard_alert.status, Alert.STATUS_DELIVERED)
        self.assertEqual(dashboard_alert.delivery_backend, "internal-dashboard")
        self.assertEqual(dashboard_alert.attempt_count, 1)
        self.assertEqual(dashboard_alert.message, "Please review field conditions in Ward One.")
        self.assertEqual(
            dashboard_alert.guided_request_metadata["surveillance_evidence"]["label_truth_state"],
            "no_surveillance_label_window",
        )
        self.assertFalse(
            dashboard_alert.guided_request_metadata["surveillance_evidence"]["proxy_only_as_confirmed_allowed"]
        )
        self.assertEqual(sms_alert.status, Alert.STATUS_QUEUED)
        self.assertEqual(sms_alert.delivery_backend, "stub")
        self.assertEqual(sms_alert.attempt_count, 0)
        self.assertEqual(sms_alert.max_attempts, 3)
        self.assertEqual(sms_alert.message, "Please review field conditions in Ward One.")
        self.assertIn("surveillance_evidence", sms_alert.guided_request_metadata)

    def test_create_alerts_for_riskscore_persists_guided_request_metadata_on_alerts(self):
        alerts = create_alerts_for_riskscore(
            self.risk_score,
            send_sms_enabled=True,
            trigger_type="FOLLOW_UP_REVIEW",
            guided_request_metadata={
                "selected_trigger_type": "FOLLOW_UP_REVIEW",
                "message_mode": "operator_edited",
                "message_preview_used": "Please review field conditions in Ward One.",
            },
        )

        for alert in alerts:
            self.assertEqual(alert.guided_request_metadata["selected_trigger_type"], "FOLLOW_UP_REVIEW")
            self.assertEqual(alert.guided_request_metadata["message_mode"], "operator_edited")

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


class SystemControlContractsTestCase(AuthenticatedAPITestCase):
    def test_system_control_status_exposes_admin_contracts(self):
        self.authenticate(self.admin_user.username)

        response = self.client.get(reverse("system-control-status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mode"], "control_contracts_enabled")
        self.assertTrue(response.data["can_retry_background_jobs"])
        self.assertTrue(response.data["can_run_manual_risk_scoring"])
        self.assertTrue(response.data["can_pause_alert_delivery"])
        self.assertFalse(response.data["alert_delivery_paused"])

    def test_system_control_status_is_read_only_for_analysts(self):
        self.authenticate(self.analyst_user.username)

        response = self.client.get(reverse("system-control-status"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["can_retry_background_jobs"])
        self.assertFalse(response.data["can_run_manual_risk_scoring"])
        self.assertFalse(response.data["can_pause_alert_delivery"])

    @patch("risk.views.deliver_alert_task.delay", return_value=SimpleNamespace(id="delivery-task"))
    def test_retry_control_queues_retryable_alert_delivery_tasks(self, mock_delay):
        queued_alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient=self.chv.phone_number,
            message="Queued alert",
            status=Alert.STATUS_QUEUED,
        )
        retry_alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient=self.chv.phone_number,
            message="Retry alert",
            status=Alert.STATUS_RETRY_PENDING,
            next_retry_at=timezone.now() - timedelta(minutes=1),
        )
        Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient=self.chv.phone_number,
            message="Delivered alert",
            status=Alert.STATUS_DELIVERED,
        )
        self.authenticate(self.admin_user.username)

        response = self.client.post(reverse("system-control-retry"), {"limit": 10}, format="json")

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["queued_alert_delivery_count"], 2)
        called_alert_ids = {call.args[0] for call in mock_delay.call_args_list}
        self.assertEqual(called_alert_ids, {queued_alert.id, retry_alert.id})
        self.assertEqual(response.data["task_ids"], ["delivery-task", "delivery-task"])

    @patch("risk.views.run_risk_model_task.delay", return_value=SimpleNamespace(id="risk-task"))
    def test_manual_risk_scoring_control_queues_model_task(self, mock_delay):
        self.authenticate(self.admin_user.username)

        response = self.client.post(
            reverse("system-control-manual-risk-scoring"),
            {"month": 5, "trigger_alerts": False, "send_sms": False},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["task_id"], "risk-task")
        mock_delay.assert_called_once_with(
            month=5,
            model_version="lr-v1",
            algorithm="logistic_regression",
            trigger_alerts=False,
            send_sms=False,
            dual_model=False,
            execution_context="manual_system_page",
            run_purpose="manual_live_scoring",
        )

    @patch("risk.services.send_sms")
    def test_alert_delivery_pause_persists_and_defers_sms_attempts(self, mock_send_sms):
        self.authenticate(self.admin_user.username)
        pause_response = self.client.post(
            reverse("system-control-alert-delivery-pause"),
            {"paused": True, "duration_minutes": 30, "reason": "Maintenance window"},
            format="json",
        )
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient=self.chv.phone_number,
            message="Escalate immediately",
            status=Alert.STATUS_QUEUED,
        )

        delivered_alert = deliver_alert(alert)
        alert.refresh_from_db()
        control = SystemControlState.objects.get(control_key=SystemControlState.KEY_ALERT_DELIVERY_PAUSE)

        self.assertEqual(pause_response.status_code, status.HTTP_200_OK)
        self.assertTrue(pause_response.data["alert_delivery_paused"])
        self.assertTrue(control.is_currently_active())
        self.assertEqual(delivered_alert.status, Alert.STATUS_RETRY_PENDING)
        self.assertEqual(alert.status, Alert.STATUS_RETRY_PENDING)
        self.assertEqual(alert.attempt_count, 0)
        self.assertEqual(alert.error_message, "Alert delivery paused by system control.")
        self.assertIsNotNone(alert.next_retry_at)
        mock_send_sms.assert_not_called()

    def test_alert_delivery_resume_clears_pause(self):
        self.authenticate(self.admin_user.username)
        self.client.post(
            reverse("system-control-alert-delivery-pause"),
            {"paused": True, "duration_minutes": 30, "reason": "Maintenance window"},
            format="json",
        )

        response = self.client.post(
            reverse("system-control-alert-delivery-pause"),
            {"paused": False, "reason": "Maintenance complete"},
            format="json",
        )

        control = SystemControlState.objects.get(control_key=SystemControlState.KEY_ALERT_DELIVERY_PAUSE)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["alert_delivery_paused"])
        self.assertFalse(control.is_currently_active())
        self.assertIsNone(control.active_until)

    def test_supervisor_cannot_mutate_system_controls(self):
        self.authenticate(self.supervisor_user.username)

        response = self.client.post(reverse("system-control-retry"), {"limit": 1}, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


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
                "language": "en",
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
                "language": "en",
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
    def test_celery_beat_schedule_includes_daily_facility_burden_forecast_run(self):
        schedule = settings.CELERY_BEAT_SCHEDULE["daily-facility-burden-forecast-run"]

        self.assertEqual(schedule["task"], "risk.tasks.run_facility_burden_forecast_task")
        self.assertEqual(schedule["kwargs"]["model_version"], "fnb-v1")
        self.assertEqual(schedule["kwargs"]["horizon_days"], 7)

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
        self.assertFalse(Ward.objects.filter(county="Migori", ward_code="").exists())
        self.assertFalse(HealthFacility.objects.filter(facility_code="").exists())
        self.assertEqual(
            Ward.objects.get(county="Migori", name="North Kamagambo").ward_code,
            "KE-WARD-1261",
        )
        self.assertTrue(Ward.objects.filter(county="Migori", name="Macalder/Kanyarwanda").exists())

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

    def test_seed_demo_data_command_can_seed_single_named_scenario_bundle(self):
        call_command("seed_demo_data", scenario_bundle="delivery_failure_concern")

        seeded_alerts = Alert.objects.filter(external_id__startswith="seed-scenario-")
        self.assertEqual(seeded_alerts.count(), 2)
        self.assertTrue(seeded_alerts.filter(status=Alert.STATUS_FAILED).exists())
        self.assertTrue(seeded_alerts.filter(status=Alert.STATUS_RETRY_PENDING).exists())
        self.assertTrue(
            RiskScore.objects.filter(notes__icontains="delivery_failure_concern", model_version="v0-demo").exists()
        )

    def test_seed_demo_data_command_lists_named_scenario_bundles(self):
        stdout = StringIO()

        call_command("seed_demo_data", list_scenario_bundles=True, stdout=stdout)

        rendered = stdout.getvalue()
        self.assertIn("decision_layer_full_suite", rendered)
        self.assertIn("stable_baseline", rendered)
        self.assertIn("localized_watch_cluster", rendered)
        self.assertIn("escalating_triggered_hotspot", rendered)
        self.assertIn("delivery_failure_concern", rendered)
        self.assertIn("facility_capacity_pressure", rendered)

    def test_run_facility_burden_forecast_command_persists_forecast_run_and_rows(self):
        call_command("seed_demo_data")

        call_command("run_facility_burden_forecast", model_version="fnb-v1")

        run = FacilityForecastRun.objects.get(model_version="fnb-v1")
        training_dataset = FeatureDataset.objects.get(dataset_ref=run.metadata["training_dataset_ref"])
        inference_dataset = FeatureDataset.objects.get(dataset_ref=run.metadata["inference_dataset_ref"])

        self.assertEqual(run.status, FacilityForecastRun.STATUS_SUCCESS)
        self.assertEqual(run.algorithm_name, "negative-binomial-baseline")
        self.assertEqual(run.metadata["execution_context"], "manual_command")
        self.assertEqual(run.metadata["promotion_target"], "forecast_preview_only")
        self.assertEqual(run.metadata["training_feature_dataset_id"], training_dataset.id)
        self.assertEqual(run.metadata["inference_feature_dataset_id"], inference_dataset.id)
        self.assertEqual(run.evaluation_metrics["target_mode"], "proxy_derived_facility_burden")
        self.assertGreater(run.training_row_count, 0)
        self.assertEqual(run.inference_row_count, HealthFacility.objects.filter(is_active=True).count())
        self.assertEqual(training_dataset.dataset_kind, FeatureDataset.KIND_TRAINING)
        self.assertEqual(training_dataset.schema_version, "facility-burden-v1")
        self.assertEqual(training_dataset.row_count, run.training_row_count)
        self.assertEqual(inference_dataset.dataset_kind, FeatureDataset.KIND_INFERENCE)
        self.assertEqual(inference_dataset.schema_version, "facility-burden-v1")
        self.assertEqual(inference_dataset.row_count, run.inference_row_count)
        self.assertEqual(FeatureDatasetRow.objects.filter(dataset=training_dataset).count(), training_dataset.row_count)
        self.assertEqual(FeatureDatasetRow.objects.filter(dataset=inference_dataset).count(), inference_dataset.row_count)
        self.assertTrue(
            FeatureDatasetRow.objects.filter(dataset=training_dataset, label__isnull=False).exists()
        )
        self.assertFalse(
            FeatureDatasetRow.objects.filter(dataset=inference_dataset, label__isnull=False).exists()
        )
        self.assertEqual(FacilityForecast.objects.filter(forecast_run=run).count(), run.inference_row_count)

    def test_run_facility_burden_forecast_command_async_queues_task(self):
        with patch("risk.management.commands.run_facility_burden_forecast.run_facility_burden_forecast_task.delay") as delay_mock:
            delay_mock.return_value = SimpleNamespace(id="facility-task-123")
            stdout = StringIO()

            call_command(
                "run_facility_burden_forecast",
                model_version="fnb-v2",
                run_async=True,
                stdout=stdout,
            )

        delay_mock.assert_called_once_with(model_version="fnb-v2", horizon_days=7)
        self.assertIn("Queued facility burden forecast task", stdout.getvalue())

    def test_promote_facility_burden_forecast_command_marks_run_as_promoted(self):
        call_command("seed_demo_data")
        call_command("run_facility_burden_forecast", model_version="fnb-vpromote")

        call_command(
            "promote_facility_burden_forecast",
            model_version="fnb-vpromote",
            promoted_by="auditor",
            note="promotion-test",
            allow_blocked_promotion=True,
        )

        run = FacilityForecastRun.objects.get(model_version="fnb-vpromote")
        self.assertEqual(run.metadata["promotion_target"], "dashboard_readiness_promoted")
        self.assertEqual(run.metadata["promoted_by"], "auditor")
        self.assertEqual(run.metadata["promotion_note"], "promotion-test")
        self.assertTrue(run.metadata["promotion_override_acknowledged"])

    def test_promote_facility_burden_forecast_command_requires_explicit_override_for_blocked_run(self):
        call_command("seed_demo_data")
        call_command("run_facility_burden_forecast", model_version="fnb-vblocked")

        with self.assertRaisesMessage(CommandError, "Promotion is blocked by unresolved evidence gaps."):
            call_command(
                "promote_facility_burden_forecast",
                model_version="fnb-vblocked",
                promoted_by="auditor",
            )

    def test_failed_facility_burden_forecast_run_is_persisted_with_failure_metadata(self):
        call_command("seed_demo_data")

        with patch("risk.facility_forecasting._fit_negative_binomial", side_effect=RuntimeError("nb-fit-failed")):
            with self.assertRaisesMessage(RuntimeError, "nb-fit-failed"):
                call_command("run_facility_burden_forecast", model_version="fnb-vfail")

        run = FacilityForecastRun.objects.get(model_version="fnb-vfail")
        self.assertEqual(run.status, FacilityForecastRun.STATUS_FAILED)
        self.assertEqual(run.metadata["failure_reason"], "nb-fit-failed")
        self.assertEqual(FacilityForecast.objects.filter(forecast_run=run).count(), 0)

    def test_evaluate_facility_burden_forecast_command_reports_not_promoted_decision(self):
        call_command("seed_demo_data")
        call_command("run_facility_burden_forecast", model_version="fnb-v1")

        stdout = StringIO()
        call_command("evaluate_facility_burden_forecast", stdout=stdout)
        payload = json.loads(stdout.getvalue())

        self.assertEqual(payload["current_run"]["model_version"], "fnb-v1")
        self.assertEqual(payload["decision"]["promotion_readiness"], "not_ready_for_promotion")
        self.assertIn("proxy_training_target_only", payload["decision"]["promotion_blockers"])

    def test_reconcile_ward_codes_command_restores_canonical_codes(self):
        call_command("seed_kenya_administrative_areas", counties=["Migori"])
        ward = Ward.objects.get(
            name="North Kamagambo",
            county="Migori",
        )
        ward.ward_code = "CCHIS-WARD-001"
        ward.save(update_fields=["ward_code"])

        call_command("reconcile_ward_codes", counties=["Migori"])

        ward.refresh_from_db()
        self.assertEqual(ward.ward_code, "KE-WARD-1261")

    def test_reconcile_ward_codes_command_normalizes_known_name_drift(self):
        Ward.objects.create(
            name="Macalder Kanyarwanda",
            county="Migori",
            sub_county="Nyatike",
            ward_code="CCHIS-WARD-003",
            is_active=True,
        )

        call_command("reconcile_ward_codes", counties=["Migori"])

        canonical = Ward.objects.get(county="Migori", name="Macalder/Kanyarwanda")
        self.assertEqual(canonical.ward_code, "KE-WARD-1285")

    def test_import_ward_geometry_command_dry_run_does_not_write_rows(self):
        call_command("seed_kenya_administrative_areas", counties=["Migori"])

        call_command(
            "import_ward_geometry",
            version_label="2026-04-25-dry-run",
            dry_run=True,
            strict=True,
        )

        self.assertEqual(WardGeometryDataset.objects.count(), 0)
        self.assertEqual(WardGeometryDatasetVersion.objects.count(), 0)
        self.assertEqual(WardGeometryFeature.objects.count(), 0)

    def test_import_ward_geometry_command_creates_managed_geometry_version(self):
        call_command("seed_kenya_administrative_areas", counties=["Migori"])

        call_command(
            "import_ward_geometry",
            version_label="2026-04-25-v1",
            strict=True,
            activate=True,
        )

        dataset = WardGeometryDataset.objects.get(slug="migori-ward-boundaries")
        version = WardGeometryDatasetVersion.objects.get(dataset=dataset, version_label="2026-04-25-v1")
        self.assertTrue(version.is_active)
        self.assertEqual(version.feature_count, 40)
        self.assertEqual(version.expected_feature_count, 40)
        self.assertEqual(version.source_url, "https://github.com/benaboki/Kenya-County-Assembly-Boundaries")
        self.assertEqual(version.source_crs, "EPSG:4326")
        self.assertEqual(version.validation_summary["backend_ward_code_match_count"], 40)
        self.assertEqual(version.validation_summary["backend_ward_name_fallback_match_count"], 0)
        self.assertEqual(WardGeometryFeature.objects.filter(dataset_version=version).count(), 40)
        self.assertFalse(
            WardGeometryFeature.objects.filter(dataset_version=version, matching_source="name").exists()
        )

    def test_import_ward_geometry_command_rejects_unknown_operator_username(self):
        call_command("seed_kenya_administrative_areas", counties=["Migori"])

        with self.assertRaisesMessage(CommandError, "Operator username not found: missing-operator"):
            call_command(
                "import_ward_geometry",
                version_label="unknown-operator-v1",
                strict=True,
                operator_username="missing-operator",
            )

    def test_import_ward_geometry_command_rejects_missing_source_url_provenance(self):
        call_command("seed_kenya_administrative_areas", counties=["Migori"])

        payload = json.loads(MIGORI_WARD_GEOMETRY_PATH.read_text())
        payload_metadata = payload.setdefault("metadata", {})
        payload_metadata.pop("source", None)
        payload_metadata.pop("source_url", None)

        with tempfile.NamedTemporaryFile("w", suffix=".geojson", delete=False) as handle:
            json.dump(payload, handle)
            temp_path = handle.name

        try:
            with self.assertRaisesMessage(
                CommandError,
                "source-url is required unless the input GeoJSON metadata provides source or source_url.",
            ):
                call_command(
                    "import_ward_geometry",
                    input_path=temp_path,
                    version_label="missing-source-url-v1",
                    strict=True,
                )
        finally:
            os.remove(temp_path)

    def test_activate_ward_geometry_version_command_switches_active_version_and_records_operator(self):
        call_command("seed_kenya_administrative_areas", counties=["Migori"])
        operator = User.objects.create_user(username="geometry_operator", password="ChangeMe123!")
        call_command(
            "import_ward_geometry",
            version_label="phase7-v1",
            strict=True,
            activate=True,
            operator_username=operator.username,
        )
        call_command(
            "import_ward_geometry",
            version_label="phase7-v2",
            strict=True,
            activate=False,
            operator_username=operator.username,
        )

        call_command(
            "activate_ward_geometry_version",
            dataset_slug="migori-ward-boundaries",
            version_label="phase7-v2",
            operator_username=operator.username,
            notes="Rollback forward to phase7-v2",
        )

        dataset = WardGeometryDataset.objects.get(slug="migori-ward-boundaries")
        v1 = WardGeometryDatasetVersion.objects.get(dataset=dataset, version_label="phase7-v1")
        v2 = WardGeometryDatasetVersion.objects.get(dataset=dataset, version_label="phase7-v2")
        self.assertFalse(v1.is_active)
        self.assertTrue(v2.is_active)
        self.assertEqual(v2.activated_by_id, operator.id)
        self.assertEqual(v2.imported_by_id, operator.id)
        self.assertEqual(v2.notes, "Rollback forward to phase7-v2")
        self.assertIsNotNone(Ward.objects.get(county="Migori", name="North Kamagambo").boundary)

    def test_activate_ward_geometry_version_command_rejects_unknown_operator_username(self):
        call_command("seed_kenya_administrative_areas", counties=["Migori"])
        call_command(
            "import_ward_geometry",
            version_label="phase7-unknown-operator-v1",
            strict=True,
            activate=True,
        )

        with self.assertRaisesMessage(CommandError, "Operator username not found: missing-operator"):
            call_command(
                "activate_ward_geometry_version",
                dataset_slug="migori-ward-boundaries",
                version_label="phase7-unknown-operator-v1",
                operator_username="missing-operator",
            )

    def test_ward_geometry_status_command_reports_versions(self):
        call_command("seed_kenya_administrative_areas", counties=["Migori"])
        operator = User.objects.create_user(username="status_operator", password="ChangeMe123!")
        call_command(
            "import_ward_geometry",
            version_label="phase7-status-v1",
            strict=True,
            activate=True,
            operator_username=operator.username,
            notes="Status test import",
        )
        with patch("sys.stdout.write") as mocked_write:
            call_command("ward_geometry_status", dataset_slug="migori-ward-boundaries")

        rendered = "".join(str(call.args[0]) for call in mocked_write.call_args_list)
        self.assertIn("phase7-status-v1", rendered)
        self.assertIn("migori-ward-boundaries", rendered)
        self.assertIn("https://github.com/benaboki/Kenya-County-Assembly-Boundaries", rendered)
        self.assertIn("\"imported_by\": \"status_operator\"", rendered)
        self.assertIn("\"activated_by\": \"status_operator\"", rendered)
        self.assertIn("\"source_license\": \"CC-BY-4.0\"", rendered)
        self.assertIn("\"notes\": \"Status test import\"", rendered)

    def test_activate_ward_geometry_version_command_syncs_canonical_fields_by_default(self):
        call_command("seed_kenya_administrative_areas", counties=["Migori"])
        call_command(
            "import_ward_geometry",
            version_label="phase10-v1",
            strict=True,
            activate=True,
        )
        call_command(
            "import_ward_geometry",
            version_label="phase10-v2",
            strict=True,
            activate=False,
        )
        ward = Ward.objects.get(county="Migori", name="North Kamagambo")
        ward.boundary = None
        ward.centroid = None
        ward.save(update_fields=["boundary", "centroid"])

        call_command(
            "activate_ward_geometry_version",
            dataset_slug="migori-ward-boundaries",
            version_label="phase10-v2",
        )

        ward.refresh_from_db()
        self.assertIsNotNone(ward.boundary)
        self.assertIsNotNone(ward.centroid)

    def test_activate_ward_geometry_version_command_skip_sync_leaves_canonical_fields_unchanged(self):
        call_command("seed_kenya_administrative_areas", counties=["Migori"])
        call_command(
            "import_ward_geometry",
            version_label="phase10-skip-v1",
            strict=True,
            activate=True,
        )
        call_command(
            "import_ward_geometry",
            version_label="phase10-skip-v2",
            strict=True,
            activate=False,
        )
        ward = Ward.objects.get(county="Migori", name="North Kamagambo")
        ward.boundary = None
        ward.centroid = None
        ward.save(update_fields=["boundary", "centroid"])

        call_command(
            "activate_ward_geometry_version",
            dataset_slug="migori-ward-boundaries",
            version_label="phase10-skip-v2",
            skip_sync=True,
        )

        ward.refresh_from_db()
        self.assertIsNone(ward.boundary)
        self.assertIsNone(ward.centroid)

    def test_sync_ward_geometry_fields_command_populates_boundary_and_centroid_from_active_version(self):
        call_command("seed_kenya_administrative_areas", counties=["Migori"])
        ward = Ward.objects.get(county="Migori", name="North Kamagambo")
        ward.boundary = None
        ward.centroid = None
        ward.save(update_fields=["boundary", "centroid"])

        call_command(
            "import_ward_geometry",
            version_label="phase8-sync-v1",
            strict=True,
            activate=True,
        )
        call_command("sync_ward_geometry_fields", dataset_slug="migori-ward-boundaries")

        ward.refresh_from_db()
        self.assertIsNotNone(ward.boundary)
        self.assertIsNotNone(ward.centroid)

    def test_merge_ward_records_command_moves_known_related_rows_and_deletes_legacy(self):
        legacy = Ward.objects.create(
            name="Macalder Kanyarwanda",
            county="Migori",
            sub_county="Nyatike",
            ward_code="CCHIS-WARD-003",
            is_active=True,
        )
        canonical = Ward.objects.create(
            name="Macalder/Kanyarwanda",
            county="Migori",
            sub_county="Nyatike",
            ward_code="KE-WARD-1285",
            is_active=True,
        )
        user = User.objects.create_user(username="ward_merge_user", password="ChangeMe123!")
        user.ward = legacy
        user.save(update_fields=["ward"])
        AuthAuditEvent.objects.create(
            event_type=AuthAuditEvent.EVENT_LOGIN_SUCCESS,
            status=AuthAuditEvent.STATUS_SUCCESS,
            ward=legacy,
        )
        chv = CHV.objects.create(name="Merge CHV", phone_number="+254700111111", ward=legacy, is_active=True)
        facility = HealthFacility.objects.create(
            name="Merge Facility",
            facility_code="MERGE-HF-001",
            ward=legacy,
            facility_type=HealthFacility.TYPE_DISPENSARY,
            ownership=HealthFacility.OWNERSHIP_PUBLIC,
            level=HealthFacility.LEVEL_2,
            is_active=True,
        )
        model_run = ModelRun.objects.create(model_version="merge-test", status=ModelRun.STATUS_SUCCESS)
        risk_score = RiskScore.objects.create(
            ward=legacy,
            model_run=model_run,
            score=0.7,
            risk_level=Ward.RISK_MEDIUM,
            predicted_cases=5,
        )
        alert = Alert.objects.create(
            ward=legacy,
            risk_score=risk_score,
            recipient="+254700111111",
            message="test",
        )
        triage = TriageSession.objects.create(ward=legacy)
        ussd = UssdSessionLog.objects.create(session_id="merge-session", ward=legacy)
        sync = SyncQueue.objects.create(client_submission_id="merge-sync", ward=legacy)

        call_command(
            "merge_ward_records",
            county="Migori",
            legacy_name="Macalder Kanyarwanda",
            canonical_name="Macalder/Kanyarwanda",
        )

        self.assertFalse(Ward.objects.filter(id=legacy.id).exists())
        user.refresh_from_db()
        chv.refresh_from_db()
        facility.refresh_from_db()
        risk_score.refresh_from_db()
        alert.refresh_from_db()
        triage.refresh_from_db()
        ussd.refresh_from_db()
        sync.refresh_from_db()
        self.assertEqual(user.ward_id, canonical.id)
        self.assertEqual(chv.ward_id, canonical.id)
        self.assertEqual(facility.ward_id, canonical.id)
        self.assertEqual(risk_score.ward_id, canonical.id)
        self.assertEqual(alert.ward_id, canonical.id)
        self.assertEqual(triage.ward_id, canonical.id)
        self.assertEqual(ussd.ward_id, canonical.id)
        self.assertEqual(sync.ward_id, canonical.id)
        self.assertEqual(AuthAuditEvent.objects.filter(ward=canonical).count(), 1)

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
        self.assertEqual(model_run.feature_schema_version, "baseline-v1")
        self.assertTrue(model_run.training_dataset_ref.startswith("training-baseline-v1-month-4-"))
        self.assertTrue(model_run.inference_dataset_ref.startswith("inference-baseline-v1-month-4-"))
        self.assertIsNotNone(model_run.training_feature_dataset)
        self.assertIsNotNone(model_run.inference_feature_dataset)
        self.assertEqual(model_run.training_feature_dataset.dataset_kind, FeatureDataset.KIND_TRAINING)
        self.assertEqual(model_run.inference_feature_dataset.dataset_kind, FeatureDataset.KIND_INFERENCE)
        self.assertEqual(model_run.training_feature_dataset.schema_version, "baseline-v1")
        self.assertEqual(model_run.inference_feature_dataset.schema_version, "baseline-v1")
        self.assertEqual(model_run.training_feature_dataset.row_count, 8)
        self.assertEqual(model_run.inference_feature_dataset.row_count, 2)
        self.assertEqual(FeatureDatasetRow.objects.filter(dataset=model_run.training_feature_dataset).count(), 8)
        self.assertEqual(FeatureDatasetRow.objects.filter(dataset=model_run.inference_feature_dataset).count(), 2)
        self.assertEqual(model_run.metadata["algorithm"], "logistic_regression")
        self.assertEqual(model_run.metadata["promotion_state"], "promotion_blocked")
        self.assertTrue(model_run.metadata["requested_alert_eligible"])
        self.assertFalse(model_run.metadata["alert_eligible"])
        self.assertEqual(model_run.metadata["operational_trust"]["prediction_state"], TRUST_STATE_DEGRADED)
        self.assertTrue(model_run.metadata["automatic_alerts_blocked_by_trust_policy"] is False)
        self.assertEqual(model_run.metadata["execution_context"], "manual_command")
        self.assertEqual(model_run.metadata["run_purpose"], "live_scoring")
        self.assertEqual(model_run.metadata["promotion_target"], "benchmark_only")
        self.assertIn(
            "surveillance_training_labels_not_goal_aligned",
            model_run.metadata["live_promotion_policy"]["blockers"],
        )
        self.assertIn("phase_4_temporal_promotion_missing", model_run.metadata["live_promotion_policy"]["blockers"])
        self.assertEqual(model_run.metadata["retraining_policy"], "manual_promotion_only")

    @patch("risk.tasks.trigger_alerts_task.delay", return_value=SimpleNamespace(id="truth-policy-task"))
    def test_seeded_training_fallback_blocks_live_promotion_even_with_fresh_rainfall(self, mock_delay):
        ward = Ward.objects.create(
            name="Ward Truth Policy",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.20,
            is_active=True,
        )
        ETLHeartbeat.objects.create(component=ETLHeartbeat.COMPONENT_SCHEDULER)
        ETLHeartbeat.objects.create(component=ETLHeartbeat.COMPONENT_WORKER)
        rainfall_run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="live",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="open-meteo-forecast",
            source_timestamp=timezone.now(),
            freshness_state=IngestionRun.FRESHNESS_FRESH,
            fallback_used=False,
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now(),
        )
        training_dataset = FeatureDataset.objects.create(
            dataset_ref="training-seeded-truth-policy",
            dataset_kind=FeatureDataset.KIND_TRAINING,
            schema_version="baseline-v1",
            source_kind=FeatureDataset.SOURCE_KIND_SEEDED,
            month=4,
            feature_keys=["rainfall_mm", "flood_indicator", "historical_cases", "month", "seasonality", "population_proxy"],
            row_count=2,
            lineage_metadata={
                "surveillance_label_usage": "seeded_training_baseline_not_goal_aligned",
                "training_label_seeded_demo_row_count": 2,
                "training_label_readiness": {
                    "ready": False,
                    "reason": "missing_surveillance_label_dataset",
                },
                "surveillance_label_truth_gate": {
                    "proxy_only_as_confirmed_allowed": False,
                    "confirmed_truth_required_for_confirmed_outbreak_claims": True,
                },
            },
        )
        inference_dataset = FeatureDataset.objects.create(
            dataset_ref="inference-live-truth-policy",
            dataset_kind=FeatureDataset.KIND_INFERENCE,
            schema_version="baseline-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=4,
            feature_keys=["rainfall_mm", "flood_indicator", "historical_cases", "month", "seasonality", "population_proxy"],
            row_count=1,
            lineage_metadata={},
        )
        training_rows = [
            WardFeatureRow(1, "Train A", 120.0, 0.8, 14, 4, 5400, 1),
            WardFeatureRow(2, "Train B", 60.0, 0.3, 5, 4, 4700, 0),
        ]
        inference_rows = [WardFeatureRow(ward.id, ward.name, 115.0, 0.78, 12, 4, 5000, None)]

        with patch(
            "risk.ml.pipeline.build_training_feature_dataset",
            return_value=TrainingDataset(rows=training_rows, feature_dataset=training_dataset),
        ), patch(
            "risk.ml.pipeline.build_inference_feature_dataset",
            return_value=InferenceDataset(
                rows=inference_rows,
                feature_dataset=inference_dataset,
                rainfall_ingestion_run=rainfall_run,
            ),
        ):
            created_scores = run_mock_prediction_pipeline(
                month=4,
                model_version="lr-truth-policy-v1",
                trigger_alerts=True,
            )

        self.assertEqual(len(created_scores), 1)
        model_run = ModelRun.objects.get(model_version="lr-truth-policy-v1")
        self.assertEqual(model_run.metadata["operational_trust"]["alert_state"], ALERT_STATE_ALLOWED)
        self.assertTrue(model_run.metadata["requested_alert_eligible"])
        self.assertFalse(model_run.metadata["alert_eligible"])
        self.assertEqual(model_run.metadata["promotion_state"], "promotion_blocked")
        self.assertEqual(model_run.metadata["promotion_target"], "benchmark_only")
        self.assertTrue(model_run.metadata["automatic_alerts_blocked_by_promotion_policy"])
        self.assertFalse(model_run.metadata["automatic_alerts_blocked_by_trust_policy"])
        self.assertIn("seeded_training_labels_present", model_run.metadata["live_promotion_policy"]["blockers"])
        self.assertIn("phase_4_temporal_promotion_missing", model_run.metadata["live_promotion_policy"]["blockers"])
        mock_delay.assert_not_called()

    def test_run_risk_model_dual_model_mode_persists_shared_dataset_lineage(self):
        Ward.objects.create(
            name="Ward Alpha",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.20,
            is_active=True,
        )
        Ward.objects.create(
            name="Ward Beta",
            county="Migori",
            sub_county="Nyatike",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.55,
            is_active=True,
        )

        call_command(
            "run_risk_model",
            "--month=4",
            "--model-version=lr-dual-v1",
            "--dual-model",
            "--benchmark-version=rf-dual-v1",
        )

        self.assertEqual(ModelRun.objects.filter(status=ModelRun.STATUS_SUCCESS).count(), 2)
        self.assertEqual(RiskScore.objects.count(), 4)

        primary_run = ModelRun.objects.get(model_version="lr-dual-v1")
        benchmark_run = ModelRun.objects.get(model_version="rf-dual-v1")

        self.assertEqual(primary_run.algorithm_name, "logistic-regression-baseline")
        self.assertEqual(benchmark_run.algorithm_name, "random-forest-benchmark")
        self.assertEqual(primary_run.training_dataset_ref, benchmark_run.training_dataset_ref)
        self.assertEqual(primary_run.inference_dataset_ref, benchmark_run.inference_dataset_ref)
        self.assertEqual(primary_run.training_feature_dataset_id, benchmark_run.training_feature_dataset_id)
        self.assertEqual(primary_run.inference_feature_dataset_id, benchmark_run.inference_feature_dataset_id)
        self.assertEqual(primary_run.metadata["run_role"], "primary")
        self.assertEqual(benchmark_run.metadata["run_role"], "benchmark")
        self.assertEqual(primary_run.metadata["run_purpose"], "live_scoring")
        self.assertEqual(benchmark_run.metadata["run_purpose"], "benchmark_scoring")
        self.assertEqual(primary_run.metadata["execution_context"], "manual_command")
        self.assertEqual(benchmark_run.metadata["execution_context"], "manual_command")
        self.assertTrue(primary_run.metadata["requested_alert_eligible"])
        self.assertFalse(primary_run.metadata["alert_eligible"])
        self.assertFalse(benchmark_run.metadata["alert_eligible"])
        self.assertEqual(primary_run.metadata["promotion_state"], "promotion_blocked")
        self.assertEqual(benchmark_run.metadata["promotion_state"], "benchmark_only")
        self.assertEqual(primary_run.metadata["promotion_target"], "benchmark_only")
        self.assertEqual(benchmark_run.metadata["promotion_target"], "benchmark_only")
        self.assertIn("phase_4_temporal_promotion_missing", primary_run.metadata["live_promotion_policy"]["blockers"])
        self.assertEqual(primary_run.metadata["benchmark_group_ref"], benchmark_run.metadata["benchmark_group_ref"])
        self.assertEqual(
            RiskScore.objects.filter(model_run=primary_run, source=RiskScore.SOURCE_MODEL).count(),
            2,
        )
        self.assertEqual(
            RiskScore.objects.filter(model_run=benchmark_run, source=RiskScore.SOURCE_MODEL).count(),
            2,
        )
        self.assertEqual(FeatureDataset.objects.filter(dataset_kind=FeatureDataset.KIND_TRAINING).count(), 1)
        self.assertEqual(
            FeatureDataset.objects.filter(
                dataset_kind=FeatureDataset.KIND_INFERENCE,
                schema_version=primary_run.feature_schema_version,
            ).count(),
            1,
        )
        self.assertEqual(
            FeatureDataset.objects.filter(
                dataset_kind=FeatureDataset.KIND_INFERENCE,
                schema_version=POPULATION_EXPOSURE_FEATURE_SCHEMA_VERSION,
            ).count(),
            1,
        )

    def test_run_random_forest_benchmark_command_creates_benchmark_only_outputs(self):
        Ward.objects.create(
            name="Ward RF One",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.20,
            is_active=True,
        )
        Ward.objects.create(
            name="Ward RF Two",
            county="Migori",
            sub_county="Nyatike",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.55,
            is_active=True,
        )

        call_command("run_random_forest_benchmark", "--month=4", "--model-version=rf-test-v1")

        self.assertEqual(ModelRun.objects.filter(model_version="rf-test-v1", status=ModelRun.STATUS_SUCCESS).count(), 1)
        model_run = ModelRun.objects.get(model_version="rf-test-v1")
        self.assertEqual(model_run.algorithm_name, "random-forest-benchmark")
        self.assertEqual(model_run.metadata["execution_context"], "manual_command")
        self.assertEqual(model_run.metadata["run_purpose"], "benchmark_scoring")
        self.assertEqual(model_run.metadata["promotion_target"], "benchmark_only")
        self.assertFalse(model_run.metadata["alert_eligible"])
        self.assertEqual(model_run.evaluation_metrics["algorithm"], "random_forest")
        self.assertIn("feature_importances", model_run.evaluation_metrics)
        self.assertEqual(RiskScore.objects.filter(model_run=model_run, source=RiskScore.SOURCE_MODEL).count(), 2)

    def test_run_risk_model_random_forest_standalone_is_labeled_as_benchmark_scoring(self):
        Ward.objects.create(
            name="Ward RF Generic One",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.20,
            is_active=True,
        )
        Ward.objects.create(
            name="Ward RF Generic Two",
            county="Migori",
            sub_county="Nyatike",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.55,
            is_active=True,
        )

        call_command(
            "run_risk_model",
            "--month=4",
            "--model-version=rf-generic-v1",
            "--algorithm=random_forest",
        )

        model_run = ModelRun.objects.get(model_version="rf-generic-v1")
        self.assertEqual(model_run.algorithm_name, "random-forest-benchmark")
        self.assertEqual(model_run.metadata["run_purpose"], "benchmark_scoring")
        self.assertEqual(model_run.metadata["promotion_target"], "benchmark_only")
        self.assertFalse(model_run.metadata["alert_eligible"])

    @patch("risk.tasks.trigger_alerts_task.delay", return_value=SimpleNamespace(id="task-123"))
    def test_run_risk_model_degraded_inputs_suppress_automatic_alerts(self, mock_delay):
        Ward.objects.create(
            name="Ward Delta",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_HIGH,
            current_risk_score=0.92,
            is_active=True,
        )
        CHV.objects.create(
            name="CHV Delta",
            phone_number="+254700010099",
            ward=Ward.objects.get(name="Ward Delta"),
            is_active=True,
            language="en",
        )

        call_command("run_risk_model", "--month=4", "--model-version=lr-trust-v1", "--trigger-alerts")

        model_run = ModelRun.objects.get(model_version="lr-trust-v1")
        self.assertEqual(model_run.metadata["operational_trust"]["prediction_state"], TRUST_STATE_DEGRADED)
        self.assertEqual(model_run.metadata["operational_trust"]["alert_state"], ALERT_STATE_BLOCKED)
        self.assertTrue(model_run.metadata["automatic_alerts_blocked_by_trust_policy"])
        self.assertTrue(model_run.metadata["automatic_alerts_blocked_by_promotion_policy"])
        self.assertFalse(model_run.metadata["trigger_alerts"])
        mock_delay.assert_not_called()

    def test_operational_trust_blocks_predictions_when_live_source_is_stale(self):
        ward = Ward.objects.create(
            name="Blocked Ward",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.20,
            is_active=True,
        )
        stale_run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="live",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="open-meteo-forecast",
            source_timestamp=timezone.now() - timedelta(hours=30),
            freshness_state=IngestionRun.FRESHNESS_STALE,
            fallback_used=False,
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now(),
        )
        training_dataset = FeatureDataset.objects.create(
            dataset_ref="training-test-phase5",
            dataset_kind=FeatureDataset.KIND_TRAINING,
            schema_version="baseline-v1",
            source_kind=FeatureDataset.SOURCE_KIND_SEEDED,
            month=4,
            feature_keys=["rainfall_mm", "flood_indicator", "historical_cases", "month", "seasonality", "population_proxy"],
            row_count=2,
            lineage_metadata={},
        )
        inference_dataset = FeatureDataset.objects.create(
            dataset_ref="inference-test-phase5",
            dataset_kind=FeatureDataset.KIND_INFERENCE,
            schema_version="baseline-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=4,
            feature_keys=["rainfall_mm", "flood_indicator", "historical_cases", "month", "seasonality", "population_proxy"],
            row_count=1,
            lineage_metadata={},
        )
        training_rows = [
            WardFeatureRow(1, "Train A", 120.0, 0.8, 14, 4, 5400, 1),
            WardFeatureRow(2, "Train B", 60.0, 0.3, 5, 4, 4700, 0),
        ]
        inference_rows = [
            WardFeatureRow(ward.id, ward.name, 115.0, 0.78, 12, 4, 5000, None),
        ]

        with patch(
            "risk.ml.pipeline.build_training_feature_dataset",
            return_value=TrainingDataset(rows=training_rows, feature_dataset=training_dataset),
        ), patch(
            "risk.ml.pipeline.build_inference_feature_dataset",
            return_value=InferenceDataset(
                rows=inference_rows,
                feature_dataset=inference_dataset,
                rainfall_ingestion_run=stale_run,
            ),
        ):
            created_scores = run_mock_prediction_pipeline(month=4, model_version="lr-stale-v1")

        self.assertEqual(created_scores, [])
        self.assertTrue(ModelRun.objects.filter(model_version="lr-stale-v1").exists())
        blocked_run = ModelRun.objects.get(model_version="lr-stale-v1")
        self.assertEqual(blocked_run.status, ModelRun.STATUS_FAILED)
        self.assertEqual(blocked_run.algorithm_name, "logistic-regression-baseline")
        self.assertEqual(blocked_run.training_feature_dataset_id, training_dataset.id)
        self.assertEqual(blocked_run.inference_feature_dataset_id, inference_dataset.id)
        self.assertTrue(blocked_run.metadata["scoring_blocked_by_trust_policy"])
        self.assertEqual(blocked_run.metadata["operational_trust"]["prediction_state"], TRUST_STATE_BLOCKED)
        self.assertFalse(RiskScore.objects.filter(model_version="lr-stale-v1").exists())

    def test_operational_trust_blocks_dual_model_runs_with_auditable_modelrun_records(self):
        ward = Ward.objects.create(
            name="Blocked Dual Ward",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.10,
            is_active=True,
        )
        stale_run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="live",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="open-meteo-forecast",
            source_timestamp=timezone.now() - timedelta(hours=30),
            freshness_state=IngestionRun.FRESHNESS_STALE,
            fallback_used=False,
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now(),
        )
        training_dataset = FeatureDataset.objects.create(
            dataset_ref="training-test-phase5-dual",
            dataset_kind=FeatureDataset.KIND_TRAINING,
            schema_version="baseline-v1",
            source_kind=FeatureDataset.SOURCE_KIND_SEEDED,
            month=4,
            feature_keys=["rainfall_mm", "flood_indicator", "historical_cases", "month", "seasonality", "population_proxy"],
            row_count=2,
            lineage_metadata={},
        )
        inference_dataset = FeatureDataset.objects.create(
            dataset_ref="inference-test-phase5-dual",
            dataset_kind=FeatureDataset.KIND_INFERENCE,
            schema_version="baseline-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=4,
            feature_keys=["rainfall_mm", "flood_indicator", "historical_cases", "month", "seasonality", "population_proxy"],
            row_count=1,
            lineage_metadata={},
        )
        training_rows = [
            WardFeatureRow(1, "Train A", 120.0, 0.8, 14, 4, 5400, 1),
            WardFeatureRow(2, "Train B", 60.0, 0.3, 5, 4, 4700, 0),
        ]
        inference_rows = [
            WardFeatureRow(ward.id, ward.name, 115.0, 0.78, 12, 4, 5000, None),
        ]

        with patch(
            "risk.ml.pipeline.build_training_feature_dataset",
            return_value=TrainingDataset(rows=training_rows, feature_dataset=training_dataset),
        ), patch(
            "risk.ml.pipeline.build_inference_feature_dataset",
            return_value=InferenceDataset(
                rows=inference_rows,
                feature_dataset=inference_dataset,
                rainfall_ingestion_run=stale_run,
            ),
        ):
            created_scores = run_mock_prediction_pipeline(
                month=4,
                model_version="lr-stale-dual-v1",
                dual_model=True,
                benchmark_model_version="rf-stale-dual-v1",
            )

        self.assertEqual(created_scores, [])
        self.assertEqual(
            ModelRun.objects.filter(model_version__in=["lr-stale-dual-v1", "rf-stale-dual-v1"]).count(),
            2,
        )
        primary_run = ModelRun.objects.get(model_version="lr-stale-dual-v1")
        benchmark_run = ModelRun.objects.get(model_version="rf-stale-dual-v1")
        self.assertEqual(primary_run.status, ModelRun.STATUS_FAILED)
        self.assertEqual(benchmark_run.status, ModelRun.STATUS_FAILED)
        self.assertEqual(primary_run.metadata["run_role"], "primary")
        self.assertEqual(benchmark_run.metadata["run_role"], "benchmark")
        self.assertEqual(primary_run.metadata["benchmark_group_ref"], benchmark_run.metadata["benchmark_group_ref"])
        self.assertTrue(primary_run.metadata["scoring_blocked_by_trust_policy"])
        self.assertTrue(benchmark_run.metadata["scoring_blocked_by_trust_policy"])
        self.assertFalse(RiskScore.objects.filter(model_version__in=["lr-stale-dual-v1", "rf-stale-dual-v1"]).exists())

    def test_seed_demo_data_assigns_model_run_to_seeded_model_scores(self):
        call_command("seed_demo_data")

        self.assertTrue(ModelRun.objects.filter(model_version="v0-demo", status=ModelRun.STATUS_SUCCESS).exists())
        self.assertFalse(RiskScore.objects.filter(source=RiskScore.SOURCE_MODEL, model_run__isnull=True).exists())
        demo_run = ModelRun.objects.get(model_version="v0-demo")
        self.assertEqual(demo_run.metadata["execution_context"], "seeded_demo")
        self.assertEqual(demo_run.metadata["run_purpose"], "demo_seed")
        self.assertEqual(demo_run.metadata["promotion_target"], "demo_only")
        self.assertFalse(demo_run.metadata["alert_eligible"])

    @patch("risk.management.commands.run_random_forest_benchmark.run_random_forest_benchmark_task.delay")
    def test_run_random_forest_benchmark_command_can_queue_task(self, mock_delay):
        mock_delay.return_value = SimpleNamespace(id="rf-task-123")

        call_command("run_random_forest_benchmark", "--month=4", "--model-version=rf-queued-v1", "--async")

        mock_delay.assert_called_once_with(month=4, model_version="rf-queued-v1")

    def test_compare_model_candidates_command_emits_conservative_decision_summary(self):
        Ward.objects.create(
            name="Ward Compare One",
            county="Migori",
            sub_county="Rongo",
            current_risk_level=Ward.RISK_LOW,
            current_risk_score=0.20,
            is_active=True,
        )
        Ward.objects.create(
            name="Ward Compare Two",
            county="Migori",
            sub_county="Nyatike",
            current_risk_level=Ward.RISK_MEDIUM,
            current_risk_score=0.55,
            is_active=True,
        )

        call_command("run_risk_model", "--month=4", "--model-version=lr-compare-v1")
        call_command("run_random_forest_benchmark", "--month=4", "--model-version=rf-compare-v1")

        out = StringIO()
        call_command(
            "compare_model_candidates",
            "--lr-version=lr-compare-v1",
            "--rf-version=rf-compare-v1",
            stdout=out,
        )
        payload = json.loads(out.getvalue())

        self.assertEqual(payload["decision"]["recommended_primary_model"], "logistic_regression")
        self.assertEqual(payload["decision"]["governance_mode"], "shadow_benchmark_mode")
        self.assertEqual(payload["decision"]["promotion_readiness"], "not_ready_for_promotion")
        self.assertEqual(payload["decision"]["candidate_scoring_task"], "risk.tasks.run_risk_model_task")
        self.assertEqual(payload["decision"]["live_alert_task"], None)
        self.assertEqual(payload["decision"]["dashboard_wording_impact"], "do_not_label_candidate_scores_as_live_promoted")
        self.assertEqual(payload["decision"]["benchmark_only_tasks"], ["risk.tasks.run_random_forest_benchmark_task"])
        self.assertEqual(payload["logistic_regression"]["model_version"], "lr-compare-v1")
        self.assertEqual(payload["random_forest"]["model_version"], "rf-compare-v1")
        self.assertTrue(payload["comparison"]["same_feature_schema"])
        self.assertIn("lead_time_evidence_missing", payload["decision"]["promotion_blockers"])
        self.assertIn("out_of_time_validation_missing", payload["decision"]["promotion_blockers"])
        self.assertIn("training_truth_gate_missing", payload["decision"]["promotion_blockers"])
        self.assertIn("climate_coverage_evidence_missing", payload["decision"]["promotion_blockers"])
        self.assertFalse(payload["decision"]["evidence_assessment"]["calibration_score"]["logistic_regression"])
        self.assertFalse(payload["decision"]["evidence_assessment"]["phase_4_training_truth_gate_passed"]["logistic_regression"])
        self.assertFalse(payload["decision"]["evidence_assessment"]["climate_coverage_gate_passed"]["logistic_regression"])
        self.assertEqual(payload["decision"]["retraining_task"], None)

    def test_build_model_comparison_summary_marks_input_mismatch_as_promotion_blocker(self):
        logistic_run = ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version="lr-mismatch-v1",
            status=ModelRun.STATUS_SUCCESS,
            month=4,
            feature_schema_version="baseline-v1",
            training_dataset_ref="training-a",
            inference_dataset_ref="inference-a",
            evaluation_metrics={"training_accuracy": 0.71},
            metadata={"promotion_target": "live_baseline"},
            completed_at=timezone.now(),
        )
        random_forest_run = ModelRun.objects.create(
            algorithm_name="random-forest-benchmark",
            model_version="rf-mismatch-v1",
            status=ModelRun.STATUS_SUCCESS,
            month=4,
            feature_schema_version="baseline-v2",
            training_dataset_ref="training-b",
            inference_dataset_ref="inference-b",
            evaluation_metrics={"training_accuracy": 0.88},
            metadata={"promotion_target": "benchmark_only"},
            completed_at=timezone.now(),
        )

        payload = build_model_comparison_summary(
            logistic_run=logistic_run,
            random_forest_run=random_forest_run,
        )

        self.assertEqual(payload["decision"]["comparison_validity"], "comparison_input_mismatch")
        self.assertIn("feature_or_dataset_mismatch", payload["decision"]["promotion_blockers"])
        self.assertEqual(payload["decision"]["recommended_primary_model"], "logistic_regression")
        self.assertEqual(payload["decision"]["governance_mode"], "shadow_benchmark_mode")
        self.assertFalse(payload["comparison"]["same_feature_schema"])

    def test_describe_boosting_readiness_command_reports_candidate_only_state(self):
        out = StringIO()
        call_command("describe_boosting_readiness", stdout=out)
        payload = json.loads(out.getvalue())

        self.assertIsNone(payload["live_state"]["current_live_baseline"])
        self.assertEqual(payload["live_state"]["primary_scoring_candidate"], "logistic_regression")
        self.assertEqual(payload["live_state"]["promotion_state"], "candidate_scoring_until_phase_4_promotion")
        self.assertEqual(payload["live_state"]["current_benchmark_model"], "random_forest")
        self.assertFalse(payload["candidate_models"]["xgboost"]["runnable"])
        self.assertFalse(payload["candidate_models"]["lightgbm"]["runnable"])
        self.assertTrue(payload["decision"]["do_not_enable_in_run_risk_model"])

    def test_boosting_readiness_summary_requires_stricter_promotion_gates(self):
        payload = build_boosting_readiness_summary()

        self.assertTrue(payload["promotion_gates_stricter_than_random_forest"]["lead_time_evidence_required"])
        self.assertTrue(payload["promotion_gates_stricter_than_random_forest"]["calibration_review_required"])
        self.assertEqual(payload["decision"]["recommended_action"], "prepare_interfaces_only")


class ETLOperationalTrustPolicyTestCase(APITestCase):
    def _fresh_live_ingestion_run(self):
        return IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="hybrid",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="open-meteo-forecast",
            source_timestamp=timezone.now(),
            freshness_state=IngestionRun.FRESHNESS_FRESH,
            fallback_used=False,
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now(),
        )

    def test_build_operational_trust_snapshot_classifies_fresh_live_run_as_normal(self):
        recorded_at = timezone.now()
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_SCHEDULER,
            task_name="risk.tasks.record_etl_heartbeat_task",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=recorded_at,
        )
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_WORKER,
            task_name="risk.tasks.record_etl_heartbeat_task",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=recorded_at,
        )
        run = self._fresh_live_ingestion_run()

        snapshot = build_operational_trust_snapshot(run)

        self.assertEqual(snapshot["prediction_state"], TRUST_STATE_NORMAL)
        self.assertEqual(snapshot["alert_state"], ALERT_STATE_ALLOWED)

    def test_build_operational_trust_snapshot_marks_fallback_as_degraded(self):
        recorded_at = timezone.now()
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_SCHEDULER,
            task_name="risk.tasks.record_etl_heartbeat_task",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=recorded_at,
        )
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_WORKER,
            task_name="risk.tasks.record_etl_heartbeat_task",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=recorded_at,
        )
        run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_PARTIAL,
            source_mode="hybrid",
            source_kind=IngestionRun.SOURCE_KIND_SEEDED,
            source_name="static-csv",
            source_timestamp=None,
            freshness_state=IngestionRun.FRESHNESS_UNKNOWN,
            fallback_used=True,
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now(),
        )

        snapshot = build_operational_trust_snapshot(run)

        self.assertEqual(snapshot["prediction_state"], TRUST_STATE_DEGRADED)
        self.assertEqual(snapshot["alert_state"], ALERT_STATE_BLOCKED)
        self.assertIn("fallback-used", snapshot["reasons"])

    def test_build_operational_trust_snapshot_marks_delayed_live_source_for_review(self):
        recorded_at = timezone.now()
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_SCHEDULER,
            task_name="risk.tasks.record_etl_heartbeat_task",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=recorded_at,
        )
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_WORKER,
            task_name="risk.tasks.record_etl_heartbeat_task",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=recorded_at,
        )
        run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="hybrid",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="open-meteo-forecast",
            source_timestamp=timezone.now() - timedelta(hours=12),
            freshness_state=IngestionRun.FRESHNESS_DELAYED,
            fallback_used=False,
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now(),
        )

        snapshot = build_operational_trust_snapshot(run)

        self.assertEqual(snapshot["prediction_state"], TRUST_STATE_DEGRADED)
        self.assertEqual(snapshot["alert_state"], ALERT_STATE_REVIEW_ONLY)

    def test_build_operational_trust_snapshot_blocks_stale_live_source(self):
        recorded_at = timezone.now()
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_SCHEDULER,
            task_name="risk.tasks.record_etl_heartbeat_task",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=recorded_at,
        )
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_WORKER,
            task_name="risk.tasks.record_etl_heartbeat_task",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=recorded_at,
        )
        run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="live",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="open-meteo-forecast",
            source_timestamp=timezone.now() - timedelta(hours=30),
            freshness_state=IngestionRun.FRESHNESS_STALE,
            fallback_used=False,
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now(),
        )

        snapshot = build_operational_trust_snapshot(run)

        self.assertEqual(snapshot["prediction_state"], TRUST_STATE_BLOCKED)
        self.assertEqual(snapshot["alert_state"], ALERT_STATE_BLOCKED)
        self.assertIn("source-stale", snapshot["reasons"])

    def test_build_operational_trust_snapshot_marks_large_schedule_gap_as_degraded(self):
        recorded_at = timezone.now()
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_SCHEDULER,
            task_name="risk.tasks.record_etl_heartbeat_task",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=recorded_at,
        )
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_WORKER,
            task_name="risk.tasks.record_etl_heartbeat_task",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=recorded_at,
        )
        IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="hybrid",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="open-meteo-forecast",
            source_timestamp=timezone.now() - timedelta(hours=36),
            freshness_state=IngestionRun.FRESHNESS_FRESH,
            fallback_used=False,
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now() - timedelta(hours=36),
        )
        run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="hybrid",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="open-meteo-forecast",
            source_timestamp=timezone.now(),
            freshness_state=IngestionRun.FRESHNESS_FRESH,
            fallback_used=False,
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now(),
        )

        snapshot = build_operational_trust_snapshot(run)

        self.assertEqual(snapshot["prediction_state"], TRUST_STATE_DEGRADED)
        self.assertEqual(snapshot["alert_state"], ALERT_STATE_BLOCKED)
        self.assertEqual(snapshot["schedule_state"], "delayed")
        self.assertGreater(snapshot["schedule_gap_hours"], 30)
        self.assertIn("scheduled-ingestion-gap", snapshot["reasons"])

    @patch("risk.ml.trust.config")
    def test_build_operational_trust_snapshot_marks_static_mode_as_degraded(self, mock_config):
        def config_side_effect(key, *args, **kwargs):
            if key == "RAINFALL_SOURCE_MODE":
                return "static"
            if key == "RAINFALL_INGESTION_DELAY_WARNING_HOURS":
                return kwargs.get("default", 30)
            return kwargs.get("default")

        mock_config.side_effect = config_side_effect

        run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="static",
            source_kind=IngestionRun.SOURCE_KIND_SEEDED,
            source_name="static-csv",
            source_timestamp=None,
            freshness_state=IngestionRun.FRESHNESS_UNKNOWN,
            fallback_used=False,
            records_seen=1,
            records_loaded=1,
            completed_at=timezone.now(),
        )

        snapshot = build_operational_trust_snapshot(run)

        self.assertEqual(snapshot["prediction_state"], TRUST_STATE_DEGRADED)
        self.assertEqual(snapshot["alert_state"], ALERT_STATE_BLOCKED)
        self.assertIn("static-mode-forced", snapshot["reasons"])

    def test_build_operational_trust_snapshot_degrades_when_heartbeat_missing(self):
        run = self._fresh_live_ingestion_run()

        snapshot = build_operational_trust_snapshot(run)

        self.assertEqual(snapshot["prediction_state"], TRUST_STATE_DEGRADED)
        self.assertEqual(snapshot["alert_state"], ALERT_STATE_BLOCKED)
        self.assertIn("heartbeat-missing", snapshot["reasons"])

    def test_build_operational_trust_snapshot_blocks_when_heartbeat_stale(self):
        stale_time = timezone.now() - timedelta(minutes=90)
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_SCHEDULER,
            task_name="risk.tasks.record_etl_heartbeat_task",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=stale_time,
        )
        ETLHeartbeat.objects.create(
            component=ETLHeartbeat.COMPONENT_WORKER,
            task_name="risk.tasks.record_etl_heartbeat_task",
            status=ETLHeartbeat.STATUS_OK,
            recorded_at=stale_time,
        )
        run = self._fresh_live_ingestion_run()

        snapshot = build_operational_trust_snapshot(run)

        self.assertEqual(snapshot["prediction_state"], TRUST_STATE_BLOCKED)
        self.assertEqual(snapshot["alert_state"], ALERT_STATE_BLOCKED)
        self.assertIn("heartbeat-stale", snapshot["reasons"])


class ETLHeartbeatTaskTestCase(APITestCase):
    def test_record_etl_heartbeat_task_persists_scheduler_and_worker_records(self):
        from risk.tasks import record_etl_heartbeat_task

        count = record_etl_heartbeat_task.run()

        self.assertEqual(count, 2)
        self.assertEqual(ETLHeartbeat.objects.count(), 2)
        self.assertTrue(
            ETLHeartbeat.objects.filter(component=ETLHeartbeat.COMPONENT_SCHEDULER, status=ETLHeartbeat.STATUS_OK).exists()
        )
        self.assertTrue(
            ETLHeartbeat.objects.filter(component=ETLHeartbeat.COMPONENT_WORKER, status=ETLHeartbeat.STATUS_OK).exists()
        )


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
        self.assertEqual(run.source_kind, IngestionRun.SOURCE_KIND_LIVE)
        self.assertEqual(run.source_name, "open-meteo-forecast")
        self.assertEqual(run.freshness_state, IngestionRun.FRESHNESS_FRESH)
        self.assertFalse(run.fallback_used)
        self.assertEqual(run.records_seen, 1)
        self.assertEqual(run.records_loaded, 1)
        self.assertEqual(run.results[0]["canonical_record"]["entity_type"], "climate_record")
        self.assertEqual(run.results[0]["canonical_record"]["schema_version"], ETL_SCHEMA_VERSION)
        self.assertEqual(run.results[0]["canonical_record"]["source_kind"], IngestionRun.SOURCE_KIND_LIVE)

    @patch("risk.ml.ingestion.fetch_open_meteo_daily_precipitation", side_effect=Exception("network down"))
    def test_fetch_rainfall_falls_back_to_static(self, mock_fetch):
        result = fetch_rainfall_for_ward("North Kamagambo")
        self.assertGreater(result.rainfall_mm, 0)
        self.assertIn(result.source, ["static-csv", "static-default", "static-fallback"])
        run = IngestionRun.objects.get()
        self.assertEqual(run.status, IngestionRun.STATUS_PARTIAL)
        self.assertEqual(run.results[0]["fallback_reason"], "live-fetch-failed")
        self.assertIn(run.source_kind, [IngestionRun.SOURCE_KIND_SEEDED, IngestionRun.SOURCE_KIND_HYBRID])
        self.assertTrue(run.fallback_used)
        self.assertEqual(run.freshness_state, IngestionRun.FRESHNESS_UNKNOWN)
        self.assertEqual(run.results[0]["canonical_record"]["source_kind"], IngestionRun.SOURCE_KIND_SEEDED)
        self.assertEqual(run.results[0]["canonical_record"]["fallback_reason"], "live-fetch-failed")

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

    @patch("risk.ml.ingestion.fetch_open_meteo_daily_precipitation", side_effect=Exception("network down"))
    def test_fetch_rainfall_marks_seeded_source_kind_when_static_fallback_used(self, mock_fetch):
        fetch_rainfall_for_ward("North Kamagambo")
        run = IngestionRun.objects.get()
        self.assertEqual(run.source_kind, IngestionRun.SOURCE_KIND_SEEDED)

    def test_ingestion_run_serializer_exposes_operator_note(self):
        run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_PARTIAL,
            source_mode="hybrid",
            source_kind=IngestionRun.SOURCE_KIND_HYBRID,
            source_name="open-meteo-forecast",
            freshness_state=IngestionRun.FRESHNESS_DELAYED,
            fallback_used=True,
            records_seen=4,
            records_loaded=3,
            records_rejected=1,
            operator_note="Backfill accepted after provider retry.",
        )

        payload = IngestionRunSerializer(run).data

        self.assertEqual(payload["operator_note"], "Backfill accepted after provider retry.")
        self.assertGreaterEqual(run.records_seen, 1)
        self.assertGreaterEqual(run.records_loaded, 1)


class CanonicalETLNormalizationTestCase(AuthenticatedAPITestCase):
    def test_triage_session_maps_to_canonical_surveillance_and_chv_response_records(self):
        session = TriageSession.objects.create(
            channel="API",
            phone_number="+254711999001",
            ward=self.ward,
            diarrhea=True,
            vomiting=True,
            dehydration=False,
            fever=False,
            recommendation="Use ORS",
            referral_needed=True,
        )

        surveillance = surveillance_record_from_triage_session(session)
        chv_response = chv_response_record_from_triage_session(session)

        self.assertEqual(surveillance.entity_type, "surveillance_record")
        self.assertEqual(surveillance.schema_version, ETL_SCHEMA_VERSION)
        self.assertEqual(surveillance.ward_public_id, str(self.ward.public_id))
        self.assertEqual(surveillance.suspected_case_count, 1)
        self.assertTrue(surveillance.outbreak_signal)

        self.assertEqual(chv_response.entity_type, "chv_response_record")
        self.assertEqual(chv_response.schema_version, ETL_SCHEMA_VERSION)
        self.assertEqual(chv_response.ward_public_id, str(self.ward.public_id))
        self.assertIn("diarrhea", chv_response.symptom_signal)
        self.assertEqual(chv_response.alert_response_state, "referral_needed")

    def test_sync_queue_maps_to_canonical_surveillance_and_chv_response_records(self):
        triage_session = TriageSession.objects.create(
            channel="OFFLINE_SYNC",
            phone_number="+254711999002",
            ward=self.ward,
            diarrhea=True,
            vomiting=False,
            dehydration=True,
            fever=False,
            recommendation="Refer",
            referral_needed=True,
        )
        sync_item = SyncQueue.objects.create(
            source_device_id="device-001",
            client_submission_id="submission-001",
            phone_number="+254711999002",
            ward=self.ward,
            triage_session=triage_session,
            payload={
                "client_submission_id": "submission-001",
                "diarrhea": True,
                "vomiting": False,
                "dehydration": True,
                "fever": False,
                "text_input": "child weak and dehydrated",
            },
            status=SyncQueue.STATUS_PROCESSED,
            processed_at=timezone.now(),
        )

        surveillance = surveillance_record_from_sync_queue(sync_item)
        chv_response = chv_response_record_from_sync_queue(sync_item)

        self.assertEqual(surveillance.entity_type, "surveillance_record")
        self.assertEqual(surveillance.schema_version, ETL_SCHEMA_VERSION)
        self.assertEqual(surveillance.ward_public_id, str(self.ward.public_id))
        self.assertEqual(surveillance.source_name, "chv-sync-payload")
        self.assertEqual(surveillance.suspected_case_count, 1)
        self.assertTrue(surveillance.outbreak_signal)

        self.assertEqual(chv_response.entity_type, "chv_response_record")
        self.assertEqual(chv_response.schema_version, ETL_SCHEMA_VERSION)
        self.assertEqual(chv_response.chv_phone_number, "+254711999002")
        self.assertEqual(chv_response.alert_response_state, "processed")
        self.assertIn("dehydration", chv_response.symptom_signal)

    def test_facility_intelligence_snapshot_maps_to_canonical_readiness_record(self):
        snapshot = build_facility_intelligence_snapshot(self.health_facility)
        canonical = facility_readiness_record_from_intelligence_snapshot(
            facility=self.health_facility,
            snapshot=snapshot,
        )

        self.assertEqual(canonical.entity_type, "facility_readiness_record")
        self.assertEqual(canonical.schema_version, ETL_SCHEMA_VERSION)
        self.assertEqual(canonical.facility_public_id, str(self.health_facility.public_id))
        self.assertEqual(canonical.ward_public_id, str(self.ward.public_id))
        self.assertIsNotNone(canonical.readiness_state)
        self.assertIsNotNone(canonical.readiness_score)
        self.assertEqual(canonical.source_name, "facility-intelligence-snapshot")


class ZZZNotificationWebsocketLifecycleIsolationTest(AuthenticatedAPITestCase):
    @override_settings(
        CHANNEL_LAYERS={
            "default": {
                "BACKEND": "channels.layers.InMemoryChannelLayer",
            }
        }
    )
    def test_notification_websocket_receives_lifecycle_updates(self):
        self.authenticate(self.analyst_user.username)
        async_to_sync(self._exercise_notification_websocket_lifecycle)()

    @override_settings(
        CHANNEL_LAYERS={
            "default": {
                "BACKEND": "channels.layers.InMemoryChannelLayer",
            }
        }
    )
    def test_policy_missing_user_cannot_open_notification_websocket(self):
        self.analyst_user.policy_acceptances.all().delete()
        async_to_sync(self._exercise_policy_missing_notification_websocket_rejected)()

    async def _exercise_policy_missing_notification_websocket_rejected(self):
        token = AccessToken.for_user(self.analyst_user)
        token["purpose"] = "dashboard_notifications_stream"
        token["role"] = self.analyst_user.role
        token["ward_id"] = self.analyst_user.ward_id

        communicator = WebsocketCommunicator(
            application,
            f"/ws/notifications/stream/?token={token}",
        )
        connected, close_code = await communicator.connect()

        self.assertFalse(connected)
        self.assertEqual(close_code, 4401)

    async def _exercise_notification_websocket_lifecycle(self):
        list_response = await sync_to_async(self.client.get)(reverse("notification-list"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        notification = next(
            item for item in list_response.data["results"] if item["type"] == DashboardNotification.TYPE_WARD_RISK_HIGH
        )

        token = AccessToken.for_user(self.analyst_user)
        token["purpose"] = "dashboard_notifications_stream"
        token["role"] = self.analyst_user.role
        token["ward_id"] = self.analyst_user.ward_id

        communicator = WebsocketCommunicator(
            application,
            f"/ws/notifications/stream/?token={token}",
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        initial = await communicator.receive_json_from()
        self.assertEqual(initial["event"], "notification.connected")
        self.assertTrue(any(feed["id"] == "risks" for feed in initial["feeds"]))
        self.assertEqual(initial["freshness"]["last_model_run_at"], self.model_run.completed_at.isoformat())
        self.assertEqual(initial["freshness"]["freshness_state"], "fresh")

        seen_response = await sync_to_async(self.client.post)(
            reverse("notification-seen", kwargs={"public_id": notification["public_id"]}),
            format="json",
        )
        self.assertEqual(seen_response.status_code, status.HTTP_200_OK)

        event = await communicator.receive_json_from()
        self.assertEqual(event["event"], "notification.updated")
        self.assertEqual(event["notification"]["public_id"], notification["public_id"])
        self.assertEqual(event["notification"]["state"], DashboardNotification.STATE_SEEN)
        self.assertTrue(any(feed["id"] == "risks" for feed in event["feeds"]))
        self.assertIn("freshness", event)

        await communicator.disconnect()


class CHVCoverageWorkflowModelTestCase(AuthenticatedAPITestCase):
    def test_chv_coverage_workflow_models_are_registered_in_admin(self):
        registry = admin.site._registry

        self.assertIn(CHVCoverageRequest, registry)
        self.assertIn(CHVCoverageRequestAlertLink, registry)
        self.assertIn(CHVAssignment, registry)
        self.assertIn(CHVCoverageRequestEvent, registry)

    def test_admin_creation_requires_requesting_user(self):
        model_admin = admin.site._registry[CHVCoverageRequest]
        request = RequestFactory().post("/admin/risk/chvcoveragerequest/add/")
        request.user = self.admin_user
        request_record = CHVCoverageRequest(
            ward=self.ward,
            requested_by=None,
            priority=CHVCoverageRequest.PRIORITY_MEDIUM,
            reason="Coverage gap detected.",
            requested_chv_count=1,
        )

        with self.assertRaises(ValidationError):
            model_admin.save_model(request, request_record, form=SimpleNamespace(changed_data=[]), change=False)

    def test_admin_creation_blocks_alert_driven_request_without_linkage_workflow(self):
        model_admin = admin.site._registry[CHVCoverageRequest]
        request = RequestFactory().post("/admin/risk/chvcoveragerequest/add/")
        request.user = self.admin_user
        request_record = CHVCoverageRequest(
            ward=self.ward,
            requested_by=self.admin_user,
            priority=CHVCoverageRequest.PRIORITY_MEDIUM,
            reason="Coverage gap detected from alert context.",
            requested_chv_count=1,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
        )

        with self.assertRaises(ValidationError):
            model_admin.save_model(request, request_record, form=SimpleNamespace(changed_data=[]), change=False)

    def test_admin_cannot_rewrite_trigger_source_after_creation(self):
        model_admin = admin.site._registry[CHVCoverageRequest]
        request = RequestFactory().post("/admin/risk/chvcoveragerequest/change/")
        request.user = self.admin_user
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_MEDIUM,
            reason="Manual request should stay manual.",
            requested_chv_count=1,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_MANUAL,
        )
        request_record.trigger_source = CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN

        with self.assertRaises(ValidationError):
            model_admin.save_model(
                request,
                request_record,
                form=SimpleNamespace(changed_data=["trigger_source"]),
                change=True,
            )

    def test_admin_alert_linkage_inline_is_review_only(self):
        model_admin = admin.site._registry[CHVCoverageRequest]
        inline = CHVCoverageRequestAlertLinkInline(CHVCoverageRequest, admin.site)
        request = RequestFactory().get("/admin/risk/chvcoveragerequest/change/")
        request.user = self.admin_user

        self.assertFalse(inline.has_add_permission(request))
        self.assertFalse(inline.has_delete_permission(request))
        self.assertIn("alert", inline.readonly_fields)
        self.assertIn("linked_by", inline.readonly_fields)

    def test_only_one_live_coverage_request_per_ward_is_allowed(self):
        CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Coverage gap detected.",
            requested_chv_count=1,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CHVCoverageRequest.objects.create(
                    ward=self.ward,
                    requested_by=self.admin_user,
                    status=CHVCoverageRequest.STATUS_APPROVED,
                    priority=CHVCoverageRequest.PRIORITY_HIGH,
                    reason="Second live request should fail.",
                    requested_chv_count=1,
                )

    def test_non_live_coverage_request_can_exist_after_resolved_request(self):
        CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_RESOLVED,
            priority=CHVCoverageRequest.PRIORITY_MEDIUM,
            reason="Resolved prior request.",
            requested_chv_count=1,
        )

        second = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="New live request after resolution.",
            requested_chv_count=1,
        )

        self.assertEqual(second.status, CHVCoverageRequest.STATUS_OPEN)

    def test_only_one_active_assignment_per_request_is_allowed(self):
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_APPROVED,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Request ready for assignment.",
            requested_chv_count=1,
        )

        CHVAssignment.objects.create(
            coverage_request=request_record,
            ward=self.ward,
            chv=self.chv,
            assigned_by=self.admin_user,
            status=CHVAssignment.STATUS_ACTIVE,
        )

        second_chv = CHV.objects.create(
            name="John CHV",
            phone_number="+254700000099",
            ward=self.ward,
            is_active=True,
            language="en",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CHVAssignment.objects.create(
                    coverage_request=request_record,
                    ward=self.ward,
                    chv=second_chv,
                    assigned_by=self.admin_user,
                    status=CHVAssignment.STATUS_ACTIVE,
                )

    def test_only_one_link_per_alert_and_request_is_allowed(self):
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Alert-linked request.",
            requested_chv_count=1,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
        )
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=None,
            channel=Alert.CHANNEL_SMS,
            recipient="CHVs",
            message="Coverage follow-up recommended.",
            status=Alert.STATUS_DELIVERED,
        )

        CHVCoverageRequestAlertLink.objects.create(
            coverage_request=request_record,
            alert=alert,
            linked_by=self.admin_user,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CHVCoverageRequestAlertLink.objects.create(
                    coverage_request=request_record,
                    alert=alert,
                    linked_by=self.admin_user,
                )


class CHVCoverageWorkflowApiTestCase(AuthenticatedAPITestCase):
    def test_admin_can_create_and_view_coverage_request_detail(self):
        self.authenticate(self.admin_user.username)

        create_response = self.client.post(
            reverse("chv-coverage-request-list-create"),
            {
                "ward_id": self.ward.id,
                "priority": CHVCoverageRequest.PRIORITY_HIGH,
                "reason": "Coverage gap detected: 0 active CHVs recorded in this ward.",
                "requested_chv_count": 1,
                "notes": "Field review requested.",
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["status"], CHVCoverageRequest.STATUS_OPEN)
        self.assertEqual(create_response.data["trigger_source"], CHVCoverageRequest.TRIGGER_SOURCE_MANUAL)
        self.assertEqual(create_response.data["requested_by_username"], self.admin_user.username)
        self.assertEqual(len(create_response.data["events"]), 1)
        self.assertEqual(create_response.data["events"][0]["action"], CHVCoverageRequestEvent.ACTION_CREATED)

        detail_response = self.client.get(
            reverse("chv-coverage-request-detail", kwargs={"public_id": create_response.data["public_id"]})
        )

        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        self.assertEqual(detail_response.data["ward_name"], self.ward.name)
        self.assertEqual(detail_response.data["priority"], CHVCoverageRequest.PRIORITY_HIGH)

    def test_admin_can_create_alert_driven_request_with_linked_alerts(self):
        self.authenticate(self.admin_user.username)
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient="CHVs",
            message="Coverage follow-up recommended from alert context.",
            status=Alert.STATUS_DELIVERED,
        )

        create_response = self.client.post(
            reverse("chv-coverage-request-list-create"),
            {
                "ward_id": self.ward.id,
                "priority": CHVCoverageRequest.PRIORITY_HIGH,
                "reason": "Coverage follow-up requested from linked alert context.",
                "requested_chv_count": 1,
                "trigger_source": CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
                "linked_alert_public_ids": [str(alert.public_id)],
            },
            format="json",
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(create_response.data["trigger_source"], CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN)
        self.assertEqual(create_response.data["linked_alert_public_ids"], [str(alert.public_id)])
        self.assertEqual(len(create_response.data["linked_alerts_summary"]), 1)
        self.assertEqual(create_response.data["linked_alerts_summary"][0]["alert_public_id"], str(alert.public_id))
        self.assertEqual(create_response.data["linked_alerts_summary"][0]["alert_id"], alert.id)
        event_actions = [event["action"] for event in create_response.data["events"]]
        self.assertIn(CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_ATTACHED, event_actions)
        self.assertIn(CHVCoverageRequestEvent.ACTION_CREATED, event_actions)
        attachment_event = next(
            event for event in create_response.data["events"]
            if event["action"] == CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_ATTACHED
        )
        self.assertEqual(attachment_event["metadata"]["linked_alert_public_ids"], [str(alert.public_id)])

    def test_admin_can_prefill_alert_driven_request_from_alert_context(self):
        self.authenticate(self.admin_user.username)
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="Operations",
            message="Alert-linked CHV coverage review recommended.",
            status=Alert.STATUS_DELIVERED,
        )

        response = self.client.post(
            reverse("chv-coverage-request-from-alert-prefill"),
            {"alert_public_ids": [str(alert.public_id)]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mode"], "CREATE_READY")
        self.assertIsNone(response.data["existing_request"])
        self.assertEqual(response.data["create_defaults"]["ward_id"], self.ward.id)
        self.assertEqual(response.data["create_defaults"]["ward_public_id"], str(self.ward.public_id))
        self.assertEqual(response.data["create_defaults"]["trigger_source"], CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN)
        self.assertEqual(response.data["create_defaults"]["priority"], CHVCoverageRequest.PRIORITY_HIGH)
        self.assertEqual(response.data["create_defaults"]["linked_alert_public_ids"], [str(alert.public_id)])
        self.assertEqual(response.data["create_defaults"]["linked_alerts_summary"][0]["alert_public_id"], str(alert.public_id))

    def test_prefill_returns_existing_live_request_for_same_ward(self):
        self.authenticate(self.admin_user.username)
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient="CHVs",
            message="Existing request should be returned.",
            status=Alert.STATUS_DELIVERED,
        )
        existing_request = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Existing live request.",
            requested_chv_count=1,
        )

        response = self.client.post(
            reverse("chv-coverage-request-from-alert-prefill"),
            {"alert_public_ids": [str(alert.public_id)]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mode"], "EXISTING_LIVE_REQUEST")
        self.assertIsNone(response.data["create_defaults"])
        self.assertEqual(response.data["existing_request"]["public_id"], str(existing_request.public_id))
        existing_request.refresh_from_db()
        attachment_event = existing_request.events.filter(
            action=CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_ATTACHED
        ).latest("created_at")
        redirect_event = existing_request.events.filter(
            action=CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_REDIRECTED
        ).latest("created_at")
        self.assertEqual(
            attachment_event.metadata["linked_alert_public_ids"],
            [str(alert.public_id)],
        )
        self.assertEqual(attachment_event.metadata["attachment_mode"], "EXISTING_REQUEST")
        self.assertEqual(
            redirect_event.detail,
            "Alert-linked request attempt resolved to the existing live coverage request.",
        )
        self.assertEqual(
            redirect_event.metadata["linked_alert_public_ids"],
            [str(alert.public_id)],
        )
        self.assertEqual(redirect_event.metadata["resolution"], "EXISTING_LIVE_REQUEST")

    def test_prefill_redirect_persists_new_alert_linkage_on_existing_request(self):
        self.authenticate(self.admin_user.username)
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient="CHVs",
            message="Redirect should still persist linked alert context.",
            status=Alert.STATUS_DELIVERED,
        )
        existing_request = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Existing manual live request.",
            requested_chv_count=1,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_MANUAL,
        )

        response = self.client.post(
            reverse("chv-coverage-request-from-alert-prefill"),
            {"alert_public_ids": [str(alert.public_id)]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["mode"], "EXISTING_LIVE_REQUEST")
        self.assertEqual(response.data["existing_request"]["trigger_source"], CHVCoverageRequest.TRIGGER_SOURCE_MANUAL)
        self.assertEqual(response.data["existing_request"]["linked_alert_public_ids"], [str(alert.public_id)])
        self.assertEqual(
            response.data["existing_request"]["linked_alerts_summary"][0]["alert_public_id"],
            str(alert.public_id),
        )
        existing_request.refresh_from_db()
        self.assertTrue(existing_request.linked_alert_links.filter(alert=alert).exists())
        redirect_event = existing_request.events.filter(
            action=CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_REDIRECTED
        ).latest("created_at")
        attachment_event = existing_request.events.filter(
            action=CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_ATTACHED
        ).latest("created_at")
        self.assertEqual(
            redirect_event.metadata["attached_alert_public_ids"],
            [str(alert.public_id)],
        )
        self.assertEqual(
            attachment_event.metadata["linked_alert_public_ids"],
            [str(alert.public_id)],
        )

    def test_prefill_rejects_mixed_ward_alerts(self):
        self.authenticate(self.admin_user.username)
        first_alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient="CHVs",
            message="Ward one alert.",
            status=Alert.STATUS_DELIVERED,
        )
        second_alert = Alert.objects.create(
            ward=self.other_ward,
            risk_score=self.other_risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient="CHVs",
            message="Ward two alert.",
            status=Alert.STATUS_DELIVERED,
        )

        response = self.client.post(
            reverse("chv-coverage-request-from-alert-prefill"),
            {"alert_public_ids": [str(first_alert.public_id), str(second_alert.public_id)]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Linked alerts must all belong to the same ward.")

    def test_analyst_cannot_prefill_alert_driven_request(self):
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="Operations",
            message="Analyst cannot create CHV request.",
            status=Alert.STATUS_DELIVERED,
        )
        self.authenticate(self.analyst_user.username)

        response = self.client.post(
            reverse("chv-coverage-request-from-alert-prefill"),
            {"alert_public_ids": [str(alert.public_id)]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_supervisor_prefill_rejects_alert_outside_permitted_scope(self):
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_DASHBOARD,
            recipient="Operations",
            message="Out-of-scope alert.",
            status=Alert.STATUS_DELIVERED,
        )
        self.authenticate(self.supervisor_user.username)

        response = self.client.post(
            reverse("chv-coverage-request-from-alert-prefill"),
            {"alert_public_ids": [str(alert.public_id)]},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "One or more linked alerts could not be found in your permitted scope.")

    def test_alert_driven_request_requires_linked_alerts(self):
        self.authenticate(self.admin_user.username)

        response = self.client.post(
            reverse("chv-coverage-request-list-create"),
            {
                "ward_id": self.ward.id,
                "priority": CHVCoverageRequest.PRIORITY_HIGH,
                "reason": "Coverage follow-up requested from linked alert context.",
                "requested_chv_count": 1,
                "trigger_source": CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
                "linked_alert_public_ids": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("linked_alert_public_ids", response.data)

    def test_alert_driven_request_rejects_out_of_scope_or_unknown_alerts(self):
        other_ward = Ward.objects.create(
            name="Scoped Other Ward",
            county="Migori",
            sub_county="Suna",
            ward_code="OT-002",
            public_id=uuid.uuid4(),
            is_active=True,
        )
        other_alert = Alert.objects.create(
            ward=other_ward,
            risk_score=None,
            channel=Alert.CHANNEL_SMS,
            recipient="CHVs",
            message="Out-of-scope alert.",
            status=Alert.STATUS_DELIVERED,
        )
        self.authenticate(self.supervisor_user.username)

        response = self.client.post(
            reverse("chv-coverage-request-list-create"),
            {
                "ward_id": self.other_ward.id,
                "priority": CHVCoverageRequest.PRIORITY_HIGH,
                "reason": "Coverage follow-up requested from linked alert context.",
                "requested_chv_count": 1,
                "trigger_source": CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
                "linked_alert_public_ids": [str(other_alert.public_id)],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "One or more linked alerts could not be found in your permitted scope.")

    def test_alert_driven_request_rejects_alerts_from_different_ward(self):
        other_ward = Ward.objects.create(
            name="Alert Other Ward",
            county="Migori",
            sub_county="Suna",
            ward_code="OT-003",
            public_id=uuid.uuid4(),
            is_active=True,
        )
        other_alert = Alert.objects.create(
            ward=other_ward,
            risk_score=None,
            channel=Alert.CHANNEL_SMS,
            recipient="CHVs",
            message="Different ward alert.",
            status=Alert.STATUS_DELIVERED,
        )
        self.authenticate(self.admin_user.username)

        response = self.client.post(
            reverse("chv-coverage-request-list-create"),
            {
                "ward_id": self.ward.id,
                "priority": CHVCoverageRequest.PRIORITY_HIGH,
                "reason": "Coverage follow-up requested from linked alert context.",
                "requested_chv_count": 1,
                "trigger_source": CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
                "linked_alert_public_ids": [str(other_alert.public_id)],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Linked alerts must belong to the same ward as the coverage request.")

    @patch("risk.views.create_chv_coverage_request", side_effect=IntegrityError("duplicate live request"))
    def test_duplicate_live_request_race_returns_truthful_400(self, mock_create_request):
        self.authenticate(self.admin_user.username)

        response = self.client.post(
            reverse("chv-coverage-request-list-create"),
            {
                "ward_id": self.ward.id,
                "priority": CHVCoverageRequest.PRIORITY_HIGH,
                "reason": "Concurrent duplicate request should not surface as a server error.",
                "requested_chv_count": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "A live CHV coverage request already exists for this ward.")
        mock_create_request.assert_called_once()

    def test_direct_alert_driven_duplicate_attaches_alerts_to_existing_request(self):
        self.authenticate(self.admin_user.username)
        existing_request = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Existing live request.",
            requested_chv_count=1,
        )
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient="CHVs",
            message="Duplicate direct create should still attach this alert.",
            status=Alert.STATUS_DELIVERED,
        )

        response = self.client.post(
            reverse("chv-coverage-request-list-create"),
            {
                "ward_id": self.ward.id,
                "priority": CHVCoverageRequest.PRIORITY_HIGH,
                "reason": "Coverage follow-up requested from linked alert context.",
                "requested_chv_count": 1,
                "trigger_source": CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
                "linked_alert_public_ids": [str(alert.public_id)],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "A live CHV coverage request already exists for this ward.")
        self.assertEqual(response.data["existing_request_public_id"], str(existing_request.public_id))
        existing_request.refresh_from_db()
        self.assertTrue(existing_request.linked_alert_links.filter(alert=alert).exists())
        attachment_event = existing_request.events.filter(
            action=CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_ATTACHED
        ).latest("created_at")
        redirect_event = existing_request.events.filter(
            action=CHVCoverageRequestEvent.ACTION_ALERT_LINKAGE_REDIRECTED
        ).latest("created_at")
        self.assertEqual(attachment_event.metadata["linked_alert_public_ids"], [str(alert.public_id)])
        self.assertEqual(attachment_event.metadata["attachment_mode"], "EXISTING_REQUEST")
        self.assertEqual(redirect_event.metadata["linked_alert_public_ids"], [str(alert.public_id)])
        self.assertEqual(redirect_event.metadata["source_api"], "DIRECT_CREATE")

    def test_request_list_can_filter_by_linked_alert_presence(self):
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient="CHVs",
            message="Linked alert for filter coverage.",
            status=Alert.STATUS_DELIVERED,
        )
        manual_request = CHVCoverageRequest.objects.create(
            ward=self.other_ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_RESOLVED,
            priority=CHVCoverageRequest.PRIORITY_MEDIUM,
            reason="Manual request without linked alerts.",
            requested_chv_count=1,
        )
        alert_request = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_RESOLVED,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Alert-driven request with linkage.",
            requested_chv_count=1,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
        )
        CHVCoverageRequestAlertLink.objects.create(
            coverage_request=alert_request,
            alert=alert,
            linked_by=self.admin_user,
        )
        self.authenticate(self.admin_user.username)

        linked_response = self.client.get(
            reverse("chv-coverage-request-list-create"),
            {"has_linked_alerts": "true"},
        )
        unlinked_response = self.client.get(
            reverse("chv-coverage-request-list-create"),
            {"has_linked_alerts": "false"},
        )

        self.assertEqual(linked_response.status_code, status.HTTP_200_OK)
        self.assertEqual(unlinked_response.status_code, status.HTTP_200_OK)
        self.assertEqual([item["public_id"] for item in linked_response.data["results"]], [str(alert_request.public_id)])
        self.assertIn(str(manual_request.public_id), [item["public_id"] for item in unlinked_response.data["results"]])
        self.assertNotIn(str(alert_request.public_id), [item["public_id"] for item in unlinked_response.data["results"]])

    def test_analyst_can_list_requests_but_cannot_create(self):
        CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Existing request",
            requested_chv_count=1,
        )
        self.authenticate(self.analyst_user.username)

        list_response = self.client.get(reverse("chv-coverage-request-list-create"))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(list_response.data["count"], 1)

        create_response = self.client.post(
            reverse("chv-coverage-request-list-create"),
            {
                "ward_id": self.ward.id,
                "priority": CHVCoverageRequest.PRIORITY_HIGH,
                "reason": "Analyst should not create this.",
                "requested_chv_count": 1,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_supervisor_cannot_create_request_for_out_of_scope_ward(self):
        self.authenticate(self.supervisor_user.username)

        response = self.client.post(
            reverse("chv-coverage-request-list-create"),
            {
                "ward_id": self.ward.id,
                "priority": CHVCoverageRequest.PRIORITY_HIGH,
                "reason": "Out of scope request",
                "requested_chv_count": 1,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data["detail"], "Ward not found.")

    def test_reject_requires_reason(self):
        self.authenticate(self.admin_user.username)
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Needs decision",
            requested_chv_count=1,
        )

        response = self.client.post(
            reverse("chv-coverage-request-reject", kwargs={"public_id": request_record.public_id}),
            {"reason": ""},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "A rejection reason is required.")

    def test_cannot_assign_until_request_is_approved(self):
        self.authenticate(self.admin_user.username)
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Pending approval",
            requested_chv_count=1,
        )

        response = self.client.post(
            reverse("chv-coverage-request-assign", kwargs={"public_id": request_record.public_id}),
            {"chv_id": self.chv.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["detail"], "Only approved coverage requests can receive CHV assignments.")

    def test_cannot_assign_chv_from_different_ward(self):
        other_ward = Ward.objects.create(
            name="Other Ward",
            county="Migori",
            sub_county="Suna",
            ward_code="OT-001",
            public_id=uuid.uuid4(),
            is_active=True,
        )
        other_chv = CHV.objects.create(
            name="Atieno",
            phone_number="+254700999001",
            language="en",
            ward=other_ward,
            is_active=True,
        )
        self.authenticate(self.admin_user.username)
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_APPROVED,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Ready for assignment",
            requested_chv_count=1,
        )

        response = self.client.post(
            reverse("chv-coverage-request-assign", kwargs={"public_id": request_record.public_id}),
            {"chv_id": other_chv.id},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"],
            "Only CHVs linked to the requested ward can be assigned from this workflow.",
        )

    def test_admin_can_approve_assign_complete_and_resolve_request(self):
        self.authenticate(self.admin_user.username)
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.admin_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Workflow path",
            requested_chv_count=1,
        )

        approve_response = self.client.post(
            reverse("chv-coverage-request-approve", kwargs={"public_id": request_record.public_id}),
            {"reason": "Approved for field deployment."},
            format="json",
        )
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_response.data["status"], CHVCoverageRequest.STATUS_APPROVED)

        assign_response = self.client.post(
            reverse("chv-coverage-request-assign", kwargs={"public_id": request_record.public_id}),
            {"chv_id": self.chv.id, "notes": "Deploy immediately."},
            format="json",
        )
        self.assertEqual(assign_response.status_code, status.HTTP_200_OK)
        self.assertEqual(assign_response.data["status"], CHVCoverageRequest.STATUS_IN_PROGRESS)
        self.assertEqual(len(assign_response.data["assignments"]), 1)
        assignment_public_id = assign_response.data["assignments"][0]["public_id"]

        complete_response = self.client.post(
            reverse("chv-assignment-complete", kwargs={"public_id": assignment_public_id}),
            {"notes": "Assignment completed on the ground."},
            format="json",
        )
        self.assertEqual(complete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(complete_response.data["status"], CHVCoverageRequest.STATUS_APPROVED)

        resolve_response = self.client.post(
            reverse("chv-coverage-request-resolve", kwargs={"public_id": request_record.public_id}),
            {"reason": "Coverage restored."},
            format="json",
        )
        self.assertEqual(resolve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(resolve_response.data["status"], CHVCoverageRequest.STATUS_RESOLVED)
        self.assertGreaterEqual(len(resolve_response.data["events"]), 4)
        self.assertEqual(resolve_response.data["sla_status"], "NOT_APPLICABLE")


class CHVCoverageWorkflowNotificationTestCase(AuthenticatedAPITestCase):
    @patch("risk.notifications.send_email")
    def test_approval_creates_dashboard_notification_and_records_email_attempt(self, mock_send_email):
        mock_send_email.return_value = EmailDeliveryResult(success=True, external_id="email-123", error="", provider="stub", status_code=200)
        self.authenticate(self.admin_user.username)
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.supervisor_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Needs approval",
            requested_chv_count=1,
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("chv-coverage-request-approve", kwargs={"public_id": request_record.public_id}),
                {"reason": "Approved for deployment."},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = DashboardNotification.objects.get(
            type=DashboardNotification.TYPE_CHV_COVERAGE_REQUEST_STATUS,
            source_object_id=str(request_record.public_id),
        )
        self.assertEqual(notification.recipient_user, self.supervisor_user)
        self.assertEqual(notification.metadata["coverage_request_status"], CHVCoverageRequest.STATUS_APPROVED)

        delivery = CHVCoverageRequestEmailDelivery.objects.get(coverage_request=request_record)
        self.assertEqual(delivery.status, CHVCoverageRequestEmailDelivery.STATUS_SENT)
        self.assertEqual(delivery.delivery_backend, "stub")
        self.assertEqual(delivery.external_id, "email-123")
        mock_send_email.assert_called_once()
        _, kwargs = mock_send_email.call_args
        self.assertIn(f"{settings.FRONTEND_APP_URL}/chvs/requests/{request_record.public_id}", kwargs["text_body"])
        self.assertIn(f'href="{settings.FRONTEND_APP_URL}/chvs/requests/{request_record.public_id}"', kwargs["html_body"])
        self.assertNotIn("opened from alert context", notification.body.lower())

    @patch("risk.notifications.send_email")
    def test_assignment_completion_creates_notification_and_email_attempt(self, mock_send_email):
        mock_send_email.return_value = EmailDeliveryResult(success=True, external_id="email-456", error="", provider="stub", status_code=200)
        self.authenticate(self.admin_user.username)
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.supervisor_user,
            status=CHVCoverageRequest.STATUS_APPROVED,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Ready for assignment",
            requested_chv_count=1,
        )
        assignment = CHVAssignment.objects.create(
            coverage_request=request_record,
            ward=self.ward,
            chv=self.chv,
            assigned_by=self.admin_user,
            status=CHVAssignment.STATUS_ACTIVE,
        )
        request_record.status = CHVCoverageRequest.STATUS_IN_PROGRESS
        request_record.save(update_fields=["status", "updated_at"])

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("chv-assignment-complete", kwargs={"public_id": assignment.public_id}),
                {"notes": "Finished field response."},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = DashboardNotification.objects.get(
            type=DashboardNotification.TYPE_CHV_COVERAGE_REQUEST_STATUS,
            metadata__coverage_event_action=CHVCoverageRequestEvent.ACTION_ASSIGNMENT_COMPLETED,
        )
        self.assertEqual(notification.recipient_user, self.supervisor_user)
        request_record.refresh_from_db()
        self.assertEqual(request_record.status, CHVCoverageRequest.STATUS_APPROVED)

        delivery = CHVCoverageRequestEmailDelivery.objects.get(event__action=CHVCoverageRequestEvent.ACTION_ASSIGNMENT_COMPLETED)
        self.assertEqual(delivery.status, CHVCoverageRequestEmailDelivery.STATUS_SENT)
        mock_send_email.assert_called_once()

    @patch("risk.notifications.send_email")
    def test_alert_driven_approval_mentions_alert_origin_truthfully(self, mock_send_email):
        mock_send_email.return_value = EmailDeliveryResult(success=True, external_id="email-321", error="", provider="stub", status_code=200)
        self.authenticate(self.admin_user.username)
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.supervisor_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Needs approval from alert context",
            requested_chv_count=1,
            trigger_source=CHVCoverageRequest.TRIGGER_SOURCE_ALERT_DRIVEN,
        )
        alert = Alert.objects.create(
            ward=self.ward,
            risk_score=self.risk_score,
            channel=Alert.CHANNEL_SMS,
            recipient="CHVs",
            message="Coverage follow-up recommended from alert context.",
            status=Alert.STATUS_DELIVERED,
        )
        CHVCoverageRequestAlertLink.objects.create(
            coverage_request=request_record,
            alert=alert,
            linked_by=self.admin_user,
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("chv-coverage-request-approve", kwargs={"public_id": request_record.public_id}),
                {"reason": "Approved for deployment."},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = DashboardNotification.objects.get(
            type=DashboardNotification.TYPE_CHV_COVERAGE_REQUEST_STATUS,
            source_object_id=str(request_record.public_id),
        )
        self.assertIn("opened from alert context", notification.body.lower())
        self.assertIn(str(alert.public_id), notification.body)

        delivery = CHVCoverageRequestEmailDelivery.objects.get(coverage_request=request_record)
        self.assertEqual(delivery.status, CHVCoverageRequestEmailDelivery.STATUS_SENT)
        mock_send_email.assert_called_once()
        _, kwargs = mock_send_email.call_args
        self.assertIn("opened from alert context", kwargs["text_body"].lower())
        self.assertIn(str(alert.public_id), kwargs["text_body"])

    @patch("risk.notifications.send_email")
    def test_assignment_cancellation_creates_notification_and_email_attempt(self, mock_send_email):
        mock_send_email.return_value = EmailDeliveryResult(success=True, external_id="email-654", error="", provider="stub", status_code=200)
        self.authenticate(self.admin_user.username)
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.supervisor_user,
            status=CHVCoverageRequest.STATUS_IN_PROGRESS,
            priority=CHVCoverageRequest.PRIORITY_HIGH,
            reason="Assignment active",
            requested_chv_count=1,
        )
        assignment = CHVAssignment.objects.create(
            coverage_request=request_record,
            ward=self.ward,
            chv=self.chv,
            assigned_by=self.admin_user,
            status=CHVAssignment.STATUS_ACTIVE,
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse("chv-assignment-cancel", kwargs={"public_id": assignment.public_id}),
                {"notes": "Assignment cancelled after review."},
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], CHVCoverageRequest.STATUS_APPROVED)
        notification = DashboardNotification.objects.get(
            type=DashboardNotification.TYPE_CHV_COVERAGE_REQUEST_STATUS,
            metadata__coverage_event_action=CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CANCELLED,
        )
        self.assertEqual(notification.recipient_user, self.supervisor_user)

        delivery = CHVCoverageRequestEmailDelivery.objects.get(event__action=CHVCoverageRequestEvent.ACTION_ASSIGNMENT_CANCELLED)
        self.assertEqual(delivery.status, CHVCoverageRequestEmailDelivery.STATUS_SENT)
        mock_send_email.assert_called_once()

    @patch("risk.notifications.send_email")
    def test_admin_status_change_uses_same_notification_and_email_flow(self, mock_send_email):
        mock_send_email.return_value = EmailDeliveryResult(success=True, external_id="email-789", error="", provider="stub", status_code=200)
        request_record = CHVCoverageRequest.objects.create(
            ward=self.ward,
            requested_by=self.supervisor_user,
            status=CHVCoverageRequest.STATUS_OPEN,
            priority=CHVCoverageRequest.PRIORITY_MEDIUM,
            reason="Admin flow",
            requested_chv_count=1,
        )
        admin_site = AdminSite()
        model_admin = CHVCoverageRequestAdmin(CHVCoverageRequest, admin_site)
        request = RequestFactory().post("/admin/risk/chvcoveragerequest/")
        request.user = self.admin_user

        request_record.status = CHVCoverageRequest.STATUS_APPROVED
        request_record.review_decision_reason = "Approved from admin."
        form = SimpleNamespace(changed_data=["status", "review_decision_reason"])

        with self.captureOnCommitCallbacks(execute=True):
            model_admin.save_model(request, request_record, form, change=True)

        request_record.refresh_from_db()
        self.assertEqual(request_record.status, CHVCoverageRequest.STATUS_APPROVED)
        self.assertEqual(
            DashboardNotification.objects.filter(
                type=DashboardNotification.TYPE_CHV_COVERAGE_REQUEST_STATUS,
                source_object_id=str(request_record.public_id),
            ).count(),
            1,
        )
        self.assertEqual(
            CHVCoverageRequestEmailDelivery.objects.filter(coverage_request=request_record).count(),
            1,
        )
        mock_send_email.assert_called_once()
