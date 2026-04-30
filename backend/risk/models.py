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


class FacilityContact(models.Model):
    CHANNEL_SMS = "SMS"
    CHANNEL_EMAIL = "EMAIL"
    CHANNEL_SYSTEM = "SYSTEM"
    CHANNEL_CHOICES = [
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_SYSTEM, "System"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    facility = models.ForeignKey(HealthFacility, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    preferred_channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_SMS)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=120)
    source_reference = models.CharField(max_length=160, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["facility__name", "-is_verified", "-updated_at"]
        indexes = [
            models.Index(fields=["facility", "is_active", "is_verified"]),
            models.Index(fields=["source", "source_reference"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(phone__gt="") | models.Q(email__gt=""),
                name="facility_contact_requires_phone_or_email",
            ),
        ]

    def __str__(self) -> str:
        label = self.name or self.role or "Facility contact"
        return f"{label} ({self.facility.name})"


class FacilityReadinessReview(models.Model):
    STATUS_OPEN = "OPEN"
    STATUS_ACKNOWLEDGED = "ACKNOWLEDGED"
    STATUS_RESOLVED = "RESOLVED"
    STATUS_DISMISSED = "DISMISSED"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_ACKNOWLEDGED, "Acknowledged"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_DISMISSED, "Dismissed"),
    ]
    ACTIVE_STATUSES = [STATUS_OPEN, STATUS_ACKNOWLEDGED]

    SEVERITY_LOW = "LOW"
    SEVERITY_MEDIUM = "MEDIUM"
    SEVERITY_HIGH = "HIGH"
    SEVERITY_CHOICES = [
        (SEVERITY_LOW, "Low"),
        (SEVERITY_MEDIUM, "Medium"),
        (SEVERITY_HIGH, "High"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    facility = models.ForeignKey(
        HealthFacility,
        on_delete=models.PROTECT,
        related_name="readiness_reviews",
    )
    ward = models.ForeignKey(
        Ward,
        on_delete=models.PROTECT,
        related_name="facility_readiness_reviews",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default=SEVERITY_LOW)
    reason_codes = models.JSONField(default=list, blank=True)
    decision_summary_snapshot = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facility_readiness_reviews_created",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facility_readiness_reviews_assigned",
    )
    notes = models.TextField(blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["facility"],
                condition=models.Q(status__in=["OPEN", "ACKNOWLEDGED"]),
                name="unique_active_facility_readiness_review",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="risk_facrev_status_idx"),
            models.Index(fields=["facility", "status"], name="risk_facrev_facility_idx"),
            models.Index(fields=["ward", "status"], name="risk_facrev_ward_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.facility.name} [{self.status}]"


class FacilityReadinessReviewEvent(models.Model):
    ACTION_CREATED = "CREATED"
    ACTION_ACKNOWLEDGED = "ACKNOWLEDGED"
    ACTION_RESOLVED = "RESOLVED"
    ACTION_DISMISSED = "DISMISSED"
    ACTION_UPDATE_REQUEST_CREATED = "UPDATE_REQUEST_CREATED"
    ACTION_ESCALATION_CREATED = "ESCALATION_CREATED"
    ACTION_ESCALATION_ACKNOWLEDGED = "ESCALATION_ACKNOWLEDGED"
    ACTION_ESCALATION_RESOLVED = "ESCALATION_RESOLVED"
    ACTION_ESCALATION_DISMISSED = "ESCALATION_DISMISSED"
    ACTION_CHOICES = [
        (ACTION_CREATED, "Created"),
        (ACTION_ACKNOWLEDGED, "Acknowledged"),
        (ACTION_RESOLVED, "Resolved"),
        (ACTION_DISMISSED, "Dismissed"),
        (ACTION_UPDATE_REQUEST_CREATED, "Update Request Created"),
        (ACTION_ESCALATION_CREATED, "Escalation Created"),
        (ACTION_ESCALATION_ACKNOWLEDGED, "Escalation Acknowledged"),
        (ACTION_ESCALATION_RESOLVED, "Escalation Resolved"),
        (ACTION_ESCALATION_DISMISSED, "Escalation Dismissed"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    review = models.ForeignKey(
        FacilityReadinessReview,
        on_delete=models.PROTECT,
        related_name="events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facility_readiness_review_events",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    detail = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["review", "created_at"], name="risk_facreve_review_idx"),
            models.Index(fields=["action", "created_at"], name="risk_facreve_action_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.review.public_id} {self.action}"


class FacilityReadinessUpdateRequest(models.Model):
    CHANNEL_SMS = "SMS"
    CHANNEL_EMAIL = "EMAIL"
    CHANNEL_SYSTEM = "SYSTEM"
    CHANNEL_CHOICES = [
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_SYSTEM, "System"),
    ]

    STATUS_DRAFT = "DRAFT"
    STATUS_QUEUED = "QUEUED"
    STATUS_SENT = "SENT"
    STATUS_ACKNOWLEDGED = "ACKNOWLEDGED"
    STATUS_FAILED = "FAILED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_SENT, "Sent"),
        (STATUS_ACKNOWLEDGED, "Acknowledged"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    ACTIVE_STATUSES = [STATUS_DRAFT, STATUS_QUEUED, STATUS_SENT]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    review = models.ForeignKey(
        FacilityReadinessReview,
        on_delete=models.PROTECT,
        related_name="update_requests",
    )
    facility = models.ForeignKey(
        HealthFacility,
        on_delete=models.PROTECT,
        related_name="readiness_update_requests",
    )
    contact = models.ForeignKey(
        FacilityContact,
        on_delete=models.PROTECT,
        related_name="readiness_update_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facility_readiness_update_requests",
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_SMS)
    message_body = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    provider_reference = models.CharField(max_length=120, blank=True)
    failure_reason = models.TextField(blank=True)
    requested_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-requested_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["review"],
                condition=models.Q(status__in=["DRAFT", "QUEUED", "SENT"]),
                name="unique_active_facility_update_request_per_review",
            ),
            models.UniqueConstraint(
                fields=["facility"],
                condition=models.Q(status__in=["DRAFT", "QUEUED", "SENT"]),
                name="unique_active_facility_update_request_per_facility",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "requested_at"], name="risk_facupd_status_idx"),
            models.Index(fields=["review", "status"], name="risk_facupd_review_idx"),
            models.Index(fields=["facility", "status"], name="risk_facupd_facility_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.facility.name} update request [{self.status}]"


class FacilityReadinessEscalation(models.Model):
    STATUS_OPEN = "OPEN"
    STATUS_ACKNOWLEDGED = "ACKNOWLEDGED"
    STATUS_RESOLVED = "RESOLVED"
    STATUS_DISMISSED = "DISMISSED"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_ACKNOWLEDGED, "Acknowledged"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_DISMISSED, "Dismissed"),
    ]
    ACTIVE_STATUSES = [STATUS_OPEN, STATUS_ACKNOWLEDGED]

    SEVERITY_LOW = "LOW"
    SEVERITY_MEDIUM = "MEDIUM"
    SEVERITY_HIGH = "HIGH"
    SEVERITY_CHOICES = [
        (SEVERITY_LOW, "Low"),
        (SEVERITY_MEDIUM, "Medium"),
        (SEVERITY_HIGH, "High"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    review = models.ForeignKey(
        FacilityReadinessReview,
        on_delete=models.PROTECT,
        related_name="escalations",
    )
    facility = models.ForeignKey(
        HealthFacility,
        on_delete=models.PROTECT,
        related_name="readiness_escalations",
    )
    ward = models.ForeignKey(
        Ward,
        on_delete=models.PROTECT,
        related_name="facility_readiness_escalations",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default=SEVERITY_LOW)
    reason = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facility_readiness_escalations_created",
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facility_readiness_escalations_acknowledged",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="facility_readiness_escalations_assigned",
    )
    notes = models.TextField(blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["review"],
                condition=models.Q(status__in=["OPEN", "ACKNOWLEDGED"]),
                name="unique_active_facility_escalation_per_review",
            ),
            models.UniqueConstraint(
                fields=["facility"],
                condition=models.Q(status__in=["OPEN", "ACKNOWLEDGED"]),
                name="unique_active_facility_escalation_per_facility",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="risk_facesc_status_idx"),
            models.Index(fields=["facility", "status"], name="risk_facesc_facility_idx"),
            models.Index(fields=["ward", "status"], name="risk_facesc_ward_idx"),
            models.Index(fields=["assigned_to", "status"], name="risk_facesc_assign_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.facility.name} county review [{self.status}]"


class CHV(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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


class CHVMessage(models.Model):
    CHANNEL_SMS = "SMS"
    CHANNEL_CHOICES = [
        (CHANNEL_SMS, "SMS"),
    ]

    STATUS_QUEUED = "QUEUED"
    STATUS_SENT = "SENT"
    STATUS_DELIVERED = "DELIVERED"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_SENT, "Sent"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_FAILED, "Failed"),
    ]

    DELIVERY_KIND_LIVE = "LIVE"
    DELIVERY_KIND_SIMULATED = "SIMULATED"
    DELIVERY_KIND_QUEUE_ONLY = "QUEUE_ONLY"
    DELIVERY_KIND_UNAVAILABLE = "UNAVAILABLE"
    DELIVERY_KIND_CHOICES = [
        (DELIVERY_KIND_LIVE, "Live"),
        (DELIVERY_KIND_SIMULATED, "Simulated"),
        (DELIVERY_KIND_QUEUE_ONLY, "Queue Only"),
        (DELIVERY_KIND_UNAVAILABLE, "Unavailable"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    chv = models.ForeignKey("risk.CHV", on_delete=models.PROTECT, related_name="messages")
    ward = models.ForeignKey("risk.Ward", on_delete=models.PROTECT, related_name="chv_messages")
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chv_messages_sent",
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_SMS)
    message_body = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    delivery_kind = models.CharField(max_length=20, choices=DELIVERY_KIND_CHOICES, default=DELIVERY_KIND_UNAVAILABLE)
    delivery_backend = models.CharField(max_length=50, blank=True)
    provider_reference = models.CharField(max_length=120, blank=True)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["chv", "created_at"], name="risk_chvmsg_chv_6a85ae_idx"),
            models.Index(fields=["status", "created_at"], name="risk_chvmsg_status_8f9cc6_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.chv.name} message [{self.status}]"


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
    operator_note = models.TextField(blank=True)
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

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
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
    guided_request_metadata = models.JSONField(default=dict, blank=True)
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


class DashboardNotification(models.Model):
    TYPE_WARD_RISK_HIGH = "WARD_RISK_HIGH"
    TYPE_ALERT_FAILED = "ALERT_FAILED"
    TYPE_ALERT_RETRY_PENDING = "ALERT_RETRY_PENDING"
    TYPE_FEED_STALE = "FEED_STALE"
    TYPE_CHV_COVERAGE_REQUEST_STATUS = "CHV_COVERAGE_REQUEST_STATUS"
    TYPE_CHOICES = [
        (TYPE_WARD_RISK_HIGH, "Ward Risk High"),
        (TYPE_ALERT_FAILED, "Alert Failed"),
        (TYPE_ALERT_RETRY_PENDING, "Alert Retry Pending"),
        (TYPE_FEED_STALE, "Feed Stale"),
        (TYPE_CHV_COVERAGE_REQUEST_STATUS, "CHV Coverage Request Status"),
    ]

    SEVERITY_INFO = "INFO"
    SEVERITY_WARNING = "WARNING"
    SEVERITY_CRITICAL = "CRITICAL"
    SEVERITY_CHOICES = [
        (SEVERITY_INFO, "Info"),
        (SEVERITY_WARNING, "Warning"),
        (SEVERITY_CRITICAL, "Critical"),
    ]

    STATE_NEW = "NEW"
    STATE_SEEN = "SEEN"
    STATE_ACKNOWLEDGED = "ACKNOWLEDGED"
    STATE_RESOLVED = "RESOLVED"
    STATE_DISMISSED = "DISMISSED"
    STATE_EXPIRED = "EXPIRED"
    STATE_CHOICES = [
        (STATE_NEW, "New"),
        (STATE_SEEN, "Seen"),
        (STATE_ACKNOWLEDGED, "Acknowledged"),
        (STATE_RESOLVED, "Resolved"),
        (STATE_DISMISSED, "Dismissed"),
        (STATE_EXPIRED, "Expired"),
    ]

    SCOPE_GLOBAL = "GLOBAL"
    SCOPE_WARD = "WARD"
    RECIPIENT_SCOPE_CHOICES = [
        (SCOPE_GLOBAL, "Global"),
        (SCOPE_WARD, "Ward"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    external_key = models.CharField(max_length=180, unique=True)
    type = models.CharField(max_length=40, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_INFO)
    title = models.CharField(max_length=255)
    body = models.TextField()
    source_system = models.CharField(max_length=80, default="risk")
    source_object_type = models.CharField(max_length=40, blank=True)
    source_object_id = models.CharField(max_length=80, blank=True)
    href = models.CharField(max_length=255, blank=True)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_NEW)
    recipient_scope = models.CharField(max_length=20, choices=RECIPIENT_SCOPE_CHOICES, default=SCOPE_GLOBAL)
    recipient_role = models.CharField(max_length=20, blank=True)
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dashboard_notifications",
    )
    ward = models.ForeignKey(
        Ward,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dashboard_notifications",
    )
    requires_acknowledgement = models.BooleanField(default=False)
    dismissible = models.BooleanField(default=True)
    auto_resolve = models.BooleanField(default=False)
    pinned_until_actioned = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    seen_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["state", "created_at"]),
            models.Index(fields=["severity", "created_at"]),
            models.Index(fields=["recipient_role", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} [{self.state}]"


class DashboardNotificationEvent(models.Model):
    ACTION_CREATED = "CREATED"
    ACTION_SEEN = "SEEN"
    ACTION_ACKNOWLEDGED = "ACKNOWLEDGED"
    ACTION_RESOLVED = "RESOLVED"
    ACTION_DISMISSED = "DISMISSED"
    ACTION_EXPIRED = "EXPIRED"
    ACTION_UPDATED = "UPDATED"
    ACTION_CHOICES = [
        (ACTION_CREATED, "Created"),
        (ACTION_SEEN, "Seen"),
        (ACTION_ACKNOWLEDGED, "Acknowledged"),
        (ACTION_RESOLVED, "Resolved"),
        (ACTION_DISMISSED, "Dismissed"),
        (ACTION_EXPIRED, "Expired"),
        (ACTION_UPDATED, "Updated"),
    ]

    notification = models.ForeignKey(
        DashboardNotification,
        on_delete=models.CASCADE,
        related_name="events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dashboard_notification_events",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    old_state = models.CharField(max_length=20, blank=True)
    new_state = models.CharField(max_length=20, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["notification", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.notification_id} {self.action}"


class AlertWorkflowState(models.Model):
    STATUS_REVIEW_PENDING = "REVIEW_PENDING"
    STATUS_QUEUED = "QUEUED"
    STATUS_DELIVERED = "DELIVERED"
    STATUS_RETRY_PENDING = "RETRY_PENDING"
    STATUS_FAILED = "FAILED"
    STATUS_RESOLVED = "RESOLVED"
    STATUS_CHOICES = [
        (STATUS_REVIEW_PENDING, "Review Pending"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_RETRY_PENDING, "Retry Pending"),
        (STATUS_FAILED, "Failed"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    SEVERITY_HIGH = "HIGH"
    SEVERITY_MEDIUM = "MEDIUM"
    SEVERITY_REVIEW = "REVIEW"
    SEVERITY_CHOICES = [
        (SEVERITY_HIGH, "High"),
        (SEVERITY_MEDIUM, "Medium"),
        (SEVERITY_REVIEW, "Review"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    ward = models.OneToOneField(Ward, on_delete=models.CASCADE, related_name="alert_workflow_state")
    alert = models.ForeignKey(Alert, on_delete=models.SET_NULL, null=True, blank=True, related_name="workflow_states")
    latest_risk_score = models.ForeignKey(
        RiskScore,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="workflow_states",
    )
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_REVIEW_PENDING)
    decision_mode = models.CharField(max_length=40, default="risk_only")
    confidence = models.CharField(max_length=20, default="review")
    trigger_severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_REVIEW)
    alert_delivery_state = models.CharField(max_length=40, default="awaiting_review")
    alert_delivery_label = models.CharField(max_length=120, blank=True)
    risk_level = models.CharField(max_length=10, choices=Ward.RISK_CHOICES, null=True, blank=True)
    risk_score = models.FloatField(null=True, blank=True)
    predicted_cases = models.PositiveIntegerField(default=0)
    reason_flagged = models.TextField(blank=True)
    trigger_reason = models.TextField(blank=True)
    recommended_action = models.TextField(blank=True)
    recommended_response = models.TextField(blank=True)
    expected_operational_effect = models.TextField(blank=True)
    rules_basis = models.JSONField(default=dict, blank=True)
    trigger_reason_items = models.JSONField(default=list, blank=True)
    eligible_actions = models.JSONField(default=list, blank=True)
    active_alert_count = models.PositiveIntegerField(default=0)
    delivered_alert_count = models.PositiveIntegerField(default=0)
    retry_pending_alert_count = models.PositiveIntegerField(default=0)
    failed_alert_count = models.PositiveIntegerField(default=0)
    queued_alert_count = models.PositiveIntegerField(default=0)
    triggered_at = models.DateTimeField(null=True, blank=True)
    latest_risk_update_at = models.DateTimeField(null=True, blank=True)
    last_manual_request_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    last_evaluated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["status", "updated_at"]),
            models.Index(fields=["trigger_severity", "updated_at"]),
            models.Index(fields=["last_evaluated_at"]),
        ]

    def __str__(self) -> str:
        return f"Workflow {self.ward.name} [{self.status}]"


class AlertWorkflowEvent(models.Model):
    ACTION_MATERIALIZED = "MATERIALIZED"
    ACTION_MANUAL_REQUEST_QUEUED = "MANUAL_REQUEST_QUEUED"
    ACTION_STATUS_CHANGED = "STATUS_CHANGED"
    ACTION_CHOICES = [
        (ACTION_MATERIALIZED, "Materialized"),
        (ACTION_MANUAL_REQUEST_QUEUED, "Manual Request Queued"),
        (ACTION_STATUS_CHANGED, "Status Changed"),
    ]

    workflow = models.ForeignKey(AlertWorkflowState, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alert_workflow_events",
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES, default=ACTION_MATERIALIZED)
    old_status = models.CharField(max_length=24, blank=True)
    new_status = models.CharField(max_length=24, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["workflow", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.workflow.ward.name} {self.action}"


class CHVCoverageRequest(models.Model):
    STATUS_OPEN = "OPEN"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_RESOLVED = "RESOLVED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_RESOLVED, "Resolved"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    PRIORITY_LOW = "LOW"
    PRIORITY_MEDIUM = "MEDIUM"
    PRIORITY_HIGH = "HIGH"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_MEDIUM, "Medium"),
        (PRIORITY_HIGH, "High"),
    ]

    TRIGGER_SOURCE_MANUAL = "MANUAL"
    TRIGGER_SOURCE_ALERT_DRIVEN = "ALERT_DRIVEN"
    TRIGGER_SOURCE_CHOICES = [
        (TRIGGER_SOURCE_MANUAL, "Manual"),
        (TRIGGER_SOURCE_ALERT_DRIVEN, "Alert Driven"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    ward = models.ForeignKey(
        Ward,
        on_delete=models.PROTECT,
        related_name="chv_coverage_requests",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chv_coverage_requests_requested",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    trigger_source = models.CharField(
        max_length=20,
        choices=TRIGGER_SOURCE_CHOICES,
        default=TRIGGER_SOURCE_MANUAL,
    )
    reason = models.TextField()
    requested_chv_count = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)
    assigned_to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chv_coverage_requests_owned",
    )
    assigned_to_team = models.CharField(max_length=120, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chv_coverage_requests_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_decision_reason = models.TextField(blank=True)
    expected_response_by = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["ward"],
                condition=models.Q(
                    status__in=[
                        "OPEN",
                        "APPROVED",
                        "IN_PROGRESS",
                    ]
                ),
                name="unique_live_chv_coverage_request_per_ward",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="risk_chvcov_status_3a8532_idx"),
            models.Index(fields=["priority", "created_at"], name="risk_chvcov_priorit_54f322_idx"),
            models.Index(fields=["trigger_source", "created_at"], name="risk_chvcov_trigger_04df10_idx"),
            models.Index(fields=["expected_response_by"], name="risk_chvcov_expecte_1ad931_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.ward.name} [{self.status}]"


class CHVCoverageRequestAlertLink(models.Model):
    coverage_request = models.ForeignKey(
        CHVCoverageRequest,
        on_delete=models.PROTECT,
        related_name="linked_alert_links",
    )
    alert = models.ForeignKey(
        Alert,
        on_delete=models.PROTECT,
        related_name="chv_coverage_request_links",
    )
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chv_coverage_request_alert_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["coverage_request", "alert"],
                name="unique_chv_coverage_request_alert_link",
            ),
        ]
        indexes = [
            models.Index(fields=["coverage_request", "created_at"], name="risk_chvalink_cov_c4879f"),
            models.Index(fields=["alert", "created_at"], name="risk_chvalink_alt_0730cb"),
        ]

    def __str__(self) -> str:
        return f"{self.coverage_request.public_id} <- {self.alert.public_id}"


class CHVAssignment(models.Model):
    STATUS_ACTIVE = "ACTIVE"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    coverage_request = models.ForeignKey(
        CHVCoverageRequest,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    ward = models.ForeignKey(
        Ward,
        on_delete=models.PROTECT,
        related_name="chv_assignments",
    )
    chv = models.ForeignKey(
        CHV,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chv_assignments_created",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["coverage_request"],
                condition=models.Q(status="ACTIVE"),
                name="unique_active_chv_assignment_per_request",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="risk_chvass_status_bcfa68_idx"),
            models.Index(fields=["ward", "status"], name="risk_chvass_ward_id_9eb603_idx"),
            models.Index(fields=["chv", "status"], name="risk_chvass_chv_id_3f583f_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.chv.name} -> {self.ward.name} [{self.status}]"


class CHVCoverageRequestEvent(models.Model):
    ACTION_CREATED = "CREATED"
    ACTION_ALERT_LINKAGE_ATTACHED = "ALERT_LINKAGE_ATTACHED"
    ACTION_ALERT_LINKAGE_REDIRECTED = "ALERT_LINKAGE_REDIRECTED"
    ACTION_APPROVED = "APPROVED"
    ACTION_REJECTED = "REJECTED"
    ACTION_CANCELLED = "CANCELLED"
    ACTION_RESOLVED = "RESOLVED"
    ACTION_OWNERSHIP_CHANGED = "OWNERSHIP_CHANGED"
    ACTION_ASSIGNMENT_CREATED = "ASSIGNMENT_CREATED"
    ACTION_ASSIGNMENT_COMPLETED = "ASSIGNMENT_COMPLETED"
    ACTION_ASSIGNMENT_CANCELLED = "ASSIGNMENT_CANCELLED"
    ACTION_CHOICES = [
        (ACTION_CREATED, "Created"),
        (ACTION_ALERT_LINKAGE_ATTACHED, "Alert Linkage Attached"),
        (ACTION_ALERT_LINKAGE_REDIRECTED, "Alert Linkage Redirected"),
        (ACTION_APPROVED, "Approved"),
        (ACTION_REJECTED, "Rejected"),
        (ACTION_CANCELLED, "Cancelled"),
        (ACTION_RESOLVED, "Resolved"),
        (ACTION_OWNERSHIP_CHANGED, "Ownership Changed"),
        (ACTION_ASSIGNMENT_CREATED, "Assignment Created"),
        (ACTION_ASSIGNMENT_COMPLETED, "Assignment Completed"),
        (ACTION_ASSIGNMENT_CANCELLED, "Assignment Cancelled"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    coverage_request = models.ForeignKey(
        CHVCoverageRequest,
        on_delete=models.PROTECT,
        related_name="events",
    )
    assignment = models.ForeignKey(
        CHVAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chv_coverage_request_events",
    )
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    detail = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"], name="risk_chvcov_action_567608_idx"),
            models.Index(fields=["coverage_request", "created_at"], name="risk_chvcov_coverag_2b70a4_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.coverage_request.ward.name} {self.action}"


class CHVCoverageRequestEmailDelivery(models.Model):
    STATUS_SENT = "SENT"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    coverage_request = models.ForeignKey(
        CHVCoverageRequest,
        on_delete=models.PROTECT,
        related_name="email_deliveries",
    )
    event = models.ForeignKey(
        CHVCoverageRequestEvent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_deliveries",
    )
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chv_coverage_request_email_deliveries",
    )
    recipient_email = models.EmailField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    delivery_backend = models.CharField(max_length=40, blank=True)
    external_id = models.CharField(max_length=255, blank=True)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["coverage_request", "created_at"], name="risk_chvema_coverag_2f1f3e_idx"),
            models.Index(fields=["status", "created_at"], name="risk_chvema_status_9a6a3b_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.coverage_request.public_id} email [{self.status}]"


class ScenarioSimulationRun(models.Model):
    SCENARIO_RAINFALL_INCREASE = "RAINFALL_INCREASE"
    SCENARIO_RESPONSE_DELAY = "RESPONSE_DELAY"
    SCENARIO_CHOICES = [
        (SCENARIO_RAINFALL_INCREASE, "Rainfall Increase"),
        (SCENARIO_RESPONSE_DELAY, "Response Delay"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    scenario_id = models.CharField(max_length=40, choices=SCENARIO_CHOICES)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scenario_simulation_runs",
    )
    input_parameters = models.JSONField(default=dict, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    ward_results = models.JSONField(default=list, blank=True)
    facility_results = models.JSONField(default=list, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["scenario_id", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.scenario_id} {self.created_at}"
