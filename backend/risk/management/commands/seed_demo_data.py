from django.core.management.base import BaseCommand
from django.utils import timezone

from risk.models import CHV, RiskScore, Ward


class Command(BaseCommand):
    help = "Seed demo data for CCHIS prototype"

    def handle(self, *args, **options):
        wards_data = [
            {"name": "North Kamagambo", "sub_county": "Rongo", "risk_level": "HIGH", "score": 0.86},
            {"name": "North Kadem", "sub_county": "Nyatike", "risk_level": "MEDIUM", "score": 0.62},
            {"name": "Macalder Kanyarwanda", "sub_county": "Nyatike", "risk_level": "HIGH", "score": 0.79},
            {"name": "Got Kachola", "sub_county": "Nyatike", "risk_level": "HIGH", "score": 0.83},
        ]

        for item in wards_data:
            ward, _ = Ward.objects.get_or_create(
                name=item["name"],
                defaults={
                    "county": "Migori",
                    "sub_county": item["sub_county"],
                    "current_risk_level": item["risk_level"],
                    "current_risk_score": item["score"],
                },
            )

            ward.current_risk_level = item["risk_level"]
            ward.current_risk_score = item["score"]
            ward.save()

            CHV.objects.get_or_create(
                phone_number=f"+254700000{ward.id:03d}",
                defaults={
                    "name": f"CHV {ward.name}",
                    "ward": ward,
                    "language": "en",
                    "is_active": True,
                },
            )

            RiskScore.objects.create(
                ward=ward,
                score=item["score"],
                risk_level=item["risk_level"],
                rainfall_mm=120.0 if item["risk_level"] == "HIGH" else 60.0,
                flood_indicator=0.8 if item["risk_level"] == "HIGH" else 0.4,
                predicted_cases=18 if item["risk_level"] == "HIGH" else 7,
                source=RiskScore.SOURCE_MODEL,
                model_version="v0-demo",
                notes="Seeded demo record",
                generated_at=timezone.now(),
            )

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
