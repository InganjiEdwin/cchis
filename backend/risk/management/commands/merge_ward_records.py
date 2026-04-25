from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import AuthAuditEvent, User
from risk.models import Alert, CHV, HealthFacility, RiskScore, SyncQueue, TriageSession, UssdSessionLog, Ward


RELATED_MODELS = [
    ("users", User, "ward"),
    ("auth_audit_events", AuthAuditEvent, "ward"),
    ("chvs", CHV, "ward"),
    ("health_facilities", HealthFacility, "ward"),
    ("risk_scores", RiskScore, "ward"),
    ("alerts", Alert, "ward"),
    ("triage_sessions", TriageSession, "ward"),
    ("ussd_session_logs", UssdSessionLog, "ward"),
    ("sync_queue_items", SyncQueue, "ward"),
]


class Command(BaseCommand):
    help = "Merge a legacy ward record into a canonical ward record and move all known ward-linked rows."

    def add_arguments(self, parser):
        parser.add_argument("--county", required=True, help="County for both ward rows.")
        parser.add_argument("--legacy-name", required=True, help="Legacy/source ward name to merge away.")
        parser.add_argument("--canonical-name", required=True, help="Canonical ward name to retain.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the merge summary without updating rows.",
        )

    def handle(self, *args, **options):
        county = options["county"].strip().title()
        legacy_name = options["legacy_name"].strip()
        canonical_name = options["canonical_name"].strip()
        dry_run = options["dry_run"]

        if legacy_name == canonical_name:
            raise CommandError("legacy-name and canonical-name must be different.")

        try:
            legacy = Ward.objects.get(county=county, name=legacy_name)
        except Ward.DoesNotExist as error:
            raise CommandError(f"Legacy ward not found: {legacy_name} ({county})") from error

        try:
            canonical = Ward.objects.get(county=county, name=canonical_name)
        except Ward.DoesNotExist as error:
            raise CommandError(f"Canonical ward not found: {canonical_name} ({county})") from error

        if legacy.id == canonical.id:
            raise CommandError("Legacy and canonical ward resolve to the same row.")

        summary = {}
        for label, model, field_name in RELATED_MODELS:
            summary[label] = model.objects.filter(**{field_name: legacy}).count()

        self.stdout.write(self.style.MIGRATE_HEADING("Ward merge summary"))
        self.stdout.write(f"County: {county}")
        self.stdout.write(f"Legacy ward: {legacy.name} ({legacy.ward_code or 'no code'}) [id={legacy.id}]")
        self.stdout.write(
            f"Canonical ward: {canonical.name} ({canonical.ward_code or 'no code'}) [id={canonical.id}]"
        )
        for label, count in summary.items():
            self.stdout.write(f"{label}: {count}")

        if dry_run:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Dry run complete. No rows were updated."))
            return

        with transaction.atomic():
            for _, model, field_name in RELATED_MODELS:
                model.objects.filter(**{field_name: legacy}).update(**{field_name: canonical})
            legacy.delete()

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Merged ward '{legacy_name}' into '{canonical_name}' and removed the legacy ward row."
            )
        )
