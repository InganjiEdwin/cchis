from django.core.management.base import BaseCommand

from risk.seed_kenya_administrative_areas import seed_kenya_counties_and_wards


class Command(BaseCommand):
    help = "Seed all Kenyan counties and wards into the Ward table."

    def handle(self, *args, **options):
        seed_kenya_counties_and_wards(stdout=self.stdout)
