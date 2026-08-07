from types import SimpleNamespace

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, override_settings

from risk.lead_time_features import build_lead_time_feature_dataset
from risk.surveillance_labels import (
    build_surveillance_label_dataset,
    build_surveillance_lead_time_label_dataset,
)
from risk.truth_policy import (
    PRODUCTION_SEEDED_TRUTH_BLOCKED,
    PRODUCTION_STATIC_FALLBACK_BLOCKED,
    ProductionTruthPolicyError,
    production_feature_dataset_blockers,
    production_model_run_blockers,
    require_demo_data_allowed,
)


def feature_dataset(*, source_kind="LIVE", lineage_metadata=None, dataset_ref="dataset-ref"):
    return SimpleNamespace(
        source_kind=source_kind,
        lineage_metadata=lineage_metadata or {},
        dataset_ref=dataset_ref,
    )


class ProductionTruthPolicyTestCase(SimpleTestCase):
    @override_settings(CCHIS_ENVIRONMENT="production")
    def test_seeded_training_and_static_rainfall_are_blocked(self):
        blockers = production_feature_dataset_blockers(
            training_dataset=SimpleNamespace(
                feature_dataset=feature_dataset(
                    source_kind="SEEDED",
                    lineage_metadata={"training_label_source": "seeded_mock_training_rows"},
                )
            ),
            inference_dataset=SimpleNamespace(
                feature_dataset=feature_dataset(source_kind="LIVE"),
                rainfall_ingestion_run=SimpleNamespace(
                    source_kind="SEEDED",
                    fallback_used=True,
                    results=[{"record_type": "fallback_static"}],
                ),
            ),
        )

        self.assertEqual(
            blockers,
            [PRODUCTION_SEEDED_TRUTH_BLOCKED, PRODUCTION_STATIC_FALLBACK_BLOCKED],
        )

    @override_settings(CCHIS_ENVIRONMENT="production")
    def test_seeded_persisted_model_run_cannot_be_promoted_or_used_for_alerts(self):
        blockers = production_model_run_blockers(
            SimpleNamespace(
                model_version="v0-demo",
                metadata={"seeded": True, "seeded_non_production": True},
                training_feature_dataset=None,
                inference_feature_dataset=None,
                rainfall_ingestion_run=None,
            )
        )

        self.assertEqual(blockers, [PRODUCTION_SEEDED_TRUTH_BLOCKED])

    @override_settings(CCHIS_ENVIRONMENT="production")
    def test_demo_operations_fail_with_stable_code(self):
        with self.assertRaises(ProductionTruthPolicyError) as context:
            require_demo_data_allowed("dashboard scenario simulation")

        self.assertEqual(context.exception.code, PRODUCTION_SEEDED_TRUTH_BLOCKED)

    @override_settings(CCHIS_ENVIRONMENT="local")
    def test_local_demo_operations_remain_allowed(self):
        require_demo_data_allowed("dashboard scenario simulation")

    @override_settings(CCHIS_ENVIRONMENT="production")
    def test_demo_commands_and_seeded_training_option_fail_in_production(self):
        for command_name, command_kwargs in (
            ("seed_demo_data", {}),
            ("seed_e2e_source_feeds", {}),
            ("run_risk_model", {"include_seeded_training_labels": True}),
        ):
            with self.subTest(command_name=command_name), self.assertRaises(CommandError) as context:
                call_command(command_name, **command_kwargs)
            self.assertIn("production_seeded_truth_blocked", str(context.exception))

    @override_settings(CCHIS_ENVIRONMENT="production")
    def test_explicit_seeded_label_and_feature_builders_fail_closed(self):
        builders = (
            (build_surveillance_label_dataset, {"include_seeded": True}),
            (build_surveillance_lead_time_label_dataset, {"include_seeded": True}),
            (build_lead_time_feature_dataset, {"include_seeded_surveillance": True}),
        )
        for builder, kwargs in builders:
            with self.subTest(builder=builder.__name__), self.assertRaises(ProductionTruthPolicyError) as context:
                builder(**kwargs)
            self.assertEqual(context.exception.code, PRODUCTION_SEEDED_TRUTH_BLOCKED)
