import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.registry import execute_model_rollback
from risk.models import ModelRegistryEntry


class Command(BaseCommand):
    help = "Execute a Phase 5 model rollback with atomic registry updates and current-risk materialization."

    def add_arguments(self, parser):
        parser.add_argument("--rolled-back-from-registry-entry-id", type=int, default=None)
        parser.add_argument("--rollback-target-registry-entry-id", type=int, default=None)
        parser.add_argument("--reason", type=str, required=True)
        parser.add_argument("--rolled-back-by", type=str, required=True)
        parser.add_argument("--authorized-role", type=str, default="model_operations")
        parser.add_argument(
            "--review-only-current-risk",
            action="store_true",
            help="Record current-risk review metadata without recomputing ward materialized risk fields.",
        )

    def _registry_entry(self, registry_entry_id: int | None, *, option_name: str):
        if registry_entry_id is None:
            return None
        try:
            return ModelRegistryEntry.objects.get(id=registry_entry_id)
        except ModelRegistryEntry.DoesNotExist as error:
            raise CommandError(f"{option_name}={registry_entry_id} does not exist.") from error

    def handle(self, *args, **options):
        try:
            event = execute_model_rollback(
                rolled_back_from=self._registry_entry(
                    options["rolled_back_from_registry_entry_id"],
                    option_name="rolled-back-from-registry-entry-id",
                ),
                rollback_target=self._registry_entry(
                    options["rollback_target_registry_entry_id"],
                    option_name="rollback-target-registry-entry-id",
                ),
                reason=options["reason"],
                rolled_back_by=options["rolled_back_by"],
                authorized_role=options["authorized_role"],
                materialize_current_risk=not options["review_only_current_risk"],
                metadata={"source": "perform_model_rollback_command"},
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        materialization = (event.metadata or {}).get("current_risk_materialization") or {}
        payload = {
            "rollback_event_id": event.id,
            "rollback_event_public_id": str(event.public_id),
            "rolled_back_from_registry_entry_id": event.rolled_back_from_id,
            "rollback_target_registry_entry_id": event.rollback_target_id,
            "rolled_back_by": event.rolled_back_by,
            "authorized_role": (event.metadata or {}).get("authorized_role"),
            "reason": event.reason,
            "new_active_model_run_id": ((event.metadata or {}).get("new_active") or {}).get("model_run_id"),
            "new_active_model_version": ((event.metadata or {}).get("new_active") or {}).get("model_version"),
            "current_risk_materialization": materialization,
            "alerts_respect_active_registry_state": (event.metadata or {}).get(
                "alerts_respect_active_registry_state"
            ),
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
