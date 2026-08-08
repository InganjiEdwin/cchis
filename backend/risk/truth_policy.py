"""Fail-closed boundaries between demonstration data and operational truth."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from django.conf import settings


PRODUCTION_SEEDED_TRUTH_BLOCKED = "production_seeded_truth_blocked"
PRODUCTION_STATIC_FALLBACK_BLOCKED = "production_static_fallback_blocked"
PRODUCTION_UNMAPPED_WARD_BLOCKED = "production_unmapped_ward_blocked"
PRODUCTION_PROXY_NOT_CONFIRMED = "proxy_only_not_confirmed"
PRODUCTION_SYNTHETIC_FEATURE_FALLBACK_BLOCKED = "production_synthetic_feature_fallback_blocked"
PRODUCTION_SUPERSEDED_TRUTH_BLOCKED = "production_superseded_truth_blocked"
PRODUCTION_CANONICAL_DATASET_REQUIRED = "production_canonical_dataset_required"
PRODUCTION_CANONICAL_DATASET_INVALID = "production_canonical_dataset_invalid"
PRODUCTION_CANONICAL_REFERENCE_REQUIRED = "production_canonical_reference_required"
PRODUCTION_CANONICAL_REFERENCE_INVALID = "production_canonical_reference_invalid"
PRODUCTION_INVALID_FEATURE_ROW_BLOCKED = "production_invalid_feature_row_blocked"
PRODUCTION_ALERT_MODEL_RUN_REQUIRED = "production_alert_model_run_required"
PRODUCTION_ALERT_MODEL_RUN_NOT_SUCCESS = "production_alert_model_run_not_success"
PRODUCTION_ALERT_ACTIVE_REGISTRY_REQUIRED = "production_alert_active_registry_required"
PRODUCTION_ACTIVE_ARTIFACT_INTEGRITY_REQUIRED = "production_active_artifact_integrity_required"
PRODUCTION_ACTIVE_MODEL_APPROVAL_REQUIRED = "production_active_model_approval_required"
PRODUCTION_ACTIVE_DEPLOYMENT_TARGET_REQUIRED = "production_active_deployment_target_required"
PRODUCTION_ALERT_ELIGIBILITY_BLOCKED = "production_alert_eligibility_blocked"


_CANONICAL_REFERENCE_PATTERN = re.compile(
    r"(?:surveillance_record|climate_record|surveillance_label_window):[^,\s\]}]+"
)
_SURVEILLANCE_RECORD_ID_PATTERN = re.compile(r"^surveillance_record:(\d+)$")
_CLIMATE_RECORD_ID_PATTERN = re.compile(r"^climate_record:(\d+)$")
_LABEL_WINDOW_ID_PATTERN = re.compile(r"^surveillance_label_window:(\d+)$")
_POPULATION_BASELINE_REFERENCE_PATTERN = re.compile(
    r"population_baseline_record:[^,\s\]}]+"
)
_POPULATION_BASELINE_RECORD_ID_PATTERN = re.compile(r"^population_baseline_record:(\d+)$")
_SURVEILLANCE_RECORD_ID_KEYS = {
    "record_id",
    "record_ids",
    "source_record_id",
    "source_record_ids",
    "surveillance_record_id",
    "surveillance_record_ids",
    "generated_from_record_ids",
}
_CLIMATE_RECORD_ID_KEYS = {
    "climate_record_id",
    "climate_record_ids",
    "rainfall_record_id",
    "rainfall_record_ids",
}
_LABEL_WINDOW_ID_KEYS = {
    "label_window_id",
    "label_window_ids",
    "surveillance_label_window_id",
    "surveillance_label_window_ids",
}
_POPULATION_BASELINE_RECORD_ID_KEYS = {
    "population_baseline_record_id",
    "population_baseline_record_ids",
    "population_baseline_record_ref",
    "population_baseline_record_refs",
    "population_record_id",
    "population_record_ids",
    "population_record_ref",
    "population_record_refs",
}
_SYNTHETIC_FALLBACK_KEYS = {
    "synthetic_rainfall_fallback_used",
    "synthetic_population_fallback_used",
    "fallback_static_rainfall_used",
    "production_synthetic_fallback_used",
}
_FALLBACK_POPULATION_SOURCES = {
    "fallback_static_proxy",
    "population_exposure_unavailable_for_training_row",
}
_PROXY_CONFIRMED_CLAIM_KEYS = {
    "proxy_only_as_confirmed_allowed",
    "surveillance_proxy_only_as_confirmed_allowed",
}
_LABEL_DATASET_REF_KEYS = (
    "surveillance_label_dataset_ref",
    "surveillance_label_feature_dataset_ref",
    "ward_risk_classification_label_dataset_ref",
)


class ProductionTruthPolicyError(ValueError):
    """Stable, machine-readable error raised by production truth boundaries."""

    def __init__(self, code: str, detail: str, *, reason_codes: list[str] | None = None):
        self.code = code
        self.detail = detail
        self.reason_codes = list(dict.fromkeys(reason_codes or []))
        super().__init__(f"{code}: {detail}")


def is_production_environment() -> bool:
    return getattr(settings, "CCHIS_ENVIRONMENT", "local") == "production"


def require_demo_data_allowed(operation: str) -> None:
    if is_production_environment():
        raise ProductionTruthPolicyError(
            PRODUCTION_SEEDED_TRUTH_BLOCKED,
            f"{operation} is categorically disabled in production.",
        )


def require_seeded_truth_allowed(operation: str, *, requested: bool) -> None:
    if requested:
        require_demo_data_allowed(operation)


def _dataset_lineage(dataset) -> dict:
    lineage = (getattr(dataset, "lineage_metadata", None) or {}) if dataset is not None else {}
    return lineage if isinstance(lineage, dict) else {}


def _rainfall_contains_static_fallback(ingestion_run) -> bool:
    if ingestion_run is None:
        return False
    if getattr(ingestion_run, "fallback_used", False):
        return True
    if str(getattr(ingestion_run, "source_kind", "")).upper() == "SEEDED":
        return True
    for result in getattr(ingestion_run, "results", None) or []:
        if not isinstance(result, dict):
            continue
        if result.get("fallback_flag") or result.get("record_type") == "fallback_static":
            return True
        canonical = result.get("canonical_record") or {}
        if canonical.get("fallback_flag") or canonical.get("record_type") == "fallback_static":
            return True
    return False


def _dataset_id(dataset):
    return getattr(dataset, "pk", None) or getattr(dataset, "id", None)


def _append_unique(blockers: list[str], *values: str) -> None:
    for value in values:
        if value and value not in blockers:
            blockers.append(value)


def _contains_truthy_key(value, keys: set[str]) -> bool:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if key in keys and nested_value:
                return True
            if _contains_truthy_key(nested_value, keys):
                return True
    elif isinstance(value, list):
        return any(_contains_truthy_key(item, keys) for item in value)
    return False


def _contains_synthetic_fallback(value) -> bool:
    if _contains_truthy_key(value, _SYNTHETIC_FALLBACK_KEYS):
        return True
    if isinstance(value, dict):
        population_source = str(value.get("population_proxy_source") or "").strip().lower()
        if population_source in _FALLBACK_POPULATION_SOURCES:
            return True
        if value.get("population_exposure_feature_mode") == "fallback_proxy_only":
            return True
        rainfall_lineage = value.get("rainfall_source_lineage")
        if isinstance(rainfall_lineage, dict) and (
            rainfall_lineage.get("fallback_flag")
            or rainfall_lineage.get("record_type") == "fallback_static"
            or rainfall_lineage.get("fallback_static_rainfall_used")
        ):
            return True
        return any(_contains_synthetic_fallback(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_synthetic_fallback(item) for item in value)
    return False


def _contains_proxy_confirmed_claim(value) -> bool:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            if key in _PROXY_CONFIRMED_CLAIM_KEYS and nested_value is True:
                return True
            if _contains_proxy_confirmed_claim(nested_value):
                return True
    elif isinstance(value, list):
        return any(_contains_proxy_confirmed_claim(item) for item in value)
    return False


def _collect_canonical_record_refs(
    value,
    *,
    surveillance_ids: set[int],
    climate_ids: set[int],
    label_window_ids: set[int],
    string_refs: set[str],
) -> None:
    """Collect only typed, resolvable references from persisted lineage JSON."""

    if isinstance(value, str):
        for match in _CANONICAL_REFERENCE_PATTERN.finditer(value):
            reference = match.group(0).rstrip(".);\"")
            string_refs.add(reference)
            surveillance_match = _SURVEILLANCE_RECORD_ID_PATTERN.fullmatch(reference)
            climate_match = _CLIMATE_RECORD_ID_PATTERN.fullmatch(reference)
            label_window_match = _LABEL_WINDOW_ID_PATTERN.fullmatch(reference)
            if surveillance_match:
                surveillance_ids.add(int(surveillance_match.group(1)))
            elif climate_match:
                climate_ids.add(int(climate_match.group(1)))
            elif label_window_match:
                label_window_ids.add(int(label_window_match.group(1)))
        return
    if isinstance(value, list):
        for item in value:
            _collect_canonical_record_refs(
                item,
                surveillance_ids=surveillance_ids,
                climate_ids=climate_ids,
                label_window_ids=label_window_ids,
                string_refs=string_refs,
            )
        return
    if not isinstance(value, dict):
        return
    for key, nested_value in value.items():
        values = nested_value if isinstance(nested_value, list) else [nested_value]
        if key in _SURVEILLANCE_RECORD_ID_KEYS:
            for item in values:
                try:
                    if item is not None and str(item).strip():
                        surveillance_ids.add(int(item))
                except (TypeError, ValueError):
                    pass
        elif key in _CLIMATE_RECORD_ID_KEYS:
            for item in values:
                try:
                    if item is not None and str(item).strip():
                        climate_ids.add(int(item))
                except (TypeError, ValueError):
                    pass
        elif key in _LABEL_WINDOW_ID_KEYS:
            for item in values:
                try:
                    if item is not None and str(item).strip():
                        label_window_ids.add(int(item))
                except (TypeError, ValueError):
                    pass
        _collect_canonical_record_refs(
            nested_value,
            surveillance_ids=surveillance_ids,
            climate_ids=climate_ids,
            label_window_ids=label_window_ids,
            string_refs=string_refs,
        )


def _canonical_refs_from_value(value) -> tuple[set[int], set[int], set[int], set[str]]:
    surveillance_ids: set[int] = set()
    climate_ids: set[int] = set()
    label_window_ids: set[int] = set()
    string_refs: set[str] = set()
    _collect_canonical_record_refs(
        value,
        surveillance_ids=surveillance_ids,
        climate_ids=climate_ids,
        label_window_ids=label_window_ids,
        string_refs=string_refs,
    )
    return surveillance_ids, climate_ids, label_window_ids, string_refs


def _collect_population_baseline_record_refs(
    value,
    *,
    population_ids: set[int],
    string_refs: set[str],
) -> None:
    """Collect typed population baseline references from persisted lineage JSON."""

    if isinstance(value, str):
        for match in _POPULATION_BASELINE_REFERENCE_PATTERN.finditer(value):
            reference = match.group(0).rstrip(".);\"")
            string_refs.add(reference)
            reference_match = _POPULATION_BASELINE_RECORD_ID_PATTERN.fullmatch(reference)
            if reference_match:
                population_ids.add(int(reference_match.group(1)))
        return
    if isinstance(value, list):
        for item in value:
            _collect_population_baseline_record_refs(
                item,
                population_ids=population_ids,
                string_refs=string_refs,
            )
        return
    if not isinstance(value, dict):
        return
    for key, nested_value in value.items():
        values = nested_value if isinstance(nested_value, list) else [nested_value]
        if key in _POPULATION_BASELINE_RECORD_ID_KEYS:
            for item in values:
                try:
                    if item is not None and str(item).strip():
                        population_ids.add(int(item))
                except (TypeError, ValueError):
                    pass
        _collect_population_baseline_record_refs(
            nested_value,
            population_ids=population_ids,
            string_refs=string_refs,
        )


def _population_baseline_refs_from_value(value) -> tuple[set[int], set[str]]:
    population_ids: set[int] = set()
    string_refs: set[str] = set()
    _collect_population_baseline_record_refs(
        value,
        population_ids=population_ids,
        string_refs=string_refs,
    )
    return population_ids, string_refs


def _population_value_matches(feature_value, population_total: int) -> bool:
    if feature_value is None or isinstance(feature_value, bool):
        return False
    try:
        feature_decimal = Decimal(str(feature_value))
        source_decimal = Decimal(str(population_total))
    except (InvalidOperation, TypeError, ValueError):
        return False
    return feature_decimal.is_finite() and feature_decimal == source_decimal


def _expected_truth_level_for_records(truth_levels) -> str:
    from risk.models import SurveillanceTruthLevel

    if truth_levels == {SurveillanceTruthLevel.SEEDED_DEMO}:
        return SurveillanceTruthLevel.SEEDED_DEMO
    if SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE in truth_levels:
        return SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
    if SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE in truth_levels:
        return SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE
    if SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL in truth_levels:
        return SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL
    if SurveillanceTruthLevel.FIELD_SIGNAL_ONLY in truth_levels:
        return SurveillanceTruthLevel.FIELD_SIGNAL_ONLY
    return SurveillanceTruthLevel.FIELD_SIGNAL_ONLY


def _canonical_dataset_reference_blockers(
    dataset,
    *,
    require_surveillance: bool = False,
    require_climate: bool = False,
    require_label_window: bool = False,
    require_population: bool = False,
    allowed_label_window_dataset_ids: set[int] | None = None,
    climate_ingestion_run_id: int | None = None,
) -> list[str]:
    """Validate dataset lineage against canonical source-backed rows."""

    dataset_id = _dataset_id(dataset)
    if not dataset_id:
        # In-memory policy unit fixtures do not have rows to resolve. Persisted
        # production datasets always take the database-backed branch below.
        return []

    from risk.models import (
        ClimateRecord,
        ClimateRecordQualityFlag,
        ClimateRecordType,
        FeatureDatasetRow,
        IngestionRun,
        SurveillanceCaseClass,
        SurveillanceFreshnessState,
        SurveillanceIngestionRun,
        SurveillanceLabelWindow,
        SurveillanceRecord,
        SurveillanceSourceKind,
        SurveillanceTruthLevel,
        PopulationBaselineRecord,
        PopulationExposureFreshness,
        PopulationExposureIngestionRun,
        PopulationExposureSourceKind,
        PopulationExposureTruth,
    )

    lineage = getattr(dataset, "lineage_metadata", None) or {}
    surveillance_ids, climate_ids, label_window_ids, string_refs = _canonical_refs_from_value(lineage)
    population_ids, population_string_refs = _population_baseline_refs_from_value(lineage)
    rows = list(FeatureDatasetRow.objects.filter(dataset_id=dataset_id).select_related("ward"))
    for row in rows:
        row_refs = _canonical_refs_from_value(row.feature_values or {})
        surveillance_ids.update(row_refs[0])
        climate_ids.update(row_refs[1])
        label_window_ids.update(row_refs[2])
        string_refs.update(row_refs[3])
        row_population_ids, row_population_string_refs = _population_baseline_refs_from_value(
            row.feature_values or {}
        )
        population_ids.update(row_population_ids)
        population_string_refs.update(row_population_string_refs)

    attached_windows = list(SurveillanceLabelWindow.objects.filter(feature_dataset_id=dataset_id))
    label_window_ids.update(window.id for window in attached_windows)
    for window in attached_windows:
        window_refs = _canonical_refs_from_value(
            {
                "generated_from_record_refs": window.generated_from_record_refs,
                "source_coverage_summary": window.source_coverage_summary,
            }
        )
        surveillance_ids.update(window_refs[0])
        climate_ids.update(window_refs[1])
        label_window_ids.update(window_refs[2])
        string_refs.update(window_refs[3])

    blockers: list[str] = []
    valid_string_refs = {
        *(f"surveillance_record:{record_id}" for record_id in surveillance_ids),
        *(f"climate_record:{record_id}" for record_id in climate_ids),
        *(f"surveillance_label_window:{window_id}" for window_id in label_window_ids),
    }
    if any(reference not in valid_string_refs for reference in string_refs):
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
    valid_population_string_refs = {
        f"population_baseline_record:{record_id}" for record_id in population_ids
    }
    if any(reference not in valid_population_string_refs for reference in population_string_refs):
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
    typed_population_ids = {
        int(match.group(1))
        for reference in population_string_refs
        if (match := _POPULATION_BASELINE_RECORD_ID_PATTERN.fullmatch(reference))
    }

    if not surveillance_ids and not climate_ids:
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_REQUIRED)
    if require_surveillance and not surveillance_ids:
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_REQUIRED)
    if require_climate and not climate_ids:
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_REQUIRED)
    if require_label_window and not label_window_ids:
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_REQUIRED)
    if require_population and (not population_ids or typed_population_ids != population_ids):
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_REQUIRED)

    surveillance_records = {
        record.id: record
        for record in SurveillanceRecord.objects.filter(id__in=surveillance_ids).select_related(
            "ward", "source", "ingestion_run"
        )
    }
    climate_records = {
        record.id: record
        for record in ClimateRecord.objects.filter(id__in=climate_ids).select_related("ward", "ingestion_run")
    }
    label_windows = {
        window.id: window
        for window in SurveillanceLabelWindow.objects.filter(id__in=label_window_ids).select_related("ward")
    }
    population_records = {
        record.id: record
        for record in PopulationBaselineRecord.objects.filter(id__in=population_ids).select_related(
            "ward", "source", "ingestion_run"
        )
    }

    if len(surveillance_records) != len(surveillance_ids) or len(climate_records) != len(climate_ids):
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
    if len(label_windows) != len(label_window_ids):
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
    if len(population_records) != len(population_ids):
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)

    surveillance_refs = {f"surveillance_record:{record_id}" for record_id in surveillance_ids}
    superseding_refs = set(
        SurveillanceRecord.objects.filter(supersedes_record_ref__in=surveillance_refs).values_list(
            "supersedes_record_ref", flat=True
        )
    )
    for record in surveillance_records.values():
        raw_payload = record.raw_payload if isinstance(record.raw_payload, dict) else {}
        if raw_payload.get("superseded_by_record_ref") or f"surveillance_record:{record.id}" in superseding_refs:
            _append_unique(blockers, PRODUCTION_SUPERSEDED_TRUTH_BLOCKED)
        if str(record.source_kind).lower() == SurveillanceSourceKind.SEEDED or (
            str(record.truth_level).lower() == SurveillanceTruthLevel.SEEDED_DEMO
        ):
            _append_unique(blockers, PRODUCTION_SEEDED_TRUTH_BLOCKED)
        if (
            record.source is None
            or not record.source.is_active
            or not record.source.source_ref
            or record.ingestion_run is None
            or record.ingestion_run.status != SurveillanceIngestionRun.STATUS_SUCCESS
            or record.ingestion_run.fallback_used
            or not record.ingestion_run.source_ref
            or record.source_kind != SurveillanceSourceKind.LIVE
            or record.freshness_state != SurveillanceFreshnessState.FRESH
            or not record.source_ref
            or not raw_payload.get("source_credibility")
            or not record.reporting_period_start
            or not record.reporting_period_end
            or (
                record.source.reporting_period_start
                and record.source.reporting_period_start != record.reporting_period_start
            )
            or (
                record.source.reporting_period_end
                and record.source.reporting_period_end != record.reporting_period_end
            )
            or (
                record.ingestion_run.reporting_period_start
                and record.ingestion_run.reporting_period_start != record.reporting_period_start
            )
            or (
                record.ingestion_run.reporting_period_end
                and record.ingestion_run.reporting_period_end != record.reporting_period_end
            )
        ):
            _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
        if (
            record.case_class == SurveillanceCaseClass.CONFIRMED
            and record.truth_level != SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
        ) or (
            record.truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
            and record.case_class != SurveillanceCaseClass.CONFIRMED
        ):
            _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
        if (
            record.case_class == SurveillanceCaseClass.PROXY
            and record.truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
        ):
            _append_unique(blockers, PRODUCTION_PROXY_NOT_CONFIRMED)

    for record in climate_records.values():
        if (
            record.ward_id is None
            or record.ingestion_run is None
            or record.ingestion_run.status != IngestionRun.STATUS_SUCCESS
            or record.ingestion_run.source_kind != IngestionRun.SOURCE_KIND_LIVE
            or record.ingestion_run.fallback_used
            or record.ingestion_run.freshness_state != IngestionRun.FRESHNESS_FRESH
            or record.source_kind != IngestionRun.SOURCE_KIND_LIVE
            or record.quality_flag != ClimateRecordQualityFlag.ACCEPTED
            or record.fallback_flag
            or record.record_type == ClimateRecordType.FALLBACK_STATIC
            or not record.source_ref
            or not record.source_run
            or not record.valid_date
            or (
                record.record_type == ClimateRecordType.OBSERVED and not record.observed_timestamp
            )
            or (
                record.record_type == ClimateRecordType.FORECAST
                and (not record.issue_time or record.lead_day is None)
            )
            or (climate_ingestion_run_id is not None and record.ingestion_run_id != climate_ingestion_run_id)
        ):
            _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)

    population_refs = {f"population_baseline_record:{record_id}" for record_id in population_ids}
    population_superseding_refs = set(
        PopulationBaselineRecord.objects.filter(supersedes_record_ref__in=population_refs).values_list(
            "supersedes_record_ref", flat=True
        )
    )
    for record in population_records.values():
        raw_payload = record.raw_payload if isinstance(record.raw_payload, dict) else {}
        if raw_payload.get("superseded_by_record_ref") or f"population_baseline_record:{record.id}" in population_superseding_refs:
            _append_unique(blockers, PRODUCTION_SUPERSEDED_TRUTH_BLOCKED)
        if (
            str(record.source_kind).lower() == PopulationExposureSourceKind.SEEDED
            or str(record.truth_class).lower() == PopulationExposureTruth.SEEDED_DEMO
        ):
            _append_unique(blockers, PRODUCTION_SEEDED_TRUTH_BLOCKED)
        if (
            record.ward_id is None
            or record.source is None
            or not record.source.is_active
            or not record.source.source_ref
            or record.ingestion_run is None
            or record.ingestion_run.status != PopulationExposureIngestionRun.STATUS_SUCCESS
            or record.ingestion_run.fallback_used
            or not record.ingestion_run.source_ref
            or record.source_kind != PopulationExposureSourceKind.LIVE
            or record.freshness_state != PopulationExposureFreshness.FRESH
            or not record.source_ref
            or record.truth_class
            not in {
                PopulationExposureTruth.DIRECT_POPULATION_BASELINE,
                PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
            }
        ):
            _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)

    for row in rows:
        row_surveillance_ids, row_climate_ids, row_window_ids, _ = _canonical_refs_from_value(
            row.feature_values or {}
        )
        row_population_ids, row_population_string_refs = _population_baseline_refs_from_value(
            row.feature_values or {}
        )
        row_typed_population_ids = {
            int(match.group(1))
            for reference in row_population_string_refs
            if (match := _POPULATION_BASELINE_RECORD_ID_PATTERN.fullmatch(reference))
        }
        if require_surveillance and not row_surveillance_ids:
            _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_REQUIRED)
        if require_climate and not row_climate_ids:
            _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_REQUIRED)
        if require_population and (
            not row_population_ids or row_typed_population_ids != row_population_ids
        ):
            _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_REQUIRED)
        if row.ward_id is None:
            continue
        for record_id in row_surveillance_ids:
            record = surveillance_records.get(record_id)
            if record is not None and record.ward_id != row.ward_id:
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
        for record_id in row_climate_ids:
            record = climate_records.get(record_id)
            if record is not None and record.ward_id != row.ward_id:
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
        row_values = row.feature_values if isinstance(row.feature_values, dict) else {}
        for record_id in row_population_ids:
            record = population_records.get(record_id)
            if record is not None:
                if record.ward_id != row.ward_id:
                    _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
                if not _population_value_matches(row_values.get("population_total"), record.population_total):
                    _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
        for window_id in row_window_ids:
            window = label_windows.get(window_id)
            if window is not None and (
                window.ward_id != row.ward_id
                or (
                    (require_label_window or allowed_label_window_dataset_ids is not None)
                    and window.feature_dataset_id
                    not in (
                        allowed_label_window_dataset_ids
                        if allowed_label_window_dataset_ids is not None
                        else {dataset_id}
                    )
                )
            ):
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)

    if require_label_window:
        expected_label_window_dataset_ids = allowed_label_window_dataset_ids or {dataset_id}
        for window in label_windows.values():
            if window.feature_dataset_id not in expected_label_window_dataset_ids:
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
        actual_row_count = len(rows)
        if actual_row_count == 0 or int(getattr(dataset, "row_count", 0) or 0) != actual_row_count:
            _append_unique(blockers, PRODUCTION_CANONICAL_DATASET_INVALID)
        for window in label_windows.values():
            generated_refs = window.generated_from_record_refs or []
            window_surveillance_ids, _, _, window_string_refs = _canonical_refs_from_value(generated_refs)
            if not window_surveillance_ids:
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_REQUIRED)
                continue
            if any(
                reference not in {f"surveillance_record:{record_id}" for record_id in window_surveillance_ids}
                for reference in window_string_refs
            ):
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
            window_records = [surveillance_records.get(record_id) for record_id in window_surveillance_ids]
            if any(record is None for record in window_records):
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
                continue
            window_records = [record for record in window_records if record is not None]
            if any(
                record.ward_id != window.ward_id
                or record.reporting_period_end < window.label_window_start
                or record.reporting_period_start > window.label_window_end
                for record in window_records
            ):
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
            expected_counts = {
                SurveillanceCaseClass.SUSPECTED: sum(
                    record.count_value
                    for record in window_records
                    if record.case_class == SurveillanceCaseClass.SUSPECTED
                ),
                SurveillanceCaseClass.CONFIRMED: sum(
                    record.count_value
                    for record in window_records
                    if record.case_class == SurveillanceCaseClass.CONFIRMED
                ),
                SurveillanceCaseClass.PROXY: sum(
                    record.count_value
                    for record in window_records
                    if record.case_class == SurveillanceCaseClass.PROXY
                ),
            }
            if (
                window.source_record_count != len(window_records)
                or window.suspected_case_count != expected_counts[SurveillanceCaseClass.SUSPECTED]
                or window.confirmed_case_count != expected_counts[SurveillanceCaseClass.CONFIRMED]
                or window.proxy_case_count != expected_counts[SurveillanceCaseClass.PROXY]
            ):
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
            expected_truth = _expected_truth_level_for_records(
                {record.truth_level for record in window_records}
            )
            if window.label_truth_level != expected_truth:
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
            if (
                window.label_truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
                and not any(
                    record.truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
                    for record in window_records
                )
            ):
                if any(record.truth_level == SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL for record in window_records):
                    _append_unique(blockers, PRODUCTION_PROXY_NOT_CONFIRMED)
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
            coverage = window.source_coverage_summary if isinstance(window.source_coverage_summary, dict) else {}
            coverage_refs = coverage.get("source_record_refs") or coverage.get("generated_from_record_refs") or []
            if coverage and (
                coverage.get("record_count") not in (None, len(window_records))
                or (coverage_refs and set(coverage_refs) != {f"surveillance_record:{record.id}" for record in window_records})
            ):
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)

        for row in rows:
            row_values = row.feature_values if isinstance(row.feature_values, dict) else {}
            row_window_ids = _canonical_refs_from_value(row_values)[2]
            row_windows = [label_windows[window_id] for window_id in row_window_ids if window_id in label_windows]
            if not row_windows:
                _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_REQUIRED)
                continue
            for window in row_windows:
                if row.label not in (0, 1):
                    _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
                expected_label_fields = {
                    "suspected_case_count": window.suspected_case_count,
                    "confirmed_case_count": window.confirmed_case_count,
                    "proxy_case_count": window.proxy_case_count,
                    "source_record_count": window.source_record_count,
                    "label_truth_level": window.label_truth_level,
                    "outbreak_label": window.outbreak_label,
                }
                if any(
                    field not in row_values or row_values.get(field) != expected_value
                    for field, expected_value in expected_label_fields.items()
                ):
                    _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
                if row.label == 1 and window.outbreak_label != "active":
                    _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)

    return blockers


def _canonical_surveillance_reference_blockers(dataset) -> list[str]:
    return _canonical_dataset_reference_blockers(dataset)


def _feature_dataset_row_blockers(
    dataset,
    *,
    require_surveillance: bool = False,
    require_climate: bool = False,
    require_population: bool = False,
    climate_ingestion_run_id: int | None = None,
) -> list[str]:
    dataset_id = _dataset_id(dataset)
    if not dataset_id:
        return []

    from risk.models import FeatureDatasetRow

    blockers: list[str] = []
    rows = FeatureDatasetRow.objects.filter(dataset_id=dataset_id).select_related("ward")
    for row in rows:
        if (
            row.ward_id is None
            or row.ward is None
            or not row.ward.is_active
            or row.ward_name_snapshot.strip() != row.ward.name.strip()
        ):
            _append_unique(blockers, PRODUCTION_UNMAPPED_WARD_BLOCKED, PRODUCTION_INVALID_FEATURE_ROW_BLOCKED)
        if _contains_synthetic_fallback(row.feature_values or {}):
            _append_unique(blockers, PRODUCTION_SYNTHETIC_FEATURE_FALLBACK_BLOCKED)
    _append_unique(
        blockers,
        *_canonical_dataset_reference_blockers(
            dataset,
            require_surveillance=require_surveillance,
            require_climate=require_climate,
            require_population=require_population,
            climate_ingestion_run_id=climate_ingestion_run_id,
        ),
    )
    return blockers


def production_feature_dataset_blockers(*, training_dataset=None, inference_dataset=None) -> list[str]:
    """Return blockers for production scoring, without mutating any records."""

    if not is_production_environment():
        return []

    blockers: list[str] = []
    training_feature_dataset = getattr(training_dataset, "feature_dataset", None)
    inference_feature_dataset = getattr(inference_dataset, "feature_dataset", None)
    training_lineage = _dataset_lineage(training_feature_dataset)
    inference_lineage = _dataset_lineage(inference_feature_dataset)

    if training_feature_dataset is None or inference_feature_dataset is None:
        _append_unique(blockers, PRODUCTION_CANONICAL_DATASET_REQUIRED)

    if (
        str(getattr(training_feature_dataset, "source_kind", "")).upper() == "SEEDED"
        or training_lineage.get("include_seeded_labels_for_simulation") is True
        or int(training_lineage.get("training_label_seeded_demo_row_count") or 0) > 0
        or training_lineage.get("training_label_source") == "seeded_mock_training_rows"
    ):
        blockers.append(PRODUCTION_SEEDED_TRUTH_BLOCKED)

    if str(getattr(inference_feature_dataset, "source_kind", "")).upper() == "SEEDED":
        _append_unique(blockers, PRODUCTION_SEEDED_TRUTH_BLOCKED)

    if _rainfall_contains_static_fallback(getattr(inference_dataset, "rainfall_ingestion_run", None)):
        _append_unique(blockers, PRODUCTION_STATIC_FALLBACK_BLOCKED)

    rainfall_ingestion_run = getattr(inference_dataset, "rainfall_ingestion_run", None)
    rainfall_run_blockers: list[str] = []
    rainfall_run_id = getattr(rainfall_ingestion_run, "pk", None) or getattr(rainfall_ingestion_run, "id", None)
    if _dataset_id(inference_feature_dataset):
        if rainfall_ingestion_run is None:
            _append_unique(rainfall_run_blockers, PRODUCTION_CANONICAL_REFERENCE_REQUIRED)
        elif rainfall_run_id:
            from risk.models import ClimateRecord, IngestionRun

            if (
                rainfall_ingestion_run.status != IngestionRun.STATUS_SUCCESS
                or rainfall_ingestion_run.source_kind != IngestionRun.SOURCE_KIND_LIVE
                or rainfall_ingestion_run.freshness_state != IngestionRun.FRESHNESS_FRESH
                or rainfall_ingestion_run.fallback_used
                or not ClimateRecord.objects.filter(ingestion_run_id=rainfall_run_id).exists()
            ):
                _append_unique(rainfall_run_blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
    _append_unique(blockers, *rainfall_run_blockers)

    for dataset, expected_kind in (
        (training_feature_dataset, "TRAINING"),
        (inference_feature_dataset, "INFERENCE"),
    ):
        if dataset is None:
            continue
        if str(getattr(dataset, "dataset_kind", "")).upper() != expected_kind:
            _append_unique(blockers, PRODUCTION_CANONICAL_DATASET_INVALID)
        is_training = expected_kind == "TRAINING"
        is_inference = expected_kind == "INFERENCE"
        _append_unique(
            blockers,
            *_feature_dataset_row_blockers(
                dataset,
                require_surveillance=is_training,
                require_climate=is_inference,
                require_population=True,
                climate_ingestion_run_id=rainfall_run_id if is_inference else None,
            ),
        )
        if _contains_proxy_confirmed_claim(getattr(dataset, "lineage_metadata", None) or {}):
            _append_unique(blockers, PRODUCTION_PROXY_NOT_CONFIRMED)

    for lineage in (training_lineage, inference_lineage):
        if _contains_synthetic_fallback(lineage):
            _append_unique(blockers, PRODUCTION_SYNTHETIC_FEATURE_FALLBACK_BLOCKED)
        truth_gate = lineage.get("surveillance_label_truth_gate") or {}
        if truth_gate.get("proxy_only_as_confirmed_allowed") is True:
            _append_unique(blockers, PRODUCTION_PROXY_NOT_CONFIRMED)

    return list(dict.fromkeys(blockers))


def _production_label_dataset_blockers(model_run) -> list[str]:
    metadata = getattr(model_run, "metadata", None) or {}
    if not isinstance(metadata, dict):
        return [PRODUCTION_CANONICAL_REFERENCE_INVALID]
    label_refs = {
        str(metadata.get(key)).strip()
        for key in _LABEL_DATASET_REF_KEYS
        if metadata.get(key)
    }
    label_ids = {
        int(metadata[key])
        for key in ("surveillance_label_feature_dataset_id", "ward_risk_classification_label_dataset_id")
        if str(metadata.get(key) or "").isdigit()
    }
    if not label_refs and not label_ids:
        return [PRODUCTION_CANONICAL_REFERENCE_REQUIRED]

    from risk.models import FeatureDataset

    blockers: list[str] = []
    datasets = {}
    for dataset in FeatureDataset.objects.filter(dataset_ref__in=label_refs):
        datasets[dataset.id] = dataset
    for dataset in FeatureDataset.objects.filter(id__in=label_ids):
        datasets[dataset.id] = dataset
    resolved_refs = {dataset.dataset_ref for dataset in datasets.values()}
    if any(label_ref not in resolved_refs for label_ref in label_refs) or any(
        dataset_id not in datasets for dataset_id in label_ids
    ):
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)

    for dataset in datasets.values():
        if str(getattr(dataset, "dataset_kind", "")).upper() != "TRAINING":
            _append_unique(blockers, PRODUCTION_CANONICAL_DATASET_INVALID)
        if str(getattr(dataset, "source_kind", "")).upper() == "SEEDED":
            _append_unique(blockers, PRODUCTION_SEEDED_TRUTH_BLOCKED)
        lineage = _dataset_lineage(dataset)
        if _contains_synthetic_fallback(lineage):
            _append_unique(blockers, PRODUCTION_SYNTHETIC_FEATURE_FALLBACK_BLOCKED)
        if _contains_proxy_confirmed_claim(lineage):
            _append_unique(blockers, PRODUCTION_PROXY_NOT_CONFIRMED)
        _append_unique(
            blockers,
            *_feature_dataset_row_blockers(dataset, require_surveillance=True),
            *_canonical_dataset_reference_blockers(
                dataset,
                require_surveillance=True,
                require_label_window=True,
            ),
        )
    return blockers


def _declared_label_dataset_ids(metadata: dict) -> set[int]:
    label_refs = {
        str(metadata.get(key)).strip()
        for key in _LABEL_DATASET_REF_KEYS
        if metadata.get(key)
    }
    label_ids = {
        int(metadata[key])
        for key in ("surveillance_label_feature_dataset_id", "ward_risk_classification_label_dataset_id")
        if str(metadata.get(key) or "").isdigit()
    }
    if not label_refs and not label_ids:
        return set()

    from risk.models import FeatureDataset

    return set(
        FeatureDataset.objects.filter(dataset_ref__in=label_refs).values_list("id", flat=True)
    ) | set(FeatureDataset.objects.filter(id__in=label_ids).values_list("id", flat=True))


def production_model_run_blockers(model_run) -> list[str]:
    """Check persisted lineage before a model can be promoted or used operationally."""

    if not is_production_environment():
        return []

    class _DatasetRef:
        def __init__(self, feature_dataset, rainfall_ingestion_run=None):
            self.feature_dataset = feature_dataset
            self.rainfall_ingestion_run = rainfall_ingestion_run

    if model_run is None:
        return [PRODUCTION_CANONICAL_DATASET_REQUIRED]

    inference_feature_dataset = getattr(model_run, "inference_feature_dataset", None)
    training_feature_dataset = getattr(model_run, "training_feature_dataset", None)
    inference_dataset = _DatasetRef(
        inference_feature_dataset,
        getattr(model_run, "rainfall_ingestion_run", None),
    )
    training_dataset = _DatasetRef(training_feature_dataset)
    blockers = production_feature_dataset_blockers(
        training_dataset=training_dataset,
        inference_dataset=inference_dataset,
    )
    metadata = getattr(model_run, "metadata", None) or {}
    if not isinstance(metadata, dict):
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
        return blockers
    if (
        metadata.get("seeded") is True
        or metadata.get("seeded_non_production") is True
        or metadata.get("execution_context") == "seeded_demo"
        or str(getattr(model_run, "model_version", "")).startswith("v0-demo")
    ):
        blockers.append(PRODUCTION_SEEDED_TRUTH_BLOCKED)
    persisted_truth_policy = metadata.get("production_truth_policy") or {}
    if isinstance(persisted_truth_policy, dict) and persisted_truth_policy.get("blocked_reason_codes"):
        blockers.extend(persisted_truth_policy["blocked_reason_codes"])
    blockers.extend(_production_label_dataset_blockers(model_run))
    declared_label_dataset_ids = _declared_label_dataset_ids(metadata)
    if declared_label_dataset_ids:
        for dataset in (training_feature_dataset, inference_feature_dataset):
            _append_unique(
                blockers,
                *_canonical_dataset_reference_blockers(
                    dataset,
                    allowed_label_window_dataset_ids=declared_label_dataset_ids,
                ),
            )
    for truth_gate in (
        metadata.get("surveillance_label_truth_gate") or {},
        metadata.get("surveillance_truth_gate") or {},
    ):
        if isinstance(truth_gate, dict) and truth_gate.get("proxy_only_as_confirmed_allowed") is True:
            blockers.append(PRODUCTION_PROXY_NOT_CONFIRMED)
    return list(dict.fromkeys(blockers))


def production_alert_eligibility_blockers(risk_score) -> list[str]:
    """Return the complete production gate for a score before workflow mutation or delivery."""

    if not is_production_environment():
        return []

    blockers: list[str] = []
    model_run_id = getattr(risk_score, "model_run_id", None)
    if not model_run_id:
        return [PRODUCTION_ALERT_MODEL_RUN_REQUIRED]

    try:
        model_run = getattr(risk_score, "model_run", None)
    except Exception:
        model_run = None
    if model_run is None:
        _append_unique(blockers, PRODUCTION_ALERT_MODEL_RUN_REQUIRED)
        return blockers

    if getattr(model_run, "status", None) != "SUCCESS":
        _append_unique(blockers, PRODUCTION_ALERT_MODEL_RUN_NOT_SUCCESS)
    _append_unique(blockers, *production_model_run_blockers(model_run))

    from risk.ml.registry import active_model_registry_entry

    active_entry = active_model_registry_entry()
    if active_entry is None or active_entry.model_run_id != getattr(model_run, "id", None):
        _append_unique(blockers, PRODUCTION_ALERT_ACTIVE_REGISTRY_REQUIRED)
    else:
        from risk.models import ModelRegistryApprovalState, ModelRegistryLifecycleState

        if active_entry.lifecycle_state != ModelRegistryLifecycleState.ACTIVE:
            _append_unique(blockers, PRODUCTION_ALERT_ACTIVE_REGISTRY_REQUIRED)
        if active_entry.approval_state != ModelRegistryApprovalState.APPROVED:
            _append_unique(blockers, PRODUCTION_ACTIVE_MODEL_APPROVAL_REQUIRED)
        if active_entry.deployment_target != "live_baseline":
            _append_unique(blockers, PRODUCTION_ACTIVE_DEPLOYMENT_TARGET_REQUIRED)
        from risk.ml.model_artifacts import verify_registry_artifact

        if not verify_registry_artifact(active_entry).get("valid"):
            _append_unique(blockers, PRODUCTION_ACTIVE_ARTIFACT_INTEGRITY_REQUIRED)
        from risk.ml.model_registry_governance import model_artifact_approval_blockers

        _append_unique(
            blockers,
            *model_artifact_approval_blockers(active_entry),
        )
    return blockers


def require_production_alert_eligibility(risk_score) -> None:
    blockers = production_alert_eligibility_blockers(risk_score)
    if blockers:
        raise ProductionTruthPolicyError(
            PRODUCTION_ALERT_ELIGIBILITY_BLOCKED,
            "Production alert eligibility failed: " + ",".join(blockers),
            reason_codes=blockers,
        )
