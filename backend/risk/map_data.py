import json
import re
from functools import lru_cache
from pathlib import Path

from django.db.models import Count, Prefetch

from .models import (
    Alert,
    CHV,
    HealthFacility,
    RiskScore,
    Ward,
    WardGeometryDatasetVersion,
    WardGeometryFeature,
)


MIGORI_WARD_GEOMETRY_PATH = Path(__file__).resolve().parent / "data" / "migori_wards.geojson"


def normalize_ward_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


@lru_cache(maxsize=1)
def load_migori_ward_geometry() -> dict:
    return json.loads(MIGORI_WARD_GEOMETRY_PATH.read_text())


def load_active_migori_ward_geometry() -> dict:
    active_version = (
        WardGeometryDatasetVersion.objects.select_related("dataset")
        .filter(dataset__slug="migori-ward-boundaries", is_active=True)
        .order_by("-activated_at", "-id")
        .first()
    )
    if active_version is None:
        raise WardGeometryDatasetVersion.DoesNotExist("No active managed Migori ward geometry version found.")

    features = []
    for feature in (
        WardGeometryFeature.objects.filter(dataset_version=active_version)
        .select_related("ward")
        .order_by("display_name_snapshot")
    ):
        properties = dict(feature.properties or {})
        properties.setdefault("name", feature.display_name_snapshot)
        properties.setdefault("ward_code", feature.ward_code_snapshot)
        properties.setdefault("source_name", feature.source_name or feature.display_name_snapshot)
        properties.setdefault("source_ward_code", feature.source_ward_code or feature.ward_code_snapshot)
        properties.setdefault(
            "centroid",
            [round(feature.centroid.x, 6), round(feature.centroid.y, 6)] if feature.centroid else None,
        )
        features.append(
            {
                "type": "Feature",
                "geometry": json.loads(feature.geometry.geojson),
                "properties": properties,
            }
        )

    validation_summary = active_version.validation_summary or {}
    placeholder_geometry_detected = validation_summary.get("placeholder_geometry_detected", False)
    return {
        "type": "FeatureCollection",
        "metadata": {
            "county": validation_summary.get("county", "Migori"),
            "geometry_source": f"managed:{active_version.dataset.slug}:{active_version.version_label}",
            "source_dataset": active_version.source_name,
            "source_license": active_version.source_license,
            "source_crs": active_version.source_crs,
            "geometry_feature_count": active_version.feature_count or len(features),
            "expected_ward_count": active_version.expected_feature_count or len(features),
            "missing_source_wards": active_version.missing_source_wards or [],
            "placeholder_geometry_detected": placeholder_geometry_detected,
            "geometry_note": (
                "The active managed geometry version appears to contain placeholder polygons."
                if placeholder_geometry_detected
                else None
            ),
            "dataset_slug": active_version.dataset.slug,
            "dataset_version_label": active_version.version_label,
            "activated_at": active_version.activated_at.isoformat() if active_version.activated_at else None,
        },
        "features": features,
    }


def _ring_is_axis_aligned_rectangle(ring: list[list[float]]) -> bool:
    if len(ring) != 5 or ring[0] != ring[-1]:
        return False

    unique_points = ring[:-1]
    if len({tuple(point) for point in unique_points}) != 4:
        return False

    lons = {point[0] for point in unique_points}
    lats = {point[1] for point in unique_points}
    if len(lons) != 2 or len(lats) != 2:
        return False

    for index in range(len(unique_points)):
        current = unique_points[index]
        nxt = unique_points[(index + 1) % len(unique_points)]
        if current[0] != nxt[0] and current[1] != nxt[1]:
            return False

    return True


def geometry_looks_placeholder(feature_collection: dict) -> bool:
    features = feature_collection.get("features", [])
    if not features:
        return False

    for feature in features:
        geometry = feature.get("geometry", {})
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates", [])

        if geometry_type == "Polygon":
            outer_ring = coordinates[0] if coordinates else []
            if not _ring_is_axis_aligned_rectangle(outer_ring):
                return False
            continue

        if geometry_type == "MultiPolygon":
            first_polygon = coordinates[0] if coordinates else []
            outer_ring = first_polygon[0] if first_polygon else []
            if not _ring_is_axis_aligned_rectangle(outer_ring):
                return False
            continue

        return False

    return True


def build_migori_ward_map_summary(ward_queryset, *, limit_to_backend_wards: bool = False) -> dict:
    geometry = load_active_migori_ward_geometry()
    metadata = geometry.get("metadata", {})
    placeholder_geometry_detected = metadata.get("placeholder_geometry_detected", False)
    wards = list(
        ward_queryset.prefetch_related(
            Prefetch(
                "risk_scores",
                queryset=RiskScore.objects.order_by("-generated_at"),
            )
        )
    )
    ward_ids = [ward.id for ward in wards]
    ward_by_name = {normalize_ward_name(ward.name): ward for ward in wards}
    ward_by_code = {
        str(ward.ward_code).strip(): ward
        for ward in wards
        if isinstance(ward.ward_code, str) and ward.ward_code.strip()
    }
    allowed_names = set(ward_by_name)
    allowed_codes = set(ward_by_code)

    chv_counts = {
        row["ward_id"]: row["count"]
        for row in CHV.objects.filter(ward_id__in=ward_ids)
        .values("ward_id")
        .annotate(count=Count("id"))
    }
    active_chv_counts = {
        row["ward_id"]: row["count"]
        for row in CHV.objects.filter(ward_id__in=ward_ids, is_active=True)
        .values("ward_id")
        .annotate(count=Count("id"))
    }
    alert_counts = {
        row["ward_id"]: row["count"]
        for row in Alert.objects.filter(ward_id__in=ward_ids)
        .values("ward_id")
        .annotate(count=Count("id"))
    }
    facility_counts = {
        row["ward_id"]: row["count"]
        for row in HealthFacility.objects.filter(ward_id__in=ward_ids, is_active=True)
        .values("ward_id")
        .annotate(count=Count("id"))
    }

    features = []
    geometry_name_keys = set()
    geometry_code_keys = set()
    ward_code_match_count = 0
    ward_name_fallback_match_count = 0

    for feature in geometry["features"]:
        properties = feature["properties"]
        ward_name = properties["name"]
        normalized_name = normalize_ward_name(ward_name)
        ward_code = str(properties.get("ward_code", "")).strip()

        if limit_to_backend_wards and ward_code not in allowed_codes and normalized_name not in allowed_names:
            continue

        ward = ward_by_code.get(ward_code) if ward_code else None
        match_source = "ward_code" if ward else None
        if ward is None:
            ward = ward_by_name.get(normalized_name)
            if ward is not None:
                match_source = "name"

        ward_risks = list(ward.risk_scores.all()[:1]) if ward else []
        latest_risk = ward_risks[0] if ward_risks else None
        geometry_name_keys.add(normalized_name)
        if ward_code:
            geometry_code_keys.add(ward_code)
        if match_source == "ward_code":
            ward_code_match_count += 1
        elif match_source == "name":
            ward_name_fallback_match_count += 1
        features.append(
            {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": {
                    "name": ward_name,
                    "ward_code": ward_code,
                    "source_name": properties.get("source_name", ward_name),
                    "source_ward_code": properties.get("source_ward_code", ward_code or None),
                    "centroid": properties["centroid"],
                    "backend_ward_id": ward.id if ward else None,
                    "backend_public_id": str(ward.public_id) if ward else None,
                    "has_backend_ward": ward is not None,
                    "matching_source": match_source,
                    "risk_level": latest_risk.risk_level if latest_risk else (ward.current_risk_level if ward else None),
                    "risk_score": latest_risk.score if latest_risk else (ward.current_risk_score if ward else None),
                    "predicted_cases": latest_risk.predicted_cases if latest_risk else 0,
                    "risk_generated_at": latest_risk.generated_at.isoformat() if latest_risk else None,
                    "chv_count": chv_counts.get(ward.id, 0) if ward else 0,
                    "active_chv_count": active_chv_counts.get(ward.id, 0) if ward else 0,
                    "alert_count": alert_counts.get(ward.id, 0) if ward else 0,
                    "facility_count": facility_counts.get(ward.id, 0) if ward else 0,
                },
            }
        )

    backend_wards_without_geometry = sorted(
        ward.name
        for ward in wards
        if (
            (ward.ward_code.strip() not in geometry_code_keys if isinstance(ward.ward_code, str) and ward.ward_code.strip() else True)
            and normalize_ward_name(ward.name) not in geometry_name_keys
        )
    )
    return {
        "type": "FeatureCollection",
        "metadata": {
            "county": metadata.get("county", "Migori"),
            "geometry_source": metadata.get("geometry_source"),
            "source_dataset": metadata.get("source_dataset"),
            "source_license": metadata.get("source_license"),
            "source_crs": metadata.get("source_crs"),
            "geometry_feature_count": metadata.get("geometry_feature_count", len(geometry.get("features", []))),
            "expected_ward_count": metadata.get("expected_ward_count", len(features)),
            "missing_source_wards": metadata.get("missing_source_wards", []),
            "backend_ward_match_count": sum(1 for feature in features if feature["properties"]["has_backend_ward"]),
            "backend_ward_code_match_count": ward_code_match_count,
            "backend_ward_name_fallback_match_count": ward_name_fallback_match_count,
            "matching_strategy": "ward_code_then_name",
            "returned_feature_count": len(features),
            "backend_wards_without_geometry": backend_wards_without_geometry,
            "placeholder_geometry_detected": placeholder_geometry_detected,
            "geometry_note": metadata.get("geometry_note"),
            "dataset_slug": metadata.get("dataset_slug"),
            "dataset_version_label": metadata.get("dataset_version_label"),
            "activated_at": metadata.get("activated_at"),
        },
        "features": features,
    }
