import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.retraining_policy import (
    DEFAULT_NEW_LABEL_VOLUME_THRESHOLD,
    DEFAULT_REPEATED_FALSE_ALERT_THRESHOLD,
    DEFAULT_REPEATED_MISS_THRESHOLD,
    DEFAULT_STALE_MODEL_MAX_DAYS,
    evaluate_retraining_policy,
)
from risk.models import ModelRegistryEntry


class Command(BaseCommand):
    help = "Evaluate Phase 3 stale-model and retraining-review triggers for a ward-risk registry entry."

    def add_arguments(self, parser):
        parser.add_argument("--registry-entry-id", type=int, default=None)
        parser.add_argument("--stale-model-max-days", type=int, default=DEFAULT_STALE_MODEL_MAX_DAYS)
        parser.add_argument("--new-label-volume-threshold", type=int, default=DEFAULT_NEW_LABEL_VOLUME_THRESHOLD)
        parser.add_argument(
            "--repeated-false-alert-threshold",
            type=int,
            default=DEFAULT_REPEATED_FALSE_ALERT_THRESHOLD,
        )
        parser.add_argument("--repeated-miss-threshold", type=int, default=DEFAULT_REPEATED_MISS_THRESHOLD)

    def _registry_entry(self, registry_entry_id: int | None):
        if registry_entry_id is None:
            return None
        try:
            return ModelRegistryEntry.objects.get(id=registry_entry_id)
        except ModelRegistryEntry.DoesNotExist as error:
            raise CommandError(f"ModelRegistryEntry id={registry_entry_id} does not exist.") from error

    def handle(self, *args, **options):
        try:
            recommendation = evaluate_retraining_policy(
                registry_entry=self._registry_entry(options["registry_entry_id"]),
                stale_model_max_days=options["stale_model_max_days"],
                new_label_volume_threshold=options["new_label_volume_threshold"],
                repeated_false_alert_threshold=options["repeated_false_alert_threshold"],
                repeated_miss_threshold=options["repeated_miss_threshold"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        payload = {
            "recommendation_id": recommendation.id,
            "recommendation_public_id": str(recommendation.public_id),
            "registry_entry_id": recommendation.registry_entry_id,
            "model_run_id": recommendation.model_run_id,
            "recommendation_state": recommendation.recommendation_state,
            "recommended_action": recommendation.recommended_action,
            "reason_codes": recommendation.reason_codes,
            "new_label_count": recommendation.new_label_count,
            "false_alert_count": recommendation.false_alert_count,
            "miss_count": recommendation.miss_count,
            "automatic_live_promotion_allowed": recommendation.metadata.get("automatic_live_promotion_allowed"),
            "phase_4_promotion_gates_required": recommendation.metadata.get("phase_4_promotion_gates_required"),
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
