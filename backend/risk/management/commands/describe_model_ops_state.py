import json

from django.core.management.base import BaseCommand

from risk.ml.operations_inventory import build_model_ops_state_inventory


class Command(BaseCommand):
    help = "Describe the current ward-risk model operations state and Phase 0 gaps."

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(build_model_ops_state_inventory(), indent=2, sort_keys=True, default=str))
