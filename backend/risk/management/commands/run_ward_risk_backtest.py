import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from risk.lead_time_features import LEAD_TIME_FEATURE_SCHEMA_VERSION
from risk.ml.backtesting import build_temporal_backtest_report, persist_temporal_backtest_report
from risk.models import FeatureDataset, ModelRun
from risk.surveillance_labels import latest_surveillance_lead_time_label_dataset


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise CommandError(f"Invalid date '{value}'. Expected YYYY-MM-DD.") from error


class Command(BaseCommand):
    help = "Run Phase 4 temporal ward-risk backtesting and optionally persist promotion evidence on a ModelRun."

    def add_arguments(self, parser):
        parser.add_argument("--feature-dataset-ref", default="")
        parser.add_argument("--label-dataset-ref", default="")
        parser.add_argument("--model-run-id", type=int, default=None)
        parser.add_argument("--train-end-date", default="")
        parser.add_argument("--validation-start-date", default="")
        parser.add_argument("--rainfall-threshold-mm", type=float, default=50.0)
        parser.add_argument(
            "--promote",
            action="store_true",
            help="Promote the supplied model run only if Phase 4 truth/leakage gates pass.",
        )

    def _feature_dataset(self, dataset_ref: str) -> FeatureDataset:
        if dataset_ref:
            try:
                return FeatureDataset.objects.get(dataset_ref=dataset_ref)
            except FeatureDataset.DoesNotExist as error:
                raise CommandError(f"FeatureDataset '{dataset_ref}' does not exist.") from error
        dataset = (
            FeatureDataset.objects.filter(schema_version=LEAD_TIME_FEATURE_SCHEMA_VERSION)
            .order_by("-created_at", "-id")
            .first()
        )
        if dataset is None:
            raise CommandError("No lead-time feature dataset is available. Supply --feature-dataset-ref.")
        return dataset

    def _label_dataset(self, dataset_ref: str) -> FeatureDataset:
        if dataset_ref:
            try:
                return FeatureDataset.objects.get(dataset_ref=dataset_ref)
            except FeatureDataset.DoesNotExist as error:
                raise CommandError(f"FeatureDataset '{dataset_ref}' does not exist.") from error
        dataset = latest_surveillance_lead_time_label_dataset(dataset_role="evaluation")
        if dataset is None:
            raise CommandError("No surveillance lead-time label dataset is available. Supply --label-dataset-ref.")
        return dataset

    def handle(self, *args, **options):
        feature_dataset = self._feature_dataset(options["feature_dataset_ref"])
        label_dataset = self._label_dataset(options["label_dataset_ref"])
        train_end_date = _parse_date(options["train_end_date"]) if options["train_end_date"] else None
        validation_start_date = (
            _parse_date(options["validation_start_date"]) if options["validation_start_date"] else None
        )
        report = build_temporal_backtest_report(
            feature_dataset=feature_dataset,
            label_dataset=label_dataset,
            train_end_date=train_end_date,
            validation_start_date=validation_start_date,
            rainfall_threshold_mm=options["rainfall_threshold_mm"],
        )

        if options["model_run_id"] is not None:
            try:
                model_run = ModelRun.objects.get(id=options["model_run_id"])
            except ModelRun.DoesNotExist as error:
                raise CommandError(f"ModelRun id={options['model_run_id']} does not exist.") from error
            try:
                persist_temporal_backtest_report(
                    model_run=model_run,
                    report=report,
                    promote=options["promote"],
                )
            except ValueError as error:
                raise CommandError(str(error)) from error

        self.stdout.write(json.dumps(report, indent=2, sort_keys=True, default=str))
