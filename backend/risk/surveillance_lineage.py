"""Durable supersession lifecycle for surveillance label evidence.

Surveillance records are append-only.  A correction therefore retires the
label snapshot that cited the old record and creates a new snapshot from the
current canonical record set.  This module owns the cross-cutting lineage
updates so ingestion, reconciliation, truth policy, and audits share the
same contract.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from typing import Any, Iterable

from django.db import transaction
from django.utils import timezone

from risk.models import (
    FeatureDataset,
    FeatureDatasetRow,
    ModelRegistryEntry,
    ModelRun,
    SurveillanceIngestionRun,
    SurveillanceLabelWindow,
    SurveillanceRecord,
    Ward,
)


DATASET_ELIGIBILITY_ACTIVE = FeatureDataset.ELIGIBILITY_ACTIVE
DATASET_ELIGIBILITY_SUPERSEDED = FeatureDataset.ELIGIBILITY_SUPERSEDED
DATASET_ELIGIBILITY_NON_ELIGIBLE = FeatureDataset.ELIGIBILITY_NON_ELIGIBLE
NON_CURRENT_DATASET_ELIGIBILITY_STATES = frozenset(
    {
        DATASET_ELIGIBILITY_SUPERSEDED,
        DATASET_ELIGIBILITY_NON_ELIGIBLE,
    }
)


def surveillance_record_ids_from_refs(refs: Iterable[Any] | None) -> set[int]:
    """Return valid surveillance record ids from a persisted ref list."""

    record_ids: set[int] = set()
    for ref in refs or []:
        value = str(ref)
        if not value.startswith("surveillance_record:"):
            continue
        try:
            record_ids.add(int(value.split(":", 1)[1]))
        except (TypeError, ValueError):
            continue
    return record_ids


def surveillance_record_refs_from_ids(record_ids: Iterable[int]) -> list[str]:
    return [f"surveillance_record:{record_id}" for record_id in sorted(set(record_ids))]


def dataset_is_currently_eligible(dataset: FeatureDataset | None) -> bool:
    """Return whether a persisted dataset may be used as current evidence."""

    if dataset is None:
        return False
    state = str(getattr(dataset, "eligibility_state", DATASET_ELIGIBILITY_ACTIVE) or "").lower()
    lineage = getattr(dataset, "lineage_metadata", None) or {}
    lineage_state = str(lineage.get("eligibility_state") or "").lower()
    lineage_status = str(lineage.get("eligibility_status") or "").lower()
    return not (
        state in NON_CURRENT_DATASET_ELIGIBILITY_STATES
        or lineage_state in NON_CURRENT_DATASET_ELIGIBILITY_STATES
        or lineage_status in {"non_eligible", "superseded"}
    )


def dataset_is_superseded(dataset: FeatureDataset | None) -> bool:
    if dataset is None:
        return False
    state = str(getattr(dataset, "eligibility_state", "") or "").lower()
    lineage = getattr(dataset, "lineage_metadata", None) or {}
    return state == DATASET_ELIGIBILITY_SUPERSEDED or str(
        lineage.get("eligibility_state") or ""
    ).lower() == DATASET_ELIGIBILITY_SUPERSEDED


def label_window_is_currently_eligible(window: SurveillanceLabelWindow) -> bool:
    """Keep retired snapshots out of current feature/decision consumers."""

    dataset = getattr(window, "feature_dataset", None)
    return dataset_is_currently_eligible(dataset) if dataset is not None else True


def _dataset_lineage(dataset: FeatureDataset) -> dict:
    lineage = dataset.lineage_metadata or {}
    return deepcopy(lineage) if isinstance(lineage, dict) else {}


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _window_refs(window: SurveillanceLabelWindow) -> set[int]:
    return surveillance_record_ids_from_refs(window.generated_from_record_refs)


def _dataset_windows(dataset: FeatureDataset) -> list[SurveillanceLabelWindow]:
    return list(
        SurveillanceLabelWindow.objects.filter(feature_dataset=dataset)
        .select_related("ward")
        .order_by("id")
    )


def _dataset_config(dataset: FeatureDataset, windows: list[SurveillanceLabelWindow]) -> dict:
    lineage = _dataset_lineage(dataset)
    generation_mode = lineage.get("generation_mode")
    if not generation_mode and any(
        window.generation_mode == "phase_3_7_to_14_day_evaluation_labels_v1" for window in windows
    ):
        generation_mode = "phase_3_7_to_14_day_evaluation_labels_v1"
    start_date = _parse_date(lineage.get("start_date")) or min(
        (window.label_window_start for window in windows),
        default=None,
    )
    end_date = _parse_date(lineage.get("end_date")) or max(
        (window.label_window_end for window in windows),
        default=None,
    )
    prediction_dates = [
        parsed
        for parsed in (_parse_date(value) for value in lineage.get("prediction_dates") or [])
        if parsed is not None
    ]
    if not prediction_dates and generation_mode == "phase_3_7_to_14_day_evaluation_labels_v1":
        feature_values = FeatureDatasetRow.objects.filter(dataset=dataset).values_list("feature_values", flat=True)
        prediction_dates = sorted(
            {
                parsed
                for values in feature_values
                for parsed in [_parse_date((values or {}).get("prediction_date"))]
                if parsed is not None
            }
        )
    ward_ids = sorted({window.ward_id for window in windows if window.ward_id})
    return {
        "dataset_role": lineage.get("dataset_role") or "training",
        "generation_mode": generation_mode,
        "start_date": start_date,
        "end_date": end_date,
        "prediction_dates": prediction_dates,
        "window_days": int(lineage.get("window_days") or 7),
        "step_days": int(lineage.get("step_days") or 7),
        "include_seeded": bool(lineage.get("include_seeded", False)),
        "include_empty_windows": bool(lineage.get("include_empty_windows", False)),
        "lead_time_start_days": int(lineage.get("label_window_start_offset_days") or 7),
        "lead_time_end_days": int(lineage.get("label_window_end_offset_days") or 14),
        "ward_ids": ward_ids,
    }


def _run_ref(run_id: int | None) -> str | None:
    return f"surveillance_ingestion_run:{run_id}" if run_id else None


def _supersession_context(
    *,
    superseded_records: list[SurveillanceRecord],
    superseding_ingestion_run: SurveillanceIngestionRun | None,
    now: datetime,
) -> dict:
    run_ids = {
        int((record.raw_payload or {}).get("superseded_by_run_id"))
        for record in superseded_records
        if str((record.raw_payload or {}).get("superseded_by_run_id") or "").isdigit()
    }
    if superseding_ingestion_run is not None:
        run_ids.add(superseding_ingestion_run.id)
    runs = {
        run.id: run
        for run in SurveillanceIngestionRun.objects.filter(id__in=run_ids)
        .only("id", "correction_reason")
        .order_by("id")
    }
    if superseding_ingestion_run is not None:
        runs[superseding_ingestion_run.id] = superseding_ingestion_run
    superseding_record_refs = sorted(
        {
            str((record.raw_payload or {}).get("superseded_by_record_ref"))
            for record in superseded_records
            if (record.raw_payload or {}).get("superseded_by_record_ref")
        }
    )
    run_refs = [_run_ref(run_id) for run_id in sorted(runs) if _run_ref(run_id)]
    reasons = sorted(
        {
            (run.correction_reason or "").strip()
            for run in runs.values()
            if (run.correction_reason or "").strip()
        }
    )
    if not reasons:
        reasons = ["Canonical surveillance correction superseded an existing record."]
    return {
        "superseded_at": now.isoformat(),
        "superseded_record_refs": surveillance_record_refs_from_ids(record.id for record in superseded_records),
        "superseding_record_refs": superseding_record_refs,
        "superseding_ingestion_run_refs": run_refs,
        "superseding_ingestion_run_ref": run_refs[0] if run_refs else None,
        "supersession_reason": reasons[0] if len(reasons) == 1 else "; ".join(reasons),
    }


def _build_replacement_dataset(
    *,
    dataset: FeatureDataset,
    config: dict,
    now: datetime,
) -> FeatureDataset:
    from risk.surveillance_labels import (
        SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE,
        build_surveillance_label_dataset,
        build_surveillance_lead_time_label_dataset,
    )

    wards = Ward.objects.filter(id__in=config["ward_ids"]).order_by("name")
    if config["generation_mode"] == SURVEILLANCE_LEAD_TIME_LABEL_GENERATION_MODE:
        snapshot = build_surveillance_lead_time_label_dataset(
            wards=wards,
            prediction_dates=config["prediction_dates"],
            as_of=now,
            lead_time_start_days=config["lead_time_start_days"],
            lead_time_end_days=config["lead_time_end_days"],
            step_days=config["step_days"],
            dataset_role=config["dataset_role"],
            include_seeded=config["include_seeded"],
            include_empty_windows=config["include_empty_windows"],
        )
    else:
        snapshot = build_surveillance_label_dataset(
            wards=wards,
            start_date=config["start_date"],
            end_date=config["end_date"],
            as_of=now,
            window_days=config["window_days"],
            step_days=config["step_days"],
            dataset_role=config["dataset_role"],
            include_seeded=config["include_seeded"],
            include_empty_windows=config["include_empty_windows"],
        )
    replacement = snapshot.feature_dataset
    if replacement.dataset_kind != dataset.dataset_kind:
        replacement.dataset_kind = dataset.dataset_kind
        replacement.save(update_fields=["dataset_kind"])
    return replacement


def _current_payload_contains_ref(value: Any, refs: set[str], *, key: str = "") -> bool:
    if "history" in key.lower():
        return False
    if isinstance(value, str):
        return value in refs
    if isinstance(value, list):
        return any(_current_payload_contains_ref(item, refs, key=key) for item in value)
    if isinstance(value, dict):
        return any(
            _current_payload_contains_ref(nested, refs, key=str(nested_key))
            for nested_key, nested in value.items()
        )
    return False


def _replace_current_payload_refs(
    value: Any,
    ref_mapping: dict[str, str],
    id_mapping: dict[int, int],
    *,
    key: str = "",
) -> Any:
    if "history" in key.lower():
        return deepcopy(value)
    if isinstance(value, str):
        return ref_mapping.get(value, value)
    if isinstance(value, list):
        return [
            _replace_current_payload_refs(item, ref_mapping, id_mapping, key=key)
            for item in value
        ]
    if not isinstance(value, dict):
        return value

    replaced = {}
    for nested_key, nested in value.items():
        if (
            str(nested_key).endswith("_dataset_id")
            and str(nested).isdigit()
            and int(nested) in id_mapping
        ):
            replaced[nested_key] = id_mapping[int(nested)]
        else:
            replaced[nested_key] = _replace_current_payload_refs(
                nested,
                ref_mapping,
                id_mapping,
                key=str(nested_key),
            )
    return replaced


def _update_current_model_evidence(
    *,
    ref_mapping: dict[str, str],
    id_mapping: dict[int, int],
) -> list[dict]:
    updated_runs = []
    retired_refs = set(ref_mapping)
    for model_run in ModelRun.objects.select_for_update().order_by("id"):
        metadata = deepcopy(model_run.metadata or {})
        evaluation_metrics = deepcopy(model_run.evaluation_metrics or {})
        direct_ref_fields = {
            field_name: getattr(model_run, field_name) or ""
            for field_name in ("training_dataset_ref", "inference_dataset_ref")
        }
        direct_ref_affected = any(value in retired_refs for value in direct_ref_fields.values())
        direct_fk_affected = any(
            getattr(model_run, field_name) in id_mapping
            for field_name in ("training_feature_dataset_id", "inference_feature_dataset_id")
        )
        if not (
            _current_payload_contains_ref(metadata, retired_refs)
            or _current_payload_contains_ref(evaluation_metrics, retired_refs)
            or direct_ref_affected
            or direct_fk_affected
        ):
            continue

        current_evaluation = evaluation_metrics.get("surveillance_7_to_14_day_evaluation")
        if _current_payload_contains_ref(current_evaluation, retired_refs):
            history = list(evaluation_metrics.get("surveillance_7_to_14_day_evaluation_history") or [])
            if current_evaluation not in history:
                history.append(deepcopy(current_evaluation))
            evaluation_metrics["surveillance_7_to_14_day_evaluation_history"] = history[-20:]

        model_run.metadata = _replace_current_payload_refs(metadata, ref_mapping, id_mapping)
        model_run.evaluation_metrics = _replace_current_payload_refs(
            evaluation_metrics,
            ref_mapping,
            id_mapping,
        )
        update_fields = ["metadata", "evaluation_metrics"]
        for field_name, value in direct_ref_fields.items():
            if value in ref_mapping:
                setattr(model_run, field_name, ref_mapping[value])
                update_fields.append(field_name)
        for field_name in ("training_feature_dataset_id", "inference_feature_dataset_id"):
            value = getattr(model_run, field_name)
            if value in id_mapping:
                setattr(model_run, field_name, id_mapping[value])
                update_fields.append(field_name)
        model_run.save(update_fields=update_fields)
        updated_runs.append({"model_run_id": model_run.id, "model_version": model_run.model_version})
    return updated_runs


def _update_current_registry_evidence(
    *,
    ref_mapping: dict[str, str],
    id_mapping: dict[int, int],
) -> list[dict]:
    updated_entries = []
    for entry in ModelRegistryEntry.objects.select_for_update().order_by("id"):
        old_ref = (entry.training_label_dataset_ref or "").strip()
        if old_ref not in ref_mapping:
            continue
        metadata = deepcopy(entry.metadata or {})
        metadata["surveillance_label_supersession"] = {
            "superseded_dataset_ref": old_ref,
            "replacement_dataset_ref": ref_mapping[old_ref],
            "replacement_dataset_id": id_mapping.get(
                FeatureDataset.objects.filter(dataset_ref=ref_mapping[old_ref]).values_list("id", flat=True).first()
            ),
        }
        update_fields = ["metadata"]
        if entry.approval_state != "APPROVED":
            entry.training_label_dataset_ref = ref_mapping[old_ref]
            update_fields.append("training_label_dataset_ref")
        entry.metadata = metadata
        entry.save(update_fields=update_fields)
        updated_entries.append(
            {
                "registry_entry_id": entry.id,
                "model_run_id": entry.model_run_id,
                "superseded_dataset_ref": old_ref,
                "replacement_dataset_ref": ref_mapping[old_ref],
                "updated_current_pointer": entry.approval_state != "APPROVED",
            }
        )
    return updated_entries


def _replacement_evidence_is_complete(dataset: FeatureDataset) -> bool:
    lineage = _dataset_lineage(dataset)
    replacement_ref = lineage.get("replacement_dataset_ref")
    affected_windows = lineage.get("affected_window_refs")
    superseded_records = lineage.get("superseded_record_refs")
    if not replacement_ref or not affected_windows or not superseded_records:
        return False
    replacement = FeatureDataset.objects.filter(dataset_ref=replacement_ref).first()
    return bool(
        replacement
        and dataset_is_currently_eligible(replacement)
        and replacement.row_count > 0
        and SurveillanceLabelWindow.objects.filter(feature_dataset=replacement).exists()
    )


def reconcile_surveillance_label_lineage(
    *,
    superseding_ingestion_run: SurveillanceIngestionRun | None = None,
    superseded_record_ids: Iterable[int] | None = None,
    apply: bool = True,
    now: datetime | None = None,
) -> dict:
    """Retire affected label datasets and build current replacements.

    ``apply=False`` performs a read-only reconciliation report.  ``apply=True``
    performs all dataset, model, and registry updates in one transaction and is
    safe to repeat after a successful run.
    """

    now = now or timezone.now()
    requested_record_ids = {int(record_id) for record_id in superseded_record_ids or []}
    all_superseded_records = list(
        SurveillanceRecord.objects.filter(id__in=requested_record_ids)
        .only("id", "raw_payload")
        .order_by("id")
    )
    if not requested_record_ids:
        candidates = []
        for record in SurveillanceRecord.objects.only("id", "raw_payload").order_by("id"):
            if (record.raw_payload or {}).get("superseded_by_record_ref"):
                candidates.append(record)
        all_superseded_records = candidates

    if superseding_ingestion_run is not None and not requested_record_ids:
        all_superseded_records = [
            record
            for record in all_superseded_records
            if (record.raw_payload or {}).get("superseded_by_run_id") == superseding_ingestion_run.id
        ]

    record_ids = {record.id for record in all_superseded_records}
    context = _supersession_context(
        superseded_records=all_superseded_records,
        superseding_ingestion_run=superseding_ingestion_run,
        now=now,
    )
    affected_by_dataset: dict[int, dict] = {}
    windows_without_dataset: list[int] = []
    for window in SurveillanceLabelWindow.objects.only(
        "id",
        "feature_dataset_id",
        "generated_from_record_refs",
    ).order_by("id"):
        overlap = _window_refs(window).intersection(record_ids)
        if not overlap:
            continue
        if window.feature_dataset_id is None:
            windows_without_dataset.append(window.id)
            continue
        item = affected_by_dataset.setdefault(
            window.feature_dataset_id,
            {"dataset_id": window.feature_dataset_id, "windows": [], "record_ids": set()},
        )
        item["windows"].append(window)
        item["record_ids"].update(overlap)

    affected_datasets = FeatureDataset.objects.in_bulk(affected_by_dataset)
    for dataset_id, item in affected_by_dataset.items():
        item["dataset"] = affected_datasets[dataset_id]

    summary = {
        "applied": False,
        "dry_run": not apply,
        "superseded_record_count": len(record_ids),
        "superseded_record_refs": surveillance_record_refs_from_ids(record_ids),
        "affected_window_count": sum(len(item["windows"]) for item in affected_by_dataset.values())
        + len(windows_without_dataset),
        "windows_without_dataset_count": len(windows_without_dataset),
        "windows_without_dataset_ids": windows_without_dataset[:100],
        "affected_datasets": [],
        "replacement_datasets": [],
        "updated_model_runs": [],
        "updated_registry_entries": [],
    }

    if not apply:
        for item in affected_by_dataset.values():
            dataset = item["dataset"]
            config = _dataset_config(dataset, _dataset_windows(dataset))
            summary["affected_datasets"].append(
                {
                    "dataset_id": dataset.id,
                    "dataset_ref": dataset.dataset_ref,
                    "affected_window_count": len(item["windows"]),
                    "affected_window_refs": [f"surveillance_label_window:{window.id}" for window in item["windows"][:100]],
                    "superseded_record_refs": surveillance_record_refs_from_ids(item["record_ids"]),
                    "eligibility_state": dataset.eligibility_state,
                    "replacement_possible": bool(config["ward_ids"] and config["start_date"] and config["end_date"]),
                }
            )
        return summary

    ref_mapping: dict[str, str] = {}
    id_mapping: dict[int, int] = {}
    with transaction.atomic():
        for item in affected_by_dataset.values():
            dataset = FeatureDataset.objects.select_for_update().get(id=item["dataset"].id)
            lineage = _dataset_lineage(dataset)
            existing_replacement_ref = lineage.get("replacement_dataset_ref")
            if dataset_is_superseded(dataset) and existing_replacement_ref:
                replacement = FeatureDataset.objects.filter(dataset_ref=existing_replacement_ref).first()
                if replacement is not None and dataset_is_currently_eligible(replacement):
                    ref_mapping[dataset.dataset_ref] = replacement.dataset_ref
                    id_mapping[dataset.id] = replacement.id
                    summary["affected_datasets"].append(
                        {
                            "dataset_id": dataset.id,
                            "dataset_ref": dataset.dataset_ref,
                            "affected_window_count": len(item["windows"]),
                            "already_reconciled": True,
                            "replacement_dataset_ref": replacement.dataset_ref,
                        }
                    )
                    continue

            config = _dataset_config(dataset, _dataset_windows(dataset))
            affected_window_refs = [
                f"surveillance_label_window:{window.id}" for window in item["windows"]
            ]
            replacement = None
            replacement_error = None
            if config["ward_ids"] and config["start_date"] and config["end_date"]:
                try:
                    replacement = _build_replacement_dataset(dataset=dataset, config=config, now=now)
                except (ValueError, TypeError) as error:
                    replacement_error = str(error)

            dataset_lineage = {
                **lineage,
                "eligibility_state": DATASET_ELIGIBILITY_SUPERSEDED,
                "superseded_at": context["superseded_at"],
                "superseded_by_ingestion_run_ref": context["superseding_ingestion_run_ref"],
                "superseding_ingestion_run_refs": context["superseding_ingestion_run_refs"],
                "superseded_record_refs": surveillance_record_refs_from_ids(item["record_ids"]),
                "superseding_record_refs": context["superseding_record_refs"],
                "supersession_reason": context["supersession_reason"],
                "affected_window_refs": affected_window_refs,
                "replacement_dataset_ref": replacement.dataset_ref if replacement else None,
                "replacement_dataset_id": replacement.id if replacement else None,
                "replacement_error": replacement_error,
                "historical_evidence": "immutable_label_windows_and_feature_rows_preserved",
            }
            dataset.eligibility_state = DATASET_ELIGIBILITY_SUPERSEDED
            dataset.lineage_metadata = dataset_lineage
            dataset.save(update_fields=["eligibility_state", "lineage_metadata"])

            affected_entry = {
                "dataset_id": dataset.id,
                "dataset_ref": dataset.dataset_ref,
                "affected_window_count": len(item["windows"]),
                "affected_window_refs": affected_window_refs[:100],
                "superseded_record_refs": surveillance_record_refs_from_ids(item["record_ids"]),
                "replacement_dataset_ref": replacement.dataset_ref if replacement else None,
                "replacement_dataset_id": replacement.id if replacement else None,
                "replacement_error": replacement_error,
                "already_reconciled": False,
            }
            summary["affected_datasets"].append(affected_entry)
            if replacement is not None:
                replacement_lineage = _dataset_lineage(replacement)
                replacement.lineage_metadata = {
                    **replacement_lineage,
                    "eligibility_state": DATASET_ELIGIBILITY_ACTIVE,
                    "supersedes_dataset_ref": dataset.dataset_ref,
                    "superseded_dataset_ref": dataset.dataset_ref,
                    "superseded_record_refs": surveillance_record_refs_from_ids(item["record_ids"]),
                    "superseding_record_refs": context["superseding_record_refs"],
                    "superseding_ingestion_run_refs": context["superseding_ingestion_run_refs"],
                    "supersession_reason": context["supersession_reason"],
                    "superseded_at": context["superseded_at"],
                    "superseded_window_refs": affected_window_refs,
                }
                replacement.eligibility_state = DATASET_ELIGIBILITY_ACTIVE
                replacement.save(update_fields=["eligibility_state", "lineage_metadata"])
                ref_mapping[dataset.dataset_ref] = replacement.dataset_ref
                id_mapping[dataset.id] = replacement.id
                summary["replacement_datasets"].append(
                    {
                        "dataset_id": replacement.id,
                        "dataset_ref": replacement.dataset_ref,
                        "replaces_dataset_ref": dataset.dataset_ref,
                        "row_count": replacement.row_count,
                    }
                )

        if ref_mapping:
            summary["updated_model_runs"] = _update_current_model_evidence(
                ref_mapping=ref_mapping,
                id_mapping=id_mapping,
            )
            summary["updated_registry_entries"] = _update_current_registry_evidence(
                ref_mapping=ref_mapping,
                id_mapping=id_mapping,
            )
        summary["applied"] = True

        if superseding_ingestion_run is not None:
            superseding_ingestion_run.results = {
                **(superseding_ingestion_run.results or {}),
                "label_lineage_reconciliation": summary,
            }
            superseding_ingestion_run.save(update_fields=["results"])

    return summary


def current_model_run_dataset_refs(model_run: ModelRun) -> set[str]:
    """Collect current model/evaluation dataset refs while ignoring history."""

    refs: set[str] = set()

    def collect(value: Any, *, key: str = "") -> None:
        if "history" in key.lower():
            return
        if isinstance(value, str):
            if value.startswith("surveillance-label-"):
                refs.add(value)
            return
        if isinstance(value, list):
            for item in value:
                collect(item, key=key)
            return
        if isinstance(value, dict):
            for nested_key, nested in value.items():
                collect(nested, key=str(nested_key))

    collect(model_run.metadata or {})
    collect(model_run.evaluation_metrics or {})
    for value in (
        getattr(model_run, "training_dataset_ref", ""),
        getattr(model_run, "inference_dataset_ref", ""),
        getattr(getattr(model_run, "training_feature_dataset", None), "dataset_ref", ""),
        getattr(getattr(model_run, "inference_feature_dataset", None), "dataset_ref", ""),
    ):
        if isinstance(value, str) and value.startswith("surveillance-label-"):
            refs.add(value)
    return refs
