from django.conf import settings
from django.test import SimpleTestCase

from accounts.models import User
from risk.models import PopulationExposureSource, SurveillanceSource
from risk.source_data.phase0 import (
    APPROVAL_STATES,
    FEED_SCOPE_LATER,
    FEED_SCOPE_MVP,
    MAKER_CHECKER_POLICY,
    RETENTION_POLICY,
    RISKY_IMPORT_CATEGORIES,
    ROLE_PERMISSION_MAP,
    SOURCE_DATA_FEED_DECISIONS,
    SOURCE_DATA_UPLOAD_STORAGE_DECISION,
    THREAT_MODEL,
    UPLOAD_LIFECYCLE_STATUSES,
    UPLOAD_STATUS_TRANSITIONS,
    UX_BLUEPRINT,
    feed_decision_for_key,
    later_feed_decisions,
    mvp_feed_decisions,
    validate_phase0_contract,
)


class SourceDataPhaseZeroContractTests(SimpleTestCase):
    def test_phase_zero_contract_is_self_consistent(self):
        self.assertEqual(validate_phase0_contract(), [])

    def test_mvp_feed_scope_and_source_type_mapping_are_locked(self):
        expected_mvp_keys = {
            "surveillance_weekly_aggregate",
            "surveillance_daily_aggregate",
            "surveillance_backfill",
            "population_baseline",
            "gridded_population",
            "settlement_layer",
            "wash_vulnerability_layer",
            "water_body_distance_layer",
            "flood_exposure_layer",
            "facility_catchment_mapping",
            "facility_readiness_snapshot",
        }
        self.assertEqual({feed.feed_key for feed in mvp_feed_decisions()}, expected_mvp_keys)
        self.assertTrue(all(feed.scope == FEED_SCOPE_MVP for feed in mvp_feed_decisions()))
        self.assertTrue(all(feed.scope == FEED_SCOPE_LATER for feed in later_feed_decisions()))

        self.assertEqual(
            feed_decision_for_key("surveillance_weekly_aggregate").source_type,
            SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
        )
        self.assertEqual(
            feed_decision_for_key("surveillance_daily_aggregate").source_type,
            SurveillanceSource.SOURCE_TYPE_DAILY_AGGREGATE,
        )
        self.assertEqual(
            feed_decision_for_key("surveillance_backfill").source_type,
            SurveillanceSource.SOURCE_TYPE_CSV_BACKFILL,
        )
        self.assertEqual(
            feed_decision_for_key("population_baseline").source_type,
            PopulationExposureSource.SOURCE_TYPE_POPULATION_BASELINE,
        )
        self.assertEqual(
            feed_decision_for_key("facility_catchment_mapping").source_type,
            PopulationExposureSource.SOURCE_TYPE_CATCHMENT_MAPPING,
        )
        self.assertTrue(feed_decision_for_key("facility_readiness_snapshot").requires_new_ingestion_path)

    def test_role_permissions_and_maker_checker_policy_are_locked(self):
        self.assertIn("source_data:replace_import", ROLE_PERMISSION_MAP[User.ROLE_ADMIN])
        self.assertIn("source_data:manage_retention", ROLE_PERMISSION_MAP[User.ROLE_ADMIN])
        self.assertIn("source_data:confirm_import", ROLE_PERMISSION_MAP[User.ROLE_SUPERVISOR])
        self.assertIn("source_data:request_approval", ROLE_PERMISSION_MAP[User.ROLE_SUPERVISOR])
        self.assertEqual(
            ROLE_PERMISSION_MAP[User.ROLE_ANALYST],
            ("source_data:view", "source_data:download_template"),
        )
        self.assertEqual(ROLE_PERMISSION_MAP[User.ROLE_CHV], ())
        self.assertEqual(ROLE_PERMISSION_MAP["SUPERUSER"], ("source_data:emergency_override",))

        risky_policy = MAKER_CHECKER_POLICY["risky_import"]
        self.assertTrue(risky_policy["approval_required"])
        self.assertFalse(risky_policy["self_approval_allowed"])
        self.assertIn(User.ROLE_ADMIN, risky_policy["second_approvers"])
        self.assertEqual(
            set(RISKY_IMPORT_CATEGORIES),
            {
                "historical_backfill",
                "replacement_import",
                "replay_import",
                "production_surveillance_truth",
                "unusually_large_source_delta",
                "production_downstream_rebuild",
            },
        )
        self.assertEqual(
            set(APPROVAL_STATES),
            {"not_required", "pending", "approved", "rejected", "expired"},
        )

    def test_lifecycle_retention_and_shared_storage_decisions_are_explicit(self):
        self.assertEqual(
            UPLOAD_LIFECYCLE_STATUSES,
            (
                "draft",
                "uploaded",
                "validating",
                "validation_failed",
                "ready_for_confirmation",
                "confirming",
                "imported",
                "import_failed",
                "cancelled",
                "superseded",
            ),
        )
        self.assertIn("imported", UPLOAD_STATUS_TRANSITIONS["confirming"])
        self.assertEqual(UPLOAD_STATUS_TRANSITIONS["cancelled"], ())
        self.assertEqual(UPLOAD_STATUS_TRANSITIONS["superseded"], ())

        raw_retention = RETENTION_POLICY["raw_upload_artifacts"]
        diagnostics_retention = RETENTION_POLICY["rejected_row_diagnostics"]
        audit_retention = RETENTION_POLICY["metadata_hashes_counts_audit_events"]
        self.assertEqual(raw_retention["minimum_days"], 30)
        self.assertEqual(raw_retention["maximum_days"], 90)
        self.assertLessEqual(diagnostics_retention["default_days"], raw_retention["default_days"])
        self.assertFalse(audit_retention["contains_raw_source_values"])

        self.assertEqual(SOURCE_DATA_UPLOAD_STORAGE_DECISION["storage_backend"], "shared_filesystem")
        self.assertEqual(SOURCE_DATA_UPLOAD_STORAGE_DECISION["docker_volume"], "source_uploads")
        self.assertTrue(SOURCE_DATA_UPLOAD_STORAGE_DECISION["durable_between_web_and_worker"])
        self.assertFalse(SOURCE_DATA_UPLOAD_STORAGE_DECISION["local_process_temp_files_allowed_for_queued_imports"])
        self.assertTrue(SOURCE_DATA_UPLOAD_STORAGE_DECISION["hash_must_match_validated_file"])

    def test_runtime_upload_storage_defaults_match_phase_zero_decision(self):
        self.assertEqual(settings.SOURCE_DATA_UPLOAD_STORAGE_BACKEND, "shared_filesystem")
        self.assertEqual(str(settings.SOURCE_DATA_UPLOAD_ROOT), "/var/lib/cchis/source_uploads")
        self.assertEqual(settings.SOURCE_DATA_RAW_UPLOAD_RETENTION_DAYS, 60)
        self.assertEqual(settings.SOURCE_DATA_REJECTED_DIAGNOSTIC_RETENTION_DAYS, 30)
        self.assertEqual(settings.SOURCE_DATA_METADATA_AUDIT_RETENTION_DAYS, 730)

    def test_threat_model_and_ux_blueprint_cover_phase_zero_acceptance(self):
        threat_ids = {threat["risk_id"] for threat in THREAT_MODEL}
        self.assertTrue(
            {
                "malicious_file",
                "accidental_pii",
                "stale_source_data",
                "duplicate_import",
                "unauthorized_replacement",
                "downstream_leakage",
            }.issubset(threat_ids)
        )
        accidental_pii = next(threat for threat in THREAT_MODEL if threat["risk_id"] == "accidental_pii")
        self.assertIn("sample_first_rows_and_bounded_random_rows_for_pii_values", accidental_pii["mitigations"])

        self.assertEqual(UX_BLUEPRINT["navigation"]["href"], "/source-data")
        self.assertIn(User.ROLE_ADMIN, UX_BLUEPRINT["navigation"]["roles"])
        self.assertIn(User.ROLE_ANALYST, UX_BLUEPRINT["navigation"]["roles"])
        self.assertEqual(
            set(UX_BLUEPRINT["views"].keys()),
            {"overview", "feed_detail", "upload_wizard", "validation_summary", "import_result"},
        )
        self.assertEqual(
            set(UX_BLUEPRINT["states"].keys()),
            {"empty", "loading", "failed", "stale", "demo_backed", "success"},
        )
        self.assertIn("download_template", UX_BLUEPRINT["views"]["overview"]["row_actions"])
        self.assertIn("approval_state", UX_BLUEPRINT["views"]["upload_wizard"]["required_controls"])

    def test_all_feed_keys_are_unique(self):
        feed_keys = [feed.feed_key for feed in SOURCE_DATA_FEED_DECISIONS]
        self.assertEqual(len(feed_keys), len(set(feed_keys)))
