import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.model_registry_governance import (
    ModelRegistryGovernanceError,
    resolve_registry_entry,
    review_model_artifact,
)


class Command(BaseCommand):
    help = "Reject a pending registered model artifact."

    def add_arguments(self, parser):
        parser.add_argument("--registry-ref", required=True)
        parser.add_argument("--actor", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--request-id", default="")

    def handle(self, *args, **options):
        try:
            entry = review_model_artifact(
                entry=resolve_registry_entry(options["registry_ref"]),
                actor=options["actor"],
                reason=options["reason"],
                approve=False,
                request_id=options["request_id"],
            )
        except (ModelRegistryGovernanceError, ValueError) as error:
            raise CommandError(getattr(error, "code", str(error))) from error
        self.stdout.write(json.dumps({"registry_entry_id": entry.id, "approval_state": entry.approval_state}, sort_keys=True))
