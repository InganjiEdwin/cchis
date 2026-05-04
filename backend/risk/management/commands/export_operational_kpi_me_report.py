import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.operational_metric_audit import build_operational_kpi_me_export


class Command(BaseCommand):
    help = "Export a reproducible operational KPI M&E report."

    def add_arguments(self, parser):
        parser.add_argument("--date-from", default="", help="Start date in YYYY-MM-DD format.")
        parser.add_argument("--date-to", default="", help="End date in YYYY-MM-DD format.")
        parser.add_argument("--ward-id", default="", help="Optional ward id filter.")
        parser.add_argument("--sub-county", default="", help="Optional sub-county filter.")
        parser.add_argument("--source-channel", default="", help="Optional source channel filter.")
        parser.add_argument("--format", choices=["json", "csv"], default="json", help="Export payload format.")
        parser.add_argument("--output", default="", help="Optional output path. Defaults to stdout.")

    def handle(self, *args, **options):
        try:
            export = build_operational_kpi_me_export(
                date_from=options["date_from"] or None,
                date_to=options["date_to"] or None,
                ward_id=options["ward_id"] or None,
                sub_county=options["sub_county"],
                source_channel=options["source_channel"],
                output_format=options["format"],
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        output_path = options["output"].strip()
        if output_path:
            Path(output_path).write_text(export["payload"], encoding="utf-8")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Wrote {export['filename']} rows={export['row_count']} data_sha256={export['data_sha256']} to {output_path}"
                )
            )
            return

        if options["format"] == "json":
            self.stdout.write(export["payload"])
        else:
            self.stdout.write(export["payload"])
        self.stderr.write(
            json.dumps(
                {
                    "schema_version": export["schema_version"],
                    "filename": export["filename"],
                    "row_count": export["row_count"],
                    "data_sha256": export["data_sha256"],
                    "payload_sha256": export["payload_sha256"],
                    "audit_status": export["audit_status"],
                    "audit_issue_count": export["audit_issue_count"],
                },
                cls=DjangoJSONEncoder,
                sort_keys=True,
            )
        )
