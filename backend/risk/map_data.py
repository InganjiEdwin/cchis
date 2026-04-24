import json
import re
from functools import lru_cache
from pathlib import Path

from django.db.models import Count, Prefetch

from .models import Alert, CHV, HealthFacility, RiskScore, Ward


MIGORI_WARD_GEOMETRY_PATH = Path(__file__).resolve().parent / "data" / "migori_wards.geojson"


def normalize_ward_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


@lru_cache(maxsize=1)
def load_migori_ward_geometry() -> dict:
    return json.loads(MIGORI_WARD_GEOMETRY_PATH.read_text())


def build_migori_ward_map_summary(ward_queryset, *, limit_to_backend_wards: bool = False) -> dict:
    geometry = load_migori_ward_geometry()
    wards = list(
        ward_queryset.prefetch_related(
            Prefetch(
                "risk_scores",
                queryset=RiskScore.objects.order_by("-generated_at"),
            )
        )
    )
    ward_ids = [ward.id for ward in wards]
    ward_by_key = {normalize_ward_name(ward.name): ward for ward in wards}
    allowed_keys = set(ward_by_key)

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
    geometry_keys = set()

    for feature in geometry["features"]:
        properties = feature["properties"]
        ward_name = properties["name"]
        normalized_name = normalize_ward_name(ward_name)

        if limit_to_backend_wards and normalized_name not in allowed_keys:
            continue

        ward = ward_by_key.get(normalized_name)
        ward_risks = list(ward.risk_scores.all()[:1]) if ward else []
        latest_risk = ward_risks[0] if ward_risks else None
        geometry_keys.add(normalized_name)
        features.append(
            {
                "type": "Feature",
                "geometry": feature["geometry"],
                "properties": {
                    "name": ward_name,
                    "ward_code": properties["ward_code"],
                    "centroid": properties["centroid"],
                    "backend_ward_id": ward.id if ward else None,
                    "backend_public_id": str(ward.public_id) if ward else None,
                    "has_backend_ward": ward is not None,
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
        ward.name for key, ward in ward_by_key.items() if key not in geometry_keys
    )
    metadata = geometry.get("metadata", {})

    return {
        "type": "FeatureCollection",
        "metadata": {
            "county": metadata.get("county", "Migori"),
            "geometry_source": "backend/risk/data/migori_wards.geojson",
            "geometry_feature_count": metadata.get("geometry_feature_count", len(geometry.get("features", []))),
            "expected_ward_count": metadata.get("expected_ward_count", len(features)),
            "missing_source_wards": metadata.get("missing_source_wards", []),
            "backend_ward_match_count": sum(1 for feature in features if feature["properties"]["has_backend_ward"]),
            "returned_feature_count": len(features),
            "backend_wards_without_geometry": backend_wards_without_geometry,
        },
        "features": features,
    }
