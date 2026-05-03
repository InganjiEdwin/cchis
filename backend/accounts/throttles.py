from django.conf import settings
from rest_framework.throttling import ScopedRateThrottle


class AuthScopedRateThrottle(ScopedRateThrottle):
    scope_attr = "throttle_scope"

    def get_rate(self):
        rates = settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {})
        self.THROTTLE_RATES = rates
        return super().get_rate()


class SecondaryAuthScopedRateThrottle(AuthScopedRateThrottle):
    scope_attr = "secondary_throttle_scope"
