from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


class HealthEndpointTestCase(SimpleTestCase):
    def test_liveness_is_public_and_stable(self):
        response = self.client.get("/health/live/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "backend"})

    @override_settings(CELERY_BROKER_URL="redis://redis:6379/0")
    @patch("core.health.redis.Redis.from_url")
    @patch("core.health.connection")
    def test_readiness_is_200_when_database_and_redis_are_available(self, db_connection, from_url):
        redis_client = from_url.return_value

        response = self.client.get("/health/ready/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ready",
                "service": "backend",
                "checks": {"database": "ok", "redis": "ok"},
            },
        )
        db_connection.cursor.assert_called_once()
        redis_client.ping.assert_called_once()

    @patch("core.health.redis.Redis.from_url", side_effect=RuntimeError("redis unavailable"))
    @patch("core.health.connection")
    def test_readiness_is_503_without_dependency_details(self, db_connection, from_url):
        db_connection.cursor.side_effect = RuntimeError("database unavailable")
        response = self.client.get("/health/ready/")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "status": "not_ready",
                "service": "backend",
                "checks": {"database": "failed", "redis": "failed"},
            },
        )
