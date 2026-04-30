from __future__ import annotations

import asyncio
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from accounts.models import User

from .notifications import (
    notification_group_name,
    notification_summary_for_user,
    serialize_dashboard_freshness_summary,
    serialize_feed_status_snapshots,
)


ALLOWED_DASHBOARD_ROLES = {User.ROLE_ADMIN, User.ROLE_SUPERVISOR, User.ROLE_ANALYST}
TOPBAR_SNAPSHOT_INTERVAL_SECONDS = 30


class DashboardNotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        token = self._extract_token()
        if not token:
            await self.close(code=4401)
            return

        user = await self._authenticate(token)
        if not user:
            await self.close(code=4401)
            return

        self.user = user
        self.group_name = notification_group_name(user.id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        self.snapshot_task = asyncio.create_task(self._snapshot_loop())
        await self.send_json(
            {
                "event": "notification.connected",
                **await self._notification_summary(),
                "feeds": await self._feed_snapshots(),
                "freshness": await self._freshness_summary(),
            }
        )

    async def disconnect(self, close_code):
        snapshot_task = getattr(self, "snapshot_task", None)
        if snapshot_task is not None:
            snapshot_task.cancel()
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def dashboard_notification_event(self, event):
        await self.send_json(event["payload"])

    async def _snapshot_loop(self):
        try:
            while True:
                await asyncio.sleep(TOPBAR_SNAPSHOT_INTERVAL_SECONDS)
                await self.send_json(
                    {
                        "event": "topbar.snapshot",
                        **await self._notification_summary(),
                        "feeds": await self._feed_snapshots(),
                        "freshness": await self._freshness_summary(),
                    }
                )
        except asyncio.CancelledError:
            return

    def _extract_token(self) -> str | None:
        query_string = self.scope.get("query_string", b"").decode("utf-8")
        token = parse_qs(query_string).get("token", [""])[0].strip()
        return token or None

    @database_sync_to_async
    def _authenticate(self, token: str) -> User | None:
        jwt_authenticator = JWTAuthentication()
        try:
            validated_token = jwt_authenticator.get_validated_token(token)
        except (InvalidToken, TokenError):
            return None

        if validated_token.get("purpose") != "dashboard_notifications_stream":
            return None

        user = jwt_authenticator.get_user(validated_token)
        if not user.is_active or user.role not in ALLOWED_DASHBOARD_ROLES:
            return None

        return user

    @database_sync_to_async
    def _notification_summary(self) -> dict[str, str | int | None]:
        return notification_summary_for_user(self.user)

    @database_sync_to_async
    def _feed_snapshots(self) -> list[dict[str, str | bool | None]]:
        return serialize_feed_status_snapshots()

    @database_sync_to_async
    def _freshness_summary(self) -> dict[str, str | None]:
        return serialize_dashboard_freshness_summary()
