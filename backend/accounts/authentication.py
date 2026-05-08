from __future__ import annotations

from rest_framework.exceptions import APIException
from rest_framework_simplejwt.authentication import JWTAuthentication

from .session_security import validate_access_token_session
from .services import build_policy_acceptance_status


class PolicyAcceptanceRequired(APIException):
    status_code = 403
    default_code = "policy_acceptance_required"

    def __init__(self, policy_acceptance: dict):
        super().__init__(
            {
                "detail": "Policy acceptance is required before using this API.",
                "code": self.default_code,
                "policy_acceptance": policy_acceptance,
            }
        )


def _normalized_api_path(path: str) -> str:
    normalized_path = path or "/"
    api_prefix = "/api/v1"

    if normalized_path.startswith(api_prefix):
        normalized_path = normalized_path[len(api_prefix) :] or "/"

    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"

    return normalized_path


def _is_policy_acceptance_bypass_path(path: str, method: str) -> bool:
    normalized_path = _normalized_api_path(path)
    normalized_method = method.upper()

    exact_allowed_paths = {
        "/auth/login/",
        "/auth/refresh/",
        "/auth/session/",
        "/auth/policy-acceptance/",
        "/auth/logout/",
        "/auth/verify-2fa/",
        "/auth/2fa/setup/",
        "/auth/2fa/setup/confirm/",
        "/auth/password-reset/request/",
        "/auth/password-reset/confirm/",
        "/auth/access/request/",
        "/auth/access/request/options/",
        "/ussd/menu/",
    }

    if normalized_path in exact_allowed_paths:
        return True

    return normalized_method == "GET" and normalized_path == "/auth/me/"


class PolicyAwareJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        auth_result = super().authenticate(request)
        if auth_result is None:
            return None

        user, validated_token = auth_result
        validate_access_token_session(user, validated_token)
        if _is_policy_acceptance_bypass_path(request.path_info, request.method):
            return user, validated_token

        policy_acceptance = build_policy_acceptance_status(user)
        if policy_acceptance["required"] and not policy_acceptance["is_current"]:
            raise PolicyAcceptanceRequired(policy_acceptance)

        return user, validated_token
