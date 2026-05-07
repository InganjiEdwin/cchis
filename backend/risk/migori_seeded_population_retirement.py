from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from risk.migori_worldpop_population_import import (
    DEFAULT_IMPORT_SUMMARY_PATH,
    DEFAULT_RELEASE_VERSION,
    DEFAULT_SOURCE_NAME,
    DEFAULT_SOURCE_TYPE,
)
from risk.models import (
    ExposureFeatureRecord,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
)


DEFAULT_RETIREMENT_SUMMARY_PATH = (
    DEFAULT_IMPORT_SUMMARY_PATH.parent / "migori_seeded_population_density_retirement.json"
)
DEFAULT_RETIREMENT_SCOPE = "population_and_density"
DEFAULT_EXPECTED_WARD_COUNT = 40
DEFAULT_COUNTY = "Migori"


def _replacement_run(replacement_run_id: int | None = None) -> PopulationExposureIngestionRun:
    if replacement_run_id is None:
        run = (
            PopulationExposureIngestionRun.objects.filter(
                status=PopulationExposureIngestionRun.STATUS_SUCCESS,
                source_name=DEFAULT_SOURCE_NAME,
                source_type=DEFAULT_SOURCE_TYPE,
                release_version=DEFAULT_RELEASE_VERSION,
            )
            .order_by("-started_at", "-id")
            .first()
        )
        if run is None:
            raise ValueError(
                "No successful Migori WorldPop replacement run found. "
                "Pass --replacement-run-id explicitly after importing WorldPop data."
            )
    else:
        run = PopulationExposureIngestionRun.objects.get(id=replacement_run_id)
    if run.status != PopulationExposureIngestionRun.STATUS_SUCCESS:
        raise ValueError(f"Replacement run {run.id} is not successful.")
    if run.source_name != DEFAULT_SOURCE_NAME:
        raise ValueError(f"Replacement run {run.id} is not the Migori WorldPop source.")
    if run.source_type != DEFAULT_SOURCE_TYPE:
        raise ValueError(f"Replacement run {run.id} is not a {DEFAULT_SOURCE_TYPE} run.")
    if run.release_version != DEFAULT_RELEASE_VERSION:
        raise ValueError(f"Replacement run {run.id} is not release '{DEFAULT_RELEASE_VERSION}'.")
    return run


def _replacement_ward_ids(replacement_run: PopulationExposureIngestionRun) -> set[int]:
    return _replacement_record_scope(replacement_run)["replacement_ward_ids"]


def _replacement_record_scope(replacement_run: PopulationExposureIngestionRun) -> dict[str, set[int]]:
    population_ward_ids = set(
        PopulationBaselineRecord.objects.filter(ingestion_run=replacement_run).values_list("ward_id", flat=True)
    )
    density_ward_ids = set(
        ExposureFeatureRecord.objects.filter(
            ingestion_run=replacement_run,
            exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
        ).values_list("ward_id", flat=True)
    )
    return {
        "population_ward_ids": population_ward_ids,
        "density_ward_ids": density_ward_ids,
        "replacement_ward_ids": population_ward_ids | density_ward_ids,
    }


def _scoped_seeded_population_qs(*, ward_ids: set[int], county: str):
    return PopulationBaselineRecord.objects.filter(
        source_kind=PopulationExposureSourceKind.SEEDED,
        truth_class=PopulationExposureTruth.SEEDED_DEMO,
        ward_id__in=ward_ids,
        ward__county__iexact=county,
    )


def _current_seeded_population_qs(*, ward_ids: set[int], county: str):
    return _scoped_seeded_population_qs(ward_ids=ward_ids, county=county).exclude(
        freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE
    )


def _scoped_seeded_density_qs(*, ward_ids: set[int], county: str):
    return ExposureFeatureRecord.objects.filter(
        source_kind=PopulationExposureSourceKind.SEEDED,
        truth_class=PopulationExposureTruth.SEEDED_DEMO,
        exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
        ward_id__in=ward_ids,
        ward__county__iexact=county,
    )


def _current_seeded_density_qs(*, ward_ids: set[int], county: str):
    return _scoped_seeded_density_qs(ward_ids=ward_ids, county=county).exclude(
        freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE
    )


def _other_seeded_exposure_qs(*, ward_ids: set[int], county: str):
    return ExposureFeatureRecord.objects.filter(
        source_kind=PopulationExposureSourceKind.SEEDED,
        truth_class=PopulationExposureTruth.SEEDED_DEMO,
        ward_id__in=ward_ids,
        ward__county__iexact=county,
    ).exclude(exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY)


def _out_of_scope_current_seeded_qs(*, ward_ids: set[int], county: str):
    return PopulationBaselineRecord.objects.filter(
        source_kind=PopulationExposureSourceKind.SEEDED,
        truth_class=PopulationExposureTruth.SEEDED_DEMO,
    ).exclude(ward_id__in=ward_ids, ward__county__iexact=county).exclude(
        freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE
    )


def _out_of_scope_current_seeded_density_qs(*, ward_ids: set[int], county: str):
    return ExposureFeatureRecord.objects.filter(
        source_kind=PopulationExposureSourceKind.SEEDED,
        truth_class=PopulationExposureTruth.SEEDED_DEMO,
        exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
    ).exclude(ward_id__in=ward_ids, ward__county__iexact=county).exclude(
        freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE
    )


def _count_by(queryset, *fields: str) -> list[dict[str, Any]]:
    return list(queryset.values(*fields).annotate(count=Count("id")).order_by(*fields))


def _mark_records(records, *, replacement_run: PopulationExposureIngestionRun, reason: str, scope: str) -> int:
    retired_at = timezone.now().isoformat()
    count = 0
    for record in records:
        record.freshness_state = PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE
        record.raw_payload = {
            **(record.raw_payload or {}),
            "seeded_retirement": {
                "retired_at": retired_at,
                "replacement_run_id": replacement_run.id,
                "replacement_source_name": replacement_run.source_name,
                "replacement_release_version": replacement_run.release_version,
                "reason": reason,
                "scope": scope,
            },
        }
        record.save(update_fields=["freshness_state", "raw_payload"])
        count += 1
    return count


def retire_seeded_population_density_records(
    *,
    replacement_run_id: int | None = None,
    apply: bool = False,
    reason: str = "WorldPop 2026 Migori gridded population import replaced seeded population and density demo records.",
    expected_ward_count: int = DEFAULT_EXPECTED_WARD_COUNT,
    county: str = DEFAULT_COUNTY,
) -> dict[str, Any]:
    replacement_run = _replacement_run(replacement_run_id)
    replacement_scope = _replacement_record_scope(replacement_run)
    replacement_population_ward_ids = replacement_scope["population_ward_ids"]
    replacement_density_ward_ids = replacement_scope["density_ward_ids"]
    replacement_ward_ids = replacement_scope["replacement_ward_ids"]
    scope = DEFAULT_RETIREMENT_SCOPE
    population_candidates = _current_seeded_population_qs(ward_ids=replacement_ward_ids, county=county)
    density_candidates = _current_seeded_density_qs(ward_ids=replacement_ward_ids, county=county)
    other_seeded_exposures = _other_seeded_exposure_qs(ward_ids=replacement_ward_ids, county=county)

    before = {
        "current_seeded_population_records": population_candidates.count(),
        "current_seeded_density_records": density_candidates.count(),
        "other_seeded_exposure_records": other_seeded_exposures.count(),
        "out_of_scope_current_seeded_population_records": _out_of_scope_current_seeded_qs(
            ward_ids=replacement_ward_ids,
            county=county,
        ).count(),
        "out_of_scope_current_seeded_density_records": _out_of_scope_current_seeded_density_qs(
            ward_ids=replacement_ward_ids,
            county=county,
        ).count(),
        "other_seeded_exposure_records_by_type": _count_by(
            other_seeded_exposures,
            "exposure_type",
            "freshness_state",
        ),
    }
    records_marked = {
        "population_baseline_records": 0,
        "density_exposure_records": 0,
        "canonical_records_total": 0,
    }

    if apply:
        with transaction.atomic():
            replacement_run = PopulationExposureIngestionRun.objects.select_for_update().get(id=replacement_run.id)
            records_marked["population_baseline_records"] = _mark_records(
                _current_seeded_population_qs(
                    ward_ids=replacement_ward_ids,
                    county=county,
                ).select_for_update().order_by("id"),
                replacement_run=replacement_run,
                reason=reason,
                scope=scope,
            )
            records_marked["density_exposure_records"] = _mark_records(
                _current_seeded_density_qs(
                    ward_ids=replacement_ward_ids,
                    county=county,
                ).select_for_update().order_by("id"),
                replacement_run=replacement_run,
                reason=reason,
                scope=scope,
            )
            records_marked["canonical_records_total"] = (
                records_marked["population_baseline_records"] + records_marked["density_exposure_records"]
            )

    after_population = _current_seeded_population_qs(ward_ids=replacement_ward_ids, county=county)
    after_density = _current_seeded_density_qs(ward_ids=replacement_ward_ids, county=county)
    after_other_seeded_exposures = _other_seeded_exposure_qs(ward_ids=replacement_ward_ids, county=county)
    after = {
        "current_seeded_population_records": after_population.count(),
        "current_seeded_density_records": after_density.count(),
        "other_seeded_exposure_records": after_other_seeded_exposures.count(),
        "out_of_scope_current_seeded_population_records": _out_of_scope_current_seeded_qs(
            ward_ids=replacement_ward_ids,
            county=county,
        ).count(),
        "out_of_scope_current_seeded_density_records": _out_of_scope_current_seeded_density_qs(
            ward_ids=replacement_ward_ids,
            county=county,
        ).count(),
        "other_seeded_exposure_records_by_type": _count_by(
            after_other_seeded_exposures,
            "exposure_type",
            "freshness_state",
        ),
        "retired_seeded_population_records": PopulationBaselineRecord.objects.filter(
            source_kind=PopulationExposureSourceKind.SEEDED,
            truth_class=PopulationExposureTruth.SEEDED_DEMO,
            freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE,
            ward_id__in=replacement_ward_ids,
            ward__county__iexact=county,
        ).count(),
        "retired_seeded_density_records": ExposureFeatureRecord.objects.filter(
            source_kind=PopulationExposureSourceKind.SEEDED,
            truth_class=PopulationExposureTruth.SEEDED_DEMO,
            exposure_type=ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY,
            freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE,
            ward_id__in=replacement_ward_ids,
            ward__county__iexact=county,
        ).count(),
    }
    gates = {
        "applied": apply,
        "replacement_run_success": replacement_run.status == PopulationExposureIngestionRun.STATUS_SUCCESS,
        "replacement_ward_count_expected": len(replacement_ward_ids) == expected_ward_count,
        "replacement_population_ward_count_expected": len(replacement_population_ward_ids) == expected_ward_count,
        "replacement_density_ward_count_expected": len(replacement_density_ward_ids) == expected_ward_count,
        "replacement_population_and_density_ward_sets_match": replacement_population_ward_ids == replacement_density_ward_ids,
        "population_candidates_within_expected": before["current_seeded_population_records"] <= expected_ward_count,
        "density_candidates_within_expected": before["current_seeded_density_records"] <= expected_ward_count,
        "population_replacement_complete": (
            after["current_seeded_population_records"] == 0
            and after["retired_seeded_population_records"] >= expected_ward_count
        ),
        "density_replacement_complete": (
            after["current_seeded_density_records"] == 0
            and after["retired_seeded_density_records"] >= expected_ward_count
        ),
        "no_current_seeded_population_records": after["current_seeded_population_records"] == 0,
        "no_current_seeded_density_records": after["current_seeded_density_records"] == 0,
        "other_seeded_exposure_records_preserved": after["other_seeded_exposure_records"]
        == before["other_seeded_exposure_records"],
        "out_of_scope_seeded_population_preserved": after["out_of_scope_current_seeded_population_records"]
        == before["out_of_scope_current_seeded_population_records"],
        "out_of_scope_seeded_density_preserved": after["out_of_scope_current_seeded_density_records"]
        == before["out_of_scope_current_seeded_density_records"],
    }
    return {
        "phase": "migori_knbs_worldpop_seeded_population_density_retirement",
        "generated_at": timezone.now().isoformat(),
        "applied": apply,
        "passed": all(gates.values()),
        "scope": scope,
        "county": county,
        "replacement_ward_count": len(replacement_ward_ids),
        "replacement_population_ward_count": len(replacement_population_ward_ids),
        "replacement_density_ward_count": len(replacement_density_ward_ids),
        "reason": reason,
        "replacement_run": {
            "id": replacement_run.id,
            "status": replacement_run.status,
            "source_name": replacement_run.source_name,
            "source_type": replacement_run.source_type,
            "release_version": replacement_run.release_version,
            "source_ref": replacement_run.source_ref,
        },
        "before": before,
        "records_marked": records_marked,
        "after": after,
        "gates": gates,
    }


def write_retirement_summary(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
