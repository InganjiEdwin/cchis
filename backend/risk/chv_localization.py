from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any


CHV_LOCALIZATION_SCHEMA_VERSION = "chv-localization-phase-0-1-v1"
DEFAULT_CHV_LANGUAGE = "en"
SUPPORTED_CHV_LANGUAGES = ("en", "sw", "luo")
SUPPORTED_CHV_LANGUAGE_CHOICES = (
    ("en", "English"),
    ("sw", "Kiswahili"),
    ("luo", "Dholuo"),
)

LOCALIZATION_CATEGORY_UI_CHROME = "ui_chrome"
LOCALIZATION_CATEGORY_PUBLIC_HEALTH_COPY = "public_health_copy"
LOCALIZATION_CATEGORY_OPERATIONAL_ERROR = "operational_error_copy"

LOCALIZATION_MANAGEMENT_FRONTEND_DICTIONARY = "frontend_dictionary"
LOCALIZATION_MANAGEMENT_GOVERNED_TEMPLATE = "governed_message_template"
LOCALIZATION_MANAGEMENT_USSD_MENU_VERSION = "ussd_menu_version"
LOCALIZATION_MANAGEMENT_SAFE_ERROR_CODE = "safe_error_code"
LOCALIZATION_MANAGEMENT_DOCUMENTED_GAP = "documented_gap"


@dataclass(frozen=True)
class LanguageResolution:
    requested_language: str
    resolved_language: str
    fallback_used: bool
    preference_source: str

    def as_metadata(self) -> dict[str, Any]:
        return {
            "schema_version": CHV_LOCALIZATION_SCHEMA_VERSION,
            "supported_languages": list(SUPPORTED_CHV_LANGUAGES),
            "default_language": DEFAULT_CHV_LANGUAGE,
            "requested_language": self.requested_language,
            "resolved_language": self.resolved_language,
            "fallback_used": self.fallback_used,
            "preference_source": self.preference_source,
        }


@dataclass(frozen=True)
class LocalizationSurfaceItem:
    localization_key: str
    title: str
    owner: str
    audience: str
    channel: str
    category: str
    risk_level: str
    source_file_or_model: str
    management: str
    stable_key: str = ""
    governed_template_key: str = ""
    notes: str = ""


def normalize_language_code(language: str | None) -> str:
    return (language or "").strip().lower()


def is_supported_language(language: str | None) -> bool:
    return normalize_language_code(language) in SUPPORTED_CHV_LANGUAGES


def supported_language_or_default(language: str | None) -> str:
    normalized = normalize_language_code(language)
    if normalized in SUPPORTED_CHV_LANGUAGES:
        return normalized
    return DEFAULT_CHV_LANGUAGE


def _language_from_object(obj: object | None, *field_names: str) -> str:
    if obj is None:
        return ""
    for field_name in field_names:
        value = getattr(obj, field_name, "")
        normalized = normalize_language_code(value)
        if normalized:
            return normalized
    return ""


def resolve_language_preference(
    *,
    requested_language: str | None = None,
    device_registration: object | None = None,
    chv: object | None = None,
    user: object | None = None,
) -> LanguageResolution:
    candidates = (
        ("request", normalize_language_code(requested_language)),
        ("device_registration", _language_from_object(device_registration, "preferred_language")),
        ("chv", _language_from_object(chv, "preferred_language", "language")),
        ("user_profile", _language_from_object(user, "preferred_language", "language")),
    )

    for source, language in candidates:
        if not language:
            continue
        if language in SUPPORTED_CHV_LANGUAGES:
            return LanguageResolution(
                requested_language=language,
                resolved_language=language,
                fallback_used=False,
                preference_source=source,
            )
        return LanguageResolution(
            requested_language=language,
            resolved_language=DEFAULT_CHV_LANGUAGE,
            fallback_used=True,
            preference_source=source,
        )

    return LanguageResolution(
        requested_language=DEFAULT_CHV_LANGUAGE,
        resolved_language=DEFAULT_CHV_LANGUAGE,
        fallback_used=False,
        preference_source="default",
    )


CHV_LOCALIZATION_SURFACES: tuple[LocalizationSurfaceItem, ...] = (
    LocalizationSurfaceItem(
        localization_key="chv.pwa.navigation",
        stable_key="chv.pwa.navigation",
        title="CHV PWA navigation tabs and view labels",
        owner="chv_product_experience",
        audience="chv",
        channel="pwa",
        category=LOCALIZATION_CATEGORY_UI_CHROME,
        risk_level="low",
        source_file_or_model="frontend/app/chv/page.tsx; frontend/lib/chv-localization.ts",
        management=LOCALIZATION_MANAGEMENT_FRONTEND_DICTIONARY,
        notes="Visible labels include Tasks, Triage, Guidance, Sync, and Profile and are rendered through stable frontend dictionary keys.",
    ),
    LocalizationSurfaceItem(
        localization_key="chv.pwa.offline_status",
        stable_key="chv.pwa.offline_status",
        title="CHV PWA online, offline, bundle freshness, and sync status labels",
        owner="chv_product_experience",
        audience="chv",
        channel="pwa",
        category=LOCALIZATION_CATEGORY_UI_CHROME,
        risk_level="medium",
        source_file_or_model="frontend/app/chv/page.tsx; frontend/lib/chv-localization.ts",
        management=LOCALIZATION_MANAGEMENT_FRONTEND_DICTIONARY,
        notes="Online, offline, bundle freshness, language fallback, and sync status labels are rendered through frontend dictionary keys.",
    ),
    LocalizationSurfaceItem(
        localization_key="chv.pwa.triage_form",
        stable_key="chv.pwa.triage_form",
        title="CHV PWA triage form labels, symptom names, and action buttons",
        owner="chv_product_experience",
        audience="chv",
        channel="pwa",
        category=LOCALIZATION_CATEGORY_UI_CHROME,
        risk_level="high",
        source_file_or_model="frontend/app/chv/page.tsx; frontend/lib/chv-localization.ts",
        management=LOCALIZATION_MANAGEMENT_FRONTEND_DICTIONARY,
        notes="Clinical guidance remains separate in the governed offline bundle; triage form labels and action text are dictionary-backed UI chrome.",
    ),
    LocalizationSurfaceItem(
        localization_key="chv.offline.triage_recommendations",
        governed_template_key="cholera.chv.triage.*_offline",
        title="Offline CHV triage recommendation titles and advice",
        owner="county_health_promotion",
        audience="chv",
        channel="offline_chv_bundle",
        category=LOCALIZATION_CATEGORY_PUBLIC_HEALTH_COPY,
        risk_level="high",
        source_file_or_model="risk.MessageTemplate; risk.chv_offline.build_decision_support_rule_bundle",
        management=LOCALIZATION_MANAGEMENT_GOVERNED_TEMPLATE,
        notes=(
            "Rule outcomes carry recommendation keys only; displayed triage recommendation title and body copy are selected from approved offline CHV MessageTemplate variants."
        ),
    ),
    LocalizationSurfaceItem(
        localization_key="chv.pwa.task_labels",
        stable_key="chv.pwa.task_labels",
        title="CHV task/action labels, priorities, and status labels",
        owner="preparedness_action_operations",
        audience="chv",
        channel="pwa/offline_bundle",
        category=LOCALIZATION_CATEGORY_UI_CHROME,
        risk_level="medium",
        source_file_or_model="risk.chv_offline.build_task_bundle; frontend/app/chv/page.tsx; frontend/lib/chv-localization.ts",
        management=LOCALIZATION_MANAGEMENT_FRONTEND_DICTIONARY,
        notes="Task metadata remains language-neutral codes; user-facing labels are resolved through frontend dictionary keys.",
    ),
    LocalizationSurfaceItem(
        localization_key="chv.offline.guidance_bundle",
        governed_template_key="cholera.household.prevention_guidance_offline_bundle",
        title="Offline CHV prevention and household guidance bundle",
        owner="county_health_promotion",
        audience="chv",
        channel="offline_chv_bundle",
        category=LOCALIZATION_CATEGORY_PUBLIC_HEALTH_COPY,
        risk_level="high",
        source_file_or_model="risk.MessageTemplate; risk.chv_offline.build_guidance_bundle",
        management=LOCALIZATION_MANAGEMENT_GOVERNED_TEMPLATE,
        notes="Approved MessageTemplate variants are selected by resolved language with visible English fallback metadata.",
    ),
    LocalizationSurfaceItem(
        localization_key="chv.sms.operational_message",
        governed_template_key="cholera.chv.workflow_check_in_sms",
        title="CHV operational SMS templates and rendered delivery metadata",
        owner="ward_supervisor",
        audience="chv",
        channel="sms",
        category=LOCALIZATION_CATEGORY_PUBLIC_HEALTH_COPY,
        risk_level="medium",
        source_file_or_model="risk.MessageTemplate; risk.services.create_chv_message",
        management=LOCALIZATION_MANAGEMENT_GOVERNED_TEMPLATE,
        notes="Message render metadata stores requested and resolved language.",
    ),
    LocalizationSurfaceItem(
        localization_key="chv.sync.receipts",
        stable_key="chv.sync.receipts",
        title="CHV sync receipts, safe failure summaries, and conflict explanations",
        owner="offline_sync_operations",
        audience="chv",
        channel="pwa/offline_sync",
        category=LOCALIZATION_CATEGORY_OPERATIONAL_ERROR,
        risk_level="medium",
        source_file_or_model="risk.views.CHVSyncAPIView; risk.chv_offline.record_chv_offline_rejected_submission_audit",
        management=LOCALIZATION_MANAGEMENT_SAFE_ERROR_CODE,
        notes="Receipts use stable status and conflict codes with language metadata; raw payload values are not exposed in safe summaries.",
    ),
    LocalizationSurfaceItem(
        localization_key="chv.ussd.cholera_health_menu",
        governed_template_key="cholera_health_menu",
        title="USSD menu nodes and safe fallback copy",
        owner="county_health_promotion",
        audience="chv/household",
        channel="ussd",
        category=LOCALIZATION_CATEGORY_PUBLIC_HEALTH_COPY,
        risk_level="high",
        source_file_or_model="risk.UssdMenuVersion; risk.ussd_governance",
        management=LOCALIZATION_MANAGEMENT_USSD_MENU_VERSION,
        notes="USSD logs store requested and resolved language plus fallback metadata.",
    ),
)


def build_chv_localization_inventory_report() -> dict[str, Any]:
    surfaces = [asdict(item) for item in CHV_LOCALIZATION_SURFACES]
    missing_required_fields = [
        item["localization_key"]
        for item in surfaces
        if not all(
            item[field]
            for field in (
                "localization_key",
                "owner",
                "audience",
                "channel",
                "category",
                "risk_level",
                "source_file_or_model",
                "management",
            )
        )
    ]
    unmanaged_english_only_gaps = [
        item
        for item in surfaces
        if item["management"] == LOCALIZATION_MANAGEMENT_DOCUMENTED_GAP
    ]
    category_counts = Counter(item["category"] for item in surfaces)
    return {
        "schema_version": CHV_LOCALIZATION_SCHEMA_VERSION,
        "supported_languages": list(SUPPORTED_CHV_LANGUAGES),
        "default_language": DEFAULT_CHV_LANGUAGE,
        "surface_count": len(surfaces),
        "category_counts": dict(category_counts),
        "surfaces": surfaces,
        "missing_required_fields": missing_required_fields,
        "unmanaged_english_only_gaps": unmanaged_english_only_gaps,
    }
