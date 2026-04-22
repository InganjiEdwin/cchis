import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.contrib.gis.geos import Point
from django.conf import settings
from django.utils import timezone

from accounts.two_factor import generate_totp_secret
from risk.models import Alert, CHV, HealthFacility, ModelRun, RiskScore, Ward
from risk.seed_kenya_administrative_areas import seed_kenya_counties_and_wards


User = get_user_model()


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
    help = "Seed demo data for CCHIS prototype"

    def handle(self, *args, **options):
        allow_non_local_seed = env_bool("SEED_ALLOW_NON_LOCAL", False)
        if settings.CCHIS_ENVIRONMENT != "local" and not allow_non_local_seed:
            raise CommandError(
                "seed_demo_data is blocked outside local environments. "
                "Set CCHIS_ENVIRONMENT=local for local development or "
                "SEED_ALLOW_NON_LOCAL=True for an intentional shared-environment demo seed."
            )

        seed_kenya_counties_and_wards(stdout=self.stdout)

        wards_data = [
            {
                "name": "North Kamagambo",
                "ward_code": "CCHIS-WARD-001",
                "sub_county": "Rongo",
                "risk_level": "HIGH",
                "score": 0.86,
                "facilities": [
                    {
                        "name": "North Kamagambo Dispensary",
                        "facility_code": "CCHIS-HF-001",
                        "facility_type": HealthFacility.TYPE_DISPENSARY,
                        "ownership": HealthFacility.OWNERSHIP_PUBLIC,
                        "level": HealthFacility.LEVEL_2,
                        "contact_phone": "+254720000001",
                        "point": Point(34.6410, -0.9876, srid=4326),
                    },
                ],
            },
            {
                "name": "North Kadem",
                "ward_code": "CCHIS-WARD-002",
                "sub_county": "Nyatike",
                "risk_level": "MEDIUM",
                "score": 0.62,
                "facilities": [
                    {
                        "name": "North Kadem Health Centre",
                        "facility_code": "CCHIS-HF-002",
                        "facility_type": HealthFacility.TYPE_HEALTH_CENTER,
                        "ownership": HealthFacility.OWNERSHIP_PUBLIC,
                        "level": HealthFacility.LEVEL_3,
                        "contact_phone": "+254720000002",
                        "point": Point(34.3063, -1.0865, srid=4326),
                    },
                ],
            },
            {
                "name": "Macalder Kanyarwanda",
                "ward_code": "CCHIS-WARD-003",
                "sub_county": "Nyatike",
                "risk_level": "HIGH",
                "score": 0.79,
                "facilities": [
                    {
                        "name": "Macalder Mission Hospital",
                        "facility_code": "CCHIS-HF-003",
                        "facility_type": HealthFacility.TYPE_HOSPITAL,
                        "ownership": HealthFacility.OWNERSHIP_FAITH,
                        "level": HealthFacility.LEVEL_4,
                        "contact_phone": "+254720000003",
                        "point": Point(34.2871, -1.1212, srid=4326),
                    },
                ],
            },
            {
                "name": "Got Kachola",
                "ward_code": "CCHIS-WARD-004",
                "sub_county": "Nyatike",
                "risk_level": "HIGH",
                "score": 0.83,
                "facilities": [
                    {
                        "name": "Got Kachola Dispensary",
                        "facility_code": "CCHIS-HF-004",
                        "facility_type": HealthFacility.TYPE_DISPENSARY,
                        "ownership": HealthFacility.OWNERSHIP_PUBLIC,
                        "level": HealthFacility.LEVEL_2,
                        "contact_phone": "+254720000004",
                        "point": Point(34.5122, -1.0634, srid=4326),
                    },
                ],
            },
        ]

        seeded_wards = []
        seed_model_run, _ = ModelRun.objects.get_or_create(
            model_version="v0-demo",
            month=4,
            defaults={
                "algorithm_name": "seed-demo-baseline",
                "status": ModelRun.STATUS_SUCCESS,
                "feature_schema_version": "mock-v1",
                "feature_keys": [
                    "rainfall_mm",
                    "flood_indicator",
                    "historical_cases",
                    "month",
                    "seasonality",
                    "population_proxy",
                ],
                "training_dataset_ref": "seed-training-dataset:v1",
                "inference_dataset_ref": "seed-inference-dataset:v1",
                "training_row_count": 8,
                "inference_row_count": len(wards_data),
                "evaluation_metrics": {"seed_demo": True},
                "metadata": {"seeded": True},
                "completed_at": timezone.now(),
            },
        )
        if seed_model_run.status != ModelRun.STATUS_SUCCESS or seed_model_run.completed_at is None:
            seed_model_run.status = ModelRun.STATUS_SUCCESS
            seed_model_run.completed_at = timezone.now()
            seed_model_run.save(update_fields=["status", "completed_at"])

        for item in wards_data:
            ward, _ = Ward.objects.get_or_create(
                county="Migori",
                name=item["name"],
                defaults={
                    "sub_county": item["sub_county"],
                    "current_risk_level": item["risk_level"],
                    "current_risk_score": item["score"],
                },
            )

            ward.current_risk_level = item["risk_level"]
            ward.current_risk_score = item["score"]
            ward.ward_code = item["ward_code"]
            ward.save()
            seeded_wards.append(ward)

            CHV.objects.get_or_create(
                phone_number=f"+254700000{ward.id:03d}",
                defaults={
                    "name": f"CHV {ward.name}",
                    "ward": ward,
                    "language": "en",
                    "is_active": True,
                },
            )

            for facility in item.get("facilities", []):
                HealthFacility.objects.update_or_create(
                    facility_code=facility["facility_code"],
                    defaults={
                        "name": facility["name"],
                        "ward": ward,
                        "facility_type": facility["facility_type"],
                        "ownership": facility["ownership"],
                        "level": facility["level"],
                        "is_active": True,
                        "contact_phone": facility["contact_phone"],
                        "point": facility["point"],
                    },
                )

            RiskScore.objects.update_or_create(
                ward=ward,
                model_version="v0-demo",
                source=RiskScore.SOURCE_MODEL,
                defaults={
                    "model_run": seed_model_run,
                    "score": item["score"],
                    "risk_level": item["risk_level"],
                    "rainfall_mm": 120.0 if item["risk_level"] == "HIGH" else 60.0,
                    "flood_indicator": 0.8 if item["risk_level"] == "HIGH" else 0.4,
                    "predicted_cases": 18 if item["risk_level"] == "HIGH" else 7,
                    "notes": "Seeded demo record",
                    "generated_at": timezone.now(),
                },
            )

        seeded_risk_scores = {
            risk_score.ward.name: risk_score
            for risk_score in RiskScore.objects.filter(ward__in=seeded_wards, model_version="v0-demo")
        }

        alert_seed_rows = [
            {
                "ward_name": "North Kamagambo",
                "channel": Alert.CHANNEL_SMS,
                "recipient": "+254711000321",
                "status": Alert.STATUS_DELIVERED,
                "delivery_backend": "seeded-sms",
                "attempt_count": 1,
                "max_attempts": 1,
                "minutes_ago": 2,
                "external_id": "seed-alert-001",
            },
            {
                "ward_name": "Got Kachola",
                "channel": Alert.CHANNEL_DASHBOARD,
                "recipient": "dashboard",
                "status": Alert.STATUS_RETRY_PENDING,
                "delivery_backend": "internal-dashboard",
                "attempt_count": 1,
                "max_attempts": 3,
                "minutes_ago": 14,
                "external_id": "seed-alert-002",
            },
            {
                "ward_name": "Macalder Kanyarwanda",
                "channel": Alert.CHANNEL_DASHBOARD,
                "recipient": "dashboard",
                "status": Alert.STATUS_DELIVERED,
                "delivery_backend": "internal-dashboard",
                "attempt_count": 1,
                "max_attempts": 1,
                "minutes_ago": 32,
                "external_id": "seed-alert-003",
            },
            {
                "ward_name": "North Kadem",
                "channel": Alert.CHANNEL_SMS,
                "recipient": "+254711000654",
                "status": Alert.STATUS_DELIVERED,
                "delivery_backend": "seeded-radio",
                "attempt_count": 1,
                "max_attempts": 1,
                "minutes_ago": 60,
                "external_id": "seed-alert-004",
            },
            {
                "ward_name": "North Kamagambo",
                "channel": Alert.CHANNEL_DASHBOARD,
                "recipient": "dashboard",
                "status": Alert.STATUS_DELIVERED,
                "delivery_backend": "internal-dashboard",
                "attempt_count": 1,
                "max_attempts": 1,
                "minutes_ago": 120,
                "external_id": "seed-alert-005",
            },
        ]

        for item in alert_seed_rows:
            ward = next((candidate for candidate in seeded_wards if candidate.name == item["ward_name"]), None)
            risk_score = seeded_risk_scores.get(item["ward_name"])
            if ward is None or risk_score is None:
                continue

            timestamp = timezone.now() - timedelta(minutes=item["minutes_ago"])
            alert, _ = Alert.objects.update_or_create(
                external_id=item["external_id"],
                defaults={
                    "ward": ward,
                    "risk_score": risk_score,
                    "channel": item["channel"],
                    "recipient": item["recipient"],
                    "message": (
                        f"Pilot alert for {ward.name}. "
                        f"Risk level: {risk_score.risk_level}. "
                        f"Predicted cases: {risk_score.predicted_cases}."
                    ),
                    "status": item["status"],
                    "delivery_backend": item["delivery_backend"],
                    "attempt_count": item["attempt_count"],
                    "max_attempts": item["max_attempts"],
                    "last_attempted_at": timestamp,
                    "next_retry_at": timestamp + timedelta(minutes=10)
                    if item["status"] == Alert.STATUS_RETRY_PENDING
                    else None,
                    "sent_at": None if item["status"] == Alert.STATUS_RETRY_PENDING else timestamp,
                    "error_message": "" if item["status"] != Alert.STATUS_RETRY_PENDING else "Awaiting retry dispatch.",
                },
            )
            Alert.objects.filter(pk=alert.pk).update(created_at=timestamp)

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

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
        if seeded_accounts:
            self.stdout.write("Seeded accounts: " + ", ".join(seeded_accounts))
        else:
            self.stdout.write("Seeded accounts: none")
