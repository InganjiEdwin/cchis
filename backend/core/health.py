from __future__ import annotations

import redis
from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def live_health(request):
    return JsonResponse({"status": "ok", "service": "backend"}, status=200)


def ready_health(request):
    checks = {"database": "failed", "redis": "failed"}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = "ok"
    except Exception:
        pass

    client = None
    try:
        client = redis.Redis.from_url(
            settings.CELERY_BROKER_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        checks["redis"] = "ok"
    except Exception:
        pass
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    ready = all(value == "ok" for value in checks.values())
    return JsonResponse(
        {
            "status": "ready" if ready else "not_ready",
            "service": "backend",
            "checks": checks,
        },
        status=200 if ready else 503,
    )
