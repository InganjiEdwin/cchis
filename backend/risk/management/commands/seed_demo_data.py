import os
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.two_factor import generate_totp_secret
from risk.models import (
    Alert,
    CHV,
    FacilityForecast,
    FacilityForecastRun,
    HealthFacility,
    IngestionRun,
    ModelRun,
    RiskScore,
    SyncQueue,
    TriageSession,
    Ward,
)
from risk.seed_kenya_administrative_areas import (
    reconcile_ward_codes_from_reference,
    seed_kenya_counties_and_wards,
)


User = get_user_model()

FULL_SUITE_BUNDLE = "decision_layer_full_suite"
SCENARIO_BUNDLES = [
    "stable_baseline",
    "localized_watch_cluster",
    "escalating_triggered_hotspot",
    "delivery_failure_concern",
    "facility_capacity_pressure",
]
SCENARIO_CHOICES = [FULL_SUITE_BUNDLE, *SCENARIO_BUNDLES]


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


class Command(BaseCommand):
    help = "Seed explicit non-production dashboard scenario data for CCHIS"

    def add_arguments(self, parser):
        parser.add_argument(
            "--scenario-bundle",
            choices=SCENARIO_CHOICES,
            default=FULL_SUITE_BUNDLE,
            help="Seed one named decision-layer scenario bundle or the full suite.",
        )
        parser.add_argument(
            "--list-scenario-bundles",
            action="store_true",
            help="List the available decision-layer scenario bundle names and exit.",
        )

    def handle(self, *args, **options):
        if options["list_scenario_bundles"]:
            self.stdout.write("Available scenario bundles:")
            for item in SCENARIO_CHOICES:
                self.stdout.write(f"- {item}")
            return

        allow_non_local_seed = env_bool("SEED_ALLOW_NON_LOCAL", False)
        if settings.CCHIS_ENVIRONMENT != "local" and not allow_non_local_seed:
            raise CommandError(
                "seed_demo_data is blocked outside local environments. "
                "Set CCHIS_ENVIRONMENT=local for local development or "
                "SEED_ALLOW_NON_LOCAL=True for an intentional shared-environment demo seed."
            )

        selected_bundle = options["scenario_bundle"]
        selected_scenarios = SCENARIO_BUNDLES if selected_bundle == FULL_SUITE_BUNDLE else [selected_bundle]

        seed_kenya_counties_and_wards(stdout=self.stdout, county_names=["Migori"])
        self._cleanup_previous_seed_artifacts()

        anchor = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0)
        ward_profiles = self._build_ward_profiles(selected_scenarios)
        seeded_wards = []

        ingestion_run = self._seed_ingestion_run(anchor, selected_scenarios)
        model_runs = self._seed_model_runs(anchor, ingestion_run, selected_scenarios)

        for profile in ward_profiles:
            ward = profile["ward"]
            ward.current_risk_level = profile["current_risk_level"]
            ward.current_risk_score = profile["current_risk_score"]
            ward.save(update_fields=["current_risk_level", "current_risk_score"])
            seeded_wards.append(ward)

            self._seed_chvs_for_profile(ward, profile)
            facilities = self._seed_facilities_for_profile(ward, profile)
            current_risk_score = self._seed_risk_history(ward, profile, model_runs, anchor)
            self._seed_alerts(ward, current_risk_score, profile, anchor)
            self._seed_field_feedback(ward, profile, anchor)

            if profile["scenario_name"] == "facility_capacity_pressure":
                self._seed_facility_forecasts(facilities, ward, anchor, promoted=True)
            else:
                self._seed_facility_forecasts(facilities, ward, anchor, promoted=False)

        reconcile_ward_codes_from_reference(stdout=self.stdout, county_names=["Migori"])
        seeded_accounts = self._seed_accounts()

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
        self.stdout.write("Scenario bundle: " + selected_bundle)
        self.stdout.write("Seeded scenarios: " + ", ".join(selected_scenarios))
        if seeded_accounts:
            self.stdout.write("Seeded accounts: " + ", ".join(seeded_accounts))
        else:
            self.stdout.write("Seeded accounts: none")

    def _cleanup_previous_seed_artifacts(self):
        Alert.objects.filter(external_id__startswith="seed-scenario-").delete()
        SyncQueue.objects.filter(client_submission_id__startswith="seed-scenario-").delete()
        TriageSession.objects.filter(phone_number__startswith="+2547999").delete()
        FacilityForecastRun.objects.filter(model_version__startswith="seed-scenario-ff-").delete()
        RiskScore.objects.filter(model_version__startswith="v0-demo-seeded-").delete()
        ModelRun.objects.filter(model_version__in=["v0-demo", "v0-demo-seeded-24h", "v0-demo-seeded-48h"]).delete()
        IngestionRun.objects.filter(source_name__startswith="seed-scenario-").delete()

    def _build_ward_profiles(self, selected_scenarios: list[str]):
        predefined_names = {
            "escalating_triggered_hotspot": "North Kamagambo",
            "localized_watch_cluster": "North Kadem",
            "delivery_failure_concern": "Macalder/Kanyarwanda",
            "facility_capacity_pressure": "Got Kachola",
        }
        used_names = set(predefined_names.values())
        fallback_ward = (
            Ward.objects.filter(county="Migori")
            .exclude(name__in=used_names)
            .order_by("name")
            .first()
        )
        if fallback_ward is None:
            raise CommandError("Unable to find a fifth Migori ward for the stable_baseline scenario.")
        predefined_names["stable_baseline"] = fallback_ward.name

        scenario_profiles = {
            "stable_baseline": {
                "current_risk_level": Ward.RISK_LOW,
                "current_risk_score": 0.12,
                "sub_county": fallback_ward.sub_county,
                "history": [
                    {"model_version": "v0-demo-seeded-48h", "score": 0.18, "risk_level": Ward.RISK_LOW, "predicted_cases": 2, "hours_ago": 48},
                    {"model_version": "v0-demo-seeded-24h", "score": 0.15, "risk_level": Ward.RISK_LOW, "predicted_cases": 1, "hours_ago": 24},
                    {"model_version": "v0-demo", "score": 0.12, "risk_level": Ward.RISK_LOW, "predicted_cases": 1, "hours_ago": 2},
                ],
                "facility": {
                    "name": f"{fallback_ward.name} Health Centre",
                    "facility_code": "CCHIS-HF-005",
                    "facility_type": HealthFacility.TYPE_HEALTH_CENTER,
                    "ownership": HealthFacility.OWNERSHIP_PUBLIC,
                    "level": HealthFacility.LEVEL_3,
                    "contact_phone": "+254720000005",
                    "point": Point(34.5000, -1.0000, srid=4326),
                },
                "chv_count": 1,
                "alerts": [],
                "field_feedback": {"triage": 0, "sync": 0},
            },
            "localized_watch_cluster": {
                "current_risk_level": Ward.RISK_MEDIUM,
                "current_risk_score": 0.58,
                "sub_county": "Nyatike",
                "history": [
                    {"model_version": "v0-demo-seeded-48h", "score": 0.39, "risk_level": Ward.RISK_LOW, "predicted_cases": 3, "hours_ago": 48},
                    {"model_version": "v0-demo-seeded-24h", "score": 0.47, "risk_level": Ward.RISK_MEDIUM, "predicted_cases": 4, "hours_ago": 24},
                    {"model_version": "v0-demo", "score": 0.58, "risk_level": Ward.RISK_MEDIUM, "predicted_cases": 5, "hours_ago": 2},
                ],
                "facility": {
                    "name": "North Kadem Health Centre",
                    "facility_code": "CCHIS-HF-002",
                    "facility_type": HealthFacility.TYPE_HEALTH_CENTER,
                    "ownership": HealthFacility.OWNERSHIP_PUBLIC,
                    "level": HealthFacility.LEVEL_3,
                    "contact_phone": "+254720000002",
                    "point": Point(34.3063, -1.0865, srid=4326),
                },
                "chv_count": 1,
                "alerts": [],
                "field_feedback": {"triage": 1, "sync": 0},
            },
            "escalating_triggered_hotspot": {
                "current_risk_level": Ward.RISK_HIGH,
                "current_risk_score": 0.88,
                "sub_county": "Rongo",
                "history": [
                    {"model_version": "v0-demo-seeded-48h", "score": 0.46, "risk_level": Ward.RISK_MEDIUM, "predicted_cases": 6, "hours_ago": 48},
                    {"model_version": "v0-demo-seeded-24h", "score": 0.71, "risk_level": Ward.RISK_HIGH, "predicted_cases": 11, "hours_ago": 24},
                    {"model_version": "v0-demo", "score": 0.88, "risk_level": Ward.RISK_HIGH, "predicted_cases": 18, "hours_ago": 2},
                ],
                "facility": {
                    "name": "North Kamagambo Dispensary",
                    "facility_code": "CCHIS-HF-001",
                    "facility_type": HealthFacility.TYPE_DISPENSARY,
                    "ownership": HealthFacility.OWNERSHIP_PUBLIC,
                    "level": HealthFacility.LEVEL_2,
                    "contact_phone": "+254720000001",
                    "point": Point(34.6410, -0.9876, srid=4326),
                },
                "chv_count": 2,
                "alerts": [
                    {
                        "external_id": "seed-scenario-escalating-triggered-hotspot-dashboard",
                        "channel": Alert.CHANNEL_DASHBOARD,
                        "recipient": "dashboard",
                        "status": Alert.STATUS_DELIVERED,
                        "delivery_backend": "internal-dashboard",
                        "attempt_count": 1,
                        "max_attempts": 1,
                        "minutes_ago": 25,
                    },
                    {
                        "external_id": "seed-scenario-escalating-triggered-hotspot-sms",
                        "channel": Alert.CHANNEL_SMS,
                        "recipient": "+254711000321",
                        "status": Alert.STATUS_DELIVERED,
                        "delivery_backend": "seeded-sms",
                        "attempt_count": 1,
                        "max_attempts": 1,
                        "minutes_ago": 18,
                    },
                ],
                "field_feedback": {"triage": 1, "sync": 1},
            },
            "delivery_failure_concern": {
                "current_risk_level": Ward.RISK_HIGH,
                "current_risk_score": 0.81,
                "sub_county": "Nyatike",
                "history": [
                    {"model_version": "v0-demo-seeded-48h", "score": 0.55, "risk_level": Ward.RISK_MEDIUM, "predicted_cases": 7, "hours_ago": 48},
                    {"model_version": "v0-demo-seeded-24h", "score": 0.68, "risk_level": Ward.RISK_HIGH, "predicted_cases": 10, "hours_ago": 24},
                    {"model_version": "v0-demo", "score": 0.81, "risk_level": Ward.RISK_HIGH, "predicted_cases": 14, "hours_ago": 2},
                ],
                "facility": {
                    "name": "Macalder Mission Hospital",
                    "facility_code": "CCHIS-HF-003",
                    "facility_type": HealthFacility.TYPE_HOSPITAL,
                    "ownership": HealthFacility.OWNERSHIP_FAITH,
                    "level": HealthFacility.LEVEL_4,
                    "contact_phone": "+254720000003",
                    "point": Point(34.2871, -1.1212, srid=4326),
                },
                "chv_count": 1,
                "alerts": [
                    {
                        "external_id": "seed-scenario-delivery-failure-concern-retry",
                        "channel": Alert.CHANNEL_DASHBOARD,
                        "recipient": "dashboard",
                        "status": Alert.STATUS_RETRY_PENDING,
                        "delivery_backend": "internal-dashboard",
                        "attempt_count": 1,
                        "max_attempts": 3,
                        "minutes_ago": 16,
                        "error_message": "Awaiting retry dispatch.",
                    },
                    {
                        "external_id": "seed-scenario-delivery-failure-concern-failed",
                        "channel": Alert.CHANNEL_SMS,
                        "recipient": "+254711000654",
                        "status": Alert.STATUS_FAILED,
                        "delivery_backend": "seeded-sms",
                        "attempt_count": 3,
                        "max_attempts": 3,
                        "minutes_ago": 9,
                        "error_message": "Delivery failed after retry exhaustion.",
                    },
                ],
                "field_feedback": {"triage": 0, "sync": 1},
            },
            "facility_capacity_pressure": {
                "current_risk_level": Ward.RISK_HIGH,
                "current_risk_score": 0.84,
                "sub_county": "Nyatike",
                "history": [
                    {"model_version": "v0-demo-seeded-48h", "score": 0.49, "risk_level": Ward.RISK_MEDIUM, "predicted_cases": 6, "hours_ago": 48},
                    {"model_version": "v0-demo-seeded-24h", "score": 0.67, "risk_level": Ward.RISK_HIGH, "predicted_cases": 9, "hours_ago": 24},
                    {"model_version": "v0-demo", "score": 0.84, "risk_level": Ward.RISK_HIGH, "predicted_cases": 16, "hours_ago": 2},
                ],
                "facility": {
                    "name": "Got Kachola Dispensary",
                    "facility_code": "CCHIS-HF-004",
                    "facility_type": HealthFacility.TYPE_DISPENSARY,
                    "ownership": HealthFacility.OWNERSHIP_PUBLIC,
                    "level": HealthFacility.LEVEL_2,
                    "contact_phone": "+254720000004",
                    "point": Point(34.5122, -1.0634, srid=4326),
                },
                "chv_count": 1,
                "alerts": [
                    {
                        "external_id": "seed-scenario-facility-capacity-pressure-dashboard",
                        "channel": Alert.CHANNEL_DASHBOARD,
                        "recipient": "dashboard",
                        "status": Alert.STATUS_DELIVERED,
                        "delivery_backend": "internal-dashboard",
                        "attempt_count": 1,
                        "max_attempts": 1,
                        "minutes_ago": 38,
                    },
                ],
                "field_feedback": {"triage": 1, "sync": 1},
            },
        }

        profiles = []
        for scenario_name in selected_scenarios:
            ward_name = predefined_names[scenario_name]
            ward = Ward.objects.get(county="Migori", name=ward_name)
            profile = {
                "scenario_name": scenario_name,
                "ward": ward,
                **scenario_profiles[scenario_name],
            }
            profiles.append(profile)
        return profiles

    def _seed_ingestion_run(self, anchor, selected_scenarios: list[str]):
        run, _ = IngestionRun.objects.update_or_create(
            source_name="seed-scenario-rainfall",
            defaults={
                "run_type": IngestionRun.RUN_TYPE_RAINFALL,
                "status": IngestionRun.STATUS_SUCCESS,
                "source_mode": "seeded-demo-scenario",
                "source_kind": IngestionRun.SOURCE_KIND_SEEDED,
                "source_priority": ["seeded_scenario_bundle"],
                "requested_wards": [Ward.objects.get(county="Migori", name=Ward.objects.filter(county="Migori").first().name).name] if Ward.objects.filter(county="Migori").exists() else [],
                "source_timestamp": anchor - timedelta(minutes=40),
                "freshness_state": IngestionRun.FRESHNESS_DELAYED,
                "fallback_used": True,
                "records_seen": len(selected_scenarios),
                "records_loaded": len(selected_scenarios),
                "records_rejected": 0,
                "operator_note": f"seeded_non_production_scenarios={','.join(selected_scenarios)}",
                "results": [{"scenario": scenario_name, "mode": "seeded_non_production"} for scenario_name in selected_scenarios],
                "error_message": "",
                "completed_at": anchor - timedelta(minutes=35),
            },
        )
        IngestionRun.objects.filter(pk=run.pk).update(started_at=anchor - timedelta(minutes=45))
        run.refresh_from_db()
        return run

    def _seed_model_runs(self, anchor, ingestion_run, selected_scenarios: list[str]):
        definitions = [
            ("v0-demo-seeded-48h", anchor - timedelta(hours=48), "historical_seeded_decision_state"),
            ("v0-demo-seeded-24h", anchor - timedelta(hours=24), "historical_seeded_decision_state"),
            ("v0-demo", anchor - timedelta(hours=2), "current_seeded_decision_state"),
        ]
        runs = {}
        for model_version, timestamp, run_role in definitions:
            run, _ = ModelRun.objects.update_or_create(
                model_version=model_version,
                defaults={
                    "algorithm_name": "seed-demo-baseline",
                    "status": ModelRun.STATUS_SUCCESS,
                    "month": anchor.month,
                    "feature_schema_version": "mock-v1",
                    "feature_keys": [
                        "rainfall_mm",
                        "flood_indicator",
                        "historical_cases",
                        "month",
                        "seasonality",
                        "population_proxy",
                    ],
                    "training_dataset_ref": f"{model_version}:seed-training-dataset",
                    "inference_dataset_ref": f"{model_version}:seed-inference-dataset",
                    "training_row_count": 12,
                    "inference_row_count": len(selected_scenarios),
                    "evaluation_metrics": {
                        "seed_demo": True,
                        "scenario_bundle": FULL_SUITE_BUNDLE if len(selected_scenarios) > 1 else selected_scenarios[0],
                    },
                    "metadata": {
                        "seeded": True,
                        "seeded_non_production": True,
                        "execution_context": "seeded_demo",
                        "run_purpose": "demo_seed",
                        "promotion_target": "demo_only",
                        "retraining_policy": "manual_promotion_only",
                        "alert_eligible": False,
                        "model_family": "ward_risk_classification",
                        "scenario_bundle_names": selected_scenarios,
                        "run_role": run_role,
                    },
                    "rainfall_ingestion_run": ingestion_run,
                    "completed_at": timestamp,
                },
            )
            ModelRun.objects.filter(pk=run.pk).update(started_at=timestamp - timedelta(minutes=8))
            run.refresh_from_db()
            runs[model_version] = run
        return runs

    def _seed_chvs_for_profile(self, ward: Ward, profile: dict):
        for index in range(profile["chv_count"]):
            CHV.objects.update_or_create(
                phone_number=f"+254700000{ward.id:03d}{index}",
                defaults={
                    "name": f"{profile['scenario_name'].replace('_', ' ').title()} CHV {index + 1}",
                    "ward": ward,
                    "language": "en",
                    "is_active": True,
                },
            )

    def _seed_facilities_for_profile(self, ward: Ward, profile: dict):
        facility_payload = profile["facility"]
        facility, _ = HealthFacility.objects.update_or_create(
            facility_code=facility_payload["facility_code"],
            defaults={
                "name": facility_payload["name"],
                "ward": ward,
                "facility_type": facility_payload["facility_type"],
                "ownership": facility_payload["ownership"],
                "level": facility_payload["level"],
                "is_active": True,
                "contact_phone": facility_payload["contact_phone"],
                "point": facility_payload["point"],
            },
        )
        return [facility]

    def _seed_risk_history(self, ward: Ward, profile: dict, model_runs: dict, anchor):
        current_score = None
        for history_row in profile["history"]:
            generated_at = anchor - timedelta(hours=history_row["hours_ago"])
            risk_score, _ = RiskScore.objects.update_or_create(
                ward=ward,
                model_version=history_row["model_version"],
                generated_at=generated_at,
                source=RiskScore.SOURCE_MODEL,
                defaults={
                    "model_run": model_runs[history_row["model_version"]],
                    "score": history_row["score"],
                    "risk_level": history_row["risk_level"],
                    "rainfall_mm": round(history_row["score"] * 140, 1),
                    "flood_indicator": round(min(1.0, history_row["score"]), 2),
                    "predicted_cases": history_row["predicted_cases"],
                    "notes": f"Seeded non-production dashboard scenario: {profile['scenario_name']}",
                },
            )
            if history_row["model_version"] == "v0-demo":
                current_score = risk_score
        return current_score

    def _seed_alerts(self, ward: Ward, risk_score: RiskScore, profile: dict, anchor):
        for alert_payload in profile["alerts"]:
            timestamp = anchor - timedelta(minutes=alert_payload["minutes_ago"])
            alert, _ = Alert.objects.update_or_create(
                external_id=alert_payload["external_id"],
                defaults={
                    "ward": ward,
                    "risk_score": risk_score,
                    "channel": alert_payload["channel"],
                    "recipient": alert_payload["recipient"],
                    "message": (
                        f"Seeded non-production scenario alert for {ward.name}. "
                        f"Scenario: {profile['scenario_name']}. "
                        f"Risk level: {risk_score.risk_level}. "
                        f"Predicted cases: {risk_score.predicted_cases}."
                    ),
                    "status": alert_payload["status"],
                    "delivery_backend": alert_payload["delivery_backend"],
                    "attempt_count": alert_payload["attempt_count"],
                    "max_attempts": alert_payload["max_attempts"],
                    "last_attempted_at": timestamp,
                    "next_retry_at": timestamp + timedelta(minutes=10)
                    if alert_payload["status"] == Alert.STATUS_RETRY_PENDING
                    else None,
                    "sent_at": None
                    if alert_payload["status"] in {Alert.STATUS_RETRY_PENDING, Alert.STATUS_FAILED}
                    else timestamp,
                    "error_message": alert_payload.get("error_message", ""),
                },
            )
            Alert.objects.filter(pk=alert.pk).update(created_at=timestamp)

    def _seed_field_feedback(self, ward: Ward, profile: dict, anchor):
        for index in range(profile["field_feedback"]["triage"]):
            phone_number = f"+2547999{ward.id:03d}{index}"
            TriageSession.objects.filter(phone_number=phone_number).delete()
            created_at = anchor - timedelta(minutes=12 + index * 4)
            triage = TriageSession.objects.create(
                channel="USSD",
                phone_number=phone_number,
                ward=ward,
                text_input=f"seed-scenario triage {profile['scenario_name']}",
                diarrhea=True,
                vomiting=index == 0,
                dehydration=index == 0,
                fever=False,
                recommendation="Escalate dehydration review if symptoms persist.",
                referral_needed=index == 0,
            )
            TriageSession.objects.filter(pk=triage.pk).update(created_at=created_at)

        for index in range(profile["field_feedback"]["sync"]):
            created_at = anchor - timedelta(minutes=10 + index * 3)
            sync_item, _ = SyncQueue.objects.update_or_create(
                source_device_id=f"seed-scenario-device-{ward.id}",
                client_submission_id=f"seed-scenario-sync-{profile['scenario_name']}-{index}",
                defaults={
                    "phone_number": f"+2547888{ward.id:03d}{index}",
                    "ward": ward,
                    "payload": {"scenario_name": profile["scenario_name"], "kind": "field_feedback"},
                    "status": SyncQueue.STATUS_PROCESSED,
                    "processed_at": created_at + timedelta(minutes=1),
                    "error_message": "",
                },
            )
            SyncQueue.objects.filter(pk=sync_item.pk).update(created_at=created_at)

    def _seed_facility_forecasts(self, facilities: list[HealthFacility], ward: Ward, anchor, *, promoted: bool):
        run, _ = FacilityForecastRun.objects.update_or_create(
            model_version=f"seed-scenario-ff-{ward.id}",
            defaults={
                "algorithm_name": "negative-binomial-baseline",
                "status": FacilityForecastRun.STATUS_SUCCESS,
                "horizon_days": 7,
                "feature_schema_version": "facility-burden-v1",
                "feature_keys": [
                    "ward_risk_score",
                    "ward_alert_count",
                    "projected_cases",
                    "rainfall_proxy",
                ],
                "target_definition": "expected_suspected_cases_per_facility_7d",
                "training_row_count": 16,
                "inference_row_count": len(facilities),
                "evaluation_metrics": {
                    "seeded_non_production": True,
                    "scenario": "facility_capacity_pressure" if promoted else "baseline_readiness",
                },
                "metadata": {
                    "seeded": True,
                    "seeded_non_production": True,
                    "execution_context": "seeded_demo",
                    "promotion_target": "dashboard_readiness_promoted" if promoted else "forecast_preview_only",
                    "scenario_bundle_name": "facility_capacity_pressure" if promoted else "supporting_readiness_context",
                    "promotion_note": "Seeded non-production dashboard scenario data only.",
                },
                "completed_at": anchor - timedelta(minutes=55 if promoted else 70),
            },
        )
        FacilityForecastRun.objects.filter(pk=run.pk).update(started_at=anchor - timedelta(minutes=65 if promoted else 80))

        for facility in facilities:
            FacilityForecast.objects.update_or_create(
                facility=facility,
                forecast_run=run,
                defaults={
                    "generated_at": anchor - timedelta(minutes=54 if promoted else 69),
                    "horizon_days": 7,
                    "projected_case_burden": 12 if promoted else 4,
                    "projected_pressure_score": 91 if promoted else 36,
                    "projected_readiness_state": FacilityForecast.READINESS_CAPACITY_CONCERN if promoted else FacilityForecast.READINESS_LOW,
                    "surge_threshold_state": {
                        "ors": "capacity_concern" if promoted else "low",
                        "staffing": "capacity_concern" if promoted else "low",
                    },
                    "driving_ward_ids": [ward.id],
                    "forecast_factors": [
                        {"label": "Seeded scenario driver", "detail": "Non-production dashboard verification scenario."},
                    ],
                    "model_version": run.model_version,
                    "freshness_state": "FRESH",
                    "forecast_mode": "seeded_non_production_dashboard_scenario",
                },
            )

    def _seed_accounts(self):
        default_password = os.getenv("SEED_DEFAULT_PASSWORD", "ChangeMe123!")
        seed_superuser_enabled = env_bool("SEED_ENABLE_SUPERUSER", True)
        seed_demo_users_enabled = env_bool("SEED_ENABLE_DEMO_USERS", True)
        superuser_password = os.getenv("SEED_SUPERUSER_PASSWORD", default_password)
        superuser_username = os.getenv("SEED_SUPERUSER_USERNAME", "superuser")
        superuser_email = os.getenv("SEED_SUPERUSER_EMAIL", "superuser@example.com")
        primary_ward = Ward.objects.filter(county="Migori", name="North Kamagambo").first()
        secondary_ward = Ward.objects.filter(county="Migori", name="North Kadem").first() or primary_ward

        seeded_accounts = []

        if seed_superuser_enabled:
            superuser, _ = User.objects.update_or_create(
                username=superuser_username,
                defaults={
                    "email": superuser_email,
                    "full_name": "Seeded Superuser",
                    "phone_number": "+254711000000",
                    "role": User.ROLE_ADMIN,
                    "ward": primary_ward,
                    "is_staff": True,
                    "is_superuser": True,
                    "is_active": True,
                },
            )
            superuser.set_password(superuser_password)
            superuser.save(update_fields=["password"])
            seeded_accounts.append(f"superuser={superuser_username}")

        demo_users = [
            {
                "username": "admin",
                "email": "admin@example.com",
                "full_name": "System Admin",
                "phone_number": "+254711000001",
                "role": User.ROLE_ADMIN,
                "ward": primary_ward,
                "is_staff": True,
                "is_superuser": False,
            },
            {
                "username": "supervisor",
                "email": "supervisor@example.com",
                "full_name": "Field Supervisor",
                "phone_number": "+254711000002",
                "role": User.ROLE_SUPERVISOR,
                "ward": secondary_ward,
                "is_staff": True,
                "is_superuser": False,
            },
            {
                "username": "chv_demo",
                "email": "chv@example.com",
                "full_name": "Demo CHV",
                "phone_number": "+254711000003",
                "role": User.ROLE_CHV,
                "ward": primary_ward,
                "is_staff": False,
                "is_superuser": False,
            },
            {
                "username": "analyst_demo",
                "email": "analyst@example.com",
                "full_name": "Demo Analyst",
                "phone_number": "+254711000004",
                "role": User.ROLE_ANALYST,
                "ward": secondary_ward,
                "is_staff": False,
                "is_superuser": False,
            },
        ]

        if seed_demo_users_enabled:
            for item in demo_users:
                user, _ = User.objects.update_or_create(
                    username=item["username"],
                    defaults={
                        "email": item["email"],
                        "full_name": item["full_name"],
                        "phone_number": item["phone_number"],
                        "role": item["role"],
                        "ward": item["ward"],
                        "is_staff": item["is_staff"],
                        "is_superuser": item["is_superuser"],
                        "is_active": True,
                    },
                )
                user.set_password(default_password)
                update_fields = ["password"]

                fixed_totp_secret = ""
                if item["username"] == "admin":
                    fixed_totp_secret = env_str("SEED_DEMO_ADMIN_TOTP_SECRET")
                elif item["username"] == "supervisor":
                    fixed_totp_secret = env_str("SEED_DEMO_SUPERVISOR_TOTP_SECRET")

                if fixed_totp_secret:
                    user.totp_secret = fixed_totp_secret
                    user.is_totp_enabled = True
                    update_fields.extend(["totp_secret", "is_totp_enabled"])
                elif item["role"] in settings.TOTP_REQUIRED_ROLES and not user.totp_secret:
                    user.totp_secret = generate_totp_secret()
                    user.is_totp_enabled = True
                    update_fields.extend(["totp_secret", "is_totp_enabled"])

                user.save(update_fields=update_fields)
                seeded_accounts.append(item["username"])

        return seeded_accounts
