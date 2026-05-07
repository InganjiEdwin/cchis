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
        parser.add_argument(
            "--include-seeded-training-labels",
            action="store_true",
            help=(
                "Use seeded surveillance label datasets for non-production simulation scoring. "
                "Live promotion remains blocked by seeded-truth policy."
            ),
        )
        parser.add_argument("--async", action="store_true", dest="run_async")

    def _validate_version_discipline(self, *, algorithm: str, model_version: str, benchmark_algorithm: str, benchmark_version: str, dual_model: bool):
        if algorithm == "logistic_regression" and not model_version.startswith("lr-"):
            self.stderr.write(self.style.WARNING("Expected logistic regression model versions to start with 'lr-'"))
        if algorithm == "random_forest" and not model_version.startswith("rf-"):
            self.stderr.write(self.style.WARNING("Expected Random Forest model versions to start with 'rf-'"))
        if dual_model and benchmark_algorithm == "random_forest" and not benchmark_version.startswith("rf-"):
            self.stderr.write(self.style.WARNING("Expected Random Forest benchmark versions to start with 'rf-'"))

    def _default_run_purpose(self, *, algorithm: str, dual_model: bool) -> str:
        if dual_model:
            return "live_scoring"
        if algorithm == "random_forest":
            return "benchmark_scoring"
        return "live_scoring"

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
        include_seeded_training_labels = options["include_seeded_training_labels"]
        run_async = options["run_async"]
        self._validate_version_discipline(
            algorithm=algorithm,
            model_version=model_version,
            benchmark_algorithm=benchmark_algorithm,
            benchmark_version=benchmark_model_version,
            dual_model=dual_model,
        )
        run_purpose = self._default_run_purpose(algorithm=algorithm, dual_model=dual_model)

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
                run_purpose=run_purpose,
                include_seeded_training_labels=include_seeded_training_labels,
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
            run_purpose=run_purpose,
            include_seeded_training_labels=include_seeded_training_labels,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Risk model run complete. Created {len(created_scores)} risk scores "
                f"with model_version={model_version} algorithm={algorithm}."
            )
        )
