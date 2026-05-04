import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError, connection

from risk.models import (
    Alert,
    CHVAssignment,
    CHVMessage,
    ContactPreference,
    ContactPreferenceAuditEvent,
    PreparednessAction,
    PreparednessActionEvent,
    PrivacyRetentionHold,
    SensitiveExportDownloadAudit,
    SensitiveExportRequest,
    SyncQueue,
)
from risk.privacy_audit import build_privacy_controls_audit


REQUIRED_AUDIT_MODELS = (
    Alert,
    CHVAssignment,
    CHVMessage,
    ContactPreference,
    ContactPreferenceAuditEvent,
    PreparednessAction,
    PreparednessActionEvent,
    PrivacyRetentionHold,
    SensitiveExportDownloadAudit,
    SensitiveExportRequest,
    SyncQueue,
)


class Command(BaseCommand):
    help = "Audit privacy, consent, retention, PII-safe response, and sensitive export controls."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format for the audit report.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with an error when the audit reports fail or warning status.",
        )
        parser.add_argument(
            "--stale-sync-days",
            type=int,
            default=30,
            help="Retention window, in days, for processed sync raw envelopes.",
        )

    def handle(self, *args, **options):
        if options["stale_sync_days"] < 1:
            raise CommandError("--stale-sync-days must be greater than zero.")

        existing_tables = set(connection.introspection.table_names())
        missing_tables = sorted(
            model._meta.db_table for model in REQUIRED_AUDIT_MODELS if model._meta.db_table not in existing_tables
        )
        if missing_tables:
            raise CommandError(
                "Privacy controls audit could not query one or more required tables. "
                "Run database migrations before executing audit_privacy_controls. "
                f"Missing tables: {', '.join(missing_tables)}"
            )

        try:
            audit = build_privacy_controls_audit(stale_sync_days=options["stale_sync_days"])
        except DatabaseError as exc:
            raise CommandError(
                "Privacy controls audit could not query one or more required tables. "
                "Run database migrations before executing audit_privacy_controls."
            ) from exc

        if options["format"] == "json":
            self.stdout.write(json.dumps(audit, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Privacy controls audit: {audit['overall_status']}")
            self.stdout.write(f"Records: {audit['record_totals']}")
            self.stdout.write(f"High-risk findings: {audit['high_risk_finding_count']}")
            for item in audit["audit_checks"]:
                self.stdout.write(f"- {item['id']}: {item['status']} ({item['severity']})")
                self.stdout.write(f"  {item['answer']}")
                if item["gaps"]:
                    self.stdout.write(f"  gaps={item['gaps']}")
            self.stdout.write(f"Operator handling: {audit['operator_handling']['doc_path']}")

        if options["strict"] and audit["overall_status"] in {"fail", "warning"}:
            raise CommandError(f"Privacy controls audit finished with {audit['overall_status']} status.")
