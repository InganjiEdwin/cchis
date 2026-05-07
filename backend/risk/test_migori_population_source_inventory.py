import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from risk.migori_population_source_inventory import (
    EXPECTED_WORLDPOP_DOI,
    EXPECTED_WORLDPOP_FILE_URL,
    EXPECTED_WORLDPOP_RECORD_ID,
    EXPECTED_WORLDPOP_SOURCE_DATE,
    build_migori_population_phase0_inventory,
    normalize_worldpop_record,
    select_worldpop_population_record,
)
from risk.models import Ward


class WorldPopPopulationMetadataSelectionTestCase(SimpleTestCase):
    def test_selects_requested_population_year(self):
        payload = {
            "data": [
                {"id": "73999", "popyear": "2025", "files": ["old.tif"]},
                {
                    "id": EXPECTED_WORLDPOP_RECORD_ID,
                    "title": "Kenya - Spatial Distribution of Population",
                    "popyear": "2026",
                    "date": EXPECTED_WORLDPOP_SOURCE_DATE,
                    "doi": EXPECTED_WORLDPOP_DOI,
                    "data_format": "Geotiff",
                    "category": "Individual countries 2015-2030 ( 100m resolution ) R2025A v1",
                    "source": "WorldPop, University of Southampton, UK",
                    "citation": f"WorldPop citation DOI:{EXPECTED_WORLDPOP_DOI}",
                    "files": [EXPECTED_WORLDPOP_FILE_URL],
                    "license": "https://hub.worldpop.org/data/licence.txt",
                },
            ]
        }

        record = select_worldpop_population_record(payload, popyear="2026")
        normalized = normalize_worldpop_record(record)

        self.assertEqual(normalized["id"], EXPECTED_WORLDPOP_RECORD_ID)
        self.assertEqual(normalized["popyear"], "2026")
        self.assertEqual(normalized["files"], [EXPECTED_WORLDPOP_FILE_URL])


class MigoriPopulationPhase0InventoryTestCase(TestCase):
    def test_inventory_records_local_ward_and_geojson_gates(self):
        Ward.objects.create(name="Alpha", county="Migori", sub_county="Test", ward_code="KE-WARD-1")
        Ward.objects.create(name="Beta", county="Migori", sub_county="Test", ward_code="KE-WARD-2")
        payload = {
            "type": "FeatureCollection",
            "metadata": {"county": "Migori"},
            "features": [
                self._feature("Alpha", "KE-WARD-1", 34.0),
                self._feature("Beta", "KE-WARD-2", 34.2),
            ],
        }
        worldpop_record = {
            "id": EXPECTED_WORLDPOP_RECORD_ID,
            "popyear": "2026",
            "date": EXPECTED_WORLDPOP_SOURCE_DATE,
            "doi": EXPECTED_WORLDPOP_DOI,
            "data_format": "Geotiff",
            "category": "Individual countries 2015-2030 ( 100m resolution ) R2025A v1",
            "source": "WorldPop, University of Southampton, UK",
            "citation": f"WorldPop citation DOI:{EXPECTED_WORLDPOP_DOI}",
            "files": [EXPECTED_WORLDPOP_FILE_URL],
            "license": "https://hub.worldpop.org/data/licence.txt",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "migori_wards.geojson"
            path.write_text(json.dumps(payload), encoding="utf-8")

            inventory = build_migori_population_phase0_inventory(
                geojson_path=path,
                expected_ward_count=2,
                worldpop_record=worldpop_record,
            )

        self.assertTrue(all(inventory["phase0_gates"].values()))
        self.assertTrue(inventory["passed"])
        self.assertEqual(inventory["local_ward_register"]["active_ward_count"], 2)
        self.assertEqual(inventory["local_geojson"]["summary"]["filtered_feature_count"], 2)
        self.assertEqual(inventory["worldpop"]["record"]["id"], EXPECTED_WORLDPOP_RECORD_ID)
        self.assertEqual(inventory["worldpop"]["expected_release"]["file_url"], EXPECTED_WORLDPOP_FILE_URL)

    def test_inventory_fails_expected_release_gates_when_worldpop_metadata_drifts(self):
        Ward.objects.create(name="Alpha", county="Migori", sub_county="Test", ward_code="KE-WARD-1")
        payload = {
            "type": "FeatureCollection",
            "metadata": {"county": "Migori"},
            "features": [self._feature("Alpha", "KE-WARD-1", 34.0)],
        }
        drifted_worldpop_record = {
            "id": "99999",
            "popyear": "2026",
            "date": EXPECTED_WORLDPOP_SOURCE_DATE,
            "doi": "10.0000/DRIFTED",
            "data_format": "CSV",
            "category": "Coarse tabular output",
            "source": "Unknown",
            "citation": "No planned DOI",
            "files": ["https://example.test/not-the-planned-worldpop-file.tif"],
            "license": "https://hub.worldpop.org/data/licence.txt",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "migori_wards.geojson"
            path.write_text(json.dumps(payload), encoding="utf-8")

            inventory = build_migori_population_phase0_inventory(
                geojson_path=path,
                expected_ward_count=1,
                worldpop_record=drifted_worldpop_record,
            )

        self.assertFalse(inventory["phase0_gates"]["worldpop_record_id_matches_expected"])
        self.assertFalse(inventory["phase0_gates"]["worldpop_doi_matches_expected"])
        self.assertFalse(inventory["phase0_gates"]["worldpop_data_format_is_geotiff"])
        self.assertFalse(inventory["phase0_gates"]["worldpop_category_mentions_100m"])
        self.assertFalse(inventory["phase0_gates"]["worldpop_file_url_matches_expected"])
        self.assertFalse(inventory["passed"])

    def _feature(self, name: str, ward_code: str, lon: float) -> dict:
        return {
            "type": "Feature",
            "properties": {
                "name": name,
                "ward_code": ward_code,
                "county": "Migori",
                "sub_county": "Test",
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [lon, -1.0],
                        [lon + 0.1, -1.0],
                        [lon + 0.08, -0.92],
                        [lon, -0.9],
                        [lon, -1.0],
                    ]
                ],
            },
        }
