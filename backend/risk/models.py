import uuid

from django.contrib.gis.db import models
from django.conf import settings
from django.utils import timezone


class Ward(models.Model):
    RISK_LOW = "LOW"
    RISK_MEDIUM = "MEDIUM"
    RISK_HIGH = "HIGH"
    RISK_CHOICES = [
        (RISK_LOW, "Low"),
        (RISK_MEDIUM, "Medium"),
        (RISK_HIGH, "High"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=120)
    county = models.CharField(max_length=120, default="Migori")
    sub_county = models.CharField(max_length=120, blank=True)
    ward_code = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    boundary = models.MultiPolygonField(null=True, blank=True, srid=4326)
    centroid = models.PointField(null=True, blank=True, srid=4326)
    current_risk_level = models.CharField(
        max_length=10,
        choices=RISK_CHOICES,
        default=RISK_LOW,
    )
    current_risk_score = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["county", "name"]
        constraints = [
            models.UniqueConstraint(fields=["county", "name"], name="unique_ward_name_per_county"),
        ]

    def __str__(self) -> str:
        return f"{self.name}, {self.county}"


class HealthFacility(models.Model):
    TYPE_HOSPITAL = "HOSPITAL"
    TYPE_HEALTH_CENTER = "HEALTH_CENTER"
    TYPE_DISPENSARY = "DISPENSARY"
    TYPE_CLINIC = "CLINIC"
    TYPE_CHOICES = [
        (TYPE_HOSPITAL, "Hospital"),
        (TYPE_HEALTH_CENTER, "Health Center"),
        (TYPE_DISPENSARY, "Dispensary"),
        (TYPE_CLINIC, "Clinic"),
    ]

    OWNERSHIP_PUBLIC = "PUBLIC"
    OWNERSHIP_FAITH = "FAITH_BASED"
    OWNERSHIP_PRIVATE = "PRIVATE"
    OWNERSHIP_CHOICES = [
        (OWNERSHIP_PUBLIC, "Public"),
        (OWNERSHIP_FAITH, "Faith Based"),
        (OWNERSHIP_PRIVATE, "Private"),
    ]

    LEVEL_2 = "LEVEL_2"
    LEVEL_3 = "LEVEL_3"
    LEVEL_4 = "LEVEL_4"
    LEVEL_5 = "LEVEL_5"
    LEVEL_CHOICES = [
        (LEVEL_2, "Level 2"),
        (LEVEL_3, "Level 3"),
        (LEVEL_4, "Level 4"),
        (LEVEL_5, "Level 5"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=160)
    facility_code = models.CharField(max_length=50, unique=True)
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="health_facilities")
    facility_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_DISPENSARY)
    ownership = models.CharField(max_length=20, choices=OWNERSHIP_CHOICES, default=OWNERSHIP_PUBLIC)
    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default=LEVEL_2)
    is_active = models.BooleanField(default=True)
    point = models.PointField(null=True, blank=True, srid=4326)
    contact_phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ward__name", "name"]
        indexes = [
            models.Index(fields=["facility_type", "is_active"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["ward", "name"], name="unique_facility_name_per_ward"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.ward.name})"


class CHV(models.Model):
    name = models.CharField(max_length=120)
    phone_number = models.CharField(max_length=20, unique=True)
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="chvs")
    is_active = models.BooleanField(default=True)
    language = models.CharField(max_length=20, default="en")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.ward.name})"


class RiskScore(models.Model):
    SOURCE_MODEL = "MODEL"
    SOURCE_MANUAL = "MANUAL"
    SOURCE_CHOICES = [
        (SOURCE_MODEL, "Model"),
        (SOURCE_MANUAL, "Manual"),
    ]

    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="risk_scores")
    model_run = models.ForeignKey(
        "risk.ModelRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_scores",
    )
    score = models.FloatField()
    risk_level = models.CharField(max_length=10, choices=Ward.RISK_CHOICES)
    rainfall_mm = models.FloatField(default=0.0)
    flood_indicator = models.FloatField(default=0.0)
    predicted_cases = models.PositiveIntegerField(default=0)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MODEL)
    model_version = models.CharField(max_length=50, default="v0")
    notes = models.TextField(blank=True)
    generated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["generated_at"]),
            models.Index(fields=["risk_level"]),
        ]

    def __str__(self) -> str:
        return f"{self.ward.name} - {self.risk_level} ({self.score})"


class IngestionRun(models.Model):
    RUN_TYPE_RAINFALL = "RAINFALL"
    RUN_TYPE_CHOICES = [
        (RUN_TYPE_RAINFALL, "Rainfall"),
    ]

    SOURCE_KIND_LIVE = "LIVE"
    SOURCE_KIND_SEEDED = "SEEDED"
    SOURCE_KIND_HYBRID = "HYBRID"
    SOURCE_KIND_UNKNOWN = "UNKNOWN"
    SOURCE_KIND_CHOICES = [
        (SOURCE_KIND_LIVE, "Live"),
        (SOURCE_KIND_SEEDED, "Seeded"),
        (SOURCE_KIND_HYBRID, "Hybrid"),
        (SOURCE_KIND_UNKNOWN, "Unknown"),
    ]

    FRESHNESS_FRESH = "FRESH"
    FRESHNESS_DELAYED = "DELAYED"
    FRESHNESS_STALE = "STALE"
    FRESHNESS_UNKNOWN = "UNKNOWN"
    FRESHNESS_CHOICES = [
        (FRESHNESS_FRESH, "Fresh"),
        (FRESHNESS_DELAYED, "Delayed"),
        (FRESHNESS_STALE, "Stale"),
        (FRESHNESS_UNKNOWN, "Unknown"),
    ]

    STATUS_SUCCESS = "SUCCESS"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_SUCCESS, "Success"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_FAILED, "Failed"),
    ]

    run_type = models.CharField(max_length=20, choices=RUN_TYPE_CHOICES, default=RUN_TYPE_RAINFALL)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    source_mode = models.CharField(max_length=20, default="hybrid")
    source_kind = models.CharField(max_length=20, choices=SOURCE_KIND_CHOICES, default=SOURCE_KIND_UNKNOWN)
    source_name = models.CharField(max_length=120, blank=True)
    source_priority = models.JSONField(default=list, blank=True)
    requested_wards = models.JSONField(default=list, blank=True)
    source_timestamp = models.DateTimeField(null=True, blank=True)
    freshness_state = models.CharField(max_length=20, choices=FRESHNESS_CHOICES, default=FRESHNESS_UNKNOWN)
    fallback_used = models.BooleanField(default=False)
    records_seen = models.PositiveIntegerField(default=0)
    records_loaded = models.PositiveIntegerField(default=0)
    records_rejected = models.PositiveIntegerField(default=0)
    results = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["run_type", "started_at"]),
            models.Index(fields=["status", "started_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.run_type} [{self.status}] {self.started_at}"


class ETLHeartbeat(models.Model):
    COMPONENT_SCHEDULER = "SCHEDULER"
    COMPONENT_WORKER = "WORKER"
    COMPONENT_CHOICES = [
        (COMPONENT_SCHEDULER, "Scheduler"),
        (COMPONENT_WORKER, "Worker"),
    ]

    STATUS_OK = "OK"
    STATUS_WARN = "WARN"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_OK, "OK"),
        (STATUS_WARN, "Warn"),
        (STATUS_FAILED, "Failed"),
    ]

    component = models.CharField(max_length=20, choices=COMPONENT_CHOICES)
    task_name = models.CharField(max_length=160)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OK)
    details = models.JSONField(default=dict, blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [
            models.Index(fields=["component", "recorded_at"]),
            models.Index(fields=["status", "recorded_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.component} [{self.status}] {self.recorded_at}"


class ModelRun(models.Model):
    STATUS_RUNNING = "RUNNING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    algorithm_name = models.CharField(max_length=120, default="logistic-regression-baseline")
    model_version = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    month = models.PositiveSmallIntegerField(null=True, blank=True)
    feature_schema_version = models.CharField(max_length=50, default="mock-v1")
    feature_keys = models.JSONField(default=list, blank=True)
    training_dataset_ref = models.CharField(max_length=120, blank=True)
    inference_dataset_ref = models.CharField(max_length=120, blank=True)
    training_row_count = models.PositiveIntegerField(default=0)
    inference_row_count = models.PositiveIntegerField(default=0)
    evaluation_metrics = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    training_feature_dataset = models.ForeignKey(
        "risk.FeatureDataset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="training_model_runs",
    )
    inference_feature_dataset = models.ForeignKey(
        "risk.FeatureDataset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inference_model_runs",
    )
    rainfall_ingestion_run = models.ForeignKey(
        "risk.IngestionRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="model_runs",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["model_version", "started_at"]),
            models.Index(fields=["status", "started_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.model_version} [{self.status}] {self.started_at}"


class FeatureDataset(models.Model):
    KIND_TRAINING = "TRAINING"
    KIND_INFERENCE = "INFERENCE"
    KIND_CHOICES = [
        (KIND_TRAINING, "Training"),
        (KIND_INFERENCE, "Inference"),
    ]

    SOURCE_KIND_LIVE = "LIVE"
    SOURCE_KIND_SEEDED = "SEEDED"
    SOURCE_KIND_HYBRID = "HYBRID"
    SOURCE_KIND_CHOICES = [
        (SOURCE_KIND_LIVE, "Live"),
        (SOURCE_KIND_SEEDED, "Seeded"),
        (SOURCE_KIND_HYBRID, "Hybrid"),
    ]

    dataset_ref = models.CharField(max_length=160, unique=True)
    dataset_kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    schema_version = models.CharField(max_length=50, default="baseline-v1")
    source_kind = models.CharField(max_length=20, choices=SOURCE_KIND_CHOICES, default=SOURCE_KIND_SEEDED)
    month = models.PositiveSmallIntegerField(null=True, blank=True)
    feature_keys = models.JSONField(default=list, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    lineage_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["dataset_kind", "created_at"]),
            models.Index(fields=["schema_version", "created_at"]),
        ]

    def __str__(self) -> str:
        return self.dataset_ref


class FeatureDatasetRow(models.Model):
    dataset = models.ForeignKey(
        FeatureDataset,
        on_delete=models.CASCADE,
        related_name="rows",
    )
    ward = models.ForeignKey(
        Ward,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feature_dataset_rows",
    )
    ward_name_snapshot = models.CharField(max_length=120)
    month = models.PositiveSmallIntegerField()
    feature_values = models.JSONField(default=dict, blank=True)
    label = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["dataset_id", "id"]
        indexes = [
            models.Index(fields=["dataset", "month"]),
            models.Index(fields=["dataset", "ward"]),
        ]

    def __str__(self) -> str:
        return f"{self.dataset.dataset_ref}:{self.ward_name_snapshot}"


class FacilityForecastRun(models.Model):
    STATUS_RUNNING = "RUNNING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    algorithm_name = models.CharField(max_length=120, default="negative-binomial-baseline")
    model_version = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    horizon_days = models.PositiveSmallIntegerField(default=7)
    feature_schema_version = models.CharField(max_length=50, default="facility-burden-v1")
    feature_keys = models.JSONField(default=list, blank=True)
    target_definition = models.CharField(max_length=160, default="expected_suspected_cases_per_facility_7d")
    training_row_count = models.PositiveIntegerField(default=0)
    inference_row_count = models.PositiveIntegerField(default=0)
    evaluation_metrics = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["model_version", "started_at"]),
            models.Index(fields=["status", "started_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.model_version} [{self.status}] {self.started_at}"


class FacilityForecast(models.Model):
    READINESS_LOW = "low"
    READINESS_WATCH = "watch"
    READINESS_CAPACITY_CONCERN = "capacity_concern"
    READINESS_CHOICES = [
        (READINESS_LOW, "Low"),
        (READINESS_WATCH, "Watch"),
        (READINESS_CAPACITY_CONCERN, "Capacity Concern"),
    ]

    facility = models.ForeignKey(
        HealthFacility,
        on_delete=models.CASCADE,
        related_name="facility_forecasts",
    )
    forecast_run = models.ForeignKey(
        "risk.FacilityForecastRun",
        on_delete=models.CASCADE,
        related_name="forecasts",
    )
    generated_at = models.DateTimeField(default=timezone.now)
    horizon_days = models.PositiveSmallIntegerField(default=7)
    projected_case_burden = models.PositiveIntegerField(default=0)
    projected_pressure_score = models.PositiveSmallIntegerField(default=0)
    projected_readiness_state = models.CharField(max_length=32, choices=READINESS_CHOICES, default=READINESS_LOW)
    surge_threshold_state = models.JSONField(default=dict, blank=True)
    driving_ward_ids = models.JSONField(default=list, blank=True)
    forecast_factors = models.JSONField(default=list, blank=True)
    model_version = models.CharField(max_length=50, blank=True)
    freshness_state = models.CharField(max_length=20, default="UNKNOWN")
    forecast_mode = models.CharField(max_length=80, default="negative_binomial_baseline_preview")

    class Meta:
        ordering = ["-generated_at"]
        indexes = [
            models.Index(fields=["generated_at"]),
            models.Index(fields=["projected_readiness_state", "generated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.facility.name} forecast {self.model_version or 'unversioned'}"


class Alert(models.Model):
    CHANNEL_SMS = "SMS"
    CHANNEL_WHATSAPP = "WHATSAPP"
    CHANNEL_DASHBOARD = "DASHBOARD"
    CHANNEL_CHOICES = [
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_WHATSAPP, "WhatsApp"),
        (CHANNEL_DASHBOARD, "Dashboard"),
    ]

    STATUS_QUEUED = "QUEUED"
    STATUS_RETRY_PENDING = "RETRY_PENDING"
    STATUS_DELIVERED = "DELIVERED"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_RETRY_PENDING, "Retry Pending"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_FAILED, "Failed"),
    ]

    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name="alerts")
    risk_score = models.ForeignKey(
        RiskScore,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_SMS)
    recipient = models.CharField(max_length=120)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    delivery_backend = models.CharField(max_length=50, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    external_id = models.CharField(max_length=120, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.channel} to {self.recipient} [{self.status}]"


class TriageSession(models.Model):
    channel = models.CharField(max_length=20, default="USSD")
    phone_number = models.CharField(max_length=20, blank=True)
    ward = models.ForeignKey("risk.Ward", on_delete=models.SET_NULL, null=True, blank=True)
    referral_facility = models.ForeignKey(
        "risk.HealthFacility",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="triage_sessions",
    )
    text_input = models.TextField(blank=True)
    diarrhea = models.BooleanField(default=False)
    vomiting = models.BooleanField(default=False)
    dehydration = models.BooleanField(default=False)
    fever = models.BooleanField(default=False)
    recommendation = models.TextField(blank=True)
    referral_needed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.channel} triage {self.phone_number} {self.created_at}"


class UssdSessionLog(models.Model):
    session_id = models.CharField(max_length=120, db_index=True)
    phone_number = models.CharField(max_length=20, blank=True)
    service_code = models.CharField(max_length=40, blank=True)
    text = models.TextField(blank=True)
    response_text = models.TextField(blank=True)
    ward = models.ForeignKey(Ward, on_delete=models.SET_NULL, null=True, blank=True)
    menu_level = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session_id", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"USSD {self.session_id} {self.phone_number}"


class SyncQueue(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_PROCESSED = "PROCESSED"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSED, "Processed"),
        (STATUS_FAILED, "Failed"),
    ]

    source_device_id = models.CharField(max_length=120, blank=True)
    client_submission_id = models.CharField(max_length=120)
    phone_number = models.CharField(max_length=20, blank=True)
    ward = models.ForeignKey(Ward, on_delete=models.SET_NULL, null=True, blank=True)
    triage_session = models.ForeignKey(
        "risk.TriageSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sync_queue_items",
    )
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_device_id", "client_submission_id"],
                name="unique_sync_submission_per_device",
            ),
        ]

    def __str__(self) -> str:
        return f"SyncQueue {self.id} [{self.status}]"


class WardGeometryDataset(models.Model):
    SCOPE_COUNTY = "COUNTY"
    SCOPE_NATIONAL = "NATIONAL"
    COVERAGE_SCOPE_CHOICES = [
        (SCOPE_COUNTY, "County"),
        (SCOPE_NATIONAL, "National"),
    ]

    KIND_WARD_BOUNDARIES = "WARD_BOUNDARIES"
    GEOMETRY_KIND_CHOICES = [
        (KIND_WARD_BOUNDARIES, "Ward Boundaries"),
    ]

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=160)
    coverage_scope = models.CharField(max_length=20, choices=COVERAGE_SCOPE_CHOICES, default=SCOPE_COUNTY)
    geometry_kind = models.CharField(max_length=40, choices=GEOMETRY_KIND_CHOICES, default=KIND_WARD_BOUNDARIES)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WardGeometryDatasetVersion(models.Model):
    dataset = models.ForeignKey(
        WardGeometryDataset,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_label = models.CharField(max_length=120)
    source_name = models.CharField(max_length=200)
    source_url = models.URLField(blank=True)
    source_license = models.CharField(max_length=120, blank=True)
    source_crs = models.CharField(max_length=32, default="EPSG:4326")
    source_checksum = models.CharField(max_length=128, blank=True)
    imported_at = models.DateTimeField(default=timezone.now)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ward_geometry_imports",
    )
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ward_geometry_activations",
    )
    validation_summary = models.JSONField(default=dict, blank=True)
    feature_count = models.PositiveIntegerField(default=0)
    expected_feature_count = models.PositiveIntegerField(default=0)
    missing_source_wards = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["dataset__name", "-imported_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "version_label"],
                name="unique_ward_geometry_version_per_dataset",
            ),
            models.UniqueConstraint(
                fields=["dataset"],
                condition=models.Q(is_active=True),
                name="unique_active_ward_geometry_version_per_dataset",
            ),
        ]
        indexes = [
            models.Index(fields=["dataset", "-imported_at"]),
            models.Index(fields=["is_active", "activated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.dataset.slug}:{self.version_label}"


class WardGeometryFeature(models.Model):
    dataset_version = models.ForeignKey(
        WardGeometryDatasetVersion,
        on_delete=models.CASCADE,
        related_name="features",
    )
    ward = models.ForeignKey(
        Ward,
        on_delete=models.CASCADE,
        related_name="geometry_features",
    )
    backend_public_id_snapshot = models.UUIDField()
    ward_code_snapshot = models.CharField(max_length=50, blank=True)
    display_name_snapshot = models.CharField(max_length=120)
    source_name = models.CharField(max_length=160, blank=True)
    source_ward_code = models.CharField(max_length=80, blank=True)
    matching_source = models.CharField(max_length=40, blank=True)
    geometry = models.MultiPolygonField(srid=4326)
    centroid = models.PointField(null=True, blank=True, srid=4326)
    properties = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["dataset_version_id", "display_name_snapshot"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset_version", "ward"],
                name="unique_ward_geometry_feature_per_version",
            ),
        ]
        indexes = [
            models.Index(fields=["dataset_version", "ward_code_snapshot"]),
            models.Index(fields=["dataset_version", "matching_source"]),
        ]

    def __str__(self) -> str:
        return f"{self.display_name_snapshot} [{self.dataset_version.version_label}]"
