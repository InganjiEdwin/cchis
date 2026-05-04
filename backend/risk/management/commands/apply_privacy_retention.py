import json

from django.core.management.base import BaseCommand, CommandError

from risk.privacy_retention import RETENTION_RULES, apply_privacy_retention, retention_policy_summary


class Command(BaseCommand):
    help = "Apply or inspect privacy retention anonymization rules for sensitive operational records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Apply anonymization. Without this flag the command performs a dry run.",
        )
        parser.add_argument(
            "--family",
            action="append",
            choices=[rule.key for rule in RETENTION_RULES],
            help="Limit execution to one retention family. Can be supplied more than once.",
        )
        parser.add_argument("--batch-size", type=int, default=500)
        parser.add_argument(
            "--policy",
            action="store_true",
            help="Print the configured retention policy instead of scanning records.",
        )

    def handle(self, *args, **options):
        if options["batch_size"] < 1:
            raise CommandError("--batch-size must be greater than zero.")

        if options["policy"]:
            self.stdout.write(json.dumps(retention_policy_summary(), indent=2, sort_keys=True))
            return

        try:
            summary = apply_privacy_retention(
                dry_run=not options["execute"],
                batch_size=options["batch_size"],
                families=options.get("family") or None,
            )
        except ValueError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(json.dumps(summary, indent=2, sort_keys=True))
