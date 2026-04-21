from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .models import Alert, HealthFacility, RiskScore, Ward


@dataclass(frozen=True)
class CanonicalWardRef:
    entity_type: str
    public_id: str
    ward_code: str
    name: str
    county: str
    sub_county: str
    is_active: bool


@dataclass(frozen=True)
class CanonicalFacilityRef:
    entity_type: str
    public_id: str
    facility_code: str
    name: str
    ward_public_id: str
    ward_code: str
    facility_type: str
    ownership: str
    level: str
    is_active: bool


@dataclass(frozen=True)
class CanonicalRiskScoreRecord:
    entity_type: str
    ward_public_id: str
    ward_code: str
    model_run_id: int | None
    model_version: str
    risk_level: str
    score: float
    predicted_cases: int
    rainfall_mm: float
    flood_indicator: float
    source: str
    generated_at: str


@dataclass(frozen=True)
class CanonicalAlertRecord:
    entity_type: str
    ward_public_id: str
    ward_code: str
    risk_score_id: int | None
    channel: str
    recipient: str
    message: str
    status: str
    delivery_backend: str
    attempt_count: int
    max_attempts: int
    external_id: str
    created_at: str
    sent_at: str | None


def ward_to_canonical_ref(ward: Ward) -> CanonicalWardRef:
    return CanonicalWardRef(
        entity_type="ward",
        public_id=str(ward.public_id),
        ward_code=ward.ward_code,
        name=ward.name,
        county=ward.county,
        sub_county=ward.sub_county,
        is_active=ward.is_active,
    )


def facility_to_canonical_ref(facility: HealthFacility) -> CanonicalFacilityRef:
    return CanonicalFacilityRef(
        entity_type="health_facility",
        public_id=str(facility.public_id),
        facility_code=facility.facility_code,
        name=facility.name,
        ward_public_id=str(facility.ward.public_id),
        ward_code=facility.ward.ward_code,
        facility_type=facility.facility_type,
        ownership=facility.ownership,
        level=facility.level,
        is_active=facility.is_active,
    )


def riskscore_to_canonical_record(risk_score: RiskScore) -> CanonicalRiskScoreRecord:
    return CanonicalRiskScoreRecord(
        entity_type="risk_score",
        ward_public_id=str(risk_score.ward.public_id),
        ward_code=risk_score.ward.ward_code,
        model_run_id=risk_score.model_run_id,
        model_version=risk_score.model_version,
        risk_level=risk_score.risk_level,
        score=risk_score.score,
        predicted_cases=risk_score.predicted_cases,
        rainfall_mm=risk_score.rainfall_mm,
        flood_indicator=risk_score.flood_indicator,
        source=risk_score.source,
        generated_at=risk_score.generated_at.isoformat(),
    )


def alert_to_canonical_record(alert: Alert) -> CanonicalAlertRecord:
    return CanonicalAlertRecord(
        entity_type="alert",
        ward_public_id=str(alert.ward.public_id),
        ward_code=alert.ward.ward_code,
        risk_score_id=alert.risk_score_id,
        channel=alert.channel,
        recipient=alert.recipient,
        message=alert.message,
        status=alert.status,
        delivery_backend=alert.delivery_backend,
        attempt_count=alert.attempt_count,
        max_attempts=alert.max_attempts,
        external_id=alert.external_id,
        created_at=alert.created_at.isoformat(),
        sent_at=alert.sent_at.isoformat() if alert.sent_at else None,
    )


def canonical_export_envelope(
    *,
    source_system: str,
    entity_name: str,
    record: CanonicalWardRef | CanonicalFacilityRef | CanonicalRiskScoreRecord | CanonicalAlertRecord,
) -> dict[str, Any]:
    return {
        "source_system": source_system,
        "entity_name": entity_name,
        "schema_version": "cchis.v1",
        "record": asdict(record),
    }
