from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db.models import Count
from django.utils import timezone

from risk.models import (
    CatchmentPopulationRecord,
    ExposureFeatureRecord,
    FacilityForecast,
    FacilityForecastRun,
    FacilityReadinessFreshness,
    FacilityReadinessIngestionRun,
    FacilityReadinessReview,
    FacilityReadinessSnapshot,
    FacilityReadinessSourceKind,
    FeatureDataset,
    IngestionRun,
    ModelRun,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureTruth,
    SourceDataUploadBatch,
    SurveillanceIngestionRun,
    SurveillanceRecord,
    SurveillanceTruthLevel,
)
from risk.source_data.phase0 import (
    INGESTION_FAMILY_FACILITY_READINESS,
    INGESTION_FAMILY_POPULATION_EXPOSURE,
    INGESTION_FAMILY_SURVEILLANCE,
)
from risk.source_data.registry import SourceDataFeedDefinition, source_data_feed_definitions


SOURCE_DATA_FRESHNESS_SCHEMA_VERSION = "source-data-freshness-v1"
SOURCE_DATA_OVERVIEW_SCHEMA_VERSION = "source-data-overview-v1"

STATUS_CURRENT = "current"
STATUS_DUE_SOON = "due_soon"
STATUS_STALE = "stale"
STATUS_MISSING = "missing"
STATUS_DEMO_BACKED = "demo_backed"
STATUS_FAILED = "failed"

TRUTH_API_BACKED = "api_backed"
TRUTH_CSV_BACKED = "csv_backed"
TRUTH_DEMO_BACKED = "demo_backed"
TRUTH_PROXY = "proxy"
TRUTH_FALLBACK = "fallback"
TRUTH_MISSING = "missing"
TRUTH_DERIVED = "derived"


CADENCE_DAYS = {
    "daily_where_available": 1,
    "weekly_minimum": 7,
    "one_off_then_corrections": 365,
    "annual_or_source_change": 365,
    "quarterly_or_source_change": 90,
    "quarterly_or_assessment_change": 90,
    "monthly_in_rainy_season_event_driven_after_floods": 30,
    "setup_then_facility_or_catchment_change": 180,
    "weekly_routine_daily_during_alerts": 7,
    "daily_after_source_updates": 1,
}
NON_CURRENT_POPULATION_EXPOSURE_FRESHNESS_STATES = {
    PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE,
    PopulationExposureFreshness.REPLAY_DIAGNOSTIC,
    PopulationExposureFreshness.REPLACEMENT_NOT_ACTIVATED,
}


@dataclass(frozen=True)
class FreshnessSource:
    key: str
    label: str
    domain: str
    status: str
    truth_state: str
    expected_cadence: str
    last_source_timestamp: str | None
    last_import_timestamp: str | None
    current_gap_days: int | None
    record_count: int
    recommended_action: str
    source_path: str
    feed_key: str = ""
    source_type: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "feed_key": self.feed_key,
            "label": self.label,
            "domain": self.domain,
            "source_type": self.source_type,
            "status": self.status,
            "truth_state": self.truth_state,
            "expected_cadence": self.expected_cadence,
            "last_source_timestamp": self.last_source_timestamp,
            "last_import_timestamp": self.last_import_timestamp,
            "current_gap_days": self.current_gap_days,
            "record_count": self.record_count,
            "recommended_action": self.recommended_action,
            "source_path": self.source_path,
        }


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _gap_days(value) -> int | None:
    if value is None:
        return None
    delta = timezone.now() - value
    return max(int(delta.total_seconds() // 86400), 0)


def _status_from_timestamp(
    *,
    timestamp,
    cadence: str,
    failed: bool = False,
    truth_state: str = TRUTH_MISSING,
) -> str:
    if failed:
        return STATUS_FAILED
    if timestamp is None:
        return STATUS_MISSING
    if truth_state in {TRUTH_DEMO_BACKED, TRUTH_FALLBACK, TRUTH_PROXY}:
        return STATUS_DEMO_BACKED

    cadence_days = CADENCE_DAYS.get(cadence, 30)
    age = timezone.now() - timestamp
    if age > timedelta(days=cadence_days * 2):
        return STATUS_STALE
    if age > timedelta(days=cadence_days):
        return STATUS_DUE_SOON
    return STATUS_CURRENT


def _recommendation(status: str, *, source_path: str, label: str) -> str:
    if status == STATUS_CURRENT:
        return "No immediate action required."
    if status == STATUS_DUE_SOON:
        return f"Refresh {label} at the next scheduled cadence."
    if status == STATUS_STALE:
        return f"Upload or refresh {label}; the current source is stale."
    if status == STATUS_FAILED:
        return f"Review the latest failed {label} import and re-run after correction."
    if status == STATUS_DEMO_BACKED:
        return f"Replace demo/proxy {label} with a production source when available."
    if source_path == "csv_upload":
        return f"Download the template and upload {label}."
    return f"Configure or run the source path for {label}."


def _latest_successful_upload(definition: SourceDataFeedDefinition) -> SourceDataUploadBatch | None:
    return (
        SourceDataUploadBatch.objects.filter(
            feed_key=definition.feed_key,
            status=SourceDataUploadBatch.STATUS_IMPORTED,
            import_status=SourceDataUploadBatch.IMPORT_IMPORTED,
        )
        .order_by("-source_timestamp", "-confirmed_at", "-created_at")
        .first()
    )


def _latest_upload(definition: SourceDataFeedDefinition) -> SourceDataUploadBatch | None:
    return SourceDataUploadBatch.objects.filter(feed_key=definition.feed_key).order_by("-created_at").first()


def _latest_domain_ingestion_run(definition: SourceDataFeedDefinition, *, successful_only: bool = False):
    statuses = None
    if definition.ingestion_family == INGESTION_FAMILY_SURVEILLANCE:
        queryset = SurveillanceIngestionRun.objects.filter(source_type=definition.source_type)
        statuses = [SurveillanceIngestionRun.STATUS_SUCCESS, SurveillanceIngestionRun.STATUS_PARTIAL]
    elif definition.ingestion_family == INGESTION_FAMILY_POPULATION_EXPOSURE:
        queryset = PopulationExposureIngestionRun.objects.filter(source_type=definition.source_type)
        statuses = [PopulationExposureIngestionRun.STATUS_SUCCESS, PopulationExposureIngestionRun.STATUS_PARTIAL]
    elif definition.ingestion_family == INGESTION_FAMILY_FACILITY_READINESS:
        queryset = FacilityReadinessIngestionRun.objects.filter(source_type=definition.source_type)
        statuses = [FacilityReadinessIngestionRun.STATUS_SUCCESS, FacilityReadinessIngestionRun.STATUS_PARTIAL]
    else:
        return None

    if successful_only:
        queryset = queryset.filter(status__in=statuses)
    return queryset.order_by("-source_timestamp", "-completed_at", "-started_at").first()


def _source_path_for_definition(definition: SourceDataFeedDefinition) -> str:
    if definition.requires_new_ingestion_path:
        return "new_ingestion_path_required"
    return "csv_upload"


def _feed_record_count(definition: SourceDataFeedDefinition) -> int:
    if definition.ingestion_family == INGESTION_FAMILY_SURVEILLANCE:
        return SurveillanceRecord.objects.filter(source__source_type=definition.source_type).count()
    if definition.ingestion_family == INGESTION_FAMILY_POPULATION_EXPOSURE:
        if definition.source_type == "population_baseline":
            return (
                PopulationBaselineRecord.objects.filter(source__source_type=definition.source_type)
                .exclude(freshness_state__in=NON_CURRENT_POPULATION_EXPOSURE_FRESHNESS_STATES)
                .count()
            )
        if definition.source_type == "catchment_mapping":
            return (
                CatchmentPopulationRecord.objects.filter(source__source_type=definition.source_type)
                .exclude(freshness_state__in=NON_CURRENT_POPULATION_EXPOSURE_FRESHNESS_STATES)
                .count()
            )
        return (
            ExposureFeatureRecord.objects.filter(source__source_type=definition.source_type)
            .exclude(freshness_state__in=NON_CURRENT_POPULATION_EXPOSURE_FRESHNESS_STATES)
            .count()
        )
    if definition.ingestion_family == INGESTION_FAMILY_FACILITY_READINESS:
        return FacilityReadinessSnapshot.objects.count()
    return 0


def _truth_state_for_feed(definition: SourceDataFeedDefinition, upload: SourceDataUploadBatch | None, run) -> str:
    if definition.ingestion_family == INGESTION_FAMILY_FACILITY_READINESS:
        snapshots = FacilityReadinessSnapshot.objects.all()
        if snapshots.filter(source_kind=FacilityReadinessSourceKind.SEEDED_DEMO).exists():
            return TRUTH_DEMO_BACKED
        if upload is not None or run or snapshots.exists():
            return TRUTH_CSV_BACKED
        return TRUTH_MISSING
    if upload is not None:
        return TRUTH_CSV_BACKED
    if run and run.fallback_used:
        return TRUTH_FALLBACK
    if definition.ingestion_family == INGESTION_FAMILY_SURVEILLANCE:
        records = SurveillanceRecord.objects.filter(source__source_type=definition.source_type)
        if records.filter(truth_level=SurveillanceTruthLevel.SEEDED_DEMO).exists():
            return TRUTH_DEMO_BACKED
        if records.filter(truth_level__in=[
            SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL,
            SurveillanceTruthLevel.FIELD_SIGNAL_ONLY,
        ]).exists():
            return TRUTH_PROXY
        if run or records.exists():
            return TRUTH_CSV_BACKED
    if definition.ingestion_family == INGESTION_FAMILY_POPULATION_EXPOSURE:
        if definition.source_type == "population_baseline":
            records = PopulationBaselineRecord.objects.filter(source__source_type=definition.source_type)
        elif definition.source_type == "catchment_mapping":
            records = CatchmentPopulationRecord.objects.filter(source__source_type=definition.source_type)
        else:
            records = ExposureFeatureRecord.objects.filter(source__source_type=definition.source_type)
        records = records.exclude(freshness_state__in=NON_CURRENT_POPULATION_EXPOSURE_FRESHNESS_STATES)
        if records.filter(truth_class=PopulationExposureTruth.SEEDED_DEMO).exists():
            return TRUTH_DEMO_BACKED
        if records.filter(truth_class=PopulationExposureTruth.DERIVED_EXPOSURE_PROXY).exists():
            return TRUTH_PROXY
        if records.exists():
            return TRUTH_CSV_BACKED
    return TRUTH_MISSING


def _feed_freshness(definition: SourceDataFeedDefinition) -> FreshnessSource:
    upload = _latest_successful_upload(definition)
    latest_any_upload = _latest_upload(definition)
    run = _latest_domain_ingestion_run(definition, successful_only=True)
    latest_any_run = _latest_domain_ingestion_run(definition)
    failed = bool(
        (latest_any_upload and latest_any_upload.status == SourceDataUploadBatch.STATUS_IMPORT_FAILED)
        or (
            latest_any_run
            and latest_any_run.status
            in {
                SurveillanceIngestionRun.STATUS_FAILED,
                PopulationExposureIngestionRun.STATUS_FAILED,
                FacilityReadinessIngestionRun.STATUS_FAILED,
            }
        )
    )
    last_source_timestamp = upload.source_timestamp if upload else (run.source_timestamp if run else None)
    last_import_timestamp = upload.confirmed_at if upload else ((run.completed_at or run.started_at) if run else None)
    truth_state = _truth_state_for_feed(definition, upload, run)

    if last_source_timestamp is None and truth_state in {TRUTH_DEMO_BACKED, TRUTH_PROXY}:
        if definition.ingestion_family == INGESTION_FAMILY_SURVEILLANCE:
            latest_record = SurveillanceRecord.objects.filter(source__source_type=definition.source_type).order_by("-created_at").first()
            last_source_timestamp = latest_record.created_at if latest_record else None
        elif definition.source_type == "population_baseline":
            latest_record = (
                PopulationBaselineRecord.objects.filter(source__source_type=definition.source_type)
                .exclude(freshness_state__in=NON_CURRENT_POPULATION_EXPOSURE_FRESHNESS_STATES)
                .order_by("-recorded_at", "-created_at")
                .first()
            )
            last_source_timestamp = latest_record.recorded_at if latest_record else None
        elif definition.source_type == "catchment_mapping":
            latest_record = (
                CatchmentPopulationRecord.objects.filter(source__source_type=definition.source_type)
                .exclude(freshness_state__in=NON_CURRENT_POPULATION_EXPOSURE_FRESHNESS_STATES)
                .order_by("-recorded_at", "-created_at")
                .first()
            )
            last_source_timestamp = latest_record.recorded_at if latest_record else None
        elif definition.ingestion_family == INGESTION_FAMILY_POPULATION_EXPOSURE:
            latest_record = (
                ExposureFeatureRecord.objects.filter(source__source_type=definition.source_type)
                .exclude(freshness_state__in=NON_CURRENT_POPULATION_EXPOSURE_FRESHNESS_STATES)
                .order_by("-recorded_at", "-created_at")
                .first()
            )
            last_source_timestamp = latest_record.recorded_at if latest_record else None
        elif definition.ingestion_family == INGESTION_FAMILY_FACILITY_READINESS:
            latest_record = FacilityReadinessSnapshot.objects.order_by("-reported_at", "-created_at").first()
            last_source_timestamp = latest_record.reported_at if latest_record else None

    if definition.ingestion_family == INGESTION_FAMILY_FACILITY_READINESS and last_source_timestamp is None:
        latest_record = FacilityReadinessSnapshot.objects.order_by("-reported_at", "-created_at").first()
        last_source_timestamp = latest_record.reported_at if latest_record else None
        last_import_timestamp = latest_record.created_at if latest_record and last_import_timestamp is None else last_import_timestamp

    status = _status_from_timestamp(
        timestamp=last_source_timestamp or last_import_timestamp,
        cadence=definition.cadence,
        failed=failed,
        truth_state=truth_state,
    )
    source_path = _source_path_for_definition(definition)
    return FreshnessSource(
        key=f"feed:{definition.feed_key}",
        feed_key=definition.feed_key,
        label=definition.label,
        domain=definition.domain,
        source_type=definition.source_type,
        status=status,
        truth_state=truth_state,
        expected_cadence=definition.cadence,
        last_source_timestamp=_iso(last_source_timestamp),
        last_import_timestamp=_iso(last_import_timestamp),
        current_gap_days=_gap_days(last_source_timestamp or last_import_timestamp),
        record_count=_feed_record_count(definition),
        recommended_action=_recommendation(status, source_path=source_path, label=definition.label),
        source_path=source_path,
    )


def _rainfall_freshness() -> FreshnessSource:
    run = IngestionRun.objects.filter(run_type=IngestionRun.RUN_TYPE_RAINFALL).order_by("-started_at").first()
    timestamp = run.source_timestamp if run else None
    truth_state = TRUTH_MISSING
    failed = False
    if run:
        failed = run.status == IngestionRun.STATUS_FAILED
        if run.fallback_used:
            truth_state = TRUTH_FALLBACK
        elif run.source_kind == IngestionRun.SOURCE_KIND_SEEDED:
            truth_state = TRUTH_DEMO_BACKED
        else:
            truth_state = TRUTH_API_BACKED
    status = _status_from_timestamp(timestamp=timestamp or (run.completed_at if run else None), cadence="daily_where_available", failed=failed, truth_state=truth_state)
    return FreshnessSource(
        key="system:rainfall",
        label="Rainfall forecast",
        domain="climate",
        status=status,
        truth_state=truth_state,
        expected_cadence="daily_where_available",
        last_source_timestamp=_iso(timestamp),
        last_import_timestamp=_iso(run.completed_at or run.started_at) if run else None,
        current_gap_days=_gap_days(timestamp or (run.completed_at if run else None)),
        record_count=run.records_loaded if run else 0,
        recommended_action=_recommendation(status, source_path="scheduled_api", label="rainfall forecast"),
        source_path="scheduled_api",
        source_type="rainfall",
    )


def _component_freshness() -> list[FreshnessSource]:
    latest_feature_dataset = FeatureDataset.objects.order_by("-created_at").first()
    latest_model_run = ModelRun.objects.order_by("-started_at").first()
    latest_facility_forecast_run = FacilityForecastRun.objects.order_by("-started_at").first()
    latest_facility_forecast = FacilityForecast.objects.order_by("-generated_at").first()
    latest_readiness_review = FacilityReadinessReview.objects.order_by("-created_at").first()
    latest_readiness_snapshot = FacilityReadinessSnapshot.objects.order_by("-reported_at", "-created_at").first()

    components = [
        (
            "system:feature_datasets",
            "Feature datasets",
            "model_features",
            latest_feature_dataset.created_at if latest_feature_dataset else None,
            latest_feature_dataset.row_count if latest_feature_dataset else 0,
            TRUTH_DEMO_BACKED if latest_feature_dataset and latest_feature_dataset.source_kind == FeatureDataset.SOURCE_KIND_SEEDED else TRUTH_DERIVED,
            "daily_after_source_updates",
            "builder",
            False,
        ),
        (
            "system:model_runs",
            "Model runs",
            "model_scoring",
            (latest_model_run.completed_at or latest_model_run.started_at) if latest_model_run else None,
            latest_model_run.inference_row_count if latest_model_run else 0,
            TRUTH_DERIVED,
            "daily_where_available",
            "scheduled_model_task",
            bool(latest_model_run and latest_model_run.status == ModelRun.STATUS_FAILED),
        ),
        (
            "system:facility_readiness",
            "Facility readiness snapshots",
            "facility_readiness",
            (latest_readiness_snapshot.reported_at if latest_readiness_snapshot else None)
            or (latest_readiness_review.created_at if latest_readiness_review else None),
            FacilityReadinessSnapshot.objects.count() or FacilityReadinessReview.objects.count(),
            TRUTH_DEMO_BACKED
            if latest_readiness_snapshot and latest_readiness_snapshot.source_kind == FacilityReadinessSourceKind.SEEDED_DEMO
            else TRUTH_CSV_BACKED
            if latest_readiness_snapshot or latest_readiness_review
            else TRUTH_MISSING,
            "weekly_routine_daily_during_alerts",
            "csv_upload" if latest_readiness_snapshot else "manual_workflow",
            bool(latest_readiness_snapshot and latest_readiness_snapshot.freshness_state == FacilityReadinessFreshness.REPLAY_DIAGNOSTIC),
        ),
        (
            "system:facility_forecasts",
            "Facility forecasts",
            "facility",
            (latest_facility_forecast.generated_at if latest_facility_forecast else None)
            or ((latest_facility_forecast_run.completed_at or latest_facility_forecast_run.started_at) if latest_facility_forecast_run else None),
            FacilityForecast.objects.count(),
            TRUTH_DERIVED,
            "daily_where_available",
            "scheduled_model_task",
            bool(latest_facility_forecast_run and latest_facility_forecast_run.status == FacilityForecastRun.STATUS_FAILED),
        ),
    ]
    payload: list[FreshnessSource] = []
    for key, label, domain, timestamp, count, truth_state, cadence, source_path, failed in components:
        status = _status_from_timestamp(timestamp=timestamp, cadence=cadence, failed=failed, truth_state=truth_state)
        payload.append(
            FreshnessSource(
                key=key,
                label=label,
                domain=domain,
                status=status,
                truth_state=truth_state if timestamp else TRUTH_MISSING,
                expected_cadence=cadence,
                last_source_timestamp=_iso(timestamp),
                last_import_timestamp=_iso(timestamp),
                current_gap_days=_gap_days(timestamp),
                record_count=count,
                recommended_action=_recommendation(status, source_path=source_path, label=label),
                source_path=source_path,
            )
        )
    return payload


def build_source_data_freshness_payload() -> dict[str, Any]:
    feed_sources = [_feed_freshness(definition) for definition in source_data_feed_definitions()]
    sources = [_rainfall_freshness(), *feed_sources, *_component_freshness()]
    status_counts = dict(
        SourceDataUploadBatch.objects.values("status").annotate(count=Count("id")).values_list("status", "count")
    )
    source_dicts = [source.as_dict() for source in sources]
    state_counts: dict[str, int] = {}
    truth_counts: dict[str, int] = {}
    for source in source_dicts:
        state_counts[source["status"]] = state_counts.get(source["status"], 0) + 1
        truth_counts[source["truth_state"]] = truth_counts.get(source["truth_state"], 0) + 1

    return {
        "schema_version": SOURCE_DATA_FRESHNESS_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "state_counts": state_counts,
        "truth_state_counts": truth_counts,
        "upload_status_counts": status_counts,
        "sources": source_dicts,
    }


def _recent_upload_record(batch: SourceDataUploadBatch) -> dict[str, Any]:
    return {
        "public_id": str(batch.public_id),
        "feed_key": batch.feed_key,
        "domain": batch.domain,
        "source_type": batch.source_type,
        "source_name": batch.source_name,
        "status": batch.status,
        "validation_status": batch.validation_status,
        "import_status": batch.import_status,
        "row_count": batch.row_count,
        "accepted_count": batch.accepted_count,
        "rejected_count": batch.rejected_count,
        "warning_count": batch.warning_count,
        "created_by_username": batch.created_by.username if batch.created_by_id else None,
        "confirmed_by_username": batch.confirmed_by.username if batch.confirmed_by_id else None,
        "created_at": _iso(batch.created_at),
        "confirmed_at": _iso(batch.confirmed_at),
    }


def build_source_data_overview_payload() -> dict[str, Any]:
    freshness = build_source_data_freshness_payload()
    feed_statuses = [source for source in freshness["sources"] if source["key"].startswith("feed:")]
    source_gaps = [
        {
            "feed_key": source["feed_key"],
            "label": source["label"],
            "status": source["status"],
            "truth_state": source["truth_state"],
            "recommended_action": source["recommended_action"],
            "template_url": f"/source-data/templates/{source['feed_key']}/",
        }
        for source in feed_statuses
        if source["status"] in {STATUS_MISSING, STATUS_STALE, STATUS_DEMO_BACKED, STATUS_FAILED}
    ]
    recent_uploads = [
        _recent_upload_record(batch)
        for batch in SourceDataUploadBatch.objects.select_related("created_by", "confirmed_by").order_by("-created_at")[:10]
    ]
    return {
        "schema_version": SOURCE_DATA_OVERVIEW_SCHEMA_VERSION,
        "generated_at": timezone.now().isoformat(),
        "freshness": freshness,
        "feed_statuses": feed_statuses,
        "source_gaps": source_gaps,
        "recent_uploads": recent_uploads,
        "source_matrix_reference": "docs/CCHIS_DATA_SOURCE_FEEDS.md",
    }
