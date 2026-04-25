from django.core.management.base import BaseCommand
from django.utils import timezone

from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.tasks import run_risk_model_task


class Command(BaseCommand):
    help = "Run ward risk model scoring with explicit algorithm and optional dual-model benchmark mode"

    def add_arguments(self, parser):
        parser.add_argument("--month", type=int, default=timezone.now().month)
        parser.add_argument("--model-version", type=str, default="lr-v1")
        parser.add_argument(
            "--algorithm",
            type=str,
            default="logistic_regression",
            choices=["logistic_regression", "random_forest"],
        )
        parser.add_argument("--trigger-alerts", action="store_true")
        parser.add_argument("--send-sms", action="store_true")
        parser.add_argument("--dual-model", action="store_true")
        parser.add_argument(
            "--benchmark-algorithm",
            type=str,
            default="random_forest",
            choices=["logistic_regression", "random_forest"],
        )
        parser.add_argument("--benchmark-version", type=str, default="rf-v1")
        parser.add_argument(
            "--alert-algorithm",
            type=str,
            choices=["logistic_regression", "random_forest"],
            default=None,
        )
        parser.add_argument("--async", action="store_true", dest="run_async")

    def handle(self, *args, **options):
        month = options["month"]
        model_version = options["model_version"]
        algorithm = options["algorithm"]
        trigger_alerts = options["trigger_alerts"]
        send_sms = options["send_sms"]
        dual_model = options["dual_model"]
        benchmark_algorithm = options["benchmark_algorithm"]
        benchmark_model_version = options["benchmark_version"]
        alert_algorithm = options["alert_algorithm"]
        run_async = options["run_async"]

        if run_async:
            task = run_risk_model_task.delay(
                month=month,
                model_version=model_version,
                algorithm=algorithm,
                trigger_alerts=trigger_alerts,
                send_sms=send_sms,
                dual_model=dual_model,
                benchmark_algorithm=benchmark_algorithm,
                benchmark_model_version=benchmark_model_version,
                alert_algorithm=alert_algorithm,
                execution_context="manual_task",
                run_purpose="live_scoring",
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
            algorithm=algorithm,
            trigger_alerts=trigger_alerts,
            send_sms=send_sms,
            dual_model=dual_model,
            benchmark_algorithm=benchmark_algorithm,
            benchmark_model_version=benchmark_model_version,
            alert_algorithm=alert_algorithm,
            execution_context="manual_command",
            run_purpose="live_scoring",
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Risk model run complete. Created {len(created_scores)} risk scores "
                f"with model_version={model_version} algorithm={algorithm}."
            )
        )
