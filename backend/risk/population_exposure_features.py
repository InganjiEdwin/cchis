from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable
from uuid import uuid4

from django.utils import timezone

from risk.models import (
    CatchmentPopulationRecord,
    ExposureFeatureRecord,
    FeatureDataset,
    FeatureDatasetRow,
    HealthFacility,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
    Ward,
)


POPULATION_EXPOSURE_FEATURE_SCHEMA_VERSION = "population-exposure-v1"
POPULATION_EXPOSURE_FEATURE_KEYS = [
    "population_total",
    "population_under_five",
    "household_count_proxy",
    "population_density",
    "settlement_concentration",
    "floodplain_exposure",
    "water_body_proximity",
    "wash_vulnerability",
    "exposed_population_proxy",
    "catchment_population_estimate",
    "catchment_under_five_estimate",
]
POPULATION_EXPOSURE_TRUTH_ASSUMPTIONS = {
    PopulationExposureTruth.DIRECT_POPULATION_BASELINE: "Administrative or operator-supplied population baseline.",
    PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE: "Spatial source aggregated to ward or facility context.",
    PopulationExposureTruth.DERIVED_EXPOSURE_PROXY: "Useful model context, not direct administrative truth.",
    PopulationExposureTruth.MANUAL_OVERRIDE: "Correction or replacement value requiring operator-note review.",
    PopulationExposureTruth.SEEDED_DEMO: "Non-production scenario data only.",
}
POPULATION_EXPOSURE_DASHBOARD_CONTRACT = {
    "recommended_population_language": "population baseline or estimate",
    "recommended_exposure_language": "exposure proxy or spatially aggregated context",
    "recommended_catchment_language": "catchment population estimate",
    "must_not_imply": [
        "exact live census count",
        "person-level exposure truth",
        "facility census truth",
        "direct field measurement when truth_class is derived_exposure_proxy or seeded_demo",
    ],
}
CURRENT_EXCLUDED_FRESHNESS_STATES = frozenset(
    {
        PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE,
        PopulationExposureFreshness.REPLAY_DIAGNOSTIC,
        PopulationExposureFreshness.REPLACEMENT_NOT_ACTIVATED,
    }
)
RELEASE_FILTER_EXCLUDED_FRESHNESS_STATES = frozenset(
    {
        PopulationExposureFreshness.REPLAY_DIAGNOSTIC,
        PopulationExposureFreshness.REPLACEMENT_NOT_ACTIVATED,
    }
)

_EXPOSURE_FACTOR_LABELS = {
    ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY: "Population density context",
    ExposureFeatureRecord.EXPOSURE_SETTLEMENT_CONCENTRATION: "Settlement concentration proxy",
    ExposureFeatureRecord.EXPOSURE_FLOODPLAIN_EXPOSURE: "Flood exposure proxy",
    ExposureFeatureRecord.EXPOSURE_WATER_BODY_PROXIMITY: "Water-body proximity proxy",
    ExposureFeatureRecord.EXPOSURE_WASH_VULNERABILITY: "WASH vulnerability proxy",
    ExposureFeatureRecord.EXPOSURE_EXPOSED_POPULATION_PROXY: "Exposed population proxy",
}

_EXPOSURE_SUMMARY_LABELS = {
    ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY: "population density",
    ExposureFeatureRecord.EXPOSURE_SETTLEMENT_CONCENTRATION: "settlement concentration",
    ExposureFeatureRecord.EXPOSURE_FLOODPLAIN_EXPOSURE: "flood exposure",
    ExposureFeatureRecord.EXPOSURE_WATER_BODY_PROXIMITY: "water-body proximity",
    ExposureFeatureRecord.EXPOSURE_WASH_VULNERABILITY: "WASH vulnerability",
    ExposureFeatureRecord.EXPOSURE_EXPOSED_POPULATION_PROXY: "exposed population",
}


@dataclass(frozen=True)
class PopulationExposureSnapshotDataset:
    feature_dataset: FeatureDataset
    rows_by_ward_id: dict[int, dict]


def _latest_records_by_key(records: Iterable, key_fn) -> dict:
    latest = {}
    for record in records:
        key = key_fn(record)
        existing = latest.get(key)
        if existing is None or record.recorded_at > existing.recorded_at or (
            record.recorded_at == existing.recorded_at and record.id > existing.id
        ):
            latest[key] = record
    return latest


def _source_kind_for_records(records: list) -> str:
    if not records:
        return FeatureDataset.SOURCE_KIND_HYBRID
    source_kinds = {getattr(record, "source_kind", "") for record in records}
    if source_kinds == {PopulationExposureSourceKind.SEEDED}:
        return FeatureDataset.SOURCE_KIND_SEEDED
    if source_kinds == {PopulationExposureSourceKind.LIVE}:
        return FeatureDataset.SOURCE_KIND_LIVE
    return FeatureDataset.SOURCE_KIND_HYBRID


def _source_lineage(records: list) -> dict:
    return {
        "record_count": len(records),
        "source_names": sorted({record.source_name for record in records if record.source_name}),
        "release_versions": sorted({record.release_version for record in records if record.release_version}),
        "truth_class_counts": dict(Counter(record.truth_class for record in records if record.truth_class)),
        "source_kind_counts": dict(Counter(record.source_kind for record in records if record.source_kind)),
        "freshness_state_counts": dict(Counter(record.freshness_state for record in records if record.freshness_state)),
        "non_current_record_count": sum(
            1
            for record in records
            if record.freshness_state in CURRENT_EXCLUDED_FRESHNESS_STATES
        ),
        "replaced_record_count": sum(
            1
            for record in records
            if record.freshness_state == PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE
        ),
        "replay_diagnostic_record_count": sum(
            1
            for record in records
            if record.freshness_state == PopulationExposureFreshness.REPLAY_DIAGNOSTIC
        ),
        "replacement_not_activated_record_count": sum(
            1
            for record in records
            if record.freshness_state == PopulationExposureFreshness.REPLACEMENT_NOT_ACTIVATED
        ),
    }


def _normalise_as_of(as_of: datetime | None) -> datetime:
    as_of = as_of or timezone.now()
    if timezone.is_naive(as_of):
        as_of = timezone.make_aware(as_of, timezone.get_current_timezone())
    return as_of


def _recorded_at(value) -> str | None:
    return value.isoformat() if value else None


def _mode_for_truth_class(truth_class: str | None) -> str:
    if truth_class == PopulationExposureTruth.DIRECT_POPULATION_BASELINE:
        return "release_aware_population_baseline"
    if truth_class == PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE:
        return "spatially_aggregated_context"
    if truth_class == PopulationExposureTruth.MANUAL_OVERRIDE:
        return "manual_override_context"
    if truth_class == PopulationExposureTruth.SEEDED_DEMO:
        return "seeded_demo_context"
    return "proxy_or_derived_context"


def _record_lineage(record) -> dict:
    return {
        "record_id": record.id,
        "record_type": record._meta.model_name,
        "truth_class": record.truth_class,
        "truth_assumption": POPULATION_EXPOSURE_TRUTH_ASSUMPTIONS.get(record.truth_class, ""),
        "source_kind": record.source_kind,
        "source_name": record.source_name,
        "release_version": record.release_version,
        "freshness_state": record.freshness_state,
        "recorded_at": _recorded_at(record.recorded_at),
        "source_ref": record.source_ref,
    }


def _population_factor(record: PopulationBaselineRecord) -> dict:
    return {
        "factor_type": "population_baseline",
        "label": "Population baseline",
        "value": record.population_total,
        "unit": "people",
        "source": "population_baseline_record",
        "mode": _mode_for_truth_class(record.truth_class),
        "truth_class": record.truth_class,
        "source_kind": record.source_kind,
        "freshness_state": record.freshness_state,
        "summary_text": (
            f"Population baseline/estimate is {record.population_total:,}; "
            f"truth class is {record.truth_class.replace('_', ' ')}."
        ),
        "display_caveat": "Use as a source-fed population baseline or estimate, not as exact live census truth.",
        "lineage": _record_lineage(record),
    }


def _exposure_factor(record: ExposureFeatureRecord) -> dict:
    label = _EXPOSURE_FACTOR_LABELS.get(record.exposure_type, record.exposure_type.replace("_", " ").title())
    summary_label = _EXPOSURE_SUMMARY_LABELS.get(record.exposure_type, record.exposure_type.replace("_", " "))
    value = round(record.exposure_value, 4) if isinstance(record.exposure_value, float) else record.exposure_value
    return {
        "factor_type": record.exposure_type,
        "label": label,
        "value": value,
        "unit": record.unit or "source_unit",
        "source": "exposure_feature_record",
        "mode": _mode_for_truth_class(record.truth_class),
        "truth_class": record.truth_class,
        "source_kind": record.source_kind,
        "freshness_state": record.freshness_state,
        "summary_text": (
            f"{summary_label[:1].upper() + summary_label[1:]} is available as "
            f"{record.truth_class.replace('_', ' ')} context."
        ),
        "display_caveat": "Use this as exposure context; do not describe it as direct person-level exposure truth.",
        "lineage": _record_lineage(record),
    }


def _catchment_factor(records: list[CatchmentPopulationRecord], *, facility: HealthFacility | None = None) -> dict | None:
    if not records:
        return None

    catchment_population = round(sum(record.catchment_population_estimate for record in records), 2)
    under_five_values = [
        record.catchment_under_five_estimate
        for record in records
        if record.catchment_under_five_estimate is not None
    ]
    catchment_under_five = round(sum(under_five_values), 2) if under_five_values else None
    lineage = _source_lineage(records)
    label = "Facility catchment population estimate" if facility else "Ward-linked catchment population estimate"
    return {
        "factor_type": "catchment_population_estimate",
        "label": label,
        "value": catchment_population,
        "unit": "people",
        "source": "catchment_population_record",
        "mode": "proxy_or_aggregated_context",
        "truth_class": max(lineage["truth_class_counts"], key=lineage["truth_class_counts"].get)
        if lineage["truth_class_counts"]
        else PopulationExposureTruth.DERIVED_EXPOSURE_PROXY,
        "truth_class_counts": lineage["truth_class_counts"],
        "source_kind_counts": lineage["source_kind_counts"],
        "freshness_state_counts": lineage["freshness_state_counts"],
        "catchment_under_five_estimate": catchment_under_five,
        "summary_text": (
            f"Catchment population estimate is {catchment_population:,.0f}; "
            "treat it as a catchment estimate, not facility census truth."
        ),
        "display_caveat": "Catchment values are service-area estimates or proxies and may be spatially aggregated.",
        "lineage": {
            "record_ids": [record.id for record in records],
            "facility_ids": sorted({record.facility_id for record in records}),
            "source_lineage": lineage,
            "latest_recorded_at": _recorded_at(max(record.recorded_at for record in records)),
        },
    }


def _filter_by_release(queryset, release_version: str | None):
    if release_version:
        return queryset.filter(release_version=release_version).exclude(
            freshness_state__in=RELEASE_FILTER_EXCLUDED_FRESHNESS_STATES
        )
    return queryset.exclude(freshness_state__in=CURRENT_EXCLUDED_FRESHNESS_STATES)


def _latest_context_records(
    ward: Ward,
    *,
    as_of: datetime,
    facility: HealthFacility | None = None,
) -> tuple[
    PopulationBaselineRecord | None,
    dict[str, ExposureFeatureRecord],
    list[CatchmentPopulationRecord],
]:
    population_record = (
        PopulationBaselineRecord.objects.filter(ward=ward, recorded_at__lte=as_of)
        .exclude(freshness_state__in=CURRENT_EXCLUDED_FRESHNESS_STATES)
        .order_by("-recorded_at", "-id")
        .first()
    )
    exposure_records = _latest_records_by_key(
        ExposureFeatureRecord.objects.filter(ward=ward, recorded_at__lte=as_of).exclude(
            freshness_state__in=CURRENT_EXCLUDED_FRESHNESS_STATES
        ),
        lambda record: record.exposure_type,
    )
    catchment_qs = CatchmentPopulationRecord.objects.filter(
        facility__ward=ward,
        recorded_at__lte=as_of,
    ).exclude(freshness_state__in=CURRENT_EXCLUDED_FRESHNESS_STATES).select_related("facility")
    if facility is not None:
        catchment_qs = catchment_qs.filter(facility=facility)
    catchment_records = list(_latest_records_by_key(catchment_qs, lambda record: record.facility_id).values())
    return population_record, exposure_records, catchment_records


def build_population_exposure_context_for_ward(
    ward: Ward,
    *,
    as_of: datetime | None = None,
) -> dict:
    as_of = _normalise_as_of(as_of)
    population_record, exposure_records, catchment_records = _latest_context_records(ward, as_of=as_of)
    return _population_exposure_context(
        ward=ward,
        as_of=as_of,
        population_record=population_record,
        exposure_records=exposure_records,
        catchment_records=catchment_records,
    )


def build_population_exposure_context_for_facility(
    facility: HealthFacility,
    *,
    as_of: datetime | None = None,
) -> dict:
    as_of = _normalise_as_of(as_of)
    population_record, exposure_records, catchment_records = _latest_context_records(
        facility.ward,
        as_of=as_of,
        facility=facility,
    )
    return _population_exposure_context(
        ward=facility.ward,
        as_of=as_of,
        population_record=population_record,
        exposure_records=exposure_records,
        catchment_records=catchment_records,
        facility=facility,
    )


def _population_exposure_context(
    *,
    ward: Ward,
    as_of: datetime,
    population_record: PopulationBaselineRecord | None,
    exposure_records: dict[str, ExposureFeatureRecord],
    catchment_records: list[CatchmentPopulationRecord],
    facility: HealthFacility | None = None,
) -> dict:
    factors = []
    if population_record is not None:
        factors.append(_population_factor(population_record))
    factors.extend(_exposure_factor(record) for record in exposure_records.values())
    catchment_factor = _catchment_factor(catchment_records, facility=facility)
    if catchment_factor is not None:
        factors.append(catchment_factor)

    values = _build_row_values(
        ward=ward,
        population_record=population_record,
        exposure_records=exposure_records,
        catchment_records=catchment_records,
    )
    source_records = []
    if population_record is not None:
        source_records.append(population_record)
    source_records.extend(exposure_records.values())
    source_records.extend(catchment_records)
    lineage = _source_lineage(source_records)

    if not source_records:
        status = "unavailable"
        caveat = "No source-fed population or exposure records are available for this ward yet."
    elif (
        lineage["truth_class_counts"].get(PopulationExposureTruth.DERIVED_EXPOSURE_PROXY)
        or lineage["truth_class_counts"].get(PopulationExposureTruth.SEEDED_DEMO)
        or lineage["source_kind_counts"].get(PopulationExposureSourceKind.SEEDED)
    ):
        status = "proxy_or_seeded_context"
        caveat = "Some values are proxies, spatial aggregations, or seeded demo context; do not present them as exact truth."
    else:
        status = "source_fed_context"
        caveat = "Values are source-fed but still release-bound baselines or spatial aggregates, not live person-level truth."

    return {
        "schema_version": POPULATION_EXPOSURE_FEATURE_SCHEMA_VERSION,
        "snapshot_as_of": as_of.isoformat(),
        "ward_id": ward.id,
        "ward_name": ward.name,
        "facility_id": facility.id if facility else None,
        "facility_name": facility.name if facility else "",
        "status": status,
        "values": {
            "population_total": values["population_total"],
            "population_under_five": values["population_under_five"],
            "household_count_proxy": values["household_count_proxy"],
            "population_density": values["population_density"],
            "settlement_concentration": values["settlement_concentration"],
            "floodplain_exposure": values["floodplain_exposure"],
            "water_body_proximity": values["water_body_proximity"],
            "wash_vulnerability": values["wash_vulnerability"],
            "exposed_population_proxy": values["exposed_population_proxy"],
            "catchment_population_estimate": values["catchment_population_estimate"],
            "catchment_under_five_estimate": values["catchment_under_five_estimate"],
        },
        "coverage": {
            "has_population_baseline": population_record is not None,
            "exposure_types": sorted(exposure_records.keys()),
            "has_any_exposure": bool(exposure_records),
            "has_catchment_population": bool(catchment_records),
            "catchment_record_count": len(catchment_records),
            "record_count": len(source_records),
        },
        "factor_items": factors,
        "source_lineage": lineage,
        "truth_assumptions": POPULATION_EXPOSURE_TRUTH_ASSUMPTIONS,
        "dashboard_copy_contract": POPULATION_EXPOSURE_DASHBOARD_CONTRACT,
        "display_caveat": caveat,
    }


def _build_row_values(
    *,
    ward: Ward,
    population_record: PopulationBaselineRecord | None,
    exposure_records: dict[str, ExposureFeatureRecord],
    catchment_records: list[CatchmentPopulationRecord],
) -> dict:
    exposure_values = {
        exposure_type: exposure_records.get(exposure_type).exposure_value
        if exposure_records.get(exposure_type)
        else None
        for exposure_type, _ in ExposureFeatureRecord.EXPOSURE_TYPE_CHOICES
    }
    catchment_population = sum(record.catchment_population_estimate for record in catchment_records) if catchment_records else None
    catchment_under_five_values = [
        record.catchment_under_five_estimate
        for record in catchment_records
        if record.catchment_under_five_estimate is not None
    ]
    catchment_under_five = sum(catchment_under_five_values) if catchment_under_five_values else None
    source_records = []
    if population_record:
        source_records.append(population_record)
    source_records.extend(exposure_records.values())
    source_records.extend(catchment_records)

    return {
        "ward_id": ward.id,
        "ward_name": ward.name,
        "population_total": population_record.population_total if population_record else None,
        "population_under_five": population_record.population_under_five if population_record else None,
        "household_count_proxy": population_record.household_count_proxy if population_record else None,
        "population_baseline_record_id": population_record.id if population_record else None,
        "population_density": exposure_values.get(ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY),
        "settlement_concentration": exposure_values.get(ExposureFeatureRecord.EXPOSURE_SETTLEMENT_CONCENTRATION),
        "floodplain_exposure": exposure_values.get(ExposureFeatureRecord.EXPOSURE_FLOODPLAIN_EXPOSURE),
        "water_body_proximity": exposure_values.get(ExposureFeatureRecord.EXPOSURE_WATER_BODY_PROXIMITY),
        "wash_vulnerability": exposure_values.get(ExposureFeatureRecord.EXPOSURE_WASH_VULNERABILITY),
        "exposed_population_proxy": exposure_values.get(ExposureFeatureRecord.EXPOSURE_EXPOSED_POPULATION_PROXY),
        "exposure_record_ids": {
            exposure_type: record.id
            for exposure_type, record in exposure_records.items()
        },
        "catchment_population_estimate": catchment_population,
        "catchment_under_five_estimate": catchment_under_five,
        "catchment_record_ids": [record.id for record in catchment_records],
        "source_lineage": _source_lineage(source_records),
    }


def build_population_exposure_feature_dataset(
    wards: Iterable[Ward] | None = None,
    *,
    as_of: datetime | None = None,
    release_version: str | None = None,
    month: int | None = None,
) -> PopulationExposureSnapshotDataset:
    as_of = _normalise_as_of(as_of)

    ward_list = list(wards) if wards is not None else list(Ward.objects.filter(is_active=True).order_by("name"))
    ward_ids = [ward.id for ward in ward_list]
    month = month or as_of.month

    population_qs = PopulationBaselineRecord.objects.filter(ward_id__in=ward_ids, recorded_at__lte=as_of).select_related("ward")
    exposure_qs = ExposureFeatureRecord.objects.filter(ward_id__in=ward_ids, recorded_at__lte=as_of).select_related("ward")
    catchment_qs = CatchmentPopulationRecord.objects.filter(
        facility__ward_id__in=ward_ids,
        recorded_at__lte=as_of,
    ).select_related("facility", "facility__ward")

    population_qs = _filter_by_release(population_qs, release_version)
    exposure_qs = _filter_by_release(exposure_qs, release_version)
    catchment_qs = _filter_by_release(catchment_qs, release_version)

    population_by_ward = _latest_records_by_key(population_qs, lambda record: record.ward_id)
    exposure_by_key = _latest_records_by_key(exposure_qs, lambda record: (record.ward_id, record.exposure_type))
    catchment_by_facility = _latest_records_by_key(catchment_qs, lambda record: record.facility_id)

    catchment_by_ward: dict[int, list[CatchmentPopulationRecord]] = defaultdict(list)
    for record in catchment_by_facility.values():
        catchment_by_ward[record.facility.ward_id].append(record)

    rows_by_ward_id = {}
    all_source_records = []
    for ward in ward_list:
        ward_exposures = {
            exposure_type: record
            for (ward_id, exposure_type), record in exposure_by_key.items()
            if ward_id == ward.id
        }
        row_values = _build_row_values(
            ward=ward,
            population_record=population_by_ward.get(ward.id),
            exposure_records=ward_exposures,
            catchment_records=catchment_by_ward.get(ward.id, []),
        )
        rows_by_ward_id[ward.id] = row_values
        if population_by_ward.get(ward.id):
            all_source_records.append(population_by_ward[ward.id])
        all_source_records.extend(ward_exposures.values())
        all_source_records.extend(catchment_by_ward.get(ward.id, []))

    dataset_ref = f"population-exposure-{POPULATION_EXPOSURE_FEATURE_SCHEMA_VERSION}-month-{month}-{uuid4().hex[:8]}"
    coverage = {
        "ward_count": len(ward_list),
        "wards_with_population_baseline": sum(1 for row in rows_by_ward_id.values() if row["population_total"] is not None),
        "wards_with_any_exposure": sum(1 for row in rows_by_ward_id.values() if row["exposure_record_ids"]),
        "wards_with_catchment_population": sum(1 for row in rows_by_ward_id.values() if row["catchment_record_ids"]),
        "exposure_record_counts_by_type": dict(
            Counter(
                exposure_type
                for row in rows_by_ward_id.values()
                for exposure_type in row["exposure_record_ids"].keys()
            )
        ),
    }
    dataset = FeatureDataset.objects.create(
        dataset_ref=dataset_ref,
        dataset_kind=FeatureDataset.KIND_INFERENCE,
        schema_version=POPULATION_EXPOSURE_FEATURE_SCHEMA_VERSION,
        source_kind=_source_kind_for_records(all_source_records),
        month=month,
        feature_keys=POPULATION_EXPOSURE_FEATURE_KEYS,
        row_count=len(rows_by_ward_id),
        lineage_metadata={
            "builder": "build_population_exposure_feature_dataset",
            "snapshot_as_of": as_of.isoformat(),
            "release_version_filter": release_version or "",
            "coverage": coverage,
            "source_lineage": _source_lineage(all_source_records),
            "truth_assumptions": POPULATION_EXPOSURE_TRUTH_ASSUMPTIONS,
            "dashboard_copy_contract": POPULATION_EXPOSURE_DASHBOARD_CONTRACT,
        },
    )
    FeatureDatasetRow.objects.bulk_create(
        [
            FeatureDatasetRow(
                dataset=dataset,
                ward=ward,
                ward_name_snapshot=ward.name,
                month=month,
                feature_values=rows_by_ward_id[ward.id],
                label=None,
            )
            for ward in ward_list
        ]
    )
    return PopulationExposureSnapshotDataset(feature_dataset=dataset, rows_by_ward_id=rows_by_ward_id)
