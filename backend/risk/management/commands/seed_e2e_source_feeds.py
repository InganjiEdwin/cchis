from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from risk.models import (
    Alert,
    ExposureFeatureRecord,
    PopulationExposureIngestionRun,
    PopulationExposureSource,
    PopulationExposureSourceKind,
    PopulationExposureTruth,
    RiskScore,
    SurveillanceFreshnessState,
    SurveillanceIngestionRun,
    SurveillanceOutbreakLabel,
    SurveillanceRecord,
    SurveillanceSource,
    SurveillanceSourceKind,
    SurveillanceTruthLevel,
    Ward,
)
from risk.population_exposure_ingestion import run_population_exposure_csv_ingestion
from risk.surveillance_ingestion import run_surveillance_csv_ingestion


DEFAULT_OUTPUT_DIR = Path("risk/data/e2e_source_feeds")
POPULATION_SOURCE_NAME = "seed-e2e-population-exposure-demo"
SURVEILLANCE_SOURCE_NAME = "seed-e2e-county-surveillance-demo"


@dataclass(frozen=True)
class WardDemoProfile:
    ward: Ward
    risk_index: float
    population_total: int
    population_under_five: int
    household_count_proxy: int
    population_density: float
    settlement_concentration: float
    floodplain_exposure: float
    water_body_proximity: float
    wash_vulnerability: float
    exposed_population_proxy: float


class Command(BaseCommand):
    help = "Generate non-production source CSV feeds, optionally ingesting them through the e2e ETL contracts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default=str(DEFAULT_OUTPUT_DIR),
            help="Directory where generated CSV source feeds will be written.",
        )
        parser.add_argument("--as-of", default="", help="ISO date for the synthetic source snapshot. Defaults to today.")
        parser.add_argument("--weeks", type=int, default=12, help="Number of weekly surveillance periods to generate.")
        parser.add_argument(
            "--ingest",
            action="store_true",
            help="Immediately ingest generated CSVs using the existing population/exposure and surveillance ETL.",
        )
        parser.add_argument(
            "--build-downstream",
            action="store_true",
            help="After ingesting, build population/exposure, surveillance label, and lead-time feature datasets.",
        )
        parser.add_argument(
            "--score",
            action="store_true",
            help="After downstream builds, run the non-production risk scoring command without sending alerts.",
        )
        parser.add_argument(
            "--simulate-alerts",
            action="store_true",
            help=(
                "After scoring, materialize dashboard-only simulation alerts for alert-candidate "
                "risk scores. This never sends SMS and is blocked in staging/production."
            ),
        )

    def handle(self, *args, **options):
        as_of = self._parse_as_of(options["as_of"])
        weeks = options["weeks"]
        if weeks < 2:
            raise CommandError("--weeks must be at least 2 so labels contain positive and quiet periods.")

        wards = list(
            Ward.objects.filter(is_active=True, county__iexact="Migori")
            .exclude(ward_code="")
            .order_by("name")
        )
        if not wards:
            raise CommandError("No active wards found. Seed administrative areas before generating e2e source feeds.")

        output_dir = Path(options["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)

        profiles = [self._profile_for_ward(ward, index) for index, ward in enumerate(wards, start=1)]
        population_path = output_dir / f"population_exposure_seed_e2e_{as_of.isoformat()}.csv"
        surveillance_path = output_dir / f"surveillance_seed_e2e_{as_of.isoformat()}.csv"

        population_rows = self._write_population_exposure_csv(population_path, profiles, as_of)
        surveillance_source_ref = str(surveillance_path)
        supersedes_source_ref = (
            surveillance_source_ref
            if SurveillanceRecord.objects.filter(source_ref=surveillance_source_ref).exists()
            else ""
        )
        first_period_start, last_period_end, surveillance_rows = self._write_surveillance_csv(
            surveillance_path,
            profiles,
            as_of=as_of,
            weeks=weeks,
            source_ref=surveillance_source_ref,
            supersedes_source_ref=supersedes_source_ref,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Generated e2e source feeds. "
                f"population_exposure_rows={population_rows} surveillance_rows={surveillance_rows} "
                f"output_dir={output_dir}"
            )
        )
        self.stdout.write(f"Population/exposure CSV: {population_path}")
        self.stdout.write(f"Surveillance CSV: {surveillance_path}")

        if not options["ingest"] and (options["build_downstream"] or options["score"]):
            raise CommandError("--build-downstream and --score require --ingest.")
        if options["simulate_alerts"] and not options["score"]:
            raise CommandError("--simulate-alerts requires --score.")
        if options["simulate_alerts"] and settings.CCHIS_ENVIRONMENT in {"staging", "production"}:
            raise CommandError("--simulate-alerts is blocked in staging and production environments.")

        if options["ingest"]:
            source_timestamp = self._aware_datetime(as_of)
            population_run = run_population_exposure_csv_ingestion(
                file_path=population_path,
                source_name=POPULATION_SOURCE_NAME,
                source_type=PopulationExposureSource.SOURCE_TYPE_CSV_BACKFILL,
                source_timestamp=source_timestamp,
                release_version=f"seed-e2e-{as_of.isoformat()}",
                source_ref=str(population_path),
                correction_mode=PopulationExposureIngestionRun.CORRECTION_BACKFILL,
                operator_note="Non-production synthetic feed for end-to-end pipeline testing.",
                fallback_used=True,
            )
            surveillance_run = run_surveillance_csv_ingestion(
                file_path=surveillance_path,
                source_name=SURVEILLANCE_SOURCE_NAME,
                source_type=SurveillanceSource.SOURCE_TYPE_WEEKLY_AGGREGATE,
                source_timestamp=source_timestamp,
                reporting_period_start=first_period_start,
                reporting_period_end=last_period_end,
                source_ref=str(surveillance_path),
                correction_mode=SurveillanceIngestionRun.CORRECTION_BACKFILL,
                operator_note="Non-production synthetic cholera surveillance feed for e2e testing.",
                fallback_used=True,
                regenerate_label_windows=True,
                label_dataset_role="training",
                include_seeded_labels=True,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Ingested e2e source feeds. "
                    f"population_run={population_run.id}:{population_run.status} "
                    f"surveillance_run={surveillance_run.id}:{surveillance_run.status}"
                )
            )

        if options["build_downstream"]:
            call_command("build_population_exposure_dataset", month=as_of.month)
            call_command(
                "build_surveillance_label_dataset",
                start_date=first_period_start.isoformat(),
                end_date=last_period_end.isoformat(),
                dataset_role="training",
                include_empty_windows=True,
            )
            # Lead-time features enforce created_at < prediction-day cutoff. Build demo prediction
            # dates after the source load date so freshly seeded records are valid, non-leaky inputs.
            lead_time_start = as_of + timedelta(days=1)
            lead_time_end = as_of + timedelta(days=29)
            call_command(
                "build_lead_time_feature_dataset",
                start_date=lead_time_start.isoformat(),
                end_date=lead_time_end.isoformat(),
                step_days=7,
                include_seeded_surveillance=True,
                claimed_forecast_horizon_days=3,
            )
            self.stdout.write(self.style.SUCCESS("Built downstream e2e feature and label datasets."))

        if options["score"]:
            model_version = f"lr-seed-e2e-{as_of.strftime('%Y%m%d')}"
            call_command(
                "run_risk_model",
                month=as_of.month,
                model_version=model_version,
                algorithm="logistic_regression",
                include_seeded_training_labels=True,
            )
            if options["simulate_alerts"]:
                alert_count = self._simulate_dashboard_alerts(model_version=model_version)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Materialized dashboard-only e2e simulation alerts. alerts_created={alert_count}"
                    )
                )

    def _parse_as_of(self, value: str) -> date:
        if not value:
            return timezone.localdate()
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise CommandError("--as-of must be an ISO date like 2026-05-05.") from error

    def _aware_datetime(self, value: date) -> datetime:
        return timezone.make_aware(datetime.combine(value, time(hour=12)), timezone.get_current_timezone())

    def _profile_for_ward(self, ward: Ward, index: int) -> WardDemoProfile:
        base_score = ward.current_risk_score if ward.current_risk_score is not None else 0
        name = ward.name.lower()
        hotspot_boost = 0.18 if any(token in name for token in ["kadem", "kamagambo", "macalder", "kachola"]) else 0
        risk_index = min(0.95, max(0.12, float(base_score or 0.0) + hotspot_boost + ((index % 5) * 0.035)))
        population_total = int(round(4200 + (index * 210) + (risk_index * 7800)))
        population_under_five = int(round(population_total * (0.135 + (risk_index * 0.025))))
        household_count_proxy = int(round(population_total / 4.4))
        settlement_concentration = round(min(0.92, 0.22 + risk_index * 0.58 + ((index % 3) * 0.025)), 3)
        floodplain_exposure = round(min(0.95, 0.12 + risk_index * 0.74), 3)
        water_body_proximity = round(min(0.96, 0.18 + risk_index * 0.66 + ((index % 4) * 0.02)), 3)
        wash_vulnerability = round(min(0.95, 0.20 + risk_index * 0.62 + ((index % 2) * 0.035)), 3)
        exposed_population_proxy = round(population_total * floodplain_exposure * wash_vulnerability * 0.42, 1)
        return WardDemoProfile(
            ward=ward,
            risk_index=round(risk_index, 3),
            population_total=population_total,
            population_under_five=population_under_five,
            household_count_proxy=household_count_proxy,
            population_density=round(120 + (risk_index * 620) + (index * 2.5), 1),
            settlement_concentration=settlement_concentration,
            floodplain_exposure=floodplain_exposure,
            water_body_proximity=water_body_proximity,
            wash_vulnerability=wash_vulnerability,
            exposed_population_proxy=exposed_population_proxy,
        )

    def _write_population_exposure_csv(self, path: Path, profiles: list[WardDemoProfile], as_of: date) -> int:
        fieldnames = [
            "ward_id",
            "ward_name",
            "population_total",
            "population_under_five",
            "households",
            "exposure_type",
            "exposure_value",
            "unit",
            "truth_class",
            "source_kind",
            "freshness_state",
            "aggregation_method",
            "spatial_resolution",
            "source_ref",
            "notes",
        ]
        rows = []
        for profile in profiles:
            common = {
                "ward_id": profile.ward.id,
                "ward_name": profile.ward.name,
                "truth_class": PopulationExposureTruth.SEEDED_DEMO,
                "source_kind": PopulationExposureSourceKind.SEEDED,
                "freshness_state": "fresh",
                "source_ref": f"seed-e2e:{as_of.isoformat()}",
            }
            rows.append(
                {
                    **common,
                    "population_total": profile.population_total,
                    "population_under_five": profile.population_under_five,
                    "households": profile.household_count_proxy,
                    "notes": "Seeded ward population baseline for non-production e2e testing.",
                }
            )
            exposure_rows = [
                (ExposureFeatureRecord.EXPOSURE_POPULATION_DENSITY, profile.population_density, "people_per_km2_proxy"),
                (ExposureFeatureRecord.EXPOSURE_SETTLEMENT_CONCENTRATION, profile.settlement_concentration, "index"),
                (ExposureFeatureRecord.EXPOSURE_FLOODPLAIN_EXPOSURE, profile.floodplain_exposure, "index"),
                (ExposureFeatureRecord.EXPOSURE_WATER_BODY_PROXIMITY, profile.water_body_proximity, "index"),
                (ExposureFeatureRecord.EXPOSURE_WASH_VULNERABILITY, profile.wash_vulnerability, "index"),
                (ExposureFeatureRecord.EXPOSURE_EXPOSED_POPULATION_PROXY, profile.exposed_population_proxy, "people_proxy"),
            ]
            for exposure_type, exposure_value, unit in exposure_rows:
                rows.append(
                    {
                        **common,
                        "exposure_type": exposure_type,
                        "exposure_value": exposure_value,
                        "unit": unit,
                        "aggregation_method": "deterministic_context_aligned_seed_profile",
                        "spatial_resolution": "ward",
                        "notes": "Seeded exposure proxy for non-production e2e testing.",
                    }
                )

        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    def _write_surveillance_csv(
        self,
        path: Path,
        profiles: list[WardDemoProfile],
        *,
        as_of: date,
        weeks: int,
        source_ref: str,
        supersedes_source_ref: str = "",
    ) -> tuple[date, date, int]:
        fieldnames = [
            "ward_id",
            "ward_name",
            "reporting_period_start",
            "reporting_period_end",
            "source_ref",
            "supersedes_record_ref",
            "suspected_cholera_count",
            "confirmed_cholera_count",
            "diarrheal_count",
            "outbreak_label",
            "truth_level",
            "source_kind",
            "freshness_state",
            "source_system",
            "provider",
            "provider_record_id",
            "notes",
        ]
        first_period_start = as_of - timedelta(days=(weeks * 7) - 1)
        rows = []
        for week_index in range(weeks):
            period_start = first_period_start + timedelta(days=week_index * 7)
            period_end = period_start + timedelta(days=6)
            for profile in profiles:
                suspected, confirmed, diarrheal = self._case_counts(profile, week_index, weeks)
                outbreak_label = self._outbreak_label(suspected, confirmed, diarrheal)
                rows.append(
                    {
                        "ward_id": profile.ward.id,
                        "ward_name": profile.ward.name,
                        "reporting_period_start": period_start.isoformat(),
                        "reporting_period_end": period_end.isoformat(),
                        "source_ref": source_ref,
                        "supersedes_record_ref": supersedes_source_ref,
                        "suspected_cholera_count": suspected,
                        "confirmed_cholera_count": confirmed,
                        "diarrheal_count": diarrheal,
                        "outbreak_label": outbreak_label,
                        "truth_level": SurveillanceTruthLevel.SEEDED_DEMO,
                        "source_kind": SurveillanceSourceKind.SEEDED,
                        "freshness_state": SurveillanceFreshnessState.FRESH,
                        "source_system": "seed_e2e_source_feeds",
                        "provider": "cchis_demo_seed",
                        "provider_record_id": f"seed-e2e-{profile.ward.id}-{period_start.isoformat()}",
                        "notes": "Synthetic non-production cholera surveillance aggregate.",
                    }
                )

        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return first_period_start, first_period_start + timedelta(days=(weeks * 7) - 1), len(rows)

    def _case_counts(self, profile: WardDemoProfile, week_index: int, weeks: int) -> tuple[int, int, int]:
        peak_one = max(1, weeks // 3)
        peak_two = max(peak_one + 2, (weeks * 2) // 3)
        wave_one = max(0.0, 1.0 - (abs(week_index - peak_one) / 2.4))
        wave_two = max(0.0, 1.0 - (abs(week_index - peak_two) / 2.8))
        rain_lag_signal = max(wave_one, wave_two * 0.82)
        background = max(0, round((profile.risk_index - 0.28) * 3))
        suspected = int(round(background + rain_lag_signal * (2 + profile.risk_index * 11)))
        confirmed = int(round(suspected * (0.08 + profile.risk_index * 0.10))) if suspected >= 4 else 0
        diarrheal = int(round((suspected * 2.15) + (profile.wash_vulnerability * 7) + rain_lag_signal * 5))
        return suspected, confirmed, diarrheal

    def _outbreak_label(self, suspected: int, confirmed: int, diarrheal: int) -> str:
        if confirmed >= 2 or suspected >= 9:
            return SurveillanceOutbreakLabel.ACTIVE
        if confirmed >= 1 or suspected >= 4 or diarrheal >= 14:
            return SurveillanceOutbreakLabel.WATCH
        return SurveillanceOutbreakLabel.NONE

    def _simulate_dashboard_alerts(self, *, model_version: str) -> int:
        from risk.services import MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION, sync_alert_workflow_for_ward

        now = timezone.now()
        risk_scores = list(
            RiskScore.objects.select_related("ward", "model_run")
            .filter(model_version=model_version)
            .order_by("-score", "ward__name")
        )
        selected_scores = [
            risk_score
            for risk_score in risk_scores
            if (risk_score.decision_policy or {}).get("alert_candidate")
        ]
        simulation_trigger_mode = "decision_policy_alert_candidate"
        if not selected_scores and risk_scores:
            selected_scores = risk_scores[:1]
            simulation_trigger_mode = "top_ranked_threshold_probe"

        created_count = 0
        for risk_score in selected_scores:
            decision_policy = risk_score.decision_policy or {}
            metadata = risk_score.model_run.metadata if risk_score.model_run_id else {}
            external_id = f"seed-e2e-sim-alert:{model_version}:{risk_score.id}"
            if Alert.objects.filter(external_id=external_id).exists():
                continue

            score_percent = round(float(risk_score.score or 0) * 100)
            message = (
                f"CCHIS e2e simulation: {risk_score.ward.name} is {risk_score.risk_level} "
                f"at {score_percent}% model score with {risk_score.predicted_cases} predicted cases. "
                "Review CHV follow-up, safe-water messaging, and ORS readiness."
            )
            Alert.objects.create(
                ward=risk_score.ward,
                risk_score=risk_score,
                channel=Alert.CHANNEL_DASHBOARD,
                recipient="dashboard:e2e-simulation",
                message=message,
                status=Alert.STATUS_DELIVERED,
                delivery_backend="internal-dashboard-e2e-simulation",
                attempt_count=1,
                max_attempts=1,
                last_attempted_at=now,
                sent_at=now,
                external_id=external_id,
                guided_request_metadata={
                    "simulation": True,
                    "simulation_type": "seed_e2e_dashboard_alert",
                    "source_command": "seed_e2e_source_feeds",
                    "simulation_trigger_mode": simulation_trigger_mode,
                    "model_version": model_version,
                    "risk_score_id": risk_score.id,
                    "model_run_id": risk_score.model_run_id,
                    "production_alert_guardrails": {
                        "model_run_alert_eligible": metadata.get("alert_eligible"),
                        "promotion_state": metadata.get("promotion_state"),
                        "automatic_alert_allowed": decision_policy.get("automatic_alert_allowed"),
                        "automatic_alert_blockers": decision_policy.get("automatic_alert_blockers", []),
                        "note": (
                            "This dashboard alert is a local e2e simulation artifact. "
                            "It does not mark seeded data as production alert-eligible."
                        ),
                    },
                    "decision_policy": decision_policy,
                },
                governance_metadata={
                    "schema_version": MESSAGE_AUDIENCE_GOVERNANCE_SCHEMA_VERSION,
                    "workflow": "seed_e2e_dashboard_alert_simulation",
                    "audience_decision": {
                        "allowed": True,
                        "decision": "dashboard_only_simulation_delivery_allowed",
                        "reason": "local e2e simulation without SMS delivery",
                    },
                    "audience_scope": {
                        "scope_kind": "internal_dashboard",
                        "scope_allowed": True,
                        "target_ward_id": risk_score.ward_id,
                    },
                    "simulation": True,
                },
            )
            sync_alert_workflow_for_ward(
                risk_score.ward,
                event_metadata={
                    "simulation": True,
                    "source_command": "seed_e2e_source_feeds",
                    "model_version": model_version,
                    "risk_score_id": risk_score.id,
                },
            )
            created_count += 1
        return created_count
