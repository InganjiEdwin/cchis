from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REFERENCE_CSV = Path(__file__).resolve().parent / "data" / "kenya_counties_wards.csv"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "data" / "migori_wards.geojson"


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def format_ward_code(raw_code: str) -> str:
    return f"KE-WARD-{int(raw_code):04d}"


def parse_raw_ward_code(value: str | None) -> str:
    if not value:
        return ""
    value = str(value).strip()
    if not value:
        return ""
    if value.startswith("KE-WARD-"):
        suffix = value.removeprefix("KE-WARD-").strip()
        return str(int(suffix)) if suffix.isdigit() else ""
    return str(int(value)) if value.isdigit() else ""


def load_reference_rows(reference_csv: Path, county: str) -> tuple[dict[str, dict], dict[str, dict]]:
    by_raw_code: dict[str, dict] = {}
    by_name: dict[str, dict] = {}

    with reference_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            row_county = row["COUNTY NAME"].strip().title()
            if row_county != county:
                continue

            raw_code = row["WARD ID"].strip()
            ward_name = row["WARD NAME"].strip().title()
            canonical = {
                "raw_code": raw_code,
                "ward_code": format_ward_code(raw_code),
                "name": ward_name,
                "county": row_county,
                "sub_county": row["CONSTITUENCY NAME"].strip().title(),
            }
            by_raw_code[raw_code] = canonical
            by_name[normalize_name(ward_name)] = canonical

    if not by_raw_code:
        raise ValueError(f"No reference wards found for county '{county}' in {reference_csv}")

    return by_raw_code, by_name


def polygon_area_and_centroid(ring: list[list[float]]) -> tuple[float, tuple[float, float] | None]:
    if len(ring) < 4:
        return 0.0, None

    area_term = 0.0
    centroid_x_term = 0.0
    centroid_y_term = 0.0

    for index in range(len(ring) - 1):
        x1, y1 = ring[index]
        x2, y2 = ring[index + 1]
        cross = (x1 * y2) - (x2 * y1)
        area_term += cross
        centroid_x_term += (x1 + x2) * cross
        centroid_y_term += (y1 + y2) * cross

    signed_area = area_term / 2
    if abs(signed_area) < 1e-12:
        return 0.0, None

    centroid = (
        centroid_x_term / (6 * signed_area),
        centroid_y_term / (6 * signed_area),
    )
    return abs(signed_area), centroid


def bbox_centroid(coordinates: list[tuple[float, float]]) -> list[float]:
    lons = [point[0] for point in coordinates]
    lats = [point[1] for point in coordinates]
    return [round((min(lons) + max(lons)) / 2, 6), round((min(lats) + max(lats)) / 2, 6)]


def geometry_centroid(geometry: dict) -> list[float] | None:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    best_area = 0.0
    best_centroid: tuple[float, float] | None = None
    all_points: list[tuple[float, float]] = []

    if geometry_type == "Polygon":
        rings = coordinates
        for ring in rings:
            all_points.extend((float(lon), float(lat)) for lon, lat in ring)
        if rings:
            area, centroid = polygon_area_and_centroid(rings[0])
            best_area = area
            best_centroid = centroid
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates:
            if not polygon:
                continue
            outer_ring = polygon[0]
            all_points.extend((float(lon), float(lat)) for lon, lat in outer_ring)
            area, centroid = polygon_area_and_centroid(outer_ring)
            if area > best_area and centroid is not None:
                best_area = area
                best_centroid = centroid

    if best_centroid is not None:
        return [round(best_centroid[0], 6), round(best_centroid[1], 6)]

    if all_points:
        return bbox_centroid(all_points)

    return None


def build_output_feature(source_feature: dict, canonical_row: dict) -> dict:
    source_properties = source_feature.get("properties", {})
    source_code = (
        parse_raw_ward_code(source_properties.get("wardcode"))
        or parse_raw_ward_code(source_properties.get("source_ward_code"))
        or parse_raw_ward_code(source_properties.get("ward_code"))
    )
    source_name = str(
        source_properties.get("ward")
        or source_properties.get("source_name")
        or source_properties.get("name")
        or ""
    ).strip()

    return {
        "type": "Feature",
        "geometry": source_feature["geometry"],
        "properties": {
            "name": canonical_row["name"],
            "ward_code": canonical_row["ward_code"],
            "ward_source_id": str(
                source_properties.get("id")
                or source_properties.get("Rownum")
                or source_properties.get("ward_source_id")
                or source_code
                or canonical_row["raw_code"]
            ),
            "source_name": source_name or canonical_row["name"],
            "source_ward_code": source_code or canonical_row["raw_code"],
            "county": canonical_row["county"],
            "sub_county": canonical_row["sub_county"],
            "constituency": (
                source_properties.get("const")
                or source_properties.get("constituency")
                or canonical_row["sub_county"]
            ),
            "centroid": geometry_centroid(source_feature["geometry"]),
        },
    }


def prepare_geometry_payload(input_path: Path, reference_csv: Path, county: str, source_url: str) -> dict:
    payload = json.loads(input_path.read_text())
    if payload.get("type") != "FeatureCollection":
        raise ValueError("Input GeoJSON must be a FeatureCollection.")

    reference_by_code, reference_by_name = load_reference_rows(reference_csv, county)
    filtered_features = []
    matched_codes: set[str] = set()
    matched_names: set[str] = set()
    duplicate_codes: list[str] = []

    for source_feature in payload.get("features", []):
        properties = source_feature.get("properties", {})
        if str(properties.get("county", "")).strip().title() != county:
            continue

        raw_code = (
            parse_raw_ward_code(properties.get("wardcode"))
            or parse_raw_ward_code(properties.get("source_ward_code"))
            or parse_raw_ward_code(properties.get("ward_code"))
        )
        source_name = str(
            properties.get("ward")
            or properties.get("source_name")
            or properties.get("name")
            or ""
        ).strip()
        canonical_row = reference_by_code.get(raw_code)
        if canonical_row is None and source_name:
            canonical_row = reference_by_name.get(normalize_name(source_name))

        if canonical_row is None:
            continue

        if canonical_row["raw_code"] in matched_codes:
            duplicate_codes.append(canonical_row["raw_code"])
            continue

        filtered_features.append(build_output_feature(source_feature, canonical_row))
        matched_codes.add(canonical_row["raw_code"])
        matched_names.add(normalize_name(canonical_row["name"]))

    missing_wards = [
        row["name"]
        for raw_code, row in sorted(reference_by_code.items(), key=lambda item: int(item[0]))
        if raw_code not in matched_codes
    ]

    output_payload = {
        "type": "FeatureCollection",
        "metadata": {
            "county": county,
            "source": source_url,
            "source_dataset": "benaboki/Kenya-County-Assembly-Boundaries",
            "source_license": "CC-BY-4.0",
            "source_crs": "EPSG:4326",
            "selection_rule": f"county == {county}",
            "geometry_feature_count": len(filtered_features),
            "expected_ward_count": len(reference_by_code),
            "missing_source_wards": missing_wards,
            "excluded_source_duplicates": [
                {
                    "ward_code": format_ward_code(code),
                    "source_ward_code": code,
                }
                for code in sorted(set(duplicate_codes), key=int)
            ],
        },
        "features": filtered_features,
    }

    return output_payload


def prepare_geometry(input_path: Path, output_path: Path, reference_csv: Path, county: str, source_url: str) -> dict:
    output_payload = prepare_geometry_payload(input_path, reference_csv, county, source_url)
    output_path.write_text(json.dumps(output_payload, indent=2))
    return output_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a canonical Migori ward GeoJSON artifact from a ward boundary source."
    )
    parser.add_argument("--input", required=True, help="Path to the input GeoJSON source.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to write the Migori GeoJSON artifact.")
    parser.add_argument(
        "--reference-csv",
        default=str(DEFAULT_REFERENCE_CSV),
        help="Path to the canonical Kenya wards CSV used for canonical names and ward codes.",
    )
    parser.add_argument("--county", default="Migori", help="County name to extract.")
    parser.add_argument(
        "--source-url",
        default="https://github.com/benaboki/Kenya-County-Assembly-Boundaries",
        help="Source URL to record in metadata.",
    )
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    reference_csv = Path(args.reference_csv).expanduser().resolve()

    if not input_path.exists():
        raise SystemExit(f"Input source not found: {input_path}")
    if not reference_csv.exists():
        raise SystemExit(f"Reference CSV not found: {reference_csv}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    prepared = prepare_geometry(input_path, output_path, reference_csv, args.county.strip().title(), args.source_url)

    metadata = prepared["metadata"]
    print("Prepared Migori ward geometry")
    print(f"input: {input_path}")
    print(f"output: {output_path}")
    print(f"feature_count: {metadata['geometry_feature_count']}")
    print(f"expected_ward_count: {metadata['expected_ward_count']}")
    print(f"missing_source_wards: {', '.join(metadata['missing_source_wards']) if metadata['missing_source_wards'] else 'none'}")
    print(
        "excluded_source_duplicates: "
        + (
            ", ".join(item["source_ward_code"] for item in metadata["excluded_source_duplicates"])
            if metadata["excluded_source_duplicates"]
            else "none"
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
