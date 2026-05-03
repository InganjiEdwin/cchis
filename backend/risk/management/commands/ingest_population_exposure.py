from django.core.management.base import BaseCommand, CommandError

from risk.models import PopulationExposureIngestionRun, PopulationExposureSource
from risk.population_exposure_ingestion import (
    inspect_population_exposure_csv,
    parse_source_timestamp,
    replay_population_exposure_ingestion_run,
    run_population_exposure_csv_ingestion,
)


class Command(BaseCommand):
    help = "Record and normalize a population/exposure CSV ingestion run with release and correction metadata."

    def add_arguments(self, parser):
        parser.add_argument("--file", dest="file_path", help="CSV file to inspect and record as an ingestion run.")
        parser.add_argument(
            "--inspect-only",
            action="store_true",
            help="Validate the CSV adapter contract and print row/rejection counts without creating records.",
        )
        parser.add_argument("--source-name", default="", help="Source name, for example KNBS or WorldPop.")
        parser.add_argument(
            "--source-type",
            choices=[choice[0] for choice in PopulationExposureSource.SOURCE_TYPE_CHOICES],
            default="",
        )
        parser.add_argument("--source-timestamp", default="", help="ISO timestamp or date for the source release.")
        parser.add_argument("--release-version", default="", help="Source release version or publication label.")
        parser.add_argument("--source-ref", default="", help="External URL, file reference, or publication citation.")
        parser.add_argument(
            "--correction-mode",
            choices=[choice[0] for choice in PopulationExposureIngestionRun.CORRECTION_MODE_CHOICES],
            default=PopulationExposureIngestionRun.CORRECTION_ORIGINAL,
        )
        parser.add_argument("--replacement-reason", default="")
        parser.add_argument("--operator-note", default="")
        parser.add_argument(
            "--execution-mode",
            choices=[choice[0] for choice in PopulationExposureIngestionRun.EXECUTION_MODE_CHOICES],
            default=PopulationExposureIngestionRun.EXECUTION_MANUAL,
        )
        parser.add_argument("--fallback-used", action="store_true")
        parser.add_argument("--replay-of", type=int, default=None, help="Replay a previous population/exposure ingestion run.")
        parser.add_argument(
            "--replaces-run",
            type=int,
            default=None,
            help="Required for release replacement runs; marks the previous run's canonical records as superseded after success.",
        )

    def handle(self, *args, **options):
        if options["replay_of"]:
            try:
                run = replay_population_exposure_ingestion_run(
                    options["replay_of"],
                    file_path=options["file_path"] or None,
                    operator_note=options["operator_note"],
                )
            except PopulationExposureIngestionRun.DoesNotExist as error:
                raise CommandError(f"Population/exposure ingestion run {options['replay_of']} does not exist.") from error
            except ValueError as error:
                raise CommandError(str(error)) from error
            self.stdout.write(
                self.style.SUCCESS(
                    f"Population/exposure replay complete. run_id={run.id} status={run.status} "
                    f"loaded={run.records_loaded}/{run.records_seen} rejected={run.records_rejected}"
                )
            )
            return

        if not options["file_path"]:
            raise CommandError("--file is required unless --replay-of is supplied.")
        if options["inspect_only"]:
            if not options["source_type"]:
                raise CommandError("--source-type is required for --inspect-only.")
            inspection = inspect_population_exposure_csv(
                options["file_path"],
                source_type=options["source_type"],
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Population/exposure source inspection complete. "
                    f"adapter={inspection['adapter_key']} rows={inspection['records_seen']} "
                    f"accepted={inspection['records_loaded']} rejected={inspection['records_rejected']} "
                    f"unknown_columns={inspection['unknown_columns']}"
                )
            )
            if inspection["rejected_rows"]:
                self.stdout.write(f"Rejected row samples: {inspection['rejected_rows']}")
            return
        if not options["source_name"]:
            raise CommandError("--source-name is required for a new population/exposure ingestion run.")
        if not options["source_type"]:
            raise CommandError("--source-type is required for a new population/exposure ingestion run.")
        if (
            options["correction_mode"] == PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT
            and not options["replacement_reason"].strip()
        ):
            raise CommandError("--replacement-reason is required when --correction-mode=release_replacement.")
        if (
            options["correction_mode"] == PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT
            and not options["replaces_run"]
        ):
            raise CommandError("--replaces-run is required when --correction-mode=release_replacement.")
        if (
            options["replaces_run"]
            and options["correction_mode"] != PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT
        ):
            raise CommandError("--replaces-run is only valid when --correction-mode=release_replacement.")

        try:
            source_timestamp = parse_source_timestamp(options["source_timestamp"])
        except ValueError as error:
            raise CommandError(f"Invalid --source-timestamp: {error}") from error
        replaces_run = None
        if options["replaces_run"]:
            try:
                replaces_run = PopulationExposureIngestionRun.objects.get(pk=options["replaces_run"])
            except PopulationExposureIngestionRun.DoesNotExist as error:
                raise CommandError(f"Population/exposure ingestion run {options['replaces_run']} does not exist.") from error

        try:
            run = run_population_exposure_csv_ingestion(
                file_path=options["file_path"],
                source_name=options["source_name"],
                source_type=options["source_type"],
                source_timestamp=source_timestamp,
                release_version=options["release_version"],
                source_ref=options["source_ref"],
                correction_mode=options["correction_mode"],
                replacement_reason=options["replacement_reason"],
                operator_note=options["operator_note"],
                execution_mode=options["execution_mode"],
                fallback_used=options["fallback_used"],
                replaces_run=replaces_run,
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        style = self.style.SUCCESS if run.status != PopulationExposureIngestionRun.STATUS_FAILED else self.style.ERROR
        self.stdout.write(
            style(
                f"Population/exposure ingestion complete. run_id={run.id} status={run.status} "
                f"source_type={run.source_type} release={run.release_version or 'unversioned'} "
                f"loaded={run.records_loaded}/{run.records_seen} rejected={run.records_rejected}"
            )
        )
