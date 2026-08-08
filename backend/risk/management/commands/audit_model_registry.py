import json

from django.core.management.base import BaseCommand, CommandError

from risk.ml.model_registry_audit import build_model_registry_audit


class Command(BaseCommand):
    help = "Run the read-only model artifact registry integrity audit."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        payload = build_model_registry_audit(strict=options["strict"])
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True, default=str))
        if options["strict"] and payload["overall_status"] == "fail":
            raise CommandError("model_registry_audit_failed")
