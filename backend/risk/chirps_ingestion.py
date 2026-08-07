"""Orchestration and persistence for historical CHIRPS v3 rainfall."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from typing import Iterable

from decouple import config
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from risk.climate.connectors.chirps import (
    CHIRPS_DAILY_VARIANTS,
    CHIRPS_PROCESSING_CODE_VERSION,
    CHIRPS_PRODUCT_STATUS_FINAL,
    CHIRPS_PROVIDER,
    CHIRPS_VERSION,
    ChirpsAssetUnavailable,
    ChirpsConnector,
    ChirpsRasterWindow,
    ChirpsZonalStats,
    fractional_zonal_stats,
    ward_geometry_in_raster_crs,
    chirps_max_date_range_days,
    chirps_min_coverage_fraction,
    validate_variant_date_range,
)
from risk.models import (
    ClimateRecord,
    ClimateRecordQualityFlag,
    ClimateRecordType,
    IngestionRun,
    Ward,
    WardGeometryDatasetVersion,
    WardGeometryFeature,
)


@dataclass(frozen=True)
class CanonicalWardPolygon:
    ward: Ward
    geometry: object
    public_id: str
    geometry_dataset_version: str
    geometry_hash: str


def _geometry_hash(geometry: object) -> str:
    return hashlib.sha256(bytes(geometry.wkb)).hexdigest()


def load_active_migori_ward_polygons() -> list[CanonicalWardPolygon]:
    """Load active Migori polygons from the managed geometry version/ward field.

    An active managed geometry version is authoritative.  When no managed
    version has been activated yet, the canonical ``Ward.boundary`` field is
    used.  Missing polygons are a hard ingestion error; centroids are never a
    CHIRPS substitute.
    """

    wards = list(
        Ward.objects.filter(is_active=True, county__iexact="Migori")
        .order_by("name", "id")
    )
    if not wards:
        raise ValueError("No active Migori wards are available for CHIRPS ingestion.")

    dataset_slug = config("MIGORI_WARD_GEOMETRY_DATASET_SLUG", default="migori-ward-boundaries")
    managed_version = (
        WardGeometryDatasetVersion.objects.select_related("dataset")
        .filter(
            dataset__slug=dataset_slug,
            dataset__is_active=True,
            is_active=True,
        )
        .order_by("-activated_at", "-id")
        .first()
    )
    managed_features: dict[int, WardGeometryFeature] = {}
    if managed_version:
        managed_features = {
            feature.ward_id: feature
            for feature in WardGeometryFeature.objects.filter(
                dataset_version=managed_version,
                ward_id__in=[ward.id for ward in wards],
            )
        }

    polygons: list[CanonicalWardPolygon] = []
    for ward in wards:
        feature = managed_features.get(ward.id)
        if managed_version and feature is None:
            raise ValueError(
                f"Active managed geometry version {managed_version.version_label!r} "
                f"has no polygon for active ward {ward.name!r}."
            )
        geometry = feature.geometry if feature is not None else ward.boundary
        if geometry is None or geometry.empty or not geometry.valid:
            raise ValueError(f"Active Migori ward {ward.name!r} has no canonical polygon.")
        polygons.append(
            CanonicalWardPolygon(
                ward=ward,
                geometry=geometry,
                public_id=str(ward.public_id),
                geometry_dataset_version=(
                    f"{managed_version.dataset.slug}:{managed_version.version_label}"
                    if managed_version
                    else "ward.boundary"
                ),
                geometry_hash=_geometry_hash(geometry),
            )
        )
    return polygons


def _all_ward_bounds(polygons: Iterable[CanonicalWardPolygon]) -> tuple[float, float, float, float]:
    bounds = [polygon.geometry.extent for polygon in polygons]
    if not bounds:
        raise ValueError("At least one canonical ward polygon is required.")
    min_x = min(item[0] for item in bounds)
    min_y = min(item[1] for item in bounds)
    max_x = max(item[2] for item in bounds)
    max_y = max(item[3] for item in bounds)
    return float(min_x), float(min_y), float(max_x), float(max_y)


def chirps_identity_key(
    *,
    source_date: date,
    variant: str,
    product_status: str,
    ward_public_id: str,
) -> str:
    return "|".join(
        [
            CHIRPS_PROVIDER,
            CHIRPS_VERSION,
            product_status,
            variant,
            source_date.isoformat(),
            ward_public_id,
            CHIRPS_PROCESSING_CODE_VERSION,
        ]
    )


def chirps_source_ref(
    *,
    source_date: date,
    variant: str,
    product_status: str,
    ward_public_id: str,
) -> str:
    return (
        f"chirps:{CHIRPS_VERSION}:{product_status}:{variant}:"
        f"{source_date.isoformat()}:ward:{ward_public_id}"
    )


def chirps_source_run_ref(*, source_date: date, variant: str, product_status: str) -> str:
    """Return the stable source batch identity shared by all wards for a date."""

    return f"chirps-ingestion:{CHIRPS_VERSION}:{product_status}:{variant}:{source_date.isoformat()}"


def _date_range(start_date: date, end_date: date) -> list[date]:
    return [
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    ]


def _daily_interval(source_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(source_date, time.min, tzinfo=dt_timezone.utc)
    return start, start + timedelta(days=1)


def _lineage_metadata(
    *,
    source_date: date,
    variant: str,
    product_status: str,
    polygon: CanonicalWardPolygon,
    asset: ChirpsRasterWindow,
    stats: ChirpsZonalStats,
) -> dict:
    interval_start, interval_end = _daily_interval(source_date)
    daily_method = CHIRPS_DAILY_VARIANTS[variant]["daily_disaggregation_method"]
    return {
        "provider": CHIRPS_PROVIDER,
        "chirps_version": CHIRPS_VERSION,
        "product_status": product_status,
        "daily_variant": variant,
        "source_date": source_date.isoformat(),
        "official_asset_url": asset.source_url,
        "asset_url": asset.source_url,
        "asset_filename": asset.asset_filename,
        "etag": asset.etag,
        "last_modified": asset.last_modified,
        "content_length": asset.content_length,
        "retrieval_timestamp": asset.retrieval_timestamp,
        "hashes": {
            "full_asset_sha256": asset.full_asset_sha256,
            "extracted_window_sha256": asset.extracted_window_sha256,
        },
        "full_asset_sha256": asset.full_asset_sha256,
        "extracted_window_sha256": asset.extracted_window_sha256,
        "raster_crs": asset.crs,
        "raster_transform": list(asset.transform_values),
        "raster_resolution": list(asset.resolution),
        "raster_nodata": asset.nodata,
        "aggregation_method": "fractional_cell_area_weighted_zonal_mean",
        "valid_pixel_count": stats.valid_pixel_count,
        "ward_coverage_fraction": stats.ward_coverage_fraction,
        "ward_public_id": polygon.public_id,
        "ward_geometry_dataset_version": polygon.geometry_dataset_version,
        "ward_geometry_hash": polygon.geometry_hash,
        "processing_code_version": CHIRPS_PROCESSING_CODE_VERSION,
        "chirps_daily_disaggregation_method": daily_method,
        "daily_interval_start": interval_start.isoformat(),
        "daily_interval_end": interval_end.isoformat(),
        "daily_interval_timezone": "UTC",
        "source_access_mode": asset.source_access_mode,
    }


def _record_fields(
    *,
    run: IngestionRun,
    source_date: date,
    variant: str,
    product_status: str,
    polygon: CanonicalWardPolygon,
    asset: ChirpsRasterWindow,
    stats: ChirpsZonalStats,
) -> dict:
    interval_start, _ = _daily_interval(source_date)
    identity_key = chirps_identity_key(
        source_date=source_date,
        variant=variant,
        product_status=product_status,
        ward_public_id=polygon.public_id,
    )
    source_ref = chirps_source_ref(
        source_date=source_date,
        variant=variant,
        product_status=product_status,
        ward_public_id=polygon.public_id,
    )
    source_run = chirps_source_run_ref(
        source_date=source_date,
        variant=variant,
        product_status=product_status,
    )
    lineage = _lineage_metadata(
        source_date=source_date,
        variant=variant,
        product_status=product_status,
        polygon=polygon,
        asset=asset,
        stats=stats,
    )
    lineage["source_ref"] = source_ref
    lineage["identity_key"] = identity_key
    lineage["source_run"] = source_run
    return {
        "ward": polygon.ward,
        "ingestion_run": run,
        "record_type": ClimateRecordType.OBSERVED,
        "source_provider": CHIRPS_PROVIDER,
        "source_kind": IngestionRun.SOURCE_KIND_LIVE,
        "source_mode": f"{product_status}-{variant}",
        "issue_time": None,
        "valid_date": source_date,
        "lead_day": None,
        "observed_timestamp": interval_start,
        "forecast_horizon_days": 0,
        "rainfall_mm": float(stats.rainfall_mm),
        "quality_flag": ClimateRecordQualityFlag.ACCEPTED,
        "fallback_flag": False,
        "source_run": source_run,
        "source_ref": source_ref,
        "identity_key": identity_key,
        "lineage_metadata": lineage,
        # Keep raw payload deliberately small.  The extracted raster is never
        # serialized into JSON.
        "raw_payload": {
            "provider": CHIRPS_PROVIDER,
            "source_date": source_date.isoformat(),
            "record_type": ClimateRecordType.OBSERVED,
            "rainfall_mm": round(float(stats.rainfall_mm), 6),
            "valid_pixel_count": stats.valid_pixel_count,
            "ward_coverage_fraction": round(stats.ward_coverage_fraction, 8),
            "source_ref": source_ref,
            "source_run": source_run,
        },
    }


def _existing_record(identity_key: str, source_ref: str) -> ClimateRecord | None:
    return (
        ClimateRecord.objects.select_for_update()
        .filter(Q(identity_key=identity_key) | Q(source_ref=source_ref))
        .order_by("id")
        .first()
    )


def _persist_record(fields: dict, *, force: bool) -> str:
    identity_key = fields["identity_key"]
    source_ref = fields["source_ref"]
    existing = _existing_record(identity_key, source_ref)
    if existing is not None and not force:
        return "skipped"
    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        existing.save()
        return "updated"

    try:
        ClimateRecord.objects.create(**fields)
        return "created"
    except IntegrityError:
        # A concurrent worker may have won the durable identity race.  It is
        # safe to treat that as an idempotent skip unless --force was explicit.
        existing = ClimateRecord.objects.filter(
            Q(identity_key=identity_key) | Q(source_ref=source_ref)
        ).first()
        if existing is None:
            raise
        if force:
            for key, value in fields.items():
                setattr(existing, key, value)
            existing.save()
            return "updated"
        return "skipped"


def _new_run(
    *,
    start_date: date,
    end_date: date,
    variant: str,
    product_status: str,
    polygons: list[CanonicalWardPolygon],
    max_date_range_days: int,
) -> IngestionRun:
    requested_dates = [item.isoformat() for item in _date_range(start_date, end_date)]
    return IngestionRun.objects.create(
        run_type=IngestionRun.RUN_TYPE_RAINFALL,
        status=IngestionRun.STATUS_PARTIAL,
        source_mode=f"{product_status}-{variant}",
        source_kind=IngestionRun.SOURCE_KIND_LIVE,
        source_name=CHIRPS_PROVIDER,
        source_priority=[CHIRPS_PROVIDER],
        requested_wards=[polygon.public_id for polygon in polygons],
        freshness_state=IngestionRun.FRESHNESS_UNKNOWN,
        fallback_used=False,
        operator_note=(
            "CHIRPS v3 historical final-product ingestion; no static fallback. "
            f"variant={variant} product_status={product_status}"
        ),
        lineage_metadata={
            "provider": CHIRPS_PROVIDER,
            "chirps_version": CHIRPS_VERSION,
            "product_status": product_status,
            "daily_variant": variant,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "requested_dates": requested_dates,
            "requested_ward_public_ids": [polygon.public_id for polygon in polygons],
            "ward_geometry_dataset_versions": sorted(
                {polygon.geometry_dataset_version for polygon in polygons}
            ),
            "processing_code_version": CHIRPS_PROCESSING_CODE_VERSION,
            "max_date_range_days": max_date_range_days,
            "dry_run": False,
        },
    )


def ingest_chirps_rainfall(
    *,
    start_date: date,
    end_date: date,
    variant: str = "sat",
    product_status: str = CHIRPS_PRODUCT_STATUS_FINAL,
    dry_run: bool = False,
    resume: bool = False,
    force: bool = False,
    connector: ChirpsConnector | None = None,
) -> dict:
    """Ingest a bounded inclusive date range for every active Migori ward."""

    if product_status != CHIRPS_PRODUCT_STATUS_FINAL:
        raise ValueError("Only the CHIRPS final product is implemented in this tranche.")
    validate_variant_date_range(variant=variant, start_date=start_date, end_date=end_date)
    dates = _date_range(start_date, end_date)
    max_date_range_days = chirps_max_date_range_days()
    if len(dates) > max_date_range_days:
        raise ValueError(
            f"Requested {len(dates)} dates, exceeding CHIRPS_MAX_DATE_RANGE_DAYS={max_date_range_days}."
        )

    polygons = load_active_migori_ward_polygons()
    bounds = _all_ward_bounds(polygons)
    connector = connector or ChirpsConnector()
    run = None
    if not dry_run:
        run = _new_run(
            start_date=start_date,
            end_date=end_date,
            variant=variant,
            product_status=product_status,
            polygons=polygons,
            max_date_range_days=max_date_range_days,
        )

    requested_identity_keys = [
        chirps_identity_key(
            source_date=source_date,
            variant=variant,
            product_status=product_status,
            ward_public_id=polygon.public_id,
        )
        for source_date in dates
        for polygon in polygons
    ]
    existing_identities = set(
        ClimateRecord.objects.filter(identity_key__in=requested_identity_keys).values_list(
            "identity_key", flat=True
        )
    )

    date_summaries: list[dict] = []
    unavailable_dates: list[str] = []
    rejected_dates: list[str] = []
    completed_dates: list[str] = []
    assets_found = 0
    records_created = 0
    records_updated = 0
    records_skipped = 0
    records_rejected = 0
    latest_retrieval: datetime | None = None

    try:
        for source_date in dates:
            date_key = source_date.isoformat()
            date_identities = {
                chirps_identity_key(
                    source_date=source_date,
                    variant=variant,
                    product_status=product_status,
                    ward_public_id=polygon.public_id,
                )
                for polygon in polygons
            }
            if resume and not force and date_identities.issubset(existing_identities):
                records_skipped += len(polygons)
                completed_dates.append(date_key)
                date_summaries.append(
                    {
                        "kind": "date_summary",
                        "source_date": date_key,
                        "status": "skipped_existing",
                        "asset_found": False,
                        "ward_count": len(polygons),
                        "records_skipped": len(polygons),
                    }
                )
                continue

            try:
                asset = connector.fetch_window(
                    source_date,
                    variant=variant,
                    product_status=product_status,
                    bounds=bounds,
                )
                assets_found += 1
                try:
                    retrieved = datetime.fromisoformat(asset.retrieval_timestamp)
                    latest_retrieval = max(latest_retrieval, retrieved) if latest_retrieval else retrieved
                except ValueError:
                    pass
            except ChirpsAssetUnavailable as exc:
                unavailable_dates.append(date_key)
                records_rejected += len(polygons)
                date_summaries.append(
                    {
                        "kind": "date_summary",
                        "source_date": date_key,
                        "status": "unavailable",
                        "asset_found": False,
                        "ward_count": len(polygons),
                        "records_rejected": len(polygons),
                        "error": str(exc),
                    }
                )
                continue
            except Exception as exc:
                rejected_dates.append(date_key)
                records_rejected += len(polygons)
                date_summaries.append(
                    {
                        "kind": "date_summary",
                        "source_date": date_key,
                        "status": "rejected",
                        "asset_found": False,
                        "ward_count": len(polygons),
                        "records_rejected": len(polygons),
                        "error": str(exc),
                    }
                )
                continue

            stats_by_ward: dict[int, ChirpsZonalStats] = {}
            rejection_error = ""
            try:
                for polygon in polygons:
                    raster_geometry = ward_geometry_in_raster_crs(polygon.geometry, asset.crs)
                    stats_by_ward[polygon.ward.id] = fractional_zonal_stats(
                        asset.array,
                        transform=asset.transform,
                        ward_geometry=raster_geometry,
                        nodata=asset.nodata,
                        min_coverage_fraction=chirps_min_coverage_fraction(),
                        ward_label=polygon.ward.name,
                    )
            except Exception as exc:
                rejection_error = str(exc)

            if rejection_error:
                rejected_dates.append(date_key)
                records_rejected += len(polygons)
                date_summaries.append(
                    {
                        "kind": "date_summary",
                        "source_date": date_key,
                        "status": "rejected",
                        "asset_found": True,
                        "source_url": asset.source_url,
                        "asset_filename": asset.asset_filename,
                        "source_access_mode": asset.source_access_mode,
                        "ward_count": len(polygons),
                        "records_rejected": len(polygons),
                        "error": rejection_error,
                    }
                )
                continue

            created_for_date = 0
            updated_for_date = 0
            skipped_for_date = 0
            if dry_run:
                for polygon in polygons:
                    identity = chirps_identity_key(
                        source_date=source_date,
                        variant=variant,
                        product_status=product_status,
                        ward_public_id=polygon.public_id,
                    )
                    if identity in existing_identities and not force:
                        skipped_for_date += 1
                    else:
                        created_for_date += 1
            else:
                assert run is not None
                with transaction.atomic():
                    for polygon in polygons:
                        fields = _record_fields(
                            run=run,
                            source_date=source_date,
                            variant=variant,
                            product_status=product_status,
                            polygon=polygon,
                            asset=asset,
                            stats=stats_by_ward[polygon.ward.id],
                        )
                        action = _persist_record(fields, force=force)
                        if action == "created":
                            created_for_date += 1
                            existing_identities.add(fields["identity_key"])
                        elif action == "updated":
                            updated_for_date += 1
                            existing_identities.add(fields["identity_key"])
                        else:
                            skipped_for_date += 1

            records_created += created_for_date
            records_updated += updated_for_date
            records_skipped += skipped_for_date
            completed_dates.append(date_key)
            date_summaries.append(
                {
                    "kind": "date_summary",
                    "source_date": date_key,
                    "status": "dry_run" if dry_run else "processed",
                    "asset_found": True,
                    "source_url": asset.source_url,
                    "asset_filename": asset.asset_filename,
                    "source_access_mode": asset.source_access_mode,
                    "etag": asset.etag,
                    "last_modified": asset.last_modified,
                    "content_length": asset.content_length,
                    "extracted_window_sha256": asset.extracted_window_sha256,
                    "ward_count": len(polygons),
                    "records_created": created_for_date,
                    "records_updated": updated_for_date,
                    "records_skipped": skipped_for_date,
                }
            )
    except Exception as exc:
        if run is not None:
            _finalize_run(
                run,
                date_summaries=date_summaries,
                dates=dates,
                completed_dates=completed_dates,
                unavailable_dates=unavailable_dates,
                rejected_dates=rejected_dates,
                assets_found=assets_found,
                records_created=records_created,
                records_updated=records_updated,
                records_skipped=records_skipped,
                records_rejected=records_rejected,
                latest_retrieval=latest_retrieval,
                error_message=str(exc),
            )
        raise

    status = _status_for_results(
        dates=dates,
        completed_dates=completed_dates,
        unavailable_dates=unavailable_dates,
        rejected_dates=rejected_dates,
    )
    if run is not None:
        _finalize_run(
            run,
            date_summaries=date_summaries,
            dates=dates,
            completed_dates=completed_dates,
            unavailable_dates=unavailable_dates,
            rejected_dates=rejected_dates,
            assets_found=assets_found,
            records_created=records_created,
            records_updated=records_updated,
            records_skipped=records_skipped,
            records_rejected=records_rejected,
            latest_retrieval=latest_retrieval,
            error_message="" if status != IngestionRun.STATUS_FAILED else "No requested CHIRPS dates were successfully processed.",
        )

    return {
        "run": run,
        "run_id": run.id if run else None,
        "status": status,
        "provider": CHIRPS_PROVIDER,
        "version": CHIRPS_VERSION,
        "product_status": product_status,
        "variant": variant,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "dates_requested": len(dates),
        "assets_found": assets_found,
        "processed_dates": len(completed_dates),
        "unavailable_dates": unavailable_dates,
        "rejected_dates": rejected_dates,
        "records_created": records_created,
        "records_updated": records_updated,
        "records_skipped": records_skipped,
        "records_rejected": records_rejected,
        "dry_run": dry_run,
        "date_summaries": date_summaries,
    }


def _status_for_results(
    *,
    dates: list[date],
    completed_dates: list[str],
    unavailable_dates: list[str],
    rejected_dates: list[str],
) -> str:
    if len(completed_dates) == len(dates):
        return IngestionRun.STATUS_SUCCESS
    if completed_dates:
        return IngestionRun.STATUS_PARTIAL
    return IngestionRun.STATUS_FAILED


def _finalize_run(
    run: IngestionRun,
    *,
    date_summaries: list[dict],
    dates: list[date],
    completed_dates: list[str],
    unavailable_dates: list[str],
    rejected_dates: list[str],
    assets_found: int,
    records_created: int,
    records_updated: int,
    records_skipped: int,
    records_rejected: int,
    latest_retrieval: datetime | None,
    error_message: str,
) -> None:
    status = _status_for_results(
        dates=dates,
        completed_dates=completed_dates,
        unavailable_dates=unavailable_dates,
        rejected_dates=rejected_dates,
    )
    lineage = {
        **(run.lineage_metadata or {}),
        "processed_dates": completed_dates,
        "unavailable_dates": unavailable_dates,
        "rejected_dates": rejected_dates,
        "assets_found": assets_found,
        "records_created": records_created,
        "records_updated": records_updated,
        "records_skipped": records_skipped,
        "records_rejected": records_rejected,
        # An unavailable source date is explicitly represented and may be
        # retried; only an aggregation/validation rejection breaks the
        # requested date sequence.
        "date_range_contiguous": not rejected_dates,
        "explicitly_unavailable_dates": unavailable_dates,
    }
    run.status = status
    run.source_timestamp = latest_retrieval or timezone.now()
    run.freshness_state = IngestionRun.FRESHNESS_FRESH if assets_found else IngestionRun.FRESHNESS_UNKNOWN
    run.fallback_used = False
    run.records_seen = len(dates) * len(run.requested_wards or [])
    run.records_loaded = records_created + records_updated
    run.records_rejected = records_rejected
    run.results = date_summaries
    run.lineage_metadata = lineage
    run.error_message = error_message
    run.completed_at = timezone.now()
    run.save(
        update_fields=[
            "status",
            "source_timestamp",
            "freshness_state",
            "fallback_used",
            "records_seen",
            "records_loaded",
            "records_rejected",
            "results",
            "lineage_metadata",
            "error_message",
            "completed_at",
        ]
    )
