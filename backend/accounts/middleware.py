from .audit import record_auth_event
from .models import AuthAuditEvent
from .step_up import HIGH_RISK_ACTION_AUDIT_ATTR


class HighRiskActionAuditMiddleware:
    unsafe_methods = {"POST", "PUT", "PATCH", "DELETE"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        audit_payload = getattr(request, HIGH_RISK_ACTION_AUDIT_ATTR, None)
        if not audit_payload:
            return response
        if request.method.upper() not in self.unsafe_methods:
            return response
        if not (200 <= getattr(response, "status_code", 0) < 400):
            return response

        actor = audit_payload.get("actor")
        if not actor or not getattr(actor, "is_authenticated", False):
            return response

        metadata = dict(audit_payload.get("metadata") or {})
        metadata.update(
            {
                "path": request.path,
                "method": request.method.upper(),
                "status_code": response.status_code,
            }
        )
        record_auth_event(
            request=request,
            event_type=AuthAuditEvent.EVENT_HIGH_RISK_ACTION_COMPLETED,
            status=AuthAuditEvent.STATUS_SUCCESS,
            actor=actor,
            target_user=audit_payload.get("target_user") or actor,
            metadata=metadata,
        )
        return response
