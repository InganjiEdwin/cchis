"""Official CHIRPS v3 daily COG retrieval and fractional zonal statistics.

This module deliberately has no static-data fallback.  A source failure is an
ingestion failure/partial result and is surfaced to the caller.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

import numpy as np
import requests
import rasterio
from decouple import config
from rasterio.io import MemoryFile
from rasterio.transform import Affine
from rasterio.errors import WindowError
from rasterio.windows import Window, from_bounds
from rasterio.warp import transform_bounds, transform_geom
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry
from shapely import wkb as shapely_wkb


CHIRPS_VERSION = "v3.0"
CHIRPS_PROVIDER = "chirps-v3.0"
CHIRPS_PRODUCT_STATUS_FINAL = "final"
CHIRPS_PRODUCT_STATUSES = frozenset({CHIRPS_PRODUCT_STATUS_FINAL})
CHIRPS_DAILY_VARIANTS = {
    "sat": {
        "available_from": date(1998, 1, 1),
        "daily_disaggregation_method": "IMERG Late V07 disaggregation of CHIRPS pentad totals",
    },
    "rnl": {
        "available_from": date(1981, 1, 1),
        "daily_disaggregation_method": "ERA5 reanalysis disaggregation of CHIRPS pentad totals",
    },
}
CHIRPS_SOURCE_HOST = "data.chc.ucsb.edu"
CHIRPS_SOURCE_PATH_PREFIX = "/products/CHIRPS/v3.0/daily/final/"
CHIRPS_PROCESSING_CODE_VERSION = "chirps-fractional-zonal-v1"
CHIRPS_DEFAULT_MIN_COVERAGE_FRACTION = 0.95
CHIRPS_DEFAULT_MAX_DATE_RANGE_DAYS = 31
CHIRPS_COVERAGE_NUMERICAL_EPSILON = 1e-9


class ChirpsError(Exception):
    """Base class for CHIRPS retrieval and processing errors."""


class ChirpsAssetUnavailable(ChirpsError):
    """The requested official daily asset is unavailable."""


class ChirpsRasterError(ChirpsError):
    """The asset could not be opened or does not satisfy the raster contract."""


class InvalidRasterValue(ChirpsRasterError):
    """A non-finite or negative non-data rainfall value was encountered."""


class InsufficientRasterCoverage(ChirpsRasterError):
    """A ward does not have enough valid raster coverage for the configured threshold."""


@dataclass(frozen=True)
class ChirpsRasterWindow:
    array: np.ma.MaskedArray
    transform: Affine
    crs: str
    nodata: float | None
    resolution: tuple[float, float]
    transform_values: tuple[float, float, float, float, float, float]
    source_url: str
    asset_filename: str
    etag: str | None
    last_modified: str | None
    content_length: int | None
    retrieval_timestamp: str
    full_asset_sha256: str | None
    extracted_window_sha256: str
    source_access_mode: str


@dataclass(frozen=True)
class ChirpsZonalStats:
    rainfall_mm: float
    valid_pixel_count: int
    ward_coverage_fraction: float
    covered_area: float
    weighted_sum: float


def chirps_max_date_range_days() -> int:
    return config(
        "CHIRPS_MAX_DATE_RANGE_DAYS",
        cast=int,
        default=CHIRPS_DEFAULT_MAX_DATE_RANGE_DAYS,
    )


def chirps_min_coverage_fraction() -> float:
    return config(
        "CHIRPS_MIN_WARD_COVERAGE_FRACTION",
        cast=float,
        default=CHIRPS_DEFAULT_MIN_COVERAGE_FRACTION,
    )


def validate_variant_date_range(*, variant: str, start_date: date, end_date: date) -> None:
    if variant not in CHIRPS_DAILY_VARIANTS:
        raise ValueError(f"Unsupported CHIRPS daily variant: {variant}")
    if end_date < start_date:
        raise ValueError("CHIRPS end date must be on or after start date.")
    available_from = CHIRPS_DAILY_VARIANTS[variant]["available_from"]
    if start_date < available_from:
        raise ValueError(
            f"CHIRPS daily/{CHIRPS_PRODUCT_STATUS_FINAL}/{variant} is documented from "
            f"{available_from.isoformat()}; select one variant for the whole period "
            f"(use --variant rnl for dates before 1998-01-01)."
        )


def build_chirps_asset_url(
    source_date: date,
    *,
    variant: str,
    product_status: str = CHIRPS_PRODUCT_STATUS_FINAL,
) -> str:
    """Build and validate an allowlisted official CHC asset URL."""

    if product_status not in CHIRPS_PRODUCT_STATUSES:
        raise ValueError(f"Unsupported CHIRPS product status: {product_status}")
    if variant not in CHIRPS_DAILY_VARIANTS:
        raise ValueError(f"Unsupported CHIRPS daily variant: {variant}")

    filename = f"chirps-v3.0.{variant}.{source_date:%Y.%m.%d}.cog"
    path = (
        f"/products/CHIRPS/{CHIRPS_VERSION}/daily/{product_status}/{variant}/"
        f"cogs/{source_date:%Y}/{filename}"
    )
    url = f"https://{CHIRPS_SOURCE_HOST}{path}"
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != CHIRPS_SOURCE_HOST
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith(CHIRPS_SOURCE_PATH_PREFIX)
    ):
        raise ValueError("Generated CHIRPS URL failed the official-host allowlist.")
    return url


def _header(headers: Any, name: str) -> str | None:
    if not headers:
        return None
    lowered = name.lower()
    for key, value in dict(headers).items():
        if str(key).lower() == lowered:
            return str(value) if value not in (None, "") else None
    return None


def _content_length(headers: Any, fallback: int | None = None) -> int | None:
    value = _header(headers, "Content-Length")
    if value is None:
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _masked_array_sha256(array: np.ma.MaskedArray) -> str:
    masked = np.ma.array(array, copy=False)
    data = np.ascontiguousarray(masked.data).tobytes()
    mask = np.ascontiguousarray(np.ma.getmaskarray(masked)).tobytes()
    return hashlib.sha256(data + mask).hexdigest()


def _geometry_to_shapely(geometry: BaseGeometry | Any) -> BaseGeometry:
    if isinstance(geometry, BaseGeometry):
        return geometry
    if hasattr(geometry, "wkb"):
        return shapely_wkb.loads(bytes(geometry.wkb))
    if hasattr(geometry, "__geo_interface__"):
        return shape(geometry.__geo_interface__)
    raise TypeError("Ward geometry must be a Shapely or GeoDjango geometry.")


def _window_for_bounds(dataset, bounds: tuple[float, float, float, float]) -> Window:
    source_bounds = bounds
    dataset_crs = str(dataset.crs) if dataset.crs else ""
    if dataset_crs and dataset_crs.upper() not in {"EPSG:4326", "OGC:CRS84"}:
        source_bounds = transform_bounds("EPSG:4326", dataset.crs, *bounds, densify_pts=21)

    raw_window = from_bounds(*source_bounds, transform=dataset.transform)
    left = max(0, math.floor(raw_window.col_off))
    top = max(0, math.floor(raw_window.row_off))
    right = min(dataset.width, math.ceil(raw_window.col_off + raw_window.width))
    bottom = min(dataset.height, math.ceil(raw_window.row_off + raw_window.height))
    if right <= left or bottom <= top:
        raise ChirpsRasterError("Migori ward bounding box does not intersect the CHIRPS raster.")
    try:
        return Window(left, top, right - left, bottom - top)
    except WindowError as exc:
        raise ChirpsRasterError(f"Invalid CHIRPS raster window: {exc}") from exc


def _read_dataset_window(dataset, bounds: tuple[float, float, float, float]):
    if dataset.count < 1 or dataset.crs is None:
        raise ChirpsRasterError("CHIRPS asset must contain at least one band and a CRS.")
    window = _window_for_bounds(dataset, bounds)
    array = dataset.read(1, window=window, masked=True)
    if array.size == 0:
        raise ChirpsRasterError("CHIRPS raster window is empty.")
    transform = dataset.window_transform(window)
    crs = str(dataset.crs)
    nodata = float(dataset.nodata) if dataset.nodata is not None else None
    resolution = (abs(float(transform.a)), abs(float(transform.e)))
    transform_values = (
        float(transform.a),
        float(transform.b),
        float(transform.c),
        float(transform.d),
        float(transform.e),
        float(transform.f),
    )
    return array, transform, crs, nodata, resolution, transform_values


def _read_remote_cog_window(url: str, bounds: tuple[float, float, float, float]):
    remote_url = f"/vsicurl/{url}"
    with rasterio.open(remote_url) as dataset:
        return _read_dataset_window(dataset, bounds)


def _read_full_asset_window(content: bytes, bounds: tuple[float, float, float, float]):
    try:
        with MemoryFile(content) as memory_file:
            with memory_file.open() as dataset:
                return _read_dataset_window(dataset, bounds)
    except (rasterio.errors.RasterioIOError, ChirpsError) as exc:
        if isinstance(exc, ChirpsError):
            raise
        raise ChirpsRasterError(f"Downloaded CHIRPS asset is not a readable raster: {exc}") from exc


class ChirpsConnector:
    """Retrieve one official CHIRPS asset and extract one Migori window."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout_seconds: int | None = None,
        use_remote_window: bool = True,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds or config(
            "CHIRPS_HTTP_TIMEOUT_SECONDS",
            cast=int,
            default=60,
        )
        self.use_remote_window = use_remote_window
        self._cache: dict[tuple[date, str, tuple[float, float, float, float]], ChirpsRasterWindow] = {}

    def fetch_window(
        self,
        source_date: date,
        *,
        variant: str,
        product_status: str,
        bounds: tuple[float, float, float, float],
    ) -> ChirpsRasterWindow:
        validate_variant_date_range(variant=variant, start_date=source_date, end_date=source_date)
        if product_status not in CHIRPS_PRODUCT_STATUSES:
            raise ValueError(f"Unsupported CHIRPS product status: {product_status}")

        cache_key = (source_date, variant, tuple(float(value) for value in bounds))
        if cache_key in self._cache:
            return self._cache[cache_key]

        url = build_chirps_asset_url(source_date, variant=variant, product_status=product_status)
        filename = PurePosixPath(urlparse(url).path).name
        retrieval_timestamp = timezone_now_iso()
        etag = None
        last_modified = None
        content_length = None
        head_status = None

        try:
            head_response = self.session.head(
                url,
                timeout=self.timeout_seconds,
                allow_redirects=False,
            )
            head_status = int(getattr(head_response, "status_code", 0) or 0)
            if head_status == 404:
                raise ChirpsAssetUnavailable(f"CHIRPS asset is unavailable: {url}")
            if 200 <= head_status < 400:
                etag = _header(getattr(head_response, "headers", {}), "ETag")
                last_modified = _header(getattr(head_response, "headers", {}), "Last-Modified")
                content_length = _content_length(getattr(head_response, "headers", {}))
        except ChirpsAssetUnavailable:
            raise
        except requests.RequestException:
            # Some object stores do not support HEAD.  GET below remains the
            # authoritative availability check.
            head_status = None

        remote_error: Exception | None = None
        # Keep remote-window mode tied to usable HTTP metadata. If HEAD is
        # unavailable, the bounded full download gives us a complete SHA-256
        # and exact content length for provenance.
        if self.use_remote_window and head_status != 404 and content_length is not None:
            try:
                array, transform, crs, nodata, resolution, transform_values = _read_remote_cog_window(url, bounds)
                window = ChirpsRasterWindow(
                    array=np.ma.array(array, copy=False),
                    transform=transform,
                    crs=crs,
                    nodata=nodata,
                    resolution=resolution,
                    transform_values=transform_values,
                    source_url=url,
                    asset_filename=filename,
                    etag=etag,
                    last_modified=last_modified,
                    content_length=content_length,
                    retrieval_timestamp=retrieval_timestamp,
                    full_asset_sha256=None,
                    extracted_window_sha256=_masked_array_sha256(array),
                    source_access_mode="remote_cog_window",
                )
                self._cache[cache_key] = window
                return window
            except Exception as exc:  # GDAL range access is an optional optimization.
                remote_error = exc

        try:
            response = self.session.get(url, timeout=self.timeout_seconds, allow_redirects=False)
            status_code = int(getattr(response, "status_code", 0) or 0)
            if status_code == 404:
                raise ChirpsAssetUnavailable(f"CHIRPS asset is unavailable: {url}")
            if status_code < 200 or status_code >= 300:
                raise ChirpsAssetUnavailable(f"CHIRPS asset request failed with HTTP {status_code}: {url}")
            response_headers = getattr(response, "headers", {})
            etag = etag or _header(response_headers, "ETag")
            last_modified = last_modified or _header(response_headers, "Last-Modified")
            content = bytes(getattr(response, "content", b""))
            if not content:
                raise ChirpsAssetUnavailable(f"CHIRPS asset response was empty: {url}")
            content_length = content_length or _content_length(response_headers, len(content))
        except ChirpsAssetUnavailable:
            raise
        except requests.RequestException as exc:
            detail = f"; remote COG error: {remote_error}" if remote_error else ""
            raise ChirpsAssetUnavailable(f"Could not retrieve CHIRPS asset {url}: {exc}{detail}") from exc

        full_asset_sha256 = hashlib.sha256(content).hexdigest()
        array, transform, crs, nodata, resolution, transform_values = _read_full_asset_window(content, bounds)
        window = ChirpsRasterWindow(
            array=np.ma.array(array, copy=False),
            transform=transform,
            crs=crs,
            nodata=nodata,
            resolution=resolution,
            transform_values=transform_values,
            source_url=url,
            asset_filename=filename,
            etag=etag,
            last_modified=last_modified,
            content_length=content_length,
            retrieval_timestamp=retrieval_timestamp,
            full_asset_sha256=full_asset_sha256,
            extracted_window_sha256=_masked_array_sha256(array),
            source_access_mode="full_asset_download_once",
        )
        self._cache[cache_key] = window
        return window


def _cell_polygon(transform: Affine, row: int, column: int) -> BaseGeometry:
    from shapely.geometry import Polygon

    top_left = transform * (column, row)
    top_right = transform * (column + 1, row)
    bottom_right = transform * (column + 1, row + 1)
    bottom_left = transform * (column, row + 1)
    return Polygon([top_left, top_right, bottom_right, bottom_left, top_left])


def fractional_zonal_stats(
    array: np.ma.MaskedArray | np.ndarray,
    *,
    transform: Affine,
    ward_geometry: BaseGeometry | Any,
    nodata: float | None,
    min_coverage_fraction: float | None = None,
    ward_label: str = "ward",
) -> ChirpsZonalStats:
    """Compute an area-weighted mean using fractional cell intersections.

    The denominator is the area covered by valid raster cells.  No-data cells
    are excluded from both numerator and denominator; invalid negative or
    non-finite values are rejected rather than silently repaired.
    """

    masked = np.ma.array(array, copy=False)
    if masked.ndim != 2:
        raise ChirpsRasterError("CHIRPS extraction expects a single two-dimensional raster band.")

    geometry = _geometry_to_shapely(ward_geometry)
    if geometry.is_empty or geometry.area <= 0:
        raise ChirpsRasterError(f"{ward_label} has an empty or zero-area canonical polygon.")
    if not geometry.is_valid:
        raise ChirpsRasterError(f"{ward_label} canonical polygon is invalid.")

    coverage_threshold = (
        chirps_min_coverage_fraction()
        if min_coverage_fraction is None
        else float(min_coverage_fraction)
    )
    if not 0 < coverage_threshold <= 1:
        raise ValueError("CHIRPS coverage threshold must be greater than zero and at most one.")

    min_x, min_y, max_x, max_y = geometry.bounds
    extraction_bounds = box(min_x, min_y, max_x, max_y)
    valid_pixel_count = 0
    covered_area = 0.0
    weighted_sum = 0.0
    mask = np.ma.getmaskarray(masked)

    # The extracted window is already bounded to all ward geometries, so this
    # loop processes each cell once and never downloads/reads once per ward.
    for row in range(masked.shape[0]):
        for column in range(masked.shape[1]):
            cell = _cell_polygon(transform, row, column)
            if not cell.intersects(extraction_bounds):
                continue
            intersection = geometry.intersection(cell)
            intersection_area = float(intersection.area)
            if intersection_area <= 0:
                continue

            if bool(mask[row, column]):
                continue
            value = float(masked.data[row, column])
            if nodata is not None and (
                (math.isnan(nodata) and math.isnan(value))
                or (not math.isnan(nodata) and value == nodata)
            ):
                continue
            if not math.isfinite(value) or value < 0:
                raise InvalidRasterValue(
                    f"{ward_label} contains invalid CHIRPS rainfall value {value!r} "
                    f"at raster row={row}, column={column}."
                )

            valid_pixel_count += 1
            covered_area += intersection_area
            weighted_sum += value * intersection_area

    ward_area = float(geometry.area)
    coverage_fraction = covered_area / ward_area if ward_area else 0.0
    if coverage_fraction > 1 and coverage_fraction <= 1 + CHIRPS_COVERAGE_NUMERICAL_EPSILON:
        # GEOS intersection arithmetic can exceed the polygon area by a few
        # ulps when a valid window exactly covers a ward. Normalize that
        # numerical artifact so persisted coverage remains in [0, 1].
        scale = ward_area / covered_area
        weighted_sum *= scale
        covered_area = ward_area
        coverage_fraction = 1.0
    elif coverage_fraction > 1:
        raise ChirpsRasterError(
            f"{ward_label} has impossible CHIRPS coverage fraction {coverage_fraction:.12f}."
        )
    if covered_area <= 0 or coverage_fraction < coverage_threshold:
        raise InsufficientRasterCoverage(
            f"{ward_label} has CHIRPS valid coverage fraction {coverage_fraction:.6f}; "
            f"required at least {coverage_threshold:.6f}."
        )
    return ChirpsZonalStats(
        rainfall_mm=weighted_sum / covered_area,
        valid_pixel_count=valid_pixel_count,
        ward_coverage_fraction=coverage_fraction,
        covered_area=covered_area,
        weighted_sum=weighted_sum,
    )


def ward_geometry_in_raster_crs(ward_geometry: BaseGeometry | Any, raster_crs: str) -> BaseGeometry:
    geometry = _geometry_to_shapely(ward_geometry)
    if raster_crs.upper() in {"EPSG:4326", "OGC:CRS84"}:
        return geometry
    transformed = transform_geom("EPSG:4326", raster_crs, geometry.__geo_interface__, precision=-1)
    return shape(transformed)


def timezone_now_iso() -> str:
    # Imported lazily to keep this connector's pure raster helpers easy to use
    # from unit tests that do not initialize Django.
    from django.utils import timezone

    return timezone.now().isoformat()
