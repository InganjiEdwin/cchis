from django.core.management.base import BaseCommand, CommandError

from risk.models import SurveillanceIngestionRun, SurveillanceSource
from risk.surveillance_ingestion import (
    inspect_surveillance_csv,
    parse_surveillance_date,
    parse_surveillance_source_timestamp,
    regenerate_surveillance_label_windows_for_run,
    replay_surveillance_ingestion_run,
    run_surveillance_csv_ingestion,
)


class Command(BaseCommand):
    help = "Inspect, record, and replay surveillance CSV ingestion runs with correction metadata."

    def add_arguments(self, parser):
        parser.add_argument("--file", dest="file_path", help="CSV file to inspect or record as a surveillance ingestion run.")
        parser.add_argument(
            "--inspect-only",
            action="store_true",
            help="Validate the surveillance CSV adapter contract without creating records.",
        )
        parser.add_argument("--source-name", default="", help="Reporting source name, for example DHIS2 export or county weekly report.")
        parser.add_argument(
            "--source-type",
            choices=[choice[0] for choice in SurveillanceSource.SOURCE_TYPE_CHOICES],
            default="",
        )
        parser.add_argument("--source-timestamp", default="", help="ISO timestamp or date for the source submission.")
        parser.add_argument("--reporting-period-start", default="", help="ISO date for the reporting period start.")
        parser.add_argument("--reporting-period-end", default="", help="ISO date for the reporting period end.")
        parser.add_argument("--source-ref", default="", help="External URL, file reference, batch id, or publication citation.")
        parser.add_argument(
            "--correction-mode",
            choices=[choice[0] for choice in SurveillanceIngestionRun.CORRECTION_MODE_CHOICES],
            default=SurveillanceIngestionRun.CORRECTION_ORIGINAL,
        )
        parser.add_argument("--correction-reason", default="", help="Required for amendment imports.")
        parser.add_argument("--operator-note", default="")
        parser.add_argument(
            "--execution-mode",
            choices=[choice[0] for choice in SurveillanceIngestionRun.EXECUTION_MODE_CHOICES],
            default=SurveillanceIngestionRun.EXECUTION_MANUAL,
        )
        parser.add_argument("--fallback-used", action="store_true")
        parser.add_argument("--replay-of", type=int, default=None, help="Replay a previous surveillance ingestion run.")
        parser.add_argument(
            "--regenerate-label-windows",
            action="store_true",
            help="Regenerate downstream surveillance label windows for the affected wards and reporting period.",
        )
        parser.add_argument(
            "--label-dataset-role",
            choices=["training", "evaluation"],
            default="evaluation",
            help="Dataset role to record when regenerating surveillance labels.",
        )
        parser.add_argument("--label-window-days", type=int, default=7)
        parser.add_argument("--label-step-days", type=int, default=7)
        parser.add_argument(
            "--include-seeded-labels",
            action="store_true",
            help="Include seeded demo records when regenerating labels. Operational regeneration excludes them by default.",
        )

    def handle(self, *args, **options):
        if options["replay_of"]:
            try:
                run = replay_surveillance_ingestion_run(
                    options["replay_of"],
                    file_path=options["file_path"] or None,
                    operator_note=options["operator_note"],
                )
            except SurveillanceIngestionRun.DoesNotExist as error:
                raise CommandError(f"Surveillance ingestion run {options['replay_of']} does not exist.") from error
            except ValueError as error:
                raise CommandError(str(error)) from error
            regeneration = None
            if options["regenerate_label_windows"]:
                regeneration = regenerate_surveillance_label_windows_for_run(
                    run,
                    dataset_role=options["label_dataset_role"],
                    window_days=options["label_window_days"],
                    step_days=options["label_step_days"],
                    include_seeded=options["include_seeded_labels"],
                )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Surveillance replay complete. run_id={run.id} status={run.status} "
                    f"loaded={run.records_loaded}/{run.records_seen} rejected={run.records_rejected}"
                )
            )
            if regeneration:
                self.stdout.write(f"Label regeneration: {regeneration}")
            return

        if not options["file_path"]:
            raise CommandError("--file is required unless --replay-of is supplied.")
        if options["inspect_only"]:
            if not options["source_type"]:
                raise CommandError("--source-type is required for --inspect-only.")
            inspection = inspect_surveillance_csv(
                options["file_path"],
                source_type=options["source_type"],
                source_name=options["source_name"],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Surveillance source inspection complete. "
                    f"adapter={inspection['adapter_key']} rows={inspection['records_seen']} "
                    f"accepted={inspection['records_loaded']} rejected={inspection['records_rejected']} "
                    f"truth_levels={inspection['truth_level_counts']} "
                    f"unknown_columns={inspection['unknown_columns']}"
                )
            )
            if inspection["rejected_rows"]:
                self.stdout.write(f"Rejected row samples: {inspection['rejected_rows']}")
            return

        if not options["source_name"]:
            raise CommandError("--source-name is required for a new surveillance ingestion run.")
        if not options["source_type"]:
            raise CommandError("--source-type is required for a new surveillance ingestion run.")
        if (
            options["correction_mode"] == SurveillanceIngestionRun.CORRECTION_AMENDMENT
            and not options["correction_reason"].strip()
        ):
            raise CommandError("--correction-reason is required when --correction-mode=amendment.")

        try:
            source_timestamp = parse_surveillance_source_timestamp(options["source_timestamp"])
            reporting_period_start = parse_surveillance_date(options["reporting_period_start"])
            reporting_period_end = parse_surveillance_date(options["reporting_period_end"])
        except ValueError as error:
            raise CommandError(f"Invalid surveillance date or timestamp: {error}") from error

        try:
            run = run_surveillance_csv_ingestion(
                file_path=options["file_path"],
                source_name=options["source_name"],
                source_type=options["source_type"],
                source_timestamp=source_timestamp,
                reporting_period_start=reporting_period_start,
                reporting_period_end=reporting_period_end,
                source_ref=options["source_ref"],
                correction_mode=options["correction_mode"],
                correction_reason=options["correction_reason"],
                operator_note=options["operator_note"],
                execution_mode=options["execution_mode"],
                fallback_used=options["fallback_used"],
                regenerate_label_windows=options["regenerate_label_windows"],
                label_dataset_role=options["label_dataset_role"],
                label_window_days=options["label_window_days"],
                label_step_days=options["label_step_days"],
                include_seeded_labels=options["include_seeded_labels"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        style = self.style.SUCCESS if run.status != SurveillanceIngestionRun.STATUS_FAILED else self.style.ERROR
        self.stdout.write(
            style(
                f"Surveillance ingestion complete. run_id={run.id} status={run.status} "
                f"source_type={run.source_type} period={run.reporting_period_start}:{run.reporting_period_end} "
                f"loaded={run.records_loaded}/{run.records_seen} rejected={run.records_rejected}"
            )
        )
        if options["regenerate_label_windows"]:
            self.stdout.write(f"Label regeneration: {run.results.get('downstream_label_regeneration')}")
