import json

from django.core.management.base import BaseCommand

from risk.ml.readiness import build_boosting_readiness_summary


class Command(BaseCommand):
    help = "Describe XGBoost and LightGBM readiness requirements without enabling them as runnable live models."

    def handle(self, *args, **options):
        payload = build_boosting_readiness_summary()
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
