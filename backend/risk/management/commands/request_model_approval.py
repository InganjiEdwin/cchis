import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.model_registry_governance import (
    ModelRegistryGovernanceError,
    request_model_approval,
    resolve_registry_entry,
)


class Command(BaseCommand):
    help = "Request human review for a registered model artifact."

    def add_arguments(self, parser):
        parser.add_argument("--registry-ref", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--request-id", default="")

    def handle(self, *args, **options):
        try:
            entry = request_model_approval(
                entry=resolve_registry_entry(options["registry_ref"]),
                actor=options["actor"],
                reason=options["reason"],
                request_id=options["request_id"],
            )
        except (ModelRegistryGovernanceError, ValueError) as error:
            raise CommandError(getattr(error, "code", str(error))) from error
        self.stdout.write(json.dumps({"registry_entry_id": entry.id, "approval_state": entry.approval_state}, sort_keys=True))
