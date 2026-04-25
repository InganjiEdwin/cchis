from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("risk", "0012_ingestionrun_source_metadata_and_counts"),
    ]

    operations = [
        migrations.CreateModel(
            name="FeatureDataset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("dataset_ref", models.CharField(max_length=160, unique=True)),
                ("dataset_kind", models.CharField(choices=[("TRAINING", "Training"), ("INFERENCE", "Inference")], max_length=20)),
                ("schema_version", models.CharField(default="baseline-v1", max_length=50)),
                ("source_kind", models.CharField(choices=[("LIVE", "Live"), ("SEEDED", "Seeded"), ("HYBRID", "Hybrid")], default="SEEDED", max_length=20)),
                ("month", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("feature_keys", models.JSONField(blank=True, default=list)),
                ("row_count", models.PositiveIntegerField(default=0)),
                ("lineage_metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="FeatureDatasetRow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ward_name_snapshot", models.CharField(max_length=120)),
                ("month", models.PositiveSmallIntegerField()),
                ("feature_values", models.JSONField(blank=True, default=dict)),
                ("label", models.IntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("dataset", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rows", to="risk.featuredataset")),
                ("ward", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="feature_dataset_rows", to="risk.ward")),
            ],
            options={
                "ordering": ["dataset_id", "id"],
            },
        ),
        migrations.AddField(
            model_name="modelrun",
            name="inference_feature_dataset",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="inference_model_runs", to="risk.featuredataset"),
        ),
        migrations.AddField(
            model_name="modelrun",
            name="training_feature_dataset",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="training_model_runs", to="risk.featuredataset"),
        ),
        migrations.AddIndex(
            model_name="featuredataset",
            index=models.Index(fields=["dataset_kind", "created_at"], name="risk_featur_dataset_a593ec_idx"),
        ),
        migrations.AddIndex(
            model_name="featuredataset",
            index=models.Index(fields=["schema_version", "created_at"], name="risk_featur_schema__9c9241_idx"),
        ),
        migrations.AddIndex(
            model_name="featuredatasetrow",
            index=models.Index(fields=["dataset", "month"], name="risk_featur_dataset_3e8f4b_idx"),
        ),
        migrations.AddIndex(
            model_name="featuredatasetrow",
            index=models.Index(fields=["dataset", "ward"], name="risk_featur_dataset_d11a21_idx"),
        ),
    ]
