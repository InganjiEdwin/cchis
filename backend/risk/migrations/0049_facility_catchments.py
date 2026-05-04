# Generated manually for child plan 5 phase 2 on 2026-05-04

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0048_ward_spatial_relationships"),
    ]

    operations = [
        migrations.CreateModel(
            name="FacilityCatchment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "catchment_method",
                    models.CharField(
                        choices=[
                            ("primary_ward_only", "Primary ward only"),
                            ("spatial_graph_adjacent_wards", "Spatial graph adjacent wards"),
                            ("distance_threshold", "Distance threshold"),
                            ("source_catchment_record", "Source catchment record"),
                            ("externally_verified", "Externally verified"),
                        ],
                        default="primary_ward_only",
                        max_length=60,
                    ),
                ),
                (
                    "source_kind",
                    models.CharField(
                        choices=[
                            ("approximated", "Approximated"),
                            ("externally_verified", "Externally verified"),
                            ("manual_override", "Manual override"),
                        ],
                        default="approximated",
                        max_length=40,
                    ),
                ),
                ("distance_threshold", models.FloatField(blank=True, null=True)),
                ("distance_unit", models.CharField(default="source_crs_degrees", max_length=40)),
                ("population_estimate", models.FloatField(blank=True, null=True)),
                ("confidence", models.FloatField(default=0.5)),
                ("is_approximate", models.BooleanField(default=True)),
                ("generated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("lineage_metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "covered_wards",
                    models.ManyToManyField(blank=True, related_name="facility_catchments", to="risk.ward"),
                ),
                (
                    "facility",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="facility_catchments",
                        to="risk.healthfacility",
                    ),
                ),
                (
                    "geometry_dataset_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="facility_catchments",
                        to="risk.wardgeometrydatasetversion",
                    ),
                ),
                (
                    "primary_ward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="primary_facility_catchments",
                        to="risk.ward",
                    ),
                ),
            ],
            options={
                "ordering": ["facility__ward__name", "facility__name", "-generated_at"],
                "indexes": [
                    models.Index(fields=["facility", "generated_at"], name="risk_fcatch_fac_gen_idx"),
                    models.Index(fields=["primary_ward", "catchment_method"], name="risk_fcatch_ward_method_idx"),
                    models.Index(fields=["geometry_dataset_version", "source_kind"], name="risk_fcatch_geom_src_idx"),
                    models.Index(fields=["is_approximate", "generated_at"], name="risk_fcatch_approx_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("facility", "geometry_dataset_version", "catchment_method", "source_kind"),
                        name="risk_fcatch_unique_method",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(confidence__gte=0.0) & models.Q(confidence__lte=1.0),
                        name="risk_fcatch_conf_0_1",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(distance_threshold__isnull=True) | models.Q(distance_threshold__gte=0.0),
                        name="risk_fcatch_distance_nonneg",
                    ),
                ],
            },
        ),
    ]
