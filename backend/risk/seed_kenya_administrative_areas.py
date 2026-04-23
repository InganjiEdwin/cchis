from __future__ import annotations

import csv
from pathlib import Path

from risk.models import Ward


DATASET_PATH = Path(__file__).resolve().parent / "data" / "kenya_counties_wards.csv"


def seed_kenya_counties_and_wards(*, stdout=None, county_names: list[str] | None = None) -> tuple[int, int]:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Kenya ward seed dataset not found at {DATASET_PATH}")

    created = 0
    updated = 0
    normalized_county_names = {county_name.strip().title() for county_name in county_names or [] if county_name.strip()}

    with DATASET_PATH.open("r", encoding="utf-8-sig", newline="") as dataset:
        reader = csv.DictReader(dataset)
        for row in reader:
            county = row["COUNTY NAME"].strip().title()
            if normalized_county_names and county not in normalized_county_names:
                continue
            constituency = row["CONSTITUENCY NAME"].strip().title()
            ward_name = row["WARD NAME"].strip().title()
            ward_code = f"KE-WARD-{int(row['WARD ID']):04d}"

            ward, was_created = Ward.objects.update_or_create(
                county=county,
                name=ward_name,
                defaults={
                    "sub_county": constituency,
                    "ward_code": ward_code,
                    "is_active": True,
                },
            )

            if was_created:
                created += 1
            else:
                updated += 1

    if stdout:
        stdout.write(
            f"Seeded Kenya county/ward dataset from {DATASET_PATH.name}: created={created}, updated={updated}"
        )

    return created, updated
