from django.core.management.base import BaseCommand
from django.utils import timezone

from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.tasks import run_risk_model_task


class Command(BaseCommand):
    help = "Run baseline logistic regression model and write ward risk scores"

    def add_arguments(self, parser):
        parser.add_argument("--month", type=int, default=timezone.now().month)
        parser.add_argument("--model-version", type=str, default="lr-v1")
        parser.add_argument("--trigger-alerts", action="store_true")
        parser.add_argument("--send-sms", action="store_true")
        parser.add_argument("--async", action="store_true", dest="run_async")

    def handle(self, *args, **options):
        month = options["month"]
        model_version = options["model_version"]
        trigger_alerts = options["trigger_alerts"]
        send_sms = options["send_sms"]
        run_async = options["run_async"]

        if run_async:
            task = run_risk_model_task.delay(
                month=month,
                model_version=model_version,
                trigger_alerts=trigger_alerts,
                send_sms=send_sms,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Queued risk model task with id={task.id} model_version={model_version}"
                )
            )
            return

        created_scores = run_mock_prediction_pipeline(
            month=month,
            model_version=model_version,
            trigger_alerts=trigger_alerts,
            send_sms=send_sms,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Risk model run complete. Created {len(created_scores)} risk scores "
                f"with model_version={model_version}."
            )
        )