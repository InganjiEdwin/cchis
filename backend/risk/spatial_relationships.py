from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from itertools import combinations

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from risk.climate_records import enrich_rainfall_result_with_climate_contract
from risk.models import (
    CatchmentPopulationRecord,
    ExposureFeatureRecord,
    FeatureDataset,
    FeatureDatasetRow,
    FacilityCatchment,
    FacilityCatchmentMethod,
    FacilityCatchmentSourceKind,
    FacilityForecast,
    HealthFacility,
    ClimateRecord,
    ClimateRecordType,
    IngestionRun,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureSource,
    SurveillanceRecord,
    Ward,
    WardGeometryDatasetVersion,
    WardGeometryFeature,
    WardSpatialRelationship,
    WardSpatialRelationshipSource,
    WardSpatialRelationshipType,
)


SPATIAL_SOURCE_AUDIT_SCHEMA_VERSION = "spatial-source-audit-v1"
WARD_SPATIAL_GRAPH_SCHEMA_VERSION = "ward-spatial-relationship-graph-v1"
FACILITY_CATCHMENT_SCHEMA_VERSION = "facility-catchment-approximation-v1"
SPATIAL_GRAPH_AUDIT_SCHEMA_VERSION = "spatial-graph-monitoring-audit-v1"
SPATIAL_GRAPH_AUDIT_NAME = "spatial_relationship_catchment_graph_phase_5"
LEAD_TIME_FEATURE_SCHEMA_VERSION_FOR_SPATIAL_AUDIT = "lead-time-feature-v1"
DEFAULT_GEOMETRY_DATASET_SLUG = "migori-ward-boundaries"
DEFAULT_SPATIAL_COUNTY = "Migori"
DEFAULT_DISTANCE_UNIT = "source_crs_degrees"
STALE_POPULATION_EXPOSURE_STATES = {
    PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE,
    PopulationExposureFreshness.REPLAY_DIAGNOSTIC,
    PopulationExposureFreshness.REPLACEMENT_NOT_ACTIVATED,
}
SPATIAL_AUDIT_NEIGHBOR_RELATIONSHIP_TYPES = {
    WardSpatialRelationshipType.ADJACENT,
    WardSpatialRelationshipType.NEARBY,
    WardSpatialRelationshipType.UPSTREAM,
    WardSpatialRelationshipType.SAME_FACILITY_CATCHMENT,
    WardSpatialRelationshipType.MANUAL_PUBLIC_HEALTH_LINK,
}


def _active_geometry_version(dataset_slug: str) -> WardGeometryDatasetVersion | None:
    return (
        WardGeometryDatasetVersion.objects.select_related("dataset")
        .filter(dataset__slug=dataset_slug, is_active=True)
        .order_by("-activated_at", "-id")
        .first()
    )


def _version_lineage(version: WardGeometryDatasetVersion | None) -> dict:
    if version is None:
        return {
            "dataset_slug": "",
            "version_label": "",
            "available": False,
        }
    return {
        "dataset_slug": version.dataset.slug,
        "dataset_name": version.dataset.name,
        "version_label": version.version_label,
        "geometry_dataset_version_id": version.id,
        "source_name": version.source_name,
        "source_url": version.source_url,
        "source_license": version.source_license,
        "source_crs": version.source_crs,
        "source_checksum": version.source_checksum,
        "activated_at": version.activated_at.isoformat() if version.activated_at else None,
        "available": True,
    }


def _question(
    *,
    question_id: str,
    status: str,
    answer: str,
    evidence: dict,
    gaps: list[str] | None = None,
    assumptions: list[str] | None = None,
) -> dict:
    return {
        "id": question_id,
        "status": status,
        "answer": answer,
        "evidence": evidence,
        "gaps": gaps or [],
        "assumptions": assumptions or [],
    }


def _overall_status(questions: list[dict]) -> str:
    statuses = {question["status"] for question in questions}
    if "fail" in statuses:
        return "fail"
    if "warning" in statuses:
        return "warning"
    return "pass"


def _safe_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_spatial_audit_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _parse_spatial_audit_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _audit_issue(
    *,
    check_id: str,
    severity: str,
    record_type: str,
    record_id,
    message: str,
    evidence: dict,
) -> dict:
    return {
        "check_id": check_id,
        "severity": severity,
        "record_type": record_type,
        "record_id": str(record_id),
        "message": message,
        "evidence": evidence,
    }


def _feature_row_audit_issue(row: FeatureDatasetRow, *, check_id: str, severity: str, message: str) -> dict:
    values = _as_dict(row.feature_values)
    return _audit_issue(
        check_id=check_id,
        severity=severity,
        record_type="risk.FeatureDatasetRow",
        record_id=row.id,
        message=message,
        evidence={
            "dataset_ref": row.dataset.dataset_ref,
            "ward_id": row.ward_id,
            "ward_name": row.ward_name_snapshot,
            "prediction_date": values.get("prediction_date"),
            "source_cutoff_timestamp": values.get("source_cutoff_timestamp"),
        },
    )


def _audit_check(
    *,
    check_id: str,
    title: str,
    issues: list[dict],
    scanned_count: int,
    empty_warning: str,
) -> dict:
    fail_count = sum(1 for issue in issues if issue.get("severity") == "fail")
    warning_count = sum(1 for issue in issues if issue.get("severity") == "warning")
    if fail_count:
        status = "fail"
    elif warning_count or scanned_count == 0:
        status = "warning"
    else:
        status = "pass"
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "scanned_count": scanned_count,
        "issue_count": len(issues),
        "fail_count": fail_count,
        "warning_count": warning_count,
        "summary": empty_warning if scanned_count == 0 else "Check passed." if status == "pass" else "Issues found.",
        "issues": issues[:50],
    }


def _geometry_is_usable(geometry) -> bool:
    if geometry is None:
        return False
    if getattr(geometry, "empty", False):
        return False
    return bool(getattr(geometry, "valid", True))


def _centroid_for_feature(feature: WardGeometryFeature):
    if feature.centroid is not None:
        return feature.centroid
    if feature.geometry is not None:
        return feature.geometry.centroid
    return None


def _centroid_distance(left: WardGeometryFeature, right: WardGeometryFeature) -> float | None:
    left_centroid = _centroid_for_feature(left)
    right_centroid = _centroid_for_feature(right)
    if left_centroid is None or right_centroid is None:
        return None
    return float(left_centroid.distance(right_centroid))


def _shared_boundary_length(left: WardGeometryFeature, right: WardGeometryFeature) -> float:
    if not _geometry_is_usable(left.geometry) or not _geometry_is_usable(right.geometry):
        return 0.0
    intersection = left.geometry.boundary.intersection(right.geometry.boundary)
    return float(intersection.length or 0.0)


def _candidate_adjacency_summary(
    features: list[WardGeometryFeature],
    *,
    min_shared_boundary_length: float = 0.0,
) -> dict:
    adjacency_by_ward_id: dict[int, set[int]] = defaultdict(set)
    pair_count = 0
    skipped_pairs = 0
    errors = []

    for left, right in combinations(features, 2):
        try:
            shared_boundary_length = _shared_boundary_length(left, right)
        except Exception as error:  # GEOS errors should be surfaced as data-quality gaps.
            skipped_pairs += 1
            errors.append(
                {
                    "source_ward_id": left.ward_id,
                    "target_ward_id": right.ward_id,
                    "source_ward_name": left.ward.name,
                    "target_ward_name": right.ward.name,
                    "error": str(error),
                }
            )
            continue
        if shared_boundary_length > min_shared_boundary_length:
            pair_count += 1
            adjacency_by_ward_id[left.ward_id].add(right.ward_id)
            adjacency_by_ward_id[right.ward_id].add(left.ward_id)

    isolated_ward_names = sorted(
        feature.ward.name
        for feature in features
        if _geometry_is_usable(feature.geometry) and feature.ward_id not in adjacency_by_ward_id
    )
    return {
        "undirected_adjacent_pair_count": pair_count,
        "directed_adjacent_edge_count": pair_count * 2,
        "isolated_ward_names": isolated_ward_names,
        "skipped_pair_count": skipped_pairs,
        "pair_errors": errors[:20],
    }


def _geometry_features_for_version(
    version: WardGeometryDatasetVersion,
    *,
    county: str,
    active_only: bool = True,
) -> list[WardGeometryFeature]:
    queryset = (
        WardGeometryFeature.objects.select_related("ward", "dataset_version", "dataset_version__dataset")
        .filter(dataset_version=version, ward__county__iexact=county)
        .order_by("ward__name", "id")
    )
    if active_only:
        queryset = queryset.filter(ward__is_active=True)
    return list(queryset)


def _ref_ids(value: list, *, prefix: str) -> tuple[list[int], list[str]]:
    ids = []
    malformed = []
    expected_prefix = f"{prefix}:"
    for item in value:
        text = str(item or "")
        if not text.startswith(expected_prefix):
            malformed.append(text)
            continue
        parsed = _safe_int(text[len(expected_prefix):])
        if parsed is None:
            malformed.append(text)
            continue
        ids.append(parsed)
    return ids, malformed


def _lead_time_feature_rows_for_spatial_audit(
    *,
    feature_dataset_ref: str | None = None,
    row_limit: int | None = None,
) -> tuple[list[FeatureDatasetRow], list[str]]:
    datasets = FeatureDataset.objects.filter(schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION_FOR_SPATIAL_AUDIT)
    if feature_dataset_ref:
        datasets = datasets.filter(dataset_ref=feature_dataset_ref)
    dataset_refs = list(datasets.order_by("-created_at", "-id").values_list("dataset_ref", flat=True))
    if not dataset_refs:
        return [], []

    rows = (
        FeatureDatasetRow.objects.select_related("dataset", "ward")
        .filter(dataset__dataset_ref__in=dataset_refs)
        .order_by("dataset__created_at", "dataset_id", "id")
    )
    if row_limit is not None and row_limit > 0:
        rows = rows[:row_limit]
    return list(rows), dataset_refs


def _active_ward_geometry_audit_issues(
    *,
    active_wards: list[Ward],
    features_by_ward_id: dict[int, WardGeometryFeature],
    version: WardGeometryDatasetVersion | None,
) -> list[dict]:
    issues = []
    for ward in active_wards:
        feature = features_by_ward_id.get(ward.id)
        active_feature_geometry_usable = bool(feature is not None and _geometry_is_usable(feature.geometry))
        canonical_boundary_usable = _geometry_is_usable(ward.boundary)
        if active_feature_geometry_usable:
            continue
        issues.append(
            _audit_issue(
                check_id="active_wards_have_geometry",
                severity="fail",
                record_type="risk.Ward",
                record_id=ward.id,
                message="Active ward is missing usable geometry in the active spatial dataset version.",
                evidence={
                    "ward_id": ward.id,
                    "ward_name": ward.name,
                    "ward_code": ward.ward_code,
                    "county": ward.county,
                    "has_active_geometry_feature": feature is not None,
                    "active_feature_geometry_usable": active_feature_geometry_usable,
                    "canonical_boundary_usable": canonical_boundary_usable,
                    "geometry_dataset_version_id": version.id if version else None,
                    "geometry_dataset_version_label": version.version_label if version else "",
                },
            )
        )
    return issues


def _active_geometry_version_audit_issues(
    *,
    version: WardGeometryDatasetVersion | None,
    dataset_slug: str,
) -> list[dict]:
    if version is not None:
        return []
    return [
        _audit_issue(
            check_id="active_geometry_dataset_version_available",
            severity="fail",
            record_type="risk.WardGeometryDatasetVersion",
            record_id=dataset_slug,
            message="No active geometry dataset version is available for spatial graph audit.",
            evidence={
                "dataset_slug": dataset_slug,
                "required_for": [
                    "ward spatial relationship graph",
                    "active-version facility catchments",
                    "spatial feature lineage validation",
                ],
            },
        )
    ]


def _isolated_ward_audit_issues(
    *,
    active_wards: list[Ward],
    features_by_ward_id: dict[int, WardGeometryFeature],
    version: WardGeometryDatasetVersion | None,
) -> list[dict]:
    active_ward_ids = {ward.id for ward in active_wards}
    relationships = WardSpatialRelationship.objects.filter(
        source_ward_id__in=active_ward_ids,
        target_ward__is_active=True,
        relationship_type__in=SPATIAL_AUDIT_NEIGHBOR_RELATIONSHIP_TYPES,
    )
    if version is not None:
        relationships = relationships.filter(geometry_dataset_version=version)
    neighbor_source_ids = set(relationships.values_list("source_ward_id", flat=True))
    issues = []
    for ward in active_wards:
        feature = features_by_ward_id.get(ward.id)
        if feature is None or not _geometry_is_usable(feature.geometry):
            continue
        if ward.id in neighbor_source_ids:
            continue
        issues.append(
            _audit_issue(
                check_id="active_wards_have_spatial_neighbors",
                severity="fail",
                record_type="risk.Ward",
                record_id=ward.id,
                message="Active ward has usable geometry but no outgoing spatial neighbor relationships.",
                evidence={
                    "ward_id": ward.id,
                    "ward_name": ward.name,
                    "ward_code": ward.ward_code,
                    "county": ward.county,
                    "relationship_types_considered": sorted(SPATIAL_AUDIT_NEIGHBOR_RELATIONSHIP_TYPES),
                },
            )
        )
    return issues


def _facility_without_catchment_audit_issues(
    *,
    county: str,
    version: WardGeometryDatasetVersion | None,
) -> tuple[list[dict], int]:
    active_facilities = list(
        HealthFacility.objects.select_related("ward")
        .filter(is_active=True, ward__county__iexact=county)
        .order_by("ward__name", "name", "id")
    )
    catchments = FacilityCatchment.objects.filter(facility_id__in=[facility.id for facility in active_facilities])
    if version is not None:
        catchments = catchments.filter(geometry_dataset_version=version)
    facility_ids_with_catchments = set(
        catchments.values_list(
            "facility_id",
            flat=True,
        )
    )
    issues = []
    for facility in active_facilities:
        if facility.id in facility_ids_with_catchments:
            continue
        issues.append(
            _audit_issue(
                check_id="active_facilities_have_catchments",
                severity="fail",
                record_type="risk.HealthFacility",
                record_id=facility.id,
                message="Active facility has no FacilityCatchment record.",
                evidence={
                    "facility_id": facility.id,
                    "facility_name": facility.name,
                    "facility_code": facility.facility_code,
                    "ward_id": facility.ward_id,
                    "ward_name": facility.ward.name,
                    "has_coordinates": facility.point is not None,
                },
            )
        )
    return issues, len(active_facilities)


def _catchment_population_audit_issues(
    *,
    county: str,
    version: WardGeometryDatasetVersion | None,
) -> tuple[list[dict], int]:
    catchments_queryset = (
        FacilityCatchment.objects.select_related("facility", "primary_ward")
        .prefetch_related("covered_wards")
        .filter(facility__ward__county__iexact=county)
        .order_by("facility__name", "id")
    )
    if version is not None:
        catchments_queryset = catchments_queryset.filter(geometry_dataset_version=version)
    catchments = list(catchments_queryset)
    issues = []
    for catchment in catchments:
        covered_wards = list(catchment.covered_wards.all())
        population = catchment.population_estimate
        messages = []
        if not covered_wards:
            messages.append("covered wards are missing")
        if population is None:
            messages.append("population estimate is missing")
        elif population <= 0:
            messages.append("population estimate is non-positive")
        if not messages:
            continue
        issues.append(
            _audit_issue(
                check_id="catchment_population_estimates_plausible",
                severity="fail",
                record_type="risk.FacilityCatchment",
                record_id=catchment.id,
                message="Facility catchment has impossible or missing population context: " + "; ".join(messages),
                evidence={
                    "catchment_id": catchment.id,
                    "facility_id": catchment.facility_id,
                    "facility_name": catchment.facility.name,
                    "primary_ward_id": catchment.primary_ward_id,
                    "primary_ward_name": catchment.primary_ward.name,
                    "covered_ward_count": len(covered_wards),
                    "covered_ward_names": [ward.name for ward in covered_wards],
                    "population_estimate": population,
                    "population_estimate_source": _as_dict(catchment.lineage_metadata).get(
                        "population_estimate_source",
                        {},
                    ),
                },
            )
        )
    return issues, len(catchments)


def _approximate_spatial_label_audit_issues(
    *,
    county: str,
    version: WardGeometryDatasetVersion | None,
) -> tuple[list[dict], int]:
    catchments_queryset = (
        FacilityCatchment.objects.select_related("facility", "primary_ward")
        .filter(facility__ward__county__iexact=county)
        .order_by("facility__name", "id")
    )
    if version is not None:
        catchments_queryset = catchments_queryset.filter(geometry_dataset_version=version)
    catchments = list(catchments_queryset)

    same_facility_edges_queryset = (
        WardSpatialRelationship.objects.select_related("source_ward", "target_ward")
        .filter(
            source_ward__county__iexact=county,
            relationship_type=WardSpatialRelationshipType.SAME_FACILITY_CATCHMENT,
            generation_method=WardSpatialRelationshipSource.DERIVED_FACILITY_CATCHMENT,
        )
        .order_by("source_ward__name", "target_ward__name", "id")
    )
    if version is not None:
        same_facility_edges_queryset = same_facility_edges_queryset.filter(geometry_dataset_version=version)
    same_facility_edges = list(same_facility_edges_queryset)
    issues = []
    for catchment in catchments:
        lineage = _as_dict(catchment.lineage_metadata)
        should_be_labelled_approximate = (
            catchment.source_kind != FacilityCatchmentSourceKind.EXTERNALLY_VERIFIED
            or catchment.catchment_method != FacilityCatchmentMethod.EXTERNALLY_VERIFIED
        )
        if should_be_labelled_approximate and not catchment.is_approximate:
            issues.append(
                _audit_issue(
                    check_id="approximate_spatial_relationships_labelled_honestly",
                    severity="fail",
                    record_type="risk.FacilityCatchment",
                    record_id=catchment.id,
                    message="Facility catchment is not externally verified but is not labelled approximate.",
                    evidence={
                        "catchment_id": catchment.id,
                        "facility_name": catchment.facility.name,
                        "catchment_method": catchment.catchment_method,
                        "source_kind": catchment.source_kind,
                        "is_approximate": catchment.is_approximate,
                    },
                )
            )
        if catchment.is_approximate and not lineage.get("approximation_notice"):
            issues.append(
                _audit_issue(
                    check_id="approximate_spatial_relationships_labelled_honestly",
                    severity="fail",
                    record_type="risk.FacilityCatchment",
                    record_id=catchment.id,
                    message="Approximate facility catchment is missing an approximation notice for frontend display.",
                    evidence={
                        "catchment_id": catchment.id,
                        "facility_name": catchment.facility.name,
                        "catchment_method": catchment.catchment_method,
                        "source_kind": catchment.source_kind,
                        "is_approximate": catchment.is_approximate,
                    },
                )
            )
        claims_external_verification = (
            catchment.source_kind == FacilityCatchmentSourceKind.EXTERNALLY_VERIFIED
            or catchment.catchment_method == FacilityCatchmentMethod.EXTERNALLY_VERIFIED
            or not catchment.is_approximate
        )
        has_external_validation_lineage = bool(
            lineage.get("source_catchment_record") and lineage.get("verification_notice")
        )
        if claims_external_verification and not has_external_validation_lineage:
            issues.append(
                _audit_issue(
                    check_id="approximate_spatial_relationships_labelled_honestly",
                    severity="fail",
                    record_type="risk.FacilityCatchment",
                    record_id=catchment.id,
                    message="Facility catchment claims external verification without source validation lineage.",
                    evidence={
                        "catchment_id": catchment.id,
                        "facility_name": catchment.facility.name,
                        "catchment_method": catchment.catchment_method,
                        "source_kind": catchment.source_kind,
                        "is_approximate": catchment.is_approximate,
                        "has_source_catchment_record_lineage": bool(lineage.get("source_catchment_record")),
                        "has_verification_notice": bool(lineage.get("verification_notice")),
                    },
                )
            )

    for relationship in same_facility_edges:
        lineage = _as_dict(relationship.lineage_metadata)
        if lineage.get("approximation_notice"):
            continue
        issues.append(
            _audit_issue(
                check_id="approximate_spatial_relationships_labelled_honestly",
                severity="fail",
                record_type="risk.WardSpatialRelationship",
                record_id=relationship.id,
                message="Same-facility-catchment relationship is missing an approximation notice.",
                evidence={
                    "relationship_id": relationship.id,
                    "source_ward_id": relationship.source_ward_id,
                    "source_ward_name": relationship.source_ward.name,
                    "target_ward_id": relationship.target_ward_id,
                    "target_ward_name": relationship.target_ward.name,
                    "relationship_type": relationship.relationship_type,
                    "generation_method": relationship.generation_method,
                },
            )
        )
    return issues, len(catchments) + len(same_facility_edges)


def _spatial_feature_uses_relationship_graph(values: dict) -> bool:
    relationship_types = _as_list(values.get("spatial_neighbor_relationship_types"))
    return bool(
        (_safe_int(values.get("spatial_neighbor_ward_count")) or 0) > 0
        or (_safe_int(values.get("neighboring_high_risk_ward_count")) or 0) > 0
        or values.get("distance_to_nearest_high_risk_ward") is not None
        or relationship_types
        or str(values.get("upstream_or_neighboring_ward_signal_source") or "").startswith(
            "ward_spatial_relationship_graph"
        )
    )


def _neighboring_climate_signal_present(values: dict, neighbor_climate_lineage: dict) -> bool:
    # A ward can have spatial neighbors without having observed neighbor climate inputs.
    # Treat climate as present only when an observation/result was actually used.
    return bool(
        (_safe_int(neighbor_climate_lineage.get("neighbor_wards_with_observed_rainfall")) or 0) > 0
        or _as_list(neighbor_climate_lineage.get("source_record_refs"))
        or values.get("neighboring_rainfall_anomaly") not in (None, 0, 0.0)
    )


def _spatial_feature_lineage_audit_issues(
    rows: list[FeatureDatasetRow],
    *,
    version: WardGeometryDatasetVersion | None,
) -> list[dict]:
    issues = []
    for row in rows:
        values = _as_dict(row.feature_values)
        source_lineage = _as_dict(values.get("source_lineage"))
        source_cutoff = _parse_spatial_audit_datetime(values.get("source_cutoff_timestamp"))
        spatial_lineage = _as_dict(source_lineage.get("spatial_relationships")) or _as_dict(
            source_lineage.get("spatial_features")
        )
        neighbor_lineage = _as_dict(source_lineage.get("neighboring_surveillance")) or _as_dict(
            spatial_lineage.get("neighbor_surveillance")
        )
        neighbor_climate_lineage = _as_dict(source_lineage.get("neighboring_climate")) or _as_dict(
            spatial_lineage.get("neighbor_climate")
        )
        relationship_lineage = _as_dict(spatial_lineage.get("relationships"))
        relationship_refs = _as_list(relationship_lineage.get("relationship_refs"))
        relationship_count = _safe_int(relationship_lineage.get("relationship_count")) or 0
        neighboring_record_count = (
            _safe_int(values.get("neighboring_surveillance_record_count"))
            or _safe_int(neighbor_lineage.get("record_count"))
            or 0
        )
        active_outbreak_count = _safe_int(values.get("neighboring_active_outbreak_label_count")) or 0
        relationship_lineage_required = bool(
            _spatial_feature_uses_relationship_graph(values)
            or neighboring_record_count > 0
            or active_outbreak_count > 0
            or _neighboring_climate_signal_present(values, neighbor_climate_lineage)
        )
        if relationship_lineage_required and (relationship_count <= 0 or not relationship_refs):
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_features_have_source_relationship_lineage",
                    severity="fail",
                    message="Spatial neighbor, surveillance, or climate feature is present without source relationship refs.",
                )
            )
        if relationship_refs:
            relationship_ids, malformed_refs = _ref_ids(relationship_refs, prefix="ward_spatial_relationship")
            if malformed_refs:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message="Spatial relationship lineage contains malformed refs: " + ", ".join(malformed_refs[:5]),
                    )
                )
            relationships = {
                relationship.id: relationship
                for relationship in WardSpatialRelationship.objects.filter(id__in=relationship_ids).select_related(
                    "geometry_dataset_version",
                    "source_ward",
                    "target_ward",
                )
            }
            if relationship_count > len(set(relationship_ids)):
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message=(
                            "Spatial relationship lineage count exceeds cited relationship refs "
                            f"({relationship_count} declared, {len(set(relationship_ids))} cited)."
                        ),
                    )
                )
            missing_relationship_ids = sorted(set(relationship_ids) - set(relationships))
            if missing_relationship_ids:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message=(
                            "Spatial relationship lineage refs point to missing records: "
                            + ", ".join(str(item) for item in missing_relationship_ids[:5])
                        ),
                    )
                )
            stale_relationship_ids = []
            future_relationship_ids = []
            wrong_source_relationship_ids = []
            inactive_target_relationship_ids = []
            for relationship in relationships.values():
                if version is not None and relationship.geometry_dataset_version_id != version.id:
                    stale_relationship_ids.append(relationship.id)
                if source_cutoff is not None and relationship.generated_at >= source_cutoff:
                    future_relationship_ids.append(relationship.id)
                if relationship.source_ward_id != row.ward_id:
                    wrong_source_relationship_ids.append(relationship.id)
                if not relationship.target_ward.is_active:
                    inactive_target_relationship_ids.append(relationship.id)
            if stale_relationship_ids:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message=(
                            "Spatial relationship lineage uses records outside the active geometry version: "
                            + ", ".join(str(item) for item in sorted(stale_relationship_ids)[:5])
                        ),
                    )
                )
            if future_relationship_ids:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message=(
                            "Spatial relationship lineage uses records generated at or after source cutoff: "
                            + ", ".join(str(item) for item in sorted(future_relationship_ids)[:5])
                        ),
                    )
                )
            if wrong_source_relationship_ids:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message=(
                            "Spatial relationship lineage refs are not sourced from the feature row ward: "
                            + ", ".join(str(item) for item in sorted(wrong_source_relationship_ids)[:5])
                        ),
                    )
                )
            if inactive_target_relationship_ids:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message=(
                            "Spatial relationship lineage refs point to inactive target wards: "
                            + ", ".join(str(item) for item in sorted(inactive_target_relationship_ids)[:5])
                        ),
                    )
                )

        catchment_lineage = _as_dict(source_lineage.get("facility_catchment_pressure")) or _as_dict(
            spatial_lineage.get("catchment_facility_pressure")
        )
        catchment_refs = _as_list(catchment_lineage.get("catchment_refs"))
        catchment_count = _safe_int(values.get("catchment_facility_count")) or 0
        if (catchment_count > 0 or values.get("catchment_facility_readiness_pressure") is not None) and not catchment_refs:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_features_have_source_relationship_lineage",
                    severity="fail",
                    message="Catchment pressure feature is present without facility catchment refs.",
                )
            )
        if catchment_refs:
            catchment_ids, malformed_refs = _ref_ids(catchment_refs, prefix="facility_catchment")
            if malformed_refs:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message="Facility catchment lineage contains malformed refs: " + ", ".join(malformed_refs[:5]),
                    )
                )
            catchments = {
                catchment.id: catchment
                for catchment in FacilityCatchment.objects.filter(id__in=catchment_ids).select_related(
                    "facility",
                    "geometry_dataset_version",
                    "primary_ward",
                ).prefetch_related("covered_wards")
            }
            if catchment_count > len(set(catchment_ids)):
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message=(
                            "Facility catchment lineage count exceeds cited catchment refs "
                            f"({catchment_count} declared, {len(set(catchment_ids))} cited)."
                        ),
                    )
                )
            missing_catchment_ids = sorted(set(catchment_ids) - set(catchments))
            if missing_catchment_ids:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message=(
                            "Facility catchment lineage refs point to missing records: "
                            + ", ".join(str(item) for item in missing_catchment_ids[:5])
                        ),
                    )
                )
            stale_catchment_ids = []
            future_catchment_ids = []
            row_not_covered_catchment_ids = []
            inactive_facility_catchment_ids = []
            for catchment in catchments.values():
                if version is not None and catchment.geometry_dataset_version_id != version.id:
                    stale_catchment_ids.append(catchment.id)
                if source_cutoff is not None and catchment.generated_at >= source_cutoff:
                    future_catchment_ids.append(catchment.id)
                covered_ward_ids = {ward.id for ward in catchment.covered_wards.all()}
                if row.ward_id not in covered_ward_ids:
                    row_not_covered_catchment_ids.append(catchment.id)
                if not catchment.facility.is_active:
                    inactive_facility_catchment_ids.append(catchment.id)
            if stale_catchment_ids:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message=(
                            "Facility catchment lineage uses records outside the active geometry version: "
                            + ", ".join(str(item) for item in sorted(stale_catchment_ids)[:5])
                        ),
                    )
                )
            if future_catchment_ids:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message=(
                            "Facility catchment lineage uses records generated at or after source cutoff: "
                            + ", ".join(str(item) for item in sorted(future_catchment_ids)[:5])
                        ),
                    )
                )
            if row_not_covered_catchment_ids:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message=(
                            "Facility catchment lineage refs do not cover the feature row ward: "
                            + ", ".join(str(item) for item in sorted(row_not_covered_catchment_ids)[:5])
                        ),
                    )
                )
            if inactive_facility_catchment_ids:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_features_have_source_relationship_lineage",
                        severity="fail",
                        message=(
                            "Facility catchment lineage refs point to inactive facilities: "
                            + ", ".join(str(item) for item in sorted(inactive_facility_catchment_ids)[:5])
                        ),
                    )
                )
    return issues


def _neighbor_surveillance_record_ref_audit_issues(
    row: FeatureDatasetRow,
    *,
    spatial_lineage: dict,
    neighbor_lineage: dict,
    neighboring_record_count: int,
    active_outbreak_count: int,
    prediction_date: date,
    source_cutoff: datetime,
) -> list[dict]:
    issues = []
    refs = _as_list(neighbor_lineage.get("source_record_refs"))
    refs_required = neighboring_record_count > 0 or active_outbreak_count > 0
    if refs_required and not refs:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Neighbor surveillance feature is missing source_record refs.",
            )
        )
    if not refs:
        return issues

    record_ids, malformed_refs = _ref_ids(refs, prefix="surveillance_record")
    if malformed_refs:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Neighbor surveillance lineage contains malformed refs: " + ", ".join(malformed_refs[:5]),
            )
        )
    if not record_ids:
        return issues

    records = {record.id: record for record in SurveillanceRecord.objects.filter(id__in=record_ids)}
    missing_record_ids = sorted(set(record_ids) - set(records))
    if missing_record_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message=(
                    "Neighbor surveillance lineage refs point to missing records: "
                    + ", ".join(str(item) for item in missing_record_ids[:5])
                ),
            )
        )

    raw_neighbor_ward_ids = _as_list(neighbor_lineage.get("neighbor_ward_ids"))
    neighbor_ward_ids = set()
    malformed_neighbor_ward_ids = []
    for item in raw_neighbor_ward_ids:
        parsed = _safe_int(item)
        if parsed is None:
            malformed_neighbor_ward_ids.append(str(item or ""))
            continue
        neighbor_ward_ids.add(parsed)
    if malformed_neighbor_ward_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Neighbor surveillance lineage contains malformed neighbor_ward_ids: "
                + ", ".join(malformed_neighbor_ward_ids[:5]),
            )
        )
    if refs_required and not neighbor_ward_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Neighbor surveillance feature is missing neighbor_ward_ids for cited records.",
            )
        )

    relationship_lineage = _as_dict(spatial_lineage.get("relationships"))
    relationship_ids, _malformed_relationship_refs = _ref_ids(
        _as_list(relationship_lineage.get("relationship_refs")),
        prefix="ward_spatial_relationship",
    )
    if refs_required and not relationship_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Neighbor surveillance feature is missing ward_spatial_relationship refs.",
            )
        )
    if neighbor_ward_ids and relationship_ids:
        relationship_edges = list(
            WardSpatialRelationship.objects.filter(id__in=relationship_ids).values(
                "id",
                "source_ward_id",
                "target_ward_id",
            )
        )
        wrong_source_relationship_ids = sorted(
            edge["id"] for edge in relationship_edges if edge["source_ward_id"] != row.ward_id
        )
        relationship_target_ward_ids = {
            edge["target_ward_id"] for edge in relationship_edges if edge["source_ward_id"] == row.ward_id
        }
        unsupported_neighbor_ward_ids = sorted(neighbor_ward_ids - relationship_target_ward_ids)
        if wrong_source_relationship_ids:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message=(
                        "Neighbor surveillance relationship refs are not sourced from the feature row ward: "
                        + ", ".join(str(item) for item in wrong_source_relationship_ids[:5])
                    ),
                )
            )
        if unsupported_neighbor_ward_ids:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message=(
                        "Neighbor surveillance neighbor_ward_ids are not supported by relationship refs: "
                        + ", ".join(str(item) for item in unsupported_neighbor_ward_ids[:5])
                    ),
                )
            )

    future_record_ids = sorted(record.id for record in records.values() if record.created_at >= source_cutoff)
    future_reporting_period_ids = sorted(
        record.id for record in records.values() if record.reporting_period_end >= prediction_date
    )
    focal_ward_record_ids = sorted(record.id for record in records.values() if record.ward_id == row.ward_id)
    outside_neighbor_record_ids = sorted(
        record.id for record in records.values() if neighbor_ward_ids and record.ward_id not in neighbor_ward_ids
    )
    if future_record_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message=(
                    "Neighbor surveillance refs include records created at or after source cutoff: "
                    + ", ".join(str(item) for item in future_record_ids[:5])
                ),
            )
        )
    if future_reporting_period_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message=(
                    "Neighbor surveillance refs include reporting periods at or after prediction date: "
                    + ", ".join(str(item) for item in future_reporting_period_ids[:5])
                ),
            )
        )
    if focal_ward_record_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message=(
                    "Neighbor surveillance refs include focal ward records: "
                    + ", ".join(str(item) for item in focal_ward_record_ids[:5])
                ),
            )
        )
    if outside_neighbor_record_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message=(
                    "Neighbor surveillance refs include records outside neighbor_ward_ids: "
                    + ", ".join(str(item) for item in outside_neighbor_record_ids[:5])
                ),
            )
        )
    return issues


def _climate_source_ref_ids(value: list) -> tuple[list[int], list[tuple[int, int]], list[str]]:
    climate_record_ids = []
    ingestion_result_refs = []
    malformed = []
    for item in value:
        text = str(item or "")
        if text.startswith("climate_record:"):
            record_id = _safe_int(text.removeprefix("climate_record:"))
            if record_id is None:
                malformed.append(text)
            else:
                climate_record_ids.append(record_id)
            continue
        if text.startswith("ingestion_run_result:"):
            parts = text.split(":")
            run_id = _safe_int(parts[1]) if len(parts) == 3 else None
            row_index = _safe_int(parts[2]) if len(parts) == 3 else None
            if run_id is None or row_index is None:
                malformed.append(text)
            else:
                ingestion_result_refs.append((run_id, row_index))
            continue
        malformed.append(text)
    return climate_record_ids, ingestion_result_refs, malformed


def _neighbor_climate_record_ref_audit_issues(
    row: FeatureDatasetRow,
    *,
    values: dict,
    spatial_lineage: dict,
    neighbor_climate_lineage: dict,
    source_cutoff: datetime,
) -> list[dict]:
    if not _neighboring_climate_signal_present(values, neighbor_climate_lineage):
        return []

    issues = []
    refs = _as_list(neighbor_climate_lineage.get("source_record_refs"))
    if not refs:
        return [
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Neighbor climate feature is missing climate source_record refs.",
            )
        ]

    neighbor_ward_ids = {
        ward_id
        for ward_id in (_safe_int(item) for item in _as_list(neighbor_climate_lineage.get("neighbor_ward_ids")))
        if ward_id is not None
    }
    if not neighbor_ward_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Neighbor climate feature is missing neighbor_ward_ids for cited records.",
            )
        )

    relationship_ids, _malformed_relationship_refs = _ref_ids(
        _as_list(_as_dict(spatial_lineage.get("relationships")).get("relationship_refs")),
        prefix="ward_spatial_relationship",
    )
    if not relationship_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Neighbor climate feature is missing ward_spatial_relationship refs.",
            )
        )
    elif neighbor_ward_ids:
        relationship_edges = list(
            WardSpatialRelationship.objects.filter(id__in=relationship_ids).values(
                "id",
                "source_ward_id",
                "target_ward_id",
            )
        )
        wrong_source_relationship_ids = sorted(
            edge["id"] for edge in relationship_edges if edge["source_ward_id"] != row.ward_id
        )
        relationship_target_ward_ids = {
            edge["target_ward_id"] for edge in relationship_edges if edge["source_ward_id"] == row.ward_id
        }
        unsupported_neighbor_ward_ids = sorted(neighbor_ward_ids - relationship_target_ward_ids)
        if wrong_source_relationship_ids:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message=(
                        "Neighbor climate relationship refs are not sourced from the feature row ward: "
                        + ", ".join(str(item) for item in wrong_source_relationship_ids[:5])
                    ),
                )
            )
        if unsupported_neighbor_ward_ids:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message=(
                        "Neighbor climate neighbor_ward_ids are not supported by relationship refs: "
                        + ", ".join(str(item) for item in unsupported_neighbor_ward_ids[:5])
                    ),
                )
            )

    climate_record_ids, ingestion_result_refs, malformed_refs = _climate_source_ref_ids(refs)
    if malformed_refs:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Neighbor climate lineage contains malformed source refs: " + ", ".join(malformed_refs[:5]),
            )
        )

    if climate_record_ids:
        records = {
            record.id: record
            for record in ClimateRecord.objects.filter(id__in=climate_record_ids).select_related("ingestion_run")
        }
        missing_record_ids = sorted(set(climate_record_ids) - set(records))
        if missing_record_ids:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message=(
                        "Neighbor climate refs point to missing ClimateRecord rows: "
                        + ", ".join(str(item) for item in missing_record_ids[:5])
                    ),
                )
            )
        bad_record_ids = []
        future_record_ids = []
        outside_neighbor_record_ids = []
        for record in records.values():
            if record.record_type != ClimateRecordType.OBSERVED or record.fallback_flag:
                bad_record_ids.append(record.id)
            if (
                record.observed_timestamp is None
                or record.observed_timestamp >= source_cutoff
                or record.ingestion_run.completed_at is None
                or record.ingestion_run.completed_at >= source_cutoff
            ):
                future_record_ids.append(record.id)
            if neighbor_ward_ids and record.ward_id not in neighbor_ward_ids:
                outside_neighbor_record_ids.append(record.id)
        if bad_record_ids:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message=(
                        "Neighbor climate refs include non-observed or fallback records: "
                        + ", ".join(str(item) for item in sorted(bad_record_ids)[:5])
                    ),
                )
            )
        if future_record_ids:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message=(
                        "Neighbor climate refs include records at or after source cutoff: "
                        + ", ".join(str(item) for item in sorted(future_record_ids)[:5])
                    ),
                )
            )
        if outside_neighbor_record_ids:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message=(
                        "Neighbor climate refs include wards outside neighbor_ward_ids: "
                        + ", ".join(str(item) for item in sorted(outside_neighbor_record_ids)[:5])
                    ),
                )
            )

    if ingestion_result_refs:
        runs = {
            run.id: run
            for run in IngestionRun.objects.filter(
                id__in={run_id for run_id, _row_index in ingestion_result_refs}
            )
        }
        missing_run_ids = sorted({run_id for run_id, _row_index in ingestion_result_refs} - set(runs))
        if missing_run_ids:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message=(
                        "Neighbor climate refs point to missing IngestionRun rows: "
                        + ", ".join(str(item) for item in missing_run_ids[:5])
                    ),
                )
            )
        malformed_result_refs = []
        future_result_refs = []
        outside_neighbor_result_refs = []
        bad_result_refs = []
        for run_id, row_index in ingestion_result_refs:
            run = runs.get(run_id)
            if run is None:
                continue
            results = run.results if isinstance(run.results, list) else []
            if row_index >= len(results) or not isinstance(results[row_index], dict):
                malformed_result_refs.append(f"ingestion_run_result:{run_id}:{row_index}")
                continue
            result = results[row_index]
            enriched = enrich_rainfall_result_with_climate_contract(
                ingestion_run=run,
                result=result,
                row_index=row_index,
            )
            canonical = _as_dict(enriched.get("canonical_record"))
            ward_id = _safe_int(enriched.get("ward_id")) or _safe_int(canonical.get("ward_id"))
            observed_at = _parse_spatial_audit_datetime(
                enriched.get("observed_timestamp") or canonical.get("observed_timestamp")
            )
            record_type = enriched.get("record_type") or canonical.get("record_type") or ClimateRecordType.OBSERVED
            fallback_flag = bool(enriched.get("fallback_flag") or canonical.get("fallback_flag"))
            ref = f"ingestion_run_result:{run_id}:{row_index}"
            if record_type != ClimateRecordType.OBSERVED or fallback_flag:
                bad_result_refs.append(ref)
            if run.completed_at is None or run.completed_at >= source_cutoff or observed_at is None or observed_at >= source_cutoff:
                future_result_refs.append(ref)
            if neighbor_ward_ids and ward_id not in neighbor_ward_ids:
                outside_neighbor_result_refs.append(ref)
        if malformed_result_refs:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message="Neighbor climate refs point to missing ingestion result rows: "
                    + ", ".join(malformed_result_refs[:5]),
                )
            )
        if bad_result_refs:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message="Neighbor climate refs include non-observed or fallback ingestion results: "
                    + ", ".join(bad_result_refs[:5]),
                )
            )
        if future_result_refs:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message="Neighbor climate refs include ingestion results at or after source cutoff: "
                    + ", ".join(future_result_refs[:5]),
                )
            )
        if outside_neighbor_result_refs:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message="Neighbor climate refs include ingestion results outside neighbor_ward_ids: "
                    + ", ".join(outside_neighbor_result_refs[:5]),
                )
            )

    return issues


def _facility_forecast_ref_audit_issues(
    row: FeatureDatasetRow,
    *,
    values: dict,
    catchment_lineage: dict,
    source_cutoff: datetime,
) -> list[dict]:
    issues = []
    forecast_refs = _as_list(catchment_lineage.get("forecast_refs"))
    pressure_present = values.get("catchment_facility_readiness_pressure") is not None
    forecast_source_declared = (
        catchment_lineage.get("source_mode") == "facility_catchments_with_latest_forecast_before_cutoff"
    )
    if (pressure_present or forecast_source_declared) and not forecast_refs:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Catchment pressure feature with forecast pressure is missing facility_forecast refs.",
            )
        )
    if not forecast_refs:
        return issues

    forecast_ids, malformed_refs = _ref_ids(forecast_refs, prefix="facility_forecast")
    if malformed_refs:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Facility forecast lineage contains malformed refs: " + ", ".join(malformed_refs[:5]),
            )
        )
    if not forecast_ids:
        return issues

    forecasts = {forecast.id: forecast for forecast in FacilityForecast.objects.filter(id__in=forecast_ids)}
    missing_forecast_ids = sorted(set(forecast_ids) - set(forecasts))
    if missing_forecast_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message=(
                    "Facility forecast lineage refs point to missing records: "
                    + ", ".join(str(item) for item in missing_forecast_ids[:5])
                ),
            )
        )

    facility_ids, malformed_facility_refs = _ref_ids(
        _as_list(catchment_lineage.get("facility_refs")),
        prefix="health_facility",
    )
    if malformed_facility_refs:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Catchment pressure lineage contains malformed facility refs: "
                + ", ".join(malformed_facility_refs[:5]),
            )
        )
    if not facility_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Catchment pressure forecast lineage is missing health_facility refs.",
            )
        )

    catchment_ids, malformed_catchment_refs = _ref_ids(
        _as_list(catchment_lineage.get("catchment_refs")),
        prefix="facility_catchment",
    )
    if malformed_catchment_refs:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message="Catchment pressure lineage contains malformed catchment refs: "
                + ", ".join(malformed_catchment_refs[:5]),
            )
        )
    catchment_facility_ids = set(
        FacilityCatchment.objects.filter(id__in=catchment_ids).values_list("facility_id", flat=True)
    )
    if facility_ids and catchment_facility_ids:
        unsupported_facility_ids = sorted(set(facility_ids) - catchment_facility_ids)
        if unsupported_facility_ids:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message=(
                        "Catchment pressure facility_refs are not supported by catchment refs: "
                        + ", ".join(str(item) for item in unsupported_facility_ids[:5])
                    ),
                )
            )

    future_forecast_ids = sorted(
        forecast.id for forecast in forecasts.values() if forecast.generated_at >= source_cutoff
    )
    outside_facility_forecast_ids = sorted(
        forecast.id for forecast in forecasts.values() if facility_ids and forecast.facility_id not in facility_ids
    )
    outside_catchment_forecast_ids = sorted(
        forecast.id
        for forecast in forecasts.values()
        if catchment_facility_ids and forecast.facility_id not in catchment_facility_ids
    )
    if future_forecast_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message=(
                    "Facility forecast refs include forecasts generated at or after source cutoff: "
                    + ", ".join(str(item) for item in future_forecast_ids[:5])
                ),
            )
        )
    if outside_facility_forecast_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message=(
                    "Facility forecast refs include facilities outside catchment facility_refs: "
                    + ", ".join(str(item) for item in outside_facility_forecast_ids[:5])
                ),
            )
        )
    if outside_catchment_forecast_ids:
        issues.append(
            _feature_row_audit_issue(
                row,
                check_id="spatial_neighbor_features_cutoff_safe",
                severity="fail",
                message=(
                    "Facility forecast refs include facilities outside catchment refs: "
                    + ", ".join(str(item) for item in outside_catchment_forecast_ids[:5])
                ),
            )
        )
    return issues


def _spatial_feature_leakage_audit_issues(rows: list[FeatureDatasetRow]) -> list[dict]:
    issues = []
    for row in rows:
        values = _as_dict(row.feature_values)
        source_lineage = _as_dict(values.get("source_lineage"))
        leakage = _as_dict(values.get("leakage_proof"))
        prediction_date = _parse_spatial_audit_date(values.get("prediction_date"))
        source_cutoff = _parse_spatial_audit_datetime(
            values.get("source_cutoff_timestamp") or leakage.get("source_cutoff_timestamp")
        )

        if prediction_date is None or source_cutoff is None:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message="Feature row is missing prediction date or source cutoff for spatial leakage audit.",
                )
            )
            continue

        spatial_lineage = _as_dict(source_lineage.get("spatial_relationships")) or _as_dict(
            source_lineage.get("spatial_features")
        )
        neighbor_lineage = _as_dict(source_lineage.get("neighboring_surveillance")) or _as_dict(
            spatial_lineage.get("neighbor_surveillance")
        )
        neighbor_climate_lineage = _as_dict(source_lineage.get("neighboring_climate")) or _as_dict(
            spatial_lineage.get("neighbor_climate")
        )
        catchment_lineage = _as_dict(source_lineage.get("facility_catchment_pressure")) or _as_dict(
            spatial_lineage.get("catchment_facility_pressure")
        )
        neighboring_record_count = (
            _safe_int(values.get("neighboring_surveillance_record_count"))
            or _safe_int(neighbor_lineage.get("record_count"))
            or 0
        )
        active_outbreak_count = _safe_int(values.get("neighboring_active_outbreak_label_count")) or 0
        catchment_count = _safe_int(values.get("catchment_facility_count")) or 0
        spatial_signal_present = bool(
            _spatial_feature_uses_relationship_graph(values)
            or neighboring_record_count > 0
            or active_outbreak_count > 0
            or _neighboring_climate_signal_present(values, neighbor_climate_lineage)
            or catchment_count > 0
            or values.get("catchment_facility_readiness_pressure") is not None
        )
        if spatial_signal_present and not leakage:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message="Spatial feature row is missing leakage_proof metadata.",
                )
            )

        issues.extend(
            _neighbor_surveillance_record_ref_audit_issues(
                row,
                spatial_lineage=spatial_lineage,
                neighbor_lineage=neighbor_lineage,
                neighboring_record_count=neighboring_record_count,
                active_outbreak_count=active_outbreak_count,
                prediction_date=prediction_date,
                source_cutoff=source_cutoff,
            )
        )
        issues.extend(
            _neighbor_climate_record_ref_audit_issues(
                row,
                values=values,
                spatial_lineage=spatial_lineage,
                neighbor_climate_lineage=neighbor_climate_lineage,
                source_cutoff=source_cutoff,
            )
        )
        issues.extend(
            _facility_forecast_ref_audit_issues(
                row,
                values=values,
                catchment_lineage=catchment_lineage,
                source_cutoff=source_cutoff,
            )
        )

        relationship_generated_at = _parse_spatial_audit_datetime(
            leakage.get("max_spatial_relationship_generated_at")
            or spatial_lineage.get("max_relationship_generated_at")
        )
        if (
            _spatial_feature_uses_relationship_graph(values)
            and relationship_generated_at is not None
            and relationship_generated_at >= source_cutoff
        ):
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message="Spatial relationship generated at or after the feature source cutoff was used.",
                )
            )

        catchment_generated_at = _parse_spatial_audit_datetime(
            leakage.get("max_facility_catchment_generated_at")
            or catchment_lineage.get("max_catchment_generated_at")
        )
        forecast_generated_at = _parse_spatial_audit_datetime(
            leakage.get("max_facility_forecast_generated_at")
            or catchment_lineage.get("max_forecast_generated_at")
        )
        if catchment_count > 0 and catchment_generated_at is not None and catchment_generated_at >= source_cutoff:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message="Catchment pressure feature uses a catchment generated at or after source cutoff.",
                )
            )
        if forecast_generated_at is not None and forecast_generated_at >= source_cutoff:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message="Catchment pressure feature uses a facility forecast generated at or after source cutoff.",
                )
            )

        if neighboring_record_count > 0 or active_outbreak_count > 0:
            max_reporting_end = _parse_spatial_audit_date(
                leakage.get("max_neighbor_surveillance_reporting_period_end")
                or neighbor_lineage.get("max_reporting_period_end")
            )
            max_record_created_at = _parse_spatial_audit_datetime(
                leakage.get("max_neighbor_surveillance_record_created_at")
                or neighbor_lineage.get("max_record_created_at")
            )
            if max_reporting_end is None:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_neighbor_features_cutoff_safe",
                        severity="fail",
                        message="Neighbor surveillance feature is missing max reporting-period lineage.",
                    )
                )
            elif max_reporting_end >= prediction_date:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_neighbor_features_cutoff_safe",
                        severity="fail",
                        message="Neighbor outbreak or surveillance feature uses a reporting period at or after prediction date.",
                    )
                )
            if max_record_created_at is None:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_neighbor_features_cutoff_safe",
                        severity="fail",
                        message="Neighbor surveillance feature is missing record-created-at cutoff lineage.",
                    )
                )
            elif max_record_created_at >= source_cutoff:
                issues.append(
                    _feature_row_audit_issue(
                        row,
                        check_id="spatial_neighbor_features_cutoff_safe",
                        severity="fail",
                        message="Neighbor outbreak or surveillance feature uses records created at or after source cutoff.",
                    )
                )

        if leakage and leakage.get("passes_cutoff_check") is False:
            issues.append(
                _feature_row_audit_issue(
                    row,
                    check_id="spatial_neighbor_features_cutoff_safe",
                    severity="fail",
                    message="Feature row leakage proof reports that cutoff checks did not pass.",
                )
            )
    return issues


def build_spatial_graph_monitoring_audit(
    *,
    dataset_slug: str = DEFAULT_GEOMETRY_DATASET_SLUG,
    county: str = DEFAULT_SPATIAL_COUNTY,
    feature_dataset_ref: str | None = None,
    row_limit: int | None = None,
) -> dict:
    generated_at = timezone.now()
    county = county.strip() or DEFAULT_SPATIAL_COUNTY
    version = _active_geometry_version(dataset_slug)
    active_wards = list(Ward.objects.filter(county__iexact=county, is_active=True).order_by("name"))
    features = _geometry_features_for_version(version, county=county) if version else []
    features_by_ward_id = {feature.ward_id: feature for feature in features}
    feature_rows, feature_dataset_refs = _lead_time_feature_rows_for_spatial_audit(
        feature_dataset_ref=feature_dataset_ref,
        row_limit=row_limit,
    )
    facility_issues, active_facility_count = _facility_without_catchment_audit_issues(
        county=county,
        version=version,
    )
    catchment_population_issues, catchment_count = _catchment_population_audit_issues(
        county=county,
        version=version,
    )
    approximation_label_issues, approximate_label_scanned_count = _approximate_spatial_label_audit_issues(
        county=county,
        version=version,
    )

    checks = [
        _audit_check(
            check_id="active_geometry_dataset_version_available",
            title="Active geometry dataset version",
            issues=_active_geometry_version_audit_issues(version=version, dataset_slug=dataset_slug),
            scanned_count=1,
            empty_warning="No geometry dataset version lookup was performed.",
        ),
        _audit_check(
            check_id="active_wards_have_geometry",
            title="Active ward geometry coverage",
            issues=_active_ward_geometry_audit_issues(
                active_wards=active_wards,
                features_by_ward_id=features_by_ward_id,
                version=version,
            ),
            scanned_count=len(active_wards),
            empty_warning="No active wards are available to audit.",
        ),
        _audit_check(
            check_id="active_wards_have_spatial_neighbors",
            title="Isolated ward graph coverage",
            issues=_isolated_ward_audit_issues(
                active_wards=active_wards,
                features_by_ward_id=features_by_ward_id,
                version=version,
            ),
            scanned_count=len(active_wards),
            empty_warning="No active wards are available to audit.",
        ),
        _audit_check(
            check_id="active_facilities_have_catchments",
            title="Active facility catchment coverage",
            issues=facility_issues,
            scanned_count=active_facility_count,
            empty_warning="No active facilities are available to audit.",
        ),
        _audit_check(
            check_id="catchment_population_estimates_plausible",
            title="Catchment population plausibility",
            issues=catchment_population_issues,
            scanned_count=catchment_count,
            empty_warning="No facility catchments are available to audit.",
        ),
        _audit_check(
            check_id="spatial_features_have_source_relationship_lineage",
            title="Spatial feature source lineage",
            issues=_spatial_feature_lineage_audit_issues(feature_rows, version=version),
            scanned_count=len(feature_rows),
            empty_warning="No lead-time feature rows are available for spatial lineage audit.",
        ),
        _audit_check(
            check_id="spatial_neighbor_features_cutoff_safe",
            title="Spatial leakage and neighboring outbreak cutoff",
            issues=_spatial_feature_leakage_audit_issues(feature_rows),
            scanned_count=len(feature_rows),
            empty_warning="No lead-time feature rows are available for spatial leakage audit.",
        ),
        _audit_check(
            check_id="approximate_spatial_relationships_labelled_honestly",
            title="Approximate relationship display honesty",
            issues=approximation_label_issues,
            scanned_count=approximate_label_scanned_count,
            empty_warning="No catchments or same-facility relationships are available to label.",
        ),
    ]
    if any(check["status"] == "fail" for check in checks):
        overall_status = "fail"
    elif any(check["status"] == "warning" for check in checks):
        overall_status = "warning"
    else:
        overall_status = "pass"
    issues = [issue for check in checks for issue in check["issues"]]

    return {
        "audit_name": SPATIAL_GRAPH_AUDIT_NAME,
        "schema_version": SPATIAL_GRAPH_AUDIT_SCHEMA_VERSION,
        "overall_status": overall_status,
        "generated_at": generated_at.isoformat(),
        "county": county,
        "geometry_dataset": _version_lineage(version),
        "filters": {
            "dataset_slug": dataset_slug,
            "feature_dataset_ref": feature_dataset_ref or "",
            "row_limit": row_limit,
        },
        "record_totals": {
            "active_ward_count": len(active_wards),
            "active_geometry_feature_count": len(features),
            "active_facility_count": active_facility_count,
            "facility_catchment_count": catchment_count,
            "lead_time_feature_row_count": len(feature_rows),
            "lead_time_feature_dataset_refs": feature_dataset_refs,
            "ward_spatial_relationship_count": WardSpatialRelationship.objects.filter(
                source_ward__county__iexact=county,
                geometry_dataset_version=version,
                relationship_type__in=SPATIAL_AUDIT_NEIGHBOR_RELATIONSHIP_TYPES,
            ).count(),
        },
        "checks": checks,
        "issues": issues,
        "operator_guidance": {
            "phase_5_exit_criteria": (
                "Spatial graph audit passes, lead-time feature rows include spatial lineage and leakage checks, "
                "and approximate catchments are labelled as operational approximations."
            ),
            "strict_command": "python manage.py audit_spatial_graph --strict",
        },
    }


def build_spatial_source_quality_report(
    *,
    dataset_slug: str = DEFAULT_GEOMETRY_DATASET_SLUG,
    county: str = DEFAULT_SPATIAL_COUNTY,
) -> dict:
    generated_at = timezone.now()
    county = county.strip() or DEFAULT_SPATIAL_COUNTY
    version = _active_geometry_version(dataset_slug)
    active_wards = list(Ward.objects.filter(county__iexact=county, is_active=True).order_by("name"))
    active_ward_ids = {ward.id for ward in active_wards}
    features = _geometry_features_for_version(version, county=county) if version else []
    features_by_ward_id = {feature.ward_id: feature for feature in features}

    missing_feature_ward_names = sorted(
        ward.name for ward in active_wards if ward.id not in features_by_ward_id
    )
    invalid_geometry_ward_names = sorted(
        feature.ward.name for feature in features if not _geometry_is_usable(feature.geometry)
    )
    missing_centroid_ward_names = sorted(feature.ward.name for feature in features if feature.centroid is None)
    canonical_boundary_missing_ward_names = sorted(
        ward.name for ward in active_wards if ward.boundary is None
    )
    canonical_centroid_missing_ward_names = sorted(
        ward.name for ward in active_wards if ward.centroid is None
    )
    geometry_srid_counts = Counter(
        str(feature.geometry.srid or "unknown") for feature in features if feature.geometry is not None
    )
    validation_summary = version.validation_summary if version and isinstance(version.validation_summary, dict) else {}
    placeholder_geometry_detected = bool(validation_summary.get("placeholder_geometry_detected"))
    adjacency_summary = _candidate_adjacency_summary(features) if features else {
        "undirected_adjacent_pair_count": 0,
        "directed_adjacent_edge_count": 0,
        "isolated_ward_names": [],
        "skipped_pair_count": 0,
        "pair_errors": [],
    }

    active_facilities = HealthFacility.objects.filter(is_active=True, ward__county__iexact=county)
    active_facility_count = active_facilities.count()
    facilities_with_coordinates = active_facilities.exclude(point__isnull=True).count()
    facilities_without_coordinates = active_facilities.filter(point__isnull=True).count()
    facility_points_outside_ward = 0
    for facility in active_facilities.exclude(point__isnull=True).select_related("ward"):
        feature = features_by_ward_id.get(facility.ward_id)
        if feature and _geometry_is_usable(feature.geometry) and not facility.point.within(feature.geometry):
            facility_points_outside_ward += 1

    water_body_record_count = ExposureFeatureRecord.objects.filter(
        ward_id__in=active_ward_ids,
        exposure_type=ExposureFeatureRecord.EXPOSURE_WATER_BODY_PROXIMITY,
    ).count()
    floodplain_record_count = ExposureFeatureRecord.objects.filter(
        ward_id__in=active_ward_ids,
        exposure_type=ExposureFeatureRecord.EXPOSURE_FLOODPLAIN_EXPOSURE,
    ).count()
    proximity_source_counts = {
        row["source_type"]: row["count"]
        for row in PopulationExposureSource.objects.filter(
            source_type__in=[
                PopulationExposureSource.SOURCE_TYPE_WATER_BODY_DISTANCE_LAYER,
                PopulationExposureSource.SOURCE_TYPE_FLOOD_EXPOSURE_LAYER,
            ],
        )
        .values("source_type")
        .annotate(count=Count("id"))
    }

    geometry_gaps = []
    if version is None:
        geometry_gaps.append("active_geometry_version_missing")
    if missing_feature_ward_names:
        geometry_gaps.append("active_wards_missing_managed_geometry")
    if invalid_geometry_ward_names:
        geometry_gaps.append("invalid_or_empty_ward_geometry")
    if placeholder_geometry_detected:
        geometry_gaps.append("placeholder_geometry_detected")

    geometry_status = "pass" if not geometry_gaps else "fail"
    boundary_gaps = []
    if not features:
        boundary_gaps.append("no_managed_geometry_features_available")
    if adjacency_summary["isolated_ward_names"]:
        boundary_gaps.append("isolated_wards_without_candidate_neighbors")
    if adjacency_summary["skipped_pair_count"]:
        boundary_gaps.append("geometry_pair_comparison_errors")
    boundary_status = "pass" if not boundary_gaps else "warning"

    facility_gaps = []
    if active_facility_count and facilities_without_coordinates:
        facility_gaps.append("facilities_without_coordinates")
    if facility_points_outside_ward:
        facility_gaps.append("facility_points_outside_assigned_ward_geometry")
    facility_status = "pass" if not facility_gaps else "warning"

    proximity_gaps = []
    if water_body_record_count == 0:
        proximity_gaps.append("water_body_proximity_inputs_not_available")
    if floodplain_record_count == 0:
        proximity_gaps.append("floodplain_exposure_inputs_not_available")
    proximity_status = "pass" if not proximity_gaps else "warning"

    crs_gaps = []
    source_crs = version.source_crs if version else ""
    if not source_crs or source_crs.lower() == "unknown":
        crs_gaps.append("source_crs_missing_or_unknown")
    if geometry_srid_counts and set(geometry_srid_counts) != {"4326"}:
        crs_gaps.append("geometry_feature_srid_not_epsg_4326")
    crs_status = "pass" if not crs_gaps else "warning"

    questions = [
        _question(
            question_id="active_ward_geometry_coverage",
            status=geometry_status,
            answer=(
                "All active wards have usable managed geometry."
                if geometry_status == "pass"
                else "Managed ward geometry coverage has critical gaps."
            ),
            evidence={
                "active_ward_count": len(active_wards),
                "managed_geometry_feature_count": len(features),
                "missing_feature_ward_names": missing_feature_ward_names,
                "invalid_geometry_ward_names": invalid_geometry_ward_names,
                "missing_centroid_ward_names": missing_centroid_ward_names,
                "canonical_boundary_missing_ward_names": canonical_boundary_missing_ward_names,
                "canonical_centroid_missing_ward_names": canonical_centroid_missing_ward_names,
                "placeholder_geometry_detected": placeholder_geometry_detected,
            },
            gaps=geometry_gaps,
            assumptions=[
                "Managed WardGeometryFeature rows are treated as the reproducible geometry source for graph generation.",
                "Canonical Ward.boundary and Ward.centroid are treated as synchronized operational copies.",
            ],
        ),
        _question(
            question_id="ward_boundary_relationship_signal",
            status=boundary_status,
            answer=(
                "Ward boundaries expose shared-border candidates for adjacency."
                if boundary_status == "pass"
                else "Ward boundary adjacency candidates exist with gaps that need review."
            ),
            evidence=adjacency_summary,
            gaps=boundary_gaps,
            assumptions=[
                "A positive GEOS boundary-intersection length means the two wards share an administrative border.",
                "Length and distance are measured in the source CRS units until a projected CRS is introduced.",
            ],
        ),
        _question(
            question_id="facility_coordinate_coverage",
            status=facility_status,
            answer=(
                "Active facilities have coordinates that can support proximity checks."
                if facility_status == "pass"
                else "Some facilities only have ward assignment or have coordinates that need review."
            ),
            evidence={
                "active_facility_count": active_facility_count,
                "facilities_with_coordinates": facilities_with_coordinates,
                "facilities_without_coordinates": facilities_without_coordinates,
                "facility_points_outside_ward": facility_points_outside_ward,
            },
            gaps=facility_gaps,
            assumptions=[
                "Facilities without point coordinates remain usable for ward-linked catchment context, not precise proximity.",
            ],
        ),
        _question(
            question_id="water_and_floodplain_inputs",
            status=proximity_status,
            answer=(
                "Water-body and floodplain proximity inputs are available."
                if proximity_status == "pass"
                else "Water-body or floodplain proximity inputs are missing from current canonical exposure records."
            ),
            evidence={
                "water_body_proximity_record_count": water_body_record_count,
                "floodplain_exposure_record_count": floodplain_record_count,
                "population_exposure_source_counts": proximity_source_counts,
            },
            gaps=proximity_gaps,
            assumptions=[
                "Water and floodplain proximity features must come from PopulationExposureSource/ExposureFeatureRecord lineage.",
            ],
        ),
        _question(
            question_id="coordinate_reference_system",
            status=crs_status,
            answer=(
                "The managed geometry CRS contract is explicit."
                if crs_status == "pass"
                else "The managed geometry CRS contract has assumptions or inconsistent feature SRIDs."
            ),
            evidence={
                "source_crs": source_crs,
                "geometry_feature_srid_counts": dict(geometry_srid_counts),
                "distance_unit_for_phase_1": DEFAULT_DISTANCE_UNIT,
            },
            gaps=crs_gaps,
            assumptions=[
                "Phase 1 stores shared-boundary length and centroid distance in source CRS degrees for EPSG:4326 inputs.",
            ],
        ),
    ]

    return {
        "schema_version": SPATIAL_SOURCE_AUDIT_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "county": county,
        "overall_status": _overall_status(questions),
        "geometry_dataset": _version_lineage(version),
        "source_quality": {
            "active_ward_count": len(active_wards),
            "managed_geometry_feature_count": len(features),
            "active_facility_count": active_facility_count,
            "facilities_with_coordinates": facilities_with_coordinates,
            "facilities_without_coordinates": facilities_without_coordinates,
            "water_body_proximity_record_count": water_body_record_count,
            "floodplain_exposure_record_count": floodplain_record_count,
            "existing_spatial_relationship_count": WardSpatialRelationship.objects.filter(
                geometry_dataset_version=version
            ).count()
            if version
            else 0,
        },
        "explicit_assumptions": [
            "The active managed geometry version is the source of truth for derived ward graph edges.",
            "Derived phase-1 adjacency is based on shared boundary geometry, not epidemiological causality.",
            "Manual public-health links must use generation_method=manual_public_health and remain separate from derived edges.",
            "Distance values are recorded in source CRS degrees until the project introduces a projected distance workflow.",
        ],
        "verification_questions": questions,
    }


def _edge_lineage(
    *,
    version: WardGeometryDatasetVersion,
    relationship_type: str,
    left: WardGeometryFeature,
    right: WardGeometryFeature,
    min_shared_boundary_length: float,
    nearby_centroid_threshold: float | None,
    shared_boundary_length: float,
    centroid_distance: float | None,
) -> dict:
    lineage = {
        "schema_version": WARD_SPATIAL_GRAPH_SCHEMA_VERSION,
        "geometry_dataset": _version_lineage(version),
        "relationship_type": relationship_type,
        "generation_method": WardSpatialRelationshipSource.DERIVED_GEOMETRY,
        "source_geometry_feature_ids": [left.id, right.id],
        "source_ward_ids": [left.ward_id, right.ward_id],
        "source_ward_public_ids": [str(left.ward.public_id), str(right.ward.public_id)],
        "calculation": {
            "min_shared_boundary_length": min_shared_boundary_length,
            "nearby_centroid_threshold": nearby_centroid_threshold,
            "shared_boundary_length": shared_boundary_length,
            "centroid_distance": centroid_distance,
            "distance_unit": DEFAULT_DISTANCE_UNIT,
            "directed_edge": True,
        },
    }
    validation_summary = version.validation_summary if isinstance(version.validation_summary, dict) else {}
    if validation_summary.get("placeholder_geometry_detected"):
        lineage["caveat"] = "Active geometry version appears to contain placeholder polygons."
    return lineage


def _relationship_rows_for_pair(
    *,
    version: WardGeometryDatasetVersion,
    left: WardGeometryFeature,
    right: WardGeometryFeature,
    relationship_type: str,
    shared_boundary_length: float,
    centroid_distance: float | None,
    min_shared_boundary_length: float,
    nearby_centroid_threshold: float | None,
    generated_at,
) -> list[WardSpatialRelationship]:
    validation_summary = version.validation_summary if isinstance(version.validation_summary, dict) else {}
    confidence = 0.4 if validation_summary.get("placeholder_geometry_detected") else 1.0
    if relationship_type == WardSpatialRelationshipType.NEARBY:
        confidence = min(confidence, 0.7)

    rows = []
    for source, target in ((left, right), (right, left)):
        rows.append(
            WardSpatialRelationship(
                source_ward=source.ward,
                target_ward=target.ward,
                relationship_type=relationship_type,
                geometry_dataset_version=version,
                shared_boundary_length=shared_boundary_length,
                centroid_distance=centroid_distance,
                distance_unit=DEFAULT_DISTANCE_UNIT,
                confidence=confidence,
                generation_method=WardSpatialRelationshipSource.DERIVED_GEOMETRY,
                generated_at=generated_at,
                lineage_metadata=_edge_lineage(
                    version=version,
                    relationship_type=relationship_type,
                    left=source,
                    right=target,
                    min_shared_boundary_length=min_shared_boundary_length,
                    nearby_centroid_threshold=nearby_centroid_threshold,
                    shared_boundary_length=shared_boundary_length,
                    centroid_distance=centroid_distance,
                ),
            )
        )
    return rows


def rebuild_ward_spatial_relationship_graph(
    *,
    dataset_slug: str = DEFAULT_GEOMETRY_DATASET_SLUG,
    county: str = DEFAULT_SPATIAL_COUNTY,
    min_shared_boundary_length: float = 0.0,
    nearby_centroid_threshold: float | None = None,
    dry_run: bool = False,
) -> dict:
    county = county.strip() or DEFAULT_SPATIAL_COUNTY
    version = _active_geometry_version(dataset_slug)
    if version is None:
        raise WardGeometryDatasetVersion.DoesNotExist(
            f"No active managed ward geometry version found for dataset '{dataset_slug}'."
        )

    features = _geometry_features_for_version(version, county=county)
    if not features:
        raise WardGeometryFeature.DoesNotExist(
            f"No active ward geometry features found for dataset '{dataset_slug}' in county '{county}'."
        )

    generated_at = timezone.now()
    rows: list[WardSpatialRelationship] = []
    skipped_pairs = []
    adjacent_pair_count = 0
    nearby_pair_count = 0

    for left, right in combinations(features, 2):
        if not _geometry_is_usable(left.geometry) or not _geometry_is_usable(right.geometry):
            skipped_pairs.append(
                {
                    "source_ward_id": left.ward_id,
                    "target_ward_id": right.ward_id,
                    "reason": "invalid_or_empty_geometry",
                }
            )
            continue
        try:
            shared_boundary_length = _shared_boundary_length(left, right)
            centroid_distance = _centroid_distance(left, right)
        except Exception as error:
            skipped_pairs.append(
                {
                    "source_ward_id": left.ward_id,
                    "target_ward_id": right.ward_id,
                    "reason": str(error),
                }
            )
            continue

        if shared_boundary_length > min_shared_boundary_length:
            adjacent_pair_count += 1
            rows.extend(
                _relationship_rows_for_pair(
                    version=version,
                    left=left,
                    right=right,
                    relationship_type=WardSpatialRelationshipType.ADJACENT,
                    shared_boundary_length=shared_boundary_length,
                    centroid_distance=centroid_distance,
                    min_shared_boundary_length=min_shared_boundary_length,
                    nearby_centroid_threshold=nearby_centroid_threshold,
                    generated_at=generated_at,
                )
            )
            continue

        if (
            nearby_centroid_threshold is not None
            and centroid_distance is not None
            and centroid_distance <= nearby_centroid_threshold
        ):
            nearby_pair_count += 1
            rows.extend(
                _relationship_rows_for_pair(
                    version=version,
                    left=left,
                    right=right,
                    relationship_type=WardSpatialRelationshipType.NEARBY,
                    shared_boundary_length=shared_boundary_length,
                    centroid_distance=centroid_distance,
                    min_shared_boundary_length=min_shared_boundary_length,
                    nearby_centroid_threshold=nearby_centroid_threshold,
                    generated_at=generated_at,
                )
            )

    relationship_types = [WardSpatialRelationshipType.ADJACENT]
    if nearby_centroid_threshold is not None:
        relationship_types.append(WardSpatialRelationshipType.NEARBY)

    with transaction.atomic():
        deleted_count, _ = WardSpatialRelationship.objects.filter(
            geometry_dataset_version=version,
            generation_method=WardSpatialRelationshipSource.DERIVED_GEOMETRY,
            relationship_type__in=relationship_types,
        ).delete()
        WardSpatialRelationship.objects.bulk_create(rows, batch_size=500)
        if dry_run:
            transaction.set_rollback(True)

    return {
        "schema_version": WARD_SPATIAL_GRAPH_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "county": county,
        "dry_run": dry_run,
        "geometry_dataset": _version_lineage(version),
        "feature_count": len(features),
        "relationship_types_rebuilt": relationship_types,
        "deleted_derived_edge_count": deleted_count,
        "created_derived_edge_count": len(rows),
        "undirected_adjacent_pair_count": adjacent_pair_count,
        "directed_adjacent_edge_count": adjacent_pair_count * 2,
        "undirected_nearby_pair_count": nearby_pair_count,
        "directed_nearby_edge_count": nearby_pair_count * 2,
        "manual_edge_count_preserved": WardSpatialRelationship.objects.filter(
            geometry_dataset_version=version,
            generation_method=WardSpatialRelationshipSource.MANUAL_PUBLIC_HEALTH,
        ).count(),
        "skipped_pair_count": len(skipped_pairs),
        "skipped_pairs": skipped_pairs[:50],
        "assumptions": [
            "Derived adjacency edges are directed duplicates of undirected shared-border pairs.",
            "Manual links are preserved because only generation_method=derived_geometry rows are rebuilt.",
            "Shared-boundary length and centroid distance are stored in source CRS degrees.",
        ],
    }


def _latest_population_baselines_by_ward(ward_ids: set[int]) -> dict[int, PopulationBaselineRecord]:
    records: dict[int, PopulationBaselineRecord] = {}
    queryset = (
        PopulationBaselineRecord.objects.filter(ward_id__in=ward_ids)
        .exclude(freshness_state__in=STALE_POPULATION_EXPOSURE_STATES)
        .select_related("source", "ingestion_run", "ward")
        .order_by("ward_id", "-recorded_at", "-id")
    )
    for record in queryset:
        records.setdefault(record.ward_id, record)
    return records


def _latest_catchment_records_by_facility(facility_ids: set[int]) -> dict[int, CatchmentPopulationRecord]:
    records: dict[int, CatchmentPopulationRecord] = {}
    queryset = (
        CatchmentPopulationRecord.objects.filter(facility_id__in=facility_ids)
        .exclude(freshness_state__in=STALE_POPULATION_EXPOSURE_STATES)
        .select_related("facility", "source", "ingestion_run")
        .order_by("facility_id", "-recorded_at", "-id")
    )
    for record in queryset:
        records.setdefault(record.facility_id, record)
    return records


def _adjacent_ward_ids_by_source(version: WardGeometryDatasetVersion, source_ward_ids: set[int]) -> dict[int, set[int]]:
    adjacency: dict[int, set[int]] = defaultdict(set)
    relationships = WardSpatialRelationship.objects.filter(
        geometry_dataset_version=version,
        generation_method=WardSpatialRelationshipSource.DERIVED_GEOMETRY,
        relationship_type=WardSpatialRelationshipType.ADJACENT,
        source_ward_id__in=source_ward_ids,
    ).values("id", "source_ward_id", "target_ward_id")
    for relationship in relationships:
        adjacency[relationship["source_ward_id"]].add(relationship["target_ward_id"])
    return adjacency


def _relationship_ids_for_covered_wards(
    version: WardGeometryDatasetVersion,
    source_ward_id: int,
    covered_ward_ids: set[int],
) -> list[int]:
    if not covered_ward_ids:
        return []
    return list(
        WardSpatialRelationship.objects.filter(
            geometry_dataset_version=version,
            generation_method=WardSpatialRelationshipSource.DERIVED_GEOMETRY,
            relationship_type=WardSpatialRelationshipType.ADJACENT,
            source_ward_id=source_ward_id,
            target_ward_id__in=covered_ward_ids,
        ).values_list("id", flat=True)
    )


def _coverage_from_distance_threshold(
    *,
    facility: HealthFacility,
    features: list[WardGeometryFeature],
    distance_threshold: float | None,
) -> set[int]:
    if distance_threshold is None or facility.point is None:
        return set()
    covered_ids = set()
    for feature in features:
        if not _geometry_is_usable(feature.geometry):
            continue
        if float(feature.geometry.distance(facility.point)) <= distance_threshold:
            covered_ids.add(feature.ward_id)
    return covered_ids


def _covered_ward_ids_from_source_record(
    record: CatchmentPopulationRecord,
    *,
    fallback_primary_ward_id: int,
    active_ward_ids: set[int],
) -> set[int]:
    covered_ids = {fallback_primary_ward_id}
    assigned_ids = record.assigned_ward_ids if isinstance(record.assigned_ward_ids, list) else []
    for raw_ward_id in assigned_ids:
        try:
            ward_id = int(raw_ward_id)
        except (TypeError, ValueError):
            continue
        if ward_id in active_ward_ids:
            covered_ids.add(ward_id)
    return covered_ids


def _source_record_is_verified(record: CatchmentPopulationRecord | None) -> bool:
    if record is None:
        return False
    raw_payload = record.raw_payload if isinstance(record.raw_payload, dict) else {}
    source_metadata = record.source.metadata if record.source_id and isinstance(record.source.metadata, dict) else {}
    return bool(raw_payload.get("externally_verified") or source_metadata.get("externally_verified"))


def _population_estimate_for_wards(
    *,
    ward_ids: set[int],
    population_by_ward_id: dict[int, PopulationBaselineRecord],
    source_catchment_record: CatchmentPopulationRecord | None,
) -> tuple[float | None, dict]:
    if source_catchment_record is not None:
        return source_catchment_record.catchment_population_estimate, {
            "method": "catchment_population_record",
            "catchment_population_record_id": source_catchment_record.id,
            "source_name": source_catchment_record.source_name,
            "source_ref": source_catchment_record.source_ref,
            "truth_class": source_catchment_record.truth_class,
        }

    selected_records = [
        population_by_ward_id[ward_id]
        for ward_id in sorted(ward_ids)
        if ward_id in population_by_ward_id
    ]
    if not selected_records:
        return None, {
            "method": "unavailable",
            "missing_population_ward_ids": sorted(ward_ids),
        }
    covered_record_ward_ids = {record.ward_id for record in selected_records}
    return float(sum(record.population_total for record in selected_records)), {
        "method": "population_baseline_sum",
        "population_baseline_record_ids": [record.id for record in selected_records],
        "covered_population_ward_ids": sorted(covered_record_ward_ids),
        "missing_population_ward_ids": sorted(ward_ids - covered_record_ward_ids),
    }


def _facility_catchment_lineage(
    *,
    version: WardGeometryDatasetVersion,
    facility: HealthFacility,
    primary_ward: Ward,
    covered_wards: list[Ward],
    catchment_method: str,
    source_kind: str,
    distance_threshold: float | None,
    confidence: float,
    is_approximate: bool,
    population_lineage: dict,
    source_relationship_ids: list[int],
    source_catchment_record: CatchmentPopulationRecord | None,
) -> dict:
    lineage = {
        "schema_version": FACILITY_CATCHMENT_SCHEMA_VERSION,
        "geometry_dataset": _version_lineage(version),
        "facility": {
            "id": facility.id,
            "public_id": str(facility.public_id),
            "facility_code": facility.facility_code,
            "name": facility.name,
            "has_coordinates": facility.point is not None,
        },
        "primary_ward": {
            "id": primary_ward.id,
            "public_id": str(primary_ward.public_id),
            "name": primary_ward.name,
            "ward_code": primary_ward.ward_code,
        },
        "covered_wards": [
            {
                "id": ward.id,
                "public_id": str(ward.public_id),
                "name": ward.name,
                "ward_code": ward.ward_code,
            }
            for ward in covered_wards
        ],
        "catchment_method": catchment_method,
        "source_kind": source_kind,
        "distance_threshold": distance_threshold,
        "distance_unit": DEFAULT_DISTANCE_UNIT,
        "confidence": confidence,
        "is_approximate": is_approximate,
        "population_estimate_source": population_lineage,
        "source_relationship_ids": source_relationship_ids,
    }
    if source_catchment_record is not None:
        lineage["source_catchment_record"] = {
            "id": source_catchment_record.id,
            "assignment_method": source_catchment_record.assignment_method,
            "source_name": source_catchment_record.source_name,
            "source_kind": source_catchment_record.source_kind,
            "freshness_state": source_catchment_record.freshness_state,
            "truth_class": source_catchment_record.truth_class,
        }
    if is_approximate:
        lineage["approximation_notice"] = (
            "Facility catchment is an approximation for operational pressure context; "
            "do not treat it as a verified service-area boundary."
        )
    else:
        lineage["verification_notice"] = "Facility catchment is marked externally verified by source metadata."
    return lineage


def _confidence_for_method(
    *,
    method: str,
    source_catchment_record: CatchmentPopulationRecord | None,
    externally_verified: bool,
) -> float:
    if externally_verified:
        return 0.9
    if source_catchment_record is not None:
        return 0.7
    if method == FacilityCatchmentMethod.DISTANCE_THRESHOLD:
        return 0.55
    if method == FacilityCatchmentMethod.SPATIAL_GRAPH_ADJACENT_WARDS:
        return 0.5
    return 0.35


def _same_facility_edge_lineage(
    *,
    version: WardGeometryDatasetVersion,
    source_ward: Ward,
    target_ward: Ward,
    facility_summaries: list[dict],
    confidence: float,
) -> dict:
    return {
        "schema_version": FACILITY_CATCHMENT_SCHEMA_VERSION,
        "geometry_dataset": _version_lineage(version),
        "relationship_type": WardSpatialRelationshipType.SAME_FACILITY_CATCHMENT,
        "generation_method": WardSpatialRelationshipSource.DERIVED_FACILITY_CATCHMENT,
        "source_ward": {"id": source_ward.id, "name": source_ward.name, "ward_code": source_ward.ward_code},
        "target_ward": {"id": target_ward.id, "name": target_ward.name, "ward_code": target_ward.ward_code},
        "facility_catchments": facility_summaries,
        "confidence": confidence,
        "approximation_notice": (
            "Same-facility-catchment relationship is derived from FacilityCatchment approximations."
        ),
    }


def rebuild_facility_catchment_approximations(
    *,
    dataset_slug: str = DEFAULT_GEOMETRY_DATASET_SLUG,
    county: str = DEFAULT_SPATIAL_COUNTY,
    include_adjacent_wards: bool = True,
    distance_threshold: float | None = None,
    dry_run: bool = False,
) -> dict:
    county = county.strip() or DEFAULT_SPATIAL_COUNTY
    if distance_threshold is not None and distance_threshold < 0:
        raise ValueError("distance_threshold must be non-negative when supplied.")

    version = _active_geometry_version(dataset_slug)
    if version is None:
        raise WardGeometryDatasetVersion.DoesNotExist(
            f"No active managed ward geometry version found for dataset '{dataset_slug}'."
        )

    facilities = list(
        HealthFacility.objects.select_related("ward")
        .filter(is_active=True, ward__county__iexact=county)
        .order_by("ward__name", "name", "id")
    )
    features = _geometry_features_for_version(version, county=county)
    features_by_ward_id = {feature.ward_id: feature for feature in features}
    active_wards = {
        ward.id: ward
        for ward in Ward.objects.filter(county__iexact=county, is_active=True).order_by("name", "id")
    }
    facility_ids = {facility.id for facility in facilities}
    primary_ward_ids = {facility.ward_id for facility in facilities}
    latest_catchment_by_facility = _latest_catchment_records_by_facility(facility_ids)
    adjacency_by_source_ward = _adjacent_ward_ids_by_source(version, primary_ward_ids)
    population_by_ward_id = _latest_population_baselines_by_ward(set(active_wards.keys()))

    generated_at = timezone.now()
    catchment_summaries = []
    created_catchments: list[tuple[FacilityCatchment, list[Ward]]] = []
    skipped_facilities = []

    with transaction.atomic():
        deleted_catchment_count, _ = FacilityCatchment.objects.filter(
            geometry_dataset_version=version,
        ).filter(
            Q(source_kind=FacilityCatchmentSourceKind.APPROXIMATED)
            | Q(lineage_metadata__schema_version=FACILITY_CATCHMENT_SCHEMA_VERSION)
        ).delete()
        deleted_relationship_count, _ = WardSpatialRelationship.objects.filter(
            geometry_dataset_version=version,
            generation_method=WardSpatialRelationshipSource.DERIVED_FACILITY_CATCHMENT,
            relationship_type=WardSpatialRelationshipType.SAME_FACILITY_CATCHMENT,
        ).delete()

        for facility in facilities:
            primary_ward = facility.ward
            primary_ward_id = facility.ward_id
            if primary_ward_id is None:
                skipped_facilities.append({"facility_id": facility.id, "reason": "missing_primary_ward"})
                continue
            covered_ward_ids = {primary_ward_id}

            source_catchment_record = latest_catchment_by_facility.get(facility.id)
            externally_verified = _source_record_is_verified(source_catchment_record)
            source_relationship_ids: list[int] = []

            if source_catchment_record is not None:
                covered_ward_ids = _covered_ward_ids_from_source_record(
                    source_catchment_record,
                    fallback_primary_ward_id=primary_ward_id,
                    active_ward_ids=set(active_wards),
                )
                catchment_method = (
                    FacilityCatchmentMethod.EXTERNALLY_VERIFIED
                    if externally_verified
                    else FacilityCatchmentMethod.SOURCE_CATCHMENT_RECORD
                )
            elif distance_threshold is not None and facility.point is not None:
                covered_ward_ids.update(
                    _coverage_from_distance_threshold(
                        facility=facility,
                        features=features,
                        distance_threshold=distance_threshold,
                    )
                )
                catchment_method = FacilityCatchmentMethod.DISTANCE_THRESHOLD
            elif include_adjacent_wards and adjacency_by_source_ward.get(primary_ward_id):
                adjacent_ward_ids = adjacency_by_source_ward.get(primary_ward_id, set())
                covered_ward_ids.update(adjacent_ward_ids)
                source_relationship_ids = _relationship_ids_for_covered_wards(
                    version,
                    primary_ward_id,
                    adjacent_ward_ids,
                )
                catchment_method = FacilityCatchmentMethod.SPATIAL_GRAPH_ADJACENT_WARDS
            else:
                catchment_method = FacilityCatchmentMethod.PRIMARY_WARD_ONLY

            covered_ward_ids = {ward_id for ward_id in covered_ward_ids if ward_id in active_wards}
            if primary_ward_id not in covered_ward_ids:
                covered_ward_ids.add(primary_ward_id)
            covered_wards = [active_wards[ward_id] for ward_id in sorted(covered_ward_ids)]
            population_estimate, population_lineage = _population_estimate_for_wards(
                ward_ids=covered_ward_ids,
                population_by_ward_id=population_by_ward_id,
                source_catchment_record=source_catchment_record,
            )
            is_approximate = not externally_verified
            source_kind = (
                FacilityCatchmentSourceKind.EXTERNALLY_VERIFIED
                if externally_verified
                else FacilityCatchmentSourceKind.APPROXIMATED
            )
            confidence = _confidence_for_method(
                method=catchment_method,
                source_catchment_record=source_catchment_record,
                externally_verified=externally_verified,
            )

            catchment = FacilityCatchment.objects.create(
                facility=facility,
                primary_ward=primary_ward,
                geometry_dataset_version=version,
                catchment_method=catchment_method,
                source_kind=source_kind,
                distance_threshold=(
                    distance_threshold
                    if catchment_method == FacilityCatchmentMethod.DISTANCE_THRESHOLD
                    else None
                ),
                distance_unit=DEFAULT_DISTANCE_UNIT,
                population_estimate=population_estimate,
                confidence=confidence,
                is_approximate=is_approximate,
                generated_at=generated_at,
                lineage_metadata=_facility_catchment_lineage(
                    version=version,
                    facility=facility,
                    primary_ward=primary_ward,
                    covered_wards=covered_wards,
                    catchment_method=catchment_method,
                    source_kind=source_kind,
                    distance_threshold=(
                        distance_threshold
                        if catchment_method == FacilityCatchmentMethod.DISTANCE_THRESHOLD
                        else None
                    ),
                    confidence=confidence,
                    is_approximate=is_approximate,
                    population_lineage=population_lineage,
                    source_relationship_ids=source_relationship_ids,
                    source_catchment_record=source_catchment_record,
                ),
            )
            catchment.covered_wards.set(covered_wards)
            created_catchments.append((catchment, covered_wards))
            catchment_summaries.append(
                {
                    "facility_id": facility.id,
                    "facility_name": facility.name,
                    "facility_code": facility.facility_code,
                    "catchment_id": catchment.id,
                    "primary_ward_id": primary_ward_id,
                    "covered_ward_ids": [ward.id for ward in covered_wards],
                    "covered_ward_names": [ward.name for ward in covered_wards],
                    "catchment_method": catchment_method,
                    "source_kind": source_kind,
                    "population_estimate": population_estimate,
                    "confidence": confidence,
                    "is_approximate": is_approximate,
                }
            )

        edge_context_by_key = {}
        for catchment, covered_wards in created_catchments:
            if len(covered_wards) < 2:
                continue
            facility_summary = {
                "facility_id": catchment.facility_id,
                "facility_name": catchment.facility.name,
                "facility_code": catchment.facility.facility_code,
                "facility_catchment_id": catchment.id,
                "catchment_method": catchment.catchment_method,
                "is_approximate": catchment.is_approximate,
            }
            for left, right in combinations(covered_wards, 2):
                for source_ward, target_ward in ((left, right), (right, left)):
                    key = (source_ward.id, target_ward.id)
                    context = edge_context_by_key.setdefault(
                        key,
                        {
                            "source_ward": source_ward,
                            "target_ward": target_ward,
                            "confidence": 0.0,
                            "facility_summaries": [],
                        },
                    )
                    context["confidence"] = max(context["confidence"], catchment.confidence)
                    context["facility_summaries"].append(facility_summary)

        relationship_rows = []
        for context in edge_context_by_key.values():
            source_feature = features_by_ward_id.get(context["source_ward"].id)
            target_feature = features_by_ward_id.get(context["target_ward"].id)
            centroid_distance = (
                _centroid_distance(source_feature, target_feature)
                if source_feature is not None and target_feature is not None
                else None
            )
            shared_boundary_length = (
                _shared_boundary_length(source_feature, target_feature)
                if source_feature is not None and target_feature is not None
                else None
            )
            relationship_rows.append(
                WardSpatialRelationship(
                    source_ward=context["source_ward"],
                    target_ward=context["target_ward"],
                    relationship_type=WardSpatialRelationshipType.SAME_FACILITY_CATCHMENT,
                    geometry_dataset_version=version,
                    shared_boundary_length=shared_boundary_length,
                    centroid_distance=centroid_distance,
                    distance_unit=DEFAULT_DISTANCE_UNIT,
                    confidence=context["confidence"],
                    generation_method=WardSpatialRelationshipSource.DERIVED_FACILITY_CATCHMENT,
                    generated_at=generated_at,
                    lineage_metadata=_same_facility_edge_lineage(
                        version=version,
                        source_ward=context["source_ward"],
                        target_ward=context["target_ward"],
                        facility_summaries=context["facility_summaries"],
                        confidence=context["confidence"],
                    ),
                )
            )
        WardSpatialRelationship.objects.bulk_create(relationship_rows, batch_size=500)

        preserved_manual_catchment_count = FacilityCatchment.objects.filter(
            geometry_dataset_version=version,
            source_kind=FacilityCatchmentSourceKind.MANUAL_OVERRIDE,
        ).count()

        if dry_run:
            transaction.set_rollback(True)

    return {
        "schema_version": FACILITY_CATCHMENT_SCHEMA_VERSION,
        "generated_at": generated_at.isoformat(),
        "county": county,
        "dry_run": dry_run,
        "geometry_dataset": _version_lineage(version),
        "active_facility_count": len(facilities),
        "deleted_generated_catchment_count": deleted_catchment_count,
        "deleted_same_facility_relationship_count": deleted_relationship_count,
        "created_catchment_count": len(created_catchments),
        "created_same_facility_relationship_count": len(relationship_rows),
        "preserved_manual_catchment_count": preserved_manual_catchment_count,
        "skipped_facility_count": len(skipped_facilities),
        "skipped_facilities": skipped_facilities,
        "catchments": catchment_summaries,
        "assumptions": [
            "Generated catchments are approximate unless source metadata explicitly marks them externally verified.",
            "Primary ward is always included because current facilities have canonical ward assignment.",
            "Adjacent ward expansion depends on the phase 1 ward spatial relationship graph.",
            "Distance thresholds use source CRS degrees until projected-distance support is introduced.",
        ],
    }
