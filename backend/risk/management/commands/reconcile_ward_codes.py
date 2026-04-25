from django.core.management.base import BaseCommand

from risk.seed_kenya_administrative_areas import reconcile_ward_codes_from_reference


class Command(BaseCommand):
    help = "Reconcile backend ward codes against the canonical Kenya county/ward reference dataset."

    def add_arguments(self, parser):
        parser.add_argument(
            "--county",
            action="append",
            dest="counties",
            help="Limit reconciliation to one or more county names.",
        )

    def handle(self, *args, **options):
        reconcile_ward_codes_from_reference(
            stdout=self.stdout,
            county_names=options.get("counties"),
        )
