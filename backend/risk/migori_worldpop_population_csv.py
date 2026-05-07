from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TextIO
from urllib.parse import urlparse

import requests

from risk.map_data import MIGORI_WARD_GEOMETRY_PATH
from risk.migori_population_source_inventory import EXPECTED_WORLDPOP_FILE_URL


RISK_DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_PHASE0_INVENTORY_PATH = RISK_DATA_DIR / "source_feeds" / "migori_knbs_worldpop_phase0_inventory.json"
DEFAULT_OUTPUT_CSV_PATH = RISK_DATA_DIR / "source_feeds" / "migori_worldpop_2026_population.csv"
DEFAULT_SUMMARY_PATH = RISK_DATA_DIR / "source_feeds" / "migori_worldpop_2026_population_summary.json"
DEFAULT_RASTER_CACHE_DIR = RISK_DATA_DIR / "source_cache" / "worldpop"
AGGREGATION_METHOD = "ward_sum_from_worldpop_100m_grid_pixel_centers"
SPATIAL_RESOLUTION = "100m"
POPULATION_DENSITY_UNIT = "people_per_km2"
EARTH_RADIUS_METERS = 6_371_008.8
EXPECTED_WORLDPOP_PIXEL_SIZE_DEGREES = 1 / 1200
PIXEL_SIZE_TOLERANCE_DEGREES = 0.00000001


@dataclass(frozen=True)
class WardPolygon:
    ward_code: str
    ward_name: str
    sub_county: str
    geometry: dict
    bbox: tuple[float, float, float, float]
    area_km2: float


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def worldpop_file_url_from_inventory(inventory: dict) -> str:
    files = ((inventory.get("worldpop") or {}).get("record") or {}).get("files") or []
    for file_url in files:
        value = str(file_url).strip()
        if value:
            return value
    raise ValueError("Phase 0 inventory does not contain a WorldPop file URL.")


def default_raster_cache_path(source_url: str) -> Path:
    parsed = urlparse(source_url)
    filename = Path(parsed.path).name or "worldpop_population.tif"
    return DEFAULT_RASTER_CACHE_DIR / filename


def download_file(source_url: str, destination: Path, *, timeout: int = 60) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return {
            "downloaded": False,
            "path": str(destination),
            "bytes": destination.stat().st_size,
            "sha256": file_sha256(destination),
        }

    tmp_path = destination.with_suffix(destination.suffix + ".tmp")
    with requests.get(source_url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with tmp_path.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    tmp_path.replace(destination)
    return {
        "downloaded": True,
        "path": str(destination),
        "bytes": destination.stat().st_size,
        "sha256": file_sha256(destination),
    }


def raster_metadata_with_gdal(raster_path: Path, *, gdalinfo: str = "gdalinfo") -> dict:
    command = [gdalinfo, "-json", str(raster_path)]
    completed = subprocess.run(command, capture_output=True, check=True, text=True)
    payload = json.loads(completed.stdout)
    coordinate_system = payload.get("coordinateSystem") or {}
    wkt = str(coordinate_system.get("wkt") or "")
    geo_transform = payload.get("geoTransform") or []
    bands = payload.get("bands") or []
    first_band = bands[0] if bands else {}
    pixel_width = abs(float(geo_transform[1])) if len(geo_transform) >= 2 else None
    pixel_height = abs(float(geo_transform[5])) if len(geo_transform) >= 6 else None
    return {
        "gdalinfo_command": command,
        "driver": payload.get("driverShortName", ""),
        "size": payload.get("size", []),
        "geo_transform": geo_transform,
        "pixel_width_degrees": pixel_width,
        "pixel_height_degrees": pixel_height,
        "corner_coordinates": payload.get("cornerCoordinates") or {},
        "band_count": len(bands),
        "first_band_type": first_band.get("type", ""),
        "first_band_no_data_value": first_band.get("noDataValue"),
        "crs_declared": bool(wkt),
        "crs_wgs84_like": "WGS 84" in wkt or 'ID["EPSG",4326' in wkt,
    }


def iter_positions(coordinates) -> Iterable[tuple[float, float]]:
    if not coordinates:
        return
    first = coordinates[0]
    if isinstance(first, (int, float)):
        if len(coordinates) >= 2:
            yield float(coordinates[0]), float(coordinates[1])
        return
    for item in coordinates:
        yield from iter_positions(item)


def geometry_bbox(geometry: dict) -> tuple[float, float, float, float]:
    points = list(iter_positions(geometry.get("coordinates") or []))
    if not points:
        raise ValueError("Geometry has no coordinates.")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def geometry_collection_bbox(wards: Iterable[WardPolygon], *, padding_degrees: float = 0.01) -> tuple[float, float, float, float]:
    bboxes = [ward.bbox for ward in wards]
    if not bboxes:
        raise ValueError("No ward polygons were supplied.")
    minx = min(bbox[0] for bbox in bboxes) - padding_degrees
    miny = min(bbox[1] for bbox in bboxes) - padding_degrees
    maxx = max(bbox[2] for bbox in bboxes) + padding_degrees
    maxy = max(bbox[3] for bbox in bboxes) + padding_degrees
    return minx, miny, maxx, maxy


def geometry_polygons(geometry: dict) -> Iterable[list[list[list[float]]]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if geometry_type == "Polygon":
        yield coordinates
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates:
            yield polygon


def ring_area_km2(ring: list[list[float]]) -> float:
    if len(ring) < 4:
        return 0.0
    latitudes = [math.radians(float(point[1])) for point in ring if len(point) >= 2]
    if not latitudes:
        return 0.0
    reference_latitude = sum(latitudes) / len(latitudes)
    projected: list[tuple[float, float]] = []
    for point in ring:
        lon = math.radians(float(point[0]))
        lat = math.radians(float(point[1]))
        projected.append(
            (
                EARTH_RADIUS_METERS * lon * math.cos(reference_latitude),
                EARTH_RADIUS_METERS * lat,
            )
        )
    area = 0.0
    for index, current in enumerate(projected):
        nxt = projected[(index + 1) % len(projected)]
        area += current[0] * nxt[1] - nxt[0] * current[1]
    return abs(area) / 2.0 / 1_000_000.0


def geometry_area_km2(geometry: dict) -> float:
    total = 0.0
    for polygon in geometry_polygons(geometry):
        if not polygon:
            continue
        total += ring_area_km2(polygon[0])
        for hole in polygon[1:]:
            total -= ring_area_km2(hole)
    return max(total, 0.0)


def point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    if len(ring) < 4:
        return False
    j = len(ring) - 1
    for i, current in enumerate(ring):
        previous = ring[j]
        xi, yi = float(current[0]), float(current[1])
        xj, yj = float(previous[0]), float(previous[1])
        intersects = (yi > y) != (yj > y)
        if intersects:
            x_intersection = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_intersection:
                inside = not inside
        j = i
    return inside


def point_in_polygon(x: float, y: float, polygon: list[list[list[float]]]) -> bool:
    if not polygon or not point_in_ring(x, y, polygon[0]):
        return False
    return not any(point_in_ring(x, y, hole) for hole in polygon[1:])


def geometry_contains_point(geometry: dict, x: float, y: float) -> bool:
    for polygon in geometry_polygons(geometry):
        if point_in_polygon(x, y, polygon):
            return True
    return False


def load_ward_polygons(geojson_path: Path, *, county: str = "Migori") -> list[WardPolygon]:
    payload = load_json(geojson_path)
    wards: list[WardPolygon] = []
    for feature in payload.get("features", []):
        properties = feature.get("properties") or {}
        if str(properties.get("county") or "").strip().lower() != county.lower():
            continue
        geometry = feature.get("geometry") or {}
        ward_code = str(properties.get("ward_code") or "").strip()
        ward_name = str(properties.get("name") or properties.get("source_name") or "").strip()
        if not ward_code or not ward_name:
            raise ValueError(f"GeoJSON feature is missing ward_code or name: {properties}")
        wards.append(
            WardPolygon(
                ward_code=ward_code,
                ward_name=ward_name,
                sub_county=str(properties.get("sub_county") or properties.get("constituency") or "").strip(),
                geometry=geometry,
                bbox=geometry_bbox(geometry),
                area_km2=geometry_area_km2(geometry),
            )
        )
    if not wards:
        raise ValueError(f"No GeoJSON features found for county '{county}'.")
    return sorted(wards, key=lambda ward: ward.ward_name)


def candidate_wards_for_point(wards: list[WardPolygon], x: float, y: float) -> Iterable[WardPolygon]:
    for ward in wards:
        minx, miny, maxx, maxy = ward.bbox
        if minx <= x <= maxx and miny <= y <= maxy:
            yield ward


def parse_xyz_line(line: str) -> tuple[float, float, float] | None:
    parts = line.strip().split()
    if len(parts) < 3:
        return None
    try:
        x = float(parts[0])
        y = float(parts[1])
        value = float(parts[2])
    except ValueError:
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return x, y, value


def aggregate_xyz_stream(xyz_stream: TextIO, wards: list[WardPolygon]) -> dict:
    totals = {ward.ward_code: 0.0 for ward in wards}
    assigned_pixels = {ward.ward_code: 0 for ward in wards}
    source_pixel_count = 0
    source_positive_pixel_count = 0
    source_positive_population_value = 0.0
    assigned_pixel_count = 0
    assigned_population_value = 0.0
    unassigned_positive_pixel_count = 0
    unassigned_positive_population_value = 0.0

    for line in xyz_stream:
        parsed = parse_xyz_line(line)
        if parsed is None:
            continue
        x, y, value = parsed
        source_pixel_count += 1
        if value > 0:
            source_positive_pixel_count += 1
            source_positive_population_value += value
        matched_ward = None
        for ward in candidate_wards_for_point(wards, x, y):
            if geometry_contains_point(ward.geometry, x, y):
                matched_ward = ward
                break
        if matched_ward is None:
            if value > 0:
                unassigned_positive_pixel_count += 1
                unassigned_positive_population_value += value
            continue
        totals[matched_ward.ward_code] += value
        assigned_population_value += value
        assigned_pixels[matched_ward.ward_code] += 1
        assigned_pixel_count += 1

    return {
        "totals": totals,
        "assigned_pixels": assigned_pixels,
        "source_pixel_count": source_pixel_count,
        "source_positive_pixel_count": source_positive_pixel_count,
        "source_positive_population_value": source_positive_population_value,
        "assigned_pixel_count": assigned_pixel_count,
        "assigned_population_value": assigned_population_value,
        "unassigned_positive_pixel_count": unassigned_positive_pixel_count,
        "unassigned_positive_population_value": unassigned_positive_population_value,
    }


def aggregate_raster_with_gdal(
    *,
    raster_path: Path,
    wards: list[WardPolygon],
    gdal_translate: str = "gdal_translate",
) -> dict:
    minx, miny, maxx, maxy = geometry_collection_bbox(wards)
    command = [
        gdal_translate,
        "-q",
        "-projwin",
        str(minx),
        str(maxy),
        str(maxx),
        str(miny),
        "-of",
        "XYZ",
        str(raster_path),
        "/vsistdout/",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.stdout is None:
        raise RuntimeError("gdal_translate did not provide stdout.")
    aggregate = aggregate_xyz_stream(process.stdout, wards)
    stderr = process.stderr.read() if process.stderr is not None else ""
    returncode = process.wait()
    if returncode != 0:
        raise RuntimeError(f"gdal_translate failed with exit code {returncode}: {stderr.strip()}")
    aggregate["gdal_command"] = command
    aggregate["gdal_stderr"] = stderr.strip()
    aggregate["bbox"] = {
        "min_lon": minx,
        "min_lat": miny,
        "max_lon": maxx,
        "max_lat": maxy,
        "padding_degrees": 0.01,
    }
    return aggregate


def csv_rows_for_aggregates(
    *,
    wards: list[WardPolygon],
    aggregate: dict,
    source_ref: str,
    release_version: str,
    geojson_sha256: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    totals = aggregate["totals"]
    assigned_pixels = aggregate["assigned_pixels"]
    for ward in wards:
        raw_total = float(totals.get(ward.ward_code, 0.0))
        rounded_total = int(round(raw_total))
        density = raw_total / ward.area_km2 if ward.area_km2 else 0.0
        rows.append(
            {
                "ward_code": ward.ward_code,
                "ward_name": ward.ward_name,
                "population_total": str(max(rounded_total, 0)),
                "population_density": f"{density:.3f}",
                "gridded_population_value": f"{raw_total:.3f}",
                "aggregation_method": AGGREGATION_METHOD,
                "spatial_resolution": SPATIAL_RESOLUTION,
                "unit": POPULATION_DENSITY_UNIT,
                "truth_class": "spatially_aggregated_source",
                "source_kind": "live",
                "freshness_state": "fresh",
                "source_ref": source_ref,
                "notes": (
                    f"{release_version}; ward_area_km2={ward.area_km2:.3f}; "
                    f"assigned_pixels={assigned_pixels.get(ward.ward_code, 0)}; "
                    f"polygon_sha256={geojson_sha256}; pixel-center aggregation."
                ),
            }
        )
    return rows


def write_population_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "ward_code",
        "ward_name",
        "population_total",
        "population_density",
        "gridded_population_value",
        "aggregation_method",
        "spatial_resolution",
        "unit",
        "truth_class",
        "source_kind",
        "freshness_state",
        "source_ref",
        "notes",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_summary(
    *,
    rows: list[dict[str, str]],
    aggregate: dict,
    inventory: dict,
    geojson_path: Path,
    raster_path: Path,
    output_csv_path: Path,
    raster_download: dict,
    raster_metadata: dict,
) -> dict:
    rounded_total = sum(int(row["population_total"]) for row in rows)
    raw_total = sum(float(row["gridded_population_value"]) for row in rows)
    densities = [float(row["population_density"]) for row in rows]
    wards = load_ward_polygons(geojson_path, county=str(inventory.get("county") or "Migori"))
    ward_areas = [ward.area_km2 for ward in wards]
    phase0_gates = inventory.get("phase0_gates") or {}
    expected_ward_count = int(inventory.get("expected_ward_count") or 0)
    output_csv_sha256 = file_sha256(output_csv_path)
    geojson_sha256 = file_sha256(geojson_path)
    source_ref = worldpop_file_url_from_inventory(inventory)
    assigned_population_value = float(aggregate.get("assigned_population_value") or 0.0)
    source_positive_population_value = float(aggregate.get("source_positive_population_value") or 0.0)
    unassigned_positive_population_value = float(aggregate.get("unassigned_positive_population_value") or 0.0)
    pixel_width = raster_metadata.get("pixel_width_degrees")
    pixel_height = raster_metadata.get("pixel_height_degrees")
    raster_pixel_size_matches_expected = (
        pixel_width is not None
        and pixel_height is not None
        and abs(float(pixel_width) - EXPECTED_WORLDPOP_PIXEL_SIZE_DEGREES) <= PIXEL_SIZE_TOLERANCE_DEGREES
        and abs(float(pixel_height) - EXPECTED_WORLDPOP_PIXEL_SIZE_DEGREES) <= PIXEL_SIZE_TOLERANCE_DEGREES
    )
    population_mass_accounting_reconciles = math.isclose(
        source_positive_population_value,
        assigned_population_value + unassigned_positive_population_value,
        rel_tol=0.0,
        abs_tol=0.001,
    )
    phase1_gates = {
        "phase0_inventory_passed": bool(phase0_gates) and all(phase0_gates.values()),
        "phase0_inventory_has_expected_release_gates": all(
            key in phase0_gates
            for key in {
                "worldpop_record_id_matches_expected",
                "worldpop_popyear_matches_expected",
                "worldpop_source_date_matches_expected",
                "worldpop_doi_matches_expected",
                "worldpop_data_format_is_geotiff",
                "worldpop_file_url_matches_expected",
                "worldpop_category_mentions_100m",
                "worldpop_source_mentions_worldpop",
                "worldpop_citation_records_expected_doi",
            }
        ),
        "source_ref_matches_expected_worldpop_file": source_ref == EXPECTED_WORLDPOP_FILE_URL,
        "row_count_matches_expected": len(rows) == expected_ward_count,
        "ward_codes_unique": len({row["ward_code"] for row in rows}) == len(rows),
        "population_total_raw_positive": raw_total > 0,
        "population_total_rounded_positive": rounded_total > 0,
        "population_density_values_positive": bool(densities) and all(density > 0 for density in densities),
        "ward_area_values_positive": bool(ward_areas) and all(area > 0 for area in ward_areas),
        "assigned_pixel_count_positive": int(aggregate["assigned_pixel_count"]) > 0,
        "assigned_population_matches_csv_total": math.isclose(
            assigned_population_value,
            raw_total,
            rel_tol=0.0,
            abs_tol=max(len(rows) * 0.0005, 0.001),
        ),
        "bbox_positive_population_accounted": population_mass_accounting_reconciles,
        "raster_sha256_recorded": bool(raster_download.get("sha256")),
        "raster_cached_outside_git": "/source_cache/" in str(raster_path).replace("\\", "/"),
        "raster_crs_declared": raster_metadata.get("crs_declared") is True,
        "raster_crs_wgs84_like": raster_metadata.get("crs_wgs84_like") is True,
        "raster_pixel_size_positive": bool(raster_metadata.get("pixel_width_degrees"))
        and bool(raster_metadata.get("pixel_height_degrees")),
        "raster_pixel_size_matches_declared_100m_grid": raster_pixel_size_matches_expected,
        "geojson_sha256_recorded": bool(geojson_sha256),
        "output_csv_sha256_recorded": bool(output_csv_sha256),
    }
    return {
        "phase": "migori_knbs_worldpop_phase_1_processed_csv",
        "passed": all(phase1_gates.values()),
        "phase1_gates": phase1_gates,
        "row_count": len(rows),
        "source_ref": source_ref,
        "release_version": "WorldPop G2_CN_POP_R25A_100m KEN 2026 v1",
        "output_csv_path": str(output_csv_path),
        "output_csv_sha256": output_csv_sha256,
        "geojson_path": str(geojson_path),
        "geojson_sha256": geojson_sha256,
        "raster_path": str(raster_path),
        "raster_download": raster_download,
        "raster_metadata": raster_metadata,
        "aggregation_method": AGGREGATION_METHOD,
        "spatial_resolution": SPATIAL_RESOLUTION,
        "area_method": "local_equirectangular_shoelace_from_epsg4326_coordinates",
        "ward_area_total_km2": round(sum(ward_areas), 3),
        "ward_area_min_km2": round(min(ward_areas), 3) if ward_areas else None,
        "ward_area_max_km2": round(max(ward_areas), 3) if ward_areas else None,
        "population_total_raw": round(raw_total, 3),
        "population_total_rounded": rounded_total,
        "population_density_min": min(densities) if densities else None,
        "population_density_max": max(densities) if densities else None,
        "source_pixel_count": aggregate["source_pixel_count"],
        "source_positive_pixel_count": aggregate["source_positive_pixel_count"],
        "source_positive_population_value": round(source_positive_population_value, 3),
        "assigned_pixel_count": aggregate["assigned_pixel_count"],
        "assigned_population_value": round(assigned_population_value, 3),
        "unassigned_positive_pixel_count": aggregate["unassigned_positive_pixel_count"],
        "unassigned_positive_population_value": round(unassigned_positive_population_value, 3),
        "assigned_population_share_of_bbox_positive_value": (
            round(assigned_population_value / source_positive_population_value, 6)
            if source_positive_population_value
            else None
        ),
        "unassigned_positive_population_share_of_bbox_positive_value": (
            round(unassigned_positive_population_value / source_positive_population_value, 6)
            if source_positive_population_value
            else None
        ),
        "gdal_command": aggregate.get("gdal_command", []),
        "gdal_stderr": aggregate.get("gdal_stderr", ""),
        "bbox": aggregate.get("bbox", {}),
        "worldpop_record": (inventory.get("worldpop") or {}).get("record"),
        "knbs_role": (inventory.get("knbs") or {}).get("role"),
    }


def build_migori_worldpop_population_csv(
    *,
    inventory_path: Path = DEFAULT_PHASE0_INVENTORY_PATH,
    geojson_path: Path = MIGORI_WARD_GEOMETRY_PATH,
    raster_path: Path | None = None,
    output_csv_path: Path = DEFAULT_OUTPUT_CSV_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
    download_raster: bool = True,
) -> dict:
    inventory = load_json(inventory_path)
    source_ref = worldpop_file_url_from_inventory(inventory)
    selected_raster_path = raster_path or default_raster_cache_path(source_ref)
    if selected_raster_path.exists():
        raster_download = download_file(source_ref, selected_raster_path)
    elif download_raster:
        raster_download = download_file(source_ref, selected_raster_path)
    else:
        raise FileNotFoundError(f"Raster file not found and download disabled: {selected_raster_path}")

    wards = load_ward_polygons(geojson_path, county=str(inventory.get("county") or "Migori"))
    raster_metadata = raster_metadata_with_gdal(selected_raster_path)
    aggregate = aggregate_raster_with_gdal(raster_path=selected_raster_path, wards=wards)
    release_version = "WorldPop G2_CN_POP_R25A_100m KEN 2026 v1"
    rows = csv_rows_for_aggregates(
        wards=wards,
        aggregate=aggregate,
        source_ref=source_ref,
        release_version=release_version,
        geojson_sha256=file_sha256(geojson_path),
    )
    write_population_csv(output_csv_path, rows)
    summary = build_summary(
        rows=rows,
        aggregate=aggregate,
        inventory=inventory,
        geojson_path=geojson_path,
        raster_path=selected_raster_path,
        output_csv_path=output_csv_path,
        raster_download=raster_download,
        raster_metadata=raster_metadata,
    )
    write_json(summary_path, summary)
    return summary
