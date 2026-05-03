from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.db.models import Count, Q

from risk.facility_forecasting import FACILITY_FORECAST_FEATURE_KEYS
from risk.ml.model import FEATURE_KEYS as WARD_RISK_FEATURE_KEYS
from risk.models import (
    CatchmentPopulationRecord,
    ExposureFeatureRecord,
    FacilityForecast,
    FeatureDataset,
    ModelRun,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
)
from risk.population_exposure_features import (
    CURRENT_EXCLUDED_FRESHNESS_STATES,
    POPULATION_EXPOSURE_DASHBOARD_CONTRACT,
    POPULATION_EXPOSURE_FEATURE_KEYS,
    POPULATION_EXPOSURE_FEATURE_SCHEMA_VERSION,
    POPULATION_EXPOSURE_TRUTH_ASSUMPTIONS,
)


PHASE_5_VERIFICATION_QUESTIONS = [
    (
        "truth_class_separation",
        "Can we distinguish direct population truth from aggregated and proxy exposure values?",
    ),
    (
        "source_replay",
        "Can we replay historical and corrected source releases safely?",
    ),
    (
        "source_lineage",
        "Can every exposure feature be traced back to normalized source records and aggregation methods?",
    ),
    (
        "downstream_explainability",
        "Can downstream modeling explain exposure and vulnerability inputs cleanly?",
    ),
    (
        "honesty_under_partial_inputs",
        "Does the system stay honest when source layers are delayed, partial, aggregated, or heuristic?",
    ),
    (
        "ops_without_frontend",
        "Can ops ingest, inspect, and replay population and exposure sources without a bespoke frontend?",
    ),
    (
        "seeded_scenario_discipline",
        "Are seeded exposure scenarios clearly marked non-production while still exercising the same ETL contracts?",
    ),
]


def _counts_by_field(model, field_name: str) -> dict:
    return {
        item[field_name] or "blank": item["count"]
        for item in model.objects.values(field_name).annotate(count=Count("id")).order_by(field_name)
    }


def _counter_dict(values: Iterable[str]) -> dict:
    return dict(Counter(value for value in values if value))


def _record_totals() -> dict:
    population_count = PopulationBaselineRecord.objects.count()
    exposure_count = ExposureFeatureRecord.objects.count()
    catchment_count = CatchmentPopulationRecord.objects.count()
    return {
        "population_baseline_records": population_count,
        "exposure_feature_records": exposure_count,
        "catchment_population_records": catchment_count,
        "canonical_records_total": population_count + exposure_count + catchment_count,
    }


def _canonical_missing_field_counts(field_name: str) -> dict:
    return {
        "population_baseline_records": PopulationBaselineRecord.objects.filter(**{field_name: ""}).count(),
        "exposure_feature_records": ExposureFeatureRecord.objects.filter(**{field_name: ""}).count(),
        "catchment_population_records": CatchmentPopulationRecord.objects.filter(**{field_name: ""}).count(),
    }


def _canonical_count(**filters) -> int:
    return (
        PopulationBaselineRecord.objects.filter(**filters).count()
        + ExposureFeatureRecord.objects.filter(**filters).count()
        + CatchmentPopulationRecord.objects.filter(**filters).count()
    )


def _canonical_count_excluding_freshness(freshness_state: str, **filters) -> int:
    return (
        PopulationBaselineRecord.objects.filter(**filters).exclude(freshness_state=freshness_state).count()
        + ExposureFeatureRecord.objects.filter(**filters).exclude(freshness_state=freshness_state).count()
        + CatchmentPopulationRecord.objects.filter(**filters).exclude(freshness_state=freshness_state).count()
    )


def _sum_counts(counts: dict) -> int:
    return sum(int(value) for value in counts.values())


def _management_command_exists(command_name: str) -> bool:
    command_path = Path(settings.BASE_DIR) / "risk" / "management" / "commands" / f"{command_name}.py"
    return command_path.exists()


def _status_from_checks(*, fail: bool = False, warning: bool = False, no_data: bool = False) -> str:
    if fail:
        return "fail"
    if warning:
        return "warning"
    if no_data:
        return "ready_no_source_data"
    return "pass"


def _truth_class_question(record_totals: dict) -> dict:
    required_truth_classes = {
        PopulationExposureTruth.DIRECT_POPULATION_BASELINE,
        PopulationExposureTruth.SPATIALLY_AGGREGATED_SOURCE,
        PopulationExposureTruth.DERIVED_EXPOSURE_PROXY,
        PopulationExposureTruth.MANUAL_OVERRIDE,
        PopulationExposureTruth.SEEDED_DEMO,
    }
    configured_truth_classes = {choice[0] for choice in PopulationExposureTruth.choices}
    observed_truth_class_counts = Counter()
    observed_truth_class_counts.update(_counts_by_field(PopulationBaselineRecord, "truth_class"))
    observed_truth_class_counts.update(_counts_by_field(ExposureFeatureRecord, "truth_class"))
    observed_truth_class_counts.update(_counts_by_field(CatchmentPopulationRecord, "truth_class"))
    missing_contract_classes = sorted(required_truth_classes.difference(configured_truth_classes))
    direct_exposure_count = ExposureFeatureRecord.objects.filter(
        truth_class=PopulationExposureTruth.DIRECT_POPULATION_BASELINE,
    ).count()
    direct_catchment_count = CatchmentPopulationRecord.objects.filter(
        truth_class=PopulationExposureTruth.DIRECT_POPULATION_BASELINE,
    ).count()
    derived_population_baseline_count = PopulationBaselineRecord.objects.filter(
        truth_class=PopulationExposureTruth.DERIVED_EXPOSURE_PROXY,
    ).count()
    truth_class_misuse_count = direct_exposure_count + direct_catchment_count + derived_population_baseline_count

    return {
        "id": "truth_class_separation",
        "question": dict(PHASE_5_VERIFICATION_QUESTIONS)["truth_class_separation"],
        "status": _status_from_checks(
            fail=bool(missing_contract_classes),
            warning=truth_class_misuse_count > 0,
            no_data=record_totals["canonical_records_total"] == 0,
        ),
        "answer": (
            "Canonical records carry explicit truth_class values for direct baselines, spatial aggregation, "
            "derived proxies, manual overrides, and seeded demo data."
        ),
        "evidence": {
            "configured_truth_classes": sorted(configured_truth_classes),
            "missing_contract_classes": missing_contract_classes,
            "observed_truth_class_counts": dict(observed_truth_class_counts),
            "direct_population_truth_on_exposure_records": direct_exposure_count,
            "direct_population_truth_on_catchment_records": direct_catchment_count,
            "derived_exposure_proxy_on_population_baseline_records": derived_population_baseline_count,
        },
        "gaps": [
            gap
            for gap, present in [
                ("truth_class_contract_incomplete", bool(missing_contract_classes)),
                ("truth_class_semantic_misuse", truth_class_misuse_count > 0),
            ]
            if present
        ],
    }


def _source_replay_question() -> dict:
    run_count = PopulationExposureIngestionRun.objects.count()
    replay_run_count = PopulationExposureIngestionRun.objects.filter(
        execution_mode=PopulationExposureIngestionRun.EXECUTION_REPLAY,
    ).count()
    replayable_run_count = PopulationExposureIngestionRun.objects.exclude(input_ref="").count()
    replacement_count = PopulationExposureIngestionRun.objects.filter(
        correction_mode=PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT,
    ).count()
    replacement_without_target_count = PopulationExposureIngestionRun.objects.filter(
        correction_mode=PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT,
        replaces_run__isnull=True,
    ).count()
    replacement_without_reason_count = PopulationExposureIngestionRun.objects.filter(
        correction_mode=PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT,
        replacement_reason="",
    ).count()
    replacement_without_release_ref_count = PopulationExposureIngestionRun.objects.filter(
        Q(release_version="") | Q(source_ref=""),
        correction_mode=PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT,
    ).count()
    replaced_record_count = _canonical_count(
        freshness_state=PopulationExposureFreshness.REPLACED_BY_NEW_RELEASE,
    )
    replay_diagnostic_record_count = _canonical_count(
        freshness_state=PopulationExposureFreshness.REPLAY_DIAGNOSTIC,
    )
    replacement_not_activated_record_count = _canonical_count(
        freshness_state=PopulationExposureFreshness.REPLACEMENT_NOT_ACTIVATED,
    )
    replay_records_not_isolated_count = _canonical_count_excluding_freshness(
        PopulationExposureFreshness.REPLAY_DIAGNOSTIC,
        ingestion_run__execution_mode=PopulationExposureIngestionRun.EXECUTION_REPLAY,
    )
    unactivated_replacement_records_not_isolated_count = _canonical_count_excluding_freshness(
        PopulationExposureFreshness.REPLACEMENT_NOT_ACTIVATED,
        ingestion_run__correction_mode=PopulationExposureIngestionRun.CORRECTION_RELEASE_REPLACEMENT,
        ingestion_run__status__in=[
            PopulationExposureIngestionRun.STATUS_PARTIAL,
            PopulationExposureIngestionRun.STATUS_FAILED,
        ],
    )
    unknown_column_run_ids = [
        run_id
        for run_id, results in PopulationExposureIngestionRun.objects.values_list("id", "results")
        if (results or {}).get("unknown_columns")
    ]
    amendment_count = PopulationExposureIngestionRun.objects.filter(
        correction_mode=PopulationExposureIngestionRun.CORRECTION_AMENDMENT,
    ).count()
    command_available = _management_command_exists("ingest_population_exposure")
    non_current_isolation_failure = (
        replay_records_not_isolated_count > 0
        or unactivated_replacement_records_not_isolated_count > 0
    )
    release_metadata_gap = (
        replacement_without_target_count > 0
        or replacement_without_reason_count > 0
        or replacement_without_release_ref_count > 0
    )

    return {
        "id": "source_replay",
        "question": dict(PHASE_5_VERIFICATION_QUESTIONS)["source_replay"],
        "status": _status_from_checks(
            fail=not command_available or non_current_isolation_failure,
            warning=release_metadata_gap or bool(unknown_column_run_ids),
            no_data=run_count == 0,
        ),
        "answer": (
            "Ingestion runs preserve source, correction, execution, input, and replacement metadata; "
            "the management command exposes replay via --replay-of, and non-activated replay/replacement rows "
            "are marked non-current."
        ),
        "evidence": {
            "ingestion_run_count": run_count,
            "replayable_run_count": replayable_run_count,
            "replay_run_count": replay_run_count,
            "release_replacement_run_count": replacement_count,
            "release_replacement_without_target_count": replacement_without_target_count,
            "release_replacement_without_reason_count": replacement_without_reason_count,
            "release_replacement_without_release_or_source_ref_count": replacement_without_release_ref_count,
            "replaced_canonical_record_count": replaced_record_count,
            "replay_diagnostic_record_count": replay_diagnostic_record_count,
            "replacement_not_activated_record_count": replacement_not_activated_record_count,
            "replay_records_not_isolated_count": replay_records_not_isolated_count,
            "unactivated_replacement_records_not_isolated_count": unactivated_replacement_records_not_isolated_count,
            "runs_with_unknown_source_columns": unknown_column_run_ids[:25],
            "amendment_run_count": amendment_count,
            "correction_modes": [choice[0] for choice in PopulationExposureIngestionRun.CORRECTION_MODE_CHOICES],
            "execution_modes": [choice[0] for choice in PopulationExposureIngestionRun.EXECUTION_MODE_CHOICES],
            "management_command_available": command_available,
            "replay_command_template": "python manage.py ingest_population_exposure --replay-of <run_id>",
        },
        "gaps": [
            gap
            for gap, present in [
                ("ingest_population_exposure_command_missing", not command_available),
                ("release_replacement_without_replaces_run", replacement_without_target_count > 0),
                ("release_replacement_without_reason", replacement_without_reason_count > 0),
                ("release_replacement_without_release_or_source_ref", replacement_without_release_ref_count > 0),
                ("replay_records_not_marked_diagnostic", replay_records_not_isolated_count > 0),
                (
                    "non_success_replacement_records_not_marked_non_current",
                    unactivated_replacement_records_not_isolated_count > 0,
                ),
                ("source_files_with_unknown_columns", bool(unknown_column_run_ids)),
            ]
            if present
        ],
    }


def _source_lineage_question(record_totals: dict) -> dict:
    exposure_count = record_totals["exposure_feature_records"]
    missing_source_count = ExposureFeatureRecord.objects.filter(
        Q(source__isnull=True) | Q(ingestion_run__isnull=True) | Q(source_name="")
    ).count()
    missing_aggregation_method_count = ExposureFeatureRecord.objects.filter(aggregation_method="").count()
    missing_spatial_resolution_count = ExposureFeatureRecord.objects.filter(spatial_resolution="").count()
    missing_unit_count = ExposureFeatureRecord.objects.filter(unit="").count()
    missing_release_version_counts = _canonical_missing_field_counts("release_version")
    missing_source_ref_counts = _canonical_missing_field_counts("source_ref")
    missing_assignment_method_count = CatchmentPopulationRecord.objects.filter(assignment_method="").count()
    missing_assigned_ward_ids_count = sum(
        1
        for assigned_ids in CatchmentPopulationRecord.objects.values_list("assigned_ward_ids", flat=True)
        if not assigned_ids
    )
    exposure_type_counts = _counts_by_field(ExposureFeatureRecord, "exposure_type")
    missing_lineage = missing_source_count > 0
    missing_aggregation = exposure_count > 0 and (
        missing_aggregation_method_count > 0
        or missing_spatial_resolution_count > 0
        or missing_unit_count > 0
    )
    missing_release_or_ref = (
        _sum_counts(missing_release_version_counts) > 0
        or _sum_counts(missing_source_ref_counts) > 0
    )
    missing_catchment_assignment = (
        missing_assignment_method_count > 0
        or missing_assigned_ward_ids_count > 0
    )

    return {
        "id": "source_lineage",
        "question": dict(PHASE_5_VERIFICATION_QUESTIONS)["source_lineage"],
        "status": _status_from_checks(
            fail=missing_lineage,
            warning=missing_aggregation or missing_release_or_ref or missing_catchment_assignment,
            no_data=record_totals["canonical_records_total"] == 0,
        ),
        "answer": (
            "Exposure features are normalized records with source and ingestion-run links; "
            "aggregation_method is audited because blank methods weaken spatial lineage."
        ),
        "evidence": {
            "exposure_feature_records": exposure_count,
            "exposure_type_counts": exposure_type_counts,
            "missing_source_or_run_count": missing_source_count,
            "missing_aggregation_method_count": missing_aggregation_method_count,
            "missing_spatial_resolution_count": missing_spatial_resolution_count,
            "missing_unit_count": missing_unit_count,
            "missing_release_version_counts": missing_release_version_counts,
            "missing_source_ref_counts": missing_source_ref_counts,
            "missing_assignment_method_count": missing_assignment_method_count,
            "missing_assigned_ward_ids_count": missing_assigned_ward_ids_count,
        },
        "gaps": [
            gap
            for gap, present in [
                ("missing_source_or_ingestion_run", missing_lineage),
                ("missing_exposure_aggregation_method", missing_aggregation),
                ("missing_release_version_or_source_ref", missing_release_or_ref),
                ("missing_catchment_assignment_metadata", missing_catchment_assignment),
            ]
            if present
        ],
    }


def _downstream_explainability_question() -> dict:
    population_exposure_dataset_count = FeatureDataset.objects.filter(
        schema_version=POPULATION_EXPOSURE_FEATURE_SCHEMA_VERSION,
    ).count()
    model_run_count = sum(
        1
        for metadata in ModelRun.objects.values_list("metadata", flat=True)
        if (metadata or {}).get("population_exposure_dataset_ref")
    )
    facility_forecast_count = sum(
        1
        for factors in FacilityForecast.objects.values_list("forecast_factors", flat=True)
        if any(
            factor.get("source") in {"population_exposure_snapshot", "population_exposure_context"}
            for factor in (factors or [])
            if isinstance(factor, dict)
        )
    )
    has_ward_model_features = bool(set(POPULATION_EXPOSURE_FEATURE_KEYS).intersection(set(WARD_RISK_FEATURE_KEYS))) or {
        "exposed_population_proxy_scaled",
        "catchment_population_estimate_scaled",
    }.issubset(set(WARD_RISK_FEATURE_KEYS))
    has_facility_features = {
        "catchment_population_estimate_scaled",
        "exposed_population_proxy_scaled",
    }.issubset(set(FACILITY_FORECAST_FEATURE_KEYS))

    return {
        "id": "downstream_explainability",
        "question": dict(PHASE_5_VERIFICATION_QUESTIONS)["downstream_explainability"],
        "status": _status_from_checks(
            fail=not has_ward_model_features or not has_facility_features,
            no_data=population_exposure_dataset_count == 0 and model_run_count == 0,
        ),
        "answer": (
            "Ward risk and facility burden contracts include population/exposure features, dataset refs, "
            "truth assumptions, and forecast factor caveats."
        ),
        "evidence": {
            "population_exposure_feature_dataset_count": population_exposure_dataset_count,
            "model_runs_with_population_exposure_ref": model_run_count,
            "facility_forecasts_with_population_exposure_factors": facility_forecast_count,
            "ward_model_feature_keys": WARD_RISK_FEATURE_KEYS,
            "facility_forecast_feature_keys": FACILITY_FORECAST_FEATURE_KEYS,
        },
        "gaps": [
            gap
            for gap, present in [
                ("ward_population_exposure_features_missing", not has_ward_model_features),
                ("facility_population_exposure_features_missing", not has_facility_features),
            ]
            if present
        ],
    }


def _honesty_question(record_totals: dict) -> dict:
    delayed_or_stale_records = (
        PopulationBaselineRecord.objects.filter(
            freshness_state__in=[PopulationExposureFreshness.DELAYED, PopulationExposureFreshness.STALE]
        ).count()
        + ExposureFeatureRecord.objects.filter(
            freshness_state__in=[PopulationExposureFreshness.DELAYED, PopulationExposureFreshness.STALE]
        ).count()
        + CatchmentPopulationRecord.objects.filter(
            freshness_state__in=[PopulationExposureFreshness.DELAYED, PopulationExposureFreshness.STALE]
        ).count()
    )
    non_current_record_count = _canonical_count(
        freshness_state__in=list(CURRENT_EXCLUDED_FRESHNESS_STATES),
    )
    partial_or_failed_runs = PopulationExposureIngestionRun.objects.filter(
        status__in=[
            PopulationExposureIngestionRun.STATUS_PARTIAL,
            PopulationExposureIngestionRun.STATUS_FAILED,
        ]
    ).count()
    fallback_run_count = PopulationExposureIngestionRun.objects.filter(fallback_used=True).count()
    rejected_row_count = sum(run.records_rejected for run in PopulationExposureIngestionRun.objects.all())
    latest_dataset = FeatureDataset.objects.filter(
        schema_version=POPULATION_EXPOSURE_FEATURE_SCHEMA_VERSION,
    ).order_by("-created_at").first()
    latest_dataset_metadata = latest_dataset.lineage_metadata if latest_dataset else {}
    dashboard_contract_present = bool(POPULATION_EXPOSURE_DASHBOARD_CONTRACT.get("must_not_imply"))

    return {
        "id": "honesty_under_partial_inputs",
        "question": dict(PHASE_5_VERIFICATION_QUESTIONS)["honesty_under_partial_inputs"],
        "status": _status_from_checks(
            fail=not dashboard_contract_present,
            no_data=record_totals["canonical_records_total"] == 0,
        ),
        "answer": (
            "Freshness, fallback, rejection, seeded-demo, and copy-contract metadata are surfaced so partial "
            "or heuristic layers remain visibly limited."
        ),
        "evidence": {
            "delayed_or_stale_record_count": delayed_or_stale_records,
            "non_current_record_count": non_current_record_count,
            "non_current_freshness_states": sorted(CURRENT_EXCLUDED_FRESHNESS_STATES),
            "partial_or_failed_ingestion_run_count": partial_or_failed_runs,
            "fallback_ingestion_run_count": fallback_run_count,
            "rejected_source_row_count": rejected_row_count,
            "dashboard_copy_contract": POPULATION_EXPOSURE_DASHBOARD_CONTRACT,
            "latest_dataset_has_truth_assumptions": bool(latest_dataset_metadata.get("truth_assumptions")),
            "latest_dataset_has_copy_contract": bool(latest_dataset_metadata.get("dashboard_copy_contract")),
        },
        "gaps": [] if dashboard_contract_present else ["dashboard_copy_contract_missing"],
    }


def _ops_question() -> dict:
    command_states = {
        "ingest_population_exposure": _management_command_exists("ingest_population_exposure"),
        "build_population_exposure_dataset": _management_command_exists("build_population_exposure_dataset"),
        "audit_population_exposure_pipeline": _management_command_exists("audit_population_exposure_pipeline"),
    }
    missing_commands = [name for name, exists in command_states.items() if not exists]

    return {
        "id": "ops_without_frontend",
        "question": dict(PHASE_5_VERIFICATION_QUESTIONS)["ops_without_frontend"],
        "status": _status_from_checks(fail=bool(missing_commands)),
        "answer": (
            "Operators can ingest, replay, build reproducible datasets, and audit the pipeline from management commands."
        ),
        "evidence": {
            "management_commands": command_states,
            "example_commands": [
                "python manage.py ingest_population_exposure --inspect-only --file source.csv --source-type <type>",
                "python manage.py ingest_population_exposure --file source.csv --source-name <name> --source-type <type>",
                "python manage.py ingest_population_exposure --replay-of <run_id>",
                "python manage.py ingest_population_exposure --file replacement.csv --source-name <name> --source-type <type> --correction-mode release_replacement --replacement-reason <reason> --replaces-run <run_id>",
                "python manage.py build_population_exposure_dataset --as-of <timestamp>",
                "python manage.py audit_population_exposure_pipeline --format json",
            ],
        },
        "gaps": missing_commands,
    }


def _seeded_question() -> dict:
    seeded_record_count = (
        PopulationBaselineRecord.objects.filter(truth_class=PopulationExposureTruth.SEEDED_DEMO).count()
        + ExposureFeatureRecord.objects.filter(truth_class=PopulationExposureTruth.SEEDED_DEMO).count()
        + CatchmentPopulationRecord.objects.filter(truth_class=PopulationExposureTruth.SEEDED_DEMO).count()
    )
    seeded_source_count = sum(
        1
        for metadata in PopulationExposureSource.objects.values_list("metadata", flat=True)
        if (metadata or {}).get("seeded") is True
    )
    seeded_run_count = sum(
        1
        for metadata in PopulationExposureIngestionRun.objects.values_list("source_metadata", flat=True)
        if (metadata or {}).get("seeded") is True
    )
    seeded_kind_count = (
        PopulationBaselineRecord.objects.filter(source_kind=PopulationExposureSourceKind.SEEDED).count()
        + ExposureFeatureRecord.objects.filter(source_kind=PopulationExposureSourceKind.SEEDED).count()
        + CatchmentPopulationRecord.objects.filter(source_kind=PopulationExposureSourceKind.SEEDED).count()
    )
    contract_available = (
        PopulationExposureTruth.SEEDED_DEMO in {choice[0] for choice in PopulationExposureTruth.choices}
        and PopulationExposureSourceKind.SEEDED in {choice[0] for choice in PopulationExposureSourceKind.choices}
    )

    return {
        "id": "seeded_scenario_discipline",
        "question": dict(PHASE_5_VERIFICATION_QUESTIONS)["seeded_scenario_discipline"],
        "status": _status_from_checks(fail=not contract_available, no_data=seeded_record_count == 0),
        "answer": (
            "Seeded scenarios use the same canonical records and source/run lineage while carrying seeded truth and source-kind markers."
        ),
        "evidence": {
            "seeded_record_count": seeded_record_count,
            "seeded_source_count": seeded_source_count,
            "seeded_ingestion_run_count": seeded_run_count,
            "seeded_source_kind_record_count": seeded_kind_count,
            "seeded_truth_assumption": POPULATION_EXPOSURE_TRUTH_ASSUMPTIONS.get(PopulationExposureTruth.SEEDED_DEMO),
        },
        "gaps": [] if contract_available else ["seeded_truth_contract_missing"],
    }


def build_population_exposure_pipeline_audit() -> dict:
    record_totals = _record_totals()
    questions = [
        _truth_class_question(record_totals),
        _source_replay_question(),
        _source_lineage_question(record_totals),
        _downstream_explainability_question(),
        _honesty_question(record_totals),
        _ops_question(),
        _seeded_question(),
    ]
    status_counts = _counter_dict(question["status"] for question in questions)
    if status_counts.get("fail"):
        overall_status = "fail"
    elif status_counts.get("warning"):
        overall_status = "warning"
    elif status_counts.get("ready_no_source_data"):
        overall_status = "ready_no_source_data"
    else:
        overall_status = "pass"

    return {
        "audit_name": "population_exposure_pipeline_phase_5",
        "overall_status": overall_status,
        "status_counts": status_counts,
        "record_totals": record_totals,
        "source_totals": {
            "source_count": PopulationExposureSource.objects.count(),
            "ingestion_run_count": PopulationExposureIngestionRun.objects.count(),
            "source_type_counts": _counts_by_field(PopulationExposureSource, "source_type"),
            "run_status_counts": _counts_by_field(PopulationExposureIngestionRun, "status"),
        },
        "verification_questions": questions,
    }
