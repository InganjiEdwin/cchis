import json
import tempfile
from pathlib import Path

from django.test import TestCase

from risk.migori_worldpop_population_validation import build_migori_worldpop_phase2_validation
from risk.models import Ward


WORLDPOP_SOURCE_REF = (
    "https://data.worldpop.org/GIS/Population/Global_2015_2030/R2025A/2026/KEN/v1/100m/constrained/"
    "ken_pop_2026_CN_100m_R2025A_v1.tif"
)
WORLDPOP_HEADER = (
    "ward_code,ward_name,population_total,population_density,gridded_population_value,"
    "aggregation_method,spatial_resolution,unit,truth_class,source_kind,freshness_state,source_ref,notes"
)


class MigoriWorldPopPopulationValidationTestCase(TestCase):
    def test_validation_passes_clean_gridded_population_csv(self):
        Ward.objects.create(name="Alpha", county="Migori", ward_code="KE-WARD-1")
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "population.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        WORLDPOP_HEADER,
                        (
                            "KE-WARD-1,Alpha,123,45.6,123.4,"
                            "ward_sum_from_worldpop_100m_grid_pixel_centers,100m,people_per_km2,"
                            f"spatially_aggregated_source,live,fresh,{WORLDPOP_SOURCE_REF},clean row"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            phase1_summary_path = Path(tmpdir) / "summary.json"
            phase1_summary_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "output_csv_sha256": self._sha256(csv_path),
                        "source_ref": WORLDPOP_SOURCE_REF,
                    }
                ),
                encoding="utf-8",
            )

            summary = build_migori_worldpop_phase2_validation(
                csv_path=csv_path,
                phase1_summary_path=phase1_summary_path,
                expected_row_count=1,
            )

        self.assertTrue(summary["passed"])
        self.assertEqual(summary["inspection"]["records_loaded"], 1)
        self.assertEqual(summary["ward_resolution"]["resolved_distinct_ward_count"], 1)
        self.assertEqual(summary["row_contract"]["mismatch_count"], 0)
        self.assertEqual(summary["numeric_contract"]["missing_or_invalid_numeric_cell_count"], 0)
        self.assertEqual(summary["numeric_contract"]["population_rounding_mismatch_count"], 0)
        self.assertEqual(summary["formula_like_cells"], [])
        self.assertEqual(summary["pii_like_cells"], [])

    def test_validation_flags_formula_like_cells(self):
        Ward.objects.create(name="Alpha", county="Migori", ward_code="KE-WARD-1")
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "population.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        WORLDPOP_HEADER,
                        (
                            "KE-WARD-1,Alpha,123,45.6,123.4,"
                            "ward_sum_from_worldpop_100m_grid_pixel_centers,100m,people_per_km2,"
                            f"spatially_aggregated_source,live,fresh,{WORLDPOP_SOURCE_REF},=IMPORTXML()"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            phase1_summary_path = Path(tmpdir) / "summary.json"
            phase1_summary_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "output_csv_sha256": self._sha256(csv_path),
                        "source_ref": WORLDPOP_SOURCE_REF,
                    }
                ),
                encoding="utf-8",
            )

            summary = build_migori_worldpop_phase2_validation(
                csv_path=csv_path,
                phase1_summary_path=phase1_summary_path,
                expected_row_count=1,
            )

        self.assertFalse(summary["passed"])
        self.assertFalse(summary["phase2_gates"]["no_formula_like_cells"])
        self.assertEqual(summary["formula_like_cells"][0]["column"], "notes")

    def test_validation_flags_unresolved_ward_codes_before_import(self):
        Ward.objects.create(name="Alpha", county="Migori", ward_code="KE-WARD-1")
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "population.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        WORLDPOP_HEADER,
                        (
                            "KE-WARD-404,Missing,123,45.6,123.4,"
                            "ward_sum_from_worldpop_100m_grid_pixel_centers,100m,people_per_km2,"
                            f"spatially_aggregated_source,live,fresh,{WORLDPOP_SOURCE_REF},clean row"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            phase1_summary_path = Path(tmpdir) / "summary.json"
            phase1_summary_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "output_csv_sha256": self._sha256(csv_path),
                        "source_ref": WORLDPOP_SOURCE_REF,
                    }
                ),
                encoding="utf-8",
            )

            summary = build_migori_worldpop_phase2_validation(
                csv_path=csv_path,
                phase1_summary_path=phase1_summary_path,
                expected_row_count=1,
            )

        self.assertFalse(summary["passed"])
        self.assertFalse(summary["phase2_gates"]["all_rows_resolve_to_migori_wards"])
        self.assertEqual(summary["ward_resolution"]["unresolved_rows"][0]["reason"], "ward_not_found")

    def test_validation_flags_missing_density_even_when_adapter_accepts_population_total(self):
        Ward.objects.create(name="Alpha", county="Migori", ward_code="KE-WARD-1")
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "population.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        WORLDPOP_HEADER,
                        (
                            "KE-WARD-1,Alpha,123,,123.4,"
                            "ward_sum_from_worldpop_100m_grid_pixel_centers,100m,people_per_km2,"
                            f"spatially_aggregated_source,live,fresh,{WORLDPOP_SOURCE_REF},clean row"
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            phase1_summary_path = Path(tmpdir) / "summary.json"
            phase1_summary_path.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "output_csv_sha256": self._sha256(csv_path),
                        "source_ref": WORLDPOP_SOURCE_REF,
                    }
                ),
                encoding="utf-8",
            )

            summary = build_migori_worldpop_phase2_validation(
                csv_path=csv_path,
                phase1_summary_path=phase1_summary_path,
                expected_row_count=1,
            )

        self.assertFalse(summary["passed"])
        self.assertFalse(summary["phase2_gates"]["row_numeric_cells_present_and_valid"])
        self.assertEqual(
            summary["numeric_contract"]["missing_or_invalid_numeric_cells"][0]["column"],
            "population_density",
        )

    def _sha256(self, path: Path) -> str:
        import hashlib

        digest = hashlib.sha256()
        digest.update(path.read_bytes())
        return digest.hexdigest()
