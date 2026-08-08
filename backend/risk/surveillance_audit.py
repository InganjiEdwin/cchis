from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.db.models import Count, Q

from risk.ml.model import (
    ALGORITHM_LOGISTIC_REGRESSION,
    ALGORITHM_RANDOM_FOREST,
    MODEL_CATALOG,
)
from risk.models import (
    FeatureDataset,
    FeatureDatasetRow,
    ModelRun,
    SurveillanceCaseClass,
    SurveillanceFreshnessState,
    SurveillanceIngestionRun,
    SurveillanceLabelWindow,
    SurveillanceRecord,
    SurveillanceSource,
    SurveillanceSourceKind,
    SurveillanceTruthLevel,
)
from risk.surveillance_features import SURVEILLANCE_FEATURE_SCHEMA_VERSION
from risk.surveillance_ingestion import SURVEILLANCE_ADAPTERS, SURVEILLANCE_FEED_POLICIES
from risk.surveillance_labels import (
    EXCLUDED_LABEL_FRESHNESS_STATES,
    SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE,
    SURVEILLANCE_LABEL_SCHEMA_VERSION,
    SURVEILLANCE_LABEL_TRUTH_ASSUMPTIONS,
)
from risk.surveillance_lineage import (
    current_model_run_dataset_refs,
    dataset_is_currently_eligible,
    dataset_is_superseded,
)


PHASE_6_VERIFICATION_QUESTIONS = [
    (
        "truth_level_separation",
        "Can we distinguish confirmed, suspected, and proxy surveillance truth explicitly?",
    ),
    (
        "replay_and_corrections",
        "Can we replay historical backfills and late corrections safely?",
    ),
    (
        "label_window_lineage",
        "Can every label window be traced back to normalized source records?",
    ),
    (
        "model_backbone_consumption",
        "Can both Logistic Regression and Random Forest consume the same disciplined surveillance label backbone?",
    ),
    (
        "lead_time_period_truth",
        "Can lead-time evaluation reference true reporting periods instead of inferred placeholders?",
    ),
    (
        "honesty_under_weak_inputs",
        "Does the system stay honest when reporting is delayed, partial, corrected, or proxy-only?",
    ),
    (
        "ops_without_frontend",
        "Can ops ingest, inspect, and replay surveillance sources without a bespoke frontend?",
    ),
    (
        "seeded_scenario_discipline",
        "Are seeded surveillance scenarios clearly marked non-production while still exercising the same ETL contracts?",
    ),
]


def _question_text(question_id: str) -> str:
    return dict(PHASE_6_VERIFICATION_QUESTIONS)[question_id]


def _counts_by_field(model, field_name: str) -> dict:
    return {
        item[field_name] or "blank": item["count"]
        for item in model.objects.values(field_name).annotate(count=Count("id")).order_by(field_name)
    }


def _counter_dict(values: Iterable[str]) -> dict:
    return dict(Counter(value for value in values if value))


def _parse_iso_date(value):
    if not value:
        return None
    try:
        from datetime import date

        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _surveillance_record_ref(record: SurveillanceRecord) -> str:
    return f"surveillance_record:{record.id}"


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


def _record_totals() -> dict:
    return {
        "surveillance_records": SurveillanceRecord.objects.count(),
        "label_windows": SurveillanceLabelWindow.objects.count(),
        "label_feature_datasets": FeatureDataset.objects.filter(schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION).count(),
        "surveillance_sources": SurveillanceSource.objects.count(),
        "surveillance_ingestion_runs": SurveillanceIngestionRun.objects.count(),
    }


def _label_window_record_refs() -> dict[int, dict]:
    refs_by_window_id: dict[int, dict] = {}
    for window_id, refs in SurveillanceLabelWindow.objects.values_list("id", "generated_from_record_refs"):
        parsed_ids = []
        malformed_refs = []
        if isinstance(refs, list):
            for ref in refs:
                text = str(ref)
                if not text.startswith("surveillance_record:"):
                    malformed_refs.append(text)
                    continue
                try:
                    parsed_ids.append(int(text.split(":", 1)[1]))
                except ValueError:
                    malformed_refs.append(text)
                    continue
        else:
            malformed_refs.append(str(refs))
        refs_by_window_id[window_id] = {
            "record_ids": parsed_ids,
            "malformed_refs": malformed_refs,
        }
    return refs_by_window_id


def _label_window_record_ref_ids() -> dict[int, list[int]]:
    return {
        window_id: refs["record_ids"]
        for window_id, refs in _label_window_record_refs().items()
    }


def _window_dataset_is_current(
    window: SurveillanceLabelWindow,
    dataset: FeatureDataset | None = None,
) -> bool:
    dataset = dataset if dataset is not None else window.feature_dataset
    if dataset is None:
        return True
    return dataset_is_currently_eligible(dataset)


def _dataset_has_complete_replacement_evidence(dataset: FeatureDataset) -> bool:
    lineage = dataset.lineage_metadata or {}
    replacement_ref = lineage.get("replacement_dataset_ref")
    if not replacement_ref or not lineage.get("affected_window_refs") or not lineage.get(
        "superseded_record_refs"
    ):
        return False
    replacement = FeatureDataset.objects.filter(dataset_ref=replacement_ref).first()
    return bool(
        replacement
        and dataset_is_currently_eligible(replacement)
        and replacement.row_count > 0
        and SurveillanceLabelWindow.objects.filter(feature_dataset=replacement).exists()
    )


def _expected_truth_level_for_records(records: list[SurveillanceRecord]) -> str:
    truth_levels = {record.truth_level for record in records}
    if truth_levels == {SurveillanceTruthLevel.SEEDED_DEMO}:
        return SurveillanceTruthLevel.SEEDED_DEMO
    if SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE in truth_levels:
        return SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE
    if SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE in truth_levels:
        return SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE
    if SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL in truth_levels:
        return SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL
    if SurveillanceTruthLevel.FIELD_SIGNAL_ONLY in truth_levels:
        return SurveillanceTruthLevel.FIELD_SIGNAL_ONLY
    return SurveillanceTruthLevel.FIELD_SIGNAL_ONLY


def _surveillance_dataset_uses_surveillance(dataset: FeatureDataset) -> bool:
    metadata = dataset.lineage_metadata or {}
    return (
        dataset.schema_version == SURVEILLANCE_LABEL_SCHEMA_VERSION
        or metadata.get("surveillance_feature_schema_version") == SURVEILLANCE_FEATURE_SCHEMA_VERSION
        or metadata.get("surveillance_label_dataset_ref")
        or metadata.get("surveillance_feature_coverage")
    )


def _truth_level_question(record_totals: dict) -> dict:
    required_truth_levels = {
        SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
        SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
        SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL,
        SurveillanceTruthLevel.FIELD_SIGNAL_ONLY,
        SurveillanceTruthLevel.SEEDED_DEMO,
    }
    configured_truth_levels = {choice[0] for choice in SurveillanceTruthLevel.choices}
    missing_contract_levels = sorted(required_truth_levels.difference(configured_truth_levels))
    confirmed_records_without_confirmed_case = SurveillanceRecord.objects.filter(
        truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
    ).exclude(case_class=SurveillanceCaseClass.CONFIRMED).count()
    confirmed_case_records_without_confirmed_truth = SurveillanceRecord.objects.filter(
        case_class=SurveillanceCaseClass.CONFIRMED,
    ).exclude(truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE).count()
    proxy_case_records_with_confirmed_truth = SurveillanceRecord.objects.filter(
        case_class=SurveillanceCaseClass.PROXY,
        truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
    ).count()
    records_missing_source_credibility_count = sum(
        1
        for raw_payload in SurveillanceRecord.objects.values_list("raw_payload", flat=True)
        if not (raw_payload or {}).get("source_credibility")
    )
    confirmed_windows_without_confirmed_cases = SurveillanceLabelWindow.objects.filter(
        label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE,
        confirmed_case_count=0,
    ).count()
    non_confirmed_truth_windows_with_confirmed_cases = SurveillanceLabelWindow.objects.filter(
        confirmed_case_count__gt=0,
    ).exclude(label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE).count()
    proxy_truth_with_confirmed_cases = SurveillanceLabelWindow.objects.filter(
        label_truth_level__in=[
            SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL,
            SurveillanceTruthLevel.FIELD_SIGNAL_ONLY,
            SurveillanceTruthLevel.SEEDED_DEMO,
        ],
        confirmed_case_count__gt=0,
    ).count()
    truth_level_misuse_count = (
        confirmed_records_without_confirmed_case
        + confirmed_case_records_without_confirmed_truth
        + proxy_case_records_with_confirmed_truth
        + confirmed_windows_without_confirmed_cases
        + non_confirmed_truth_windows_with_confirmed_cases
        + proxy_truth_with_confirmed_cases
    )

    return {
        "id": "truth_level_separation",
        "question": _question_text("truth_level_separation"),
        "status": _status_from_checks(
            fail=bool(missing_contract_levels),
            warning=truth_level_misuse_count > 0 or records_missing_source_credibility_count > 0,
            no_data=record_totals["surveillance_records"] == 0 and record_totals["label_windows"] == 0,
        ),
        "answer": (
            "Surveillance records and label windows carry explicit truth levels for confirmed, suspected, "
            "proxy diarrheal, field-only, and seeded-demo evidence."
        ),
        "evidence": {
            "configured_truth_levels": sorted(configured_truth_levels),
            "missing_contract_levels": missing_contract_levels,
            "record_truth_level_counts": _counts_by_field(SurveillanceRecord, "truth_level"),
            "label_window_truth_level_counts": _counts_by_field(SurveillanceLabelWindow, "label_truth_level"),
            "truth_assumptions": SURVEILLANCE_LABEL_TRUTH_ASSUMPTIONS,
            "confirmed_records_without_confirmed_case": confirmed_records_without_confirmed_case,
            "confirmed_case_records_without_confirmed_truth": confirmed_case_records_without_confirmed_truth,
            "proxy_case_records_with_confirmed_truth": proxy_case_records_with_confirmed_truth,
            "records_missing_source_credibility_count": records_missing_source_credibility_count,
            "confirmed_windows_without_confirmed_cases": confirmed_windows_without_confirmed_cases,
            "non_confirmed_truth_windows_with_confirmed_cases": non_confirmed_truth_windows_with_confirmed_cases,
            "proxy_truth_windows_with_confirmed_cases": proxy_truth_with_confirmed_cases,
        },
        "gaps": [
            gap
            for gap, present in [
                ("truth_level_contract_incomplete", bool(missing_contract_levels)),
                ("truth_level_semantic_misuse", truth_level_misuse_count > 0),
                ("source_credibility_missing_from_canonical_records", records_missing_source_credibility_count > 0),
            ]
            if present
        ],
    }


def _replay_and_correction_question(record_totals: dict) -> dict:
    command_available = _management_command_exists("ingest_surveillance")
    reconciliation_command_available = _management_command_exists("reconcile_surveillance_label_lineage")
    replay_run_count = SurveillanceIngestionRun.objects.filter(
        execution_mode=SurveillanceIngestionRun.EXECUTION_REPLAY,
    ).count()
    replayable_run_count = SurveillanceIngestionRun.objects.exclude(input_ref="").count()
    backfill_run_count = SurveillanceIngestionRun.objects.filter(
        correction_mode=SurveillanceIngestionRun.CORRECTION_BACKFILL,
    ).count()
    amendment_run_count = SurveillanceIngestionRun.objects.filter(
        correction_mode=SurveillanceIngestionRun.CORRECTION_AMENDMENT,
    ).count()
    amendment_without_reason_count = SurveillanceIngestionRun.objects.filter(
        correction_mode=SurveillanceIngestionRun.CORRECTION_AMENDMENT,
        correction_reason="",
    ).count()
    replay_runs_missing_parent_count = SurveillanceIngestionRun.objects.filter(
        execution_mode=SurveillanceIngestionRun.EXECUTION_REPLAY,
        replay_of__isnull=True,
    ).count()
    non_replay_runs_with_parent_count = SurveillanceIngestionRun.objects.exclude(
        execution_mode=SurveillanceIngestionRun.EXECUTION_REPLAY,
    ).filter(replay_of__isnull=False).count()
    runs_missing_input_ref_count = SurveillanceIngestionRun.objects.filter(input_ref="").count()
    correction_runs_missing_period_bounds_count = SurveillanceIngestionRun.objects.filter(
        correction_mode__in=[
            SurveillanceIngestionRun.CORRECTION_AMENDMENT,
            SurveillanceIngestionRun.CORRECTION_BACKFILL,
        ],
    ).filter(Q(reporting_period_start__isnull=True) | Q(reporting_period_end__isnull=True)).count()
    replay_records_not_diagnostic_count = SurveillanceRecord.objects.filter(
        ingestion_run__execution_mode=SurveillanceIngestionRun.EXECUTION_REPLAY,
    ).exclude(freshness_state=SurveillanceFreshnessState.REPLAY_DIAGNOSTIC).count()
    replay_record_ids_used_by_labels = set(
        SurveillanceRecord.objects.filter(
            freshness_state=SurveillanceFreshnessState.REPLAY_DIAGNOSTIC,
        ).values_list("id", flat=True)
    )
    window_record_refs = _label_window_record_ref_ids()
    used_record_ids = {
        record_id
        for ref_ids in window_record_refs.values()
        for record_id in ref_ids
    }
    superseded_record_ids = {
        record_id
        for record_id, raw_payload in SurveillanceRecord.objects.values_list("id", "raw_payload")
        if (raw_payload or {}).get("superseded_by_record_ref")
    }
    superseded_by_record_refs = {
        (raw_payload or {}).get("superseded_by_record_ref")
        for raw_payload in SurveillanceRecord.objects.values_list("raw_payload", flat=True)
        if (raw_payload or {}).get("superseded_by_record_ref")
    }
    superseding_records = list(SurveillanceRecord.objects.exclude(supersedes_record_ref="").order_by("id"))
    unresolved_supersedes_ref_count = sum(
        1 for record in superseding_records if _surveillance_record_ref(record) not in superseded_by_record_refs
    )
    amendment_records_without_supersedes_ref_count = SurveillanceRecord.objects.filter(
        ingestion_run__correction_mode=SurveillanceIngestionRun.CORRECTION_AMENDMENT,
        supersedes_record_ref="",
    ).count()
    label_windows_with_superseded_records = list(
        SurveillanceLabelWindow.objects.only(
            "id",
            "feature_dataset_id",
            "generated_from_record_refs",
        ).order_by("id")
    )
    label_datasets_by_id = FeatureDataset.objects.in_bulk(
        {window.feature_dataset_id for window in label_windows_with_superseded_records if window.feature_dataset_id}
    )
    active_record_ids_used_by_labels: set[int] = set()
    retired_record_ids_used_by_labels: set[int] = set()
    retired_historical_window_ids: list[int] = []
    for window in label_windows_with_superseded_records:
        overlap = window_record_refs.get(window.id, [])
        overlap = set(overlap).intersection(superseded_record_ids)
        if not overlap:
            continue
        if _window_dataset_is_current(window, label_datasets_by_id.get(window.feature_dataset_id)):
            active_record_ids_used_by_labels.update(overlap)
        else:
            retired_record_ids_used_by_labels.update(overlap)
            retired_historical_window_ids.append(window.id)
    superseded_dataset_refs = {
        dataset.dataset_ref
        for dataset in FeatureDataset.objects.filter(schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION)
        if dataset_is_superseded(dataset)
    }
    superseded_datasets_lacking_replacement_evidence = [
        dataset.id
        for dataset in FeatureDataset.objects.filter(
            schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION,
        ).order_by("id")
        if dataset_is_superseded(dataset)
        and any(
            window.feature_dataset_id == dataset.id
            and set(window_record_refs.get(window.id, [])).intersection(superseded_record_ids)
            for window in label_windows_with_superseded_records
        )
        and not _dataset_has_complete_replacement_evidence(dataset)
    ]
    current_model_evaluation_refs = []
    for model_run in ModelRun.objects.order_by("id"):
        current_refs = current_model_run_dataset_refs(model_run)
        affected_refs = sorted(current_refs.intersection(superseded_dataset_refs))
        if affected_refs:
            current_model_evaluation_refs.append(
                {
                    "model_run_id": model_run.id,
                    "model_version": model_run.model_version,
                    "dataset_refs": affected_refs,
                }
            )
    superseded_records_used_in_labels_count = len(active_record_ids_used_by_labels)
    replay_records_used_in_labels_count = len(replay_record_ids_used_by_labels.intersection(used_record_ids))
    replay_label_regeneration_not_skipped_count = sum(
        1
        for run in SurveillanceIngestionRun.objects.filter(
            execution_mode=SurveillanceIngestionRun.EXECUTION_REPLAY,
        )
        if (run.results or {}).get("downstream_label_regeneration", {}).get("regenerated") is True
    )
    runs_with_unknown_columns = [
        run_id
        for run_id, results in SurveillanceIngestionRun.objects.values_list("id", "results")
        if (results or {}).get("unknown_columns")
    ]
    replay_parent_metadata_mismatch_count = sum(
        1
        for run in SurveillanceIngestionRun.objects.filter(
            execution_mode=SurveillanceIngestionRun.EXECUTION_REPLAY,
            replay_of__isnull=False,
        ).select_related("replay_of")
        if (
            run.source_name != run.replay_of.source_name
            or run.source_type != run.replay_of.source_type
            or run.input_ref == ""
        )
    )

    return {
        "id": "replay_and_corrections",
        "question": _question_text("replay_and_corrections"),
        "status": _status_from_checks(
            fail=(
                not command_available
                or not reconciliation_command_available
                or replay_runs_missing_parent_count > 0
                or non_replay_runs_with_parent_count > 0
                or replay_parent_metadata_mismatch_count > 0
                or replay_records_not_diagnostic_count > 0
                or replay_records_used_in_labels_count > 0
                or superseded_records_used_in_labels_count > 0
                or superseded_datasets_lacking_replacement_evidence
                or current_model_evaluation_refs
                or unresolved_supersedes_ref_count > 0
                or replay_label_regeneration_not_skipped_count > 0
            ),
            warning=(
                amendment_without_reason_count > 0
                or amendment_records_without_supersedes_ref_count > 0
                or runs_missing_input_ref_count > 0
                or correction_runs_missing_period_bounds_count > 0
                or bool(runs_with_unknown_columns)
            ),
            no_data=record_totals["surveillance_ingestion_runs"] == 0,
        ),
        "answer": (
            "Ingestion runs preserve replay, backfill, amendment, trusted-push, source-file, and feed-policy "
            "metadata; replay records are diagnostic and excluded from label generation."
        ),
        "evidence": {
            "ingestion_run_count": record_totals["surveillance_ingestion_runs"],
            "replayable_run_count": replayable_run_count,
            "replay_run_count": replay_run_count,
            "backfill_run_count": backfill_run_count,
            "amendment_run_count": amendment_run_count,
            "amendment_without_reason_count": amendment_without_reason_count,
            "replay_runs_missing_parent_count": replay_runs_missing_parent_count,
            "non_replay_runs_with_parent_count": non_replay_runs_with_parent_count,
            "runs_missing_input_ref_count": runs_missing_input_ref_count,
            "correction_runs_missing_period_bounds_count": correction_runs_missing_period_bounds_count,
            "replay_parent_metadata_mismatch_count": replay_parent_metadata_mismatch_count,
            "amendment_records_without_supersedes_ref_count": amendment_records_without_supersedes_ref_count,
            "records_with_supersedes_ref_count": len(superseding_records),
            "unresolved_supersedes_ref_count": unresolved_supersedes_ref_count,
            "superseded_record_count": len(superseded_record_ids),
            "superseded_records_used_in_label_windows_count": superseded_records_used_in_labels_count,
            "active_windows_referencing_superseded_records_count": len(active_record_ids_used_by_labels),
            "retired_historical_windows_containing_corrected_lineage_count": len(retired_historical_window_ids),
            "retired_historical_window_ids": retired_historical_window_ids[:25],
            "superseded_datasets_lacking_replacement_evidence": superseded_datasets_lacking_replacement_evidence[:25],
            "current_model_evaluations_referencing_superseded_datasets": current_model_evaluation_refs[:25],
            "replay_records_not_diagnostic_count": replay_records_not_diagnostic_count,
            "replay_records_used_in_label_windows_count": replay_records_used_in_labels_count,
            "replay_label_regeneration_not_skipped_count": replay_label_regeneration_not_skipped_count,
            "runs_with_unknown_source_columns": runs_with_unknown_columns[:25],
            "correction_modes": [choice[0] for choice in SurveillanceIngestionRun.CORRECTION_MODE_CHOICES],
            "execution_modes": [choice[0] for choice in SurveillanceIngestionRun.EXECUTION_MODE_CHOICES],
            "excluded_label_freshness_states": sorted(EXCLUDED_LABEL_FRESHNESS_STATES),
            "management_command_available": command_available,
            "reconciliation_management_command_available": reconciliation_command_available,
            "replay_command_template": "python manage.py ingest_surveillance --replay-of <run_id>",
        },
        "gaps": [
            gap
            for gap, present in [
                ("ingest_surveillance_command_missing", not command_available),
                ("reconciliation_command_missing", not reconciliation_command_available),
                ("amendment_without_reason", amendment_without_reason_count > 0),
                ("replay_run_missing_parent", replay_runs_missing_parent_count > 0),
                ("non_replay_run_has_replay_parent", non_replay_runs_with_parent_count > 0),
                ("ingestion_runs_missing_input_ref", runs_missing_input_ref_count > 0),
                ("correction_runs_missing_reporting_period_bounds", correction_runs_missing_period_bounds_count > 0),
                ("replay_parent_metadata_mismatch", replay_parent_metadata_mismatch_count > 0),
                ("amendment_records_without_supersedes_ref", amendment_records_without_supersedes_ref_count > 0),
                ("supersedes_record_refs_unresolved", unresolved_supersedes_ref_count > 0),
                ("superseded_records_used_in_label_windows", superseded_records_used_in_labels_count > 0),
                (
                    "superseded_datasets_lack_replacement_evidence",
                    bool(superseded_datasets_lacking_replacement_evidence),
                ),
                (
                    "current_model_evaluations_reference_superseded_datasets",
                    bool(current_model_evaluation_refs),
                ),
                ("replay_records_not_marked_diagnostic", replay_records_not_diagnostic_count > 0),
                ("replay_records_used_in_label_windows", replay_records_used_in_labels_count > 0),
                ("replay_label_regeneration_not_skipped", replay_label_regeneration_not_skipped_count > 0),
                ("source_files_with_unknown_columns", bool(runs_with_unknown_columns)),
            ]
            if present
        ],
    }


def _label_window_lineage_question(record_totals: dict) -> dict:
    records_by_id = {
        record.id: record
        for record in SurveillanceRecord.objects.select_related("ward").order_by("id")
    }
    refs_by_window_id = _label_window_record_refs()
    windows_missing_refs = []
    windows_with_missing_records = []
    windows_with_ref_count_mismatch = []
    windows_with_duplicate_refs = []
    windows_with_malformed_refs = []
    windows_with_cases_but_no_sources = []
    windows_with_refs_outside_ward_or_window = []
    windows_with_case_count_mismatch = []
    windows_with_truth_level_mismatch = []
    windows_with_superseded_record_refs = []
    retired_historical_windows_with_corrected_lineage = []
    retired_historical_windows_missing_replacement_evidence = []
    replacement_evidence_by_dataset_id = {}
    windows_missing_source_credibility_counts = []
    windows_missing_dataset_link = []
    windows_with_dataset_ref_mismatch = []

    label_windows = list(
        SurveillanceLabelWindow.objects.only(
            "id",
            "ward_id",
            "feature_dataset_id",
            "schema_version",
            "dataset_ref",
            "label_window_start",
            "label_window_end",
            "suspected_case_count",
            "confirmed_case_count",
            "proxy_case_count",
            "outbreak_label",
            "label_truth_level",
            "source_coverage_summary",
            "generated_from_record_refs",
            "source_record_count",
        ).order_by("id")
    )
    label_datasets_by_id = FeatureDataset.objects.in_bulk(
        {window.feature_dataset_id for window in label_windows if window.feature_dataset_id}
    )

    for window in label_windows:
        dataset = label_datasets_by_id.get(window.feature_dataset_id)
        ref_payload = refs_by_window_id.get(window.id, {"record_ids": [], "malformed_refs": []})
        refs = ref_payload["record_ids"]
        unique_ref_ids = set(refs)
        existing_ref_records = [
            records_by_id[record_id]
            for record_id in unique_ref_ids
            if record_id in records_by_id
        ]
        case_count_total = window.suspected_case_count + window.confirmed_case_count + window.proxy_case_count
        if ref_payload["malformed_refs"]:
            windows_with_malformed_refs.append(window.id)
        if window.source_record_count > 0 and not refs:
            windows_missing_refs.append(window.id)
        if case_count_total > 0 and not refs:
            windows_with_cases_but_no_sources.append(window.id)
        if any(record_id not in records_by_id for record_id in refs):
            windows_with_missing_records.append(window.id)
        if len(refs) != len(unique_ref_ids):
            windows_with_duplicate_refs.append(window.id)
        if window.source_record_count != len(unique_ref_ids):
            windows_with_ref_count_mismatch.append(window.id)
        if any(
            record.ward_id != window.ward_id
            or record.reporting_period_start > window.label_window_end
            or record.reporting_period_end < window.label_window_start
            for record in existing_ref_records
        ):
            windows_with_refs_outside_ward_or_window.append(window.id)
        if any((record.raw_payload or {}).get("superseded_by_record_ref") for record in existing_ref_records):
            if _window_dataset_is_current(window, dataset):
                windows_with_superseded_record_refs.append(window.id)
            else:
                dataset_id = window.feature_dataset_id
                if dataset_id not in replacement_evidence_by_dataset_id:
                    replacement_evidence_by_dataset_id[dataset_id] = bool(
                        dataset and _dataset_has_complete_replacement_evidence(dataset)
                    )
                if replacement_evidence_by_dataset_id[dataset_id]:
                    retired_historical_windows_with_corrected_lineage.append(window.id)
                else:
                    retired_historical_windows_missing_replacement_evidence.append(window.id)
                    windows_with_superseded_record_refs.append(window.id)
        if window.source_record_count > 0 and not (window.source_coverage_summary or {}).get(
            "source_credibility_counts"
        ):
            windows_missing_source_credibility_counts.append(window.id)
        if existing_ref_records:
            expected_counts = {
                SurveillanceCaseClass.SUSPECTED: sum(
                    record.count_value
                    for record in existing_ref_records
                    if record.case_class == SurveillanceCaseClass.SUSPECTED
                ),
                SurveillanceCaseClass.CONFIRMED: sum(
                    record.count_value
                    for record in existing_ref_records
                    if record.case_class == SurveillanceCaseClass.CONFIRMED
                ),
                SurveillanceCaseClass.PROXY: sum(
                    record.count_value
                    for record in existing_ref_records
                    if record.case_class == SurveillanceCaseClass.PROXY
                ),
            }
            if (
                expected_counts[SurveillanceCaseClass.SUSPECTED] != window.suspected_case_count
                or expected_counts[SurveillanceCaseClass.CONFIRMED] != window.confirmed_case_count
                or expected_counts[SurveillanceCaseClass.PROXY] != window.proxy_case_count
            ):
                windows_with_case_count_mismatch.append(window.id)
            if _expected_truth_level_for_records(existing_ref_records) != window.label_truth_level:
                windows_with_truth_level_mismatch.append(window.id)
        if not window.dataset_ref or window.feature_dataset_id is None:
            windows_missing_dataset_link.append(window.id)
        elif dataset and window.dataset_ref != dataset.dataset_ref:
            windows_with_dataset_ref_mismatch.append(window.id)

    label_datasets_with_row_count_mismatch = []
    label_datasets_without_windows = []
    label_rows_missing_or_invalid_window_ref = []
    for dataset in FeatureDataset.objects.filter(schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION).order_by("id"):
        dataset_rows = list(FeatureDatasetRow.objects.filter(dataset=dataset).order_by("id"))
        dataset_window_ids = set(
            SurveillanceLabelWindow.objects.filter(feature_dataset=dataset).values_list("id", flat=True)
        )
        if not dataset_window_ids:
            label_datasets_without_windows.append(dataset.id)
        if dataset.row_count != len(dataset_rows) or len(dataset_rows) != len(dataset_window_ids):
            label_datasets_with_row_count_mismatch.append(dataset.id)
        for row in dataset_rows:
            label_window_id = (row.feature_values or {}).get("label_window_id")
            if label_window_id not in dataset_window_ids:
                label_rows_missing_or_invalid_window_ref.append(row.id)

    failure_count = (
        len(windows_missing_refs)
        + len(windows_with_missing_records)
        + len(windows_with_ref_count_mismatch)
        + len(windows_with_duplicate_refs)
        + len(windows_with_malformed_refs)
        + len(windows_with_cases_but_no_sources)
        + len(windows_with_refs_outside_ward_or_window)
        + len(windows_with_case_count_mismatch)
        + len(windows_with_truth_level_mismatch)
        + len(windows_with_superseded_record_refs)
        + len(windows_missing_source_credibility_counts)
        + len(windows_with_dataset_ref_mismatch)
        + len(label_datasets_with_row_count_mismatch)
        + len(label_datasets_without_windows)
        + len(label_rows_missing_or_invalid_window_ref)
    )

    return {
        "id": "label_window_lineage",
        "question": _question_text("label_window_lineage"),
        "status": _status_from_checks(
            fail=failure_count > 0,
            warning=bool(windows_missing_dataset_link),
            no_data=record_totals["label_windows"] == 0,
        ),
        "answer": (
            "Generated label windows retain record refs and source coverage summaries back to canonical "
            "SurveillanceRecord rows and their FeatureDataset snapshots."
        ),
        "evidence": {
            "label_window_count": record_totals["label_windows"],
            "label_feature_dataset_count": record_totals["label_feature_datasets"],
            "windows_missing_generated_record_refs": windows_missing_refs[:25],
            "windows_with_nonexistent_record_refs": windows_with_missing_records[:25],
            "windows_with_source_record_count_mismatch": windows_with_ref_count_mismatch[:25],
            "windows_with_duplicate_record_refs": windows_with_duplicate_refs[:25],
            "windows_with_malformed_record_refs": windows_with_malformed_refs[:25],
            "windows_with_cases_but_no_sources": windows_with_cases_but_no_sources[:25],
            "windows_with_refs_outside_ward_or_window": windows_with_refs_outside_ward_or_window[:25],
            "windows_with_case_count_mismatch": windows_with_case_count_mismatch[:25],
            "windows_with_truth_level_mismatch": windows_with_truth_level_mismatch[:25],
            "windows_with_superseded_record_refs": windows_with_superseded_record_refs[:25],
            "active_windows_referencing_superseded_records": windows_with_superseded_record_refs[:25],
            "retired_historical_windows_containing_corrected_lineage": retired_historical_windows_with_corrected_lineage[:25],
            "retired_historical_windows_missing_replacement_evidence": retired_historical_windows_missing_replacement_evidence[:25],
            "windows_missing_source_credibility_counts": windows_missing_source_credibility_counts[:25],
            "windows_missing_dataset_ref_or_feature_dataset": windows_missing_dataset_link[:25],
            "windows_with_dataset_ref_mismatch": windows_with_dataset_ref_mismatch[:25],
            "label_datasets_with_row_count_mismatch": label_datasets_with_row_count_mismatch[:25],
            "label_datasets_without_windows": label_datasets_without_windows[:25],
            "label_rows_missing_or_invalid_window_ref": label_rows_missing_or_invalid_window_ref[:25],
            "source_record_count_total": sum(
                SurveillanceLabelWindow.objects.values_list("source_record_count", flat=True)
            ),
        },
        "gaps": [
            gap
            for gap, present in [
                ("label_windows_missing_record_refs", bool(windows_missing_refs)),
                ("label_windows_reference_missing_records", bool(windows_with_missing_records)),
                ("label_window_source_record_count_mismatch", bool(windows_with_ref_count_mismatch)),
                ("label_windows_have_duplicate_record_refs", bool(windows_with_duplicate_refs)),
                ("label_windows_have_malformed_record_refs", bool(windows_with_malformed_refs)),
                ("label_windows_have_cases_but_no_source_refs", bool(windows_with_cases_but_no_sources)),
                ("label_windows_reference_records_outside_ward_or_window", bool(windows_with_refs_outside_ward_or_window)),
                ("label_window_counts_do_not_match_referenced_records", bool(windows_with_case_count_mismatch)),
                ("label_window_truth_level_does_not_match_referenced_records", bool(windows_with_truth_level_mismatch)),
                ("label_windows_reference_superseded_records", bool(windows_with_superseded_record_refs)),
                (
                    "retired_historical_lineage_missing_replacement_evidence",
                    bool(retired_historical_windows_missing_replacement_evidence),
                ),
                ("label_windows_missing_source_credibility_counts", bool(windows_missing_source_credibility_counts)),
                ("label_windows_missing_dataset_linkage", bool(windows_missing_dataset_link)),
                ("label_windows_dataset_ref_mismatch", bool(windows_with_dataset_ref_mismatch)),
                ("label_dataset_row_count_mismatch", bool(label_datasets_with_row_count_mismatch)),
                ("label_datasets_without_windows", bool(label_datasets_without_windows)),
                ("label_rows_missing_or_invalid_window_ref", bool(label_rows_missing_or_invalid_window_ref)),
            ]
            if present
        ],
    }


def _model_backbone_question(record_totals: dict) -> dict:
    required_algorithms = {ALGORITHM_LOGISTIC_REGRESSION, ALGORITHM_RANDOM_FOREST}
    runnable_algorithms = {
        algorithm
        for algorithm, metadata in MODEL_CATALOG.items()
        if metadata.get("runnable")
    }
    missing_runnable_algorithms = sorted(required_algorithms.difference(runnable_algorithms))
    command_states = {
        "run_risk_model": _management_command_exists("run_risk_model"),
        "run_random_forest_benchmark": _management_command_exists("run_random_forest_benchmark"),
    }
    algorithm_name_to_id = {
        MODEL_CATALOG[ALGORITHM_LOGISTIC_REGRESSION]["run_name"]: ALGORITHM_LOGISTIC_REGRESSION,
        MODEL_CATALOG[ALGORITHM_RANDOM_FOREST]["run_name"]: ALGORITHM_RANDOM_FOREST,
    }
    model_run_counts = Counter()
    model_runs_missing_surveillance_metadata = []
    model_runs_missing_training_dataset = []
    model_runs_reference_missing_label_dataset = []
    model_runs_with_training_dataset_ref_mismatch = []
    model_runs_with_label_validation_ref_mismatch = []
    model_runs_missing_truth_gate = []
    label_dataset_refs = set(
        FeatureDataset.objects.filter(schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION).values_list("dataset_ref", flat=True)
    )
    label_dataset_ids = set(
        FeatureDataset.objects.filter(schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION).values_list("id", flat=True)
    )
    label_refs_by_algorithm = {algorithm: set() for algorithm in required_algorithms}
    for run in ModelRun.objects.filter(algorithm_name__in=algorithm_name_to_id.keys()).select_related(
        "training_feature_dataset",
    ).order_by("id"):
        algorithm = algorithm_name_to_id[run.algorithm_name]
        model_run_counts[algorithm] += 1
        metadata = run.metadata or {}
        metrics = run.evaluation_metrics or {}
        label_dataset_ref = metadata.get("surveillance_label_dataset_ref")
        label_dataset_id = metadata.get("surveillance_label_feature_dataset_id")
        validation = metrics.get("surveillance_lead_time_validation") or metadata.get("surveillance_lead_time_validation") or {}
        if not isinstance(validation, dict):
            validation = {}
        if label_dataset_ref:
            label_refs_by_algorithm[algorithm].add(label_dataset_ref)
        if not metadata.get("surveillance_label_usage") or not metrics.get("surveillance_lead_time_validation"):
            model_runs_missing_surveillance_metadata.append(run.id)
        if (
            metadata.get("surveillance_label_usage") not in {None, "not_available"}
            and not metadata.get("surveillance_label_truth_gate")
        ):
            model_runs_missing_truth_gate.append(run.id)
        if label_dataset_ref and label_dataset_ref not in label_dataset_refs:
            model_runs_reference_missing_label_dataset.append(run.id)
        if label_dataset_id and label_dataset_id not in label_dataset_ids:
            model_runs_reference_missing_label_dataset.append(run.id)
        if (
            label_dataset_ref
            and validation.get("label_dataset_ref")
            and validation.get("label_dataset_ref") != label_dataset_ref
        ):
            model_runs_with_label_validation_ref_mismatch.append(run.id)
        if (
            run.training_feature_dataset
            and run.training_dataset_ref
            and run.training_feature_dataset.dataset_ref != run.training_dataset_ref
        ):
            model_runs_with_training_dataset_ref_mismatch.append(run.id)
        if not run.training_dataset_ref and run.training_feature_dataset_id is None:
            model_runs_missing_training_dataset.append(run.id)
    missing_observed_algorithms = sorted(
        algorithm
        for algorithm in required_algorithms
        if record_totals["label_feature_datasets"] > 0 and model_run_counts[algorithm] == 0
    )
    shared_label_dataset_refs = sorted(
        label_refs_by_algorithm[ALGORITHM_LOGISTIC_REGRESSION].intersection(
            label_refs_by_algorithm[ALGORITHM_RANDOM_FOREST],
        )
    )
    both_algorithms_observed = all(model_run_counts[algorithm] > 0 for algorithm in required_algorithms)
    no_shared_label_backbone_count = 1 if both_algorithms_observed and not shared_label_dataset_refs else 0

    return {
        "id": "model_backbone_consumption",
        "question": _question_text("model_backbone_consumption"),
        "status": _status_from_checks(
            fail=(
                bool(missing_runnable_algorithms)
                or not all(command_states.values())
                or bool(model_runs_reference_missing_label_dataset)
                or bool(model_runs_with_label_validation_ref_mismatch)
            ),
            warning=bool(
                missing_observed_algorithms
                or no_shared_label_backbone_count
                or model_runs_missing_surveillance_metadata
                or model_runs_missing_training_dataset
                or model_runs_with_training_dataset_ref_mismatch
                or model_runs_missing_truth_gate
            ),
            no_data=record_totals["label_feature_datasets"] == 0 and sum(model_run_counts.values()) == 0,
        ),
        "answer": (
            "The logistic-regression live path and Random Forest benchmark path share the same training dataset "
            "builder and can carry surveillance label lineage and lead-time validation metadata."
        ),
        "evidence": {
            "required_algorithms": sorted(required_algorithms),
            "runnable_algorithms": sorted(runnable_algorithms),
            "missing_runnable_algorithms": missing_runnable_algorithms,
            "management_commands": command_states,
            "model_run_counts_by_algorithm": dict(model_run_counts),
            "missing_observed_algorithms": missing_observed_algorithms,
            "shared_label_dataset_refs_by_required_algorithms": shared_label_dataset_refs,
            "model_runs_missing_surveillance_metadata": model_runs_missing_surveillance_metadata[:25],
            "model_runs_missing_training_dataset": model_runs_missing_training_dataset[:25],
            "model_runs_reference_missing_label_dataset": model_runs_reference_missing_label_dataset[:25],
            "model_runs_with_training_dataset_ref_mismatch": model_runs_with_training_dataset_ref_mismatch[:25],
            "model_runs_with_label_validation_ref_mismatch": model_runs_with_label_validation_ref_mismatch[:25],
            "model_runs_missing_surveillance_truth_gate": model_runs_missing_truth_gate[:25],
            "label_feature_dataset_count": record_totals["label_feature_datasets"],
        },
        "gaps": [
            gap
            for gap, present in [
                ("required_model_algorithm_not_runnable", bool(missing_runnable_algorithms)),
                ("risk_model_management_command_missing", not command_states["run_risk_model"]),
                ("random_forest_management_command_missing", not command_states["run_random_forest_benchmark"]),
                ("required_model_algorithm_not_observed_with_label_dataset", bool(missing_observed_algorithms)),
                ("required_model_algorithms_do_not_share_label_backbone", bool(no_shared_label_backbone_count)),
                ("model_runs_missing_surveillance_metadata", bool(model_runs_missing_surveillance_metadata)),
                ("model_runs_missing_training_dataset", bool(model_runs_missing_training_dataset)),
                ("model_runs_reference_missing_label_dataset", bool(model_runs_reference_missing_label_dataset)),
                ("model_training_dataset_ref_mismatch", bool(model_runs_with_training_dataset_ref_mismatch)),
                ("model_label_validation_ref_mismatch", bool(model_runs_with_label_validation_ref_mismatch)),
                ("model_runs_missing_surveillance_truth_gate", bool(model_runs_missing_truth_gate)),
            ]
            if present
        ],
    }


def _lead_time_period_question(record_totals: dict) -> dict:
    accepted_validation_modes = {
        "retrospective_surveillance_label_window_alignment",
        "future_7_to_14_day_surveillance_label_window_alignment",
    }
    accepted_ready_statuses = {
        "ready_for_lead_time_review",
        "ready_for_7_to_14_day_evaluation",
        "evaluated",
    }
    label_datasets_missing_bounds = []
    label_datasets_invalid_bounds = []
    label_datasets_nonpositive_window_config = []
    label_datasets_with_windows_outside_bounds = []
    label_datasets_with_oversized_windows = []
    label_datasets_with_empty_source_windows = []
    for dataset in FeatureDataset.objects.filter(schema_version=SURVEILLANCE_LABEL_SCHEMA_VERSION).order_by("id"):
        metadata = dataset.lineage_metadata or {}
        coverage = metadata.get("coverage", {})
        is_lead_time_label_dataset = metadata.get("generation_mode") == SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE
        start_date = _parse_iso_date(metadata.get("start_date"))
        end_date = _parse_iso_date(metadata.get("end_date"))
        window_days = metadata.get("window_days")
        step_days = metadata.get("step_days")
        if not metadata.get("start_date") or not metadata.get("end_date") or not metadata.get("window_days"):
            label_datasets_missing_bounds.append(dataset.id)
        if start_date and end_date and start_date > end_date:
            label_datasets_invalid_bounds.append(dataset.id)
        if not isinstance(window_days, int) or window_days <= 0 or not isinstance(step_days, int) or step_days <= 0:
            label_datasets_nonpositive_window_config.append(dataset.id)
        for window in SurveillanceLabelWindow.objects.filter(feature_dataset=dataset).order_by("id"):
            if (
                start_date
                and end_date
                and (window.label_window_start < start_date or window.label_window_end > end_date)
            ):
                label_datasets_with_windows_outside_bounds.append(dataset.id)
                break
            actual_window_days = (window.label_window_end - window.label_window_start).days + 1
            if isinstance(window_days, int) and actual_window_days > window_days:
                label_datasets_with_oversized_windows.append(dataset.id)
                break
        if coverage.get("windows_without_source_records", 0) and not is_lead_time_label_dataset:
            label_datasets_with_empty_source_windows.append(dataset.id)

    model_runs_missing_lead_time = []
    model_runs_with_placeholder_mode = []
    model_runs_with_non_ready_lead_time = []
    model_runs_with_label_ref_mismatch = []
    for run in ModelRun.objects.order_by("id"):
        metadata = run.metadata or {}
        metrics = run.evaluation_metrics or {}
        if not metadata.get("surveillance_label_dataset_ref"):
            continue
        validation = metrics.get("surveillance_lead_time_validation") or metadata.get("surveillance_lead_time_validation")
        if not isinstance(validation, dict) or not validation:
            model_runs_missing_lead_time.append(run.id)
            continue
        if validation.get("label_dataset_ref") and validation.get("label_dataset_ref") != metadata.get("surveillance_label_dataset_ref"):
            model_runs_with_label_ref_mismatch.append(run.id)
        if validation.get("validation_mode") not in accepted_validation_modes:
            model_runs_with_placeholder_mode.append(run.id)
        if validation.get("status") not in accepted_ready_statuses:
            model_runs_with_non_ready_lead_time.append(run.id)

    return {
        "id": "lead_time_period_truth",
        "question": _question_text("lead_time_period_truth"),
        "status": _status_from_checks(
            fail=bool(
                label_datasets_missing_bounds
                or label_datasets_invalid_bounds
                or label_datasets_nonpositive_window_config
                or label_datasets_with_windows_outside_bounds
                or label_datasets_with_oversized_windows
                or model_runs_missing_lead_time
                or model_runs_with_label_ref_mismatch
            ),
            warning=bool(
                label_datasets_with_empty_source_windows
                or model_runs_with_placeholder_mode
                or model_runs_with_non_ready_lead_time
            ),
            no_data=record_totals["label_windows"] == 0 and record_totals["label_feature_datasets"] == 0,
        ),
        "answer": (
            "Surveillance label datasets store real start/end dates, Phase 3 datasets carry prediction-date "
            "7-to-14 day windows, and model runs record lead-time validation metadata."
        ),
        "evidence": {
            "label_feature_dataset_count": record_totals["label_feature_datasets"],
            "label_window_count": record_totals["label_windows"],
            "label_datasets_missing_period_bounds": label_datasets_missing_bounds[:25],
            "label_datasets_invalid_period_bounds": label_datasets_invalid_bounds[:25],
            "label_datasets_nonpositive_window_config": label_datasets_nonpositive_window_config[:25],
            "label_datasets_with_windows_outside_bounds": label_datasets_with_windows_outside_bounds[:25],
            "label_datasets_with_oversized_windows": label_datasets_with_oversized_windows[:25],
            "label_datasets_with_empty_source_windows": label_datasets_with_empty_source_windows[:25],
            "model_runs_missing_lead_time_validation": model_runs_missing_lead_time[:25],
            "model_runs_with_nonstandard_validation_mode": model_runs_with_placeholder_mode[:25],
            "model_runs_with_non_ready_lead_time_validation": model_runs_with_non_ready_lead_time[:25],
            "model_runs_with_label_dataset_ref_mismatch": model_runs_with_label_ref_mismatch[:25],
        },
        "gaps": [
            gap
            for gap, present in [
                ("label_datasets_missing_period_bounds", bool(label_datasets_missing_bounds)),
                ("label_datasets_invalid_period_bounds", bool(label_datasets_invalid_bounds)),
                ("label_datasets_nonpositive_window_config", bool(label_datasets_nonpositive_window_config)),
                ("label_datasets_have_windows_outside_period_bounds", bool(label_datasets_with_windows_outside_bounds)),
                ("label_datasets_have_windows_larger_than_configured_window_days", bool(label_datasets_with_oversized_windows)),
                ("model_runs_missing_lead_time_validation", bool(model_runs_missing_lead_time)),
                ("lead_time_label_dataset_ref_mismatch", bool(model_runs_with_label_ref_mismatch)),
                ("label_datasets_include_empty_assumed_zero_windows", bool(label_datasets_with_empty_source_windows)),
                ("lead_time_validation_not_using_label_window_alignment", bool(model_runs_with_placeholder_mode)),
                ("lead_time_validation_not_ready", bool(model_runs_with_non_ready_lead_time)),
            ]
            if present
        ],
    }


def _honesty_question(record_totals: dict) -> dict:
    freshness_counts = _counts_by_field(SurveillanceRecord, "freshness_state")
    partial_or_failed_runs = SurveillanceIngestionRun.objects.filter(
        status__in=[
            SurveillanceIngestionRun.STATUS_PARTIAL,
            SurveillanceIngestionRun.STATUS_FAILED,
        ]
    ).count()
    unknown_freshness_record_count = SurveillanceRecord.objects.filter(
        freshness_state=SurveillanceFreshnessState.UNKNOWN,
    ).count()
    rejected_row_count = sum(SurveillanceIngestionRun.objects.values_list("records_rejected", flat=True))
    proxy_only_label_windows = SurveillanceLabelWindow.objects.filter(
        label_truth_level__in=[
            SurveillanceTruthLevel.PROXY_DIARRHEAL_SIGNAL,
            SurveillanceTruthLevel.FIELD_SIGNAL_ONLY,
            SurveillanceTruthLevel.SEEDED_DEMO,
        ],
        confirmed_case_count=0,
    ).count()
    datasets_missing_truth_gate = []
    proxy_allowed_datasets = []
    rows_allowing_proxy_only_as_confirmed = []
    for dataset in FeatureDataset.objects.order_by("id"):
        metadata = dataset.lineage_metadata or {}
        surveillance_gate = (
            metadata.get("surveillance_truth_gate")
            or metadata.get("surveillance_label_truth_gate")
            or metadata.get("truth_gate")
        )
        uses_surveillance = _surveillance_dataset_uses_surveillance(dataset)
        if not uses_surveillance:
            continue
        if surveillance_gate is None and dataset.schema_version != SURVEILLANCE_LABEL_SCHEMA_VERSION:
            datasets_missing_truth_gate.append(dataset.id)
        if isinstance(surveillance_gate, dict) and surveillance_gate.get("proxy_only_as_confirmed_allowed") is True:
            proxy_allowed_datasets.append(dataset.id)
        rows_allowing_proxy_only_as_confirmed.extend(
            row.id
            for row in FeatureDatasetRow.objects.filter(dataset=dataset).order_by("id")
            if (row.feature_values or {}).get("surveillance_proxy_only_as_confirmed_allowed") is True
            or (row.feature_values or {}).get("proxy_only_as_confirmed_allowed") is True
        )

    proxy_allowed_model_runs = [
        run.id
        for run in ModelRun.objects.order_by("id")
        if ((run.metadata or {}).get("surveillance_label_truth_gate") or {}).get("proxy_only_as_confirmed_allowed")
        is True
    ]
    model_runs_missing_truth_gate = [
        run.id
        for run in ModelRun.objects.order_by("id")
        if (
            (run.metadata or {}).get("surveillance_label_dataset_ref")
            or (run.metadata or {}).get("surveillance_label_usage") not in {None, "not_available"}
        )
        and not (run.metadata or {}).get("surveillance_label_truth_gate")
    ]

    return {
        "id": "honesty_under_weak_inputs",
        "question": _question_text("honesty_under_weak_inputs"),
        "status": _status_from_checks(
            fail=bool(proxy_allowed_datasets or proxy_allowed_model_runs or rows_allowing_proxy_only_as_confirmed),
            warning=bool(datasets_missing_truth_gate or model_runs_missing_truth_gate or unknown_freshness_record_count),
            no_data=record_totals["surveillance_records"] == 0 and record_totals["label_windows"] == 0,
        ),
        "answer": (
            "Delayed, stale, corrected, partial, rejected, and proxy-only inputs are retained in lineage while "
            "truth gates prevent weak labels from being presented as confirmed outbreaks."
        ),
        "evidence": {
            "freshness_state_counts": freshness_counts,
            "unknown_freshness_record_count": unknown_freshness_record_count,
            "delayed_or_stale_record_count": int(freshness_counts.get(SurveillanceFreshnessState.DELAYED, 0))
            + int(freshness_counts.get(SurveillanceFreshnessState.STALE, 0)),
            "corrected_record_count": int(
                freshness_counts.get(SurveillanceFreshnessState.CORRECTED_AFTER_INITIAL_SUBMISSION, 0)
            ),
            "partial_or_failed_ingestion_run_count": partial_or_failed_runs,
            "rejected_source_row_count": rejected_row_count,
            "proxy_only_label_window_count": proxy_only_label_windows,
            "datasets_missing_surveillance_truth_gate": datasets_missing_truth_gate[:25],
            "datasets_allowing_proxy_only_as_confirmed": proxy_allowed_datasets[:25],
            "feature_rows_allowing_proxy_only_as_confirmed": rows_allowing_proxy_only_as_confirmed[:25],
            "model_runs_allowing_proxy_only_as_confirmed": proxy_allowed_model_runs[:25],
            "model_runs_missing_surveillance_truth_gate": model_runs_missing_truth_gate[:25],
        },
        "gaps": [
            gap
            for gap, present in [
                ("unknown_surveillance_freshness_state", unknown_freshness_record_count > 0),
                ("surveillance_truth_gate_missing", bool(datasets_missing_truth_gate)),
                ("model_surveillance_truth_gate_missing", bool(model_runs_missing_truth_gate)),
                (
                    "proxy_only_label_windows_allowed_as_confirmed",
                    bool(proxy_allowed_datasets or proxy_allowed_model_runs or rows_allowing_proxy_only_as_confirmed),
                ),
            ]
            if present
        ],
    }


def _ops_question() -> dict:
    command_states = {
        "ingest_surveillance": _management_command_exists("ingest_surveillance"),
        "build_surveillance_label_dataset": _management_command_exists("build_surveillance_label_dataset"),
        "build_surveillance_lead_time_labels": _management_command_exists("build_surveillance_lead_time_labels"),
        "evaluate_model_run_surveillance_labels": _management_command_exists("evaluate_model_run_surveillance_labels"),
        "audit_surveillance_pipeline": _management_command_exists("audit_surveillance_pipeline"),
        "run_risk_model": _management_command_exists("run_risk_model"),
        "run_random_forest_benchmark": _management_command_exists("run_random_forest_benchmark"),
    }
    missing_commands = [name for name, exists in command_states.items() if not exists]

    return {
        "id": "ops_without_frontend",
        "question": _question_text("ops_without_frontend"),
        "status": _status_from_checks(fail=bool(missing_commands)),
        "answer": (
            "Operators can inspect, ingest, replay, regenerate label windows, build label datasets, build "
            "7-to-14 day evaluation labels, audit the pipeline, evaluate old model runs, and run model consumers "
            "from management commands."
        ),
        "evidence": {
            "management_commands": command_states,
            "adapter_source_types": sorted(SURVEILLANCE_ADAPTERS),
            "feed_policy_source_types": sorted(SURVEILLANCE_FEED_POLICIES),
            "example_commands": [
                "python manage.py ingest_surveillance --inspect-only --file source.csv --source-type weekly_aggregate",
                "python manage.py ingest_surveillance --file source.csv --source-name <name> --source-type weekly_aggregate",
                "python manage.py ingest_surveillance --replay-of <run_id>",
                "python manage.py ingest_surveillance --file source.csv --source-name <name> --source-type weekly_aggregate --correction-mode amendment --correction-reason <reason> --regenerate-label-windows",
                "python manage.py build_surveillance_label_dataset --start-date <date> --end-date <date>",
                "python manage.py build_surveillance_lead_time_labels --prediction-date <date>",
                "python manage.py evaluate_model_run_surveillance_labels <model_run_id>",
                "python manage.py audit_surveillance_pipeline --format json",
            ],
        },
        "gaps": missing_commands,
    }


def _seeded_question() -> dict:
    contract_available = (
        SurveillanceTruthLevel.SEEDED_DEMO in {choice[0] for choice in SurveillanceTruthLevel.choices}
        and SurveillanceSourceKind.SEEDED in {choice[0] for choice in SurveillanceSourceKind.choices}
    )
    seeded_record_count = SurveillanceRecord.objects.filter(
        truth_level=SurveillanceTruthLevel.SEEDED_DEMO,
    ).count()
    seeded_label_window_count = SurveillanceLabelWindow.objects.filter(
        label_truth_level=SurveillanceTruthLevel.SEEDED_DEMO,
    ).count()
    seeded_source_name_count = SurveillanceSource.objects.filter(source_name__icontains="seed").count()
    seeded_kind_mismatch_count = SurveillanceRecord.objects.filter(
        truth_level=SurveillanceTruthLevel.SEEDED_DEMO,
    ).exclude(source_kind=SurveillanceSourceKind.SEEDED).count()
    seeded_source_kind_without_seeded_truth_count = SurveillanceRecord.objects.filter(
        source_kind=SurveillanceSourceKind.SEEDED,
    ).exclude(truth_level=SurveillanceTruthLevel.SEEDED_DEMO).count()
    seeded_source_ids = set(
        SurveillanceRecord.objects.filter(
            Q(truth_level=SurveillanceTruthLevel.SEEDED_DEMO) | Q(source_kind=SurveillanceSourceKind.SEEDED)
        ).values_list("source_id", flat=True)
    )
    seeded_source_ids.update(
        SurveillanceSource.objects.filter(source_name__icontains="seed").values_list("id", flat=True)
    )
    seeded_run_ids = set(
        SurveillanceRecord.objects.filter(
            Q(truth_level=SurveillanceTruthLevel.SEEDED_DEMO) | Q(source_kind=SurveillanceSourceKind.SEEDED)
        ).values_list("ingestion_run_id", flat=True)
    )
    seeded_run_ids.update(
        SurveillanceIngestionRun.objects.filter(source_name__icontains="seed").values_list("id", flat=True)
    )
    seeded_sources_missing_non_production_metadata = [
        source.id
        for source in SurveillanceSource.objects.filter(id__in=seeded_source_ids).order_by("id")
        if (source.metadata or {}).get("seeded_non_production") is not True
        or (source.metadata or {}).get("production_use_allowed") is not False
    ]
    seeded_runs_missing_non_production_metadata = [
        run.id
        for run in SurveillanceIngestionRun.objects.filter(id__in=seeded_run_ids).order_by("id")
        if (run.source_metadata or {}).get("seeded_non_production") is not True
        or (run.source_metadata or {}).get("production_use_allowed") is not False
    ]

    return {
        "id": "seeded_scenario_discipline",
        "question": _question_text("seeded_scenario_discipline"),
        "status": _status_from_checks(
            fail=(
                not contract_available
                or seeded_kind_mismatch_count > 0
                or seeded_source_kind_without_seeded_truth_count > 0
                or bool(seeded_sources_missing_non_production_metadata)
                or bool(seeded_runs_missing_non_production_metadata)
            ),
            no_data=seeded_record_count == 0 and seeded_label_window_count == 0 and seeded_source_name_count == 0,
        ),
        "answer": (
            "Seeded surveillance scenarios use the same source, run, record, and label contracts while carrying "
            "seeded_demo truth and seeded source-kind markers."
        ),
        "evidence": {
            "seeded_record_count": seeded_record_count,
            "seeded_label_window_count": seeded_label_window_count,
            "seeded_source_name_count": seeded_source_name_count,
            "seeded_kind_mismatch_count": seeded_kind_mismatch_count,
            "seeded_source_kind_without_seeded_truth_count": seeded_source_kind_without_seeded_truth_count,
            "seeded_sources_missing_non_production_metadata": seeded_sources_missing_non_production_metadata[:25],
            "seeded_runs_missing_non_production_metadata": seeded_runs_missing_non_production_metadata[:25],
            "seeded_truth_assumption": SURVEILLANCE_LABEL_TRUTH_ASSUMPTIONS.get(SurveillanceTruthLevel.SEEDED_DEMO),
        },
        "gaps": [
            gap
            for gap, present in [
                ("seeded_truth_contract_missing", not contract_available),
                ("seeded_truth_records_not_marked_seeded_source_kind", seeded_kind_mismatch_count > 0),
                (
                    "seeded_source_kind_records_not_marked_seeded_truth",
                    seeded_source_kind_without_seeded_truth_count > 0,
                ),
                (
                    "seeded_sources_missing_non_production_metadata",
                    bool(seeded_sources_missing_non_production_metadata),
                ),
                (
                    "seeded_runs_missing_non_production_metadata",
                    bool(seeded_runs_missing_non_production_metadata),
                ),
            ]
            if present
        ],
    }


def build_surveillance_pipeline_audit() -> dict:
    record_totals = _record_totals()
    questions = [
        _truth_level_question(record_totals),
        _replay_and_correction_question(record_totals),
        _label_window_lineage_question(record_totals),
        _model_backbone_question(record_totals),
        _lead_time_period_question(record_totals),
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
        "audit_name": "surveillance_pipeline_phase_6",
        "overall_status": overall_status,
        "status_counts": status_counts,
        "record_totals": record_totals,
        "source_totals": {
            "source_count": SurveillanceSource.objects.count(),
            "ingestion_run_count": SurveillanceIngestionRun.objects.count(),
            "source_type_counts": _counts_by_field(SurveillanceSource, "source_type"),
            "run_status_counts": _counts_by_field(SurveillanceIngestionRun, "status"),
            "record_truth_level_counts": _counts_by_field(SurveillanceRecord, "truth_level"),
            "record_freshness_state_counts": _counts_by_field(SurveillanceRecord, "freshness_state"),
            "label_truth_level_counts": _counts_by_field(SurveillanceLabelWindow, "label_truth_level"),
        },
        "verification_questions": questions,
    }
