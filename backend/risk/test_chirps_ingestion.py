import json
from datetime import date, datetime, timezone
from unittest import TestCase

import numpy as np
from django.test import TestCase as DjangoTestCase
from django.contrib.gis.geos import GEOSGeometry
from django.db.models import Count
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from risk.chirps_audit import build_chirps_ingestion_audit
from risk.chirps_ingestion import ingest_chirps_rainfall
from risk.climate.connectors.chirps import (
    CHIRPS_PROVIDER,
    ChirpsAssetUnavailable,
    ChirpsConnector,
    ChirpsRasterWindow,
    InvalidRasterValue,
    fractional_zonal_stats,
    build_chirps_asset_url,
    validate_variant_date_range,
)
from risk.lead_time_features import (
    LEAD_TIME_FEATURE_SCHEMA_VERSION,
    _rainfall_window_features,
    build_lead_time_feature_dataset,
)
from risk.models import ClimateRecord, ClimateRecordType, FeatureDataset, FeatureDatasetRow, IngestionRun, Ward


def _multipolygon(x0: float, y0: float, x1: float, y1: float) -> GEOSGeometry:
    return GEOSGeometry(
        json.dumps(
            {
                "type": "MultiPolygon",
                "coordinates": [[[
                    [x0, y0],
                    [x1, y0],
                    [x1, y1],
                    [x0, y1],
                    [x0, y0],
                ]]],
            }
        ),
        srid=4326,
    )


def _raster_bytes(values: np.ndarray, *, nodata: float = -9999.0) -> bytes:
    with MemoryFile() as memory_file:
        with memory_file.open(
            driver="GTiff",
            height=values.shape[0],
            width=values.shape[1],
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(0, 2, 1, 1),
            nodata=nodata,
        ) as dataset:
            dataset.write(values.astype("float32"), 1)
        return memory_file.read()


def _window(values: np.ndarray) -> ChirpsRasterWindow:
    transform = from_origin(0, 2, 1, 1)
    masked = np.ma.masked_equal(values.astype("float32"), -9999.0)
    return ChirpsRasterWindow(
        array=masked,
        transform=transform,
        crs="EPSG:4326",
        nodata=-9999.0,
        resolution=(1.0, 1.0),
        transform_values=(1.0, 0.0, 0.0, 0.0, -1.0, 2.0),
        source_url=build_chirps_asset_url(date(2020, 1, 1), variant="sat"),
        asset_filename="chirps-v3.0.sat.2020.01.01.cog",
        etag='"fixture-etag"',
        last_modified="Wed, 01 Jan 2020 00:00:00 GMT",
        content_length=123,
        retrieval_timestamp="2026-08-07T10:00:00+00:00",
        full_asset_sha256=None,
        extracted_window_sha256="fixture-window-hash",
        source_access_mode="fixture",
    )


class StubConnector:
    def __init__(self, window, *, unavailable_dates=()):
        self.window = window
        self.unavailable_dates = set(unavailable_dates)

    def fetch_window(self, source_date, **kwargs):
        if source_date in self.unavailable_dates:
            raise ChirpsAssetUnavailable(f"fixture unavailable for {source_date.isoformat()}")
        return self.window


class ChirpsRasterAggregationTests(TestCase):
    def test_official_url_and_pre_1998_variant_guard(self):
        self.assertEqual(
            build_chirps_asset_url(date(2024, 1, 1), variant="sat"),
            "https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/sat/cogs/2024/"
            "chirps-v3.0.sat.2024.01.01.cog",
        )
        with self.assertRaisesRegex(ValueError, "use --variant rnl"):
            validate_variant_date_range(
                variant="sat",
                start_date=date(1997, 12, 31),
                end_date=date(1998, 1, 1),
            )

    def test_local_cog_fixture_and_fractional_edge_pixels_produce_weighted_mean(self):
        content = _raster_bytes(np.array([[1, 2], [3, 4]], dtype=np.float32))

        class Response:
            def __init__(self, payload):
                self.status_code = 200
                self.headers = {"Content-Length": str(len(payload)), "ETag": '"local"'}
                self._payload = payload

            @property
            def content(self):
                return self._payload

        class Session:
            def head(self, *args, **kwargs):
                return Response(content)

            def get(self, *args, **kwargs):
                return Response(content)

        connector = ChirpsConnector(session=Session(), use_remote_window=False)
        asset = connector.fetch_window(
            date(2020, 1, 1),
            variant="sat",
            product_status="final",
            bounds=(0.5, 0.5, 1.5, 1.5),
        )
        stats = fractional_zonal_stats(
            asset.array,
            transform=asset.transform,
            ward_geometry=_multipolygon(0.5, 0.5, 1.5, 1.5),
            nodata=asset.nodata,
            min_coverage_fraction=0.99,
        )

        self.assertAlmostEqual(stats.rainfall_mm, 2.5)
        self.assertEqual(stats.valid_pixel_count, 4)
        self.assertAlmostEqual(stats.ward_coverage_fraction, 1.0)
        self.assertIsNotNone(asset.full_asset_sha256)

    def test_no_data_is_excluded_and_negative_values_are_rejected(self):
        stats = fractional_zonal_stats(
            np.ma.array([[1, -9999], [3, 4]], mask=[[False, True], [False, False]]),
            transform=from_origin(0, 2, 1, 1),
            ward_geometry=_multipolygon(0, 0, 2, 2),
            nodata=-9999,
            min_coverage_fraction=0.5,
        )
        self.assertAlmostEqual(stats.rainfall_mm, 8 / 3)
        self.assertEqual(stats.valid_pixel_count, 3)

        with self.assertRaises(InvalidRasterValue):
            fractional_zonal_stats(
                np.ma.array([[1, -2], [3, 4]], mask=False),
                transform=from_origin(0, 2, 1, 1),
                ward_geometry=_multipolygon(0, 0, 2, 2),
                nodata=-9999,
                min_coverage_fraction=0.5,
            )


class ChirpsIngestionTests(DjangoTestCase):
    def setUp(self):
        self.ward_a = Ward.objects.create(
            name="CHIRPS Ward A",
            county="Migori",
            ward_code="CH-A",
            boundary=_multipolygon(0, 1, 1, 2),
        )
        self.ward_b = Ward.objects.create(
            name="CHIRPS Ward B",
            county="Migori",
            ward_code="CH-B",
            boundary=_multipolygon(1, 0, 2, 1),
        )

    def test_all_active_wards_are_mapped_and_rerun_is_idempotent(self):
        source_date = date(2020, 1, 1)
        connector = StubConnector(_window(np.array([[1, 2], [3, 4]], dtype=np.float32)))
        first = ingest_chirps_rainfall(
            start_date=source_date,
            end_date=source_date,
            variant="sat",
            connector=connector,
        )
        self.assertEqual(first["status"], IngestionRun.STATUS_SUCCESS)
        self.assertEqual(first["records_created"], 2)
        self.assertEqual(ClimateRecord.objects.filter(source_provider=CHIRPS_PROVIDER).count(), 2)
        self.assertEqual(
            set(ClimateRecord.objects.values_list("ward_id", flat=True)),
            {self.ward_a.id, self.ward_b.id},
        )

        second = ingest_chirps_rainfall(
            start_date=source_date,
            end_date=source_date,
            variant="sat",
            connector=connector,
        )
        self.assertEqual(second["status"], IngestionRun.STATUS_SUCCESS)
        self.assertEqual(second["records_created"], 0)
        self.assertEqual(second["records_skipped"], 2)
        self.assertEqual(ClimateRecord.objects.filter(source_provider=CHIRPS_PROVIDER).count(), 2)
        self.assertEqual(
            ClimateRecord.objects.values("identity_key").annotate(count=Count("id")).filter(count__gt=1).count(),
            0,
        )

        records = list(ClimateRecord.objects.order_by("ward_id"))
        self.assertTrue(all(record.record_type == "observed" for record in records))
        self.assertTrue(all(record.source_kind == IngestionRun.SOURCE_KIND_LIVE for record in records))
        self.assertTrue(all(record.fallback_flag is False for record in records))
        self.assertTrue(
            all(record.source_run == "chirps-ingestion:v3.0:final:sat:2020-01-01" for record in records)
        )
        self.assertTrue(all(record.lineage_metadata["product_status"] == "final" for record in records))
        self.assertTrue(all(record.lineage_metadata["daily_variant"] == "sat" for record in records))
        self.assertTrue(
            all(record.lineage_metadata["ward_public_id"] == str(record.ward.public_id) for record in records)
        )

    def test_valid_ingestion_passes_strict_chirps_audit(self):
        source_date = date(2020, 1, 1)
        summary = ingest_chirps_rainfall(
            start_date=source_date,
            end_date=source_date,
            variant="sat",
            connector=StubConnector(_window(np.array([[1, 2], [3, 4]], dtype=np.float32))),
        )
        record = ClimateRecord.objects.get(ward=self.ward_a)
        dataset = FeatureDataset.objects.create(
            dataset_ref="chirps-audit-feature-fixture",
            dataset_kind=FeatureDataset.KIND_INFERENCE,
            schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION,
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            feature_keys=["chirps_observed_rainfall_total_7d"],
            row_count=1,
            lineage_metadata={
                "chirps_daily_variant": "sat",
                "chirps_historical_feature_policy": {
                    "daily_variant": "sat",
                    "allowed_daily_variants": ["sat"],
                    "reject_mixed_variants": True,
                },
            },
        )
        FeatureDatasetRow.objects.create(
            dataset=dataset,
            ward=self.ward_a,
            ward_name_snapshot=self.ward_a.name,
            month=1,
            feature_values={
                "prediction_date": "2020-01-02",
                "source_cutoff_timestamp": "2020-01-02T00:00:00+00:00",
                "chirps_daily_variant": "sat",
                "source_lineage": {"rainfall": {"chirps_source_refs": [record.source_ref]}},
            },
        )

        audit = build_chirps_ingestion_audit()
        self.assertEqual(summary["status"], IngestionRun.STATUS_SUCCESS)
        self.assertEqual(audit["overall_status"], "pass")
        self.assertTrue(all(check["status"] == "pass" for check in audit["checks"]))

    def test_retrospective_mode_persists_chirps_backed_feature_rows(self):
        source_date = date(2020, 1, 1)
        ingest_chirps_rainfall(
            start_date=source_date,
            end_date=source_date,
            variant="sat",
            connector=StubConnector(_window(np.array([[1, 2], [3, 4]], dtype=np.float32))),
        )

        standard_snapshot = build_lead_time_feature_dataset(
            [self.ward_a, self.ward_b],
            prediction_dates=[date(2020, 1, 2)],
            chirps_variant="sat",
        )
        standard_rows = FeatureDatasetRow.objects.filter(dataset=standard_snapshot.feature_dataset)
        self.assertTrue(
            all(
                (row.feature_values.get("source_lineage", {}).get("rainfall", {}).get("chirps_source_refs") or [])
                == []
                for row in standard_rows
            )
        )

        snapshot = build_lead_time_feature_dataset(
            [self.ward_a, self.ward_b],
            prediction_dates=[date(2020, 1, 2)],
            retrospective_chirps=True,
            chirps_variant="sat",
        )

        dataset = snapshot.feature_dataset
        rows = list(FeatureDatasetRow.objects.filter(dataset=dataset).order_by("ward_id"))
        self.assertEqual(dataset.row_count, 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(dataset.lineage_metadata["chirps_daily_variant"], "sat")
        self.assertTrue(dataset.lineage_metadata["retrospective_chirps_mode"])
        self.assertEqual(
            dataset.lineage_metadata["coverage"]["rows_with_chirps_observed_rainfall_records"],
            2,
        )
        for row in rows:
            self.assertEqual(row.feature_values["chirps_daily_variant"], "sat")
            self.assertTrue(row.feature_values["retrospective_chirps_mode"])
            self.assertGreater(row.feature_values["chirps_observed_rainfall_total_7d"], 0)
            self.assertEqual(len(row.feature_values["source_lineage"]["rainfall"]["chirps_source_refs"]), 1)
            self.assertLess(
                max(
                    ClimateRecord.objects.get(source_ref=source_ref).valid_date
                    for source_ref in row.feature_values["source_lineage"]["rainfall"]["chirps_source_refs"]
                ),
                date(2020, 1, 2),
            )

        audit = build_chirps_ingestion_audit()
        self.assertEqual(audit["overall_status"], "pass")
        self.assertEqual(
            next(check for check in audit["checks"] if check["id"] == "chirps_feature_variant_pinning")["status"],
            "pass",
        )

    def test_feature_loader_rejects_mixed_chirps_variants(self):
        source_date = date(2020, 1, 1)
        ingest_chirps_rainfall(
            start_date=source_date,
            end_date=source_date,
            variant="sat",
            connector=StubConnector(_window(np.array([[1, 2], [3, 4]], dtype=np.float32))),
        )
        sat_record = ClimateRecord.objects.filter(source_provider=CHIRPS_PROVIDER).order_by("id").first()
        ClimateRecord.objects.create(
            ward=self.ward_a,
            ingestion_run=sat_record.ingestion_run,
            record_type=ClimateRecordType.OBSERVED,
            source_provider=CHIRPS_PROVIDER,
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_mode="final-rnl",
            valid_date=source_date,
            observed_timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc),
            rainfall_mm=4.0,
            quality_flag="accepted",
            fallback_flag=False,
            source_run="chirps-ingestion:v3.0:final:rnl:2020-01-01",
            source_ref="chirps:v3.0:final:rnl:2020-01-01:ward-a",
            identity_key="chirps-v3.0|v3.0|final|rnl|2020-01-01|ward-a|chirps-fractional-zonal-v1",
            lineage_metadata={
                "provider": CHIRPS_PROVIDER,
                "daily_variant": "rnl",
                "source_date": source_date.isoformat(),
            },
        )

        with self.assertRaisesRegex(ValueError, "cannot mix daily variants|variant mismatch"):
            build_lead_time_feature_dataset(
                [self.ward_a],
                prediction_dates=[date(2020, 1, 2)],
                retrospective_chirps=True,
                chirps_variant="sat",
            )

    def test_audit_does_not_pass_without_persisted_feature_rows(self):
        ingest_chirps_rainfall(
            start_date=date(2020, 1, 1),
            end_date=date(2020, 1, 1),
            variant="sat",
            connector=StubConnector(_window(np.array([[1, 2], [3, 4]], dtype=np.float32))),
        )

        audit = build_chirps_ingestion_audit()
        feature_check = next(check for check in audit["checks"] if check["id"] == "chirps_feature_temporal_cutoffs")
        self.assertEqual(audit["overall_status"], "fail")
        self.assertEqual(feature_check["status"], "fail")
        self.assertEqual(feature_check["evidence"]["feature_rows_scanned"], 0)

    def test_missing_source_date_is_failed_without_static_fallback(self):
        source_date = date(2020, 1, 2)
        summary = ingest_chirps_rainfall(
            start_date=source_date,
            end_date=source_date,
            variant="sat",
            connector=StubConnector(_window(np.array([[1, 2], [3, 4]], dtype=np.float32)), unavailable_dates=[source_date]),
        )
        self.assertEqual(summary["status"], IngestionRun.STATUS_FAILED)
        self.assertEqual(summary["records_created"], 0)
        self.assertFalse(ClimateRecord.objects.filter(valid_date=source_date).exists())
        run = IngestionRun.objects.get(pk=summary["run_id"])
        self.assertFalse(run.fallback_used)
        self.assertEqual(run.source_kind, IngestionRun.SOURCE_KIND_LIVE)

    def test_future_chirps_record_cannot_change_an_earlier_feature_window(self):
        cutoff = datetime(2020, 1, 10, tzinfo=timezone.utc)
        observations = [
            {
                "ingestion_run_id": 1,
                "rainfall_mm": 10.0,
                "observed_at": datetime(2020, 1, 9, tzinfo=timezone.utc),
                "source": CHIRPS_PROVIDER,
                "source_kind": IngestionRun.SOURCE_KIND_LIVE,
                "source_mode": "final-sat",
                "canonical_record_ref": "past",
                "source_record_ref": "climate_record:past",
                "valid_date": date(2020, 1, 9),
                "record_type": "observed",
                "quality_flag": "accepted",
            },
            {
                "ingestion_run_id": 2,
                "rainfall_mm": 1.0,
                "observed_at": datetime(2020, 1, 11, tzinfo=timezone.utc),
                "source": CHIRPS_PROVIDER,
                "source_kind": IngestionRun.SOURCE_KIND_LIVE,
                "source_mode": "final-sat",
                "canonical_record_ref": "future",
                "source_record_ref": "climate_record:future",
                "valid_date": date(2020, 1, 11),
                "record_type": "observed",
                "quality_flag": "accepted",
            },
        ]
        base, _ = _rainfall_window_features(
            observations=observations,
            prediction_date=date(2020, 1, 10),
            source_cutoff=cutoff,
            heavy_rain_threshold_mm=50,
        )
        observations[-1]["rainfall_mm"] = 9999.0
        changed_future, _ = _rainfall_window_features(
            observations=observations,
            prediction_date=date(2020, 1, 10),
            source_cutoff=cutoff,
            heavy_rain_threshold_mm=50,
        )
        self.assertEqual(base["chirps_observed_rainfall_total_7d"], 10.0)
        self.assertEqual(base["chirps_observed_rainfall_total_7d"], changed_future["chirps_observed_rainfall_total_7d"])

    def test_chirps_audit_detects_missing_records_as_strict_failure(self):
        audit = build_chirps_ingestion_audit()
        self.assertEqual(audit["overall_status"], "fail")
        self.assertTrue(any(check["id"] == "genuine_chirps_observed_record_exists" for check in audit["checks"]))
