import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from risk.ml.model_registry_audit import NOT_APPROVED_FOR_OPERATIONAL_USE, build_model_registry_audit
from risk.ml.model_registry_governance import (
    ModelRegistryGovernanceError,
    activate_registered_model,
    designate_model_challenger,
    model_artifact_approval_blockers,
    register_model_artifact,
    request_model_approval,
    review_model_artifact,
)
from risk.ml.registry import active_model_registry_entry, execute_model_rollback
from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.models import (
    FeatureDataset,
    ModelGovernanceEvent,
    ModelPromotionEvent,
    ModelRegistryApprovalState,
    ModelRegistryEntry,
    ModelRegistryLifecycleState,
    ModelRegistryPromotionState,
    ModelRun,
    RiskScore,
    Ward,
)
from risk.truth_policy import PRODUCTION_ALERT_ACTIVE_REGISTRY_REQUIRED, production_alert_eligibility_blockers


class ModelArtifactRegistryTestCase(TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.settings_override = override_settings(MODEL_ARTIFACT_ROOT=Path(self.temp_dir.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.artifact_path = Path(self.temp_dir.name) / "ward-risk-v1.joblib"
        self.artifact_path.write_bytes(b"test artifact bytes")
        self.ward = Ward.objects.create(name="Registry Test Ward", county="Migori", ward_code="REG-001")

    def _dataset(self, ref, kind, *, label=False):
        return FeatureDataset.objects.create(
            dataset_ref=ref,
            dataset_kind=kind,
            schema_version="registry-test-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=8,
            feature_keys=["rainfall_total_7d", "rainfall_total_14d"],
            row_count=1,
            lineage_metadata={
                "source_record_refs": [f"source:{ref}"],
                "coverage": {"mode": "source_covered"} if label else {},
                "production_truth_policy": {"eligible": True, "blocked_reason_codes": []},
                "training_label_seeded_demo_row_count": 0,
            },
        )

    def _run(self, version="registry-test-v1", *, seeded=False):
        training = self._dataset(f"{version}-training", FeatureDataset.KIND_TRAINING)
        inference = self._dataset(f"{version}-inference", FeatureDataset.KIND_INFERENCE)
        label = self._dataset(f"{version}-labels", FeatureDataset.KIND_TRAINING, label=True)
        metadata = {
            "algorithm": "logistic_regression",
            "model_family": "ward_risk_classification",
            "promotion_target": "live_baseline",
            "promotion_state": "promoted",
            "phase_4_promotion_gates_passed": True,
            "alert_eligible": True,
            "surveillance_label_dataset_ref": label.dataset_ref,
            "production_truth_policy": {"eligible": not seeded, "blocked_reason_codes": ["seeded"] if seeded else []},
            "code_commit": "abc123",
        }
        if seeded:
            training.lineage_metadata = {
                **training.lineage_metadata,
                "training_label_seeded_demo_row_count": 1,
            }
            training.save(update_fields=["lineage_metadata"])
        return ModelRun.objects.create(
            algorithm_name="logistic-regression-baseline",
            model_version=version,
            status=ModelRun.STATUS_SUCCESS,
            month=8,
            feature_schema_version="registry-test-v1",
            feature_keys=["rainfall_total_7d", "rainfall_total_14d"],
            training_dataset_ref=training.dataset_ref,
            inference_dataset_ref=inference.dataset_ref,
            training_feature_dataset=training,
            inference_feature_dataset=inference,
            training_row_count=1,
            inference_row_count=1,
            evaluation_metrics={"precision": 0.8, "lead_time_recall": 0.7},
            metadata=metadata,
            completed_at=timezone.now(),
        )

    def _register(self, version="registry-test-v1", *, seeded=False):
        return register_model_artifact(
            model_run=self._run(version, seeded=seeded),
            artifact_path=str(self.artifact_path),
            actor="registry-test-operator",
            reason="Register controlled test candidate",
        )

    def _approve(self, entry):
        request_model_approval(entry=entry, actor="review-requester", reason="Request independent review")
        return review_model_artifact(
            entry=entry,
            actor="review-board",
            reason="Evidence reviewed for focused test",
            approve=True,
        )

    def test_registration_persists_candidate_integrity_and_event(self):
        entry = self._register()

        self.assertEqual(entry.approval_state, ModelRegistryApprovalState.NOT_REVIEWED)
        self.assertEqual(entry.lifecycle_state, ModelRegistryLifecycleState.CANDIDATE)
        self.assertEqual(entry.artifact_size_bytes, len(b"test artifact bytes"))
        self.assertEqual(entry.artifact_sha256, hashlib.sha256(b"test artifact bytes").hexdigest())
        event = entry.governance_events.get(event_type=ModelGovernanceEvent.EVENT_REGISTERED)
        self.assertEqual(event.actor, "registry-test-operator")
        self.assertNotIn(str(self.artifact_path), event.evidence_snapshot)

    def test_activation_requires_approval_and_phase4_evidence(self):
        entry = self._register()
        with self.assertRaises(ModelRegistryGovernanceError) as context:
            activate_registered_model(entry=entry, actor="operator", reason="Attempt too early")
        self.assertEqual(context.exception.code, "model_not_approved")

        self._approve(entry)
        activated = activate_registered_model(entry=entry, actor="operator", reason="Activate reviewed artifact")
        self.assertEqual(activated.lifecycle_state, ModelRegistryLifecycleState.ACTIVE)
        self.assertEqual(active_model_registry_entry(), activated)
        self.assertEqual(activated.governance_events.filter(event_type=ModelGovernanceEvent.EVENT_ACTIVATED).count(), 1)
        activated.artifact_sha256 = "0" * 64
        with self.assertRaises(ValidationError):
            activated.save(update_fields=["artifact_sha256", "updated_at"])

    def test_tampered_artifact_blocks_approval(self):
        entry = self._register()
        request_model_approval(entry=entry, actor="review-requester", reason="Request review")
        self.artifact_path.write_bytes(b"tampered artifact bytes")

        with self.assertRaises(ModelRegistryGovernanceError) as context:
            review_model_artifact(entry=entry, actor="review-board", reason="Review tampered file", approve=True)
        self.assertEqual(context.exception.code, "artifact_sha256_mismatch")
        self.assertEqual(model_artifact_approval_blockers(entry)[0], "artifact_sha256_mismatch")

    def test_duplicate_model_run_registration_is_rejected(self):
        run = self._run("duplicate-registration-v1")
        register_model_artifact(
            model_run=run,
            artifact_path=str(self.artifact_path),
            actor="operator",
            reason="Register once",
        )
        with self.assertRaises(ModelRegistryGovernanceError) as context:
            register_model_artifact(
                model_run=run,
                artifact_path=str(self.artifact_path),
                actor="operator",
                reason="Register twice",
            )
        self.assertEqual(context.exception.code, "model_run_already_registered")

    def test_feature_contract_mismatch_blocks_approval(self):
        entry = self._register("contract-mismatch-v1")
        entry.feature_contract = ["different_feature"]
        entry.save(update_fields=["feature_contract", "updated_at"])
        request_model_approval(entry=entry, actor="review-requester", reason="Request review")

        with self.assertRaises(ModelRegistryGovernanceError) as context:
            review_model_artifact(entry=entry, actor="review-board", reason="Mismatch", approve=True)
        self.assertEqual(context.exception.code, "feature_contract_mismatch")

    def test_seeded_training_truth_blocks_approval(self):
        entry = self._register("seeded-approval-blocked-v1", seeded=True)
        request_model_approval(entry=entry, actor="review-requester", reason="Request review")

        with self.assertRaises(ModelRegistryGovernanceError) as context:
            review_model_artifact(entry=entry, actor="review-board", reason="Seeded truth", approve=True)
        self.assertEqual(context.exception.code, "seeded_training_labels_present")

    def test_challenger_state_cannot_be_activated_without_approval(self):
        champion = self._register("champion-v1")
        self._approve(champion)
        activate_registered_model(entry=champion, actor="operator", reason="Activate champion")

        challenger = self._register("challenger-v1")
        designated = designate_model_challenger(
            entry=challenger,
            champion=champion,
            actor="operator",
            reason="Run as benchmark challenger",
        )
        self.assertEqual(designated.lifecycle_state, ModelRegistryLifecycleState.CHALLENGER)
        with self.assertRaises(ModelRegistryGovernanceError) as context:
            activate_registered_model(entry=challenger, actor="operator", reason="Unsafe activation")
        self.assertEqual(context.exception.code, "model_not_approved")

    def test_rollback_requires_explicit_target_and_records_governance_event(self):
        first = self._register("rollback-first-v1")
        self._approve(first)
        activate_registered_model(entry=first, actor="operator", reason="Activate first")
        second = self._register("rollback-second-v1")
        self._approve(second)
        activate_registered_model(entry=second, actor="operator", reason="Activate second")

        with self.assertRaisesMessage(ValueError, "rollback_target_explicit_required"):
            execute_model_rollback(
                rolled_back_from=second,
                reason="Target omission must fail",
                rolled_back_by="operator",
            )
        event = execute_model_rollback(
            rolled_back_from=second,
            rollback_target=first,
            reason="Restore previously approved artifact",
            rolled_back_by="operator",
            materialize_current_risk=False,
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(event.rollback_target_id, first.id)
        self.assertEqual(first.lifecycle_state, ModelRegistryLifecycleState.ACTIVE)
        self.assertEqual(second.lifecycle_state, ModelRegistryLifecycleState.ROLLED_BACK)
        self.assertTrue(ModelGovernanceEvent.objects.filter(event_type=ModelGovernanceEvent.EVENT_ROLLED_BACK).exists())

    def test_governance_events_are_immutable(self):
        entry = self._register()
        event = entry.governance_events.get(event_type=ModelGovernanceEvent.EVENT_REGISTERED)
        event.reason = "changed"
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()

    def test_audit_reports_zero_active_as_not_ready_without_vacuous_failure(self):
        payload = build_model_registry_audit(strict=True)

        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["readiness"]["active_model_count"], 0)
        self.assertFalse(payload["readiness"]["operational_model_available"])
        self.assertEqual(payload["readiness"]["readiness"], NOT_APPROVED_FOR_OPERATIONAL_USE)

    @override_settings(CCHIS_ENVIRONMENT="production")
    def test_production_alert_gate_requires_an_active_registered_model(self):
        run = self._run("production-blocked-v1")
        score = RiskScore.objects.create(
            ward=self.ward,
            model_run=run,
            score=0.7,
            risk_level=Ward.RISK_HIGH,
            source=RiskScore.SOURCE_MODEL,
            model_version=run.model_version,
        )

        blockers = production_alert_eligibility_blockers(score)

        self.assertIn(PRODUCTION_ALERT_ACTIVE_REGISTRY_REQUIRED, blockers)
        self.assertIsNone(active_model_registry_entry())

    @override_settings(CCHIS_ENVIRONMENT="production")
    def test_production_scoring_persists_a_blocked_run_without_scores_when_registry_is_empty(self):
        training_dataset = self._dataset("production-scoring-training", FeatureDataset.KIND_TRAINING)
        inference_dataset = self._dataset("production-scoring-inference", FeatureDataset.KIND_INFERENCE)
        training = SimpleNamespace(
            feature_dataset=training_dataset,
            rows=[],
            surveillance_label_dataset=None,
        )
        inference = SimpleNamespace(
            feature_dataset=inference_dataset,
            rows=[],
            rainfall_ingestion_run=None,
            population_exposure_feature_dataset=None,
        )

        with patch("risk.ml.pipeline.build_training_feature_dataset", return_value=training), patch(
            "risk.ml.pipeline.build_inference_feature_dataset", return_value=inference
        ):
            scores = run_mock_prediction_pipeline(
                month=8,
                model_version="production-scoring-blocked-v1",
                trigger_alerts=True,
            )

        self.assertEqual(scores, [])
        run = ModelRun.objects.get(model_version="production-scoring-blocked-v1")
        self.assertEqual(run.status, ModelRun.STATUS_FAILED)
        self.assertIn(PRODUCTION_ALERT_ACTIVE_REGISTRY_REQUIRED, run.evaluation_metrics["blocked_reason_codes"])
        self.assertFalse(RiskScore.objects.filter(model_run=run).exists())

    def test_database_rejects_unapproved_active_state(self):
        run = self._run("constraint-v1")
        with self.assertRaises(IntegrityError):
            ModelRegistryEntry.objects.create(
                model_run=run,
                algorithm="logistic_regression",
                model_version=run.model_version,
                lifecycle_state=ModelRegistryLifecycleState.ACTIVE,
                promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED,
                active_from=timezone.now(),
            )

    def test_database_enforces_one_active_entry_per_deployment_target(self):
        first = self._register("active-target-first-v1")
        self._approve(first)
        activate_registered_model(entry=first, actor="operator", reason="Activate first target")
        second = self._register("active-target-second-v1")
        self._approve(second)
        promotion_event = ModelPromotionEvent.objects.create(
            registry_entry=second,
            model_run=second.model_run,
            source="focused-test",
            promoted_by="operator",
            active_from=timezone.now(),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ModelRegistryEntry.objects.filter(id=second.id).update(
                    lifecycle_state=ModelRegistryLifecycleState.ACTIVE,
                    promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED,
                    promotion_event_id=promotion_event.id,
                    active_from=timezone.now(),
                    active_until=None,
                )
