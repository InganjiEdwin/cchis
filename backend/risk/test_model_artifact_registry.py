import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from datetime import date, datetime, timedelta
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from unittest import skipUnless
from django.utils import timezone

from accounts.models import User
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
from risk.ml.model_artifacts import inspect_artifact
from risk.ml.registry import (
    active_model_registry_entry,
    execute_model_rollback,
    registered_inference_scoring_blockers,
)
from risk.ml.pipeline import run_mock_prediction_pipeline
from risk.models import (
    FeatureDataset,
    FeatureDatasetRow,
    ClimateRecord,
    ClimateRecordQualityFlag,
    ClimateRecordType,
    IngestionRun,
    ModelGovernanceEvent,
    ModelPromotionEvent,
    ModelRegistryApprovalState,
    ModelRegistryEntry,
    ModelRegistryLifecycleState,
    ModelRegistryPromotionState,
    ModelRun,
    RiskScore,
    PopulationBaselineRecord,
    PopulationExposureFreshness,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
    SurveillanceCaseClass,
    SurveillanceDiseaseCategory,
    SurveillanceFreshnessState,
    SurveillanceIngestionRun,
    SurveillanceLabelWindow,
    SurveillanceOutbreakLabel,
    SurveillanceRecord,
    SurveillanceSource,
    SurveillanceSourceKind,
    SurveillanceTruthLevel,
    Ward,
)
from risk.truth_policy import (
    PRODUCTION_ALERT_ACTIVE_REGISTRY_REQUIRED,
    PRODUCTION_REGISTERED_INFERENCE_PATH_REQUIRED,
    production_alert_eligibility_blockers,
    strict_persisted_truth_blockers,
)


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

        self.registry_operator = User.objects.create_user(
            username="registry-operator",
            password="test-password",
            role=User.ROLE_ADMIN,
        )
        self.review_requester = User.objects.create_user(
            username="review-requester",
            password="test-password",
            role=User.ROLE_ANALYST,
        )
        self.review_board = User.objects.create_user(
            username="review-board",
            password="test-password",
            role=User.ROLE_ADMIN,
        )

    def _source_records(self, version):
        period_start = date(2024, 8, 1)
        period_end = date(2024, 8, 7)
        now = timezone.now()
        surveillance_source = SurveillanceSource.objects.create(
            source_name=f"County surveillance {version}",
            source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
            source_timestamp=now,
            reporting_period_start=period_start,
            reporting_period_end=period_end,
            source_ref=f"county-surveillance:{version}",
            metadata={"source_credibility": "county-surveillance"},
        )
        surveillance_run = SurveillanceIngestionRun.objects.create(
            source=surveillance_source,
            status=SurveillanceIngestionRun.STATUS_SUCCESS,
            source_name=surveillance_source.source_name,
            source_type=surveillance_source.source_type,
            source_timestamp=now,
            reporting_period_start=period_start,
            reporting_period_end=period_end,
            source_ref=surveillance_source.source_ref,
            adapter_key="focused-source-backed-test",
            input_ref=f"source-input:{version}",
            execution_mode=SurveillanceIngestionRun.EXECUTION_MANUAL,
            records_seen=1,
            records_loaded=1,
            source_metadata={"source_credibility": "county-surveillance"},
            completed_at=now,
        )
        surveillance_record = SurveillanceRecord.objects.create(
            ward=self.ward,
            ingestion_run=surveillance_run,
            source=surveillance_source,
            disease_category=SurveillanceDiseaseCategory.DIARRHEAL,
            case_class=SurveillanceCaseClass.SUSPECTED,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            count_value=2,
            reporting_period_start=period_start,
            reporting_period_end=period_end,
            reporting_granularity="week",
            truth_level=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
            source_name=surveillance_source.source_name,
            source_kind=SurveillanceSourceKind.LIVE,
            freshness_state=SurveillanceFreshnessState.FRESH,
            source_ref=f"surveillance-record:{version}",
            raw_payload={"source_credibility": "county-surveillance"},
        )

        rainfall_run = IngestionRun.objects.create(
            run_type=IngestionRun.RUN_TYPE_RAINFALL,
            status=IngestionRun.STATUS_SUCCESS,
            source_mode="chirps",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_name="CHIRPS",
            source_priority=["chirps"],
            requested_wards=[self.ward.id],
            source_timestamp=now,
            freshness_state=IngestionRun.FRESHNESS_FRESH,
            records_seen=1,
            records_loaded=1,
            lineage_metadata={"provider": "CHIRPS", "variant": "sat"},
            completed_at=now,
        )
        climate_record = ClimateRecord.objects.create(
            ward=self.ward,
            ingestion_run=rainfall_run,
            record_type=ClimateRecordType.OBSERVED,
            source_provider="CHIRPS",
            source_kind=IngestionRun.SOURCE_KIND_LIVE,
            source_mode="sat",
            valid_date=period_end,
            observed_timestamp=now,
            rainfall_mm=12.5,
            quality_flag=ClimateRecordQualityFlag.ACCEPTED,
            fallback_flag=False,
            source_run=f"chirps-run:{version}",
            source_ref=f"chirps-record:{version}",
            identity_key=f"chirps|sat|{version}|{self.ward.id}|{period_end.isoformat()}",
            lineage_metadata={"provider": "CHIRPS", "variant": "sat"},
            raw_payload={"source": "CHIRPS", "variant": "sat"},
        )

        population_source = PopulationExposureSource.objects.create(
            source_name=f"Population baseline {version}",
            source_type=PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE,
            source_timestamp=now,
            release_version="2024-test",
            source_ref=f"population-source:{version}",
        )
        population_run = PopulationExposureIngestionRun.objects.create(
            source=population_source,
            status=PopulationExposureIngestionRun.STATUS_SUCCESS,
            source_name=population_source.source_name,
            source_type=population_source.source_type,
            source_timestamp=now,
            release_version="2024-test",
            source_ref=population_source.source_ref,
            adapter_key="focused-source-backed-test",
            input_ref=f"population-input:{version}",
            execution_mode=PopulationExposureIngestionRun.EXECUTION_MANUAL,
            records_seen=1,
            records_loaded=1,
            completed_at=now,
        )
        population_record = PopulationBaselineRecord.objects.create(
            ward=self.ward,
            ingestion_run=population_run,
            source=population_source,
            recorded_at=now,
            population_total=1200,
            population_under_five=120,
            truth_class=PopulationExposureTruth.DIRECT_POPULATION_BASELINE,
            source_name=population_source.source_name,
            source_kind=PopulationExposureSourceKind.LIVE,
            freshness_state=PopulationExposureFreshness.FRESH,
            release_version="2024-test",
            source_ref=f"population-record:{version}",
            raw_payload={"source": "population-baseline"},
        )
        return surveillance_record, climate_record, population_record, period_start, period_end

    def _bare_dataset(self, ref, kind):
        return FeatureDataset.objects.create(
            dataset_ref=ref,
            dataset_kind=kind,
            schema_version="registry-test-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=8,
            feature_keys=["rainfall_total_7d", "rainfall_total_14d"],
            row_count=0,
            lineage_metadata={"production_truth_policy": {"eligible": False, "blocked_reason_codes": []}},
        )

    def _run(self, version="registry-test-v1", *, seeded=False):
        surveillance_record, climate_record, population_record, period_start, period_end = self._source_records(version)
        surveillance_ref = f"surveillance_record:{surveillance_record.id}"
        climate_ref = f"climate_record:{climate_record.id}"
        population_ref = f"population_baseline_record:{population_record.id}"
        feature_keys = ["rainfall_total_7d", "rainfall_total_14d"]
        label_ref = f"{version}-labels"
        common_lineage = {
            "production_truth_policy": {"eligible": True, "blocked_reason_codes": []},
            "training_label_seeded_demo_row_count": 0,
        }
        training = FeatureDataset.objects.create(
            dataset_ref=f"{version}-training",
            dataset_kind=FeatureDataset.KIND_TRAINING,
            schema_version="registry-test-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=8,
            feature_keys=feature_keys,
            row_count=1,
            lineage_metadata={
                **common_lineage,
                "source_record_refs": [surveillance_ref],
                "population_baseline_record_refs": [population_ref],
                "surveillance_label_dataset_ref": label_ref,
            },
        )
        inference = FeatureDataset.objects.create(
            dataset_ref=f"{version}-inference",
            dataset_kind=FeatureDataset.KIND_INFERENCE,
            schema_version="registry-test-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=8,
            feature_keys=feature_keys,
            row_count=1,
            lineage_metadata={
                **common_lineage,
                "source_record_refs": [climate_ref],
                "population_baseline_record_refs": [population_ref],
            },
        )
        label = FeatureDataset.objects.create(
            dataset_ref=label_ref,
            dataset_kind=FeatureDataset.KIND_TRAINING,
            schema_version="registry-test-v1",
            source_kind=FeatureDataset.SOURCE_KIND_LIVE,
            month=8,
            feature_keys=feature_keys,
            row_count=1,
            lineage_metadata={
                **common_lineage,
                "source_record_refs": [surveillance_ref],
                "coverage": {"record_count": 1, "source_record_refs": [surveillance_ref]},
            },
        )
        label_window = SurveillanceLabelWindow.objects.create(
            ward=self.ward,
            feature_dataset=label,
            schema_version="registry-test-v1",
            dataset_ref=label.dataset_ref,
            label_window_start=period_start,
            label_window_end=period_end,
            suspected_case_count=2,
            confirmed_case_count=0,
            proxy_case_count=0,
            outbreak_label=SurveillanceOutbreakLabel.ACTIVE,
            label_truth_level=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
            generation_mode="source_backed_test_fixture",
            source_coverage_summary={"record_count": 1, "source_record_refs": [surveillance_ref]},
            generated_from_record_refs=[surveillance_ref],
            source_record_count=1,
        )
        FeatureDatasetRow.objects.create(
            dataset=training,
            ward=self.ward,
            ward_name_snapshot=self.ward.name,
            month=8,
            feature_values={
                "source_record_refs": [surveillance_ref, f"surveillance_label_window:{label_window.id}"],
                "population_baseline_record_refs": [population_ref],
                "population_total": population_record.population_total,
            },
            label=1,
        )
        FeatureDatasetRow.objects.create(
            dataset=inference,
            ward=self.ward,
            ward_name_snapshot=self.ward.name,
            month=8,
            feature_values={
                "source_record_refs": [climate_ref],
                "population_baseline_record_refs": [population_ref],
                "population_total": population_record.population_total,
            },
        )
        FeatureDatasetRow.objects.create(
            dataset=label,
            ward=self.ward,
            ward_name_snapshot=self.ward.name,
            month=8,
            feature_values={
                "source_record_refs": [surveillance_ref],
                "surveillance_label_window_refs": [f"surveillance_label_window:{label_window.id}"],
                "suspected_case_count": label_window.suspected_case_count,
                "confirmed_case_count": label_window.confirmed_case_count,
                "proxy_case_count": label_window.proxy_case_count,
                "source_record_count": label_window.source_record_count,
                "label_truth_level": label_window.label_truth_level,
                "outbreak_label": label_window.outbreak_label,
            },
            label=1,
        )
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
            rainfall_ingestion_run=climate_record.ingestion_run,
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
            actor=self.registry_operator.username,
            reason="Register controlled test candidate",
        )

    def _approve(self, entry):
        request_model_approval(entry=entry, actor=self.review_requester.username, reason="Request independent review")
        return review_model_artifact(
            entry=entry,
            actor=self.review_board.username,
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
        self.assertEqual(event.actor, self.registry_operator.username)
        self.assertEqual(event.actor_user_id, self.registry_operator.id)
        self.assertNotIn(str(self.artifact_path), event.evidence_snapshot)

    def test_registration_rejects_missing_unsupported_and_outside_root_artifacts(self):
        run = self._run("artifact-validation-v1")
        with self.assertRaises(ModelRegistryGovernanceError) as missing:
            register_model_artifact(
                model_run=run,
                artifact_path=str(Path(self.temp_dir.name) / "missing.joblib"),
                actor=self.registry_operator.username,
                reason="Reject missing artifact",
            )
        self.assertEqual(missing.exception.code, "artifact_not_found")

        unsupported_path = Path(self.temp_dir.name) / "unsupported.txt"
        unsupported_path.write_bytes(b"unsupported")
        with self.assertRaises(ModelRegistryGovernanceError) as unsupported:
            register_model_artifact(
                model_run=self._run("artifact-unsupported-v1"),
                artifact_path=str(unsupported_path),
                actor=self.registry_operator.username,
                reason="Reject unsupported format",
            )
        self.assertEqual(unsupported.exception.code, "artifact_format_unsupported")

        with TemporaryDirectory() as outside_dir:
            outside_path = Path(outside_dir) / "outside.joblib"
            outside_path.write_bytes(b"outside")
            with self.assertRaises(ModelRegistryGovernanceError) as outside:
                register_model_artifact(
                    model_run=self._run("artifact-outside-root-v1"),
                    artifact_path=str(outside_path),
                    actor=self.registry_operator.username,
                    reason="Reject outside-root artifact",
                )
        self.assertEqual(outside.exception.code, "artifact_outside_controlled_root")
        scheme_inspection = inspect_artifact(
            location="s3://bucket/model.joblib",
            expected_sha256="0" * 64,
        )
        self.assertEqual(scheme_inspection["blockers"][0]["code"], "artifact_storage_scheme_unsupported")

    def test_genuinely_source_backed_fixture_passes_approval_checks(self):
        entry = self._register("source-backed-approval-v1")
        self.assertEqual(model_artifact_approval_blockers(entry), [])
        approved = self._approve(entry)
        self.assertEqual(approved.approval_state, ModelRegistryApprovalState.APPROVED)

    def test_fake_live_lineage_cannot_support_approval(self):
        entry = self._register("fake-live-lineage-v1")
        training = entry.model_run.training_feature_dataset
        training.lineage_metadata = {
            **training.lineage_metadata,
            "source_record_refs": ["surveillance_record:999999999"],
        }
        training.save(update_fields=["lineage_metadata"])
        request_model_approval(entry=entry, actor=self.review_requester.username, reason="Request review")

        with self.assertRaises(ModelRegistryGovernanceError) as context:
            review_model_artifact(
                entry=entry,
                actor=self.review_board.username,
                reason="Reject invented lineage",
                approve=True,
            )
        self.assertEqual(context.exception.code, "production_canonical_reference_invalid")

    def test_strict_truth_runs_outside_production_and_blocks_changed_source(self):
        entry = self._register("strict-local-v1")
        self._approve(entry)
        ClimateRecord.objects.filter(ingestion_run=entry.model_run.rainfall_ingestion_run).update(
            quality_flag=ClimateRecordQualityFlag.DEGRADED_FALLBACK,
        )

        with self.assertRaises(ModelRegistryGovernanceError) as context:
            activate_registered_model(
                entry=entry,
                actor=self.review_board.username,
                reason="Strict local activation must fail",
            )
        self.assertEqual(context.exception.code, "production_canonical_reference_invalid")
        self.assertTrue(strict_persisted_truth_blockers(entry.model_run))

    def test_self_approval_and_unauthorized_actor_are_rejected(self):
        entry = self._register("identity-controls-v1")
        request_model_approval(entry=entry, actor=self.review_board.username, reason="Request review")
        with self.assertRaises(ModelRegistryGovernanceError) as self_approval:
            review_model_artifact(
                entry=entry,
                actor=self.review_board.username,
                reason="Requester cannot approve",
                approve=True,
            )
        self.assertEqual(self_approval.exception.code, "governance_self_approval_forbidden")

        unauthorized = User.objects.create_user(
            username="unauthorized-reviewer",
            password="test-password",
            role=User.ROLE_SUPERVISOR,
        )
        with self.assertRaises(ModelRegistryGovernanceError) as unauthorized_error:
            review_model_artifact(
                entry=entry,
                actor=unauthorized.username,
                reason="Unauthorized review",
                approve=True,
            )
        self.assertEqual(unauthorized_error.exception.code, "governance_actor_role_not_authorized")

    def test_governance_event_queryset_mutation_and_deletion_are_rejected(self):
        entry = self._register("event-queryset-immutability-v1")
        events = ModelGovernanceEvent.objects.filter(registry_entry=entry)
        with self.assertRaises(ValidationError):
            events.update(reason="tampered")
        with self.assertRaises(ValidationError):
            events.delete()

    def test_valid_active_entry_gets_path_blocker_not_missing_registry_blocker(self):
        entry = self._register("registered-path-v1")
        self._approve(entry)
        activate_registered_model(entry=entry, actor=self.review_board.username, reason="Activate path test")
        training = SimpleNamespace(feature_dataset=entry.model_run.training_feature_dataset)
        inference = SimpleNamespace(
            feature_dataset=entry.model_run.inference_feature_dataset,
            rainfall_ingestion_run=entry.model_run.rainfall_ingestion_run,
        )

        blockers = registered_inference_scoring_blockers(
            model_version=entry.model_version,
            algorithm="logistic_regression",
            feature_contract=list(entry.feature_contract),
            training_dataset=training,
            inference_dataset=inference,
        )

        self.assertIn(PRODUCTION_REGISTERED_INFERENCE_PATH_REQUIRED, blockers)
        self.assertNotIn(PRODUCTION_ALERT_ACTIVE_REGISTRY_REQUIRED, blockers)

    def test_activation_requires_approval_and_phase4_evidence(self):
        entry = self._register()
        with self.assertRaises(ModelRegistryGovernanceError) as context:
            activate_registered_model(entry=entry, actor=self.review_board.username, reason="Attempt too early")
        self.assertEqual(context.exception.code, "model_not_approved")

        self._approve(entry)
        activated = activate_registered_model(entry=entry, actor=self.review_board.username, reason="Activate reviewed artifact")
        self.assertEqual(activated.lifecycle_state, ModelRegistryLifecycleState.ACTIVE)
        self.assertEqual(active_model_registry_entry(), activated)
        self.assertEqual(activated.governance_events.filter(event_type=ModelGovernanceEvent.EVENT_ACTIVATED).count(), 1)
        activated.artifact_sha256 = "0" * 64
        with self.assertRaises(ValidationError):
            activated.save(update_fields=["artifact_sha256", "updated_at"])

    def test_tampered_artifact_blocks_approval(self):
        entry = self._register()
        request_model_approval(entry=entry, actor=self.review_requester.username, reason="Request review")
        self.artifact_path.write_bytes(b"tampered artifact bytes")

        with self.assertRaises(ModelRegistryGovernanceError) as context:
            review_model_artifact(entry=entry, actor=self.review_board.username, reason="Review tampered file", approve=True)
        self.assertEqual(context.exception.code, "artifact_sha256_mismatch")
        self.assertEqual(model_artifact_approval_blockers(entry)[0], "artifact_sha256_mismatch")

    def test_duplicate_model_run_registration_is_rejected(self):
        run = self._run("duplicate-registration-v1")
        register_model_artifact(
            model_run=run,
            artifact_path=str(self.artifact_path),
            actor=self.registry_operator.username,
            reason="Register once",
        )
        with self.assertRaises(ModelRegistryGovernanceError) as context:
            register_model_artifact(
                model_run=run,
                artifact_path=str(self.artifact_path),
                actor=self.registry_operator.username,
                reason="Register twice",
            )
        self.assertEqual(context.exception.code, "model_run_already_registered")

    def test_feature_contract_mismatch_blocks_approval(self):
        entry = self._register("contract-mismatch-v1")
        entry.feature_contract = ["different_feature"]
        entry.save(update_fields=["feature_contract", "updated_at"])
        request_model_approval(entry=entry, actor=self.review_requester.username, reason="Request review")

        with self.assertRaises(ModelRegistryGovernanceError) as context:
            review_model_artifact(entry=entry, actor=self.review_board.username, reason="Mismatch", approve=True)
        self.assertEqual(context.exception.code, "feature_contract_mismatch")

    def test_seeded_training_truth_blocks_approval(self):
        entry = self._register("seeded-approval-blocked-v1", seeded=True)
        request_model_approval(entry=entry, actor=self.review_requester.username, reason="Request review")

        with self.assertRaises(ModelRegistryGovernanceError) as context:
            review_model_artifact(entry=entry, actor=self.review_board.username, reason="Seeded truth", approve=True)
        self.assertEqual(context.exception.code, "seeded_training_labels_present")

    def test_challenger_state_cannot_be_activated_without_approval(self):
        champion = self._register("champion-v1")
        self._approve(champion)
        activate_registered_model(entry=champion, actor=self.review_board.username, reason="Activate champion")

        challenger = self._register("challenger-v1")
        designated = designate_model_challenger(
            entry=challenger,
            champion=champion,
            actor=self.review_board.username,
            reason="Run as benchmark challenger",
        )
        self.assertEqual(designated.lifecycle_state, ModelRegistryLifecycleState.CHALLENGER)
        with self.assertRaises(ModelRegistryGovernanceError) as context:
            activate_registered_model(entry=challenger, actor=self.review_board.username, reason="Unsafe activation")
        self.assertEqual(context.exception.code, "model_not_approved")

    def test_rollback_requires_explicit_target_and_records_governance_event(self):
        first = self._register("rollback-first-v1")
        self._approve(first)
        activate_registered_model(entry=first, actor=self.review_board.username, reason="Activate first")
        second = self._register("rollback-second-v1")
        self._approve(second)
        activate_registered_model(entry=second, actor=self.review_board.username, reason="Activate second")

        with self.assertRaisesMessage(ValueError, "rollback_target_explicit_required"):
            execute_model_rollback(
                rolled_back_from=second,
                reason="Target omission must fail",
                rolled_back_by=self.review_board.username,
            )
        event = execute_model_rollback(
            rolled_back_from=second,
            rollback_target=first,
            reason="Restore previously approved artifact",
            rolled_back_by=self.review_board.username,
            materialize_current_risk=False,
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(event.rollback_target_id, first.id)
        self.assertEqual(first.lifecycle_state, ModelRegistryLifecycleState.ACTIVE)
        self.assertEqual(second.lifecycle_state, ModelRegistryLifecycleState.ROLLED_BACK)
        self.assertTrue(ModelGovernanceEvent.objects.filter(event_type=ModelGovernanceEvent.EVENT_ROLLED_BACK).exists())
        target_rollback_event = first.governance_events.filter(
            event_type=ModelGovernanceEvent.EVENT_ROLLED_BACK,
        ).latest("id")
        self.assertEqual(
            target_rollback_event.previous_lifecycle_state,
            ModelRegistryLifecycleState.RETIRED,
        )
        self.assertEqual(target_rollback_event.actor_user_id, self.review_board.id)
        audit = build_model_registry_audit(strict=True)
        self.assertEqual(audit["overall_status"], "pass", audit)
        self.assertTrue(audit["readiness"]["operational_model_available"])

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
        training_dataset = self._bare_dataset("production-scoring-training", FeatureDataset.KIND_TRAINING)
        inference_dataset = self._bare_dataset("production-scoring-inference", FeatureDataset.KIND_INFERENCE)
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
        activate_registered_model(entry=first, actor=self.review_board.username, reason="Activate first target")
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


@skipUnless(connection.vendor == "postgresql", "Concurrent activation coverage requires PostgreSQL.")
class ConcurrentModelActivationTestCase(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.ward = Ward.objects.create(name="Concurrent Registry Ward", county="Migori", ward_code="REG-CON")
        self.actor_one = User.objects.create_user(
            username="concurrent-operator-one",
            password="test-password",
            role=User.ROLE_ADMIN,
        )
        self.actor_two = User.objects.create_user(
            username="concurrent-operator-two",
            password="test-password",
            role=User.ROLE_ADMIN,
        )
        self.entries = []
        for version in ("concurrent-one-v1", "concurrent-two-v1"):
            run = ModelRun.objects.create(
                algorithm_name="logistic-regression-baseline",
                model_version=version,
                status=ModelRun.STATUS_SUCCESS,
                feature_schema_version="concurrent-v1",
                metadata={
                    "algorithm": "logistic_regression",
                    "promotion_target": "live_baseline",
                    "promotion_state": "promoted",
                    "phase_4_promotion_gates_passed": True,
                    "alert_eligible": True,
                },
            )
            self.entries.append(
                ModelRegistryEntry.objects.create(
                    algorithm="logistic_regression",
                    model_family="ward_risk_classification",
                    model_version=version,
                    feature_schema_version="concurrent-v1",
                    model_run=run,
                    approval_state=ModelRegistryApprovalState.APPROVED,
                    lifecycle_state=ModelRegistryLifecycleState.CANDIDATE,
                    promotion_state=ModelRegistryPromotionState.CANDIDATE,
                    deployment_target="live_baseline",
                    approved_at=timezone.now(),
                    approved_by=self.actor_one.username,
                    approval_reason="PostgreSQL concurrency fixture",
                    feature_contract=[],
                    artifact_format="joblib",
                    artifact_sha256="0" * 64,
                    training_label_dataset_ref="concurrency-labels",
                )
            )

    def _activate(self, entry_id, actor):
        close_old_connections()
        try:
            activate_registered_model(
                entry=ModelRegistryEntry.objects.get(id=entry_id),
                actor=actor,
                reason="Concurrent activation safety test",
            )
            return "success"
        except Exception as error:  # pragma: no cover - failure detail is asserted below
            return getattr(error, "code", type(error).__name__)
        finally:
            close_old_connections()

    def test_concurrent_activation_leaves_one_active_entry(self):
        with patch("risk.ml.model_registry_governance.model_artifact_approval_blockers", return_value=[]), patch(
            "risk.truth_policy.strict_persisted_truth_blockers", return_value=[]
        ), patch(
            "risk.ml.model_registry_governance.model_run_has_phase_4_promotion_metadata", return_value=True
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(
                        self._activate,
                        [self.entries[0].id, self.entries[1].id],
                        [self.actor_one.username, self.actor_two.username],
                    )
                )

        self.assertEqual(results, ["success", "success"])
        self.assertEqual(
            ModelRegistryEntry.objects.filter(
                deployment_target="live_baseline",
                lifecycle_state=ModelRegistryLifecycleState.ACTIVE,
            ).count(),
            1,
        )
