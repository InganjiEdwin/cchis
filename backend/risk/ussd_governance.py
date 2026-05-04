from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone

from risk.models import UssdMenuVersion, UssdSessionLog


USSD_MENU_GOVERNANCE_SCHEMA_VERSION = "ussd-menu-governance-phase-3-v1"
USSD_MENU_KEY = "cholera_health_menu"
USSD_BUILTIN_VERSION_LABEL = "builtin-v1"
USSD_DEFAULT_LANGUAGE = "en"
USSD_SAFE_FALLBACK_COPY = "END Invalid option. Please try again."

USSD_SESSION_OUTCOME_TAXONOMY = {
    UssdSessionLog.OUTCOME_STARTED: "Session reached the root menu.",
    UssdSessionLog.OUTCOME_IN_PROGRESS: "Session is inside a non-terminal menu branch.",
    UssdSessionLog.OUTCOME_COMPLETED: "Session reached a terminal health guidance response.",
    UssdSessionLog.OUTCOME_INVALID_INPUT: "Session submitted a route not present in the active menu tree.",
    UssdSessionLog.OUTCOME_ABANDONED_INFERRED: "Prior non-terminal interaction was inferred abandoned by a restart.",
    UssdSessionLog.OUTCOME_SAFE_FALLBACK: "Session received the configured safe fallback copy.",
}

DEFAULT_USSD_MENU_TREE = {
    "routes": {
        "": "root",
        "1": "flood_safety",
        "2": "diarrhea_menu",
        "2*1": "diarrhea_urgent",
        "2*2": "diarrhea_mild",
        "3": "heat_advice",
    },
    "nodes": {
        "root": {
            "response_type": "CON",
            "body": "Welcome to CCHIS Health Menu\n1. Flood safety advice\n2. Child diarrhea support\n3. Heat health advice",
        },
        "flood_safety": {
            "response_type": "END",
            "body": (
                "Flood safety:\nUse treated water, avoid flood water, wash hands often, "
                "and seek care if child has diarrhea or vomiting."
            ),
        },
        "diarrhea_menu": {
            "response_type": "CON",
            "body": "Child diarrhea support\n1. Diarrhea with vomiting or dehydration\n2. Mild diarrhea only",
        },
        "diarrhea_urgent": {
            "response_type": "END",
            "body": "Give ORS immediately and go to nearest health facility now. Use safe water and report to CHV if available.",
        },
        "diarrhea_mild": {
            "response_type": "END",
            "body": "Give ORS, continue fluids, monitor closely, and seek care if child worsens.",
        },
        "heat_advice": {
            "response_type": "END",
            "body": "Heat advice:\nGive water often, keep child in shade, avoid midday sun, and seek care for weakness or confusion.",
        },
    },
}


@dataclass(frozen=True)
class UssdMenuRenderResult:
    response_text: str
    menu_level: str
    session_outcome: str
    invalid_option: bool
    is_terminal: bool
    language: str
    menu_key: str
    menu_version_label: str
    menu_version: UssdMenuVersion | None
    governance_metadata: dict[str, Any]


def normalize_ussd_language(language: str | None) -> str:
    return (language or USSD_DEFAULT_LANGUAGE).strip().lower() or USSD_DEFAULT_LANGUAGE


def validate_ussd_menu_tree(menu_tree: dict) -> None:
    if not isinstance(menu_tree, dict):
        raise ValidationError("USSD menu tree must be a JSON object.")
    routes = menu_tree.get("routes")
    nodes = menu_tree.get("nodes")
    if not isinstance(routes, dict) or "" not in routes:
        raise ValidationError("USSD menu tree requires a routes object with a root route.")
    if not isinstance(nodes, dict):
        raise ValidationError("USSD menu tree requires a nodes object.")

    missing_nodes = sorted({node_key for node_key in routes.values() if node_key not in nodes})
    if missing_nodes:
        raise ValidationError("USSD routes point to missing nodes: " + ", ".join(missing_nodes))

    for node_key, node in nodes.items():
        if not isinstance(node, dict):
            raise ValidationError(f"USSD node {node_key} must be an object.")
        response_type = str(node.get("response_type") or "").upper()
        body = str(node.get("body") or "").strip()
        if response_type not in {"CON", "END"}:
            raise ValidationError(f"USSD node {node_key} must use response_type CON or END.")
        if not body:
            raise ValidationError(f"USSD node {node_key} requires body copy.")


def active_ussd_menu_version(language: str = USSD_DEFAULT_LANGUAGE) -> UssdMenuVersion | None:
    normalized_language = normalize_ussd_language(language)
    return (
        UssdMenuVersion.objects.filter(
            menu_key=USSD_MENU_KEY,
            language=normalized_language,
            is_active=True,
            approval_status=UssdMenuVersion.STATUS_APPROVED,
            retired_at__isnull=True,
        )
        .order_by("-approved_at", "-created_at", "-id")
        .first()
    )


def _menu_tree_for_version(menu_version: UssdMenuVersion | None) -> dict:
    if menu_version is None:
        return DEFAULT_USSD_MENU_TREE
    return menu_version.menu_tree or DEFAULT_USSD_MENU_TREE


def _safe_fallback_for_version(menu_version: UssdMenuVersion | None) -> str:
    if menu_version is None:
        return USSD_SAFE_FALLBACK_COPY
    return menu_version.safe_fallback_copy.strip() or USSD_SAFE_FALLBACK_COPY


def render_ussd_menu_response(text: str, *, language: str = USSD_DEFAULT_LANGUAGE) -> UssdMenuRenderResult:
    normalized_text = (text or "").strip()
    normalized_language = normalize_ussd_language(language)
    menu_version = active_ussd_menu_version(normalized_language)
    menu_tree = _menu_tree_for_version(menu_version)
    version_label = menu_version.version_label if menu_version is not None else USSD_BUILTIN_VERSION_LABEL
    session_outcome_taxonomy = (
        menu_version.session_outcome_taxonomy
        if menu_version and menu_version.session_outcome_taxonomy
        else USSD_SESSION_OUTCOME_TAXONOMY
    )
    base_metadata = {
        "schema_version": USSD_MENU_GOVERNANCE_SCHEMA_VERSION,
        "menu_key": USSD_MENU_KEY,
        "menu_version_label": version_label,
        "menu_version_public_id": str(menu_version.public_id) if menu_version else "",
        "language": normalized_language,
        "source": "database" if menu_version else "builtin_fallback",
        "session_outcome_taxonomy": session_outcome_taxonomy,
    }
    try:
        validate_ussd_menu_tree(menu_tree)
    except ValidationError as exc:
        return UssdMenuRenderResult(
            response_text=_safe_fallback_for_version(menu_version),
            menu_level="safe_fallback",
            session_outcome=UssdSessionLog.OUTCOME_SAFE_FALLBACK,
            invalid_option=False,
            is_terminal=True,
            language=normalized_language,
            menu_key=USSD_MENU_KEY,
            menu_version_label=version_label,
            menu_version=menu_version,
            governance_metadata={
                **base_metadata,
                "menu_validation_error": exc.messages,
            },
        )

    routes = menu_tree["routes"]
    nodes = menu_tree["nodes"]
    node_key = routes.get(normalized_text)
    invalid_option = node_key is None
    if invalid_option:
        response_text = _safe_fallback_for_version(menu_version)
        menu_level = "invalid"
        session_outcome = UssdSessionLog.OUTCOME_INVALID_INPUT
        is_terminal = True
    else:
        node = nodes[node_key]
        response_type = str(node["response_type"]).upper()
        body = str(node["body"]).strip()
        response_text = f"{response_type} {body}"
        menu_level = node_key
        is_terminal = response_type == "END"
        if normalized_text == "":
            session_outcome = UssdSessionLog.OUTCOME_STARTED
        elif is_terminal:
            session_outcome = UssdSessionLog.OUTCOME_COMPLETED
        else:
            session_outcome = UssdSessionLog.OUTCOME_IN_PROGRESS

    return UssdMenuRenderResult(
        response_text=response_text,
        menu_level=menu_level,
        session_outcome=session_outcome,
        invalid_option=invalid_option,
        is_terminal=is_terminal,
        language=normalized_language,
        menu_key=USSD_MENU_KEY,
        menu_version_label=version_label,
        menu_version=menu_version,
        governance_metadata=base_metadata,
    )


def _mark_inferred_abandonment(session_id: str) -> str:
    if not session_id:
        return ""
    latest_log = (
        UssdSessionLog.objects.filter(session_id=session_id)
        .exclude(is_terminal=True)
        .exclude(session_outcome=UssdSessionLog.OUTCOME_ABANDONED_INFERRED)
        .order_by("-created_at", "-id")
        .first()
    )
    if latest_log is None:
        return ""

    reason = "new_root_request_after_non_terminal_step"
    latest_log.session_outcome = UssdSessionLog.OUTCOME_ABANDONED_INFERRED
    latest_log.abandonment_reason = reason
    latest_log.is_terminal = True
    latest_log.governance_metadata = {
        **(latest_log.governance_metadata or {}),
        "abandonment_inferred_at": timezone.now().isoformat(),
        "abandonment_reason": reason,
    }
    latest_log.save(update_fields=["session_outcome", "abandonment_reason", "is_terminal", "governance_metadata"])
    return reason


def create_ussd_session_log(
    *,
    session_id: str,
    phone_number: str,
    service_code: str,
    text: str,
    language: str = USSD_DEFAULT_LANGUAGE,
) -> UssdSessionLog:
    normalized_session_id = session_id or "unknown-session"
    normalized_text = (text or "").strip()
    abandonment_reason = _mark_inferred_abandonment(normalized_session_id) if normalized_text == "" else ""
    rendered = render_ussd_menu_response(normalized_text, language=language)
    governance_metadata = {
        **rendered.governance_metadata,
        "request_text_depth": 0 if normalized_text == "" else len(normalized_text.split("*")),
        "abandonment_reason_inferred_for_prior_log": abandonment_reason,
    }
    return UssdSessionLog.objects.create(
        session_id=normalized_session_id,
        phone_number=phone_number,
        service_code=service_code,
        text=normalized_text,
        response_text=rendered.response_text,
        menu_version=rendered.menu_version,
        menu_key=rendered.menu_key,
        menu_version_label=rendered.menu_version_label,
        language=rendered.language,
        menu_level=rendered.menu_level,
        session_outcome=rendered.session_outcome,
        invalid_option=rendered.invalid_option,
        abandonment_reason="",
        is_terminal=rendered.is_terminal,
        governance_metadata=governance_metadata,
    )


def build_ussd_governance_audit() -> dict[str, Any]:
    active_versions = list(
        UssdMenuVersion.objects.filter(is_active=True, retired_at__isnull=True).order_by("menu_key", "language")
    )
    invalid_versions = []
    for menu_version in active_versions:
        try:
            validate_ussd_menu_tree(menu_version.menu_tree or {})
        except ValidationError as exc:
            invalid_versions.append(
                {
                    "menu_version_public_id": str(menu_version.public_id),
                    "menu_key": menu_version.menu_key,
                    "version_label": menu_version.version_label,
                    "language": menu_version.language,
                    "messages": exc.messages,
                }
            )

    governed_logs = UssdSessionLog.objects.exclude(governance_metadata={})
    missing_trace_logs = list(
        governed_logs.filter(menu_key="", menu_version_label="").values("id", "session_id", "menu_level")[:25]
    )
    missing_outcome_logs = list(governed_logs.filter(session_outcome="").values("id", "session_id", "menu_level")[:25])
    invalid_input_count = UssdSessionLog.objects.filter(session_outcome=UssdSessionLog.OUTCOME_INVALID_INPUT).count()
    abandoned_count = UssdSessionLog.objects.filter(session_outcome=UssdSessionLog.OUTCOME_ABANDONED_INFERRED).count()
    completed_count = UssdSessionLog.objects.filter(session_outcome=UssdSessionLog.OUTCOME_COMPLETED).count()

    checks = [
        {
            "id": "phase_3_active_ussd_menu_versions_validate",
            "status": "pass" if not invalid_versions else "fail",
            "answer": (
                "Active DB-backed USSD menu versions have valid route and node structure."
                if not invalid_versions
                else "One or more active DB-backed USSD menu versions have invalid route or node structure."
            ),
            "evidence": {"active_version_count": len(active_versions), "invalid_versions": invalid_versions[:25]},
            "gaps": ["invalid_active_ussd_menu_version"] if invalid_versions else [],
        },
        {
            "id": "phase_3_ussd_session_traceability",
            "status": "pass" if not missing_trace_logs and not missing_outcome_logs else "fail",
            "answer": (
                "Governed USSD logs carry menu version, language, and session outcome trace fields."
                if not missing_trace_logs and not missing_outcome_logs
                else "One or more governed USSD logs are missing menu trace or outcome fields."
            ),
            "evidence": {
                "governed_log_count": governed_logs.count(),
                "missing_trace_logs": missing_trace_logs,
                "missing_outcome_logs": missing_outcome_logs,
            },
            "gaps": ["ussd_log_missing_version_language_or_outcome"] if missing_trace_logs or missing_outcome_logs else [],
        },
        {
            "id": "phase_3_ussd_outcome_taxonomy_available",
            "status": "pass",
            "answer": "USSD analytics can separate completion, invalid input, and inferred abandonment outcomes.",
            "evidence": {
                "taxonomy": USSD_SESSION_OUTCOME_TAXONOMY,
                "completed_log_count": completed_count,
                "invalid_input_log_count": invalid_input_count,
                "abandoned_inferred_log_count": abandoned_count,
            },
            "gaps": [],
        },
    ]
    overall_status = "fail" if any(check["status"] == "fail" for check in checks) else "pass"
    return {
        "schema_version": USSD_MENU_GOVERNANCE_SCHEMA_VERSION,
        "overall_status": overall_status,
        "checks": checks,
    }
