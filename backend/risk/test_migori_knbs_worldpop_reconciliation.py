import json
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from risk.migori_knbs_worldpop_reconciliation import (
    build_migori_knbs_worldpop_reconciliation,
    extract_county_2019_baseline,
    extract_county_projection,
    extract_sub_county_2019_rows,
)
from risk.migori_worldpop_population_import import DEFAULT_RELEASE_VERSION, DEFAULT_SOURCE_NAME, DEFAULT_SOURCE_TYPE
from risk.models import (
    ExposureFeatureRecord,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
    Ward,
)


class KnbsWorkbookExtractionTestCase(SimpleTestCase):
    def test_extracts_baseline_sub_counties_and_interpolated_projection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            county_path = Path(tmpdir) / "county.xlsx"
            sub_county_path = Path(tmpdir) / "subcounty.xlsx"
            projection_path = Path(tmpdir) / "projection.xlsx"
            self._write_xlsx(
                county_path,
                {
                    "sheet1.xml": [
                        ["County", "Total", "Male", "Female", "Intersex", "Households", "Conventional", "Group", "Area", "Density"],
                        ["    MIGORI", 1116436, 536187, 580214, 35, 240168, 238133, 2035, 2613.4842, 427.183],
                    ]
                },
            )
            self._write_xlsx(
                sub_county_path,
                {
                    "sheet1.xml": [
                        ["Sub County", "Total", "Male", "Female", "Households", "Conventional", "Group", "Area", "Density"],
                        ["    MIGORI", 300, 0, 0, 0, 0, 0, 0, 0],
                        ["        A", 100, 0, 0, 0, 0, 0, 1, 100],
                        ["        B", 200, 0, 0, 0, 0, 0, 2, 100],
                        ["    KISII", 1, 0, 0, 0, 0, 0, 0, 0],
                    ]
                },
            )
            self._write_xlsx(
                projection_path,
                {
                    "sheet1.xml": [["unused"]],
                    "sheet2.xml": [
                        ["Table"],
                        [""],
                        ["County", 2025, 2030],
                        ["Migori", 1292, 1444],
                    ],
                },
            )

            baseline = extract_county_2019_baseline(county_path)
            sub_counties = extract_sub_county_2019_rows(sub_county_path)
            projection = extract_county_projection(projection_path, target_year=2026)

        self.assertEqual(baseline["total_population"], 1116436)
        self.assertEqual(sub_counties["sub_county_population_sum"], 300)
        self.assertEqual(projection["target_projection"], 1322400)
        self.assertEqual(projection["method"], "linear_interpolation_2025_2030")

    def _write_xlsx(self, path: Path, sheets: dict[str, list[list[object]]]) -> None:
        with ZipFile(path, "w", ZIP_DEFLATED) as archive:
            for sheet_name, rows in sheets.items():
                archive.writestr(f"xl/worksheets/{sheet_name}", self._sheet_xml(rows))

    def _sheet_xml(self, rows: list[list[object]]) -> str:
        body = []
        for row_index, row in enumerate(rows, start=1):
            cells = []
            for column_index, value in enumerate(row, start=1):
                ref = f"{chr(64 + column_index)}{row_index}"
                if isinstance(value, (int, float)):
                    cells.append(f'<c r="{ref}"><v>{value}</v></c>')
                else:
                    cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>')
            body.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(body)}</sheetData></worksheet>'
        )


class MigoriKnbsWorldPopReconciliationTestCase(TestCase):
    def test_reconciliation_passes_when_worldpop_matches_projection_threshold(self):
        ward = Ward.objects.create(name="Alpha", county="Migori", ward_code="KE-WARD-1")
        source = PopulationExposureSource.objects.create(
            source_name="seed",
            source_type=PopulationExposureSource.SOURCE_TYPE_CSV_BACKFILL,
            source_timestamp=timezone.now(),
        )
        run = PopulationExposureIngestionRun.objects.create(
            source=source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name="seed",
            source_type=PopulationExposureSource.SOURCE_TYPE_CSV_BACKFILL,
            records_seen=1,
            records_loaded=1,
        )
        PopulationBaselineRecord.objects.create(
            ward=ward,
            ingestion_run=run,
            source=source,
            population_total=100,
            truth_class=PopulationExposureTruth.SEEDED_DEMO,
            source_name="seed",
            source_kind=PopulationExposureSourceKind.SEEDED,
            freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE,
        )
        ExposureFeatureRecord.objects.create(
            ward=ward,
            ingestion_run=run,
            source=source,
            exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
            exposure_value=10,
            truth_class=PopulationExposureTruth.SEEDED_DEMO,
            source_name="seed",
            source_kind=PopulationExposureSourceKind.SEEDED,
            freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE,
        )
        other_county_ward = Ward.objects.create(name="Beta", county="Kisumu", ward_code="KE-WARD-2")
        PopulationBaselineRecord.objects.create(
            ward=other_county_ward,
            ingestion_run=run,
            source=source,
            population_total=999999,
            truth_class=PopulationExposureTruth.SEEDED_DEMO,
            source_name="seed",
            source_kind=PopulationExposureSourceKind.SEEDED,
            freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE,
        )
        worldpop_source = PopulationExposureSource.objects.create(
            source_name=DEFAULT_SOURCE_NAME,
            source_type=DEFAULT_SOURCE_TYPE,
            source_timestamp=timezone.now(),
            release_version=DEFAULT_RELEASE_VERSION,
            source_ref="worldpop",
        )
        worldpop_run = PopulationExposureIngestionRun.objects.create(
            source=worldpop_source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=worldpop_source.source_name,
            source_type=worldpop_source.source_type,
            release_version=DEFAULT_RELEASE_VERSION,
            source_ref="worldpop",
            records_seen=1,
            records_loaded=1,
        )
        PopulationBaselineRecord.objects.create(
            ward=ward,
            ingestion_run=worldpop_run,
            source=worldpop_source,
            population_total=132500,
            truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
            source_name=worldpop_source.source_name,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
        )
        ExposureFeatureRecord.objects.create(
            ward=ward,
            ingestion_run=worldpop_run,
            source=worldpop_source,
            exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
            exposure_value=100,
            truth_class=PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
            source_name=worldpop_source.source_name,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            import_summary = tmp / "import.json"
            phase1_summary = tmp / "phase1.json"
            county_path = tmp / "county.xlsx"
            sub_county_path = tmp / "subcounty.xlsx"
            projection_path = tmp / "projection.xlsx"
            import_summary.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "records": {"population_total_sum": 132500},
                        "run": {"id": worldpop_run.id, "release_version": DEFAULT_RELEASE_VERSION, "source_ref": "worldpop"},
                    }
                ),
                encoding="utf-8",
            )
            phase1_summary.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "ward_area_total_km2": 120.0,
                    }
                ),
                encoding="utf-8",
            )
            KnbsWorkbookExtractionTestCase()._write_xlsx(
                county_path,
                {
                    "sheet1.xml": [
                        ["County", "Total", "Male", "Female", "Intersex", "Households", "Conventional", "Group", "Area", "Density"],
                        ["    MIGORI", 100000, 0, 0, 0, 0, 0, 0, 100, 1000],
                    ]
                },
            )
            KnbsWorkbookExtractionTestCase()._write_xlsx(
                sub_county_path,
                {
                    "sheet1.xml": [
                        ["Sub County", "Total", "Male", "Female", "Households", "Conventional", "Group", "Area", "Density"],
                        ["    MIGORI", 100000, 0, 0, 0, 0, 0, 0, 0],
                        ["        A", 40000, 0, 0, 0, 0, 0, 1, 1],
                        ["        B", 60000, 0, 0, 0, 0, 0, 1, 1],
                    ]
                },
            )
            KnbsWorkbookExtractionTestCase()._write_xlsx(
                projection_path,
                {
                    "sheet1.xml": [["unused"]],
                    "sheet2.xml": [["Table"], [""], ["County", 2025, 2030], ["Migori", 129, 144]],
                },
            )

            summary = build_migori_knbs_worldpop_reconciliation(
                worldpop_import_summary_path=import_summary,
                phase1_summary_path=phase1_summary,
                county_baseline_path=county_path,
                sub_county_baseline_path=sub_county_path,
                projection_path=projection_path,
                expected_ward_count=1,
            )

        self.assertTrue(summary["passed"])
        self.assertTrue(summary["gates"]["worldpop_import_summary_total_matches_db"])
        self.assertTrue(summary["gates"]["worldpop_db_run_identity_expected"])
        self.assertTrue(summary["gates"]["worldpop_db_record_metadata_expected"])
        self.assertTrue(summary["gates"]["density_denominator_reconciliation_recorded"])
        self.assertEqual(summary["knbs"]["projection"]["target_projection"], 132000)
        self.assertEqual(summary["area_reconciliation"]["phase1_ward_area_total_km2"], 120.0)
        self.assertEqual(summary["seeded_demo"]["retired_population_total"], 100)
        self.assertEqual(summary["seeded_demo"]["current_seeded_population_records"], 0)
        self.assertLess(abs(summary["comparisons"]["worldpop_vs_knbs_projection"]["percentage_difference"]), 0.01)
