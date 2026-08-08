import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.model_registry_governance import (
    ModelRegistryGovernanceError,
    register_model_artifact,
)
from risk.models import ModelRun


class Command(BaseCommand):
    help = "Register a model artifact as an unapproved candidate with persisted integrity evidence."

    def add_arguments(self, parser):
        parser.add_argument("--model-run-id", type=int, required=True)
        parser.add_argument("--artifact-path", type=str, required=True)
        parser.add_argument("--actor", type=str, required=True)
        parser.add_argument("--reason", type=str, required=True)
        parser.add_argument("--deployment-target", type=str, default="live_baseline")
        parser.add_argument("--artifact-format", type=str, default="")
        parser.add_argument("--request-id", type=str, default="")

    def handle(self, *args, **options):
        try:
            model_run = ModelRun.objects.get(id=options["model_run_id"])
        except ModelRun.DoesNotExist as error:
            raise CommandError("model_run_not_found") from error
        try:
            entry = register_model_artifact(
                model_run=model_run,
                artifact_path=options["artifact_path"],
                actor=options["actor"],
                reason=options["reason"],
                deployment_target=options["deployment_target"],
                artifact_format=options["artifact_format"],
                request_id=options["request_id"],
            )
        except (ModelRegistryGovernanceError, ValueError) as error:
            raise CommandError(getattr(error, "code", str(error))) from error
        self.stdout.write(
            json.dumps(
                {
                    "registry_entry_id": entry.id,
                    "registry_entry_public_id": str(entry.public_id),
                    "registry_version": str(entry.registry_version),
                    "model_run_id": entry.model_run_id,
                    "approval_state": entry.approval_state,
                    "lifecycle_state": entry.lifecycle_state,
                    "deployment_target": entry.deployment_target,
                    "artifact_format": entry.artifact_format,
                    "artifact_size_bytes": entry.artifact_size_bytes,
                    "artifact_sha256": entry.artifact_sha256,
                },
                indent=2,
                sort_keys=True,
            )
        )
