import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.model_registry_governance import (
    ModelRegistryGovernanceError,
    resolve_registry_entry,
    retire_registered_model,
)


class Command(BaseCommand):
    help = "Retire an active registered model through the governance event path."

    def add_arguments(self, parser):
        parser.add_argument("--registry-ref", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--request-id", default="")

    def handle(self, *args, **options):
        try:
            entry = retire_registered_model(
                entry=resolve_registry_entry(options["registry_ref"]),
                actor=options["actor"],
                reason=options["reason"],
                request_id=options["request_id"],
            )
        except (ModelRegistryGovernanceError, ValueError) as error:
            raise CommandError(getattr(error, "code", str(error))) from error
        self.stdout.write(json.dumps({"registry_entry_id": entry.id, "lifecycle_state": entry.lifecycle_state}, sort_keys=True))
