# Generated manually on 2026-05-04

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("risk", "0062_model_champion_challenger_constraints"),
    ]

    operations = [
        migrations.CreateModel(
            name="PredictionFeedback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("prediction_date", models.DateField(blank=True, null=True)),
                (
                    "feedback_type",
                    models.CharField(
                        choices=[
                            ("prediction_reviewed_correct", "Prediction reviewed as correct"),
                            ("prediction_reviewed_wrong", "Prediction reviewed as wrong"),
                            ("suspected_missed_outbreak", "Suspected missed outbreak"),
                            ("suspected_false_alert", "Suspected false alert"),
                            ("local_surveillance_correction", "Local surveillance correction"),
                            ("facility_burden_correction", "Facility burden correction"),
                            ("chv_field_observation", "CHV field observation"),
                            ("household_follow_up_outcome", "Household follow-up outcome"),
                            ("alert_delivery_or_response_failure", "Alert delivery or response failure"),
                            ("data_quality_complaint", "Data-quality complaint"),
                            ("usability_feedback", "Usability feedback"),
                        ],
                        max_length=80,
                    ),
                ),
                (
                    "feedback_source_type",
                    models.CharField(
                        choices=[
                            ("system", "System"),
                            ("reviewer", "Reviewer"),
                            ("field_operator", "Field operator"),
                            ("community", "Community"),
                            ("automated_proxy", "Automated proxy"),
                        ],
                        max_length=40,
                    ),
                ),
                ("submitted_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "source_confidence",
                    models.CharField(
                        choices=[
                            ("system_matched_label", "System matched label"),
                            ("county_surveillance_officer", "County surveillance officer"),
                            ("facility_contact", "Facility contact"),
                            ("assigned_chv", "Assigned CHV"),
                            ("county_operator", "County operator"),
                            ("community_report", "Community report"),
                            ("anonymous_public", "Anonymous public"),
                            ("automated_proxy", "Automated proxy"),
                        ],
                        default="community_report",
                        max_length=80,
                    ),
                ),
                ("note", models.TextField(blank=True)),
                ("attached_evidence_refs", models.JSONField(blank=True, default=list)),
                (
                    "privacy_classification",
                    models.CharField(
                        choices=[
                            ("non_sensitive", "Non-sensitive"),
                            ("deidentified", "De-identified"),
                            ("sensitive_operational", "Sensitive operational"),
                            ("contains_pii", "Contains PII"),
                        ],
                        default="non_sensitive",
                        max_length=40,
                    ),
                ),
                (
                    "training_usage_state",
                    models.CharField(
                        choices=[
                            ("not_training_eligible", "Not training eligible"),
                            ("needs_review", "Needs review"),
                            ("adjudicated_label_candidate", "Adjudicated label candidate"),
                            ("training_eligible", "Training eligible"),
                            ("rejected", "Rejected"),
                            ("superseded_by_surveillance_truth", "Superseded by surveillance truth"),
                        ],
                        default="needs_review",
                        max_length=80,
                    ),
                ),
                ("lineage_metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "label_window",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prediction_feedback",
                        to="risk.surveillancelabelwindow",
                    ),
                ),
                (
                    "model_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prediction_feedback",
                        to="risk.modelrun",
                    ),
                ),
                (
                    "risk_score",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prediction_feedback",
                        to="risk.riskscore",
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prediction_feedback_submissions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "ward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="prediction_feedback",
                        to="risk.ward",
                    ),
                ),
            ],
            options={
                "ordering": ["-submitted_at", "-id"],
                "indexes": [
                    models.Index(fields=["ward", "submitted_at"], name="risk_predfb_ward_sub_idx"),
                    models.Index(fields=["risk_score", "submitted_at"], name="risk_predfb_score_sub_idx"),
                    models.Index(fields=["model_run", "submitted_at"], name="risk_predfb_run_sub_idx"),
                    models.Index(fields=["training_usage_state", "submitted_at"], name="risk_predfb_train_sub_idx"),
                    models.Index(fields=["source_confidence", "submitted_at"], name="risk_predfb_conf_sub_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PredictionFeedbackEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("CREATED", "Created"),
                            ("STATE_CHANGED", "State changed"),
                            ("ADJUDICATED", "Adjudicated"),
                            ("LABEL_CANDIDATE_CREATED", "Label candidate created"),
                            ("SUPERSEDED", "Superseded"),
                            ("COMMENT", "Comment"),
                        ],
                        max_length=40,
                    ),
                ),
                ("old_training_usage_state", models.CharField(blank=True, max_length=80)),
                ("new_training_usage_state", models.CharField(blank=True, max_length=80)),
                ("detail", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prediction_feedback_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "feedback",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="events",
                        to="risk.predictionfeedback",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [
                    models.Index(fields=["feedback", "created_at"], name="risk_predfbevt_fb_time_idx"),
                    models.Index(fields=["event_type", "created_at"], name="risk_predfbevt_type_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="FeedbackAdjudication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "adjudication_state",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("accepted_as_label_candidate", "Accepted as label candidate"),
                            ("accepted_as_response_quality_issue", "Accepted as response-quality issue"),
                            ("accepted_as_data_quality_issue", "Accepted as data-quality issue"),
                            ("rejected", "Rejected"),
                            ("needs_more_evidence", "Needs more evidence"),
                            ("superseded", "Superseded"),
                        ],
                        default="pending",
                        max_length=80,
                    ),
                ),
                ("accepted_label_impact", models.JSONField(blank=True, default=dict)),
                ("response_quality_impact", models.JSONField(blank=True, default=dict)),
                ("data_quality_impact", models.JSONField(blank=True, default=dict)),
                ("reason", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("evidence_refs", models.JSONField(blank=True, default=list)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "feedback",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="adjudications",
                        to="risk.predictionfeedback",
                    ),
                ),
                (
                    "reviewer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="feedback_adjudications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "superseded_by_surveillance_label",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="superseding_feedback_adjudications",
                        to="risk.surveillancelabelwindow",
                    ),
                ),
            ],
            options={
                "ordering": ["-reviewed_at", "-created_at", "-id"],
                "indexes": [
                    models.Index(fields=["feedback", "adjudication_state"], name="risk_fbadj_fb_state_idx"),
                    models.Index(fields=["adjudication_state", "reviewed_at"], name="risk_fbadj_state_rev_idx"),
                    models.Index(fields=["reviewer", "reviewed_at"], name="risk_fbadj_reviewer_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="FeedbackLabelCandidate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("candidate_ref", models.CharField(blank=True, max_length=160, unique=True)),
                ("label_window_start", models.DateField()),
                ("label_window_end", models.DateField()),
                (
                    "outbreak_label",
                    models.CharField(
                        choices=[("none", "None"), ("watch", "Watch"), ("active", "Active")],
                        default="none",
                        max_length=20,
                    ),
                ),
                (
                    "label_truth_level",
                    models.CharField(
                        choices=[
                            ("confirmed_surveillance", "Confirmed surveillance"),
                            ("suspected_surveillance", "Suspected surveillance"),
                            ("proxy_diarrheal_signal", "Proxy diarrheal signal"),
                            ("field_signal_only", "Field signal only"),
                            ("seeded_demo", "Seeded demo"),
                        ],
                        default="field_signal_only",
                        max_length=40,
                    ),
                ),
                (
                    "source_confidence",
                    models.CharField(
                        choices=[
                            ("system_matched_label", "System matched label"),
                            ("county_surveillance_officer", "County surveillance officer"),
                            ("facility_contact", "Facility contact"),
                            ("assigned_chv", "Assigned CHV"),
                            ("county_operator", "County operator"),
                            ("community_report", "Community report"),
                            ("anonymous_public", "Anonymous public"),
                            ("automated_proxy", "Automated proxy"),
                        ],
                        default="community_report",
                        max_length=80,
                    ),
                ),
                (
                    "training_usage_state",
                    models.CharField(
                        choices=[
                            ("not_training_eligible", "Not training eligible"),
                            ("needs_review", "Needs review"),
                            ("adjudicated_label_candidate", "Adjudicated label candidate"),
                            ("training_eligible", "Training eligible"),
                            ("rejected", "Rejected"),
                            ("superseded_by_surveillance_truth", "Superseded by surveillance truth"),
                        ],
                        default="adjudicated_label_candidate",
                        max_length=80,
                    ),
                ),
                ("lineage_metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "adjudication",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="label_candidate",
                        to="risk.feedbackadjudication",
                    ),
                ),
                (
                    "feedback",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="label_candidates",
                        to="risk.predictionfeedback",
                    ),
                ),
                (
                    "model_run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="feedback_label_candidates",
                        to="risk.modelrun",
                    ),
                ),
                (
                    "risk_score",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="feedback_label_candidates",
                        to="risk.riskscore",
                    ),
                ),
                (
                    "superseded_by_surveillance_label",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="superseding_feedback_label_candidates",
                        to="risk.surveillancelabelwindow",
                    ),
                ),
                (
                    "ward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="feedback_label_candidates",
                        to="risk.ward",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
                "indexes": [
                    models.Index(fields=["ward", "label_window_start", "label_window_end"], name="risk_fblbl_ward_window_idx"),
                    models.Index(fields=["training_usage_state", "created_at"], name="risk_fblbl_train_idx"),
                    models.Index(fields=["label_truth_level", "created_at"], name="risk_fblbl_truth_idx"),
                ],
                "constraints": [
                    models.CheckConstraint(
                        check=models.Q(("label_window_start__lte", models.F("label_window_end"))),
                        name="risk_fblbl_window_order",
                    ),
                    models.CheckConstraint(
                        check=models.Q(("label_truth_level", "confirmed_surveillance"), _negated=True),
                        name="risk_fblbl_not_confirmed_truth",
                    ),
                ],
            },
        ),
    ]
