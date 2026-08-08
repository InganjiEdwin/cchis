import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.model_registry_governance import (
    ModelRegistryGovernanceError,
    activate_registered_model,
    resolve_registry_entry,
)


class Command(BaseCommand):
    help = "Activate an approved registered model artifact for the operational target."

    def add_arguments(self, parser):
        parser.add_argument("--registry-ref", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--request-id", default="")

    def handle(self, *args, **options):
        try:
            entry = activate_registered_model(
                entry=resolve_registry_entry(options["registry_ref"]),
                actor=options["actor"],
                reason=options["reason"],
                request_id=options["request_id"],
            )
        except (ModelRegistryGovernanceError, ValueError) as error:
            raise CommandError(getattr(error, "code", str(error))) from error
        self.stdout.write(
            json.dumps(
                {
                    "registry_entry_id": entry.id,
                    "registry_version": str(entry.registry_version),
                    "model_run_id": entry.model_run_id,
                    "approval_state": entry.approval_state,
                    "lifecycle_state": entry.lifecycle_state,
                    "active_from": entry.active_from,
                },
                default=str,
                sort_keys=True,
            )
        )
