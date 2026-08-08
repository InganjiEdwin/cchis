"""Authenticated CCHIS identities for model-registry governance actions."""

from __future__ import annotations

from django.contrib.auth import get_user_model


MODEL_REGISTRY_REQUEST_ROLES = frozenset({"ADMIN", "ANALYST"})
MODEL_REGISTRY_GOVERNANCE_ROLES = frozenset({"ADMIN"})


class ModelGovernanceIdentityError(ValueError):
    """Stable errors for unresolved or unauthorized governance actors."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail or code
        super().__init__(self.detail)


def resolve_governance_actor(actor, *, required_roles: frozenset[str] | set[str]):
    """Resolve an active CCHIS user; never trust a caller-supplied role string."""

    User = get_user_model()
    if actor is None or (isinstance(actor, str) and not actor.strip()):
        raise ModelGovernanceIdentityError("governance_actor_required")

    if isinstance(actor, User):
        user = actor
    else:
        value = str(actor).strip()
        queryset = User.objects.all()
        try:
            if value.isdigit():
                user = queryset.get(pk=int(value))
            else:
                user = queryset.get(username=value)
        except User.DoesNotExist as error:
            raise ModelGovernanceIdentityError("governance_actor_not_found") from error

    if not user.is_active:
        raise ModelGovernanceIdentityError("governance_actor_inactive")
    if not (user.is_superuser or user.role in set(required_roles)):
        raise ModelGovernanceIdentityError("governance_actor_role_not_authorized")
    return user


def actor_identity_snapshot(user) -> dict:
    """Return non-sensitive identity evidence for an immutable governance event."""

    return {
        "user_id": user.pk,
        "username": user.get_username(),
        "role": getattr(user, "role", ""),
        "is_superuser": bool(getattr(user, "is_superuser", False)),
    }
