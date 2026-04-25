from django.conf import settings
import django.contrib.gis.db.models.fields
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0009_ward_county_name_uniqueness"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WardGeometryDataset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("slug", models.SlugField(unique=True)),
                ("name", models.CharField(max_length=160)),
                (
                    "coverage_scope",
                    models.CharField(
                        choices=[("COUNTY", "County"), ("NATIONAL", "National")],
                        default="COUNTY",
                        max_length=20,
                    ),
                ),
                (
                    "geometry_kind",
                    models.CharField(
                        choices=[("WARD_BOUNDARIES", "Ward Boundaries")],
                        default="WARD_BOUNDARIES",
                        max_length=40,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="WardGeometryDatasetVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version_label", models.CharField(max_length=120)),
                ("source_name", models.CharField(max_length=200)),
                ("source_url", models.URLField(blank=True)),
                ("source_license", models.CharField(blank=True, max_length=120)),
                ("source_crs", models.CharField(default="EPSG:4326", max_length=32)),
                ("source_checksum", models.CharField(blank=True, max_length=128)),
                ("imported_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("validation_summary", models.JSONField(blank=True, default=dict)),
                ("feature_count", models.PositiveIntegerField(default=0)),
                ("expected_feature_count", models.PositiveIntegerField(default=0)),
                ("missing_source_wards", models.JSONField(blank=True, default=list)),
                ("is_active", models.BooleanField(default=False)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "dataset",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="versions", to="risk.wardgeometrydataset"),
                ),
                (
                    "imported_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="ward_geometry_imports",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["dataset__name", "-imported_at", "-id"],
                "indexes": [
                    models.Index(fields=["dataset", "-imported_at"], name="risk_wardge_dataset_b9f742_idx"),
                    models.Index(fields=["is_active", "activated_at"], name="risk_wardge_is_acti_9e3e58_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("dataset", "version_label"), name="unique_ward_geometry_version_per_dataset"),
                    models.UniqueConstraint(condition=models.Q(("is_active", True)), fields=("dataset",), name="unique_active_ward_geometry_version_per_dataset"),
                ],
            },
        ),
        migrations.CreateModel(
            name="WardGeometryFeature",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("backend_public_id_snapshot", models.UUIDField()),
                ("ward_code_snapshot", models.CharField(blank=True, max_length=50)),
                ("display_name_snapshot", models.CharField(max_length=120)),
                ("source_name", models.CharField(blank=True, max_length=160)),
                ("source_ward_code", models.CharField(blank=True, max_length=80)),
                ("matching_source", models.CharField(blank=True, max_length=40)),
                ("geometry", django.contrib.gis.db.models.fields.MultiPolygonField(srid=4326)),
                ("centroid", django.contrib.gis.db.models.fields.PointField(blank=True, null=True, srid=4326)),
                ("properties", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "dataset_version",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="features", to="risk.wardgeometrydatasetversion"),
                ),
                (
                    "ward",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="geometry_features", to="risk.ward"),
                ),
            ],
            options={
                "ordering": ["dataset_version_id", "display_name_snapshot"],
                "indexes": [
                    models.Index(fields=["dataset_version", "ward_code_snapshot"], name="risk_wardge_dataset_a1a146_idx"),
                    models.Index(fields=["dataset_version", "matching_source"], name="risk_wardge_dataset_0e1af9_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(fields=("dataset_version", "ward"), name="unique_ward_geometry_feature_per_version"),
                ],
            },
        ),
    ]
