from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any

from django.utils import timezone

from accounts.models import User

from risk.climate_source_audit import build_climate_source_separation_audit
from risk.lead_time_features import LEAD_TIME_SOURCE_CUTOFF_POLICY, build_lead_time_feature_dataset
from risk.ml.model_ops_audit import build_model_operations_audit
from risk.models import (
    FacilityReadinessIngestionRun,
    FacilityReadinessSnapshot,
    FeatureDataset,
    SourceDataUploadBatch,
    SourceDataUploadEvent,
    SurveillanceIngestionRun,
    Ward,
)
from risk.population_exposure_audit import build_population_exposure_pipeline_audit
from risk.facility_forecasting import run_facility_burden_forecast_pipeline
from risk.source_data.events import record_source_data_upload_system_event
from risk.source_data.features import FEATURE_DOWNSTREAM_ACTIONS, require_source_data_feature
from risk.source_data.phase0 import (
    INGESTION_FAMILY_FACILITY_READINESS,
    INGESTION_FAMILY_POPULATION_EXPOSURE,
    INGESTION_FAMILY_SURVEILLANCE,
)
from risk.source_data.registry import SourceDataFeedDefinition, source_data_feed_definition
from risk.surveillance_audit import build_surveillance_pipeline_audit
from risk.surveillance_labels import (
    SURVEILLANCE_LABEL_SCHEMA_VERSION,
    build_surveillance_label_dataset,
)
from risk.truth_policy import require_seeded_truth_allowed


SOURCE_DATA_DOWNSTREAM_SCHEMA_VERSION = "source-data-downstream-actions-v1"

ACTION_REGENERATE_SURVEILLANCE_LABELS = "regenerate_surveillance_labels"
ACTION_REBUILD_LEAD_TIME_FEATURES = "rebuild_lead_time_features"
ACTION_RECOMPUTE_FACILITY_READINESS_EVIDENCE = "recompute_facility_readiness_evidence"
ACTION_RUN_SOURCE_AUDITS = "run_source_audits"

ACTION_STATUS_AVAILABLE = "available"
ACTION_STATUS_UNAVAILABLE = "unavailable"
ACTION_STATUS_COMPLETED = "completed"
ACTION_STATUS_QUEUED = "queued"
ACTION_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class SourceDataDownstreamActionDefinition:
    action_key: str
    label: str
    supported_ingestion_families: tuple[str, ...]
    safe_reason: str
    mutates_downstream_evidence: bool
    triggers_sms: bool = False
    promotes_model: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["supported_ingestion_families"] = list(self.supported_ingestion_families)
        return payload


SOURCE_DATA_DOWNSTREAM_ACTIONS: tuple[SourceDataDownstreamActionDefinition, ...] = (
    SourceDataDownstreamActionDefinition(
        action_key=ACTION_REGENERATE_SURVEILLANCE_LABELS,
        label="Regenerate surveillance labels",
        supported_ingestion_families=(INGESTION_FAMILY_SURVEILLANCE,),
        safe_reason=(
            "Uses only canonical surveillance records created on or before the action snapshot time; "
            "it does not score wards, send alerts, send SMS, or promote a model."
        ),
        mutates_downstream_evidence=True,
    ),
    SourceDataDownstreamActionDefinition(
        action_key=ACTION_REBUILD_LEAD_TIME_FEATURES,
        label="Rebuild lead-time feature dataset",
        supported_ingestion_families=(
            INGESTION_FAMILY_SURVEILLANCE,
            INGESTION_FAMILY_POPULATION_EXPOSURE,
        ),
        safe_reason=(
            "Builds a new feature dataset with per-row cutoff proof; it does not replace the active scoring "
            "pipeline, send alerts, send SMS, or promote a model."
        ),
        mutates_downstream_evidence=True,
    ),
    SourceDataDownstreamActionDefinition(
        action_key=ACTION_RECOMPUTE_FACILITY_READINESS_EVIDENCE,
        label="Recompute facility readiness evidence",
        supported_ingestion_families=(INGESTION_FAMILY_FACILITY_READINESS,),
        safe_reason=(
            "Rebuilds facility readiness evidence and forecast input previews from source-backed snapshots; "
            "it does not send alerts, send SMS, replace production forecasts, or promote a model."
        ),
        mutates_downstream_evidence=True,
    ),
    SourceDataDownstreamActionDefinition(
        action_key=ACTION_RUN_SOURCE_AUDITS,
        label="Run source and model-ops audits",
        supported_ingestion_families=(
            INGESTION_FAMILY_SURVEILLANCE,
            INGESTION_FAMILY_POPULATION_EXPOSURE,
            INGESTION_FAMILY_FACILITY_READINESS,
        ),
        safe_reason="Reads audit evidence and stores a summary on the upload; it does not mutate source records.",
        mutates_downstream_evidence=False,
    ),
)


def _is_admin_or_supervisor(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.role in {User.ROLE_ADMIN, User.ROLE_SUPERVISOR})
    )


def _definition_for_batch(batch: SourceDataUploadBatch) -> SourceDataFeedDefinition | None:
    try:
        return source_data_feed_definition(batch.feed_key)
    except KeyError:
        return None


def _action_definition(action_key: str) -> SourceDataDownstreamActionDefinition:
    for definition in SOURCE_DATA_DOWNSTREAM_ACTIONS:
        if definition.action_key == action_key:
            return definition
    raise ValueError("Unsupported downstream action.")


def _normalise_as_of(value) -> datetime:
    if value in (None, ""):
        return timezone.now()
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _normalise_prediction_dates(options: dict[str, Any]) -> list[date]:
    supplied = options.get("prediction_dates") or options.get("prediction_date") or []
    if isinstance(supplied, str):
        supplied = [supplied]
    if supplied:
        return sorted({_parse_date(item) for item in supplied})
    next_scoring_date = timezone.localdate() + timedelta(days=1)
    if options.get("start_date") and options.get("end_date"):
        start_date = _parse_date(options["start_date"])
        end_date = _parse_date(options["end_date"])
        if start_date > end_date:
            raise ValueError("start_date cannot be after end_date.")
        step_days = max(int(options.get("step_days") or 1), 1)
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(current)
            current += timedelta(days=step_days)
        return dates
    return [next_scoring_date]


def _require_explicit_as_of(options: dict[str, Any], *, action_label: str) -> datetime:
    if options.get("as_of") in (None, ""):
        raise ValueError(f"{action_label} requires an explicit as_of timestamp for cutoff evidence.")
    return _normalise_as_of(options.get("as_of"))


def _require_explicit_prediction_window(options: dict[str, Any], *, action_label: str) -> None:
    if options.get("prediction_date") or options.get("prediction_dates"):
        return
    if options.get("start_date") and options.get("end_date"):
        return
    raise ValueError(f"{action_label} requires explicit prediction_date, prediction_dates, or start/end dates.")


def _public_downstream_history(batch: SourceDataUploadBatch) -> list[dict[str, Any]]:
    return list((batch.metadata or {}).get("downstream_actions") or [])


def downstream_actions_for_upload(batch: SourceDataUploadBatch) -> list[dict[str, Any]]:
    definition = _definition_for_batch(batch)
    if definition is None:
        return []

    actions = []
    for action in SOURCE_DATA_DOWNSTREAM_ACTIONS:
        is_supported_family = definition.ingestion_family in action.supported_ingestion_families
        is_imported = (
            batch.status == SourceDataUploadBatch.STATUS_IMPORTED
            and batch.import_status == SourceDataUploadBatch.IMPORT_IMPORTED
        )
        unavailable_reason = ""
        if not is_supported_family:
            unavailable_reason = "This action does not apply to this feed family."
        elif not is_imported:
            unavailable_reason = "Import must complete successfully before downstream actions are available."
        elif action.action_key == ACTION_REGENERATE_SURVEILLANCE_LABELS and not batch.surveillance_ingestion_run_id:
            unavailable_reason = "No linked surveillance ingestion run is available."
        elif action.action_key == ACTION_REBUILD_LEAD_TIME_FEATURES and definition.ingestion_family == INGESTION_FAMILY_FACILITY_READINESS:
            unavailable_reason = "Facility readiness feature rebuilds are deferred to the readiness snapshot phase."
        elif (
            action.action_key == ACTION_RECOMPUTE_FACILITY_READINESS_EVIDENCE
            and not batch.facility_readiness_ingestion_run_id
        ):
            unavailable_reason = "No linked facility readiness ingestion run is available."

        history = [
            item for item in _public_downstream_history(batch) if item.get("action_key") == action.action_key
        ]
        actions.append(
            {
                **action.as_dict(),
                "availability_status": ACTION_STATUS_UNAVAILABLE if unavailable_reason else ACTION_STATUS_AVAILABLE,
                "unavailable_reason": unavailable_reason,
                "recommended": is_imported
                and not unavailable_reason
                and (
                    (
                        action.action_key == ACTION_REGENERATE_SURVEILLANCE_LABELS
                        and definition.ingestion_family == INGESTION_FAMILY_SURVEILLANCE
                    )
                    or (
                        action.action_key == ACTION_REBUILD_LEAD_TIME_FEATURES
                        and definition.ingestion_family == INGESTION_FAMILY_POPULATION_EXPOSURE
                    )
                    or (
                        action.action_key == ACTION_RECOMPUTE_FACILITY_READINESS_EVIDENCE
                        and definition.ingestion_family == INGESTION_FAMILY_FACILITY_READINESS
                    )
                    or action.action_key == ACTION_RUN_SOURCE_AUDITS
                ),
                "latest_result": history[-1] if history else None,
            }
        )
    return actions


def _summarise_dataset(dataset: FeatureDataset) -> dict[str, Any]:
    lineage = dataset.lineage_metadata or {}
    return {
        "feature_dataset_id": dataset.id,
        "dataset_ref": dataset.dataset_ref,
        "schema_version": dataset.schema_version,
        "row_count": dataset.row_count,
        "source_kind": dataset.source_kind,
        "created_at": dataset.created_at.isoformat(),
        "coverage": lineage.get("coverage") or {},
    }


def _source_run_ids(batch: SourceDataUploadBatch) -> dict[str, int | None]:
    return {
        "domain_ingestion_run_id": batch.domain_ingestion_run_id,
        "surveillance_ingestion_run_id": batch.surveillance_ingestion_run_id,
        "population_exposure_ingestion_run_id": batch.population_exposure_ingestion_run_id,
        "facility_readiness_ingestion_run_id": batch.facility_readiness_ingestion_run_id,
    }


def _run_surveillance_label_action(
    batch: SourceDataUploadBatch,
    *,
    options: dict[str, Any],
) -> dict[str, Any]:
    run = batch.surveillance_ingestion_run
    if run is None:
        raise ValueError("This upload is not linked to a surveillance ingestion run.")
    if run.status == SurveillanceIngestionRun.STATUS_FAILED:
        raise ValueError("Cannot regenerate labels from a failed surveillance ingestion run.")
    if run.execution_mode == SurveillanceIngestionRun.EXECUTION_REPLAY:
        raise ValueError("Replay diagnostic runs cannot regenerate operational labels.")
    if run.reporting_period_start is None or run.reporting_period_end is None:
        raise ValueError("Surveillance label regeneration requires reporting period bounds.")

    dataset_role = (options.get("dataset_role") or "evaluation").strip()
    if dataset_role not in {"training", "evaluation"}:
        raise ValueError("dataset_role must be either 'training' or 'evaluation'.")
    window_days = int(options.get("window_days") or 7)
    step_days = int(options.get("step_days") or 7)
    if window_days <= 0 or step_days <= 0:
        raise ValueError("window_days and step_days must be greater than zero.")

    ward_ids = list(run.surveillance_records.order_by().values_list("ward_id", flat=True).distinct())
    if not ward_ids:
        raise ValueError("No canonical surveillance records are linked to this ingestion run.")

    as_of = _require_explicit_as_of(options, action_label="Surveillance label regeneration")
    require_seeded_truth_allowed(
        "seeded surveillance label regeneration",
        requested=bool(options.get("include_seeded", False)),
    )
    wards = Ward.objects.filter(id__in=ward_ids).order_by("name")
    snapshot = build_surveillance_label_dataset(
        wards=wards,
        start_date=run.reporting_period_start,
        end_date=run.reporting_period_end,
        as_of=as_of,
        window_days=window_days,
        step_days=step_days,
        dataset_role=dataset_role,
        include_seeded=bool(options.get("include_seeded", False)),
    )
    dataset = snapshot.feature_dataset
    leakage_check = {
        "passed": True,
        "snapshot_as_of": as_of.isoformat(),
        "source_records_filtered_to_snapshot_as_of": True,
        "label_windows_used_as_input": False,
        "schema_version": SURVEILLANCE_LABEL_SCHEMA_VERSION,
    }
    evidence = {
        **_summarise_dataset(dataset),
        "label_window_count": len(snapshot.label_windows),
        "dataset_role": dataset_role,
        "as_of": as_of.isoformat(),
        "source_run_ids": _source_run_ids(batch),
        "leakage_check": leakage_check,
    }
    run.results = {
        **(run.results or {}),
        "downstream_label_regeneration": evidence,
    }
    run.save(update_fields=["results"])
    return evidence


def _run_feature_rebuild_action(
    batch: SourceDataUploadBatch,
    *,
    options: dict[str, Any],
) -> dict[str, Any]:
    require_seeded_truth_allowed(
        "seeded surveillance lead-time feature generation",
        requested=bool(options.get("include_seeded_surveillance", False)),
    )
    as_of = _require_explicit_as_of(options, action_label="Lead-time feature rebuild")
    _require_explicit_prediction_window(options, action_label="Lead-time feature rebuild")
    prediction_dates = _normalise_prediction_dates(options)
    snapshot = build_lead_time_feature_dataset(
        prediction_dates=prediction_dates,
        source_cutoff_as_of=as_of,
        include_seeded_surveillance=bool(options.get("include_seeded_surveillance", False)),
        heavy_rain_threshold_mm=float(options.get("heavy_rain_threshold_mm") or 50.0),
        claimed_forecast_horizon_days=int(options.get("claimed_forecast_horizon_days") or 14),
    )
    dataset = snapshot.feature_dataset
    lineage = dataset.lineage_metadata or {}
    coverage = lineage.get("coverage") or {}
    rows_passing = int(coverage.get("rows_passing_leakage_check") or 0)
    leakage_check = {
        "passed": rows_passing == dataset.row_count,
        "rows_passing_leakage_check": rows_passing,
        "row_count": dataset.row_count,
        "source_cutoff_policy": lineage.get("source_cutoff_policy") or LEAD_TIME_SOURCE_CUTOFF_POLICY,
        "leakage_proof_contract": lineage.get("leakage_proof_contract") or {},
    }
    evidence = {
        **_summarise_dataset(dataset),
        "as_of": as_of.isoformat(),
        "prediction_dates": [item.isoformat() for item in prediction_dates],
        "population_exposure_dataset_refs": lineage.get("population_exposure_dataset_refs") or [],
        "source_run_ids": _source_run_ids(batch),
        "leakage_check": leakage_check,
    }
    dataset.lineage_metadata = {
        **lineage,
        "source_data_downstream_action": {
            "source_data_upload_public_id": str(batch.public_id),
            "feed_key": batch.feed_key,
            "source_run_ids": _source_run_ids(batch),
            "requested_at": timezone.now().isoformat(),
            "requested_as_of": as_of.isoformat(),
        },
    }
    dataset.save(update_fields=["lineage_metadata"])
    if not leakage_check["passed"]:
        raise ValueError("Feature dataset rebuild failed leakage proof checks.")
    return evidence


def _audit_summary(name: str, builder) -> dict[str, Any]:
    try:
        audit = builder()
    except Exception as error:
        return {"name": name, "status": ACTION_STATUS_FAILED, "error": str(error)}
    return {
        "name": name,
        "status": audit.get("overall_status", "unknown"),
        "record_totals": audit.get("record_totals") or {},
        "source_totals": audit.get("source_totals") or {},
        "summary": audit.get("summary") or audit.get("governance") or {},
    }


def _run_audit_action() -> dict[str, Any]:
    return {
        "audits": [
            _audit_summary("climate", build_climate_source_separation_audit),
            _audit_summary("surveillance", build_surveillance_pipeline_audit),
            _audit_summary("population_exposure", build_population_exposure_pipeline_audit),
            _audit_summary("model_operations", build_model_operations_audit),
        ],
        "triggers_sms": False,
        "promotes_model": False,
        "runs_model_scoring": False,
    }


def _run_facility_readiness_recompute_action(batch: SourceDataUploadBatch) -> dict[str, Any]:
    if not batch.facility_readiness_ingestion_run_id:
        raise ValueError("This upload is not linked to a facility readiness ingestion run.")
    run = FacilityReadinessIngestionRun.objects.filter(pk=batch.facility_readiness_ingestion_run_id).first()
    if run is None:
        raise ValueError("Linked facility readiness ingestion run is not available.")
    if run.status == FacilityReadinessIngestionRun.STATUS_FAILED:
        raise ValueError("Cannot recompute readiness evidence from a failed facility readiness ingestion run.")

    snapshots = list(
        FacilityReadinessSnapshot.objects.filter(ingestion_run=run)
        .select_related("facility", "ward")
        .order_by("facility__name", "-reported_at")
    )
    if not snapshots:
        raise ValueError("No facility readiness snapshots are linked to this ingestion run.")

    forecast_run = run_facility_burden_forecast_pipeline(
        model_version=f"fnb-readiness-source-{batch.id}",
        execution_context="source_data_downstream_action",
        run_purpose="readiness_snapshot_feature_rebuild",
    )
    forecast_run.metadata = {
        **(forecast_run.metadata or {}),
        "source_data_downstream_action": {
            "source_data_upload_public_id": str(batch.public_id),
            "feed_key": batch.feed_key,
            "facility_readiness_ingestion_run_id": run.id,
            "requested_at": timezone.now().isoformat(),
            "promotion_target": "preview_only_no_model_promotion",
        },
    }
    forecast_run.save(update_fields=["metadata"])

    readiness_summary = (run.results or {}).get("readiness_summary") or {}
    evidence = {
        "facility_readiness_ingestion_run_id": run.id,
        "snapshot_count": len(snapshots),
        "facility_ids": [snapshot.facility_id for snapshot in snapshots],
        "facility_codes": [snapshot.facility.facility_code for snapshot in snapshots],
        "facility_coverage": readiness_summary,
        "source_run_ids": _source_run_ids(batch),
        "forecast_run_id": forecast_run.id,
        "forecast_run_status": forecast_run.status,
        "forecast_model_version": forecast_run.model_version,
        "forecast_feature_schema_version": forecast_run.feature_schema_version,
        "training_dataset_ref": (forecast_run.metadata or {}).get("training_dataset_ref"),
        "inference_dataset_ref": (forecast_run.metadata or {}).get("inference_dataset_ref"),
        "promotion_target": (forecast_run.metadata or {}).get("promotion_target"),
        "triggers_sms": False,
        "promotes_model": False,
        "runs_model_scoring": False,
    }
    run.results = {
        **(run.results or {}),
        "downstream_readiness_recompute": evidence,
    }
    run.save(update_fields=["results"])
    return evidence


def _persist_downstream_result(batch: SourceDataUploadBatch, result: dict[str, Any]) -> SourceDataUploadBatch:
    metadata = batch.metadata or {}
    history = list(metadata.get("downstream_actions") or [])
    history.append(result)
    batch.metadata = {
        **metadata,
        "downstream_actions": history[-20:],
        "latest_downstream_action": result,
    }
    batch.save(update_fields=["metadata", "updated_at"])
    return batch


def run_source_data_downstream_action(
    *,
    batch: SourceDataUploadBatch,
    action_key: str,
    actor=None,
    options: dict[str, Any] | None = None,
    worker_execution: bool = False,
) -> dict[str, Any]:
    require_source_data_feature(FEATURE_DOWNSTREAM_ACTIONS)
    options = options or {}
    if not _is_admin_or_supervisor(actor):
        raise ValueError("Only admins or supervisors can trigger source-data downstream actions.")
    if options.get("production") or options.get("replace_existing"):
        raise ValueError(
            "Production downstream evidence replacement requires maker-checker approval and is not enabled here."
        )

    action = _action_definition(action_key)
    available_actions = downstream_actions_for_upload(batch)
    current_action = next((item for item in available_actions if item["action_key"] == action.action_key), None)
    if current_action is None or current_action["availability_status"] != ACTION_STATUS_AVAILABLE:
        reason = (current_action or {}).get("unavailable_reason") or "This downstream action is not available."
        raise ValueError(reason)

    started_at = timezone.now()
    try:
        if action.action_key == ACTION_REGENERATE_SURVEILLANCE_LABELS:
            evidence = _run_surveillance_label_action(batch, options=options)
        elif action.action_key == ACTION_REBUILD_LEAD_TIME_FEATURES:
            evidence = _run_feature_rebuild_action(batch, options=options)
        elif action.action_key == ACTION_RECOMPUTE_FACILITY_READINESS_EVIDENCE:
            evidence = _run_facility_readiness_recompute_action(batch)
        elif action.action_key == ACTION_RUN_SOURCE_AUDITS:
            evidence = _run_audit_action()
        else:
            raise ValueError("Unsupported downstream action.")
        action_status = ACTION_STATUS_COMPLETED
    except Exception as error:
        action_status = ACTION_STATUS_FAILED
        evidence = {"error": str(error)}

    result = {
        "schema_version": SOURCE_DATA_DOWNSTREAM_SCHEMA_VERSION,
        "action_key": action.action_key,
        "action_label": action.label,
        "action_status": action_status,
        "requested_by_username": actor.username if actor else None,
        "started_at": started_at.isoformat(),
        "completed_at": timezone.now().isoformat(),
        "worker_execution": worker_execution,
        "safe_reason": action.safe_reason,
        "triggers_sms": action.triggers_sms,
        "promotes_model": action.promotes_model,
        "evidence": evidence,
    }
    _persist_downstream_result(batch, result)
    record_source_data_upload_system_event(
        batch=batch,
        event_type=SourceDataUploadEvent.EVENT_DOWNSTREAM_ACTION_REQUESTED,
        actor=actor,
        metadata={
            "action_key": action.action_key,
            "action_status": action_status,
            "worker_execution": worker_execution,
            "evidence": evidence,
        },
    )
    if action_status == ACTION_STATUS_FAILED:
        raise ValueError(str(evidence.get("error") or "Downstream action failed."))
    return result
