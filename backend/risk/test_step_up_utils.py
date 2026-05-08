from datetime import timedelta

from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import StepUpGrant, UserSession


def force_authenticate_with_step_up(client, user, *purposes: str) -> UserSession:
    session = UserSession.objects.create(
        user=user,
        current_refresh_jti_hash=f"test-step-up-{user.id}-{timezone.now().timestamp()}",
        expires_at=timezone.now() + timedelta(days=1),
    )
    token = AccessToken.for_user(user)
    token["sid"] = str(session.public_id)
    token["family"] = str(session.token_family_id)
    token["role"] = user.role
    token["ward_id"] = user.ward_id
    client.force_authenticate(user=user, token=token)

    for purpose in purposes:
        StepUpGrant.objects.create(
            user=user,
            session=session,
            purpose=purpose,
            verified_at=timezone.now(),
            expires_at=timezone.now() + timedelta(minutes=10),
            method=StepUpGrant.METHOD_TOTP,
        )

    return session
