from django.core.management.base import BaseCommand, CommandError

from risk.models import FeatureDataset, ModelRun
from risk.surveillance_labels import evaluate_model_run_against_surveillance_lead_time_labels


class Command(BaseCommand):
    help = "Evaluate a ModelRun against Phase 3 surveillance 7 to 14 day label windows."

    def add_arguments(self, parser):
        parser.add_argument("model_run_id", type=int)
        parser.add_argument(
            "--label-dataset-ref",
            default="",
            help="Specific surveillance lead-time label dataset_ref. Defaults to the latest evaluation snapshot.",
        )
        parser.add_argument(
            "--no-persist",
            action="store_true",
            help="Compute the summary without writing it back to the ModelRun.",
        )

    def handle(self, *args, **options):
        try:
            model_run = ModelRun.objects.get(id=options["model_run_id"])
        except ModelRun.DoesNotExist as error:
            raise CommandError(f"ModelRun id={options['model_run_id']} does not exist.") from error

        label_dataset = None
        if options["label_dataset_ref"]:
            try:
                label_dataset = FeatureDataset.objects.get(dataset_ref=options["label_dataset_ref"])
            except FeatureDataset.DoesNotExist as error:
                raise CommandError(f"FeatureDataset '{options['label_dataset_ref']}' does not exist.") from error

        summary = evaluate_model_run_against_surveillance_lead_time_labels(
            model_run,
            label_dataset=label_dataset,
            persist=not options["no_persist"],
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Surveillance 7-to-14 day evaluation complete. model_run_id={model_run.id} "
                f"status={summary.get('status')} label_dataset_ref={summary.get('label_dataset_ref')} "
                f"matched={summary.get('matched_prediction_count', 0)} "
                f"unmatched={summary.get('unmatched_prediction_count', 0)}"
            )
        )
