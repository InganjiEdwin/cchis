from __future__ import annotations

import csv
import re
from pathlib import Path

from risk.models import Ward


DATASET_PATH = Path(__file__).resolve().parent / "data" / "kenya_counties_wards.csv"


def _normalize_ward_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _normalize_county_names(county_names: list[str] | None) -> set[str]:
    return {county_name.strip().title() for county_name in county_names or [] if county_name.strip()}


def _iter_dataset_rows(*, county_names: list[str] | None = None):
    normalized_county_names = _normalize_county_names(county_names)

    with DATASET_PATH.open("r", encoding="utf-8-sig", newline="") as dataset:
        reader = csv.DictReader(dataset)
        for row in reader:
            county = row["COUNTY NAME"].strip().title()
            if normalized_county_names and county not in normalized_county_names:
                continue
            yield row


def seed_kenya_counties_and_wards(*, stdout=None, county_names: list[str] | None = None) -> tuple[int, int]:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Kenya ward seed dataset not found at {DATASET_PATH}")

    created = 0
    updated = 0

    for row in _iter_dataset_rows(county_names=county_names):
        county = row["COUNTY NAME"].strip().title()
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


def reconcile_ward_codes_from_reference(
    *,
    stdout=None,
    county_names: list[str] | None = None,
) -> tuple[int, int]:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Kenya ward seed dataset not found at {DATASET_PATH}")

    updated = 0
    missing = 0
    normalized_county_names = _normalize_county_names(county_names)

    ward_lookup = {}
    queryset = Ward.objects.all()
    if normalized_county_names:
        queryset = queryset.filter(county__in=normalized_county_names)
    for ward in queryset.order_by("county", "name"):
        ward_lookup[(ward.county, ward.name)] = ward
        ward_lookup[(ward.county, _normalize_ward_name(ward.name))] = ward

    for row in _iter_dataset_rows(county_names=county_names):
        county = row["COUNTY NAME"].strip().title()
        constituency = row["CONSTITUENCY NAME"].strip().title()
        ward_name = row["WARD NAME"].strip().title()
        ward_code = f"KE-WARD-{int(row['WARD ID']):04d}"

        ward = ward_lookup.get((county, ward_name)) or ward_lookup.get((county, _normalize_ward_name(ward_name)))
        if ward is None:
            missing += 1
            continue

        changed_fields = []
        if ward.name != ward_name:
            ward.name = ward_name
            changed_fields.append("name")
        if ward.sub_county != constituency:
            ward.sub_county = constituency
            changed_fields.append("sub_county")
        if ward.ward_code != ward_code:
            ward.ward_code = ward_code
            changed_fields.append("ward_code")

        if changed_fields:
            ward.save(update_fields=changed_fields)
            updated += 1

    if stdout:
        stdout.write(
            f"Reconciled ward codes from {DATASET_PATH.name}: updated={updated}, missing={missing}"
        )

    return updated, missing
