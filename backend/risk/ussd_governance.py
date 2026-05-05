from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils import timezone

from risk.chv_localization import (
    DEFAULT_CHV_LANGUAGE,
    SUPPORTED_CHV_LANGUAGES,
    normalize_language_code,
    resolve_language_preference,
)
from risk.models import UssdMenuVersion, UssdSessionLog


USSD_MENU_GOVERNANCE_SCHEMA_VERSION = "ussd-menu-governance-phase-4-v1"
USSD_MENU_KEY = "cholera_health_menu"
USSD_BUILTIN_VERSION_LABEL = "builtin-v1"
USSD_DEFAULT_LANGUAGE = DEFAULT_CHV_LANGUAGE
USSD_SAFE_FALLBACK_COPY = "END Invalid option. Please try again."
USSD_SAFE_FALLBACK_COPY_BY_LANGUAGE = {
    "en": USSD_SAFE_FALLBACK_COPY,
    "sw": "END Chaguo si sahihi. Jaribu tena.",
    "luo": "END Yiero ok ber. Tem kendo.",
}
USSD_REQUIRED_MENU_LANGUAGES = tuple(SUPPORTED_CHV_LANGUAGES)
USSD_RESPONSE_TEXT_MAX_CHARS = 182
USSD_LANGUAGE_SELECTION_VERSION_LABEL = "language-selection-v1"
USSD_LANGUAGE_SELECTION_MENU_LEVEL = "language_selection"
USSD_LANGUAGE_SELECTION_PROMPT = "CON Select language\n1. English\n2. Kiswahili\n3. Dholuo"
USSD_LANGUAGE_SELECTION_INVALID_COPY = (
    "END Invalid option. Select 1 for English, 2 for Kiswahili, or 3 for Dholuo."
)
USSD_LANGUAGE_SELECTION_OPTIONS = {
    "1": "en",
    "2": "sw",
    "3": "luo",
}

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

SW_USSD_MENU_TREE = {
    "routes": DEFAULT_USSD_MENU_TREE["routes"],
    "nodes": {
        "root": {
            "response_type": "CON",
            "body": "Karibu CCHIS Afya\n1. Usalama wa mafuriko\n2. Msaada wa kuhara kwa mtoto\n3. Ushauri wa joto",
        },
        "flood_safety": {
            "response_type": "END",
            "body": (
                "Usalama wa mafuriko:\nTumia maji yaliyotibiwa, epuka maji ya mafuriko, "
                "na nenda kituoni mtoto akihara au kutapika."
            ),
        },
        "diarrhea_menu": {
            "response_type": "CON",
            "body": "Msaada wa kuhara kwa mtoto\n1. Kuhara na kutapika au upungufu wa maji\n2. Kuhara kidogo tu",
        },
        "diarrhea_urgent": {
            "response_type": "END",
            "body": "Mpe ORS sasa na nenda kituo cha afya mara moja. Tumia maji salama na mjulishe CHV.",
        },
        "diarrhea_mild": {
            "response_type": "END",
            "body": "Mpe ORS, endelea kumpa maji, fuatilia, na tafuta huduma akizidiwa.",
        },
        "heat_advice": {
            "response_type": "END",
            "body": (
                "Ushauri wa joto:\nMpe maji mara kwa mara, mweke kivulini, epuka jua kali, "
                "na tafuta huduma akidhoofika."
            ),
        },
    },
}

LUO_USSD_MENU_TREE = {
    "routes": DEFAULT_USSD_MENU_TREE["routes"],
    "nodes": {
        "root": {
            "response_type": "CON",
            "body": "Oyawore e CCHIS Afya\n1. Puonj mar piny mopong'\n2. Kony mar lweyo nyathi\n3. Puonj mar liet",
        },
        "flood_safety": {
            "response_type": "END",
            "body": (
                "Puonj mar piny mopong':\nTi gi pi mothiedhi, kik idhi e pi mopong', "
                "luok lweti, kendo dhi e thieth ka nyathi lweyo kata nindo."
            ),
        },
        "diarrhea_menu": {
            "response_type": "CON",
            "body": "Kony mar lweyo nyathi\n1. Lweyo gi nindo kata rem pi\n2. Lweyo matin kende",
        },
        "diarrhea_urgent": {
            "response_type": "END",
            "body": "Mi ORS sani kendo dhi e od thieth machiegni. Ti gi pi maber kendo nyis CHV ka nitie.",
        },
        "diarrhea_mild": {
            "response_type": "END",
            "body": "Mi ORS, med pi, rit nyathi, kendo many thieth ka wach bedo marach.",
        },
        "heat_advice": {
            "response_type": "END",
            "body": (
                "Puonj mar liet:\nMi pi kinde duto, ket nyathi e tipo, geng' chieng' mar odiechieng', "
                "many thieth ka odoko mayom."
            ),
        },
    },
}

DEFAULT_USSD_MENU_TREES_BY_LANGUAGE = {
    "en": DEFAULT_USSD_MENU_TREE,
    "sw": SW_USSD_MENU_TREE,
    "luo": LUO_USSD_MENU_TREE,
}


@dataclass(frozen=True)
class UssdMenuRenderResult:
    response_text: str
    menu_level: str
    session_outcome: str
    invalid_option: bool
    is_terminal: bool
    language: str
    requested_language: str
    resolved_language: str
    fallback_used: bool
    menu_key: str
    menu_version_label: str
    menu_version: UssdMenuVersion | None
    governance_metadata: dict[str, Any]


def normalize_ussd_language(language: str | None) -> str:
    return (language or USSD_DEFAULT_LANGUAGE).strip().lower() or USSD_DEFAULT_LANGUAGE


def _ussd_menu_tree_structure_signature(menu_tree: dict) -> dict[str, list[str]]:
    if not isinstance(menu_tree, dict):
        return {"routes": [], "nodes": [], "response_types": []}
    routes = menu_tree.get("routes")
    nodes = menu_tree.get("nodes")
    return {
        "routes": [f"{route}:{node_key}" for route, node_key in sorted(routes.items())]
        if isinstance(routes, dict)
        else [],
        "nodes": sorted(nodes.keys()) if isinstance(nodes, dict) else [],
        "response_types": [
            f"{node_key}:{str(node.get('response_type') or '').upper()}"
            for node_key, node in sorted(nodes.items())
            if isinstance(node, dict)
        ]
        if isinstance(nodes, dict)
        else [],
    }


def validate_ussd_response_text(response_text: str, *, required_prefix: str | None = None) -> None:
    text = (response_text or "").strip()
    if required_prefix and not text.startswith(f"{required_prefix} "):
        raise ValidationError(f"USSD response must start with {required_prefix}.")
    if len(text) > USSD_RESPONSE_TEXT_MAX_CHARS:
        raise ValidationError(
            f"USSD response exceeds {USSD_RESPONSE_TEXT_MAX_CHARS} characters: {len(text)}."
        )


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
        validate_ussd_response_text(f"{response_type} {body}", required_prefix=response_type)


def validate_ussd_safe_fallback_copy(copy: str) -> None:
    validate_ussd_response_text(copy, required_prefix="END")


def validate_ussd_menu_translation_contract(menu_version: UssdMenuVersion | None) -> None:
    if menu_version is None or menu_version.language == USSD_DEFAULT_LANGUAGE:
        return
    source = menu_version.source_menu_version
    if source is None:
        raise ValidationError("Translated USSD menu versions require English source linkage.")
    if (
        source.approval_status != UssdMenuVersion.STATUS_APPROVED
        or source.retired_at is not None
        or not source.is_active
    ):
        raise ValidationError("Translated USSD menu versions require an active approved English source.")
    if _ussd_menu_tree_structure_signature(source.menu_tree or {}) != _ussd_menu_tree_structure_signature(
        menu_version.menu_tree or {}
    ):
        raise ValidationError("Translated USSD menu route semantics differ from the English source.")


def active_ussd_menu_version(language: str = USSD_DEFAULT_LANGUAGE) -> UssdMenuVersion | None:
    normalized_language = normalize_ussd_language(language)
    queryset = UssdMenuVersion.objects.filter(
        menu_key=USSD_MENU_KEY,
        language=normalized_language,
        is_active=True,
        approval_status=UssdMenuVersion.STATUS_APPROVED,
        retired_at__isnull=True,
    )
    if normalized_language != USSD_DEFAULT_LANGUAGE:
        queryset = queryset.filter(
            translation_status=UssdMenuVersion.TRANSLATION_APPROVED,
            source_menu_version__isnull=False,
            source_menu_version__is_active=True,
            source_menu_version__approval_status=UssdMenuVersion.STATUS_APPROVED,
            source_menu_version__retired_at__isnull=True,
        )
    return queryset.order_by("-approved_at", "-created_at", "-id").first()


def _menu_tree_for_version(menu_version: UssdMenuVersion | None) -> dict:
    if menu_version is None:
        return DEFAULT_USSD_MENU_TREE
    return menu_version.menu_tree or DEFAULT_USSD_MENU_TREE


def _safe_fallback_for_version(menu_version: UssdMenuVersion | None, language: str = USSD_DEFAULT_LANGUAGE) -> str:
    fallback = USSD_SAFE_FALLBACK_COPY_BY_LANGUAGE.get(language, USSD_SAFE_FALLBACK_COPY)
    if menu_version is None:
        return fallback
    configured = menu_version.safe_fallback_copy.strip() or fallback
    try:
        validate_ussd_safe_fallback_copy(configured)
    except ValidationError:
        return fallback
    return configured


def _latest_persisted_session_language(session_id: str) -> str:
    if not session_id:
        return ""
    recent_logs = UssdSessionLog.objects.filter(session_id=session_id).order_by("-created_at", "-id")[:10]
    for log in recent_logs:
        metadata = log.governance_metadata or {}
        if metadata.get("language_selection_required") and not metadata.get("language_selected"):
            continue
        language = normalize_language_code(log.resolved_language or log.language)
        if language in SUPPORTED_CHV_LANGUAGES:
            return language
    return ""


def _language_selection_result(
    *,
    normalized_text: str,
    requested_language: str,
) -> UssdMenuRenderResult:
    valid_selection_inputs = {""} | set(USSD_LANGUAGE_SELECTION_OPTIONS)
    invalid_option = normalized_text not in valid_selection_inputs
    response_text = USSD_LANGUAGE_SELECTION_INVALID_COPY if invalid_option else USSD_LANGUAGE_SELECTION_PROMPT
    validate_ussd_response_text(response_text, required_prefix="END" if invalid_option else "CON")
    return UssdMenuRenderResult(
        response_text=response_text,
        menu_level=USSD_LANGUAGE_SELECTION_MENU_LEVEL,
        session_outcome=(
            UssdSessionLog.OUTCOME_INVALID_INPUT
            if invalid_option
            else UssdSessionLog.OUTCOME_STARTED
        ),
        invalid_option=invalid_option,
        is_terminal=invalid_option,
        language=USSD_DEFAULT_LANGUAGE,
        requested_language=requested_language or USSD_DEFAULT_LANGUAGE,
        resolved_language=USSD_DEFAULT_LANGUAGE,
        fallback_used=False,
        menu_key=USSD_MENU_KEY,
        menu_version_label=USSD_LANGUAGE_SELECTION_VERSION_LABEL,
        menu_version=None,
        governance_metadata={
            "schema_version": USSD_MENU_GOVERNANCE_SCHEMA_VERSION,
            "menu_key": USSD_MENU_KEY,
            "menu_version_label": USSD_LANGUAGE_SELECTION_VERSION_LABEL,
            "menu_version_public_id": "",
            "language": USSD_DEFAULT_LANGUAGE,
            "requested_language": requested_language or USSD_DEFAULT_LANGUAGE,
            "resolved_language": USSD_DEFAULT_LANGUAGE,
            "fallback_used": False,
            "language_preference_source": "language_selection",
            "source": "phase_4_language_selection",
            "language_selection_required": True,
            "language_selected": False,
            "language_options": USSD_LANGUAGE_SELECTION_OPTIONS,
            "session_outcome_taxonomy": USSD_SESSION_OUTCOME_TAXONOMY,
        },
    )


def render_ussd_menu_response(
    text: str,
    *,
    language: str | None = USSD_DEFAULT_LANGUAGE,
    session_id: str = "",
) -> UssdMenuRenderResult:
    normalized_text = (text or "").strip()
    explicit_requested_language = normalize_language_code(language)
    has_explicit_language = bool(explicit_requested_language)
    persisted_language = "" if has_explicit_language else _latest_persisted_session_language(session_id)
    selected_language = ""
    if not has_explicit_language and not persisted_language:
        selected_language = USSD_LANGUAGE_SELECTION_OPTIONS.get(normalized_text, "")
        if not selected_language:
            return _language_selection_result(
                normalized_text=normalized_text,
                requested_language=explicit_requested_language,
            )

    language_resolution = resolve_language_preference(
        requested_language=explicit_requested_language or persisted_language or selected_language
    )
    normalized_language = language_resolution.resolved_language
    menu_version = active_ussd_menu_version(normalized_language)
    fallback_used = language_resolution.fallback_used
    if menu_version is None and normalized_language != USSD_DEFAULT_LANGUAGE:
        fallback_menu_version = active_ussd_menu_version(USSD_DEFAULT_LANGUAGE)
        if fallback_menu_version is not None:
            menu_version = fallback_menu_version
            normalized_language = USSD_DEFAULT_LANGUAGE
            fallback_used = True
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
        "requested_language": language_resolution.requested_language,
        "resolved_language": normalized_language,
        "fallback_used": fallback_used,
        "language_preference_source": (
            "request"
            if has_explicit_language
            else "ussd_session"
            if persisted_language
            else "language_selection"
            if selected_language
            else "default"
        ),
        "language_selected": bool(selected_language),
        "source": "database" if menu_version else "builtin_fallback",
        "session_outcome_taxonomy": session_outcome_taxonomy,
    }
    try:
        validate_ussd_menu_tree(menu_tree)
        validate_ussd_menu_translation_contract(menu_version)
    except ValidationError as exc:
        return UssdMenuRenderResult(
            response_text=_safe_fallback_for_version(menu_version, normalized_language),
            menu_level="safe_fallback",
            session_outcome=UssdSessionLog.OUTCOME_SAFE_FALLBACK,
            invalid_option=False,
            is_terminal=True,
            language=normalized_language,
            requested_language=language_resolution.requested_language,
            resolved_language=normalized_language,
            fallback_used=fallback_used,
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
    route_text = "" if selected_language else normalized_text
    node_key = routes.get(route_text)
    invalid_option = node_key is None
    if invalid_option:
        response_text = _safe_fallback_for_version(menu_version, normalized_language)
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
        if route_text == "":
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
        requested_language=language_resolution.requested_language,
        resolved_language=normalized_language,
        fallback_used=fallback_used,
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
    language: str | None = USSD_DEFAULT_LANGUAGE,
) -> UssdSessionLog:
    normalized_session_id = session_id or "unknown-session"
    normalized_text = (text or "").strip()
    abandonment_reason = _mark_inferred_abandonment(normalized_session_id) if normalized_text == "" else ""
    rendered = render_ussd_menu_response(normalized_text, language=language, session_id=normalized_session_id)
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
        requested_language=rendered.requested_language,
        resolved_language=rendered.resolved_language,
        fallback_used=rendered.fallback_used,
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
            validate_ussd_safe_fallback_copy(menu_version.safe_fallback_copy)
            validate_ussd_menu_translation_contract(menu_version)
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

    required_language_versions = {
        menu_version.language: menu_version
        for menu_version in UssdMenuVersion.objects.filter(
            menu_key=USSD_MENU_KEY,
            language__in=USSD_REQUIRED_MENU_LANGUAGES,
            is_active=True,
            approval_status=UssdMenuVersion.STATUS_APPROVED,
            retired_at__isnull=True,
        )
        .select_related("source_menu_version")
        .order_by("language", "-approved_at", "-created_at", "-id")
    }
    english_version = required_language_versions.get(USSD_DEFAULT_LANGUAGE)
    english_signature = _ussd_menu_tree_structure_signature(
        (english_version.menu_tree if english_version else DEFAULT_USSD_MENU_TREE) or {}
    )
    coverage_issues = []
    language_evidence = {}
    for language in USSD_REQUIRED_MENU_LANGUAGES:
        menu_version = required_language_versions.get(language)
        if menu_version is None:
            coverage_issues.append({"language": language, "message": "Active approved USSD menu version is missing."})
            language_evidence[language] = {"active": False}
            continue

        signature = _ussd_menu_tree_structure_signature(menu_version.menu_tree or {})
        language_evidence[language] = {
            "active": True,
            "version_label": menu_version.version_label,
            "approval_status": menu_version.approval_status,
            "translation_status": menu_version.translation_status,
            "source_menu_version_public_id": (
                str(menu_version.source_menu_version.public_id) if menu_version.source_menu_version else ""
            ),
            "route_count": len(signature["routes"]),
            "node_count": len(signature["nodes"]),
            "safe_fallback_copy_length": len((menu_version.safe_fallback_copy or "").strip()),
        }
        if signature != english_signature:
            coverage_issues.append(
                {"language": language, "message": "USSD translated route semantics differ from English source."}
            )
        try:
            validate_ussd_safe_fallback_copy(menu_version.safe_fallback_copy)
        except ValidationError as exc:
            coverage_issues.append(
                {
                    "language": language,
                    "message": "Safe fallback copy violates prefix or length budget.",
                    "details": exc.messages,
                }
            )
        if language != USSD_DEFAULT_LANGUAGE:
            if menu_version.source_menu_version_id != getattr(english_version, "id", None):
                coverage_issues.append(
                    {"language": language, "message": "Translated USSD menu is not linked to the active English source."}
                )
            if menu_version.translation_status != UssdMenuVersion.TRANSLATION_APPROVED:
                coverage_issues.append(
                    {"language": language, "message": "Translated USSD menu is not translation-approved."}
                )

    governed_logs = UssdSessionLog.objects.exclude(governance_metadata={})
    missing_trace_logs = list(
        governed_logs.filter(menu_key="", menu_version_label="").values("id", "session_id", "menu_level")[:25]
    )
    missing_outcome_logs = list(governed_logs.filter(session_outcome="").values("id", "session_id", "menu_level")[:25])
    invalid_input_count = UssdSessionLog.objects.filter(session_outcome=UssdSessionLog.OUTCOME_INVALID_INPUT).count()
    abandoned_count = UssdSessionLog.objects.filter(session_outcome=UssdSessionLog.OUTCOME_ABANDONED_INFERRED).count()
    completed_count = UssdSessionLog.objects.filter(session_outcome=UssdSessionLog.OUTCOME_COMPLETED).count()
    outcome_breakdown_by_language = list(
        UssdSessionLog.objects.values("resolved_language", "session_outcome")
        .annotate(count=Count("id"))
        .order_by("resolved_language", "session_outcome")
    )

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
            "id": "phase_4_multilingual_ussd_menu_coverage",
            "status": "pass" if not coverage_issues else "fail",
            "answer": (
                "Approved active English, Kiswahili, and Dholuo USSD menus preserve route semantics, safe fallback copy, and length budgets."
                if not coverage_issues
                else "One or more required USSD language variants are missing or differ from the governed English menu contract."
            ),
            "evidence": {
                "required_languages": USSD_REQUIRED_MENU_LANGUAGES,
                "languages": language_evidence,
                "issues": coverage_issues[:25],
                "response_text_max_chars": USSD_RESPONSE_TEXT_MAX_CHARS,
            },
            "gaps": ["invalid_multilingual_ussd_menu_coverage"] if coverage_issues else [],
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
                "outcome_breakdown_by_language": outcome_breakdown_by_language,
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
