from rest_framework.throttling import ScopedRateThrottle


class AuthScopedRateThrottle(ScopedRateThrottle):
    scope_attr = "throttle_scope"

