# Generated manually for child plan 5 phase 1 on 2026-05-04

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0047_climate_record_contract"),
    ]

    operations = [
        migrations.CreateModel(
            name="WardSpatialRelationship",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "relationship_type",
                    models.CharField(
                        choices=[
                            ("adjacent", "Adjacent"),
                            ("nearby", "Nearby"),
                            ("upstream", "Upstream"),
                            ("same_facility_catchment", "Same facility catchment"),
                            ("manual_public_health_link", "Manual public health link"),
                        ],
                        default="adjacent",
                        max_length=40,
                    ),
                ),
                ("shared_boundary_length", models.FloatField(blank=True, null=True)),
                ("centroid_distance", models.FloatField(blank=True, null=True)),
                ("distance_unit", models.CharField(default="source_crs_degrees", max_length=40)),
                ("confidence", models.FloatField(default=1.0)),
                (
                    "generation_method",
                    models.CharField(
                        choices=[
                            ("derived_geometry", "Derived geometry"),
                            ("derived_facility_catchment", "Derived facility catchment"),
                            ("manual_public_health", "Manual public health"),
                        ],
                        default="derived_geometry",
                        max_length=40,
                    ),
                ),
                ("generated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("lineage_metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "geometry_dataset_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="spatial_relationships",
                        to="risk.wardgeometrydatasetversion",
                    ),
                ),
                (
                    "source_ward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="outgoing_spatial_relationships",
                        to="risk.ward",
                    ),
                ),
                (
                    "target_ward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="incoming_spatial_relationships",
                        to="risk.ward",
                    ),
                ),
            ],
            options={
                "ordering": [
                    "source_ward__county",
                    "source_ward__name",
                    "relationship_type",
                    "target_ward__name",
                ],
                "indexes": [
                    models.Index(fields=["source_ward", "relationship_type"], name="risk_sprel_src_type_idx"),
                    models.Index(fields=["target_ward", "relationship_type"], name="risk_sprel_tgt_type_idx"),
                    models.Index(
                        fields=["geometry_dataset_version", "generation_method"],
                        name="risk_sprel_geom_src_idx",
                    ),
                    models.Index(fields=["relationship_type", "generated_at"], name="risk_sprel_type_gen_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=(
                            "source_ward",
                            "target_ward",
                            "relationship_type",
                            "geometry_dataset_version",
                            "generation_method",
                        ),
                        name="risk_sprel_unique_edge",
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(source_ward_id=models.F("target_ward_id")),
                        name="risk_sprel_no_self_edge",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(confidence__gte=0.0) & models.Q(confidence__lte=1.0),
                        name="risk_sprel_conf_0_1",
                    ),
                ],
            },
        ),
    ]
