from __future__ import annotations

import csv
import json
import logging
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from decouple import config
from django.utils import timezone

from risk.etl_records import canonical_record_envelope, climate_record_from_rainfall_observation
from risk.models import IngestionRun, Ward

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RainfallObservation:
    ward_name: str
    rainfall_mm: float
    source: str
    source_timestamp: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    coordinate_source: str | None = None
    fallback_reason: str | None = None


# Approximate ward centroids for initial prototype use.
# Replace later with real ward centroid extraction from PostGIS geometry.
WARD_COORDINATES: dict[str, tuple[float, float]] = {
    "North Kamagambo": (-0.9876, 34.6410),
    "North Kadem": (-1.0120, 34.2850),
    "Macalder Kanyarwanda": (-1.1430, 34.3030),
    "Got Kachola": (-1.0600, 34.2100),
    "Central Karungu": (-1.0900, 34.1800),
    "West Kanyamkago": (-0.9800, 34.5200),
    "Aneko": (-1.0200, 34.4700),
    "Kaler": (-1.1100, 34.2400),
}

DEFAULT_STATIC_RAINFALL: dict[str, float] = {
    "North Kamagambo": 118.0,
    "North Kadem": 67.0,
    "Macalder Kanyarwanda": 111.0,
    "Got Kachola": 122.0,
    "Central Karungu": 59.0,
    "West Kanyamkago": 76.0,
    "Aneko": 95.0,
    "Kaler": 54.0,
}


def _normalize_ward_name(name: str) -> str:
    return " ".join((name or "").strip().split())


def get_ward_coordinates(
    ward_name: str,
    ward: Ward | None = None,
) -> tuple[float | None, float | None, str | None]:
    if ward and ward.centroid:
        return float(ward.centroid.y), float(ward.centroid.x), "ward-centroid"

    normalized = _normalize_ward_name(ward_name)
    coords = WARD_COORDINATES.get(normalized)
    if not coords:
        return None, None, None
    latitude, longitude = coords
    return latitude, longitude, "static-ward-map"


def load_static_rainfall_from_env_or_defaults() -> dict[str, RainfallObservation]:
    rows: dict[str, RainfallObservation] = {}

    for ward_name, rainfall_mm in DEFAULT_STATIC_RAINFALL.items():
        lat, lon, coordinate_source = get_ward_coordinates(ward_name)
        rows[_normalize_ward_name(ward_name)] = RainfallObservation(
            ward_name=ward_name,
            rainfall_mm=float(rainfall_mm),
            source="static-default",
            source_timestamp=None,
            latitude=lat,
            longitude=lon,
            coordinate_source=coordinate_source,
        )

    return rows


def load_static_rainfall_from_csv() -> dict[str, RainfallObservation]:
    csv_path = config("RAINFALL_STATIC_CSV_PATH", default="risk/data/rainfall_seed.csv")
    file_path = Path(csv_path)

    if not file_path.is_absolute():
        file_path = Path("/app") / csv_path

    if not file_path.exists():
        logger.info("Static rainfall CSV not found at %s; using defaults.", file_path)
        return load_static_rainfall_from_env_or_defaults()

    rows: dict[str, RainfallObservation] = {}
    with file_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for record in reader:
            ward_name = _normalize_ward_name(record.get("ward_name", ""))
            if not ward_name:
                continue

            rainfall_mm = float(record.get("rainfall_mm", 0) or 0)
            lat_value = record.get("latitude")
            lon_value = record.get("longitude")

            latitude = float(lat_value) if lat_value not in (None, "", "null") else None
            longitude = float(lon_value) if lon_value not in (None, "", "null") else None

            rows[ward_name] = RainfallObservation(
                ward_name=ward_name,
                rainfall_mm=rainfall_mm,
                source="static-csv",
                source_timestamp=None,
                latitude=latitude,
                longitude=longitude,
                coordinate_source="static-csv",
            )

    logger.info("Loaded %s rainfall rows from static CSV.", len(rows))
    return rows


def fetch_open_meteo_daily_precipitation(
    *,
    ward_name: str,
    latitude: float,
    longitude: float,
    forecast_days: int = 3,
    timeout_seconds: int = 20,
) -> RainfallObservation:
    base_url = config(
        "OPEN_METEO_FORECAST_URL",
        default="https://api.open-meteo.com/v1/forecast",
    )
    open_meteo_timezone = config("OPEN_METEO_TIMEZONE", default="Africa/Nairobi")

    query = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "daily": "precipitation_sum",
            "forecast_days": forecast_days,
            "timezone": open_meteo_timezone,
        }
    )
    url = f"{base_url}?{query}"

    logger.info(
        "Fetching rainfall forecast for ward=%s lat=%s lon=%s days=%s",
        ward_name,
        latitude,
        longitude,
        forecast_days,
    )

    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/json"},
    )

    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))

    daily = payload.get("daily", {})
    precipitation_values = daily.get("precipitation_sum", []) or []

    if not precipitation_values:
        raise ValueError(f"No precipitation_sum returned for ward '{ward_name}'")

    rainfall_mm = float(sum(float(value or 0) for value in precipitation_values))

    return RainfallObservation(
        ward_name=_normalize_ward_name(ward_name),
        rainfall_mm=round(rainfall_mm, 2),
        source="open-meteo-forecast",
        source_timestamp=timezone.now(),
        latitude=latitude,
        longitude=longitude,
    )


def source_priority_for_mode(mode: str) -> list[str]:
    if mode == "static":
        return ["static-csv", "static-default", "static-fallback"]
    return ["ward-centroid", "static-ward-map", "open-meteo-forecast", "static-csv", "static-default", "static-fallback"]


def _build_static_fallback_observation(
    *,
    ward_name: str,
    latitude: float | None,
    longitude: float | None,
    coordinate_source: str | None,
    fallback_reason: str,
) -> RainfallObservation:
    normalized = _normalize_ward_name(ward_name)
    static_rows = load_static_rainfall_from_csv()
    observation = static_rows.get(
        normalized,
        RainfallObservation(
            ward_name=normalized,
            rainfall_mm=50.0,
            source="static-fallback",
            source_timestamp=None,
            latitude=latitude,
            longitude=longitude,
            coordinate_source=coordinate_source,
            fallback_reason=fallback_reason,
        ),
    )
    return RainfallObservation(
        ward_name=observation.ward_name,
        rainfall_mm=observation.rainfall_mm,
        source=observation.source,
        source_timestamp=observation.source_timestamp,
        latitude=observation.latitude if observation.latitude is not None else latitude,
        longitude=observation.longitude if observation.longitude is not None else longitude,
        coordinate_source=observation.coordinate_source or coordinate_source,
        fallback_reason=fallback_reason,
    )


def _serialize_observation(ward: Ward | None, observation: RainfallObservation) -> dict:
    source_timestamp = ""
    if isinstance(observation.source_timestamp, datetime):
        source_timestamp = observation.source_timestamp.isoformat()
    elif isinstance(observation.source_timestamp, str):
        source_timestamp = observation.source_timestamp
    elif observation.source == "open-meteo-forecast":
        source_timestamp = timezone.now().isoformat()
    source_kind = (
        IngestionRun.SOURCE_KIND_LIVE if observation.source == "open-meteo-forecast" else IngestionRun.SOURCE_KIND_SEEDED
    )
    freshness_state = IngestionRun.FRESHNESS_FRESH if source_timestamp else IngestionRun.FRESHNESS_UNKNOWN
    return {
        "ward_id": ward.id if ward else None,
        "ward_public_id": str(ward.public_id) if ward and ward.public_id else "",
        "ward_name": observation.ward_name,
        "rainfall_mm": observation.rainfall_mm,
        "source": observation.source,
        "source_timestamp": source_timestamp,
        "latitude": observation.latitude,
        "longitude": observation.longitude,
        "coordinate_source": observation.coordinate_source or "",
        "fallback_reason": observation.fallback_reason or "",
        "canonical_record": canonical_record_envelope(
            climate_record_from_rainfall_observation(
                ward=ward,
                ward_name=observation.ward_name,
                county=ward.county if ward else "Migori",
                source_name=observation.source,
                source_kind=source_kind,
                source_mode=config("RAINFALL_SOURCE_MODE", default="hybrid").strip().lower(),
                source_timestamp=source_timestamp or None,
                freshness_state=freshness_state,
                rainfall_mm=observation.rainfall_mm,
                latitude=observation.latitude,
                longitude=observation.longitude,
                coordinate_source=observation.coordinate_source,
                fallback_reason=observation.fallback_reason,
            )
        ),
    }


def _source_kind_for_results(results: list[dict]) -> str:
    if not results:
        return IngestionRun.SOURCE_KIND_UNKNOWN
    kinds = set()
    for item in results:
        source = item.get("source", "")
        if source == "open-meteo-forecast":
            kinds.add(IngestionRun.SOURCE_KIND_LIVE)
        elif source:
            kinds.add(IngestionRun.SOURCE_KIND_SEEDED)
    if len(kinds) > 1:
        return IngestionRun.SOURCE_KIND_HYBRID
    return next(iter(kinds), IngestionRun.SOURCE_KIND_UNKNOWN)


def _freshness_state_for_results(results: list[dict]) -> str:
    timestamps = []
    for item in results:
        source_timestamp = item.get("source_timestamp")
        if not source_timestamp:
            continue
        try:
            timestamps.append(datetime.fromisoformat(source_timestamp))
        except ValueError:
            continue
    if not timestamps:
        return IngestionRun.FRESHNESS_UNKNOWN
    latest = max(timestamps)
    now = timezone.now()
    if timezone.is_naive(latest):
        latest = timezone.make_aware(latest, timezone.get_current_timezone())
    age = now - latest
    if age <= timedelta(hours=6):
        return IngestionRun.FRESHNESS_FRESH
    if age <= timedelta(hours=24):
        return IngestionRun.FRESHNESS_DELAYED
    return IngestionRun.FRESHNESS_STALE


def _primary_source_name(results: list[dict]) -> str:
    for item in results:
        source = item.get("source", "").strip()
        if source:
            return source
    return ""


def _latest_source_timestamp(results: list[dict]):
    timestamps = []
    for item in results:
        source_timestamp = item.get("source_timestamp")
        if not source_timestamp:
            continue
        if isinstance(source_timestamp, datetime):
            parsed = source_timestamp
        elif isinstance(source_timestamp, str):
            try:
                parsed = datetime.fromisoformat(source_timestamp)
            except ValueError:
                continue
        else:
            continue
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        timestamps.append(parsed)
    return max(timestamps) if timestamps else None


def _finalize_ingestion_run(ingestion_run: IngestionRun, results: list[dict], error_message: str = "") -> None:
    status = IngestionRun.STATUS_SUCCESS
    if error_message:
        status = IngestionRun.STATUS_FAILED
    elif any(item.get("fallback_reason") for item in results):
        status = IngestionRun.STATUS_PARTIAL

    ingestion_run.status = status
    ingestion_run.source_kind = _source_kind_for_results(results)
    ingestion_run.source_name = _primary_source_name(results)
    ingestion_run.source_timestamp = _latest_source_timestamp(results)
    ingestion_run.freshness_state = _freshness_state_for_results(results)
    ingestion_run.fallback_used = any(item.get("fallback_reason") for item in results)
    ingestion_run.records_seen = len(ingestion_run.requested_wards or [])
    ingestion_run.records_loaded = len(results)
    ingestion_run.records_rejected = max(0, ingestion_run.records_seen - ingestion_run.records_loaded)
    ingestion_run.results = results
    ingestion_run.error_message = error_message
    ingestion_run.completed_at = timezone.now()
    ingestion_run.save(
        update_fields=[
            "status",
            "source_kind",
            "source_name",
            "source_timestamp",
            "freshness_state",
            "fallback_used",
            "records_seen",
            "records_loaded",
            "records_rejected",
            "results",
            "error_message",
            "completed_at",
        ]
    )


def _fetch_rainfall_observation(ward_name: str, ward: Ward | None = None) -> RainfallObservation:
    normalized = _normalize_ward_name(ward_name)
    mode = config("RAINFALL_SOURCE_MODE", default="hybrid").strip().lower()

    if mode == "static":
        return _build_static_fallback_observation(
            ward_name=normalized,
            latitude=None,
            longitude=None,
            coordinate_source=None,
            fallback_reason="static-mode-forced",
        )

    latitude, longitude, coordinate_source = get_ward_coordinates(normalized, ward=ward)

    if latitude is None or longitude is None:
        logger.warning(
            "No coordinates found for ward=%s; falling back to static rainfall.",
            normalized,
        )
        return _build_static_fallback_observation(
            ward_name=normalized,
            latitude=None,
            longitude=None,
            coordinate_source=None,
            fallback_reason="missing-coordinates",
        )

    try:
        observation = fetch_open_meteo_daily_precipitation(
            ward_name=normalized,
            latitude=latitude,
            longitude=longitude,
            forecast_days=config("OPEN_METEO_FORECAST_DAYS", cast=int, default=3),
        )
        return RainfallObservation(
            ward_name=observation.ward_name,
            rainfall_mm=observation.rainfall_mm,
            source=observation.source,
            source_timestamp=observation.source_timestamp,
            latitude=observation.latitude,
            longitude=observation.longitude,
            coordinate_source=coordinate_source,
            fallback_reason=None,
        )
    except Exception as exc:
        logger.exception(
            "Rainfall fetch failed for ward=%s. Falling back to static data. error=%s",
            normalized,
            exc,
        )
        return _build_static_fallback_observation(
            ward_name=normalized,
            latitude=latitude,
            longitude=longitude,
            coordinate_source=coordinate_source,
            fallback_reason="live-fetch-failed",
        )


def fetch_rainfall_for_ward(ward_name: str, ward: Ward | None = None) -> RainfallObservation:
    mode = config("RAINFALL_SOURCE_MODE", default="hybrid").strip().lower()
    normalized = _normalize_ward_name(ward_name)
    ingestion_run = IngestionRun.objects.create(
        run_type=IngestionRun.RUN_TYPE_RAINFALL,
        status=IngestionRun.STATUS_SUCCESS,
        source_mode=mode,
        source_priority=source_priority_for_mode(mode),
        requested_wards=[normalized],
    )
    try:
        observation = _fetch_rainfall_observation(normalized, ward=ward)
        _finalize_ingestion_run(
            ingestion_run,
            [_serialize_observation(ward, observation)],
        )
        return observation
    except Exception as exc:
        _finalize_ingestion_run(ingestion_run, [], error_message=str(exc))
        raise


def fetch_rainfall_for_wards(
    wards: list[Ward] | list[str],
    *,
    return_ingestion_run: bool = False,
) -> dict[str, RainfallObservation] | tuple[dict[str, RainfallObservation], IngestionRun]:
    results: dict[str, RainfallObservation] = {}
    mode = config("RAINFALL_SOURCE_MODE", default="hybrid").strip().lower()
    ward_entries: list[tuple[str, Ward | None]] = []

    for item in wards:
        if isinstance(item, Ward):
            ward_entries.append((_normalize_ward_name(item.name), item))
        else:
            ward_entries.append((_normalize_ward_name(str(item)), None))

    ingestion_run = IngestionRun.objects.create(
        run_type=IngestionRun.RUN_TYPE_RAINFALL,
        status=IngestionRun.STATUS_SUCCESS,
        source_mode=mode,
        source_priority=source_priority_for_mode(mode),
        requested_wards=[name for name, _ in ward_entries],
    )

    serialized_results: list[dict] = []
    try:
        for normalized, ward in ward_entries:
            observation = _fetch_rainfall_observation(normalized, ward=ward)
            results[normalized] = observation
            serialized_results.append(_serialize_observation(ward, observation))
        _finalize_ingestion_run(ingestion_run, serialized_results)
    except Exception as exc:
        _finalize_ingestion_run(ingestion_run, serialized_results, error_message=str(exc))
        raise
    if return_ingestion_run:
        return results, ingestion_run
    return results
