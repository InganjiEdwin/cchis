from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from risk.models import Ward

from .role_capabilities import (
    ACTION_CAPABILITY_KEYS,
    PAGE_CAPABILITY_KEYS,
    ROLE_ACTION_CAPABILITIES,
    ROLE_PAGE_CAPABILITIES,
    build_dashboard_capabilities,
    default_two_factor_policy_for_role,
)


User = get_user_model()


def capability_map(enabled_keys: tuple[str, ...], all_keys: tuple[str, ...]) -> dict[str, bool]:
    enabled = set(enabled_keys)
    return {key: key in enabled for key in all_keys}


EXPECTED_PAGES = {
    User.ROLE_ADMIN: capability_map(PAGE_CAPABILITY_KEYS, PAGE_CAPABILITY_KEYS),
    User.ROLE_SUPERVISOR: capability_map(
        (
            "dashboard",
            "overview",
            "wards",
            "alerts",
            "preparedness_actions",
            "chv_operations",
            "facility_readiness",
            "operational_metrics",
            "source_data",
            "message_governance",
            "model_health",
            "interoperability",
        ),
        PAGE_CAPABILITY_KEYS,
    ),
    User.ROLE_ANALYST: capability_map(
        (
            "dashboard",
            "overview",
            "wards",
            "alerts",
            "preparedness_actions",
            "facility_readiness",
            "operational_metrics",
            "source_data",
            "message_governance",
            "model_health",
            "interoperability",
            "system",
        ),
        PAGE_CAPABILITY_KEYS,
    ),
    User.ROLE_CHV: capability_map((), PAGE_CAPABILITY_KEYS),
}

EXPECTED_ACTIONS = {
    User.ROLE_ADMIN: capability_map(ACTION_CAPABILITY_KEYS, ACTION_CAPABILITY_KEYS),
    User.ROLE_SUPERVISOR: capability_map(
        (
            "trigger_alerts",
            "manage_preparedness_actions",
            "view_chv_operations",
            "manage_chv_operations",
            "manage_facility_readiness",
            "request_sensitive_exports",
            "download_sensitive_exports",
            "view_source_data",
            "manage_source_data_imports",
            "trigger_source_data_downstream_actions",
            "view_message_governance",
            "view_system_readiness",
            "read_system_control_status",
        ),
        ACTION_CAPABILITY_KEYS,
    ),
    User.ROLE_ANALYST: capability_map(
        (
            "view_source_data",
            "view_message_governance",
            "view_system_readiness",
            "read_system_control_status",
        ),
        ACTION_CAPABILITY_KEYS,
    ),
    User.ROLE_CHV: capability_map((), ACTION_CAPABILITY_KEYS),
}

EXPECTED_SCOPE_TYPE = {
    User.ROLE_ADMIN: "BROAD",
    User.ROLE_SUPERVISOR: "WARD",
    User.ROLE_ANALYST: "BROAD",
    User.ROLE_CHV: "WARD",
}

EXPECTED_TWO_FACTOR_POLICY = {
    User.ROLE_ADMIN: "REQUIRED",
    User.ROLE_SUPERVISOR: "REQUIRED",
    User.ROLE_ANALYST: "OPTIONAL",
    User.ROLE_CHV: "NONE",
}


@override_settings(
    TOTP_REQUIRED_ROLES=(User.ROLE_ADMIN, User.ROLE_SUPERVISOR),
    TOTP_OPTIONAL_ROLES=(User.ROLE_ANALYST,),
)
class DashboardRoleCapabilityTests(APITestCase):
    password = "ChangeMe123!"

    def setUp(self):
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
        self.users = {
            User.ROLE_ADMIN: self._create_user("cap_admin", User.ROLE_ADMIN, self.ward),
            User.ROLE_SUPERVISOR: self._create_user("cap_supervisor", User.ROLE_SUPERVISOR, self.ward),
            User.ROLE_ANALYST: self._create_user("cap_analyst", User.ROLE_ANALYST, self.other_ward),
            User.ROLE_CHV: self._create_user("cap_chv", User.ROLE_CHV, self.ward),
        }

    def _create_user(self, username: str, role: str, ward: Ward):
        return User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password=self.password,
            role=role,
            ward=ward,
            full_name=username.replace("_", " ").title(),
        )

    def test_capability_map_matches_final_role_contract(self):
        self.assertEqual(ROLE_PAGE_CAPABILITIES, EXPECTED_PAGES)
        self.assertEqual(ROLE_ACTION_CAPABILITIES, EXPECTED_ACTIONS)

        for role, user in self.users.items():
            with self.subTest(role=role):
                capabilities = build_dashboard_capabilities(user)
                self.assertEqual(capabilities["schema_version"], "dashboard-capabilities-v1")
                self.assertEqual(capabilities["pages"], EXPECTED_PAGES[role])
                self.assertEqual(capabilities["actions"], EXPECTED_ACTIONS[role])
                self.assertEqual(capabilities["scope"]["type"], EXPECTED_SCOPE_TYPE[role])
                if role in {User.ROLE_ADMIN, User.ROLE_ANALYST}:
                    self.assertIsNone(capabilities["scope"]["ward_id"])
                else:
                    self.assertEqual(capabilities["scope"]["ward_id"], user.ward_id)
                self.assertEqual(
                    default_two_factor_policy_for_role(role),
                    EXPECTED_TWO_FACTOR_POLICY[role],
                )

    def test_auth_me_serializes_dashboard_capabilities_for_each_role(self):
        for role, user in self.users.items():
            with self.subTest(role=role):
                self.client.force_authenticate(user=user)
                response = self.client.get(reverse("auth-me"))

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                capabilities = response.data["dashboard_capabilities"]
                self.assertEqual(capabilities["schema_version"], "dashboard-capabilities-v1")
                self.assertEqual(capabilities["pages"], EXPECTED_PAGES[role])
                self.assertEqual(capabilities["actions"], EXPECTED_ACTIONS[role])
                self.assertEqual(capabilities["policy"]["two_factor_policy"], EXPECTED_TWO_FACTOR_POLICY[role])
                self.assertEqual(response.data["scope_type"], EXPECTED_SCOPE_TYPE[role])
                self.assertEqual(capabilities["scope"]["type"], response.data["scope_type"])
                self.assertEqual(capabilities["scope"]["ward_id"], response.data["scope_ward_id"])
                self.client.force_authenticate(user=None)

    def test_auth_user_admin_endpoints_remain_admin_only(self):
        expected_statuses = {
            User.ROLE_ADMIN: status.HTTP_200_OK,
            User.ROLE_SUPERVISOR: status.HTTP_403_FORBIDDEN,
            User.ROLE_ANALYST: status.HTTP_403_FORBIDDEN,
            User.ROLE_CHV: status.HTTP_403_FORBIDDEN,
        }

        for role, user in self.users.items():
            with self.subTest(role=role):
                self.client.force_authenticate(user=user)
                response = self.client.get(reverse("access-request-list"))
                self.assertEqual(response.status_code, expected_statuses[role])
                self.client.force_authenticate(user=None)

    def test_superuser_uses_admin_contract_without_a_fifth_dashboard_policy_path(self):
        superuser = User.objects.create_user(
            username="cap_superuser",
            email="cap_superuser@example.com",
            password=self.password,
            role=User.ROLE_CHV,
            ward=self.ward,
            is_superuser=True,
            is_staff=True,
        )

        capabilities = build_dashboard_capabilities(superuser)

        self.assertNotIn("SUPERUSER", ROLE_PAGE_CAPABILITIES)
        self.assertNotIn("SUPERUSER", ROLE_ACTION_CAPABILITIES)
        self.assertEqual(capabilities["pages"], EXPECTED_PAGES[User.ROLE_ADMIN])
        self.assertEqual(capabilities["actions"], EXPECTED_ACTIONS[User.ROLE_ADMIN])
        self.assertEqual(capabilities["scope"], {"type": "BROAD", "ward_id": None})

        self.client.force_authenticate(user=superuser)
        response = self.client.get(reverse("auth-me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["scope_type"], "BROAD")
        self.assertEqual(response.data["two_factor_policy"], "REQUIRED")
        self.assertEqual(response.data["dashboard_capabilities"]["policy"]["two_factor_policy"], "REQUIRED")
        self.assertEqual(response.data["dashboard_capabilities"]["pages"], EXPECTED_PAGES[User.ROLE_ADMIN])
        self.assertEqual(response.data["dashboard_capabilities"]["actions"], EXPECTED_ACTIONS[User.ROLE_ADMIN])
