import json

from django.core.management.base import BaseCommand

from risk.facility_forecasting import build_facility_forecast_promotion_summary


class Command(BaseCommand):
    help = "Evaluate the current facility burden forecasting baseline and emit a conservative promotion summary."

    def handle(self, *args, **options):
        summary = build_facility_forecast_promotion_summary()
        self.stdout.write(json.dumps(summary, default=str, indent=2))
