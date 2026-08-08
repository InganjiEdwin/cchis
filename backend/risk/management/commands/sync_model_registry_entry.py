import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from risk.ml.registry import (
    ensure_registry_entry_for_promoted_run,
    latest_promoted_model_run_from_phase_4_metadata,
)
from risk.models import ModelRun


class Command(BaseCommand):
    help = "Deprecated compatibility guard; implicit model registry activation is disabled."

    def add_arguments(self, parser):
        parser.add_argument("--model-run-id", type=int, default=None)
        parser.add_argument("--owner", type=str, default="")
        parser.add_argument("--promoted-by", type=str, default="manual_model_ops_sync")
        parser.add_argument("--review-due-date", type=str, default="")

    def _review_due_date(self, value: str):
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise CommandError("--review-due-date must use YYYY-MM-DD format.") from error

    def _model_run(self, model_run_id: int | None) -> ModelRun:
        if model_run_id is None:
            model_run = latest_promoted_model_run_from_phase_4_metadata()
            if model_run is None:
                raise CommandError("No Phase 4-promoted ModelRun exists to sync.")
            return model_run
        try:
            return ModelRun.objects.get(id=model_run_id)
        except ModelRun.DoesNotExist as error:
            raise CommandError(f"ModelRun id={model_run_id} does not exist.") from error

    def handle(self, *args, **options):
        model_run = self._model_run(options["model_run_id"])
        try:
            entry = ensure_registry_entry_for_promoted_run(
                model_run=model_run,
                owner=options["owner"],
                promoted_by=options["promoted_by"],
                source="manual_model_ops_sync",
                review_due_date=self._review_due_date(options["review_due_date"]),
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        payload = {
            "registry_entry_id": entry.id,
            "model_run_id": entry.model_run_id,
            "algorithm": entry.algorithm,
            "model_version": entry.model_version,
            "promotion_state": entry.promotion_state,
            "active_from": entry.active_from,
            "rollback_target_model_run_id": entry.rollback_target.model_run_id if entry.rollback_target_id else None,
            "review_due_date": entry.review_due_date,
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
