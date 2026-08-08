import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.model_registry_governance import (
    ModelRegistryGovernanceError,
    designate_model_challenger,
    resolve_registry_entry,
)


class Command(BaseCommand):
    help = "Designate a registered candidate as a non-operational challenger."

    def add_arguments(self, parser):
        parser.add_argument("--registry-ref", required=True)
        parser.add_argument("--champion-registry-ref", default="")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--request-id", default="")

    def handle(self, *args, **options):
        try:
            champion = (
                resolve_registry_entry(options["champion_registry_ref"])
                if options["champion_registry_ref"]
                else None
            )
            entry = designate_model_challenger(
                entry=resolve_registry_entry(options["registry_ref"]),
                champion=champion,
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
                    "lifecycle_state": entry.lifecycle_state,
                    "challenger_of_registry_entry_id": entry.challenger_of_id,
                },
                sort_keys=True,
            )
        )
