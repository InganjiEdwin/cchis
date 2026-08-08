import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.models import SurveillanceIngestionRun
from risk.surveillance_lineage import reconcile_surveillance_label_lineage


class Command(BaseCommand):
    help = "Audit or apply supersession reconciliation for surveillance label datasets and model evidence."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Retire affected datasets, build replacements, and update current model evidence.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report affected records and datasets without changing the database (the default).",
        )
        parser.add_argument(
            "--run-id",
            type=int,
            default=None,
            help="Limit reconciliation to records superseded by this ingestion run.",
        )
        parser.add_argument(
            "--record-id",
            type=int,
            action="append",
            dest="record_ids",
            default=[],
            help="Limit reconciliation to a superseded canonical record; may be repeated.",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format for the reconciliation report.",
        )

    def handle(self, *args, **options):
        if options["apply"] and options["dry_run"]:
            raise CommandError("--apply and --dry-run cannot be used together.")

        run = None
        if options["run_id"] is not None:
            try:
                run = SurveillanceIngestionRun.objects.get(id=options["run_id"])
            except SurveillanceIngestionRun.DoesNotExist as error:
                raise CommandError(f"Surveillance ingestion run {options['run_id']} does not exist.") from error

        summary = reconcile_surveillance_label_lineage(
            superseding_ingestion_run=run,
            superseded_record_ids=options["record_ids"] or None,
            apply=bool(options["apply"]),
        )
        if options["format"] == "json":
            self.stdout.write(json.dumps(summary, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
            return

        mode = "applied" if summary["applied"] else "dry-run"
        self.stdout.write(
            f"Surveillance label lineage reconciliation ({mode}): "
            f"superseded_records={summary['superseded_record_count']} "
            f"affected_windows={summary['affected_window_count']} "
            f"affected_datasets={len(summary['affected_datasets'])} "
            f"replacements={len(summary['replacement_datasets'])}"
        )
        if summary["windows_without_dataset_count"]:
            self.stdout.write(
                self.style.WARNING(
                    "Windows without a feature-dataset link: "
                    f"{summary['windows_without_dataset_count']}"
                )
            )
