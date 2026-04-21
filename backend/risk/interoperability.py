from __future__ import annotations

from dataclasses import dataclass

from .canonical import (
    CanonicalFacilityRef,
    CanonicalRiskScoreRecord,
    CanonicalWardRef,
)


@dataclass(frozen=True)
class LocationCrosswalkKey:
    entity_type: str
    cchis_public_id: str
    local_reference_code: str


def ward_location_crosswalk_key(ward: CanonicalWardRef) -> LocationCrosswalkKey:
    return LocationCrosswalkKey(
        entity_type="ward",
        cchis_public_id=ward.public_id,
        local_reference_code=ward.ward_code,
    )


def facility_location_crosswalk_key(facility: CanonicalFacilityRef) -> LocationCrosswalkKey:
    return LocationCrosswalkKey(
        entity_type="health_facility",
        cchis_public_id=facility.public_id,
        local_reference_code=facility.facility_code,
    )


def build_dhis2_org_unit_mapping_stub(
    *,
    source_system: str,
    location_key: LocationCrosswalkKey,
    external_org_unit_id: str,
) -> dict[str, str]:
    return {
        "source_system": source_system,
        "entity_type": location_key.entity_type,
        "cchis_public_id": location_key.cchis_public_id,
        "local_reference_code": location_key.local_reference_code,
        "external_org_unit_id": external_org_unit_id,
    }


def build_dhis2_risk_score_export_stub(
    risk_score: CanonicalRiskScoreRecord,
    *,
    external_org_unit_id: str,
    data_element_id: str,
) -> dict[str, object]:
    return {
        "dataSet": "TBD",
        "completeDate": risk_score.generated_at[:10],
        "orgUnit": external_org_unit_id,
        "dataValues": [
            {
                "dataElement": data_element_id,
                "value": risk_score.score,
            },
            {
                "dataElement": f"{data_element_id}_risk_level",
                "value": risk_score.risk_level,
            },
            {
                "dataElement": f"{data_element_id}_predicted_cases",
                "value": risk_score.predicted_cases,
            },
        ],
        "metadata": {
            "source_system": "cchis",
            "schema_version": "cchis.v1",
            "ward_public_id": risk_score.ward_public_id,
            "ward_code": risk_score.ward_code,
            "model_version": risk_score.model_version,
        },
    }
