from io import StringIO

from django.test import SimpleTestCase

from risk.migori_worldpop_population_csv import (
    WardPolygon,
    aggregate_xyz_stream,
    csv_rows_for_aggregates,
    geometry_area_km2,
    geometry_bbox,
)


class MigoriWorldPopPopulationCsvTestCase(SimpleTestCase):
    def test_aggregates_xyz_points_into_ward_polygons(self):
        alpha_geometry = self._square(0.0, 0.0, 1.0, 1.0)
        beta_geometry = self._square(1.0, 0.0, 2.0, 1.0)
        wards = [
            WardPolygon(
                ward_code="KE-WARD-1",
                ward_name="Alpha",
                sub_county="Test",
                geometry=alpha_geometry,
                bbox=geometry_bbox(alpha_geometry),
                area_km2=geometry_area_km2(alpha_geometry),
            ),
            WardPolygon(
                ward_code="KE-WARD-2",
                ward_name="Beta",
                sub_county="Test",
                geometry=beta_geometry,
                bbox=geometry_bbox(beta_geometry),
                area_km2=geometry_area_km2(beta_geometry),
            ),
        ]
        xyz = StringIO(
            "\n".join(
                [
                    "0.5 0.5 10",
                    "0.25 0.25 2.5",
                    "1.5 0.5 7",
                    "3.0 3.0 11",
                    "0.5 0.5 -99999",
                    "0.5 0.5 -3.4028234663852886e+38",
                ]
            )
        )

        aggregate = aggregate_xyz_stream(xyz, wards)

        self.assertEqual(aggregate["totals"]["KE-WARD-1"], 12.5)
        self.assertEqual(aggregate["totals"]["KE-WARD-2"], 7)
        self.assertEqual(aggregate["assigned_pixel_count"], 3)
        self.assertEqual(aggregate["source_positive_pixel_count"], 4)
        self.assertEqual(aggregate["assigned_population_value"], 19.5)
        self.assertEqual(aggregate["unassigned_positive_pixel_count"], 1)
        self.assertEqual(aggregate["unassigned_positive_population_value"], 11)
        self.assertEqual(aggregate["source_positive_population_value"], 30.5)

    def test_csv_rows_include_ingestion_contract_columns(self):
        geometry = self._square(0.0, 0.0, 1.0, 1.0)
        ward = WardPolygon(
            ward_code="KE-WARD-1",
            ward_name="Alpha",
            sub_county="Test",
            geometry=geometry,
            bbox=geometry_bbox(geometry),
            area_km2=100.0,
        )
        rows = csv_rows_for_aggregates(
            wards=[ward],
            aggregate={
                "totals": {"KE-WARD-1": 1234.56},
                "assigned_pixels": {"KE-WARD-1": 42},
            },
            source_ref="https://example.test/worldpop.tif",
            release_version="WorldPop test release",
            geojson_sha256="abc123",
        )

        self.assertEqual(rows[0]["ward_code"], "KE-WARD-1")
        self.assertEqual(rows[0]["population_total"], "1235")
        self.assertEqual(rows[0]["truth_class"], "spatially_aggregated_source")
        self.assertEqual(rows[0]["source_kind"], "live")
        self.assertEqual(rows[0]["freshness_state"], "fresh")
        self.assertEqual(rows[0]["unit"], "people_per_km2")

    def _square(self, minx: float, miny: float, maxx: float, maxy: float) -> dict:
        return {
            "type": "Polygon",
            "coordinates": [
                [
                    [minx, miny],
                    [maxx, miny],
                    [maxx, maxy],
                    [minx, maxy],
                    [minx, miny],
                ]
            ],
        }
