import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.model_registry_governance import ModelRegistryGovernanceError, resolve_registry_entry
from risk.ml.registry import execute_model_rollback
from risk.models import ModelRegistryEntry


class Command(BaseCommand):
    help = "Rollback the active model to an explicitly named compatible registry target."

    def add_arguments(self, parser):
        parser.add_argument("--rollback-target", required=True)
        parser.add_argument("--deployment-target", default="")
        parser.add_argument("--rolled-back-from", default="")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--authorized-role", default="model_operations")
        parser.add_argument("--review-only-current-risk", action="store_true")
        parser.add_argument("--request-id", default="")

    def handle(self, *args, **options):
        try:
            rollback_target = resolve_registry_entry(options["rollback_target"])
            if options["deployment_target"] and rollback_target.deployment_target != options["deployment_target"]:
                raise ModelRegistryGovernanceError("rollback_target_deployment_mismatch")
            rolled_back_from = (
                resolve_registry_entry(options["rolled_back_from"])
                if options["rolled_back_from"]
                else None
            )
            event = execute_model_rollback(
                rolled_back_from=rolled_back_from,
                rollback_target=rollback_target,
                reason=options["reason"],
                rolled_back_by=options["actor"],
                authorized_role=options["authorized_role"],
                materialize_current_risk=not options["review_only_current_risk"],
                metadata={
                    "source": "rollback_registered_model_command",
                    "request_id": options["request_id"],
                },
            )
        except (ModelRegistryGovernanceError, ValueError, ModelRegistryEntry.DoesNotExist) as error:
            raise CommandError(getattr(error, "code", str(error))) from error
        self.stdout.write(
            json.dumps(
                {
                    "rollback_event_id": event.id,
                    "rolled_back_from_registry_entry_id": event.rolled_back_from_id,
                    "rollback_target_registry_entry_id": event.rollback_target_id,
                    "reason": event.reason,
                },
                sort_keys=True,
            )
        )
