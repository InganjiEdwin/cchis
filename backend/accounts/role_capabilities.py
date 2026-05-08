from copy import deepcopy

from .models import User


DASHBOARD_CAPABILITIES_SCHEMA_VERSION = "dashboard-capabilities-v1"

SCOPE_BROAD = "BROAD"
SCOPE_WARD = "WARD"
SCOPE_NONE = "NONE"

TWO_FACTOR_POLICY_REQUIRED = "REQUIRED"
TWO_FACTOR_POLICY_OPTIONAL = "OPTIONAL"
TWO_FACTOR_POLICY_NONE = "NONE"

PAGE_CAPABILITY_KEYS = (
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
    "system",
)

ACTION_CAPABILITY_KEYS = (
    "trigger_alerts",
    "manage_preparedness_actions",
    "view_chv_operations",
    "manage_chv_operations",
    "manage_facility_readiness",
    "request_sensitive_exports",
    "approve_sensitive_exports",
    "download_sensitive_exports",
    "view_source_data",
    "manage_source_data_imports",
    "approve_source_data_risky_imports",
    "trigger_source_data_downstream_actions",
    "view_message_governance",
    "approve_message_governance",
    "view_system_readiness",
    "read_system_control_status",
    "use_system_controls",
    "manage_auth_users",
    "review_auth_audit",
)


def _capability_map(enabled_keys: tuple[str, ...], all_keys: tuple[str, ...]) -> dict[str, bool]:
    enabled = set(enabled_keys)
    return {key: key in enabled for key in all_keys}


def user_is_admin_equivalent(user) -> bool:
    return bool(
        user
        and (
            getattr(user, "is_superuser", False)
            or getattr(user, "role", None) == User.ROLE_ADMIN
        )
    )


ROLE_PAGE_CAPABILITIES: dict[str, dict[str, bool]] = {
    User.ROLE_ADMIN: _capability_map(PAGE_CAPABILITY_KEYS, PAGE_CAPABILITY_KEYS),
    User.ROLE_SUPERVISOR: _capability_map(
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
    User.ROLE_ANALYST: _capability_map(
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
    User.ROLE_CHV: _capability_map((), PAGE_CAPABILITY_KEYS),
}

ROLE_ACTION_CAPABILITIES: dict[str, dict[str, bool]] = {
    User.ROLE_ADMIN: _capability_map(ACTION_CAPABILITY_KEYS, ACTION_CAPABILITY_KEYS),
    User.ROLE_SUPERVISOR: _capability_map(
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
    User.ROLE_ANALYST: _capability_map(
        (
            "view_source_data",
            "view_message_governance",
            "view_system_readiness",
            "read_system_control_status",
        ),
        ACTION_CAPABILITY_KEYS,
    ),
    User.ROLE_CHV: _capability_map((), ACTION_CAPABILITY_KEYS),
}

DEFAULT_TWO_FACTOR_POLICY_BY_ROLE: dict[str, str] = {
    User.ROLE_ADMIN: TWO_FACTOR_POLICY_REQUIRED,
    User.ROLE_SUPERVISOR: TWO_FACTOR_POLICY_REQUIRED,
    User.ROLE_ANALYST: TWO_FACTOR_POLICY_OPTIONAL,
    User.ROLE_CHV: TWO_FACTOR_POLICY_NONE,
}


def effective_dashboard_role(user) -> str:
    if user_is_admin_equivalent(user):
        return User.ROLE_ADMIN

    role = getattr(user, "role", None)
    if role in ROLE_PAGE_CAPABILITIES:
        return role
    return User.ROLE_CHV


def dashboard_scope_for_user(user) -> dict[str, int | str | None]:
    role = effective_dashboard_role(user)
    if role in {User.ROLE_ADMIN, User.ROLE_ANALYST}:
        return {
            "type": SCOPE_BROAD,
            "ward_id": None,
        }

    ward_id = getattr(user, "ward_id", None)
    if ward_id:
        return {
            "type": SCOPE_WARD,
            "ward_id": ward_id,
        }

    return {
        "type": SCOPE_NONE,
        "ward_id": None,
    }


def default_two_factor_policy_for_role(role: str) -> str:
    return DEFAULT_TWO_FACTOR_POLICY_BY_ROLE.get(role, TWO_FACTOR_POLICY_NONE)


def build_dashboard_capabilities(user, *, two_factor_policy: str | None = None) -> dict:
    role = effective_dashboard_role(user)
    return {
        "schema_version": DASHBOARD_CAPABILITIES_SCHEMA_VERSION,
        "scope": dashboard_scope_for_user(user),
        "pages": deepcopy(ROLE_PAGE_CAPABILITIES[role]),
        "actions": deepcopy(ROLE_ACTION_CAPABILITIES[role]),
        "policy": {
            "two_factor_policy": two_factor_policy or default_two_factor_policy_for_role(role),
        },
    }
