from __future__ import annotations

from collections import Counter

from django.utils import timezone

from risk.feedback_governance import (
    FEEDBACK_GOVERNANCE_DECISION_SCHEMA_VERSION,
    build_feedback_governance_decision_record,
)
from risk.models import (
    FeatureDataset,
    FeatureDatasetRow,
    FeedbackAdjudicationState,
    FeedbackLabelCandidate,
    ModelRun,
    PredictionFeedback,
    PredictionFeedbackPrivacyClassification,
    PredictionFeedbackTrainingUsageState,
    SurveillanceLabelWindow,
    SurveillanceTruthLevel,
)


FEEDBACK_TO_MODEL_AUDIT_SCHEMA_VERSION = "feedback-to-model-governance-audit-v1"
AUDIT_PASS = "pass"
AUDIT_WARNING = "warning"
AUDIT_FAIL = "fail"


def _check_result(*, check_id: str, status: str, answer: str, evidence: dict, gaps: list[str]) -> dict:
    return {
        "id": check_id,
        "status": status,
        "answer": answer,
        "evidence": evidence,
        "gaps": gaps,
    }


def _overall_status(checks: list[dict]) -> str:
    if any(check["status"] == AUDIT_FAIL for check in checks):
        return AUDIT_FAIL
    if any(check["status"] == AUDIT_WARNING for check in checks):
        return AUDIT_WARNING
    return AUDIT_PASS


def _feedback_ref(feedback: PredictionFeedback) -> str:
    return f"prediction_feedback:{feedback.public_id}"


def _unsafe_feedback_model_run_metadata(model_run: ModelRun) -> dict:
    metadata = model_run.metadata or {}
    unsafe_keys = [
        "live_reinforcement_learning_enabled",
        "online_learning_from_feedback",
        "automatic_feedback_training",
        "automatic_threshold_update_from_feedback",
        "automatic_live_promotion_from_feedback",
    ]
    unsafe_values = {key: metadata.get(key) for key in unsafe_keys if metadata.get(key)}
    feedback_training_mode = metadata.get("feedback_training_mode")
    if feedback_training_mode in {"online", "live", "reinforcement_learning"}:
        unsafe_values["feedback_training_mode"] = feedback_training_mode
    return unsafe_values


def _decision_record_check() -> dict:
    decision = build_feedback_governance_decision_record()
    unsafe_model_runs = []
    for model_run in ModelRun.objects.order_by("-started_at", "-id"):
        unsafe_metadata = _unsafe_feedback_model_run_metadata(model_run)
        if unsafe_metadata:
            unsafe_model_runs.append(
                {
                    "model_run_id": model_run.id,
                    "model_version": model_run.model_version,
                    "unsafe_metadata": unsafe_metadata,
                }
            )

    decision_violated = any(
        [
            decision["live_reinforcement_learning_allowed"],
            decision["online_model_weight_updates_allowed"],
            decision["automatic_threshold_changes_from_feedback_allowed"],
            decision["automatic_retraining_promotion_allowed"],
            decision["unadjudicated_feedback_as_confirmed_truth_allowed"],
        ]
    )
    return _check_result(
        check_id="live_reinforcement_learning_blocked",
        status=AUDIT_FAIL if decision_violated or unsafe_model_runs else AUDIT_PASS,
        answer=(
            "Governance blocks live reinforcement learning and no model run advertises online feedback mutation."
            if not decision_violated and not unsafe_model_runs
            else "Live feedback-to-model mutation is allowed or advertised in model metadata."
        ),
        evidence={
            "decision_record_schema_version": decision["schema_version"],
            "implemented_scope": decision["implemented_scope"],
            "deferred_scope": decision["deferred_scope"],
            "unsafe_model_runs": unsafe_model_runs[:25],
        },
        gaps=["live_feedback_model_mutation_path"] if decision_violated or unsafe_model_runs else [],
    )


def _training_state_requires_adjudication_check() -> dict:
    governed_states = [
        PredictionFeedbackTrainingUsageState.ADJUDICATED_LABEL_CANDIDATE,
        PredictionFeedbackTrainingUsageState.TRAINING_ELIGIBLE,
    ]
    unsafe_feedback = []
    for feedback in PredictionFeedback.objects.filter(training_usage_state__in=governed_states).order_by("-submitted_at", "-id"):
        has_accepted_adjudication = feedback.adjudications.filter(
            adjudication_state=FeedbackAdjudicationState.ACCEPTED_AS_LABEL_CANDIDATE,
            reviewed_at__isnull=False,
        ).exists()
        if not has_accepted_adjudication:
            unsafe_feedback.append(
                {
                    "feedback_ref": _feedback_ref(feedback),
                    "training_usage_state": feedback.training_usage_state,
                    "ward_id": feedback.ward_id,
                }
            )

    return _check_result(
        check_id="training_usage_requires_reviewed_adjudication",
        status=AUDIT_FAIL if unsafe_feedback else AUDIT_PASS,
        answer=(
            "Every feedback record with training-facing state has reviewed adjudication evidence."
            if not unsafe_feedback
            else "One or more feedback records reached training-facing state without reviewed adjudication."
        ),
        evidence={
            "governed_training_states": governed_states,
            "unsafe_feedback_count": len(unsafe_feedback),
            "unsafe_feedback": unsafe_feedback[:25],
        },
        gaps=["feedback_training_state_without_adjudication"] if unsafe_feedback else [],
    )


def _sensitive_feedback_training_check() -> dict:
    unsafe_feedback = list(
        PredictionFeedback.objects.filter(
            privacy_classification=PredictionFeedbackPrivacyClassification.CONTAINS_PII,
            training_usage_state__in=[
                PredictionFeedbackTrainingUsageState.ADJUDICATED_LABEL_CANDIDATE,
                PredictionFeedbackTrainingUsageState.TRAINING_ELIGIBLE,
            ],
        )
        .order_by("-submitted_at", "-id")
        .values("public_id", "ward_id", "training_usage_state", "privacy_classification")[:25]
    )
    return _check_result(
        check_id="sensitive_feedback_not_training_eligible",
        status=AUDIT_FAIL if unsafe_feedback else AUDIT_PASS,
        answer=(
            "No PII-bearing feedback is marked as training-facing."
            if not unsafe_feedback
            else "One or more PII-bearing feedback records are marked as training-facing."
        ),
        evidence={"unsafe_feedback": unsafe_feedback, "unsafe_feedback_count": len(unsafe_feedback)},
        gaps=["pii_feedback_training_eligible"] if unsafe_feedback else [],
    )


def _feedback_candidates_are_weak_truth_check() -> dict:
    confirmed_candidates = list(
        FeedbackLabelCandidate.objects.filter(label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE)
        .order_by("-created_at", "-id")
        .values("candidate_ref", "ward_id", "label_truth_level")[:25]
    )
    confirmed_feedback_windows = []
    feedback_ref_prefixes = ("prediction_feedback:", "feedback_label_candidate:")
    for window in SurveillanceLabelWindow.objects.filter(label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE).order_by("-created_at", "-id"):
        refs = window.generated_from_record_refs or []
        if any(isinstance(ref, str) and ref.startswith(feedback_ref_prefixes) for ref in refs):
            confirmed_feedback_windows.append(
                {
                    "label_window_id": window.id,
                    "ward_id": window.ward_id,
                    "dataset_ref": window.dataset_ref,
                    "generated_from_record_refs": refs,
                }
            )

    has_findings = bool(confirmed_candidates or confirmed_feedback_windows)
    return _check_result(
        check_id="feedback_never_becomes_confirmed_surveillance_truth",
        status=AUDIT_FAIL if has_findings else AUDIT_PASS,
        answer=(
            "Feedback-derived evidence remains weak and distinct from confirmed surveillance truth."
            if not has_findings
            else "Feedback-derived evidence is being represented as confirmed surveillance truth."
        ),
        evidence={
            "confirmed_feedback_candidate_count": len(confirmed_candidates),
            "confirmed_feedback_candidates": confirmed_candidates,
            "confirmed_surveillance_windows_with_feedback_refs_count": len(confirmed_feedback_windows),
            "confirmed_surveillance_windows_with_feedback_refs": confirmed_feedback_windows[:25],
        },
        gaps=["feedback_used_as_confirmed_surveillance_truth"] if has_findings else [],
    )


def _unreviewed_feedback_refs_from_payload(payload) -> list[str]:
    refs = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"feedback_refs", "prediction_feedback_refs", "feedback_label_candidate_refs"}:
                if isinstance(value, list):
                    refs.extend(str(item) for item in value)
                elif value:
                    refs.append(str(value))
            refs.extend(_unreviewed_feedback_refs_from_payload(value))
    elif isinstance(payload, list):
        for item in payload:
            refs.extend(_unreviewed_feedback_refs_from_payload(item))
    return refs


def _feedback_refs_are_reviewed(refs: list[str]) -> tuple[bool, list[str]]:
    unsafe_refs = []
    for ref in refs:
        if ref.startswith("feedback_label_candidate:"):
            candidate_exists = FeedbackLabelCandidate.objects.filter(
                candidate_ref=ref,
                training_usage_state__in=[
                    PredictionFeedbackTrainingUsageState.ADJUDICATED_LABEL_CANDIDATE,
                    PredictionFeedbackTrainingUsageState.TRAINING_ELIGIBLE,
                ],
            ).exists()
            if not candidate_exists:
                unsafe_refs.append(ref)
        elif ref.startswith("prediction_feedback:"):
            public_id = ref.split("prediction_feedback:", 1)[1]
            feedback_exists = PredictionFeedback.objects.filter(
                public_id=public_id,
                training_usage_state__in=[
                    PredictionFeedbackTrainingUsageState.ADJUDICATED_LABEL_CANDIDATE,
                    PredictionFeedbackTrainingUsageState.TRAINING_ELIGIBLE,
                ],
                adjudications__adjudication_state=FeedbackAdjudicationState.ACCEPTED_AS_LABEL_CANDIDATE,
            ).exists()
            if not feedback_exists:
                unsafe_refs.append(ref)
    return not unsafe_refs, unsafe_refs


def _feature_dataset_feedback_lineage_check() -> dict:
    unsafe_dataset_refs = []
    for dataset in FeatureDataset.objects.order_by("-created_at", "-id"):
        refs = _unreviewed_feedback_refs_from_payload(dataset.lineage_metadata or {})
        reviewed, unsafe_refs = _feedback_refs_are_reviewed(refs)
        if not reviewed:
            unsafe_dataset_refs.append(
                {
                    "dataset_ref": dataset.dataset_ref,
                    "unsafe_feedback_refs": unsafe_refs,
                }
            )
    unsafe_row_refs = []
    for row in FeatureDatasetRow.objects.exclude(feature_values={}).order_by("-created_at", "-id")[:5000]:
        refs = _unreviewed_feedback_refs_from_payload(row.feature_values or {})
        reviewed, unsafe_refs = _feedback_refs_are_reviewed(refs)
        if not reviewed:
            unsafe_row_refs.append(
                {
                    "dataset_ref": row.dataset.dataset_ref,
                    "row_id": row.id,
                    "unsafe_feedback_refs": unsafe_refs,
                }
            )

    has_findings = bool(unsafe_dataset_refs or unsafe_row_refs)
    return _check_result(
        check_id="unreviewed_feedback_not_used_in_feature_datasets",
        status=AUDIT_FAIL if has_findings else AUDIT_PASS,
        answer=(
            "Feature datasets do not cite unreviewed or rejected feedback as training evidence."
            if not has_findings
            else "One or more feature datasets cite feedback that is not reviewed and training-facing."
        ),
        evidence={
            "unsafe_dataset_ref_count": len(unsafe_dataset_refs),
            "unsafe_dataset_refs": unsafe_dataset_refs[:25],
            "unsafe_row_ref_count": len(unsafe_row_refs),
            "unsafe_row_refs": unsafe_row_refs[:25],
            "row_scan_limit": 5000,
        },
        gaps=["unreviewed_feedback_used_in_feature_dataset"] if has_findings else [],
    )


def _candidate_supersession_check() -> dict:
    unsuperseded_candidates = []
    candidates = FeedbackLabelCandidate.objects.filter(
        superseded_by_surveillance_label__isnull=True,
    ).exclude(training_usage_state=PredictionFeedbackTrainingUsageState.SUPERSEDED_BY_SURVEILLANCE_TRUTH)
    confirmed_labels = list(
        SurveillanceLabelWindow.objects.filter(label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE)
        .order_by("-label_window_end", "-id")
        .values("id", "ward_id", "label_window_start", "label_window_end")
    )
    for candidate in candidates.order_by("-created_at", "-id"):
        overlapping_label = next(
            (
                label
                for label in confirmed_labels
                if label["ward_id"] == candidate.ward_id
                and label["label_window_start"] <= candidate.label_window_end
                and label["label_window_end"] >= candidate.label_window_start
            ),
            None,
        )
        if overlapping_label:
            unsuperseded_candidates.append(
                {
                    "candidate_ref": candidate.candidate_ref,
                    "ward_id": candidate.ward_id,
                    "overlapping_confirmed_label_window_id": overlapping_label["id"],
                }
            )

    return _check_result(
        check_id="confirmed_surveillance_supersedes_feedback_candidates",
        status=AUDIT_FAIL if unsuperseded_candidates else AUDIT_PASS,
        answer=(
            "All feedback label candidates overlapping confirmed surveillance truth are superseded."
            if not unsuperseded_candidates
            else "One or more feedback label candidates should be superseded by confirmed surveillance truth."
        ),
        evidence={
            "unsuperseded_candidate_count": len(unsuperseded_candidates),
            "unsuperseded_candidates": unsuperseded_candidates[:25],
        },
        gaps=["feedback_candidate_not_superseded_by_confirmed_surveillance"] if unsuperseded_candidates else [],
    )


def build_feedback_to_model_governance_audit() -> dict:
    now = timezone.now()
    checks = [
        _decision_record_check(),
        _training_state_requires_adjudication_check(),
        _sensitive_feedback_training_check(),
        _feedback_candidates_are_weak_truth_check(),
        _feature_dataset_feedback_lineage_check(),
        _candidate_supersession_check(),
    ]
    status_counts = Counter(check["status"] for check in checks)
    return {
        "schema_version": FEEDBACK_TO_MODEL_AUDIT_SCHEMA_VERSION,
        "generated_at": now,
        "overall_status": _overall_status(checks),
        "summary": {
            "check_count": len(checks),
            "passed_check_count": status_counts[AUDIT_PASS],
            "warning_check_count": status_counts[AUDIT_WARNING],
            "failed_check_count": status_counts[AUDIT_FAIL],
            "feedback_count": PredictionFeedback.objects.count(),
            "adjudication_count": PredictionFeedback.objects.filter(adjudications__isnull=False).distinct().count(),
            "label_candidate_count": FeedbackLabelCandidate.objects.count(),
        },
        "governance": {
            "decision_record_schema_version": FEEDBACK_GOVERNANCE_DECISION_SCHEMA_VERSION,
            "feedback_record": "PredictionFeedback",
            "adjudication_record": "FeedbackAdjudication",
            "weak_label_candidate_record": "FeedbackLabelCandidate",
            "surveillance_truth_record": "SurveillanceLabelWindow",
            "policy": (
                "Feedback can become at most a reviewed weak label candidate until future offline dataset "
                "builders include it under explicit lineage and Phase 4 promotion gates."
            ),
        },
        "checks": checks,
    }
