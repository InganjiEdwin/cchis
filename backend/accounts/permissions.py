from rest_framework.permissions import BasePermission

from .models import User
from .role_capabilities import user_is_admin_equivalent


class IsAdminOrSupervisor(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user_is_admin_equivalent(user)
                or user.role == User.ROLE_SUPERVISOR
            )
        )


class IsAdminOnly(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user_is_admin_equivalent(user))


class IsAdminSupervisorOrAnalyst(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user_is_admin_equivalent(user)
                or user.role in [
                    User.ROLE_SUPERVISOR,
                    User.ROLE_ANALYST,
                ]
            )
        )


class IsFieldOperator(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role in [
                User.ROLE_SUPERVISOR,
                User.ROLE_CHV,
            ]
        )
