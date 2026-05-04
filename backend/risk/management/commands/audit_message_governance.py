import json

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError, connection

from risk.message_governance import build_message_governance_audit
from risk.models import (
    Alert,
    CHVMessage,
    ContactPreference,
    FacilityReadinessUpdateRequest,
    MessageTemplate,
    UssdMenuVersion,
    UssdSessionLog,
)


REQUIRED_AUDIT_MODELS = (
    MessageTemplate,
    Alert,
    CHVMessage,
    FacilityReadinessUpdateRequest,
    ContactPreference,
    UssdMenuVersion,
    UssdSessionLog,
)


class Command(BaseCommand):
    help = "Audit message inventory, template registry, audience decisions, monitoring, and unsafe delivery records."

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
            help="Exit with an error when the audit reports fail status.",
        )

    def handle(self, *args, **options):
        existing_tables = set(connection.introspection.table_names())
        missing_tables = sorted(
            model._meta.db_table for model in REQUIRED_AUDIT_MODELS if model._meta.db_table not in existing_tables
        )
        if missing_tables:
            raise CommandError(
                "Message governance audit could not query one or more required tables. "
                "Run database migrations before executing audit_message_governance. "
                f"Missing tables: {', '.join(missing_tables)}"
            )

        try:
            audit = build_message_governance_audit()
        except DatabaseError as exc:
            raise CommandError(
                "Message governance audit could not query one or more required tables. "
                "Run database migrations before executing audit_message_governance."
            ) from exc

        if options["format"] == "json":
            self.stdout.write(json.dumps(audit, cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Message governance audit: {audit['overall_status']}")
            self.stdout.write(f"Inventory records: {audit['inventory']['inventory_count']}")
            self.stdout.write(f"Registered templates: {audit['template_count']}")
            for item in audit["audit_checks"]:
                self.stdout.write(f"- {item['id']}: {item['status']}")
                self.stdout.write(f"  {item['answer']}")
                if item["gaps"]:
                    self.stdout.write(f"  gaps={item['gaps']}")

        if options["strict"] and audit["overall_status"] == "fail":
            raise CommandError("Message governance audit finished with fail status.")
