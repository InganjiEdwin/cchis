from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from risk.models import (
    CatchmentPopulationRecord,
    ExposureFeatureRecord,
    HealthFacility,
    PopulationBaselineRecord,
    SyncQueue,
    TriageSession,
    Ward,
)


ETL_SCHEMA_VERSION = "cchis.etl.v1"


@dataclass(frozen=True)
class CanonicalClimateRecord:
    entity_type: str
    schema_version: str
    ward_public_id: str
    ward_name: str
    county: str
    source_name: str
    source_kind: str
    source_mode: str
    source_timestamp: str | None
    freshness_state: str
    rainfall_mm: float
    latitude: float | None
    longitude: float | None
    coordinate_source: str | None
    fallback_reason: str | None


@dataclass(frozen=True)
class CanonicalSurveillanceRecord:
    entity_type: str
    schema_version: str
    ward_public_id: str | None
    ward_name: str
    county: str
    source_name: str
    source_kind: str
    source_timestamp: str | None
    reporting_window_start: str | None
    reporting_window_end: str | None
    suspected_case_count: int | None
    confirmed_case_count: int | None
    outbreak_signal: bool | None


@dataclass(frozen=True)
class CanonicalFacilityReadinessRecord:
    entity_type: str
    schema_version: str
    facility_public_id: str | None
    facility_code: str | None
    facility_name: str
    ward_public_id: str | None
    ward_name: str | None
    readiness_state: str | None
    readiness_score: float | None
    staffing_signal: str | None
    stock_signal: str | None
    current_burden_signal: str | None
    source_name: str
    source_kind: str
    source_timestamp: str | None
    freshness_state: str


@dataclass(frozen=True)
class CanonicalCHVResponseRecord:
    entity_type: str
    schema_version: str
    ward_public_id: str | None
    ward_name: str
    chv_phone_number: str | None
    source_name: str
    source_kind: str
    source_timestamp: str | None
    symptom_signal: str | None
    suspected_case_count: int | None
    household_visit_count: int | None
    alert_response_state: str | None


@dataclass(frozen=True)
class CanonicalPopulationBaselineRecord:
    entity_type: str
    schema_version: str
    ward_public_id: str
    ward_name: str
    county: str
    recorded_at: str | None
    population_total: int
    population_under_five: int | None
    household_count_proxy: int | None
    truth_class: str
    source_name: str
    source_kind: str
    freshness_state: str
    release_version: str
    supersedes_record_ref: str | None
    revision_number: int


@dataclass(frozen=True)
class CanonicalExposureFeatureRecord:
    entity_type: str
    schema_version: str
    ward_public_id: str
    ward_name: str
    county: str
    recorded_at: str | None
    exposure_type: str
    exposure_value: float
    unit: str
    truth_class: str
    source_name: str
    aggregation_method: str
    spatial_resolution: str
    source_ref: str
    notes: str


@dataclass(frozen=True)
class CanonicalCatchmentPopulationRecord:
    entity_type: str
    schema_version: str
    facility_public_id: str
    facility_code: str
    facility_name: str
    recorded_at: str | None
    catchment_population_estimate: float
    catchment_under_five_estimate: float | None
    assigned_ward_ids: list[int]
    assignment_method: str
    truth_class: str
    source_ref: str


def _boolean_symptom_summary(*, diarrhea: bool, vomiting: bool, dehydration: bool, fever: bool) -> str | None:
    active = []
    if diarrhea:
        active.append("diarrhea")
    if vomiting:
        active.append("vomiting")
    if dehydration:
        active.append("dehydration")
    if fever:
        active.append("fever")
    return ",".join(active) if active else None


def climate_record_from_rainfall_observation(
    *,
    ward: Ward | None,
    ward_name: str,
    county: str,
    source_name: str,
    source_kind: str,
    source_mode: str,
    source_timestamp: str | None,
    freshness_state: str,
    rainfall_mm: float,
    latitude: float | None,
    longitude: float | None,
    coordinate_source: str | None,
    fallback_reason: str | None,
) -> CanonicalClimateRecord:
    return CanonicalClimateRecord(
        entity_type="climate_record",
        schema_version=ETL_SCHEMA_VERSION,
        ward_public_id=str(ward.public_id) if ward and ward.public_id else "",
        ward_name=ward.name if ward else ward_name,
        county=ward.county if ward else county,
        source_name=source_name,
        source_kind=source_kind,
        source_mode=source_mode,
        source_timestamp=source_timestamp,
        freshness_state=freshness_state,
        rainfall_mm=rainfall_mm,
        latitude=latitude,
        longitude=longitude,
        coordinate_source=coordinate_source,
        fallback_reason=fallback_reason,
    )


def facility_readiness_record_from_snapshot(
    *,
    facility: HealthFacility,
    source_name: str,
    source_kind: str,
    source_timestamp: str | None,
    freshness_state: str,
    readiness_state: str | None,
    readiness_score: float | None,
    staffing_signal: str | None,
    stock_signal: str | None,
    current_burden_signal: str | None,
) -> CanonicalFacilityReadinessRecord:
    return CanonicalFacilityReadinessRecord(
        entity_type="facility_readiness_record",
        schema_version=ETL_SCHEMA_VERSION,
        facility_public_id=str(facility.public_id) if facility.public_id else "",
        facility_code=facility.facility_code,
        facility_name=facility.name,
        ward_public_id=str(facility.ward.public_id) if facility.ward and facility.ward.public_id else "",
        ward_name=facility.ward.name if facility.ward_id else None,
        readiness_state=readiness_state,
        readiness_score=readiness_score,
        staffing_signal=staffing_signal,
        stock_signal=stock_signal,
        current_burden_signal=current_burden_signal,
        source_name=source_name,
        source_kind=source_kind,
        source_timestamp=source_timestamp,
        freshness_state=freshness_state,
    )


def facility_readiness_record_from_intelligence_snapshot(
    *,
    facility: HealthFacility,
    snapshot: dict[str, Any],
    source_name: str = "facility-intelligence-snapshot",
    source_kind: str = "LIVE",
) -> CanonicalFacilityReadinessRecord:
    readiness = snapshot.get("readiness", {})
    freshness = snapshot.get("freshness", {})
    updated_at = freshness.get("updated_at")
    return facility_readiness_record_from_snapshot(
        facility=facility,
        source_name=source_name,
        source_kind=source_kind,
        source_timestamp=updated_at.isoformat() if updated_at else None,
        freshness_state=readiness.get("freshness_state") or ("STALE" if freshness.get("is_stale") else "FRESH"),
        readiness_state=(readiness.get("surge_risk") or "").lower() if readiness.get("surge_risk") else None,
        readiness_score=float(readiness.get("staffing_percent", 0) or 0),
        staffing_signal=readiness.get("staffing_state"),
        stock_signal=readiness.get("ors_state"),
        current_burden_signal=readiness.get("surge_risk_label"),
    )


def surveillance_record_from_triage_session(
    session: TriageSession,
    *,
    source_name: str | None = None,
    source_kind: str = "LIVE",
) -> CanonicalSurveillanceRecord:
    suspected_case_count = 1 if (session.diarrhea or session.vomiting or session.dehydration) else 0
    outbreak_signal = bool(session.referral_needed or session.diarrhea)
    return CanonicalSurveillanceRecord(
        entity_type="surveillance_record",
        schema_version=ETL_SCHEMA_VERSION,
        ward_public_id=str(session.ward.public_id) if session.ward and session.ward.public_id else None,
        ward_name=session.ward.name if session.ward_id else "",
        county=session.ward.county if session.ward_id else "",
        source_name=source_name or f"triage-session:{session.channel.lower()}",
        source_kind=source_kind,
        source_timestamp=session.created_at.isoformat() if session.created_at else None,
        reporting_window_start=session.created_at.isoformat() if session.created_at else None,
        reporting_window_end=session.created_at.isoformat() if session.created_at else None,
        suspected_case_count=suspected_case_count,
        confirmed_case_count=None,
        outbreak_signal=outbreak_signal,
    )


def surveillance_record_from_sync_queue(
    sync_item: SyncQueue,
    *,
    source_name: str = "chv-sync-payload",
    source_kind: str = "LIVE",
) -> CanonicalSurveillanceRecord:
    payload = sync_item.payload or {}
    suspected_case_count = 1 if any(payload.get(flag, False) for flag in ["diarrhea", "vomiting", "dehydration"]) else 0
    outbreak_signal = bool(payload.get("diarrhea") or payload.get("dehydration"))
    return CanonicalSurveillanceRecord(
        entity_type="surveillance_record",
        schema_version=ETL_SCHEMA_VERSION,
        ward_public_id=str(sync_item.ward.public_id) if sync_item.ward and sync_item.ward.public_id else None,
        ward_name=sync_item.ward.name if sync_item.ward_id else "",
        county=sync_item.ward.county if sync_item.ward_id else "",
        source_name=source_name,
        source_kind=source_kind,
        source_timestamp=(sync_item.processed_at or sync_item.created_at).isoformat() if (sync_item.processed_at or sync_item.created_at) else None,
        reporting_window_start=sync_item.created_at.isoformat() if sync_item.created_at else None,
        reporting_window_end=(sync_item.processed_at or sync_item.created_at).isoformat() if (sync_item.processed_at or sync_item.created_at) else None,
        suspected_case_count=suspected_case_count,
        confirmed_case_count=None,
        outbreak_signal=outbreak_signal,
    )


def chv_response_record_from_triage_session(
    session: TriageSession,
    *,
    source_name: str | None = None,
    source_kind: str = "LIVE",
) -> CanonicalCHVResponseRecord:
    return CanonicalCHVResponseRecord(
        entity_type="chv_response_record",
        schema_version=ETL_SCHEMA_VERSION,
        ward_public_id=str(session.ward.public_id) if session.ward and session.ward.public_id else None,
        ward_name=session.ward.name if session.ward_id else "",
        chv_phone_number=session.phone_number or None,
        source_name=source_name or f"triage-session:{session.channel.lower()}",
        source_kind=source_kind,
        source_timestamp=session.created_at.isoformat() if session.created_at else None,
        symptom_signal=_boolean_symptom_summary(
            diarrhea=session.diarrhea,
            vomiting=session.vomiting,
            dehydration=session.dehydration,
            fever=session.fever,
        ),
        suspected_case_count=1 if (session.diarrhea or session.vomiting or session.dehydration) else 0,
        household_visit_count=1,
        alert_response_state="referral_needed" if session.referral_needed else "recorded",
    )


def chv_response_record_from_sync_queue(
    sync_item: SyncQueue,
    *,
    source_name: str = "chv-sync-payload",
    source_kind: str = "LIVE",
) -> CanonicalCHVResponseRecord:
    payload = sync_item.payload or {}
    return CanonicalCHVResponseRecord(
        entity_type="chv_response_record",
        schema_version=ETL_SCHEMA_VERSION,
        ward_public_id=str(sync_item.ward.public_id) if sync_item.ward and sync_item.ward.public_id else None,
        ward_name=sync_item.ward.name if sync_item.ward_id else "",
        chv_phone_number=sync_item.phone_number or None,
        source_name=source_name,
        source_kind=source_kind,
        source_timestamp=(sync_item.processed_at or sync_item.created_at).isoformat() if (sync_item.processed_at or sync_item.created_at) else None,
        symptom_signal=_boolean_symptom_summary(
            diarrhea=bool(payload.get("diarrhea", False)),
            vomiting=bool(payload.get("vomiting", False)),
            dehydration=bool(payload.get("dehydration", False)),
            fever=bool(payload.get("fever", False)),
        ),
        suspected_case_count=1 if any(payload.get(flag, False) for flag in ["diarrhea", "vomiting", "dehydration"]) else 0,
        household_visit_count=1,
        alert_response_state=sync_item.status.lower() if sync_item.status else None,
    )


def population_baseline_record_from_model(record: PopulationBaselineRecord) -> CanonicalPopulationBaselineRecord:
    return CanonicalPopulationBaselineRecord(
        entity_type="population_baseline_record",
        schema_version=ETL_SCHEMA_VERSION,
        ward_public_id=str(record.ward.public_id) if record.ward and record.ward.public_id else "",
        ward_name=record.ward.name if record.ward_id else "",
        county=record.ward.county if record.ward_id else "",
        recorded_at=record.recorded_at.isoformat() if record.recorded_at else None,
        population_total=record.population_total,
        population_under_five=record.population_under_five,
        household_count_proxy=record.household_count_proxy,
        truth_class=record.truth_class,
        source_name=record.source_name,
        source_kind=record.source_kind,
        freshness_state=record.freshness_state,
        release_version=record.release_version,
        supersedes_record_ref=record.supersedes_record_ref or None,
        revision_number=record.revision_number,
    )


def exposure_feature_record_from_model(record: ExposureFeatureRecord) -> CanonicalExposureFeatureRecord:
    return CanonicalExposureFeatureRecord(
        entity_type="exposure_feature_record",
        schema_version=ETL_SCHEMA_VERSION,
        ward_public_id=str(record.ward.public_id) if record.ward and record.ward.public_id else "",
        ward_name=record.ward.name if record.ward_id else "",
        county=record.ward.county if record.ward_id else "",
        recorded_at=record.recorded_at.isoformat() if record.recorded_at else None,
        exposure_type=record.exposure_type,
        exposure_value=record.exposure_value,
        unit=record.unit,
        truth_class=record.truth_class,
        source_name=record.source_name,
        aggregation_method=record.aggregation_method,
        spatial_resolution=record.spatial_resolution,
        source_ref=record.source_ref,
        notes=record.notes,
    )


def catchment_population_record_from_model(record: CatchmentPopulationRecord) -> CanonicalCatchmentPopulationRecord:
    return CanonicalCatchmentPopulationRecord(
        entity_type="catchment_population_record",
        schema_version=ETL_SCHEMA_VERSION,
        facility_public_id=str(record.facility.public_id) if record.facility and record.facility.public_id else "",
        facility_code=record.facility.facility_code if record.facility_id else "",
        facility_name=record.facility.name if record.facility_id else "",
        recorded_at=record.recorded_at.isoformat() if record.recorded_at else None,
        catchment_population_estimate=record.catchment_population_estimate,
        catchment_under_five_estimate=record.catchment_under_five_estimate,
        assigned_ward_ids=record.assigned_ward_ids or [],
        assignment_method=record.assignment_method,
        truth_class=record.truth_class,
        source_ref=record.source_ref,
    )


def canonical_record_envelope(record: Any) -> dict[str, Any]:
    return asdict(record)
