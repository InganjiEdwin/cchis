"""Fail-closed boundaries between demonstration data and operational truth."""

from __future__ import annotations

from django.conf import settings


PRODUCTION_SEEDED_TRUTH_BLOCKED = "production_seeded_truth_blocked"
PRODUCTION_STATIC_FALLBACK_BLOCKED = "production_static_fallback_blocked"
PRODUCTION_UNMAPPED_WARD_BLOCKED = "production_unmapped_ward_blocked"
PRODUCTION_PROXY_NOT_CONFIRMED = "proxy_only_not_confirmed"


class ProductionTruthPolicyError(ValueError):
    """Stable, machine-readable error raised by production truth boundaries."""

    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
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
    return (getattr(dataset, "lineage_metadata", None) or {}) if dataset is not None else {}


def _rainfall_contains_static_fallback(ingestion_run) -> bool:
    if ingestion_run is None:
        return False
    if getattr(ingestion_run, "fallback_used", False):
        return True
    if str(getattr(ingestion_run, "source_kind", "")).upper() == "SEEDED":
        return True
    for result in getattr(ingestion_run, "results", None) or []:
        if result.get("fallback_flag") or result.get("record_type") == "fallback_static":
            return True
        canonical = result.get("canonical_record") or {}
        if canonical.get("fallback_flag") or canonical.get("record_type") == "fallback_static":
            return True
    return False


def production_feature_dataset_blockers(*, training_dataset=None, inference_dataset=None) -> list[str]:
    """Return blockers for production scoring, without mutating any records."""

    if not is_production_environment():
        return []

    blockers: list[str] = []
    training_feature_dataset = getattr(training_dataset, "feature_dataset", None)
    inference_feature_dataset = getattr(inference_dataset, "feature_dataset", None)
    training_lineage = _dataset_lineage(training_feature_dataset)
    inference_lineage = _dataset_lineage(inference_feature_dataset)

    if (
        str(getattr(training_feature_dataset, "source_kind", "")).upper() == "SEEDED"
        or training_lineage.get("include_seeded_labels_for_simulation") is True
        or int(training_lineage.get("training_label_seeded_demo_row_count") or 0) > 0
        or training_lineage.get("training_label_source") == "seeded_mock_training_rows"
    ):
        blockers.append(PRODUCTION_SEEDED_TRUTH_BLOCKED)

    if str(getattr(inference_feature_dataset, "source_kind", "")).upper() == "SEEDED":
        blockers.append(PRODUCTION_SEEDED_TRUTH_BLOCKED)

    if _rainfall_contains_static_fallback(getattr(inference_dataset, "rainfall_ingestion_run", None)):
        blockers.append(PRODUCTION_STATIC_FALLBACK_BLOCKED)

    return list(dict.fromkeys(blockers))


def production_model_run_blockers(model_run) -> list[str]:
    """Check persisted lineage before a model can be promoted or used operationally."""

    if not is_production_environment():
        return []

    class _DatasetRef:
        def __init__(self, feature_dataset, rainfall_ingestion_run=None):
            self.feature_dataset = feature_dataset
            self.rainfall_ingestion_run = rainfall_ingestion_run

    inference_dataset = _DatasetRef(
        getattr(model_run, "inference_feature_dataset", None),
        getattr(model_run, "rainfall_ingestion_run", None),
    )
    training_dataset = _DatasetRef(getattr(model_run, "training_feature_dataset", None))
    blockers = production_feature_dataset_blockers(
        training_dataset=training_dataset,
        inference_dataset=inference_dataset,
    )
    metadata = getattr(model_run, "metadata", None) or {}
    if (
        metadata.get("seeded") is True
        or metadata.get("seeded_non_production") is True
        or metadata.get("execution_context") == "seeded_demo"
        or str(getattr(model_run, "model_version", "")).startswith("v0-demo")
    ):
        blockers.append(PRODUCTION_SEEDED_TRUTH_BLOCKED)
    if metadata.get("production_truth_policy", {}).get("blocked_reason_codes"):
        blockers.extend(metadata["production_truth_policy"]["blocked_reason_codes"])
    return list(dict.fromkeys(blockers))
