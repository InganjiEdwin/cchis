from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from risk.map_data import geometry_looks_placeholder, normalize_ward_name
from risk.models import Ward


def load_geojson_payload(path: Path) -> dict:
    return json.loads(path.read_text())


def compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def feature_matches_county(feature: dict, county: str) -> bool:
    properties = feature.get("properties", {})
    county_value = properties.get("county") or properties.get("COUNTY")
    return isinstance(county_value, str) and county_value.strip().lower() == county.lower()


def feature_name(properties: dict) -> str | None:
    for key in ("name", "ward", "WARD", "source_name"):
        value = properties.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def feature_code(properties: dict) -> str | None:
    for key in ("ward_code", "wardcode", "WARD_CODE", "code", "source_ward_code"):
        value = properties.get(key)
        if value is None:
            continue
        value_str = str(value).strip()
        if value_str:
            return value_str
    return None


def feature_label(feature: dict) -> str:
    properties = feature.get("properties", {})
    return feature_name(properties) or feature_code(properties) or "Unnamed feature"


def detect_runtime_crs(payload: dict, features: list[dict]) -> str:
    crs = payload.get("crs")
    if isinstance(crs, dict):
        properties = crs.get("properties", {})
        name = properties.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()

    coordinates = []
    for feature in features:
        geometry = feature.get("geometry", {})
        geometry_type = geometry.get("type")
        values = geometry.get("coordinates", [])

        if geometry_type == "Polygon":
            coordinates.extend(values[0] if values else [])
        elif geometry_type == "MultiPolygon":
            for polygon in values:
                if polygon:
                    coordinates.extend(polygon[0])

    if not coordinates:
        return "unknown"

    lon_in_range = all(-180 <= point[0] <= 180 for point in coordinates if len(point) >= 2)
    lat_in_range = all(-90 <= point[1] <= 90 for point in coordinates if len(point) >= 2)
    if lon_in_range and lat_in_range:
        return "EPSG:4326 (assumed from GeoJSON coordinate ranges)"

    return "unknown"


def build_geometry_validation_summary(payload: dict, county: str) -> dict:
    if payload.get("type") != "FeatureCollection":
        raise ValueError("GeoJSON must be a FeatureCollection.")

    features = payload.get("features", [])
    county_features = [feature for feature in features if feature_matches_county(feature, county)]
    if not county_features:
        raise ValueError(f"No features found for county '{county}'.")

    extracted_payload = {
        "type": "FeatureCollection",
        "metadata": payload.get("metadata", {}),
        "features": county_features,
    }

    geometry_type_counts = Counter(
        feature.get("geometry", {}).get("type", "UNKNOWN") for feature in county_features
    )
    invalid_geometry_features = [
        feature_label(feature)
        for feature in county_features
        if feature.get("geometry", {}).get("type") not in {"Polygon", "MultiPolygon"}
    ]

    normalized_name_counts = Counter()
    code_counts = Counter()
    source_name_map = {}
    source_code_set = set()

    for feature in county_features:
        properties = feature.get("properties", {})
        name = feature_name(properties)
        code = feature_code(properties)
        if name:
            normalized_name = normalize_ward_name(name)
            normalized_name_counts[normalized_name] += 1
            source_name_map[normalized_name] = name
        if code:
            code_str = str(code)
            code_counts[code_str] += 1
            source_code_set.add(code_str)

    duplicate_source_names = sorted(name for name, count in normalized_name_counts.items() if count > 1)
    duplicate_source_codes = sorted(code for code, count in code_counts.items() if count > 1)

    backend_wards = list(
        Ward.objects.filter(county__iexact=county).order_by("name").values("name", "ward_code")
    )
    expected_names = {
        normalize_ward_name(row["name"]): row["name"]
        for row in backend_wards
        if row["name"]
    }
    expected_codes = {
        str(row["ward_code"]): row["name"]
        for row in backend_wards
        if row["ward_code"]
    }

    missing_backend_ward_names = sorted(
        display_name
        for normalized_name, display_name in expected_names.items()
        if normalized_name not in source_name_map
    )
    missing_backend_ward_codes = sorted(code for code in expected_codes if code not in source_code_set)
    extra_source_names = sorted(
        source_name
        for normalized_name, source_name in source_name_map.items()
        if normalized_name not in expected_names
    )

    backend_ward_code_match_count = 0
    backend_ward_name_fallback_match_count = 0
    backend_ward_unmatched_feature_count = 0
    for feature in county_features:
        properties = feature.get("properties", {})
        code = feature_code(properties)
        name = feature_name(properties)
        if code and str(code) in expected_codes:
            backend_ward_code_match_count += 1
        elif name and normalize_ward_name(name) in expected_names:
            backend_ward_name_fallback_match_count += 1
        else:
            backend_ward_unmatched_feature_count += 1

    return {
        "county": county,
        "source_feature_count": len(features),
        "filtered_feature_count": len(county_features),
        "backend_ward_count": len(backend_wards),
        "runtime_crs": detect_runtime_crs(payload, county_features),
        "geometry_type_counts": dict(geometry_type_counts),
        "invalid_geometry_features": invalid_geometry_features,
        "placeholder_geometry_detected": geometry_looks_placeholder(extracted_payload),
        "duplicate_source_names": duplicate_source_names,
        "duplicate_source_codes": duplicate_source_codes,
        "missing_backend_ward_names": missing_backend_ward_names,
        "missing_backend_ward_codes": missing_backend_ward_codes,
        "extra_source_names": extra_source_names,
        "backend_ward_code_match_count": backend_ward_code_match_count,
        "backend_ward_name_fallback_match_count": backend_ward_name_fallback_match_count,
        "backend_ward_unmatched_feature_count": backend_ward_unmatched_feature_count,
    }
