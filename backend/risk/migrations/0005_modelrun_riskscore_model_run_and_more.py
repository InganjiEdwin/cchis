import django.db.models.deletion
from django.utils import timezone
from django.db import migrations, models


def backfill_model_runs(apps, schema_editor):
    ModelRun = apps.get_model("risk", "ModelRun")
    RiskScore = apps.get_model("risk", "RiskScore")

    model_scores = RiskScore.objects.filter(source="MODEL", model_run__isnull=True).order_by("generated_at", "id")
    model_versions = model_scores.values_list("model_version", flat=True).distinct()

    for model_version in model_versions:
        version_scores = model_scores.filter(model_version=model_version)
        row_count = version_scores.count()
        model_run = ModelRun.objects.create(
            algorithm_name="legacy-backfill-baseline",
            model_version=model_version or "legacy-backfill",
            status="SUCCESS",
            month=None,
            feature_keys=[],
            training_row_count=0,
            inference_row_count=row_count,
            evaluation_metrics={"backfilled": True},
            metadata={"backfilled": True},
            completed_at=timezone.now(),
        )
        version_scores.update(model_run=model_run)


class Migration(migrations.Migration):

    dependencies = [
        ('risk', '0004_ingestionrun'),
    ]

    operations = [
        migrations.CreateModel(
            name='ModelRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('algorithm_name', models.CharField(default='logistic-regression-baseline', max_length=120)),
                ('model_version', models.CharField(max_length=50)),
                ('status', models.CharField(choices=[('RUNNING', 'Running'), ('SUCCESS', 'Success'), ('FAILED', 'Failed')], default='RUNNING', max_length=20)),
                ('month', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('feature_keys', models.JSONField(blank=True, default=list)),
                ('training_row_count', models.PositiveIntegerField(default=0)),
                ('inference_row_count', models.PositiveIntegerField(default=0)),
                ('evaluation_metrics', models.JSONField(blank=True, default=dict)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('rainfall_ingestion_run', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='model_runs', to='risk.ingestionrun')),
            ],
            options={
                'ordering': ['-started_at'],
            },
        ),
        migrations.AddField(
            model_name='riskscore',
            name='model_run',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='risk_scores', to='risk.modelrun'),
        ),
        migrations.AddIndex(
            model_name='modelrun',
            index=models.Index(fields=['model_version', 'started_at'], name='risk_modelr_model_v_dbe024_idx'),
        ),
        migrations.AddIndex(
            model_name='modelrun',
            index=models.Index(fields=['status', 'started_at'], name='risk_modelr_status_8451c6_idx'),
        ),
        migrations.RunPython(backfill_model_runs, migrations.RunPython.noop),
    ]
