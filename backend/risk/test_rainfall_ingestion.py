import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from risk.ml.ingestion import fetch_open_meteo_daily_precipitation


class RainfallIngestionRegressionTestCase(SimpleTestCase):
    @patch("risk.ml.ingestion.urllib.request.urlopen")
    def test_open_meteo_timezone_config_does_not_shadow_django_timezone(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = json.dumps(
            {"daily": {"precipitation_sum": [12.5, 7.5, 0]}}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = response

        observation = fetch_open_meteo_daily_precipitation(
            ward_name="North Kamagambo",
            latitude=-0.9876,
            longitude=34.641,
        )

        self.assertEqual(observation.rainfall_mm, 20.0)
        self.assertEqual(observation.source, "open-meteo-forecast")
        self.assertIsNotNone(observation.source_timestamp)
        self.assertTrue(timezone.is_aware(observation.source_timestamp))
