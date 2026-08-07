"""Fail-closed boundaries between demonstration data and operational truth."""

from __future__ import annotations

import re

from django.conf import settings


PRODUCTION_SEEDED_TRUTH_BLOCKED = "production_seeded_truth_blocked"
PRODUCTION_STATIC_FALLBACK_BLOCKED = "production_static_fallback_blocked"
PRODUCTION_UNMAPPED_WARD_BLOCKED = "production_unmapped_ward_blocked"
PRODUCTION_PROXY_NOT_CONFIRMED = "proxy_only_not_confirmed"
PRODUCTION_SYNTHETIC_FEATURE_FALLBACK_BLOCKED = "production_synthetic_feature_fallback_blocked"
PRODUCTION_SUPERSEDED_TRUTH_BLOCKED = "production_superseded_truth_blocked"
PRODUCTION_CANONICAL_DATASET_REQUIRED = "production_canonical_dataset_required"
PRODUCTION_CANONICAL_DATASET_INVALID = "production_canonical_dataset_invalid"
PRODUCTION_CANONICAL_REFERENCE_INVALID = "production_canonical_reference_invalid"
PRODUCTION_INVALID_FEATURE_ROW_BLOCKED = "production_invalid_feature_row_blocked"
PRODUCTION_ALERT_MODEL_RUN_REQUIRED = "production_alert_model_run_required"
PRODUCTION_ALERT_MODEL_RUN_NOT_SUCCESS = "production_alert_model_run_not_success"
PRODUCTION_ALERT_ACTIVE_REGISTRY_REQUIRED = "production_alert_active_registry_required"
PRODUCTION_ALERT_ELIGIBILITY_BLOCKED = "production_alert_eligibility_blocked"


_SURVEILLANCE_RECORD_REF_PATTERN = re.compile(r"surveillance_record:[^,\s\]}]+")
_SURVEILLANCE_RECORD_ID_PATTERN = re.compile(r"^surveillance_record:(\d+)$")
_SURVEILLANCE_RECORD_ID_KEYS = {
    "record_id",
    "record_ids",
    "source_record_id",
    "source_record_ids",
    "surveillance_record_id",
    "surveillance_record_ids",
    "generated_from_record_ids",
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


def _collect_surveillance_record_refs(value, *, numeric_ids: set[int], string_refs: set[str]) -> None:
    if isinstance(value, str):
        for match in _SURVEILLANCE_RECORD_REF_PATTERN.finditer(value):
            reference = match.group(0).rstrip(".);\"")
            string_refs.add(reference)
            id_match = _SURVEILLANCE_RECORD_ID_PATTERN.fullmatch(reference)
            if id_match:
                numeric_ids.add(int(id_match.group(1)))
        return
    if isinstance(value, list):
        for item in value:
            _collect_surveillance_record_refs(item, numeric_ids=numeric_ids, string_refs=string_refs)
        return
    if not isinstance(value, dict):
        return
    for key, nested_value in value.items():
        if key in _SURVEILLANCE_RECORD_ID_KEYS:
            values = nested_value if isinstance(nested_value, list) else [nested_value]
            for item in values:
                try:
                    if item is not None and str(item).strip():
                        numeric_ids.add(int(item))
                except (TypeError, ValueError):
                    pass
        _collect_surveillance_record_refs(nested_value, numeric_ids=numeric_ids, string_refs=string_refs)


def _canonical_surveillance_reference_blockers(dataset) -> list[str]:
    dataset_id = _dataset_id(dataset)
    if not dataset_id:
        return []

    from risk.models import FeatureDatasetRow, SurveillanceLabelWindow, SurveillanceRecord

    numeric_ids: set[int] = set()
    string_refs: set[str] = set()
    _collect_surveillance_record_refs(
        getattr(dataset, "lineage_metadata", None) or {},
        numeric_ids=numeric_ids,
        string_refs=string_refs,
    )
    rows = FeatureDatasetRow.objects.filter(dataset_id=dataset_id).values_list("feature_values", flat=True)
    for feature_values in rows:
        _collect_surveillance_record_refs(
            feature_values or {},
            numeric_ids=numeric_ids,
            string_refs=string_refs,
        )
    for window_values in SurveillanceLabelWindow.objects.filter(feature_dataset_id=dataset_id).values_list(
        "generated_from_record_refs", "source_coverage_summary"
    ):
        for value in window_values:
            _collect_surveillance_record_refs(value or {}, numeric_ids=numeric_ids, string_refs=string_refs)

    blockers: list[str] = []
    if any(ref not in {f"surveillance_record:{record_id}" for record_id in numeric_ids} for ref in string_refs):
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)

    records = {record.id: record for record in SurveillanceRecord.objects.filter(id__in=numeric_ids)}
    if len(records) != len(numeric_ids):
        _append_unique(blockers, PRODUCTION_CANONICAL_REFERENCE_INVALID)
    record_refs = {f"surveillance_record:{record_id}" for record_id in numeric_ids}
    superseding_refs = set(
        SurveillanceRecord.objects.filter(supersedes_record_ref__in=record_refs).values_list(
            "supersedes_record_ref", flat=True
        )
    )
    for record in records.values():
        raw_payload = record.raw_payload if isinstance(record.raw_payload, dict) else {}
        if raw_payload.get("superseded_by_record_ref") or f"surveillance_record:{record.id}" in superseding_refs:
            _append_unique(blockers, PRODUCTION_SUPERSEDED_TRUTH_BLOCKED)
        if str(record.source_kind).upper() == "SEEDED" or str(record.truth_level).lower() == "seeded_demo":
            _append_unique(blockers, PRODUCTION_SEEDED_TRUTH_BLOCKED)
    return blockers


def _feature_dataset_row_blockers(dataset) -> list[str]:
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
    _append_unique(blockers, *_canonical_surveillance_reference_blockers(dataset))
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

    for dataset, expected_kind in (
        (training_feature_dataset, "TRAINING"),
        (inference_feature_dataset, "INFERENCE"),
    ):
        if dataset is None:
            continue
        if str(getattr(dataset, "dataset_kind", "")).upper() != expected_kind:
            _append_unique(blockers, PRODUCTION_CANONICAL_DATASET_INVALID)
        _append_unique(blockers, *_feature_dataset_row_blockers(dataset))
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
        return []

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
        _append_unique(blockers, *_feature_dataset_row_blockers(dataset))
    return blockers


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
    return blockers


def require_production_alert_eligibility(risk_score) -> None:
    blockers = production_alert_eligibility_blockers(risk_score)
    if blockers:
        raise ProductionTruthPolicyError(
            PRODUCTION_ALERT_ELIGIBILITY_BLOCKED,
            "Production alert eligibility failed: " + ",".join(blockers),
            reason_codes=blockers,
        )
