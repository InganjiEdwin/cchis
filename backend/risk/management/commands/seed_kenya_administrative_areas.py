from django.core.management.base import BaseCommand

from risk.seed_kenya_administrative_areas import seed_kenya_counties_and_wards


class Command(BaseCommand):
    help = "Seed Migori County wards by default; use --all-counties for the full Kenya ward reference."

    def add_arguments(self, parser):
        parser.add_argument(
            "--county",
            action="append",
            dest="counties",
            help="Limit seeding to one or more county names. Defaults to Migori when omitted.",
        )
        parser.add_argument(
            "--all-counties",
            action="store_true",
            help="Seed every county in the Kenya ward reference. This is opt-in to keep local CCHIS data Migori-scoped.",
        )

    def handle(self, *args, **options):
        county_names = options.get("counties")
        if not county_names and not options.get("all_counties"):
            county_names = ["Migori"]

        seed_kenya_counties_and_wards(
            stdout=self.stdout,
            county_names=county_names,
        )
