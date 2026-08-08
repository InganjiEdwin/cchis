import hashlib
import json
import re
import uuid
from string import Formatter

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.contrib.gis.db import models
from django.conf import settings
from django.utils import timezone

from .chv_localization import (
    DEFAULT_CHV_LANGUAGE,
    SUPPORTED_CHV_LANGUAGE_CHOICES,
    SUPPORTED_CHV_LANGUAGES,
    normalize_language_code,
    supported_language_or_default,
)


MESSAGE_TEMPLATE_PLACEHOLDER_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _stable_identity_digest(payload: dict) -> str:
    serialized = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _message_template_body_placeholders(body: str) -> set[str]:
    placeholders: set[str] = set()
    try:
        parsed = Formatter().parse(body or "")
    except ValueError as exc:
        raise ValidationError(f"Template body has invalid placeholder syntax: {exc}") from exc

    for _literal, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if format_spec or conversion or "." in field_name or "[" in field_name:
            raise ValidationError(
                "Template placeholders must be simple names like {ward_name}; "
                "format specifiers, conversions, attribute access, and indexes are not supported."
            )
        if not MESSAGE_TEMPLATE_PLACEHOLDER_RE.match(field_name):
            raise ValidationError(
                "Template placeholders must use lowercase letters, numbers, and underscores, "
                "and start with a letter."
            )
        placeholders.add(field_name)
    return placeholders


def _ussd_menu_tree_structure_signature(menu_tree: dict) -> dict[str, list[str]]:
    if not isinstance(menu_tree, dict):
        return {"routes": [], "nodes": [], "response_types": []}
    routes = menu_tree.get("routes")
    nodes = menu_tree.get("nodes")
    return {
        "routes": [f"{route}:{node_key}" for route, node_key in sorted(routes.items())]
        if isinstance(routes, dict)
        else [],
        "nodes": sorted(nodes.keys()) if isinstance(nodes, dict) else [],
        "response_types": [
            f"{node_key}:{str(node.get('response_type') or '').upper()}"
            for node_key, node in sorted(nodes.items())
            if isinstance(node, dict)
        ]
        if isinstance(nodes, dict)
        else [],
    }


USSD_RESPONSE_TEXT_MAX_CHARS = 182


def _validate_ussd_response_copy_budget(response_text: str, *, required_prefix: str | None = None) -> None:
    text = (response_text or "").strip()
    if required_prefix and not text.startswith(f"{required_prefix} "):
        raise ValidationError(f"USSD response must start with {required_prefix}.")
    if len(text) > USSD_RESPONSE_TEXT_MAX_CHARS:
        raise ValidationError(
            f"USSD response exceeds {USSD_RESPONSE_TEXT_MAX_CHARS} characters: {len(text)}."
        )


def _validate_ussd_menu_tree_copy_budget(menu_tree: dict) -> None:
    if not isinstance(menu_tree, dict):
        raise ValidationError("USSD menu tree must be a JSON object.")
    nodes = menu_tree.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        raise ValidationError("USSD menu tree requires nodes before approval.")
    for node_key, node in nodes.items():
        if not isinstance(node, dict):
            raise ValidationError(f"USSD node {node_key} must be an object.")
        response_type = str(node.get("response_type") or "").upper()
        body = str(node.get("body") or "").strip()
        if response_type not in {"CON", "END"}:
            raise ValidationError(f"USSD node {node_key} must use response_type CON or END.")
        if not body:
            raise ValidationError(f"USSD node {node_key} requires body copy.")
        _validate_ussd_response_copy_budget(f"{response_type} {body}", required_prefix=response_type)


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


class ContactPreference(models.Model):
    AUDIENCE_HOUSEHOLD = "HOUSEHOLD"
    AUDIENCE_CHV = "CHV"
    AUDIENCE_FACILITY_CONTACT = "FACILITY_CONTACT"
    AUDIENCE_OPERATOR = "OPERATOR"
    AUDIENCE_CHOICES = [
        (AUDIENCE_HOUSEHOLD, "Household"),
        (AUDIENCE_CHV, "CHV"),
        (AUDIENCE_FACILITY_CONTACT, "Facility contact"),
        (AUDIENCE_OPERATOR, "Operator"),
    ]

    CHANNEL_SMS = "SMS"
    CHANNEL_EMAIL = "EMAIL"
    CHANNEL_USSD = "USSD"
    CHANNEL_SYSTEM = "SYSTEM"
    CHANNEL_CHOICES = [
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_EMAIL, "Email"),
        (CHANNEL_USSD, "USSD"),
        (CHANNEL_SYSTEM, "System"),
    ]

    CONSENT_UNKNOWN = "UNKNOWN"
    CONSENT_GRANTED = "GRANTED"
    CONSENT_DENIED = "DENIED"
    CONSENT_EXPIRED = "EXPIRED"
    CONSENT_CHOICES = [
        (CONSENT_UNKNOWN, "Unknown"),
        (CONSENT_GRANTED, "Granted"),
        (CONSENT_DENIED, "Denied"),
        (CONSENT_EXPIRED, "Expired"),
    ]

    OPT_OUT_NOT_OPTED_OUT = "NOT_OPTED_OUT"
    OPT_OUT_OPTED_OUT = "OPTED_OUT"
    OPT_OUT_CHOICES = [
        (OPT_OUT_NOT_OPTED_OUT, "Not opted out"),
        (OPT_OUT_OPTED_OUT, "Opted out"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    audience_type = models.CharField(max_length=32, choices=AUDIENCE_CHOICES)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_SMS)
    phone_number = models.CharField(max_length=20, blank=True)
    contact_reference = models.CharField(max_length=180, blank=True)
    consent_status = models.CharField(max_length=20, choices=CONSENT_CHOICES, default=CONSENT_UNKNOWN)
    opt_out_status = models.CharField(max_length=20, choices=OPT_OUT_CHOICES, default=OPT_OUT_NOT_OPTED_OUT)
    source = models.CharField(max_length=120)
    source_reference = models.CharField(max_length=180, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_preferences_recorded",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-recorded_at", "-created_at"]
        indexes = [
            models.Index(fields=["audience_type", "channel", "phone_number"], name="risk_contactpref_phone_idx"),
            models.Index(fields=["audience_type", "channel", "contact_reference"], name="risk_contactpref_ref_idx"),
            models.Index(fields=["opt_out_status", "recorded_at"], name="risk_contactpref_opt_idx"),
            models.Index(fields=["consent_status", "recorded_at"], name="risk_contactpref_con_idx"),
            models.Index(fields=["expires_at", "recorded_at"], name="risk_contactpref_exp_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(phone_number__gt="") | models.Q(contact_reference__gt=""),
                name="contact_preference_requires_phone_or_ref",
            ),
        ]

    @staticmethod
    def normalize_phone_number(value: str) -> str:
        compact = (value or "").strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if compact.startswith("+254") and len(compact) == 13 and compact[1:].isdigit():
            return compact
        if compact.startswith("254") and len(compact) == 12 and compact.isdigit():
            return f"+{compact}"
        if compact.startswith("0") and len(compact) == 10 and compact.isdigit():
            return f"+254{compact[1:]}"
        return compact

    @classmethod
    def is_valid_phone_number(cls, value: str) -> bool:
        normalized = cls.normalize_phone_number(value)
        return bool(
            normalized.startswith("+254")
            and len(normalized) == 13
            and normalized[1:].isdigit()
            and normalized[4] in {"1", "7"}
        )

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())

    def save(self, *args, **kwargs):
        self.phone_number = self.normalize_phone_number(self.phone_number)
        self.contact_reference = self.contact_reference.strip()
        self.source = self.source.strip()
        self.source_reference = self.source_reference.strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        contact = self.contact_reference or self.phone_number
        return f"{self.audience_type} {self.channel} preference for {contact}"


class ContactPreferenceAuditEvent(models.Model):
    ACTION_RECORDED = "RECORDED"
    ACTION_ALLOWED = "ALLOWED"
    ACTION_BLOCKED_OPT_OUT = "BLOCKED_OPT_OUT"
    ACTION_BLOCKED_CONSENT_REQUIRED = "BLOCKED_CONSENT_REQUIRED"
    ACTION_BLOCKED_CONSENT_DENIED = "BLOCKED_CONSENT_DENIED"
    ACTION_BLOCKED_CONSENT_EXPIRED = "BLOCKED_CONSENT_EXPIRED"
    ACTION_EMERGENCY_OVERRIDE_USED = "EMERGENCY_OVERRIDE_USED"
    ACTION_CHOICES = [
        (ACTION_RECORDED, "Recorded"),
        (ACTION_ALLOWED, "Allowed"),
        (ACTION_BLOCKED_OPT_OUT, "Blocked by opt-out"),
        (ACTION_BLOCKED_CONSENT_REQUIRED, "Blocked because consent is required"),
        (ACTION_BLOCKED_CONSENT_DENIED, "Blocked because consent was denied"),
        (ACTION_BLOCKED_CONSENT_EXPIRED, "Blocked because consent expired"),
        (ACTION_EMERGENCY_OVERRIDE_USED, "Emergency override used"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    preference = models.ForeignKey(
        ContactPreference,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)
    audience_type = models.CharField(max_length=32, choices=ContactPreference.AUDIENCE_CHOICES)
    channel = models.CharField(max_length=20, choices=ContactPreference.CHANNEL_CHOICES, default=ContactPreference.CHANNEL_SMS)
    phone_number = models.CharField(max_length=20, blank=True)
    contact_reference = models.CharField(max_length=180, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contact_preference_audit_events",
    )
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["action", "created_at"], name="risk_contactaudit_action_idx"),
            models.Index(fields=["audience_type", "channel", "created_at"], name="risk_contactaudit_aud_idx"),
            models.Index(fields=["contact_reference", "created_at"], name="risk_contactaudit_ref_idx"),
            models.Index(fields=["phone_number", "created_at"], name="risk_contactaudit_phone_idx"),
        ]

    def save(self, *args, **kwargs):
        self.phone_number = ContactPreference.normalize_phone_number(self.phone_number)
        self.contact_reference = self.contact_reference.strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        contact = self.contact_reference or self.phone_number
        return f"{self.action} {self.audience_type} {contact}"


class MessageTemplate(models.Model):
    AUDIENCE_CHV = "chv"
    AUDIENCE_HOUSEHOLD = "household"
    AUDIENCE_FACILITY_CONTACT = "facility_contact"
    AUDIENCE_COUNTY_OPERATOR = "county_operator"
    AUDIENCE_SYSTEM_OPERATOR = "system_operator"
    AUDIENCE_CHOICES = [
        (AUDIENCE_CHV, "CHV"),
        (AUDIENCE_HOUSEHOLD, "Household"),
        (AUDIENCE_FACILITY_CONTACT, "Facility contact"),
        (AUDIENCE_COUNTY_OPERATOR, "County operator"),
        (AUDIENCE_SYSTEM_OPERATOR, "System operator"),
    ]

    CHANNEL_SMS = "sms"
    CHANNEL_USSD = "ussd"
    CHANNEL_DASHBOARD = "dashboard"
    CHANNEL_OFFLINE_CHV_BUNDLE = "offline_chv_bundle"
    CHANNEL_CHOICES = [
        (CHANNEL_SMS, "SMS"),
        (CHANNEL_USSD, "USSD"),
        (CHANNEL_DASHBOARD, "Dashboard"),
        (CHANNEL_OFFLINE_CHV_BUNDLE, "Offline CHV bundle"),
    ]

    RISK_LOW = "low"
    RISK_MEDIUM = "medium"
    RISK_HIGH = "high"
    RISK_CRITICAL = "critical"
    RISK_CHOICES = [
        (RISK_LOW, "Low"),
        (RISK_MEDIUM, "Medium"),
        (RISK_HIGH, "High"),
        (RISK_CRITICAL, "Critical"),
    ]

    APPROVAL_DRAFT = "draft"
    APPROVAL_PENDING_REVIEW = "pending_review"
    APPROVAL_APPROVED = "approved"
    APPROVAL_REJECTED = "rejected"
    APPROVAL_RETIRED = "retired"
    APPROVAL_CHOICES = [
        (APPROVAL_DRAFT, "Draft"),
        (APPROVAL_PENDING_REVIEW, "Pending review"),
        (APPROVAL_APPROVED, "Approved"),
        (APPROVAL_REJECTED, "Rejected"),
        (APPROVAL_RETIRED, "Retired"),
    ]

    TRANSLATION_DRAFT = "draft"
    TRANSLATION_NEEDS_REVIEW = "needs_translation_review"
    TRANSLATION_APPROVED = "approved"
    TRANSLATION_RETIRED = "retired"
    TRANSLATION_BLOCKED_SOURCE_RETIRED = "blocked_source_retired"
    TRANSLATION_STATUS_CHOICES = [
        (TRANSLATION_DRAFT, "Draft"),
        (TRANSLATION_NEEDS_REVIEW, "Needs translation review"),
        (TRANSLATION_APPROVED, "Approved"),
        (TRANSLATION_RETIRED, "Retired"),
        (TRANSLATION_BLOCKED_SOURCE_RETIRED, "Blocked because source is retired"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    template_key = models.CharField(max_length=120)
    audience_type = models.CharField(max_length=32, choices=AUDIENCE_CHOICES)
    channel = models.CharField(max_length=32, choices=CHANNEL_CHOICES)
    language = models.CharField(max_length=20, choices=SUPPORTED_CHV_LANGUAGE_CHOICES, default=DEFAULT_CHV_LANGUAGE)
    version = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=160)
    body = models.TextField()
    placeholders = models.JSONField(default=list, blank=True)
    approval_status = models.CharField(max_length=32, choices=APPROVAL_CHOICES, default=APPROVAL_DRAFT)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_templates_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)
    translation_status = models.CharField(
        max_length=40,
        choices=TRANSLATION_STATUS_CHOICES,
        default=TRANSLATION_DRAFT,
    )
    source_template = models.ForeignKey(
        "risk.MessageTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="translation_variants",
    )
    translation_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_template_translation_reviews",
    )
    translation_reviewed_at = models.DateTimeField(null=True, blank=True)
    translation_review_notes = models.TextField(blank=True)
    owner = models.CharField(max_length=120)
    risk_level = models.CharField(max_length=20, choices=RISK_CHOICES, default=RISK_MEDIUM)
    public_health_caveats = models.TextField(blank=True)
    lineage_metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="message_templates_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["template_key", "language", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["template_key", "language", "version"],
                name="risk_msgtmpl_key_lang_ver_uniq",
            ),
            models.CheckConstraint(
                check=models.Q(version__gte=1),
                name="risk_msgtmpl_version_positive",
            ),
            models.CheckConstraint(
                check=models.Q(language__in=SUPPORTED_CHV_LANGUAGES),
                name="risk_msgtmpl_lang_supported",
            ),
        ]
        indexes = [
            models.Index(fields=["template_key", "language", "version"], name="risk_msgtmpl_lookup_idx"),
            models.Index(fields=["audience_type", "channel", "approval_status"], name="risk_msgtmpl_status_idx"),
            models.Index(fields=["approval_status", "retired_at"], name="risk_msgtmpl_active_idx"),
            models.Index(fields=["source_template", "translation_status"], name="risk_msgtmpl_source_trans_idx"),
        ]

    @property
    def is_approved(self) -> bool:
        return self.approval_status == self.APPROVAL_APPROVED and self.retired_at is None

    def clean(self):
        errors: dict[str, list[str]] = {}
        declared_placeholders = self.placeholders or []
        if not isinstance(declared_placeholders, list):
            errors["placeholders"] = ["Placeholders must be a list of simple placeholder names."]
        else:
            invalid_names = [
                name
                for name in declared_placeholders
                if not isinstance(name, str) or not MESSAGE_TEMPLATE_PLACEHOLDER_RE.match(name)
            ]
            if invalid_names:
                errors["placeholders"] = [
                    "Placeholders must use lowercase letters, numbers, and underscores, and start with a letter."
                ]
            elif len(set(declared_placeholders)) != len(declared_placeholders):
                errors["placeholders"] = ["Placeholders must not contain duplicate names."]

        try:
            body_placeholders = _message_template_body_placeholders(self.body)
        except ValidationError as exc:
            errors["body"] = exc.messages
            body_placeholders = set()

        if isinstance(declared_placeholders, list) and not errors.get("placeholders"):
            declared_set = set(declared_placeholders)
            undeclared = sorted(body_placeholders - declared_set)
            unused = sorted(declared_set - body_placeholders)
            if undeclared or unused:
                details = []
                if undeclared:
                    details.append("undeclared in registry: " + ", ".join(undeclared))
                if unused:
                    details.append("declared but unused in body: " + ", ".join(unused))
                errors["placeholders"] = ["Template placeholders must match the body (" + "; ".join(details) + ")."]

        if self.approval_status == self.APPROVAL_APPROVED and self.approved_at is None:
            errors["approved_at"] = ["Approved templates require an approval timestamp."]
        if self.approved_at is not None and self.approval_status != self.APPROVAL_APPROVED:
            errors["approval_status"] = ["Only approved templates may carry an approval timestamp."]
        if self.retired_at is not None and self.approval_status != self.APPROVAL_RETIRED:
            errors["approval_status"] = ["Templates with retired_at must use retired approval status."]
        normalized_language = normalize_language_code(self.language) or DEFAULT_CHV_LANGUAGE
        if normalized_language not in SUPPORTED_CHV_LANGUAGES:
            errors["language"] = ["Message template language must be one of: en, sw, luo."]
        if normalized_language == DEFAULT_CHV_LANGUAGE and self.source_template_id:
            errors["source_template"] = ["English source templates must not link to another source template."]

        source_template = self.source_template
        if normalized_language != DEFAULT_CHV_LANGUAGE and source_template is not None:
            if source_template.language != DEFAULT_CHV_LANGUAGE:
                errors["source_template"] = ["Translated message templates must link to an English source template."]
            elif source_template.template_key != self.template_key or source_template.version != self.version:
                errors["source_template"] = [
                    "Translated message templates must link to the English source for the same key and version."
                ]
            elif sorted(source_template.placeholders or []) != sorted(declared_placeholders or []):
                errors["placeholders"] = ["Translated message template placeholders must match the English source."]

        translation_review_required = (
            normalized_language != DEFAULT_CHV_LANGUAGE
            and (
                self.translation_status == self.TRANSLATION_APPROVED
                or self.approval_status == self.APPROVAL_APPROVED
            )
        )
        if translation_review_required:
            if source_template is None:
                errors["source_template"] = ["Translated message templates require an English source before approval."]
            elif source_template.approval_status != self.APPROVAL_APPROVED or source_template.retired_at is not None:
                errors["source_template"] = ["Translated message templates cannot be approved without an active approved English source."]
            if self.translation_status != self.TRANSLATION_APPROVED:
                errors["translation_status"] = ["Translated message templates require approved translation status before use."]
            if self.translation_reviewed_at is None:
                errors["translation_reviewed_at"] = ["Approved translated message templates require translation review metadata."]

        public_health_copy = (
            self.audience_type in {self.AUDIENCE_CHV, self.AUDIENCE_HOUSEHOLD}
            or self.channel in {self.CHANNEL_USSD, self.CHANNEL_OFFLINE_CHV_BUNDLE}
            or self.risk_level in {self.RISK_HIGH, self.RISK_CRITICAL}
        )
        if translation_review_required and public_health_copy and not self.public_health_caveats.strip():
            errors["public_health_caveats"] = ["Approved translated public-health copy requires public-health caveats."]

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.template_key = self.template_key.strip()
        self.language = normalize_language_code(self.language) or DEFAULT_CHV_LANGUAGE
        self.translation_review_notes = self.translation_review_notes.strip()
        self.owner = self.owner.strip()
        self.title = self.title.strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.template_key} v{self.version} ({self.language})"


class PrivacyRetentionHold(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, related_name="privacy_retention_holds")
    object_id = models.CharField(max_length=80)
    target = GenericForeignKey("content_type", "object_id")
    reason = models.TextField()
    case_reference = models.CharField(max_length=160, blank=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="privacy_retention_holds_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="risk_privhold_target_idx"),
            models.Index(fields=["is_active", "expires_at"], name="risk_privhold_active_idx"),
            models.Index(fields=["case_reference", "created_at"], name="risk_privhold_case_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id"],
                condition=models.Q(is_active=True),
                name="risk_privhold_active_target_uniq",
            ),
        ]

    def is_currently_active(self) -> bool:
        if not self.is_active:
            return False
        if self.expires_at is None:
            return True
        return self.expires_at > timezone.now()

    def __str__(self) -> str:
        return f"{self.content_type.app_label}.{self.content_type.model}:{self.object_id}"


class PrivacyRetentionAuditEvent(models.Model):
    ACTION_DRY_RUN = "DRY_RUN"
    ACTION_ANONYMIZED = "ANONYMIZED"
    ACTION_DELETED = "DELETED"
    ACTION_HELD = "HELD"
    ACTION_SKIPPED = "SKIPPED"
    ACTION_SUMMARY = "SUMMARY"
    ACTION_CHOICES = [
        (ACTION_DRY_RUN, "Dry run"),
        (ACTION_ANONYMIZED, "Anonymized"),
        (ACTION_DELETED, "Deleted"),
        (ACTION_HELD, "Held"),
        (ACTION_SKIPPED, "Skipped"),
        (ACTION_SUMMARY, "Summary"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    run_id = models.UUIDField(db_index=True)
    action = models.CharField(max_length=24, choices=ACTION_CHOICES)
    record_family = models.CharField(max_length=80)
    model_label = models.CharField(max_length=120, blank=True)
    object_id = models.CharField(max_length=80, blank=True)
    cutoff_at = models.DateTimeField(null=True, blank=True)
    window_days = models.PositiveIntegerField(null=True, blank=True)
    dry_run = models.BooleanField(default=True)
    hold = models.ForeignKey(
        PrivacyRetentionHold,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="privacy_retention_audit_events",
    )
    decision_reason = models.TextField(blank=True)
    before_state = models.JSONField(default=dict, blank=True)
    after_state = models.JSONField(default=dict, blank=True)
    aggregate_metrics = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["record_family", "created_at"], name="risk_privaudit_family_idx"),
            models.Index(fields=["model_label", "object_id"], name="risk_privaudit_target_idx"),
            models.Index(fields=["action", "created_at"], name="risk_privaudit_action_idx"),
        ]

    def __str__(self) -> str:
        target = f" {self.model_label}:{self.object_id}" if self.model_label and self.object_id else ""
        return f"{self.record_family} {self.action}{target}"


class SensitiveExportRequest(models.Model):
    EXPORT_ALERT_LIST_CSV = "ALERT_LIST_CSV"
    EXPORT_ALERT_DETAIL_REPORT = "ALERT_DETAIL_REPORT"
    EXPORT_TYPE_CHOICES = [
        (EXPORT_ALERT_LIST_CSV, "Alert list CSV"),
        (EXPORT_ALERT_DETAIL_REPORT, "Alert detail report"),
    ]

    APPROVAL_PENDING = "PENDING"
    APPROVAL_APPROVED = "APPROVED"
    APPROVAL_REJECTED = "REJECTED"
    APPROVAL_EXPIRED = "EXPIRED"
    APPROVAL_CHOICES = [
        (APPROVAL_PENDING, "Pending"),
        (APPROVAL_APPROVED, "Approved"),
        (APPROVAL_REJECTED, "Rejected"),
        (APPROVAL_EXPIRED, "Expired"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    export_type = models.CharField(max_length=40, choices=EXPORT_TYPE_CHOICES)
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sensitive_export_requests",
    )
    purpose = models.TextField()
    filters = models.JSONField(default=dict, blank=True)
    sensitive_fields_included = models.JSONField(default=list, blank=True)
    approval_state = models.CharField(max_length=20, choices=APPROVAL_CHOICES, default=APPROVAL_PENDING)
    requires_approval = models.BooleanField(default=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sensitive_exports_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sensitive_exports_rejected",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    generated_filename = models.CharField(max_length=180, blank=True)
    generated_content_type = models.CharField(max_length=80, default="text/csv")
    generated_payload = models.TextField(blank=True)
    payload_sha256 = models.CharField(max_length=64, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    download_count = models.PositiveIntegerField(default=0)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["requester", "created_at"], name="risk_sensexp_requester_idx"),
            models.Index(fields=["export_type", "approval_state"], name="risk_sensexp_type_state_idx"),
            models.Index(fields=["expires_at", "approval_state"], name="risk_sensexp_expiry_idx"),
        ]

    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())

    def __str__(self) -> str:
        return f"{self.export_type} export {self.public_id} [{self.approval_state}]"


class SensitiveExportDownloadAudit(models.Model):
    OUTCOME_DOWNLOADED = "DOWNLOADED"
    OUTCOME_BLOCKED_NOT_APPROVED = "BLOCKED_NOT_APPROVED"
    OUTCOME_BLOCKED_EXPIRED = "BLOCKED_EXPIRED"
    OUTCOME_BLOCKED_PERMISSION = "BLOCKED_PERMISSION"
    OUTCOME_CHOICES = [
        (OUTCOME_DOWNLOADED, "Downloaded"),
        (OUTCOME_BLOCKED_NOT_APPROVED, "Blocked because export is not approved"),
        (OUTCOME_BLOCKED_EXPIRED, "Blocked because export expired"),
        (OUTCOME_BLOCKED_PERMISSION, "Blocked by permission"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    export_request = models.ForeignKey(
        SensitiveExportRequest,
        on_delete=models.PROTECT,
        related_name="download_audits",
    )
    downloader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sensitive_export_download_audits",
    )
    outcome = models.CharField(max_length=40, choices=OUTCOME_CHOICES)
    reason = models.TextField(blank=True)
    request_metadata = models.JSONField(default=dict, blank=True)
    downloaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-downloaded_at"]
        indexes = [
            models.Index(fields=["export_request", "downloaded_at"], name="risk_sensdown_export_idx"),
            models.Index(fields=["downloader", "downloaded_at"], name="risk_sensdown_user_idx"),
            models.Index(fields=["outcome", "downloaded_at"], name="risk_sensdown_outcome_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.export_request.public_id} {self.outcome}"


class ExternalSystem(models.Model):
    STATUS_ACTIVE = "ACTIVE"
    STATUS_INACTIVE = "INACTIVE"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_INACTIVE, "Inactive"),
    ]

    SYSTEM_DHIS2 = "DHIS2"
    SYSTEM_CSV_PARTNER = "CSV_PARTNER"
    SYSTEM_OTHER = "OTHER"
    SYSTEM_TYPE_CHOICES = [
        (SYSTEM_DHIS2, "DHIS2"),
        (SYSTEM_CSV_PARTNER, "CSV partner"),
        (SYSTEM_OTHER, "Other"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    system_key = models.CharField(max_length=80, unique=True)
    display_name = models.CharField(max_length=160)
    system_type = models.CharField(max_length=40, choices=SYSTEM_TYPE_CHOICES, default=SYSTEM_OTHER)
    owner = models.CharField(max_length=160)
    default_exchange_format = models.CharField(max_length=40, default="CSV")
    auth_config_reference = models.CharField(max_length=160, blank=True)
    api_base_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    lineage_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["system_key"]
        indexes = [
            models.Index(fields=["system_key", "status"], name="risk_extsys_key_status_idx"),
            models.Index(fields=["system_type", "status"], name="risk_extsys_type_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} [{self.system_key}]"


class InteroperabilityMappingVersion(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_RETIRED = "RETIRED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_RETIRED, "Retired"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    system = models.ForeignKey(
        ExternalSystem,
        on_delete=models.PROTECT,
        related_name="mapping_versions",
    )
    version_label = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    effective_date = models.DateField(default=timezone.localdate)
    retired_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interoperability_mapping_versions_reviewed",
    )
    lineage_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["system__system_key", "-effective_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["system", "version_label"], name="risk_iopmapver_unique_label"),
        ]
        indexes = [
            models.Index(fields=["system", "status"], name="risk_iopmapver_system_idx"),
            models.Index(fields=["effective_date", "status"], name="risk_iopmapver_effective_idx"),
        ]

    def clean(self):
        if self.status != self.STATUS_RETIRED and self.retired_at is not None:
            raise ValidationError("Only retired interoperability mapping versions may set retired_at.")

    def __str__(self) -> str:
        return f"{self.system.system_key} {self.version_label} [{self.status}]"


class InteroperabilityMappingStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    NEEDS_REVIEW = "NEEDS_REVIEW", "Needs review"
    RETIRED = "RETIRED", "Retired"
    REJECTED = "REJECTED", "Rejected"


class ExternalOrgUnitMapping(models.Model):
    INTERNAL_WARD = "WARD"
    INTERNAL_FACILITY = "HEALTH_FACILITY"
    INTERNAL_OBJECT_TYPE_CHOICES = [
        (INTERNAL_WARD, "Ward"),
        (INTERNAL_FACILITY, "Health facility"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    system = models.ForeignKey(
        ExternalSystem,
        on_delete=models.PROTECT,
        related_name="org_unit_mappings",
    )
    mapping_version = models.ForeignKey(
        InteroperabilityMappingVersion,
        on_delete=models.PROTECT,
        related_name="org_unit_mappings",
    )
    external_identifier = models.CharField(max_length=160)
    external_display_name = models.CharField(max_length=200, blank=True)
    internal_object_type = models.CharField(max_length=40, choices=INTERNAL_OBJECT_TYPE_CHOICES)
    internal_object_public_id = models.CharField(max_length=80)
    internal_object_code = models.CharField(max_length=80, blank=True)
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, null=True, blank=True, related_name="external_mappings")
    facility = models.ForeignKey(
        HealthFacility,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="external_mappings",
    )
    mapping_confidence = models.FloatField(default=1.0)
    status = models.CharField(
        max_length=20,
        choices=InteroperabilityMappingStatus.choices,
        default=InteroperabilityMappingStatus.NEEDS_REVIEW,
    )
    effective_date = models.DateField(default=timezone.localdate)
    retired_date = models.DateField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="external_org_unit_mappings_reviewed",
    )
    lineage_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["system__system_key", "external_identifier"]
        constraints = [
            models.UniqueConstraint(
                fields=["system", "mapping_version", "external_identifier"],
                name="risk_extorg_unique_external",
            ),
            models.CheckConstraint(
                check=models.Q(mapping_confidence__gte=0) & models.Q(mapping_confidence__lte=1),
                name="risk_extorg_confidence_range",
            ),
        ]
        indexes = [
            models.Index(fields=["system", "status"], name="risk_extorg_system_status_idx"),
            models.Index(fields=["internal_object_type", "internal_object_public_id"], name="risk_extorg_internal_idx"),
            models.Index(fields=["external_identifier"], name="risk_extorg_external_idx"),
        ]

    def clean(self):
        if self.internal_object_type == self.INTERNAL_WARD and not self.ward_id:
            raise ValidationError("Ward mappings must link to a Ward.")
        if self.internal_object_type == self.INTERNAL_FACILITY and not self.facility_id:
            raise ValidationError("Facility mappings must link to a HealthFacility.")
        if self.status != InteroperabilityMappingStatus.RETIRED and self.retired_date is not None:
            raise ValidationError("Only retired interoperability mappings may set retired_date.")

    def __str__(self) -> str:
        return f"{self.system.system_key}:{self.external_identifier} -> {self.internal_object_type}"


class ExternalDataElementMapping(models.Model):
    VALUE_TYPE_NUMBER = "NUMBER"
    VALUE_TYPE_TEXT = "TEXT"
    VALUE_TYPE_BOOLEAN = "BOOLEAN"
    VALUE_TYPE_DATE = "DATE"
    VALUE_TYPE_CHOICES = [
        (VALUE_TYPE_NUMBER, "Number"),
        (VALUE_TYPE_TEXT, "Text"),
        (VALUE_TYPE_BOOLEAN, "Boolean"),
        (VALUE_TYPE_DATE, "Date"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    system = models.ForeignKey(
        ExternalSystem,
        on_delete=models.PROTECT,
        related_name="data_element_mappings",
    )
    mapping_version = models.ForeignKey(
        InteroperabilityMappingVersion,
        on_delete=models.PROTECT,
        related_name="data_element_mappings",
    )
    exchange_type = models.CharField(max_length=80)
    external_identifier = models.CharField(max_length=160)
    external_display_name = models.CharField(max_length=200, blank=True)
    internal_field = models.CharField(max_length=120)
    value_type = models.CharField(max_length=20, choices=VALUE_TYPE_CHOICES, default=VALUE_TYPE_NUMBER)
    required_for_exchange = models.BooleanField(default=True)
    mapping_confidence = models.FloatField(default=1.0)
    status = models.CharField(
        max_length=20,
        choices=InteroperabilityMappingStatus.choices,
        default=InteroperabilityMappingStatus.NEEDS_REVIEW,
    )
    effective_date = models.DateField(default=timezone.localdate)
    retired_date = models.DateField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="external_data_element_mappings_reviewed",
    )
    lineage_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["system__system_key", "exchange_type", "internal_field"]
        constraints = [
            models.UniqueConstraint(
                fields=["system", "mapping_version", "exchange_type", "internal_field"],
                name="risk_extde_unique_internal",
            ),
            models.CheckConstraint(
                check=models.Q(mapping_confidence__gte=0) & models.Q(mapping_confidence__lte=1),
                name="risk_extde_confidence_range",
            ),
        ]
        indexes = [
            models.Index(fields=["system", "exchange_type", "status"], name="risk_extde_exchange_idx"),
            models.Index(fields=["external_identifier"], name="risk_extde_external_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.exchange_type}:{self.internal_field} -> {self.external_identifier}"


class ExternalValueSetMapping(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    system = models.ForeignKey(
        ExternalSystem,
        on_delete=models.PROTECT,
        related_name="value_set_mappings",
    )
    mapping_version = models.ForeignKey(
        InteroperabilityMappingVersion,
        on_delete=models.PROTECT,
        related_name="value_set_mappings",
    )
    value_set_key = models.CharField(max_length=120)
    external_value = models.CharField(max_length=160)
    external_label = models.CharField(max_length=200, blank=True)
    internal_value = models.CharField(max_length=160)
    internal_label = models.CharField(max_length=200, blank=True)
    mapping_confidence = models.FloatField(default=1.0)
    status = models.CharField(
        max_length=20,
        choices=InteroperabilityMappingStatus.choices,
        default=InteroperabilityMappingStatus.NEEDS_REVIEW,
    )
    effective_date = models.DateField(default=timezone.localdate)
    retired_date = models.DateField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="external_value_set_mappings_reviewed",
    )
    lineage_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["system__system_key", "value_set_key", "internal_value"]
        constraints = [
            models.UniqueConstraint(
                fields=["system", "mapping_version", "value_set_key", "internal_value"],
                name="risk_extval_unique_internal",
            ),
            models.CheckConstraint(
                check=models.Q(mapping_confidence__gte=0) & models.Q(mapping_confidence__lte=1),
                name="risk_extval_confidence_range",
            ),
        ]
        indexes = [
            models.Index(fields=["system", "value_set_key", "status"], name="risk_extval_valueset_idx"),
            models.Index(fields=["external_value"], name="risk_extval_external_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.value_set_key}:{self.internal_value} -> {self.external_value}"


class InteroperabilityRun(models.Model):
    DIRECTION_IMPORT = "IMPORT"
    DIRECTION_EXPORT = "EXPORT"
    DIRECTION_CHOICES = [
        (DIRECTION_IMPORT, "Import"),
        (DIRECTION_EXPORT, "Export"),
    ]

    EXCHANGE_SURVEILLANCE_CASE_COUNT_IMPORT = "surveillance_case_count_import"
    EXCHANGE_OUTBREAK_LABEL_IMPORT = "outbreak_label_import"
    EXCHANGE_FACILITY_IMPORT = "facility_import"
    EXCHANGE_WARD_ORG_UNIT_MAPPING_IMPORT = "ward_org_unit_mapping_import"
    EXCHANGE_POPULATION_EXPOSURE_IMPORT = "population_exposure_import"
    EXCHANGE_AGGREGATE_REPORT_EXPORT = "aggregate_report_export"
    EXCHANGE_ALERT_ACTION_SUMMARY_EXPORT = "alert_action_summary_export"
    EXCHANGE_CHOICES = [
        (EXCHANGE_SURVEILLANCE_CASE_COUNT_IMPORT, "Surveillance case count import"),
        (EXCHANGE_OUTBREAK_LABEL_IMPORT, "Outbreak label import"),
        (EXCHANGE_FACILITY_IMPORT, "Facility import"),
        (EXCHANGE_WARD_ORG_UNIT_MAPPING_IMPORT, "Ward/org-unit mapping import"),
        (EXCHANGE_POPULATION_EXPOSURE_IMPORT, "Population/exposure import"),
        (EXCHANGE_AGGREGATE_REPORT_EXPORT, "Aggregate report export"),
        (EXCHANGE_ALERT_ACTION_SUMMARY_EXPORT, "Alert/action summary export"),
    ]

    STATUS_DRAFT = "DRAFT"
    STATUS_READY_FOR_CONFIRMATION = "READY_FOR_CONFIRMATION"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_FAILED = "FAILED"
    STATUS_RETRY_CREATED = "RETRY_CREATED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_READY_FOR_CONFIRMATION, "Ready for confirmation"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_FAILED, "Failed"),
        (STATUS_RETRY_CREATED, "Retry created"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES)
    exchange_type = models.CharField(max_length=80, choices=EXCHANGE_CHOICES)
    system = models.ForeignKey(ExternalSystem, on_delete=models.PROTECT, related_name="interoperability_runs")
    mapping_version = models.ForeignKey(
        InteroperabilityMappingVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="interoperability_runs",
    )
    retry_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retry_runs",
    )
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    dry_run = models.BooleanField(default=True)
    source_file_name = models.CharField(max_length=200, blank=True)
    endpoint_url = models.CharField(max_length=500, blank=True)
    records_seen = models.PositiveIntegerField(default=0)
    records_accepted = models.PositiveIntegerField(default=0)
    records_rejected = models.PositiveIntegerField(default=0)
    mapping_coverage = models.FloatField(default=0.0)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interoperability_runs",
    )
    error_summary = models.TextField(blank=True)
    dry_run_preview = models.JSONField(default=dict, blank=True)
    export_payload = models.JSONField(default=dict, blank=True)
    connector_config = models.JSONField(default=dict, blank=True)
    lineage_metadata = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-started_at", "-created_at"]
        indexes = [
            models.Index(fields=["direction", "exchange_type", "started_at"], name="risk_ioprun_exchange_idx"),
            models.Index(fields=["system", "status", "started_at"], name="risk_ioprun_system_idx"),
            models.Index(fields=["retry_of", "created_at"], name="risk_ioprun_retry_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.exchange_type} {self.direction} [{self.status}]"


class InteroperabilityRunItem(models.Model):
    STATUS_ACCEPTED = "ACCEPTED"
    STATUS_REJECTED = "REJECTED"
    STATUS_UNMAPPED = "UNMAPPED"
    STATUS_PREVIEW = "PREVIEW"
    STATUS_CHOICES = [
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_UNMAPPED, "Unmapped"),
        (STATUS_PREVIEW, "Preview"),
    ]

    ACTION_IMPORT_MAPPING = "IMPORT_MAPPING"
    ACTION_EXPORT_RECORD = "EXPORT_RECORD"
    ACTION_NOOP = "NOOP"
    ACTION_CHOICES = [
        (ACTION_IMPORT_MAPPING, "Import mapping"),
        (ACTION_EXPORT_RECORD, "Export record"),
        (ACTION_NOOP, "No-op"),
    ]

    run = models.ForeignKey(InteroperabilityRun, on_delete=models.CASCADE, related_name="items")
    row_number = models.PositiveIntegerField(default=0)
    external_identifier = models.CharField(max_length=160, blank=True)
    internal_object_type = models.CharField(max_length=40, blank=True)
    internal_object_public_id = models.CharField(max_length=80, blank=True)
    internal_object_code = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    action = models.CharField(max_length=40, choices=ACTION_CHOICES, default=ACTION_NOOP)
    safe_context = models.JSONField(default=dict, blank=True)
    source_record_ref = models.CharField(max_length=180, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["run", "row_number", "id"]
        indexes = [
            models.Index(fields=["run", "status"], name="risk_iopitem_run_status_idx"),
            models.Index(fields=["external_identifier"], name="risk_iopitem_external_idx"),
            models.Index(fields=["internal_object_type", "internal_object_public_id"], name="risk_iopitem_internal_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.run.public_id} row {self.row_number} [{self.status}]"


class InteroperabilityRunError(models.Model):
    SEVERITY_INFO = "INFO"
    SEVERITY_WARNING = "WARNING"
    SEVERITY_ERROR = "ERROR"
    SEVERITY_CHOICES = [
        (SEVERITY_INFO, "Info"),
        (SEVERITY_WARNING, "Warning"),
        (SEVERITY_ERROR, "Error"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    run = models.ForeignKey(InteroperabilityRun, on_delete=models.CASCADE, related_name="errors")
    item = models.ForeignKey(
        InteroperabilityRunItem,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="errors",
    )
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_ERROR)
    error_code = models.CharField(max_length=80)
    field_path = models.CharField(max_length=160, blank=True)
    safe_message = models.TextField()
    remediation_hint = models.TextField(blank=True)
    raw_value_digest = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["run", "item__row_number", "id"]
        indexes = [
            models.Index(fields=["run", "severity"], name="risk_ioperr_run_severity_idx"),
            models.Index(fields=["error_code", "created_at"], name="risk_ioperr_code_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.error_code} [{self.severity}]"


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
    template = models.ForeignKey(
        "risk.MessageTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="facility_update_requests",
    )
    template_key = models.CharField(max_length=120, blank=True)
    template_version = models.PositiveIntegerField(null=True, blank=True)
    message_body = models.TextField()
    governance_metadata = models.JSONField(default=dict, blank=True)
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
            models.Index(fields=["template_key", "template_version"], name="risk_facupd_tpl_idx"),
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
    language = models.CharField(max_length=20, choices=SUPPORTED_CHV_LANGUAGE_CHOICES, default=DEFAULT_CHV_LANGUAGE)
    preferred_language = models.CharField(
        max_length=20,
        choices=SUPPORTED_CHV_LANGUAGE_CHOICES,
        default=DEFAULT_CHV_LANGUAGE,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(language__in=SUPPORTED_CHV_LANGUAGES),
                name="risk_chv_language_supported",
            ),
            models.CheckConstraint(
                check=models.Q(preferred_language__in=SUPPORTED_CHV_LANGUAGES),
                name="risk_chv_preflang_supported",
            ),
        ]

    def save(self, *args, **kwargs):
        legacy_language = normalize_language_code(self.language)
        preferred_language = normalize_language_code(self.preferred_language)
        if (not preferred_language or preferred_language == DEFAULT_CHV_LANGUAGE) and legacy_language not in {
            "",
            DEFAULT_CHV_LANGUAGE,
        }:
            preferred_language = legacy_language
        self.preferred_language = supported_language_or_default(preferred_language)
        self.language = self.preferred_language
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.ward.name})"


class CHVDeviceRegistration(models.Model):
    PLATFORM_ANDROID = "ANDROID"
    PLATFORM_IOS = "IOS"
    PLATFORM_WEB = "WEB"
    PLATFORM_UNKNOWN = "UNKNOWN"
    PLATFORM_CHOICES = [
        (PLATFORM_ANDROID, "Android"),
        (PLATFORM_IOS, "iOS"),
        (PLATFORM_WEB, "Web/PWA"),
        (PLATFORM_UNKNOWN, "Unknown"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    device_id = models.CharField(max_length=120)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="chv_device_registrations",
    )
    chv = models.ForeignKey(
        "risk.CHV",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="device_registrations",
    )
    ward = models.ForeignKey("risk.Ward", on_delete=models.PROTECT, related_name="chv_device_registrations")
    contract_version = models.CharField(max_length=64, default="chv-offline-v1")
    app_version = models.CharField(max_length=64, blank=True)
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES, default=PLATFORM_UNKNOWN)
    preferred_language = models.CharField(
        max_length=20,
        choices=SUPPORTED_CHV_LANGUAGE_CHOICES,
        default=DEFAULT_CHV_LANGUAGE,
    )
    last_bundle_version = models.CharField(max_length=96, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_seen_at", "-registered_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "device_id"], name="risk_chvdev_user_device_uniq"),
            models.CheckConstraint(
                check=models.Q(preferred_language__in=SUPPORTED_CHV_LANGUAGES),
                name="risk_chvdev_preflang_supported",
            ),
        ]
        indexes = [
            models.Index(fields=["ward", "is_active"], name="risk_chvdev_ward_active_idx"),
            models.Index(fields=["chv", "is_active"], name="risk_chvdev_chv_active_idx"),
            models.Index(fields=["contract_version", "last_seen_at"], name="risk_chvdev_contract_idx"),
        ]

    def save(self, *args, **kwargs):
        self.preferred_language = supported_language_or_default(self.preferred_language)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.device_id} [{self.contract_version}]"


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
    template = models.ForeignKey(
        "risk.MessageTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="chv_messages",
    )
    template_key = models.CharField(max_length=120, blank=True)
    template_version = models.PositiveIntegerField(null=True, blank=True)
    requested_language = models.CharField(max_length=20, default=DEFAULT_CHV_LANGUAGE)
    resolved_language = models.CharField(
        max_length=20,
        choices=SUPPORTED_CHV_LANGUAGE_CHOICES,
        default=DEFAULT_CHV_LANGUAGE,
    )
    fallback_used = models.BooleanField(default=False)
    message_body = models.TextField()
    governance_metadata = models.JSONField(default=dict, blank=True)
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
            models.Index(fields=["template_key", "template_version"], name="risk_chvmsg_tpl_idx"),
            models.Index(fields=["resolved_language", "created_at"], name="risk_chvmsg_reslang_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(resolved_language__in=SUPPORTED_CHV_LANGUAGES),
                name="risk_chvmsg_reslang_supported",
            ),
        ]

    def save(self, *args, **kwargs):
        self.requested_language = normalize_language_code(self.requested_language) or DEFAULT_CHV_LANGUAGE
        self.resolved_language = supported_language_or_default(self.resolved_language or self.requested_language)
        self.fallback_used = bool(self.fallback_used or self.requested_language != self.resolved_language)
        super().save(*args, **kwargs)

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
    decision_policy = models.JSONField(default=dict, blank=True)
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
    lineage_metadata = models.JSONField(default=dict, blank=True)
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


class ClimateRecordType(models.TextChoices):
    OBSERVED = "observed", "Observed"
    FORECAST = "forecast", "Forecast"
    DERIVED_ROLLING_WINDOW = "derived_rolling_window", "Derived rolling window"
    DERIVED_ANOMALY = "derived_anomaly", "Derived anomaly"
    FALLBACK_STATIC = "fallback_static", "Fallback static"


class ClimateRecordQualityFlag(models.TextChoices):
    ACCEPTED = "accepted", "Accepted"
    DEGRADED_FALLBACK = "degraded_fallback", "Degraded fallback"
    MISSING_FORECAST_CONTRACT = "missing_forecast_contract", "Missing forecast contract"
    MISSING_OBSERVED_TIMESTAMP = "missing_observed_timestamp", "Missing observed timestamp"
    DERIVED = "derived", "Derived"
    UNKNOWN = "unknown", "Unknown"


class ClimateRecord(models.Model):
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="climate_records")
    ingestion_run = models.ForeignKey(
        IngestionRun,
        on_delete=models.PROTECT,
        related_name="climate_records",
    )
    record_type = models.CharField(
        max_length=40,
        choices=ClimateRecordType.choices,
        default=ClimateRecordType.OBSERVED,
    )
    source_provider = models.CharField(max_length=120)
    source_kind = models.CharField(
        max_length=20,
        choices=IngestionRun.SOURCE_KIND_CHOICES,
        default=IngestionRun.SOURCE_KIND_UNKNOWN,
    )
    source_mode = models.CharField(max_length=20, blank=True)
    issue_time = models.DateTimeField(null=True, blank=True)
    valid_date = models.DateField(null=True, blank=True)
    lead_day = models.PositiveSmallIntegerField(null=True, blank=True)
    observed_timestamp = models.DateTimeField(null=True, blank=True)
    forecast_horizon_days = models.PositiveSmallIntegerField(default=0)
    rainfall_mm = models.FloatField()
    quality_flag = models.CharField(
        max_length=40,
        choices=ClimateRecordQualityFlag.choices,
        default=ClimateRecordQualityFlag.UNKNOWN,
    )
    fallback_flag = models.BooleanField(default=False)
    source_run = models.CharField(max_length=160)
    source_ref = models.CharField(max_length=255)
    identity_key = models.CharField(max_length=255, unique=True, null=True, blank=True)
    lineage_metadata = models.JSONField(default=dict, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-valid_date", "-issue_time", "ward__name", "record_type"]
        indexes = [
            models.Index(fields=["ward", "record_type", "valid_date"], name="risk_climrec_ward_type_idx"),
            models.Index(fields=["source_provider", "issue_time"], name="risk_climrec_src_issue_idx"),
            models.Index(fields=["lead_day", "valid_date"], name="risk_climrec_lead_valid_idx"),
            models.Index(fields=["fallback_flag", "record_type"], name="risk_climrec_fallback_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["ingestion_run", "source_ref"],
                name="risk_climrec_run_ref_uniq",
            ),
            models.CheckConstraint(
                check=(
                    ~models.Q(record_type=ClimateRecordType.FORECAST)
                    | (
                        models.Q(issue_time__isnull=False)
                        & models.Q(valid_date__isnull=False)
                        & models.Q(lead_day__isnull=False)
                    )
                ),
                name="risk_climrec_forecast_contract",
            ),
            models.CheckConstraint(
                check=(
                    ~models.Q(record_type=ClimateRecordType.OBSERVED)
                    | models.Q(observed_timestamp__isnull=False)
                ),
                name="risk_climrec_observed_contract",
            ),
            models.CheckConstraint(
                check=(
                    ~models.Q(record_type=ClimateRecordType.FALLBACK_STATIC)
                    | models.Q(fallback_flag=True)
                ),
                name="risk_climrec_fallback_flag",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(lead_day__isnull=True)
                    | models.Q(forecast_horizon_days__gte=models.F("lead_day"))
                ),
                name="risk_climrec_horizon_lead",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ward.name} {self.record_type} {self.rainfall_mm}mm [{self.source_provider}]"


class SurveillanceSource(models.Model):
    SOURCE_TYPE_WEEKLY_AGGREGATE = "weekly_aggregate"
    SOURCE_TYPE_DAILY_AGGREGATE = "daily_aggregate"
    SOURCE_TYPE_LINE_LIST_SUMMARY = "line_list_summary"
    SOURCE_TYPE_TRUSTED_PUSH = "trusted_push"
    SOURCE_TYPE_CSV_BACKFILL = "csv_backfill"
    SOURCE_TYPE_FIELD_SIGNAL = "field_signal"
    SOURCE_TYPE_FACILITY_PROXY = "facility_proxy"
    SOURCE_TYPE_CHOICES = [
        (SOURCE_TYPE_WEEKLY_AGGREGATE, "Weekly aggregate"),
        (SOURCE_TYPE_DAILY_AGGREGATE, "Daily aggregate"),
        (SOURCE_TYPE_LINE_LIST_SUMMARY, "Line-list summary"),
        (SOURCE_TYPE_TRUSTED_PUSH, "Trusted push"),
        (SOURCE_TYPE_CSV_BACKFILL, "CSV backfill"),
        (SOURCE_TYPE_FIELD_SIGNAL, "Field signal"),
        (SOURCE_TYPE_FACILITY_PROXY, "Facility proxy"),
    ]

    source_name = models.CharField(max_length=120)
    source_type = models.CharField(max_length=40, choices=SOURCE_TYPE_CHOICES)
    source_timestamp = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)
    reporting_period_start = models.DateField(null=True, blank=True)
    reporting_period_end = models.DateField(null=True, blank=True)
    source_ref = models.CharField(max_length=255, blank=True)
    operator_note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at", "source_name"]
        indexes = [
            models.Index(fields=["source_type", "reporting_period_start"], name="risk_survsrc_type_period_idx"),
            models.Index(fields=["source_name", "submitted_at"], name="risk_survsrc_name_sub_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(reporting_period_start__isnull=True)
                    | models.Q(reporting_period_end__isnull=True)
                    | models.Q(reporting_period_start__lte=models.F("reporting_period_end"))
                ),
                name="risk_survsrc_period_order",
            ),
        ]

    def __str__(self) -> str:
        period = ""
        if self.reporting_period_start and self.reporting_period_end:
            period = f" {self.reporting_period_start}:{self.reporting_period_end}"
        return f"{self.source_name}{period} [{self.source_type}]"


class SurveillanceIngestionRun(models.Model):
    STATUS_RUNNING = "RUNNING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_FAILED, "Failed"),
    ]

    CORRECTION_ORIGINAL = "original"
    CORRECTION_AMENDMENT = "amendment"
    CORRECTION_BACKFILL = "backfill"
    CORRECTION_MODE_CHOICES = [
        (CORRECTION_ORIGINAL, "Original"),
        (CORRECTION_AMENDMENT, "Amendment"),
        (CORRECTION_BACKFILL, "Backfill"),
    ]

    EXECUTION_MANUAL = "manual"
    EXECUTION_SCHEDULED = "scheduled"
    EXECUTION_TRUSTED_PUSH = "trusted_push"
    EXECUTION_REPLAY = "replay"
    EXECUTION_MODE_CHOICES = [
        (EXECUTION_MANUAL, "Manual"),
        (EXECUTION_SCHEDULED, "Scheduled"),
        (EXECUTION_TRUSTED_PUSH, "Trusted push"),
        (EXECUTION_REPLAY, "Replay"),
    ]

    source = models.ForeignKey(
        SurveillanceSource,
        on_delete=models.PROTECT,
        related_name="ingestion_runs",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    source_name = models.CharField(max_length=120)
    source_type = models.CharField(max_length=40, choices=SurveillanceSource.SOURCE_TYPE_CHOICES)
    source_timestamp = models.DateTimeField(null=True, blank=True)
    reporting_period_start = models.DateField(null=True, blank=True)
    reporting_period_end = models.DateField(null=True, blank=True)
    source_ref = models.CharField(max_length=255, blank=True)
    adapter_key = models.CharField(max_length=80, default="surveillance_csv")
    input_ref = models.CharField(max_length=255, blank=True)
    execution_mode = models.CharField(max_length=20, choices=EXECUTION_MODE_CHOICES, default=EXECUTION_MANUAL)
    correction_mode = models.CharField(max_length=40, choices=CORRECTION_MODE_CHOICES, default=CORRECTION_ORIGINAL)
    correction_reason = models.TextField(blank=True)
    fallback_used = models.BooleanField(default=False)
    records_seen = models.PositiveIntegerField(default=0)
    records_loaded = models.PositiveIntegerField(default=0)
    records_rejected = models.PositiveIntegerField(default=0)
    operator_note = models.TextField(blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)
    results = models.JSONField(default=dict, blank=True)
    rejected_rows = models.JSONField(default=list, blank=True)
    error_summary = models.TextField(blank=True)
    replay_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replay_runs",
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["source_type", "started_at"], name="risk_survrun_type_started_idx"),
            models.Index(fields=["status", "started_at"], name="risk_survrun_status_idx"),
            models.Index(fields=["correction_mode", "started_at"], name="risk_survrun_corr_started_idx"),
            models.Index(fields=["reporting_period_start"], name="risk_survrun_period_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(reporting_period_start__isnull=True)
                    | models.Q(reporting_period_end__isnull=True)
                    | models.Q(reporting_period_start__lte=models.F("reporting_period_end"))
                ),
                name="risk_survrun_period_order",
            ),
            models.CheckConstraint(
                check=~models.Q(correction_mode="amendment") | ~models.Q(correction_reason=""),
                name="risk_survrun_amend_reason",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_name} [{self.status}] {self.started_at}"


class SurveillanceTruthLevel(models.TextChoices):
    CONFIRMED_SURVEILLANCE = "confirmed_surveillance", "Confirmed surveillance"
    SUSPECTED_SURVEILLANCE = "suspected_surveillance", "Suspected surveillance"
    PROXY_DIARRHEAL_SIGNAL = "proxy_diarrheal_signal", "Proxy diarrheal signal"
    FIELD_SIGNAL_ONLY = "field_signal_only", "Field signal only"
    SEEDED_DEMO = "seeded_demo", "Seeded demo"


class SurveillanceSourceKind(models.TextChoices):
    LIVE = "live", "Live"
    BACKFILL = "backfill", "Backfill"
    SEEDED = "seeded", "Seeded"


class SurveillanceFreshnessState(models.TextChoices):
    FRESH = "fresh", "Fresh"
    DELAYED = "delayed", "Delayed"
    STALE = "stale", "Stale"
    CORRECTED_AFTER_INITIAL_SUBMISSION = (
        "corrected_after_initial_submission",
        "Corrected after initial submission",
    )
    REPLAY_DIAGNOSTIC = "replay_diagnostic", "Replay diagnostic"
    UNKNOWN = "unknown", "Unknown"


class SurveillanceDiseaseCategory(models.TextChoices):
    CHOLERA = "cholera", "Cholera"
    DIARRHEAL = "diarrheal", "Diarrheal"


class SurveillanceCaseClass(models.TextChoices):
    SUSPECTED = "suspected", "Suspected"
    CONFIRMED = "confirmed", "Confirmed"
    PROXY = "proxy", "Proxy"


class SurveillanceOutbreakLabel(models.TextChoices):
    NONE = "none", "None"
    WATCH = "watch", "Watch"
    ACTIVE = "active", "Active"


class SurveillanceRecord(models.Model):
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="surveillance_records")
    ingestion_run = models.ForeignKey(
        SurveillanceIngestionRun,
        on_delete=models.PROTECT,
        related_name="surveillance_records",
    )
    source = models.ForeignKey(
        SurveillanceSource,
        on_delete=models.PROTECT,
        related_name="surveillance_records",
    )
    facility = models.ForeignKey(
        HealthFacility,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="surveillance_records",
    )
    disease_category = models.CharField(max_length=20, choices=SurveillanceDiseaseCategory.choices)
    case_class = models.CharField(max_length=20, choices=SurveillanceCaseClass.choices)
    outbreak_label = models.CharField(
        max_length=20,
        choices=SurveillanceOutbreakLabel.choices,
        default=SurveillanceOutbreakLabel.NONE,
    )
    count_value = models.PositiveIntegerField()
    reporting_period_start = models.DateField()
    reporting_period_end = models.DateField()
    reporting_granularity = models.CharField(
        max_length=10,
        choices=[("day", "Day"), ("week", "Week")],
        default="week",
    )
    truth_level = models.CharField(
        max_length=40,
        choices=SurveillanceTruthLevel.choices,
        default=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
    )
    source_name = models.CharField(max_length=120)
    source_kind = models.CharField(
        max_length=20,
        choices=SurveillanceSourceKind.choices,
        default=SurveillanceSourceKind.LIVE,
    )
    freshness_state = models.CharField(
        max_length=50,
        choices=SurveillanceFreshnessState.choices,
        default=SurveillanceFreshnessState.UNKNOWN,
    )
    revision_number = models.PositiveIntegerField(default=1)
    supersedes_record_ref = models.CharField(max_length=160, blank=True)
    source_ref = models.CharField(max_length=255, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reporting_period_end", "ward__name", "case_class"]
        indexes = [
            models.Index(fields=["ward", "reporting_period_start", "reporting_period_end"], name="risk_survrec_ward_period_idx"),
            models.Index(fields=["facility", "reporting_period_start"], name="risk_survrec_fac_period_idx"),
            models.Index(fields=["truth_level", "reporting_period_start"], name="risk_survrec_truth_period_idx"),
            models.Index(fields=["source", "created_at"], name="risk_survrec_src_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(reporting_period_start__lte=models.F("reporting_period_end")),
                name="risk_survrec_period_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ward.name} {self.case_class}={self.count_value} [{self.truth_level}]"


class SurveillanceLabelWindow(models.Model):
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="surveillance_label_windows")
    feature_dataset = models.ForeignKey(
        "risk.FeatureDataset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="surveillance_label_windows",
    )
    schema_version = models.CharField(max_length=50, default="surveillance-label-v1")
    dataset_ref = models.CharField(max_length=160, blank=True)
    label_window_start = models.DateField()
    label_window_end = models.DateField()
    suspected_case_count = models.PositiveIntegerField(default=0)
    confirmed_case_count = models.PositiveIntegerField(default=0)
    proxy_case_count = models.PositiveIntegerField(default=0)
    outbreak_label = models.CharField(
        max_length=20,
        choices=SurveillanceOutbreakLabel.choices,
        default=SurveillanceOutbreakLabel.NONE,
    )
    label_truth_level = models.CharField(
        max_length=40,
        choices=SurveillanceTruthLevel.choices,
        default=SurveillanceTruthLevel.SUSPECTED_SURVEILLANCE,
    )
    generation_mode = models.CharField(max_length=40, default="phase_2_shape_defined")
    source_coverage_summary = models.JSONField(default=dict, blank=True)
    generated_from_record_refs = models.JSONField(default=list, blank=True)
    source_record_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-label_window_end", "ward__name"]
        indexes = [
            models.Index(fields=["ward", "label_window_start", "label_window_end"], name="risk_survlbl_ward_window_idx"),
            models.Index(fields=["dataset_ref", "label_window_start"], name="risk_survlbl_dataset_idx"),
            models.Index(fields=["outbreak_label", "label_window_end"], name="risk_survlbl_outbreak_idx"),
            models.Index(fields=["label_truth_level", "label_window_end"], name="risk_survlbl_truth_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(label_window_start__lte=models.F("label_window_end")),
                name="risk_survlbl_window_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ward.name} {self.label_window_start}:{self.label_window_end} [{self.outbreak_label}]"


class PredictionFeedbackTrainingUsageState(models.TextChoices):
    NOT_TRAINING_ELIGIBLE = "not_training_eligible", "Not training eligible"
    NEEDS_REVIEW = "needs_review", "Needs review"
    ADJUDICATED_LABEL_CANDIDATE = "adjudicated_label_candidate", "Adjudicated label candidate"
    TRAINING_ELIGIBLE = "training_eligible", "Training eligible"
    REJECTED = "rejected", "Rejected"
    SUPERSEDED_BY_SURVEILLANCE_TRUTH = (
        "superseded_by_surveillance_truth",
        "Superseded by surveillance truth",
    )


class PredictionFeedbackSourceConfidence(models.TextChoices):
    SYSTEM_MATCHED_LABEL = "system_matched_label", "System matched label"
    COUNTY_SURVEILLANCE_OFFICER = "county_surveillance_officer", "County surveillance officer"
    FACILITY_CONTACT = "facility_contact", "Facility contact"
    ASSIGNED_CHV = "assigned_chv", "Assigned CHV"
    COUNTY_OPERATOR = "county_operator", "County operator"
    COMMUNITY_REPORT = "community_report", "Community report"
    ANONYMOUS_PUBLIC = "anonymous_public", "Anonymous public"
    AUTOMATED_PROXY = "automated_proxy", "Automated proxy"


class PredictionFeedbackPrivacyClassification(models.TextChoices):
    NON_SENSITIVE = "non_sensitive", "Non-sensitive"
    DEIDENTIFIED = "deidentified", "De-identified"
    SENSITIVE_OPERATIONAL = "sensitive_operational", "Sensitive operational"
    CONTAINS_PII = "contains_pii", "Contains PII"


class PredictionFeedback(models.Model):
    FEEDBACK_PREDICTION_REVIEWED_CORRECT = "prediction_reviewed_correct"
    FEEDBACK_PREDICTION_REVIEWED_WRONG = "prediction_reviewed_wrong"
    FEEDBACK_SUSPECTED_MISSED_OUTBREAK = "suspected_missed_outbreak"
    FEEDBACK_SUSPECTED_FALSE_ALERT = "suspected_false_alert"
    FEEDBACK_LOCAL_SURVEILLANCE_CORRECTION = "local_surveillance_correction"
    FEEDBACK_FACILITY_BURDEN_CORRECTION = "facility_burden_correction"
    FEEDBACK_CHV_FIELD_OBSERVATION = "chv_field_observation"
    FEEDBACK_HOUSEHOLD_FOLLOW_UP_OUTCOME = "household_follow_up_outcome"
    FEEDBACK_ALERT_DELIVERY_OR_RESPONSE_FAILURE = "alert_delivery_or_response_failure"
    FEEDBACK_DATA_QUALITY_COMPLAINT = "data_quality_complaint"
    FEEDBACK_USABILITY_FEEDBACK = "usability_feedback"
    FEEDBACK_TYPE_CHOICES = [
        (FEEDBACK_PREDICTION_REVIEWED_CORRECT, "Prediction reviewed as correct"),
        (FEEDBACK_PREDICTION_REVIEWED_WRONG, "Prediction reviewed as wrong"),
        (FEEDBACK_SUSPECTED_MISSED_OUTBREAK, "Suspected missed outbreak"),
        (FEEDBACK_SUSPECTED_FALSE_ALERT, "Suspected false alert"),
        (FEEDBACK_LOCAL_SURVEILLANCE_CORRECTION, "Local surveillance correction"),
        (FEEDBACK_FACILITY_BURDEN_CORRECTION, "Facility burden correction"),
        (FEEDBACK_CHV_FIELD_OBSERVATION, "CHV field observation"),
        (FEEDBACK_HOUSEHOLD_FOLLOW_UP_OUTCOME, "Household follow-up outcome"),
        (FEEDBACK_ALERT_DELIVERY_OR_RESPONSE_FAILURE, "Alert delivery or response failure"),
        (FEEDBACK_DATA_QUALITY_COMPLAINT, "Data-quality complaint"),
        (FEEDBACK_USABILITY_FEEDBACK, "Usability feedback"),
    ]

    SOURCE_TYPE_SYSTEM = "system"
    SOURCE_TYPE_REVIEWER = "reviewer"
    SOURCE_TYPE_FIELD_OPERATOR = "field_operator"
    SOURCE_TYPE_COMMUNITY = "community"
    SOURCE_TYPE_AUTOMATED_PROXY = "automated_proxy"
    SOURCE_TYPE_CHOICES = [
        (SOURCE_TYPE_SYSTEM, "System"),
        (SOURCE_TYPE_REVIEWER, "Reviewer"),
        (SOURCE_TYPE_FIELD_OPERATOR, "Field operator"),
        (SOURCE_TYPE_COMMUNITY, "Community"),
        (SOURCE_TYPE_AUTOMATED_PROXY, "Automated proxy"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    risk_score = models.ForeignKey(
        RiskScore,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prediction_feedback",
    )
    model_run = models.ForeignKey(
        "risk.ModelRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prediction_feedback",
    )
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="prediction_feedback")
    label_window = models.ForeignKey(
        SurveillanceLabelWindow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prediction_feedback",
    )
    prediction_date = models.DateField(null=True, blank=True)
    feedback_type = models.CharField(max_length=80, choices=FEEDBACK_TYPE_CHOICES)
    feedback_source_type = models.CharField(max_length=40, choices=SOURCE_TYPE_CHOICES)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prediction_feedback_submissions",
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    source_confidence = models.CharField(
        max_length=80,
        choices=PredictionFeedbackSourceConfidence.choices,
        default=PredictionFeedbackSourceConfidence.COMMUNITY_REPORT,
    )
    note = models.TextField(blank=True)
    attached_evidence_refs = models.JSONField(default=list, blank=True)
    privacy_classification = models.CharField(
        max_length=40,
        choices=PredictionFeedbackPrivacyClassification.choices,
        default=PredictionFeedbackPrivacyClassification.NON_SENSITIVE,
    )
    training_usage_state = models.CharField(
        max_length=80,
        choices=PredictionFeedbackTrainingUsageState.choices,
        default=PredictionFeedbackTrainingUsageState.NEEDS_REVIEW,
    )
    lineage_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at", "-id"]
        indexes = [
            models.Index(fields=["ward", "submitted_at"], name="risk_predfb_ward_sub_idx"),
            models.Index(fields=["risk_score", "submitted_at"], name="risk_predfb_score_sub_idx"),
            models.Index(fields=["model_run", "submitted_at"], name="risk_predfb_run_sub_idx"),
            models.Index(fields=["training_usage_state", "submitted_at"], name="risk_predfb_train_sub_idx"),
            models.Index(fields=["source_confidence", "submitted_at"], name="risk_predfb_conf_sub_idx"),
        ]

    def clean(self):
        if self.risk_score_id:
            if self.risk_score.ward_id != self.ward_id:
                raise ValidationError("Prediction feedback risk_score must belong to the feedback ward.")
            if self.model_run_id and self.risk_score.model_run_id and self.risk_score.model_run_id != self.model_run_id:
                raise ValidationError("Prediction feedback model_run must match the risk_score model_run.")
        if self.label_window_id and self.label_window.ward_id != self.ward_id:
            raise ValidationError("Prediction feedback label_window must belong to the feedback ward.")
        if (
            self.privacy_classification == PredictionFeedbackPrivacyClassification.CONTAINS_PII
            and self.training_usage_state
            not in {
                PredictionFeedbackTrainingUsageState.NOT_TRAINING_ELIGIBLE,
                PredictionFeedbackTrainingUsageState.NEEDS_REVIEW,
                PredictionFeedbackTrainingUsageState.REJECTED,
            }
        ):
            raise ValidationError("Feedback containing PII cannot be training eligible or a label candidate.")

    def __str__(self) -> str:
        return f"{self.ward.name} {self.feedback_type} [{self.training_usage_state}]"


class PredictionFeedbackEvent(models.Model):
    EVENT_CREATED = "CREATED"
    EVENT_STATE_CHANGED = "STATE_CHANGED"
    EVENT_ADJUDICATED = "ADJUDICATED"
    EVENT_LABEL_CANDIDATE_CREATED = "LABEL_CANDIDATE_CREATED"
    EVENT_SUPERSEDED = "SUPERSEDED"
    EVENT_COMMENT = "COMMENT"
    EVENT_CHOICES = [
        (EVENT_CREATED, "Created"),
        (EVENT_STATE_CHANGED, "State changed"),
        (EVENT_ADJUDICATED, "Adjudicated"),
        (EVENT_LABEL_CANDIDATE_CREATED, "Label candidate created"),
        (EVENT_SUPERSEDED, "Superseded"),
        (EVENT_COMMENT, "Comment"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    feedback = models.ForeignKey(PredictionFeedback, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prediction_feedback_events",
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    old_training_usage_state = models.CharField(max_length=80, blank=True)
    new_training_usage_state = models.CharField(max_length=80, blank=True)
    detail = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["feedback", "created_at"], name="risk_predfbevt_fb_time_idx"),
            models.Index(fields=["event_type", "created_at"], name="risk_predfbevt_type_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.feedback.public_id} {self.event_type}"


class FeedbackAdjudicationState(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED_AS_LABEL_CANDIDATE = "accepted_as_label_candidate", "Accepted as label candidate"
    ACCEPTED_AS_RESPONSE_QUALITY_ISSUE = (
        "accepted_as_response_quality_issue",
        "Accepted as response-quality issue",
    )
    ACCEPTED_AS_DATA_QUALITY_ISSUE = "accepted_as_data_quality_issue", "Accepted as data-quality issue"
    REJECTED = "rejected", "Rejected"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence", "Needs more evidence"
    SUPERSEDED = "superseded", "Superseded"


class FeedbackAdjudication(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    feedback = models.ForeignKey(PredictionFeedback, on_delete=models.PROTECT, related_name="adjudications")
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_adjudications",
    )
    adjudication_state = models.CharField(
        max_length=80,
        choices=FeedbackAdjudicationState.choices,
        default=FeedbackAdjudicationState.PENDING,
    )
    accepted_label_impact = models.JSONField(default=dict, blank=True)
    response_quality_impact = models.JSONField(default=dict, blank=True)
    data_quality_impact = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    superseded_by_surveillance_label = models.ForeignKey(
        SurveillanceLabelWindow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseding_feedback_adjudications",
    )
    evidence_refs = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-reviewed_at", "-created_at", "-id"]
        indexes = [
            models.Index(fields=["feedback", "adjudication_state"], name="risk_fbadj_fb_state_idx"),
            models.Index(fields=["adjudication_state", "reviewed_at"], name="risk_fbadj_state_rev_idx"),
            models.Index(fields=["reviewer", "reviewed_at"], name="risk_fbadj_reviewer_idx"),
        ]

    def clean(self):
        terminal_states = {
            FeedbackAdjudicationState.ACCEPTED_AS_LABEL_CANDIDATE,
            FeedbackAdjudicationState.ACCEPTED_AS_RESPONSE_QUALITY_ISSUE,
            FeedbackAdjudicationState.ACCEPTED_AS_DATA_QUALITY_ISSUE,
            FeedbackAdjudicationState.REJECTED,
            FeedbackAdjudicationState.SUPERSEDED,
        }
        if self.adjudication_state in terminal_states and self.reviewed_at is None:
            raise ValidationError("Reviewed adjudications require reviewed_at.")
        if self.adjudication_state == FeedbackAdjudicationState.ACCEPTED_AS_LABEL_CANDIDATE:
            if not self.accepted_label_impact:
                raise ValidationError("Label-candidate adjudications require accepted_label_impact.")
            truth_level = self.accepted_label_impact.get("label_truth_level")
            if truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE:
                raise ValidationError("Feedback cannot be accepted as confirmed surveillance truth.")
            outbreak_label = self.accepted_label_impact.get("outbreak_label")
            valid_outbreak_labels = {choice[0] for choice in SurveillanceOutbreakLabel.choices}
            if outbreak_label and outbreak_label not in valid_outbreak_labels:
                raise ValidationError("accepted_label_impact.outbreak_label is not a valid outbreak label.")
        if self.adjudication_state == FeedbackAdjudicationState.SUPERSEDED:
            if self.superseded_by_surveillance_label_id is None:
                raise ValidationError("Superseded adjudications require superseded_by_surveillance_label.")
            if self.feedback_id and self.superseded_by_surveillance_label.ward_id != self.feedback.ward_id:
                raise ValidationError("Superseding surveillance label must belong to the feedback ward.")

    def __str__(self) -> str:
        return f"{self.feedback.public_id} [{self.adjudication_state}]"


class FeedbackLabelCandidate(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    candidate_ref = models.CharField(max_length=160, unique=True, blank=True)
    feedback = models.ForeignKey(PredictionFeedback, on_delete=models.PROTECT, related_name="label_candidates")
    adjudication = models.OneToOneField(
        FeedbackAdjudication,
        on_delete=models.PROTECT,
        related_name="label_candidate",
    )
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="feedback_label_candidates")
    risk_score = models.ForeignKey(
        RiskScore,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_label_candidates",
    )
    model_run = models.ForeignKey(
        "risk.ModelRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_label_candidates",
    )
    label_window_start = models.DateField()
    label_window_end = models.DateField()
    outbreak_label = models.CharField(
        max_length=20,
        choices=SurveillanceOutbreakLabel.choices,
        default=SurveillanceOutbreakLabel.NONE,
    )
    label_truth_level = models.CharField(
        max_length=40,
        choices=SurveillanceTruthLevel.choices,
        default=SurveillanceTruthLevel.FIELD_SIGNAL_ONLY,
    )
    source_confidence = models.CharField(
        max_length=80,
        choices=PredictionFeedbackSourceConfidence.choices,
        default=PredictionFeedbackSourceConfidence.COMMUNITY_REPORT,
    )
    training_usage_state = models.CharField(
        max_length=80,
        choices=PredictionFeedbackTrainingUsageState.choices,
        default=PredictionFeedbackTrainingUsageState.ADJUDICATED_LABEL_CANDIDATE,
    )
    superseded_by_surveillance_label = models.ForeignKey(
        SurveillanceLabelWindow,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseding_feedback_label_candidates",
    )
    lineage_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["ward", "label_window_start", "label_window_end"], name="risk_fblbl_ward_window_idx"),
            models.Index(fields=["training_usage_state", "created_at"], name="risk_fblbl_train_idx"),
            models.Index(fields=["label_truth_level", "created_at"], name="risk_fblbl_truth_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(label_window_start__lte=models.F("label_window_end")),
                name="risk_fblbl_window_order",
            ),
            models.CheckConstraint(
                check=~models.Q(label_truth_level=SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE),
                name="risk_fblbl_not_confirmed_truth",
            ),
        ]

    def clean(self):
        if self.label_truth_level == SurveillanceTruthLevel.CONFIRMED_SURVEILLANCE:
            raise ValidationError("Feedback label candidates cannot be confirmed surveillance truth.")
        if self.feedback_id and self.adjudication_id and self.adjudication.feedback_id != self.feedback_id:
            raise ValidationError("Feedback label candidate adjudication must belong to the same feedback record.")
        if self.feedback_id and self.ward_id and self.feedback.ward_id != self.ward_id:
            raise ValidationError("Feedback label candidate ward must match the feedback ward.")
        if self.risk_score_id and self.risk_score.ward_id != self.ward_id:
            raise ValidationError("Feedback label candidate risk_score must belong to the candidate ward.")
        if self.model_run_id and self.risk_score_id and self.risk_score.model_run_id:
            if self.risk_score.model_run_id != self.model_run_id:
                raise ValidationError("Feedback label candidate model_run must match the risk_score model_run.")
        if self.superseded_by_surveillance_label_id:
            label = self.superseded_by_surveillance_label
            if label.ward_id != self.ward_id:
                raise ValidationError("Superseding surveillance label must belong to the candidate ward.")
            windows_overlap = label.label_window_start <= self.label_window_end and label.label_window_end >= self.label_window_start
            if not windows_overlap:
                raise ValidationError("Superseding surveillance label must overlap the feedback candidate window.")

    def save(self, *args, **kwargs):
        if not self.candidate_ref:
            self.candidate_ref = f"feedback_label_candidate:{self.public_id}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.ward.name} {self.label_window_start}:{self.label_window_end} [{self.outbreak_label}]"


class PopulationExposureSource(models.Model):
    SOURCE_TYPE_POPULATION_BASELINE = "population_baseline"
    SOURCE_TYPE_GRIDDED_POPULATION = "gridded_population"
    SOURCE_TYPE_SETTLEMENT_LAYER = "settlement_layer"
    SOURCE_TYPE_WASH_VULNERABILITY_LAYER = "wash_vulnerability_layer"
    SOURCE_TYPE_WATER_BODY_DISTANCE_LAYER = "water_body_distance_layer"
    SOURCE_TYPE_FLOOD_EXPOSURE_LAYER = "flood_exposure_layer"
    SOURCE_TYPE_CATCHMENT_MAPPING = "catchment_mapping"
    SOURCE_TYPE_CSV_BACKFILL = "csv_backfill"
    SOURCE_TYPE_CHOICES = [
        (SOURCE_TYPE_POPULATION_BASELINE, "Population baseline"),
        (SOURCE_TYPE_GRIDDED_POPULATION, "Gridded population"),
        (SOURCE_TYPE_SETTLEMENT_LAYER, "Settlement layer"),
        (SOURCE_TYPE_WASH_VULNERABILITY_LAYER, "WASH vulnerability layer"),
        (SOURCE_TYPE_WATER_BODY_DISTANCE_LAYER, "Water body distance layer"),
        (SOURCE_TYPE_FLOOD_EXPOSURE_LAYER, "Flood exposure layer"),
        (SOURCE_TYPE_CATCHMENT_MAPPING, "Catchment mapping"),
        (SOURCE_TYPE_CSV_BACKFILL, "CSV backfill"),
    ]

    source_name = models.CharField(max_length=120)
    source_type = models.CharField(max_length=40, choices=SOURCE_TYPE_CHOICES)
    source_timestamp = models.DateTimeField(null=True, blank=True)
    release_version = models.CharField(max_length=120, blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)
    source_ref = models.CharField(max_length=255, blank=True)
    operator_note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at", "source_name"]
        indexes = [
            models.Index(fields=["source_type", "release_version"], name="risk_popsrc_type_release_idx"),
            models.Index(fields=["source_name", "submitted_at"], name="risk_popsrc_name_sub_idx"),
        ]

    def __str__(self) -> str:
        release = self.release_version or "unversioned"
        return f"{self.source_name} {release} [{self.source_type}]"


class PopulationExposureIngestionRun(models.Model):
    STATUS_RUNNING = "RUNNING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_FAILED, "Failed"),
    ]

    CORRECTION_ORIGINAL = "original"
    CORRECTION_AMENDMENT = "amendment"
    CORRECTION_BACKFILL = "backfill"
    CORRECTION_RELEASE_REPLACEMENT = "release_replacement"
    CORRECTION_MODE_CHOICES = [
        (CORRECTION_ORIGINAL, "Original"),
        (CORRECTION_AMENDMENT, "Amendment"),
        (CORRECTION_BACKFILL, "Backfill"),
        (CORRECTION_RELEASE_REPLACEMENT, "Release replacement"),
    ]

    EXECUTION_MANUAL = "manual"
    EXECUTION_SCHEDULED = "scheduled"
    EXECUTION_REPLAY = "replay"
    EXECUTION_MODE_CHOICES = [
        (EXECUTION_MANUAL, "Manual"),
        (EXECUTION_SCHEDULED, "Scheduled"),
        (EXECUTION_REPLAY, "Replay"),
    ]

    source = models.ForeignKey(
        PopulationExposureSource,
        on_delete=models.PROTECT,
        related_name="ingestion_runs",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    source_name = models.CharField(max_length=120)
    source_type = models.CharField(max_length=40, choices=PopulationExposureSource.SOURCE_TYPE_CHOICES)
    source_timestamp = models.DateTimeField(null=True, blank=True)
    release_version = models.CharField(max_length=120, blank=True)
    source_ref = models.CharField(max_length=255, blank=True)
    adapter_key = models.CharField(max_length=80, default="csv")
    input_ref = models.CharField(max_length=255, blank=True)
    execution_mode = models.CharField(max_length=20, choices=EXECUTION_MODE_CHOICES, default=EXECUTION_MANUAL)
    correction_mode = models.CharField(max_length=40, choices=CORRECTION_MODE_CHOICES, default=CORRECTION_ORIGINAL)
    replacement_reason = models.TextField(blank=True)
    fallback_used = models.BooleanField(default=False)
    records_seen = models.PositiveIntegerField(default=0)
    records_loaded = models.PositiveIntegerField(default=0)
    records_rejected = models.PositiveIntegerField(default=0)
    operator_note = models.TextField(blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)
    results = models.JSONField(default=dict, blank=True)
    rejected_rows = models.JSONField(default=list, blank=True)
    error_summary = models.TextField(blank=True)
    replay_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replay_runs",
    )
    replaces_run = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replacement_runs",
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["source_type", "started_at"], name="risk_popexp_type_started_idx"),
            models.Index(fields=["status", "started_at"], name="risk_popexp_status_started_idx"),
            models.Index(fields=["correction_mode", "started_at"], name="risk_popexp_corr_started_idx"),
            models.Index(fields=["release_version", "started_at"], name="risk_popexp_rel_started_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    ~models.Q(correction_mode="release_replacement")
                    | (
                        models.Q(replaces_run_id__isnull=False)
                        & ~models.Q(replacement_reason="")
                        & ~models.Q(release_version="")
                        & ~models.Q(source_ref="")
                    )
                ),
                name="risk_popexp_repl_required",
            ),
            models.CheckConstraint(
                check=models.Q(replaces_run_id__isnull=True) | models.Q(correction_mode="release_replacement"),
                name="risk_popexp_repl_only",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_name} [{self.status}] {self.started_at}"


class PopulationExposureTruth(models.TextChoices):
    DIRECT_POPULATION_BASELINE = "direct_population_baseline", "Direct population baseline"
    SPATIALLY_AGGREGATED_SOURCE = "spatially_aggregated_source", "Spatially aggregated source"
    DERIVED_EXPOSURE_PROXY = "derived_exposure_proxy", "Derived exposure proxy"
    MANUAL_OVERRIDE = "manual_override", "Manual override"
    SEEDED_DEMO = "seeded_demo", "Seeded demo"


class PopulationExposureSourceKind(models.TextChoices):
    LIVE = "live", "Live"
    BACKFILL = "backfill", "Backfill"
    SEEDED = "seeded", "Seeded"


class PopulationExposureFreshness(models.TextChoices):
    FRESH = "fresh", "Fresh"
    DELAYED = "delayed", "Delayed"
    STALE = "stale", "Stale"
    REPLACED_BY_NEW_RELEASE = "replaced_by_new_release", "Replaced by new release"
    REPLAY_DIAGNOSTIC = "replay_diagnostic", "Replay diagnostic"
    REPLACEMENT_NOT_ACTIVATED = "replacement_not_activated", "Replacement not activated"
    UNKNOWN = "unknown", "Unknown"


class PopulationBaselineRecord(models.Model):
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="population_baselines")
    ingestion_run = models.ForeignKey(
        PopulationExposureIngestionRun,
        on_delete=models.PROTECT,
        related_name="population_baseline_records",
    )
    source = models.ForeignKey(
        PopulationExposureSource,
        on_delete=models.PROTECT,
        related_name="population_baseline_records",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    population_total = models.PositiveIntegerField()
    population_under_five = models.PositiveIntegerField(null=True, blank=True)
    household_count_proxy = models.PositiveIntegerField(null=True, blank=True)
    truth_class = models.CharField(
        max_length=40,
        choices=PopulationExposureTruth.choices,
        default=PopulationExposureTruth.DIRECT_POPULATION_BASELINE,
    )
    source_name = models.CharField(max_length=120)
    source_kind = models.CharField(
        max_length=20,
        choices=PopulationExposureSourceKind.choices,
        default=PopulationExposureSourceKind.LIVE,
    )
    freshness_state = models.CharField(
        max_length=40,
        choices=PopulationExposureFreshness.choices,
        default=PopulationExposureFreshness.UNKNOWN,
    )
    release_version = models.CharField(max_length=120, blank=True)
    supersedes_record_ref = models.CharField(max_length=160, blank=True)
    revision_number = models.PositiveIntegerField(default=1)
    source_ref = models.CharField(max_length=255, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "ward__name"]
        indexes = [
            models.Index(fields=["ward", "recorded_at"], name="risk_popbase_ward_recorded_idx"),
            models.Index(fields=["truth_class", "recorded_at"], name="risk_popbase_truth_idx"),
            models.Index(fields=["release_version", "recorded_at"], name="risk_popbase_release_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(truth_class=PopulationExposureTruth.DERIVED_EXPOSURE_PROXY),
                name="risk_popbase_no_proxy",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ward.name} population {self.population_total} [{self.truth_class}]"


class ExposureFeatureRecord(models.Model):
    EXPOSURE_POPULATION_DENSITY = "population_density"
    EXPOSURE_SETTLEMENT_CONCENTRATION = "settlement_concentration"
    EXPOSURE_FLOODPLAIN_EXPOSURE = "floodplain_exposure"
    EXPOSURE_WATER_BODY_PROXIMITY = "water_body_proximity"
    EXPOSURE_WASH_VULNERABILITY = "wash_vulnerability"
    EXPOSURE_EXPOSED_POPULATION_PROXY = "exposed_population_proxy"
    EXPOSURE_TYPE_CHOICES = [
        (EXPOSURE_POPULATION_DENSITY, "Population density"),
        (EXPOSURE_SETTLEMENT_CONCENTRATION, "Settlement concentration"),
        (EXPOSURE_FLOODPLAIN_EXPOSURE, "Floodplain exposure"),
        (EXPOSURE_WATER_BODY_PROXIMITY, "Water body proximity"),
        (EXPOSURE_WASH_VULNERABILITY, "WASH vulnerability"),
        (EXPOSURE_EXPOSED_POPULATION_PROXY, "Exposed population proxy"),
    ]

    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="exposure_feature_records")
    ingestion_run = models.ForeignKey(
        PopulationExposureIngestionRun,
        on_delete=models.PROTECT,
        related_name="exposure_feature_records",
    )
    source = models.ForeignKey(
        PopulationExposureSource,
        on_delete=models.PROTECT,
        related_name="exposure_feature_records",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    exposure_type = models.CharField(max_length=40, choices=EXPOSURE_TYPE_CHOICES)
    exposure_value = models.FloatField()
    unit = models.CharField(max_length=40, blank=True)
    truth_class = models.CharField(
        max_length=40,
        choices=PopulationExposureTruth.choices,
        default=PopulationExposureTruth.DERIVED_EXPOSURE_PROXY,
    )
    source_name = models.CharField(max_length=120)
    source_kind = models.CharField(
        max_length=20,
        choices=PopulationExposureSourceKind.choices,
        default=PopulationExposureSourceKind.LIVE,
    )
    freshness_state = models.CharField(
        max_length=40,
        choices=PopulationExposureFreshness.choices,
        default=PopulationExposureFreshness.UNKNOWN,
    )
    aggregation_method = models.CharField(max_length=120, blank=True)
    spatial_resolution = models.CharField(max_length=120, blank=True)
    release_version = models.CharField(max_length=120, blank=True)
    source_ref = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "ward__name", "exposure_type"]
        indexes = [
            models.Index(fields=["ward", "exposure_type", "recorded_at"], name="risk_expfeat_ward_type_idx"),
            models.Index(fields=["truth_class", "recorded_at"], name="risk_expfeat_truth_idx"),
            models.Index(fields=["release_version", "recorded_at"], name="risk_expfeat_release_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(truth_class=PopulationExposureTruth.DIRECT_POPULATION_BASELINE),
                name="risk_expfeat_no_direct",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ward.name} {self.exposure_type}={self.exposure_value}"


class CatchmentPopulationRecord(models.Model):
    facility = models.ForeignKey(
        HealthFacility,
        on_delete=models.PROTECT,
        related_name="catchment_population_records",
    )
    ingestion_run = models.ForeignKey(
        PopulationExposureIngestionRun,
        on_delete=models.PROTECT,
        related_name="catchment_population_records",
    )
    source = models.ForeignKey(
        PopulationExposureSource,
        on_delete=models.PROTECT,
        related_name="catchment_population_records",
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    catchment_population_estimate = models.FloatField()
    catchment_under_five_estimate = models.FloatField(null=True, blank=True)
    assigned_ward_ids = models.JSONField(default=list, blank=True)
    assignment_method = models.CharField(max_length=120, blank=True)
    truth_class = models.CharField(
        max_length=40,
        choices=PopulationExposureTruth.choices,
        default=PopulationExposureTruth.DERIVED_EXPOSURE_PROXY,
    )
    source_name = models.CharField(max_length=120)
    source_kind = models.CharField(
        max_length=20,
        choices=PopulationExposureSourceKind.choices,
        default=PopulationExposureSourceKind.LIVE,
    )
    freshness_state = models.CharField(
        max_length=40,
        choices=PopulationExposureFreshness.choices,
        default=PopulationExposureFreshness.UNKNOWN,
    )
    release_version = models.CharField(max_length=120, blank=True)
    source_ref = models.CharField(max_length=255, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at", "facility__name"]
        indexes = [
            models.Index(fields=["facility", "recorded_at"], name="risk_catchpop_fac_record_idx"),
            models.Index(fields=["truth_class", "recorded_at"], name="risk_catchpop_truth_idx"),
            models.Index(fields=["release_version", "recorded_at"], name="risk_catchpop_release_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(truth_class=PopulationExposureTruth.DIRECT_POPULATION_BASELINE),
                name="risk_catchpop_no_direct",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.facility.name} catchment {self.catchment_population_estimate}"


class FacilityReadinessSource(models.Model):
    SOURCE_TYPE_READINESS_SNAPSHOT = "readiness_snapshot"
    SOURCE_TYPE_CHOICES = [
        (SOURCE_TYPE_READINESS_SNAPSHOT, "Readiness snapshot"),
    ]

    source_name = models.CharField(max_length=120)
    source_type = models.CharField(max_length=40, choices=SOURCE_TYPE_CHOICES, default=SOURCE_TYPE_READINESS_SNAPSHOT)
    source_timestamp = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)
    reporting_period_start = models.DateField(null=True, blank=True)
    reporting_period_end = models.DateField(null=True, blank=True)
    source_ref = models.CharField(max_length=255, blank=True)
    operator_note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at", "source_name"]
        indexes = [
            models.Index(fields=["source_type", "reporting_period_start"], name="risk_facsrc_type_period_idx"),
            models.Index(fields=["source_name", "submitted_at"], name="risk_facsrc_name_sub_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(reporting_period_start__isnull=True)
                    | models.Q(reporting_period_end__isnull=True)
                    | models.Q(reporting_period_start__lte=models.F("reporting_period_end"))
                ),
                name="risk_facsrc_period_order",
            ),
        ]

    def __str__(self) -> str:
        period = ""
        if self.reporting_period_start and self.reporting_period_end:
            period = f" {self.reporting_period_start}:{self.reporting_period_end}"
        return f"{self.source_name}{period} [{self.source_type}]"


class FacilityReadinessIngestionRun(models.Model):
    STATUS_RUNNING = "RUNNING"
    STATUS_SUCCESS = "SUCCESS"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_FAILED, "Failed"),
    ]

    EXECUTION_MANUAL = "manual"
    EXECUTION_SCHEDULED = "scheduled"
    EXECUTION_REPLAY = "replay"
    EXECUTION_MODE_CHOICES = [
        (EXECUTION_MANUAL, "Manual"),
        (EXECUTION_SCHEDULED, "Scheduled"),
        (EXECUTION_REPLAY, "Replay"),
    ]

    source = models.ForeignKey(
        FacilityReadinessSource,
        on_delete=models.PROTECT,
        related_name="ingestion_runs",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    source_name = models.CharField(max_length=120)
    source_type = models.CharField(max_length=40, choices=FacilityReadinessSource.SOURCE_TYPE_CHOICES)
    source_timestamp = models.DateTimeField(null=True, blank=True)
    reporting_period_start = models.DateField(null=True, blank=True)
    reporting_period_end = models.DateField(null=True, blank=True)
    source_ref = models.CharField(max_length=255, blank=True)
    adapter_key = models.CharField(max_length=80, default="facility_readiness_snapshot_csv")
    input_ref = models.CharField(max_length=255, blank=True)
    execution_mode = models.CharField(max_length=20, choices=EXECUTION_MODE_CHOICES, default=EXECUTION_MANUAL)
    fallback_used = models.BooleanField(default=False)
    records_seen = models.PositiveIntegerField(default=0)
    records_loaded = models.PositiveIntegerField(default=0)
    records_rejected = models.PositiveIntegerField(default=0)
    operator_note = models.TextField(blank=True)
    source_metadata = models.JSONField(default=dict, blank=True)
    results = models.JSONField(default=dict, blank=True)
    rejected_rows = models.JSONField(default=list, blank=True)
    error_summary = models.TextField(blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["source_type", "started_at"], name="risk_facrun_type_started_idx"),
            models.Index(fields=["status", "started_at"], name="risk_facrun_status_idx"),
            models.Index(fields=["reporting_period_start"], name="risk_facrun_period_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(reporting_period_start__isnull=True)
                    | models.Q(reporting_period_end__isnull=True)
                    | models.Q(reporting_period_start__lte=models.F("reporting_period_end"))
                ),
                name="risk_facrun_period_order",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_name} [{self.status}] {self.started_at}"


class FacilityReadinessSourceKind(models.TextChoices):
    FACILITY_REPORT = "facility_report", "Facility report"
    LOGISTICS_SYSTEM = "logistics_system", "Logistics system"
    COUNTY_OPERATIONS = "county_operations", "County operations"
    SEEDED_DEMO = "seeded_demo", "Seeded demo"


class FacilityReadinessFreshness(models.TextChoices):
    FRESH = "fresh", "Fresh"
    DELAYED = "delayed", "Delayed"
    STALE = "stale", "Stale"
    REPLAY_DIAGNOSTIC = "replay_diagnostic", "Replay diagnostic"
    UNKNOWN = "unknown", "Unknown"


class FacilityReadinessState(models.TextChoices):
    READY = "ready", "Ready"
    WATCH = "watch", "Watch"
    CAPACITY_CONCERN = "capacity_concern", "Capacity concern"


class FacilityReadinessSnapshot(models.Model):
    facility = models.ForeignKey(
        HealthFacility,
        on_delete=models.PROTECT,
        related_name="readiness_snapshots",
    )
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="facility_readiness_snapshots")
    ingestion_run = models.ForeignKey(
        FacilityReadinessIngestionRun,
        on_delete=models.PROTECT,
        related_name="readiness_snapshots",
    )
    source = models.ForeignKey(
        FacilityReadinessSource,
        on_delete=models.PROTECT,
        related_name="readiness_snapshots",
    )
    reported_at = models.DateTimeField()
    ors_sachets_available = models.PositiveIntegerField(default=0)
    iv_fluids_available = models.PositiveIntegerField(default=0)
    zinc_available = models.PositiveIntegerField(default=0)
    chlorine_available = models.PositiveIntegerField(default=0)
    beds_available = models.PositiveIntegerField(default=0)
    staff_on_duty = models.PositiveIntegerField(default=0)
    referral_available = models.BooleanField(default=False)
    service_disruption = models.BooleanField(default=False)
    stockout_notes = models.TextField(blank=True)
    source_kind = models.CharField(
        max_length=40,
        choices=FacilityReadinessSourceKind.choices,
        default=FacilityReadinessSourceKind.FACILITY_REPORT,
    )
    freshness_state = models.CharField(
        max_length=40,
        choices=FacilityReadinessFreshness.choices,
        default=FacilityReadinessFreshness.UNKNOWN,
    )
    readiness_state = models.CharField(
        max_length=40,
        choices=FacilityReadinessState.choices,
        default=FacilityReadinessState.READY,
    )
    readiness_score = models.FloatField(default=100.0)
    source_name = models.CharField(max_length=120)
    source_ref = models.CharField(max_length=255, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reported_at", "facility__name"]
        indexes = [
            models.Index(fields=["facility", "reported_at"], name="risk_facready_fac_rep_idx"),
            models.Index(fields=["ward", "reported_at"], name="risk_facready_ward_rep_idx"),
            models.Index(fields=["freshness_state", "reported_at"], name="risk_facready_fresh_idx"),
            models.Index(fields=["readiness_state", "reported_at"], name="risk_facready_state_idx"),
            models.Index(fields=["source_kind", "reported_at"], name="risk_facready_source_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["facility", "reported_at"], name="risk_facready_fac_report_uniq"),
        ]

    def __str__(self) -> str:
        return f"{self.facility.name} readiness {self.reported_at} [{self.readiness_state}]"


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


class ModelRegistryPromotionState(models.TextChoices):
    CANDIDATE = "CANDIDATE", "Candidate"
    ACTIVE_PROMOTED = "ACTIVE_PROMOTED", "Active promoted"
    RETIRED = "RETIRED", "Retired"
    ROLLED_BACK = "ROLLED_BACK", "Rolled back"


class ModelRegistryMonitoringState(models.TextChoices):
    NOT_CONFIGURED = "NOT_CONFIGURED", "Not configured"
    HEALTHY = "HEALTHY", "Healthy"
    WARNING = "WARNING", "Warning"
    BREACHED = "BREACHED", "Breached"
    REVIEW_REQUIRED = "REVIEW_REQUIRED", "Review required"


class ModelRegistryApprovalState(models.TextChoices):
    NOT_REVIEWED = "NOT_REVIEWED", "Not reviewed"
    PENDING_REVIEW = "PENDING_REVIEW", "Pending review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class ModelRegistryLifecycleState(models.TextChoices):
    CANDIDATE = "CANDIDATE", "Candidate"
    CHALLENGER = "CHALLENGER", "Challenger"
    ACTIVE = "ACTIVE", "Active"
    RETIRED = "RETIRED", "Retired"
    ROLLED_BACK = "ROLLED_BACK", "Rolled back"


def _default_model_registry_version() -> str:
    return str(uuid.uuid4())


class ModelRegistryEntry(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    registry_version = models.CharField(
        max_length=180,
        default=_default_model_registry_version,
        unique=True,
        editable=False,
    )
    algorithm = models.CharField(max_length=80)
    model_family = models.CharField(max_length=120, blank=True)
    model_version = models.CharField(max_length=80)
    feature_schema_version = models.CharField(max_length=80, blank=True)
    model_run = models.OneToOneField(
        "risk.ModelRun",
        on_delete=models.PROTECT,
        related_name="registry_entry",
    )
    promotion_event = models.ForeignKey(
        "risk.ModelPromotionEvent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_registry_entries",
    )
    promotion_state = models.CharField(
        max_length=32,
        choices=ModelRegistryPromotionState.choices,
        default=ModelRegistryPromotionState.CANDIDATE,
    )
    approval_state = models.CharField(
        max_length=32,
        choices=ModelRegistryApprovalState.choices,
        default=ModelRegistryApprovalState.NOT_REVIEWED,
    )
    lifecycle_state = models.CharField(
        max_length=32,
        choices=ModelRegistryLifecycleState.choices,
        default=ModelRegistryLifecycleState.CANDIDATE,
    )
    deployment_target = models.CharField(max_length=80, default="live_baseline")
    artifact_location = models.CharField(max_length=500, blank=True)
    artifact_format = models.CharField(max_length=32, blank=True)
    artifact_size_bytes = models.PositiveBigIntegerField(default=0)
    artifact_sha256 = models.CharField(max_length=64, blank=True)
    training_feature_dataset_ref = models.CharField(max_length=160, blank=True)
    inference_feature_dataset_ref = models.CharField(max_length=160, blank=True)
    training_label_dataset_ref = models.CharField(max_length=160, blank=True)
    feature_contract = models.JSONField(default=list, blank=True)
    code_commit = models.CharField(max_length=160, blank=True)
    training_started_at = models.DateTimeField(null=True, blank=True)
    training_completed_at = models.DateTimeField(null=True, blank=True)
    evaluation_started_at = models.DateTimeField(null=True, blank=True)
    evaluation_completed_at = models.DateTimeField(null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    truth_source_classification = models.CharField(max_length=80, blank=True)
    intended_use = models.TextField(blank=True)
    prohibited_uses = models.JSONField(default=list, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.CharField(max_length=160, blank=True)
    approval_reason = models.TextField(blank=True)
    registration_reason = models.TextField(blank=True)
    active_from = models.DateTimeField(null=True, blank=True)
    active_until = models.DateTimeField(null=True, blank=True)
    retired_reason = models.TextField(blank=True)
    rollback_target = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rollback_sources",
    )
    challenger_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="challengers",
    )
    monitoring_state = models.CharField(
        max_length=32,
        choices=ModelRegistryMonitoringState.choices,
        default=ModelRegistryMonitoringState.NOT_CONFIGURED,
    )
    owner = models.CharField(max_length=160, blank=True)
    review_due_date = models.DateField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-active_from", "-created_at"]
        indexes = [
            models.Index(fields=["promotion_state", "active_from"], name="risk_modelreg_state_active_idx"),
            models.Index(fields=["algorithm", "model_version"], name="risk_modelreg_alg_ver_idx"),
            models.Index(fields=["monitoring_state", "review_due_date"], name="risk_modelreg_monitor_idx"),
            models.Index(fields=["lifecycle_state", "deployment_target"], name="risk_modelreg_life_target_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(active_until__isnull=True)
                    | models.Q(active_from__isnull=True)
                    | models.Q(active_until__gte=models.F("active_from"))
                ),
                name="risk_modelreg_active_window_order",
            ),
            models.CheckConstraint(
                check=(
                    ~models.Q(promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED)
                    | (
                        models.Q(active_from__isnull=False)
                        & models.Q(active_until__isnull=True)
                    )
                ),
                name="risk_modelreg_active_window_required",
            ),
            models.UniqueConstraint(
                fields=["deployment_target", "lifecycle_state"],
                condition=models.Q(lifecycle_state=ModelRegistryLifecycleState.ACTIVE),
                name="risk_modelreg_one_active_per_target",
            ),
            models.CheckConstraint(
                check=(
                    ~models.Q(lifecycle_state=ModelRegistryLifecycleState.ACTIVE)
                    | (
                        models.Q(approval_state=ModelRegistryApprovalState.APPROVED)
                        & models.Q(promotion_state=ModelRegistryPromotionState.ACTIVE_PROMOTED)
                        & models.Q(promotion_event__isnull=False)
                        & models.Q(active_from__isnull=False)
                        & models.Q(active_until__isnull=True)
                    )
                ),
                name="risk_modelreg_active_requires_approval",
            ),
            models.CheckConstraint(
                check=(
                    ~models.Q(approval_state=ModelRegistryApprovalState.APPROVED)
                    | (
                        models.Q(approved_at__isnull=False)
                        & models.Q(approved_by__regex=r"\S")
                    )
                ),
                name="risk_modelreg_approved_requires_evidence",
            ),
            models.CheckConstraint(
                check=(
                    ~models.Q(lifecycle_state=ModelRegistryLifecycleState.CHALLENGER)
                    | models.Q(challenger_of__isnull=False)
                ),
                name="risk_modelreg_challenger_requires_target",
            ),
        ]

    def clean(self):
        if self.promotion_state == ModelRegistryPromotionState.ACTIVE_PROMOTED:
            if self.active_from is None:
                raise ValidationError("Active promoted registry entries require active_from.")
            if self.active_until is not None:
                raise ValidationError("Active promoted registry entries require active_until to be empty.")
            if self.promotion_event_id is None:
                raise ValidationError("Active promoted registry entries require promotion_event.")
        if self.lifecycle_state == ModelRegistryLifecycleState.ACTIVE:
            if self.approval_state != ModelRegistryApprovalState.APPROVED:
                raise ValidationError("Active registry entries require approval.")
            if self.promotion_state != ModelRegistryPromotionState.ACTIVE_PROMOTED:
                raise ValidationError("Active registry entries require active promotion state.")
        if self.approval_state == ModelRegistryApprovalState.APPROVED:
            if self.approved_at is None or not (self.approved_by or "").strip():
                raise ValidationError("Approved registry entries require approval evidence.")
        if self.lifecycle_state == ModelRegistryLifecycleState.CHALLENGER and not self.challenger_of_id:
            raise ValidationError("Challenger registry entries require a champion target.")
        if self.active_until is not None and self.active_from is not None and self.active_until < self.active_from:
            raise ValidationError("active_until must be after active_from.")
        if self.promotion_event_id and self.id:
            if self.promotion_event.registry_entry_id != self.id:
                raise ValidationError("Registry entry promotion_event must point back to the registry entry.")
            if self.promotion_event.model_run_id != self.model_run_id:
                raise ValidationError("Registry entry promotion_event must reference the same model run.")

    _IMMUTABLE_AFTER_APPROVAL_FIELDS = (
        "registry_version",
        "algorithm",
        "model_family",
        "model_version",
        "model_run_id",
        "feature_schema_version",
        "deployment_target",
        "artifact_location",
        "artifact_format",
        "artifact_size_bytes",
        "artifact_sha256",
        "training_feature_dataset_ref",
        "inference_feature_dataset_ref",
        "training_label_dataset_ref",
        "feature_contract",
        "code_commit",
        "training_started_at",
        "training_completed_at",
        "evaluation_started_at",
        "evaluation_completed_at",
        "metrics",
        "truth_source_classification",
        "intended_use",
        "prohibited_uses",
    )

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            previous = type(self).objects.filter(pk=self.pk).first()
            if previous and previous.approval_state == ModelRegistryApprovalState.APPROVED:
                for field_name in self._IMMUTABLE_AFTER_APPROVAL_FIELDS:
                    if getattr(previous, field_name) != getattr(self, field_name):
                        raise ValidationError(
                            f"Approved registry entries are immutable: {field_name}."
                        )
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.approval_state == ModelRegistryApprovalState.APPROVED or (
            self.pk and self.governance_events.exists()
        ):
            raise ValidationError("Registered entries with governance history cannot be deleted.")
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.algorithm} {self.model_version} [{self.promotion_state}]"


class ModelPromotionEvent(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    registry_entry = models.ForeignKey(
        ModelRegistryEntry,
        on_delete=models.PROTECT,
        related_name="promotion_events",
    )
    model_run = models.ForeignKey(
        "risk.ModelRun",
        on_delete=models.PROTECT,
        related_name="promotion_events",
    )
    previous_registry_entry = models.ForeignKey(
        ModelRegistryEntry,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseding_promotion_events",
    )
    source = models.CharField(max_length=120, default="phase_4_temporal_backtest")
    promoted_by = models.CharField(max_length=160, blank=True)
    promoted_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="model_promotions_governed",
    )
    active_from = models.DateTimeField(default=timezone.now)
    review_due_date = models.DateField(null=True, blank=True)
    evidence_metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["model_run", "occurred_at"], name="risk_modelprom_run_time_idx"),
            models.Index(fields=["source", "occurred_at"], name="risk_modelprom_source_idx"),
        ]

    def __str__(self) -> str:
        return f"Promotion for {self.model_run.model_version} at {self.occurred_at}"


class ModelRollbackEvent(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    rolled_back_from = models.ForeignKey(
        ModelRegistryEntry,
        on_delete=models.PROTECT,
        related_name="rollback_events_from",
    )
    rollback_target = models.ForeignKey(
        ModelRegistryEntry,
        on_delete=models.PROTECT,
        related_name="rollback_events_as_target",
    )
    rolled_back_by = models.CharField(max_length=160, blank=True)
    rolled_back_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="model_rollbacks_governed",
    )
    reason = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["rollback_target", "occurred_at"], name="risk_modelroll_target_idx"),
            models.Index(fields=["rolled_back_from", "occurred_at"], name="risk_modelroll_from_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(reason__regex=r"\S"),
                name="risk_modelroll_reason_not_blank",
            ),
            models.CheckConstraint(
                check=models.Q(rolled_back_by__regex=r"\S"),
                name="risk_modelroll_operator_not_blank",
            ),
            models.CheckConstraint(
                check=~models.Q(rolled_back_from=models.F("rollback_target")),
                name="risk_modelroll_target_diff",
            ),
        ]

    def clean(self):
        if (
            self.rolled_back_from_id
            and self.rollback_target_id
            and self.rolled_back_from_id == self.rollback_target_id
        ):
            raise ValidationError("Rollback target must differ from the model being rolled back.")
        if not (self.reason or "").strip():
            raise ValidationError("Rollback reason is required.")
        if not (self.rolled_back_by or "").strip():
            raise ValidationError("Rollback operator is required.")

    def __str__(self) -> str:
        return f"Rollback {self.rolled_back_from_id} -> {self.rollback_target_id} at {self.occurred_at}"


class ImmutableModelGovernanceEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Model governance events are immutable.")

    def delete(self):
        raise ValidationError("Model governance events are immutable.")


class ModelGovernanceEvent(models.Model):
    EVENT_REGISTERED = "REGISTERED"
    EVENT_APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    EVENT_APPROVED = "APPROVED"
    EVENT_REJECTED = "REJECTED"
    EVENT_CHALLENGER_DESIGNATED = "CHALLENGER_DESIGNATED"
    EVENT_ACTIVATED = "ACTIVATED"
    EVENT_RETIRED = "RETIRED"
    EVENT_ROLLED_BACK = "ROLLED_BACK"
    EVENT_CHOICES = [
        (EVENT_REGISTERED, "Registered"),
        (EVENT_APPROVAL_REQUESTED, "Approval requested"),
        (EVENT_APPROVED, "Approved"),
        (EVENT_REJECTED, "Rejected"),
        (EVENT_CHALLENGER_DESIGNATED, "Challenger designated"),
        (EVENT_ACTIVATED, "Activated"),
        (EVENT_RETIRED, "Retired"),
        (EVENT_ROLLED_BACK, "Rolled back"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    registry_entry = models.ForeignKey(
        ModelRegistryEntry,
        on_delete=models.PROTECT,
        related_name="governance_events",
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    actor = models.CharField(max_length=160)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="model_governance_events",
    )
    reason = models.TextField()
    previous_approval_state = models.CharField(max_length=32, blank=True)
    resulting_approval_state = models.CharField(max_length=32, blank=True)
    previous_lifecycle_state = models.CharField(max_length=32, blank=True)
    resulting_lifecycle_state = models.CharField(max_length=32, blank=True)
    previous_promotion_state = models.CharField(max_length=32, blank=True)
    resulting_promotion_state = models.CharField(max_length=32, blank=True)
    evidence_snapshot = models.JSONField(default=dict, blank=True)
    request_id = models.CharField(max_length=160, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(fields=["registry_entry", "occurred_at"], name="risk_modelgov_entry_time_idx"),
            models.Index(fields=["event_type", "occurred_at"], name="risk_modelgov_type_time_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(actor__regex=r"\S"),
                name="risk_modelgov_actor_not_blank",
            ),
            models.CheckConstraint(
                check=models.Q(reason__regex=r"\S"),
                name="risk_modelgov_reason_not_blank",
            ),
        ]

    objects = ImmutableModelGovernanceEventQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Model governance events are immutable.")
        if not self.actor_user_id:
            raise ValidationError("Model governance events require an active actor user.")
        if self.actor_user_id and not self.actor_user.is_active:
            raise ValidationError("Model governance events require an active actor user.")
        if self.actor_user_id and self.actor:
            actor_username = self.actor_user.get_username()
            if self.actor != actor_username:
                raise ValidationError("Model governance event actor snapshot does not match actor user.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Model governance events are immutable.")

    def __str__(self) -> str:
        return f"{self.event_type} {self.registry_entry_id} at {self.occurred_at}"


class ModelMonitoringState(models.TextChoices):
    HEALTHY = "HEALTHY", "Healthy"
    WARNING = "WARNING", "Warning"
    BREACHED = "BREACHED", "Breached"
    NOT_READY = "NOT_READY", "Not ready"


class ModelMonitoringThresholdDirection(models.TextChoices):
    HIGHER_IS_WORSE = "HIGHER_IS_WORSE", "Higher is worse"
    LOWER_IS_WORSE = "LOWER_IS_WORSE", "Lower is worse"


class ModelMonitoringThreshold(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    metric_name = models.CharField(max_length=120)
    version = models.CharField(max_length=40, default="phase-2-default-v1")
    warning_threshold = models.FloatField(null=True, blank=True)
    breach_threshold = models.FloatField(null=True, blank=True)
    direction = models.CharField(
        max_length=32,
        choices=ModelMonitoringThresholdDirection.choices,
        default=ModelMonitoringThresholdDirection.HIGHER_IS_WORSE,
    )
    baseline_window = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["metric_name", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["metric_name", "version"],
                name="risk_modelmon_thr_metric_ver_uniq",
            ),
            models.UniqueConstraint(
                fields=["metric_name"],
                condition=models.Q(is_active=True),
                name="risk_modelmon_thr_one_active",
            ),
        ]
        indexes = [
            models.Index(fields=["metric_name", "is_active"], name="risk_modelmon_thr_active_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.metric_name}:{self.version}"


class ModelMonitoringSnapshot(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    monitoring_run_id = models.UUIDField(default=uuid.uuid4)
    registry_entry = models.ForeignKey(
        ModelRegistryEntry,
        on_delete=models.PROTECT,
        related_name="monitoring_snapshots",
    )
    model_run = models.ForeignKey(
        "risk.ModelRun",
        on_delete=models.PROTECT,
        related_name="monitoring_snapshots",
    )
    threshold = models.ForeignKey(
        ModelMonitoringThreshold,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="snapshots",
    )
    metric_name = models.CharField(max_length=120)
    metric_family = models.CharField(max_length=80, blank=True)
    value = models.FloatField(null=True, blank=True)
    baseline_value = models.FloatField(null=True, blank=True)
    threshold_value = models.FloatField(null=True, blank=True)
    threshold_version = models.CharField(max_length=40, blank=True)
    state = models.CharField(
        max_length=20,
        choices=ModelMonitoringState.choices,
        default=ModelMonitoringState.NOT_READY,
    )
    generated_at = models.DateTimeField(default=timezone.now)
    source_dataset_refs = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at", "metric_name"]
        indexes = [
            models.Index(fields=["registry_entry", "generated_at"], name="risk_modelmon_reg_time_idx"),
            models.Index(fields=["model_run", "metric_name"], name="risk_modelmon_run_metric_idx"),
            models.Index(fields=["metric_name", "state"], name="risk_modelmon_metric_state_idx"),
            models.Index(fields=["monitoring_run_id"], name="risk_modelmon_runid_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.model_run.model_version}:{self.metric_name} [{self.state}]"

    def clean(self):
        if (
            self.registry_entry_id
            and self.model_run_id
            and self.registry_entry.model_run_id != self.model_run_id
        ):
            raise ValidationError("Monitoring snapshot model_run must match registry_entry model_run.")
        if self.threshold_id:
            if self.metric_name and self.threshold.metric_name != self.metric_name:
                raise ValidationError("Monitoring snapshot threshold must match metric_name.")
            if self.threshold_version and self.threshold.version != self.threshold_version:
                raise ValidationError("Monitoring snapshot threshold_version must match threshold.version.")


class ModelRetrainingRecommendationState(models.TextChoices):
    REVIEW_NOT_REQUIRED = "REVIEW_NOT_REQUIRED", "Review not required"
    REVIEW_REQUIRED = "REVIEW_REQUIRED", "Review required"
    RETRAINING_RECOMMENDED = "RETRAINING_RECOMMENDED", "Retraining recommended"


class ModelRetrainingRecommendation(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    registry_entry = models.ForeignKey(
        ModelRegistryEntry,
        on_delete=models.PROTECT,
        related_name="retraining_recommendations",
    )
    model_run = models.ForeignKey(
        "risk.ModelRun",
        on_delete=models.PROTECT,
        related_name="retraining_recommendations",
    )
    recommendation_state = models.CharField(
        max_length=40,
        choices=ModelRetrainingRecommendationState.choices,
        default=ModelRetrainingRecommendationState.REVIEW_NOT_REQUIRED,
    )
    recommended_action = models.CharField(max_length=160, default="continue_monitoring")
    reason_codes = models.JSONField(default=list, blank=True)
    trigger_summary = models.JSONField(default=dict, blank=True)
    source_snapshot_refs = models.JSONField(default=list, blank=True)
    new_label_count = models.PositiveIntegerField(default=0)
    false_alert_count = models.PositiveIntegerField(default=0)
    miss_count = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at", "-id"]
        indexes = [
            models.Index(fields=["registry_entry", "generated_at"], name="risk_modelrec_reg_time_idx"),
            models.Index(fields=["model_run", "generated_at"], name="risk_modelrec_run_time_idx"),
            models.Index(fields=["recommendation_state", "generated_at"], name="risk_modelrec_state_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.model_run.model_version} [{self.recommendation_state}]"

    def clean(self):
        if (
            self.registry_entry_id
            and self.model_run_id
            and self.registry_entry.model_run_id != self.model_run_id
        ):
            raise ValidationError("Retraining recommendation model_run must match registry_entry model_run.")


class ModelChallengerBenchmarkStatus(models.TextChoices):
    BENCHMARK_ONLY = "BENCHMARK_ONLY", "Benchmark only"
    NOT_COMPARABLE = "NOT_COMPARABLE", "Not comparable"
    REVIEW_REQUIRED = "REVIEW_REQUIRED", "Review required"


class ModelChampionChallengerComparison(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    champion_registry_entry = models.ForeignKey(
        ModelRegistryEntry,
        on_delete=models.PROTECT,
        related_name="champion_comparisons",
    )
    champion_model_run = models.ForeignKey(
        "risk.ModelRun",
        on_delete=models.PROTECT,
        related_name="champion_comparisons",
    )
    challenger_model_run = models.ForeignKey(
        "risk.ModelRun",
        on_delete=models.PROTECT,
        related_name="challenger_comparisons",
    )
    challenger_algorithm = models.CharField(max_length=80)
    challenger_model_version = models.CharField(max_length=80)
    benchmark_status = models.CharField(
        max_length=32,
        choices=ModelChallengerBenchmarkStatus.choices,
        default=ModelChallengerBenchmarkStatus.BENCHMARK_ONLY,
    )
    comparison_validity = models.CharField(max_length=80, default="comparable_inputs")
    recommended_action = models.CharField(max_length=160, default="keep_champion_monitor_challenger")
    input_alignment = models.JSONField(default=dict, blank=True)
    operational_metrics = models.JSONField(default=dict, blank=True)
    temporal_metrics = models.JSONField(default=dict, blank=True)
    comparison_summary = models.JSONField(default=dict, blank=True)
    promotion_blockers = models.JSONField(default=list, blank=True)
    dashboard_summary = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-generated_at", "-id"]
        indexes = [
            models.Index(
                fields=["champion_registry_entry", "generated_at"],
                name="risk_modelcc_champ_time_idx",
            ),
            models.Index(fields=["challenger_model_run", "generated_at"], name="risk_modelcc_chal_time_idx"),
            models.Index(fields=["benchmark_status", "generated_at"], name="risk_modelcc_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(champion_model_run=models.F("challenger_model_run")),
                name="risk_modelcc_champion_diff_challenger",
            ),
        ]

    def clean(self):
        if self.champion_model_run_id and self.challenger_model_run_id:
            if self.champion_model_run_id == self.challenger_model_run_id:
                raise ValidationError("Challenger model run must differ from the champion model run.")
        if (
            self.champion_registry_entry_id
            and self.champion_model_run_id
            and self.champion_registry_entry.model_run_id != self.champion_model_run_id
        ):
            raise ValidationError("Champion registry entry must reference the champion model run.")

    def __str__(self) -> str:
        return (
            f"{self.champion_model_run.model_version} vs "
            f"{self.challenger_model_version} [{self.benchmark_status}]"
        )


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

    DELIVERY_KIND_LIVE = "LIVE"
    DELIVERY_KIND_SIMULATED = "SIMULATED"
    DELIVERY_KIND_QUEUE_ONLY = "QUEUE_ONLY"
    DELIVERY_KIND_CHOICES = [
        (DELIVERY_KIND_LIVE, "Live provider"),
        (DELIVERY_KIND_SIMULATED, "Simulated"),
        (DELIVERY_KIND_QUEUE_ONLY, "Queue only"),
    ]

    PROVIDER_ACCEPTANCE_PENDING = "pending"
    PROVIDER_ACCEPTANCE_ACCEPTED = "accepted"
    PROVIDER_ACCEPTANCE_REJECTED = "rejected"
    PROVIDER_ACCEPTANCE_SIMULATED = "simulated"
    PROVIDER_ACCEPTANCE_NOT_APPLICABLE = "not_applicable"
    PROVIDER_ACCEPTANCE_CHOICES = [
        (PROVIDER_ACCEPTANCE_PENDING, "Pending"),
        (PROVIDER_ACCEPTANCE_ACCEPTED, "Accepted"),
        (PROVIDER_ACCEPTANCE_REJECTED, "Rejected"),
        (PROVIDER_ACCEPTANCE_SIMULATED, "Simulated"),
        (PROVIDER_ACCEPTANCE_NOT_APPLICABLE, "Not applicable"),
    ]

    PROVIDER_DELIVERY_PENDING = "pending"
    PROVIDER_DELIVERY_DELIVERED = "delivered"
    PROVIDER_DELIVERY_FAILED = "failed"
    PROVIDER_DELIVERY_SIMULATED = "simulated"
    PROVIDER_DELIVERY_UNKNOWN = "unknown"
    PROVIDER_DELIVERY_CHOICES = [
        (PROVIDER_DELIVERY_PENDING, "Pending"),
        (PROVIDER_DELIVERY_DELIVERED, "Delivered"),
        (PROVIDER_DELIVERY_FAILED, "Failed"),
        (PROVIDER_DELIVERY_SIMULATED, "Simulated"),
        (PROVIDER_DELIVERY_UNKNOWN, "Unknown"),
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
    template = models.ForeignKey(
        "risk.MessageTemplate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="alerts",
    )
    template_key = models.CharField(max_length=120, blank=True)
    template_version = models.PositiveIntegerField(null=True, blank=True)
    requested_language = models.CharField(max_length=20, default=DEFAULT_CHV_LANGUAGE)
    resolved_language = models.CharField(
        max_length=20,
        choices=SUPPORTED_CHV_LANGUAGE_CHOICES,
        default=DEFAULT_CHV_LANGUAGE,
    )
    fallback_used = models.BooleanField(default=False)
    message = models.TextField()
    governance_metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    delivery_backend = models.CharField(max_length=50, blank=True)
    delivery_kind = models.CharField(
        max_length=20,
        choices=DELIVERY_KIND_CHOICES,
        default=DELIVERY_KIND_LIVE,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    guided_request_metadata = models.JSONField(default=dict, blank=True)
    provider_request_metadata = models.JSONField(default=dict, blank=True)
    provider_response_metadata = models.JSONField(default=dict, blank=True)
    provider_acceptance_status = models.CharField(
        max_length=24,
        choices=PROVIDER_ACCEPTANCE_CHOICES,
        default=PROVIDER_ACCEPTANCE_PENDING,
    )
    provider_accepted_at = models.DateTimeField(null=True, blank=True)
    provider_delivery_status = models.CharField(
        max_length=24,
        choices=PROVIDER_DELIVERY_CHOICES,
        default=PROVIDER_DELIVERY_PENDING,
    )
    provider_delivered_at = models.DateTimeField(null=True, blank=True)
    last_error_classification = models.CharField(max_length=80, blank=True)
    callback_payload_hash = models.CharField(max_length=64, blank=True)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, null=True)
    last_attempted_at = models.DateTimeField(null=True, blank=True)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    external_id = models.CharField(max_length=120, blank=True)
    provider_message_id = models.CharField(max_length=120, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["template_key", "template_version"], name="risk_alert_tpl_idx"),
            models.Index(fields=["resolved_language", "created_at"], name="risk_alert_reslang_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(resolved_language__in=SUPPORTED_CHV_LANGUAGES),
                name="risk_alert_reslang_supported",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.idempotency_key is None:
            self.idempotency_key = uuid.uuid4()
        self.requested_language = normalize_language_code(self.requested_language) or DEFAULT_CHV_LANGUAGE
        self.resolved_language = supported_language_or_default(self.resolved_language or self.requested_language)
        self.fallback_used = bool(self.fallback_used or self.requested_language != self.resolved_language)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.channel} to {self.recipient} [{self.status}]"


class AlertDeliveryEvent(models.Model):
    alert = models.ForeignKey(
        Alert,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivery_events",
    )
    provider = models.CharField(max_length=50)
    provider_event_id = models.CharField(max_length=160, blank=True)
    provider_message_id = models.CharField(max_length=120, blank=True)
    event_key = models.CharField(max_length=128, unique=True)
    status = models.CharField(max_length=40)
    payload_hash = models.CharField(max_length=64)
    sanitized_payload = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-received_at", "-id"]
        indexes = [
            models.Index(fields=["provider", "provider_message_id"], name="risk_alertde_msg_idx"),
            models.Index(fields=["provider", "provider_event_id"], name="risk_alertde_evt_idx"),
            models.Index(fields=["status", "received_at"], name="risk_alertde_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.provider} {self.provider_message_id or self.provider_event_id} [{self.status}]"


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


class UssdMenuVersion(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_APPROVED = "APPROVED"
    STATUS_RETIRED = "RETIRED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_RETIRED, "Retired"),
    ]

    TRANSLATION_DRAFT = "draft"
    TRANSLATION_NEEDS_REVIEW = "needs_translation_review"
    TRANSLATION_APPROVED = "approved"
    TRANSLATION_RETIRED = "retired"
    TRANSLATION_BLOCKED_SOURCE_RETIRED = "blocked_source_retired"
    TRANSLATION_STATUS_CHOICES = [
        (TRANSLATION_DRAFT, "Draft"),
        (TRANSLATION_NEEDS_REVIEW, "Needs translation review"),
        (TRANSLATION_APPROVED, "Approved"),
        (TRANSLATION_RETIRED, "Retired"),
        (TRANSLATION_BLOCKED_SOURCE_RETIRED, "Blocked because source is retired"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    menu_key = models.CharField(max_length=120, default="cholera_health_menu")
    version_label = models.CharField(max_length=80)
    language = models.CharField(max_length=20, choices=SUPPORTED_CHV_LANGUAGE_CHOICES, default=DEFAULT_CHV_LANGUAGE)
    title = models.CharField(max_length=160)
    menu_tree = models.JSONField(default=dict, blank=True)
    safe_fallback_copy = models.TextField(default="END Invalid option. Please try again.")
    session_outcome_taxonomy = models.JSONField(default=dict, blank=True)
    approval_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ussd_menu_versions_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)
    translation_status = models.CharField(
        max_length=40,
        choices=TRANSLATION_STATUS_CHOICES,
        default=TRANSLATION_DRAFT,
    )
    source_menu_version = models.ForeignKey(
        "risk.UssdMenuVersion",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="translation_variants",
    )
    translation_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ussd_menu_translation_reviews",
    )
    translation_reviewed_at = models.DateTimeField(null=True, blank=True)
    translation_review_notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=False)
    lineage_metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ussd_menu_versions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["menu_key", "language", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["menu_key", "language", "version_label"],
                name="risk_ussdmenu_langver_uniq",
            ),
            models.UniqueConstraint(
                fields=["menu_key", "language"],
                condition=models.Q(is_active=True),
                name="risk_ussdmenu_one_active_lang",
            ),
            models.CheckConstraint(
                check=models.Q(language__in=SUPPORTED_CHV_LANGUAGES),
                name="risk_ussdmenu_lang_supported",
            ),
        ]
        indexes = [
            models.Index(fields=["menu_key", "language", "is_active"], name="risk_ussdmenu_active_idx"),
            models.Index(fields=["approval_status", "retired_at"], name="risk_ussdmenu_status_idx"),
            models.Index(fields=["source_menu_version", "translation_status"], name="risk_ussdmenu_src_tr_idx"),
        ]

    def clean(self):
        errors = {}
        normalized_language = normalize_language_code(self.language) or DEFAULT_CHV_LANGUAGE
        if self.is_active and self.approval_status != self.STATUS_APPROVED:
            errors["is_active"] = ["Only approved USSD menu versions can be active."]
        if self.approval_status == self.STATUS_APPROVED and self.approved_at is None:
            errors["approved_at"] = ["Approved USSD menu versions require an approval timestamp."]
        if self.retired_at is not None and self.approval_status != self.STATUS_RETIRED:
            errors["approval_status"] = ["USSD menu versions with retired_at must use retired status."]
        if normalized_language not in SUPPORTED_CHV_LANGUAGES:
            errors["language"] = ["USSD menu language must be one of: en, sw, luo."]
        if normalized_language == DEFAULT_CHV_LANGUAGE and self.source_menu_version_id:
            errors["source_menu_version"] = ["English USSD source menus must not link to another source menu."]

        if self.approval_status == self.STATUS_APPROVED or self.is_active:
            try:
                _validate_ussd_menu_tree_copy_budget(self.menu_tree or {})
            except ValidationError as exc:
                errors.setdefault("menu_tree", []).extend(exc.messages)
            try:
                _validate_ussd_response_copy_budget(self.safe_fallback_copy, required_prefix="END")
            except ValidationError as exc:
                errors.setdefault("safe_fallback_copy", []).extend(exc.messages)

        source_menu_version = self.source_menu_version
        if normalized_language != DEFAULT_CHV_LANGUAGE and source_menu_version is not None:
            if source_menu_version.language != DEFAULT_CHV_LANGUAGE:
                errors["source_menu_version"] = ["Translated USSD menus must link to an English source menu."]
            elif source_menu_version.menu_key != self.menu_key:
                errors["source_menu_version"] = ["Translated USSD menus must link to an English source with the same menu key."]
            elif _ussd_menu_tree_structure_signature(source_menu_version.menu_tree or {}) != _ussd_menu_tree_structure_signature(
                self.menu_tree or {}
            ):
                errors.setdefault("menu_tree", []).append(
                    "Translated USSD menus must preserve English source routes and node keys."
                )

        translation_review_required = (
            normalized_language != DEFAULT_CHV_LANGUAGE
            and (
                self.translation_status == self.TRANSLATION_APPROVED
                or self.approval_status == self.STATUS_APPROVED
                or self.is_active
            )
        )
        if translation_review_required:
            if source_menu_version is None:
                errors["source_menu_version"] = ["Translated USSD menus require an English source before approval."]
            elif source_menu_version.approval_status != self.STATUS_APPROVED or source_menu_version.retired_at is not None:
                errors["source_menu_version"] = ["Translated USSD menus cannot be approved without an active approved English source."]
            if self.translation_status != self.TRANSLATION_APPROVED:
                errors["translation_status"] = ["Translated USSD menus require approved translation status before use."]
            if self.translation_reviewed_at is None:
                errors["translation_reviewed_at"] = ["Approved translated USSD menus require translation review metadata."]
            if not self.safe_fallback_copy.strip():
                errors["safe_fallback_copy"] = ["Translated USSD menus require safe fallback copy."]
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.menu_key = self.menu_key.strip() or "cholera_health_menu"
        self.version_label = self.version_label.strip()
        self.language = normalize_language_code(self.language) or DEFAULT_CHV_LANGUAGE
        self.title = self.title.strip()
        self.translation_review_notes = self.translation_review_notes.strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.menu_key} {self.version_label} ({self.language})"


class UssdSessionLog(models.Model):
    OUTCOME_STARTED = "STARTED"
    OUTCOME_IN_PROGRESS = "IN_PROGRESS"
    OUTCOME_COMPLETED = "COMPLETED"
    OUTCOME_INVALID_INPUT = "INVALID_INPUT"
    OUTCOME_ABANDONED_INFERRED = "ABANDONED_INFERRED"
    OUTCOME_SAFE_FALLBACK = "SAFE_FALLBACK"
    OUTCOME_CHOICES = [
        (OUTCOME_STARTED, "Started"),
        (OUTCOME_IN_PROGRESS, "In progress"),
        (OUTCOME_COMPLETED, "Completed"),
        (OUTCOME_INVALID_INPUT, "Invalid input"),
        (OUTCOME_ABANDONED_INFERRED, "Abandoned inferred"),
        (OUTCOME_SAFE_FALLBACK, "Safe fallback"),
    ]

    session_id = models.CharField(max_length=120, db_index=True)
    phone_number = models.CharField(max_length=20, blank=True)
    service_code = models.CharField(max_length=40, blank=True)
    text = models.TextField(blank=True)
    response_text = models.TextField(blank=True)
    ward = models.ForeignKey(Ward, on_delete=models.SET_NULL, null=True, blank=True)
    menu_version = models.ForeignKey(
        UssdMenuVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="session_logs",
    )
    menu_key = models.CharField(max_length=120, default="cholera_health_menu")
    menu_version_label = models.CharField(max_length=80, blank=True)
    language = models.CharField(max_length=20, choices=SUPPORTED_CHV_LANGUAGE_CHOICES, default=DEFAULT_CHV_LANGUAGE)
    requested_language = models.CharField(max_length=20, default=DEFAULT_CHV_LANGUAGE)
    resolved_language = models.CharField(
        max_length=20,
        choices=SUPPORTED_CHV_LANGUAGE_CHOICES,
        default=DEFAULT_CHV_LANGUAGE,
    )
    fallback_used = models.BooleanField(default=False)
    menu_level = models.CharField(max_length=50, blank=True)
    session_outcome = models.CharField(max_length=40, choices=OUTCOME_CHOICES, default=OUTCOME_IN_PROGRESS)
    invalid_option = models.BooleanField(default=False)
    abandonment_reason = models.CharField(max_length=160, blank=True)
    is_terminal = models.BooleanField(default=False)
    governance_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session_id", "created_at"]),
            models.Index(fields=["menu_key", "menu_version_label", "language"], name="risk_ussdlog_menu_idx"),
            models.Index(fields=["session_outcome", "created_at"], name="risk_ussdlog_outcome_idx"),
            models.Index(fields=["invalid_option", "created_at"], name="risk_ussdlog_invalid_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(language__in=SUPPORTED_CHV_LANGUAGES),
                name="risk_ussdlog_lang_supported",
            ),
            models.CheckConstraint(
                check=models.Q(resolved_language__in=SUPPORTED_CHV_LANGUAGES),
                name="risk_ussdlog_reslang_supported",
            ),
        ]

    def save(self, *args, **kwargs):
        self.language = supported_language_or_default(self.language)
        self.requested_language = normalize_language_code(self.requested_language) or DEFAULT_CHV_LANGUAGE
        self.resolved_language = supported_language_or_default(self.resolved_language or self.language)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"USSD {self.session_id} {self.phone_number}"


class SyncQueue(models.Model):
    CONTRACT_VERSION_DEFAULT = "chv-offline-v1"

    UPLOAD_SYMPTOM_TRIAGE = "symptom_triage"
    UPLOAD_SUSPECTED_CASE_SIGNAL = "suspected_case_signal"
    UPLOAD_PREVENTION_VISIT = "prevention_visit"
    UPLOAD_TASK_ACK = "task_ack"
    UPLOAD_ALERT_ACK = "alert_ack"
    UPLOAD_CHOICES = [
        (UPLOAD_SYMPTOM_TRIAGE, "Symptom triage"),
        (UPLOAD_SUSPECTED_CASE_SIGNAL, "Suspected case signal"),
        (UPLOAD_PREVENTION_VISIT, "Household prevention visit"),
        (UPLOAD_TASK_ACK, "Task acknowledgement"),
        (UPLOAD_ALERT_ACK, "Alert acknowledgement"),
    ]

    STATUS_PENDING = "PENDING"
    STATUS_PROCESSED = "PROCESSED"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSED, "Processed"),
        (STATUS_FAILED, "Failed"),
    ]

    CONFLICT_NONE = "NONE"
    CONFLICT_REPLAYED = "REPLAYED"
    CONFLICT_SCOPE_MISMATCH = "SCOPE_MISMATCH"
    CONFLICT_STALE_BUNDLE = "STALE_BUNDLE"
    CONFLICT_UNSUPPORTED_UPLOAD = "UNSUPPORTED_UPLOAD"
    CONFLICT_CHOICES = [
        (CONFLICT_NONE, "None"),
        (CONFLICT_REPLAYED, "Replayed"),
        (CONFLICT_SCOPE_MISMATCH, "Scope mismatch"),
        (CONFLICT_STALE_BUNDLE, "Stale bundle"),
        (CONFLICT_UNSUPPORTED_UPLOAD, "Unsupported upload"),
    ]

    source_device_id = models.CharField(max_length=120, blank=True)
    device_registration = models.ForeignKey(
        "risk.CHVDeviceRegistration",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sync_queue_items",
    )
    contract_version = models.CharField(max_length=64, default=CONTRACT_VERSION_DEFAULT)
    upload_type = models.CharField(max_length=40, choices=UPLOAD_CHOICES, default=UPLOAD_SYMPTOM_TRIAGE)
    client_submission_id = models.CharField(max_length=120)
    idempotency_key = models.CharField(max_length=160, blank=True)
    download_bundle_version = models.CharField(max_length=96, blank=True)
    recorded_at = models.DateTimeField(null=True, blank=True)
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
    conflict_state = models.CharField(max_length=32, choices=CONFLICT_CHOICES, default=CONFLICT_NONE)
    server_receipt = models.JSONField(default=dict, blank=True)
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
            models.UniqueConstraint(
                fields=["source_device_id", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="unique_sync_idempotency_per_device",
            ),
        ]
        indexes = [
            models.Index(fields=["device_registration", "created_at"], name="risk_sync_device_idx"),
            models.Index(fields=["upload_type", "status"], name="risk_sync_upload_status_idx"),
            models.Index(fields=["contract_version", "created_at"], name="risk_sync_contract_idx"),
        ]

    def __str__(self) -> str:
        return f"SyncQueue {self.id} [{self.status}]"


class CHVOfflineRejectedSubmissionAudit(models.Model):
    STAGE_ENVELOPE_VALIDATION = "ENVELOPE_VALIDATION"
    STAGE_PAYLOAD_SCHEMA = "PAYLOAD_SCHEMA"
    STAGE_PII_MINIMIZATION = "PII_MINIMIZATION"
    STAGE_CONTRACT_VERSION = "CONTRACT_VERSION"
    STAGE_WARD_SCOPE = "WARD_SCOPE"
    STAGE_DEVICE_REGISTRATION = "DEVICE_REGISTRATION"
    STAGE_CHOICES = [
        (STAGE_ENVELOPE_VALIDATION, "Envelope validation"),
        (STAGE_PAYLOAD_SCHEMA, "Payload schema"),
        (STAGE_PII_MINIMIZATION, "PII minimization"),
        (STAGE_CONTRACT_VERSION, "Contract version"),
        (STAGE_WARD_SCOPE, "Ward scope"),
        (STAGE_DEVICE_REGISTRATION, "Device registration"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chv_offline_rejected_submission_audits",
    )
    ward = models.ForeignKey(
        Ward,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chv_offline_rejected_submission_audits",
    )
    device_registration = models.ForeignKey(
        "risk.CHVDeviceRegistration",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_submission_audits",
    )
    source_device_id = models.CharField(max_length=120, blank=True)
    client_submission_id = models.CharField(max_length=120, blank=True)
    idempotency_key = models.CharField(max_length=160, blank=True)
    upload_type = models.CharField(max_length=40, blank=True)
    contract_version = models.CharField(max_length=64, blank=True)
    rejection_stage = models.CharField(
        max_length=40,
        choices=STAGE_CHOICES,
        default=STAGE_ENVELOPE_VALIDATION,
    )
    error_code = models.CharField(max_length=80, blank=True)
    safe_error_summary = models.TextField(blank=True)
    field_paths = models.JSONField(default=list, blank=True)
    status_code = models.PositiveSmallIntegerField(default=400)
    request_body_hmac = models.CharField(max_length=64, blank=True)
    request_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["ward", "created_at"], name="risk_chvrej_ward_created_idx"),
            models.Index(fields=["user", "created_at"], name="risk_chvrej_user_created_idx"),
            models.Index(fields=["source_device_id", "created_at"], name="risk_chvrej_device_created_idx"),
            models.Index(fields=["rejection_stage", "created_at"], name="risk_chvrej_stage_created_idx"),
            models.Index(fields=["request_body_hmac"], name="risk_chvrej_hmac_idx"),
        ]

    def __str__(self) -> str:
        return f"CHV offline rejection {self.public_id} [{self.rejection_stage}]"


class SystemControlState(models.Model):
    KEY_ALERT_DELIVERY_PAUSE = "ALERT_DELIVERY_PAUSE"
    KEY_WARD_RISK_DECISION_POLICY = "WARD_RISK_DECISION_POLICY"
    CONTROL_KEY_CHOICES = [
        (KEY_ALERT_DELIVERY_PAUSE, "Alert delivery pause"),
        (KEY_WARD_RISK_DECISION_POLICY, "Ward risk decision policy"),
    ]

    control_key = models.CharField(max_length=80, choices=CONTROL_KEY_CHOICES, unique=True)
    is_active = models.BooleanField(default=False)
    reason = models.TextField(blank=True)
    active_until = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="system_control_updates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["control_key"]
        indexes = [
            models.Index(fields=["control_key", "is_active"], name="risk_system_control_key_idx"),
            models.Index(fields=["active_until"], name="risk_system_active_until_idx"),
        ]

    def is_currently_active(self) -> bool:
        if not self.is_active:
            return False
        if self.active_until is None:
            return True
        return self.active_until > timezone.now()

    def __str__(self) -> str:
        state = "active" if self.is_currently_active() else "inactive"
        return f"{self.control_key} [{state}]"


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


class WardSpatialRelationshipType(models.TextChoices):
    ADJACENT = "adjacent", "Adjacent"
    NEARBY = "nearby", "Nearby"
    UPSTREAM = "upstream", "Upstream"
    SAME_FACILITY_CATCHMENT = "same_facility_catchment", "Same facility catchment"
    MANUAL_PUBLIC_HEALTH_LINK = "manual_public_health_link", "Manual public health link"


class WardSpatialRelationshipSource(models.TextChoices):
    DERIVED_GEOMETRY = "derived_geometry", "Derived geometry"
    DERIVED_FACILITY_CATCHMENT = "derived_facility_catchment", "Derived facility catchment"
    MANUAL_PUBLIC_HEALTH = "manual_public_health", "Manual public health"


class WardSpatialRelationship(models.Model):
    source_ward = models.ForeignKey(
        Ward,
        on_delete=models.PROTECT,
        related_name="outgoing_spatial_relationships",
    )
    target_ward = models.ForeignKey(
        Ward,
        on_delete=models.PROTECT,
        related_name="incoming_spatial_relationships",
    )
    relationship_type = models.CharField(
        max_length=40,
        choices=WardSpatialRelationshipType.choices,
        default=WardSpatialRelationshipType.ADJACENT,
    )
    geometry_dataset_version = models.ForeignKey(
        WardGeometryDatasetVersion,
        on_delete=models.PROTECT,
        related_name="spatial_relationships",
    )
    shared_boundary_length = models.FloatField(null=True, blank=True)
    centroid_distance = models.FloatField(null=True, blank=True)
    distance_unit = models.CharField(max_length=40, default="source_crs_degrees")
    confidence = models.FloatField(default=1.0)
    generation_method = models.CharField(
        max_length=40,
        choices=WardSpatialRelationshipSource.choices,
        default=WardSpatialRelationshipSource.DERIVED_GEOMETRY,
    )
    generated_at = models.DateTimeField(default=timezone.now)
    lineage_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_ward__county", "source_ward__name", "relationship_type", "target_ward__name"]
        indexes = [
            models.Index(fields=["source_ward", "relationship_type"], name="risk_sprel_src_type_idx"),
            models.Index(fields=["target_ward", "relationship_type"], name="risk_sprel_tgt_type_idx"),
            models.Index(fields=["geometry_dataset_version", "generation_method"], name="risk_sprel_geom_src_idx"),
            models.Index(fields=["relationship_type", "generated_at"], name="risk_sprel_type_gen_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "source_ward",
                    "target_ward",
                    "relationship_type",
                    "geometry_dataset_version",
                    "generation_method",
                ],
                name="risk_sprel_unique_edge",
            ),
            models.CheckConstraint(
                check=~models.Q(source_ward_id=models.F("target_ward_id")),
                name="risk_sprel_no_self_edge",
            ),
            models.CheckConstraint(
                check=models.Q(confidence__gte=0.0) & models.Q(confidence__lte=1.0),
                name="risk_sprel_conf_0_1",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_ward.name} -> {self.target_ward.name} [{self.relationship_type}]"


class FacilityCatchmentMethod(models.TextChoices):
    PRIMARY_WARD_ONLY = "primary_ward_only", "Primary ward only"
    SPATIAL_GRAPH_ADJACENT_WARDS = "spatial_graph_adjacent_wards", "Spatial graph adjacent wards"
    DISTANCE_THRESHOLD = "distance_threshold", "Distance threshold"
    SOURCE_CATCHMENT_RECORD = "source_catchment_record", "Source catchment record"
    EXTERNALLY_VERIFIED = "externally_verified", "Externally verified"


class FacilityCatchmentSourceKind(models.TextChoices):
    APPROXIMATED = "approximated", "Approximated"
    EXTERNALLY_VERIFIED = "externally_verified", "Externally verified"
    MANUAL_OVERRIDE = "manual_override", "Manual override"


class FacilityCatchment(models.Model):
    facility = models.ForeignKey(
        HealthFacility,
        on_delete=models.PROTECT,
        related_name="facility_catchments",
    )
    primary_ward = models.ForeignKey(
        Ward,
        on_delete=models.PROTECT,
        related_name="primary_facility_catchments",
    )
    covered_wards = models.ManyToManyField(Ward, related_name="facility_catchments", blank=True)
    geometry_dataset_version = models.ForeignKey(
        WardGeometryDatasetVersion,
        on_delete=models.PROTECT,
        related_name="facility_catchments",
    )
    catchment_method = models.CharField(
        max_length=60,
        choices=FacilityCatchmentMethod.choices,
        default=FacilityCatchmentMethod.PRIMARY_WARD_ONLY,
    )
    source_kind = models.CharField(
        max_length=40,
        choices=FacilityCatchmentSourceKind.choices,
        default=FacilityCatchmentSourceKind.APPROXIMATED,
    )
    distance_threshold = models.FloatField(null=True, blank=True)
    distance_unit = models.CharField(max_length=40, default="source_crs_degrees")
    population_estimate = models.FloatField(null=True, blank=True)
    confidence = models.FloatField(default=0.5)
    is_approximate = models.BooleanField(default=True)
    generated_at = models.DateTimeField(default=timezone.now)
    lineage_metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["facility__ward__name", "facility__name", "-generated_at"]
        indexes = [
            models.Index(fields=["facility", "generated_at"], name="risk_fcatch_fac_gen_idx"),
            models.Index(fields=["primary_ward", "catchment_method"], name="risk_fcatch_ward_method_idx"),
            models.Index(fields=["geometry_dataset_version", "source_kind"], name="risk_fcatch_geom_src_idx"),
            models.Index(fields=["is_approximate", "generated_at"], name="risk_fcatch_approx_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["facility", "geometry_dataset_version", "catchment_method", "source_kind"],
                name="risk_fcatch_unique_method",
            ),
            models.CheckConstraint(
                check=models.Q(confidence__gte=0.0) & models.Q(confidence__lte=1.0),
                name="risk_fcatch_conf_0_1",
            ),
            models.CheckConstraint(
                check=models.Q(distance_threshold__isnull=True) | models.Q(distance_threshold__gte=0.0),
                name="risk_fcatch_distance_nonneg",
            ),
        ]

    def __str__(self) -> str:
        label = "approximate" if self.is_approximate else "verified"
        return f"{self.facility.name} catchment [{label}]"


class DashboardNotification(models.Model):
    TYPE_WARD_RISK_HIGH = "WARD_RISK_HIGH"
    TYPE_ALERT_FAILED = "ALERT_FAILED"
    TYPE_ALERT_RETRY_PENDING = "ALERT_RETRY_PENDING"
    TYPE_FEED_STALE = "FEED_STALE"
    TYPE_CHV_COVERAGE_REQUEST_STATUS = "CHV_COVERAGE_REQUEST_STATUS"
    TYPE_OPERATIONAL_KPI_THRESHOLD = "OPERATIONAL_KPI_THRESHOLD"
    TYPE_SESSION_REPLAY_DETECTED = "SESSION_REPLAY_DETECTED"
    TYPE_STEP_UP_FAILURE_SPIKE = "STEP_UP_FAILURE_SPIKE"
    TYPE_SESSION_CONTEXT_CHANGED = "SESSION_CONTEXT_CHANGED"
    TYPE_ADMIN_NEW_DEVICE = "ADMIN_NEW_DEVICE"
    TYPE_CHOICES = [
        (TYPE_WARD_RISK_HIGH, "Ward Risk High"),
        (TYPE_ALERT_FAILED, "Alert Failed"),
        (TYPE_ALERT_RETRY_PENDING, "Alert Retry Pending"),
        (TYPE_FEED_STALE, "Feed Stale"),
        (TYPE_CHV_COVERAGE_REQUEST_STATUS, "CHV Coverage Request Status"),
        (TYPE_OPERATIONAL_KPI_THRESHOLD, "Operational KPI Threshold"),
        (TYPE_SESSION_REPLAY_DETECTED, "Session Replay Detected"),
        (TYPE_STEP_UP_FAILURE_SPIKE, "Step-Up Failure Spike"),
        (TYPE_SESSION_CONTEXT_CHANGED, "Session Context Changed"),
        (TYPE_ADMIN_NEW_DEVICE, "Admin New Device"),
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


class PreparednessAction(models.Model):
    ACTION_CHV_FOLLOW_UP = "chv_follow_up"
    ACTION_HOUSEHOLD_PREVENTION_MESSAGE = "household_prevention_message"
    ACTION_FACILITY_ORS_REVIEW = "facility_ors_review"
    ACTION_FACILITY_STAFFING_REVIEW = "facility_staffing_review"
    ACTION_COUNTY_ESCALATION = "county_escalation"
    ACTION_WATER_TREATMENT_DISTRIBUTION = "water_treatment_distribution"
    ACTION_SURVEILLANCE_FOLLOW_UP = "surveillance_follow_up"
    ACTION_FIELD_VERIFICATION = "field_verification"
    ACTION_TYPE_CHOICES = [
        (ACTION_CHV_FOLLOW_UP, "CHV follow-up"),
        (ACTION_HOUSEHOLD_PREVENTION_MESSAGE, "Household prevention message"),
        (ACTION_FACILITY_ORS_REVIEW, "Facility ORS review"),
        (ACTION_FACILITY_STAFFING_REVIEW, "Facility staffing review"),
        (ACTION_COUNTY_ESCALATION, "County escalation"),
        (ACTION_WATER_TREATMENT_DISTRIBUTION, "Water treatment distribution"),
        (ACTION_SURVEILLANCE_FOLLOW_UP, "Surveillance follow-up"),
        (ACTION_FIELD_VERIFICATION, "Field verification"),
    ]

    SOURCE_MANUAL = "manual"
    SOURCE_ALERT = "alert"
    SOURCE_ALERT_WORKFLOW = "alert_workflow"
    SOURCE_RISK_SCORE = "risk_score"
    SOURCE_CHV_COVERAGE_REQUEST = "chv_coverage_request"
    SOURCE_FACILITY_READINESS_REVIEW = "facility_readiness_review"
    SOURCE_FACILITY_UPDATE_REQUEST = "facility_update_request"
    SOURCE_FACILITY_ESCALATION = "facility_escalation"
    SOURCE_OUTCOME_FEEDBACK = "outcome_feedback"
    SOURCE_SYSTEM = "system"
    SOURCE_TRIGGER_CHOICES = [
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_ALERT, "Alert"),
        (SOURCE_ALERT_WORKFLOW, "Alert workflow"),
        (SOURCE_RISK_SCORE, "Risk score"),
        (SOURCE_CHV_COVERAGE_REQUEST, "CHV coverage request"),
        (SOURCE_FACILITY_READINESS_REVIEW, "Facility readiness review"),
        (SOURCE_FACILITY_UPDATE_REQUEST, "Facility update request"),
        (SOURCE_FACILITY_ESCALATION, "Facility escalation"),
        (SOURCE_OUTCOME_FEEDBACK, "Outcome feedback"),
        (SOURCE_SYSTEM, "System"),
    ]

    STATUS_DRAFT = "DRAFT"
    STATUS_QUEUED = "QUEUED"
    STATUS_ASSIGNED = "ASSIGNED"
    STATUS_ACKNOWLEDGED = "ACKNOWLEDGED"
    STATUS_IN_PROGRESS = "IN_PROGRESS"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_BLOCKED = "BLOCKED"
    STATUS_CANCELLED = "CANCELLED"
    STATUS_ESCALATED = "ESCALATED"
    STATUS_EXPIRED = "EXPIRED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_QUEUED, "Queued"),
        (STATUS_ASSIGNED, "Assigned"),
        (STATUS_ACKNOWLEDGED, "Acknowledged"),
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_BLOCKED, "Blocked"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_ESCALATED, "Escalated"),
        (STATUS_EXPIRED, "Expired"),
    ]
    ACTIVE_STATUSES = [
        STATUS_DRAFT,
        STATUS_QUEUED,
        STATUS_ASSIGNED,
        STATUS_ACKNOWLEDGED,
        STATUS_IN_PROGRESS,
        STATUS_BLOCKED,
        STATUS_ESCALATED,
    ]
    CLOSED_STATUSES = [STATUS_COMPLETED, STATUS_CANCELLED, STATUS_EXPIRED]

    PRIORITY_LOW = "LOW"
    PRIORITY_MEDIUM = "MEDIUM"
    PRIORITY_HIGH = "HIGH"
    PRIORITY_URGENT = "URGENT"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Low"),
        (PRIORITY_MEDIUM, "Medium"),
        (PRIORITY_HIGH, "High"),
        (PRIORITY_URGENT, "Urgent"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    action_type = models.CharField(max_length=64, choices=ACTION_TYPE_CHOICES)
    source_trigger_type = models.CharField(max_length=64, choices=SOURCE_TRIGGER_CHOICES, default=SOURCE_MANUAL)
    source_trigger_ref = models.CharField(max_length=160, blank=True)
    ward = models.ForeignKey(Ward, on_delete=models.PROTECT, related_name="preparedness_actions")
    facility = models.ForeignKey(
        HealthFacility,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="preparedness_actions",
    )
    chv = models.ForeignKey(
        CHV,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="preparedness_actions",
    )
    alert = models.ForeignKey(
        Alert,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="preparedness_actions",
    )
    alert_workflow = models.ForeignKey(
        AlertWorkflowState,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="preparedness_actions",
    )
    risk_score = models.ForeignKey(
        RiskScore,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preparedness_actions",
    )
    model_run = models.ForeignKey(
        "risk.ModelRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preparedness_actions",
    )
    facility_readiness_review = models.ForeignKey(
        FacilityReadinessReview,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="preparedness_actions",
    )
    facility_update_request = models.ForeignKey(
        FacilityReadinessUpdateRequest,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="preparedness_actions",
    )
    facility_escalation = models.ForeignKey(
        FacilityReadinessEscalation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="preparedness_actions",
    )
    chv_coverage_request = models.ForeignKey(
        "risk.CHVCoverageRequest",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="preparedness_actions",
    )
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default=STATUS_QUEUED)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_MEDIUM)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preparedness_actions_created",
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preparedness_actions_assigned",
    )
    assigned_to_team = models.CharField(max_length=120, blank=True)
    decision_policy_version = models.CharField(max_length=80, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    sla_target_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    escalated_at = models.DateTimeField(null=True, blank=True)
    completion_evidence = models.JSONField(default=dict, blank=True)
    cancellation_reason = models.TextField(blank=True)
    escalation_metadata = models.JSONField(default=dict, blank=True)
    lineage_metadata = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["action_type", "source_trigger_type", "source_trigger_ref"],
                condition=(
                    models.Q(status__in=["DRAFT", "QUEUED", "ASSIGNED", "ACKNOWLEDGED", "IN_PROGRESS", "BLOCKED", "ESCALATED"])
                    & ~models.Q(source_trigger_ref="")
                ),
                name="risk_prepact_src_active_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "due_at"], name="risk_prepact_status_idx"),
            models.Index(fields=["priority", "due_at"], name="risk_prepact_prior_idx"),
            models.Index(fields=["ward", "status"], name="risk_prepact_ward_idx"),
            models.Index(fields=["facility", "status"], name="risk_prepact_fac_idx"),
            models.Index(fields=["assigned_to", "status"], name="risk_prepact_assign_idx"),
            models.Index(fields=["source_trigger_type", "source_trigger_ref"], name="risk_prepact_source_idx"),
        ]

    @property
    def is_active(self) -> bool:
        return self.status in self.ACTIVE_STATUSES

    @property
    def is_overdue(self) -> bool:
        return bool(self.due_at and self.is_active and self.due_at < timezone.now())

    def __str__(self) -> str:
        return f"{self.ward.name} {self.action_type} [{self.status}]"


class PreparednessActionEvent(models.Model):
    EVENT_CREATED = "CREATED"
    EVENT_ASSIGNED = "ASSIGNED"
    EVENT_ACKNOWLEDGED = "ACKNOWLEDGED"
    EVENT_IN_PROGRESS = "IN_PROGRESS"
    EVENT_COMPLETED = "COMPLETED"
    EVENT_BLOCKED = "BLOCKED"
    EVENT_CANCELLED = "CANCELLED"
    EVENT_ESCALATED = "ESCALATED"
    EVENT_EXPIRED = "EXPIRED"
    EVENT_STATUS_CHANGED = "STATUS_CHANGED"
    EVENT_DUE_DATE_CHANGED = "DUE_DATE_CHANGED"
    EVENT_COMPLETION_EVIDENCE_ADDED = "COMPLETION_EVIDENCE_ADDED"
    EVENT_COMMENT = "COMMENT"
    EVENT_CHOICES = [
        (EVENT_CREATED, "Created"),
        (EVENT_ASSIGNED, "Assigned"),
        (EVENT_ACKNOWLEDGED, "Acknowledged"),
        (EVENT_IN_PROGRESS, "In Progress"),
        (EVENT_COMPLETED, "Completed"),
        (EVENT_BLOCKED, "Blocked"),
        (EVENT_CANCELLED, "Cancelled"),
        (EVENT_ESCALATED, "Escalated"),
        (EVENT_EXPIRED, "Expired"),
        (EVENT_STATUS_CHANGED, "Status Changed"),
        (EVENT_DUE_DATE_CHANGED, "Due Date Changed"),
        (EVENT_COMPLETION_EVIDENCE_ADDED, "Completion Evidence Added"),
        (EVENT_COMMENT, "Comment"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    preparedness_action = models.ForeignKey(
        PreparednessAction,
        on_delete=models.PROTECT,
        related_name="events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="preparedness_action_events",
    )
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    old_status = models.CharField(max_length=24, blank=True)
    new_status = models.CharField(max_length=24, blank=True)
    detail = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["preparedness_action", "created_at"], name="risk_prepevt_action_idx"),
            models.Index(fields=["event_type", "created_at"], name="risk_prepevt_type_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.preparedness_action.public_id} {self.event_type}"


class OperationalMetricDefinition(models.Model):
    GROUP_ALERT_DELIVERY = "alert_delivery"
    GROUP_TRIGGER_ACTIVATION = "trigger_activation"
    GROUP_ACTION_COMPLETION = "action_completion"
    GROUP_CHV_ADOPTION = "chv_adoption"
    GROUP_FACILITY_PREPAREDNESS = "facility_preparedness"
    GROUP_USSD_COMPLETION = "ussd_completion"
    GROUP_HOUSEHOLD_REACH = "household_reach"
    GROUP_OUTCOME_FEEDBACK = "outcome_feedback"
    GROUP_SOURCE_DATA_HEALTH = "source_data_health"
    GROUP_CHOICES = [
        (GROUP_ALERT_DELIVERY, "Alert delivery"),
        (GROUP_TRIGGER_ACTIVATION, "Trigger activation"),
        (GROUP_ACTION_COMPLETION, "Action completion"),
        (GROUP_CHV_ADOPTION, "CHV adoption"),
        (GROUP_FACILITY_PREPAREDNESS, "Facility preparedness"),
        (GROUP_USSD_COMPLETION, "USSD completion"),
        (GROUP_HOUSEHOLD_REACH, "Household reach"),
        (GROUP_OUTCOME_FEEDBACK, "Outcome feedback"),
        (GROUP_SOURCE_DATA_HEALTH, "Source data health"),
    ]

    FAMILY_OPERATIONAL = "OPERATIONAL"
    FAMILY_MODEL = "MODEL"
    FAMILY_CHOICES = [
        (FAMILY_OPERATIONAL, "Operational KPI"),
        (FAMILY_MODEL, "Model performance metric"),
    ]

    VALUE_COUNT = "count"
    VALUE_PERCENT = "percent"
    VALUE_RATE = "rate"
    VALUE_DURATION_SECONDS = "duration_seconds"
    VALUE_RATIO = "ratio"
    VALUE_CHOICES = [
        (VALUE_COUNT, "Count"),
        (VALUE_PERCENT, "Percent"),
        (VALUE_RATE, "Rate"),
        (VALUE_DURATION_SECONDS, "Duration seconds"),
        (VALUE_RATIO, "Ratio"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    metric_key = models.SlugField(max_length=120)
    version = models.CharField(max_length=40, default="v1")
    display_name = models.CharField(max_length=180)
    description = models.TextField()
    metric_group = models.CharField(max_length=40, choices=GROUP_CHOICES)
    metric_family = models.CharField(max_length=20, choices=FAMILY_CHOICES, default=FAMILY_OPERATIONAL)
    value_type = models.CharField(max_length=32, choices=VALUE_CHOICES)
    value_unit = models.CharField(max_length=40, blank=True)
    owner = models.CharField(max_length=120)
    formula = models.TextField()
    window = models.CharField(max_length=80)
    source_model = models.CharField(max_length=160)
    source_models = models.JSONField(default=list, blank=True)
    allowed_dimensions = models.JSONField(default=list, blank=True)
    interpretation = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    effective_from = models.DateTimeField(default=timezone.now)
    effective_to = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["metric_group", "metric_key", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["metric_key", "version"], name="risk_opsdef_key_ver_uniq"),
            models.UniqueConstraint(
                fields=["metric_key"],
                condition=models.Q(is_active=True),
                name="risk_opsdef_active_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["metric_group", "is_active"], name="risk_opsdef_group_idx"),
            models.Index(fields=["metric_family", "is_active"], name="risk_opsdef_family_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.metric_key}:{self.version}"


class OperationalMetricDimension(models.Model):
    VALUE_DATE = "date"
    VALUE_TEXT = "text"
    VALUE_ENUM = "enum"
    VALUE_FOREIGN_KEY = "foreign_key"
    VALUE_CHOICES = [
        (VALUE_DATE, "Date"),
        (VALUE_TEXT, "Text"),
        (VALUE_ENUM, "Enum"),
        (VALUE_FOREIGN_KEY, "Foreign key"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    dimension_key = models.SlugField(max_length=80, unique=True)
    display_name = models.CharField(max_length=120)
    description = models.TextField()
    value_type = models.CharField(max_length=32, choices=VALUE_CHOICES)
    source_model = models.CharField(max_length=160, blank=True)
    allowed_values = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["dimension_key"]
        indexes = [
            models.Index(fields=["is_active", "dimension_key"], name="risk_opsdim_active_idx"),
        ]

    def __str__(self) -> str:
        return self.dimension_key


class OperationalMetricSnapshot(models.Model):
    GRAIN_DAILY = "DAILY"
    GRAIN_WEEKLY = "WEEKLY"
    GRAIN_MONTHLY = "MONTHLY"
    GRAIN_ROLLING = "ROLLING"
    GRAIN_CUSTOM = "CUSTOM"
    GRAIN_CHOICES = [
        (GRAIN_DAILY, "Daily"),
        (GRAIN_WEEKLY, "Weekly"),
        (GRAIN_MONTHLY, "Monthly"),
        (GRAIN_ROLLING, "Rolling"),
        (GRAIN_CUSTOM, "Custom"),
    ]

    STATUS_COMPLETE = "COMPLETE"
    STATUS_PARTIAL = "PARTIAL"
    STATUS_NO_SOURCE = "NO_SOURCE"
    STATUS_STALE = "STALE"
    STATUS_FAILED = "FAILED"
    STATUS_CHOICES = [
        (STATUS_COMPLETE, "Complete"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_NO_SOURCE, "No source records"),
        (STATUS_STALE, "Stale"),
        (STATUS_FAILED, "Failed"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    snapshot_key = models.CharField(max_length=255, unique=True, blank=True)
    metric_definition = models.ForeignKey(
        OperationalMetricDefinition,
        on_delete=models.PROTECT,
        related_name="snapshots",
    )
    date = models.DateField()
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    grain = models.CharField(max_length=20, choices=GRAIN_CHOICES, default=GRAIN_DAILY)
    value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    numerator = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    denominator = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    value_unit = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_COMPLETE)
    source_record_count = models.PositiveIntegerField(default=0)
    source_coverage = models.JSONField(default=dict, blank=True)
    dimension_values = models.JSONField(default=dict, blank=True)
    county = models.CharField(max_length=120, blank=True)
    sub_county = models.CharField(max_length=120, blank=True)
    ward = models.ForeignKey(Ward, on_delete=models.SET_NULL, null=True, blank=True, related_name="operational_metric_snapshots")
    facility = models.ForeignKey(
        HealthFacility,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operational_metric_snapshots",
    )
    chv = models.ForeignKey(CHV, on_delete=models.SET_NULL, null=True, blank=True, related_name="operational_metric_snapshots")
    source_channel = models.CharField(max_length=40, blank=True)
    action_type = models.CharField(max_length=64, blank=True)
    alert_severity = models.CharField(max_length=40, blank=True)
    model_version = models.CharField(max_length=80, blank=True)
    calculation_run_id = models.UUIDField(null=True, blank=True)
    calculation_metadata = models.JSONField(default=dict, blank=True)
    generated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "metric_definition__metric_key"]
        indexes = [
            models.Index(fields=["metric_definition", "date"], name="risk_opssnap_def_idx"),
            models.Index(fields=["date", "status"], name="risk_opssnap_date_idx"),
            models.Index(fields=["ward", "date"], name="risk_opssnap_ward_idx"),
            models.Index(fields=["facility", "date"], name="risk_opssnap_fac_idx"),
            models.Index(fields=["chv", "date"], name="risk_opssnap_chv_idx"),
            models.Index(fields=["source_channel", "date"], name="risk_opssnap_chan_idx"),
            models.Index(fields=["model_version", "date"], name="risk_opssnap_model_idx"),
        ]

    def compute_snapshot_key(self) -> str:
        definition = self.metric_definition
        payload = {
            "metric_key": definition.metric_key,
            "metric_version": definition.version,
            "date": self.date.isoformat() if self.date else "",
            "period_start": self.period_start.isoformat() if self.period_start else "",
            "period_end": self.period_end.isoformat() if self.period_end else "",
            "grain": self.grain,
            "dimensions": {
                "county": self.county or "",
                "sub_county": self.sub_county or "",
                "ward_id": self.ward_id,
                "facility_id": self.facility_id,
                "chv_id": self.chv_id,
                "source_channel": self.source_channel or "",
                "action_type": self.action_type or "",
                "alert_severity": self.alert_severity or "",
                "model_version": self.model_version or "",
                "dimension_values": self.dimension_values or {},
            },
        }
        return f"opsmetric:{definition.metric_key}:{definition.version}:{_stable_identity_digest(payload)}"

    def save(self, *args, **kwargs):
        if not self.snapshot_key:
            self.snapshot_key = self.compute_snapshot_key()
        if not self.value_unit:
            self.value_unit = self.metric_definition.value_unit
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.metric_definition.metric_key} {self.date} [{self.status}]"


class OperationalBaselinePeriod(models.Model):
    STATUS_DRAFT = "DRAFT"
    STATUS_ACTIVE = "ACTIVE"
    STATUS_RETIRED = "RETIRED"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_RETIRED, "Retired"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    baseline_key = models.CharField(max_length=255, unique=True, blank=True)
    metric_definition = models.ForeignKey(
        OperationalMetricDefinition,
        on_delete=models.PROTECT,
        related_name="baseline_periods",
    )
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    grain = models.CharField(max_length=20, choices=OperationalMetricSnapshot.GRAIN_CHOICES, default=OperationalMetricSnapshot.GRAIN_DAILY)
    baseline_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    numerator = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    denominator = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    source_snapshot_count = models.PositiveIntegerField(default=0)
    source_snapshot_keys = models.JSONField(default=list, blank=True)
    calculation_method = models.CharField(max_length=160, default="explicit_period_average")
    dimensions = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    owner = models.CharField(max_length=120, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["metric_definition__metric_key", "-period_end", "name"]
        indexes = [
            models.Index(fields=["metric_definition", "status"], name="risk_opsbase_def_idx"),
            models.Index(fields=["period_start", "period_end"], name="risk_opsbase_period_idx"),
        ]

    def compute_baseline_key(self) -> str:
        definition = self.metric_definition
        payload = {
            "metric_key": definition.metric_key,
            "metric_version": definition.version,
            "name": self.name,
            "period_start": self.period_start.isoformat() if self.period_start else "",
            "period_end": self.period_end.isoformat() if self.period_end else "",
            "grain": self.grain,
            "dimensions": self.dimensions or {},
        }
        return f"opsbase:{definition.metric_key}:{definition.version}:{_stable_identity_digest(payload)}"

    def save(self, *args, **kwargs):
        if not self.baseline_key:
            self.baseline_key = self.compute_baseline_key()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.metric_definition.metric_key} baseline {self.name}"


class OperationalSLAThreshold(models.Model):
    COMPARATOR_LTE = "LTE"
    COMPARATOR_GTE = "GTE"
    COMPARATOR_LT = "LT"
    COMPARATOR_GT = "GT"
    COMPARATOR_CHOICES = [
        (COMPARATOR_LTE, "Less than or equal"),
        (COMPARATOR_GTE, "Greater than or equal"),
        (COMPARATOR_LT, "Less than"),
        (COMPARATOR_GT, "Greater than"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    threshold_key = models.SlugField(max_length=120)
    metric_definition = models.ForeignKey(
        OperationalMetricDefinition,
        on_delete=models.PROTECT,
        related_name="sla_thresholds",
    )
    version = models.CharField(max_length=40, default="v1")
    display_name = models.CharField(max_length=180)
    comparator = models.CharField(max_length=8, choices=COMPARATOR_CHOICES)
    target_value = models.DecimalField(max_digits=18, decimal_places=6)
    warning_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    critical_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    value_unit = models.CharField(max_length=40, blank=True)
    applies_to_dimensions = models.JSONField(default=dict, blank=True)
    owner = models.CharField(max_length=120)
    rationale = models.TextField()
    is_active = models.BooleanField(default=True)
    effective_from = models.DateTimeField(default=timezone.now)
    effective_to = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["metric_definition__metric_key", "threshold_key", "-version"]
        constraints = [
            models.UniqueConstraint(fields=["threshold_key", "version"], name="risk_opssla_key_ver_uniq"),
            models.UniqueConstraint(
                fields=["threshold_key"],
                condition=models.Q(is_active=True),
                name="risk_opssla_active_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["metric_definition", "is_active"], name="risk_opssla_def_idx"),
            models.Index(fields=["effective_from", "effective_to"], name="risk_opssla_eff_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self.value_unit:
            self.value_unit = self.metric_definition.value_unit
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.threshold_key}:{self.version}"


class OperationalThresholdBreach(models.Model):
    BREACH_THRESHOLD_WARNING = "THRESHOLD_WARNING"
    BREACH_THRESHOLD_BREACH = "THRESHOLD_BREACH"
    BREACH_SOURCE_WARNING = "SOURCE_WARNING"
    BREACH_SNAPSHOT_STALE = "SNAPSHOT_STALE"
    BREACH_MISSING_SNAPSHOT = "MISSING_SNAPSHOT"
    BREACH_STATUS_WARNING = "STATUS_WARNING"
    BREACH_CHOICES = [
        (BREACH_THRESHOLD_WARNING, "Threshold warning"),
        (BREACH_THRESHOLD_BREACH, "Threshold breach"),
        (BREACH_SOURCE_WARNING, "Source warning"),
        (BREACH_SNAPSHOT_STALE, "Snapshot stale"),
        (BREACH_MISSING_SNAPSHOT, "Missing snapshot"),
        (BREACH_STATUS_WARNING, "Status warning"),
    ]

    SEVERITY_WARNING = "WARNING"
    SEVERITY_CRITICAL = "CRITICAL"
    SEVERITY_CHOICES = [
        (SEVERITY_WARNING, "Warning"),
        (SEVERITY_CRITICAL, "Critical"),
    ]

    STATUS_ACTIVE = "ACTIVE"
    STATUS_RESOLVED = "RESOLVED"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    breach_key = models.CharField(max_length=255, unique=True, blank=True)
    metric_definition = models.ForeignKey(
        OperationalMetricDefinition,
        on_delete=models.PROTECT,
        related_name="threshold_breaches",
    )
    threshold = models.ForeignKey(
        OperationalSLAThreshold,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="breaches",
    )
    snapshot = models.ForeignKey(
        OperationalMetricSnapshot,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="threshold_breaches",
    )
    ward = models.ForeignKey(
        Ward,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operational_threshold_breaches",
    )
    breach_type = models.CharField(max_length=32, choices=BREACH_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_WARNING)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    date = models.DateField()
    title = models.CharField(max_length=220)
    body = models.TextField()
    warning_code = models.CharField(max_length=120, blank=True)
    observed_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    observed_status = models.CharField(max_length=40, blank=True)
    observed_unit = models.CharField(max_length=40, blank=True)
    comparator = models.CharField(max_length=8, blank=True)
    target_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    warning_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    critical_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    threshold_key_snapshot = models.CharField(max_length=120, blank=True)
    threshold_version_snapshot = models.CharField(max_length=40, blank=True)
    metric_key_snapshot = models.SlugField(max_length=120)
    metric_version_snapshot = models.CharField(max_length=40)
    dimension_values = models.JSONField(default=dict, blank=True)
    source_coverage = models.JSONField(default=dict, blank=True)
    attribution = models.JSONField(default=dict, blank=True)
    evaluation_metadata = models.JSONField(default=dict, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-severity", "metric_definition__metric_key"]
        indexes = [
            models.Index(fields=["status", "severity", "date"], name="risk_opsbreach_state_idx"),
            models.Index(fields=["metric_definition", "status"], name="risk_opsbreach_metric_idx"),
            models.Index(fields=["threshold", "status"], name="risk_opsbreach_threshold_idx"),
            models.Index(fields=["snapshot", "status"], name="risk_opsbreach_snapshot_idx"),
            models.Index(fields=["ward", "status", "date"], name="risk_opsbreach_ward_idx"),
        ]

    def compute_breach_key(self) -> str:
        payload = {
            "metric_key": self.metric_key_snapshot,
            "metric_version": self.metric_version_snapshot,
            "threshold_key": self.threshold_key_snapshot,
            "threshold_version": self.threshold_version_snapshot,
            "snapshot_key": self.snapshot.snapshot_key if self.snapshot_id and self.snapshot else "",
            "date": self.date.isoformat() if self.date else "",
            "breach_type": self.breach_type,
            "warning_code": self.warning_code,
            "dimensions": self.dimension_values or {},
        }
        return f"opsthreshold:{self.metric_key_snapshot}:{_stable_identity_digest(payload)}"

    def save(self, *args, **kwargs):
        if not self.metric_key_snapshot and self.metric_definition_id:
            self.metric_key_snapshot = self.metric_definition.metric_key
        if not self.metric_version_snapshot and self.metric_definition_id:
            self.metric_version_snapshot = self.metric_definition.version
        if self.threshold_id and self.threshold:
            self.threshold_key_snapshot = self.threshold_key_snapshot or self.threshold.threshold_key
            self.threshold_version_snapshot = self.threshold_version_snapshot or self.threshold.version
            self.comparator = self.comparator or self.threshold.comparator
            self.target_value = self.target_value if self.target_value is not None else self.threshold.target_value
            self.warning_value = self.warning_value if self.warning_value is not None else self.threshold.warning_value
            self.critical_value = self.critical_value if self.critical_value is not None else self.threshold.critical_value
        if self.snapshot_id and self.snapshot:
            self.observed_value = self.observed_value if self.observed_value is not None else self.snapshot.value
            self.observed_status = self.observed_status or self.snapshot.status
            self.observed_unit = self.observed_unit or self.snapshot.value_unit
            self.dimension_values = self.dimension_values or self.snapshot.dimension_values
            self.source_coverage = self.source_coverage or self.snapshot.source_coverage
            self.ward = self.ward or self.snapshot.ward
        if not self.breach_key:
            self.breach_key = self.compute_breach_key()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.metric_key_snapshot} {self.breach_type} [{self.status}]"


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


class SourceDataUploadBatch(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_UPLOADED = "uploaded"
    STATUS_VALIDATING = "validating"
    STATUS_VALIDATION_FAILED = "validation_failed"
    STATUS_READY_FOR_CONFIRMATION = "ready_for_confirmation"
    STATUS_CONFIRMING = "confirming"
    STATUS_IMPORTED = "imported"
    STATUS_IMPORT_FAILED = "import_failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_SUPERSEDED = "superseded"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_UPLOADED, "Uploaded"),
        (STATUS_VALIDATING, "Validating"),
        (STATUS_VALIDATION_FAILED, "Validation failed"),
        (STATUS_READY_FOR_CONFIRMATION, "Ready for confirmation"),
        (STATUS_CONFIRMING, "Confirming"),
        (STATUS_IMPORTED, "Imported"),
        (STATUS_IMPORT_FAILED, "Import failed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_SUPERSEDED, "Superseded"),
    ]

    VALIDATION_NOT_STARTED = "not_started"
    VALIDATION_RUNNING = "running"
    VALIDATION_PASSED = "passed"
    VALIDATION_FAILED = "failed"
    VALIDATION_CHOICES = [
        (VALIDATION_NOT_STARTED, "Not started"),
        (VALIDATION_RUNNING, "Running"),
        (VALIDATION_PASSED, "Passed"),
        (VALIDATION_FAILED, "Failed"),
    ]

    IMPORT_NOT_STARTED = "not_started"
    IMPORT_RUNNING = "running"
    IMPORT_IMPORTED = "imported"
    IMPORT_FAILED = "failed"
    IMPORT_CHOICES = [
        (IMPORT_NOT_STARTED, "Not started"),
        (IMPORT_RUNNING, "Running"),
        (IMPORT_IMPORTED, "Imported"),
        (IMPORT_FAILED, "Failed"),
    ]

    APPROVAL_NOT_REQUIRED = "not_required"
    APPROVAL_PENDING = "pending"
    APPROVAL_APPROVED = "approved"
    APPROVAL_REJECTED = "rejected"
    APPROVAL_EXPIRED = "expired"
    APPROVAL_CHOICES = [
        (APPROVAL_NOT_REQUIRED, "Not required"),
        (APPROVAL_PENDING, "Pending"),
        (APPROVAL_APPROVED, "Approved"),
        (APPROVAL_REJECTED, "Rejected"),
        (APPROVAL_EXPIRED, "Expired"),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    feed_key = models.CharField(max_length=80)
    domain = models.CharField(max_length=80)
    source_type = models.CharField(max_length=80)
    source_name = models.CharField(max_length=160)
    source_ref = models.CharField(max_length=255, blank=True)
    source_timestamp = models.DateTimeField(null=True, blank=True)
    release_version = models.CharField(max_length=120, blank=True)
    reporting_period_start = models.DateField(null=True, blank=True)
    reporting_period_end = models.DateField(null=True, blank=True)
    correction_mode = models.CharField(max_length=40, blank=True)
    replacement_reason = models.TextField(blank=True)
    operator_note = models.TextField(blank=True)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default=STATUS_UPLOADED)
    validation_status = models.CharField(max_length=40, choices=VALIDATION_CHOICES, default=VALIDATION_NOT_STARTED)
    import_status = models.CharField(max_length=40, choices=IMPORT_CHOICES, default=IMPORT_NOT_STARTED)
    row_count = models.PositiveIntegerField(default=0)
    accepted_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    duplicate_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="duplicate_uploads",
    )
    replaces_upload = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replacement_uploads",
    )
    approval_status = models.CharField(max_length=40, choices=APPROVAL_CHOICES, default=APPROVAL_NOT_REQUIRED)
    approval_risk_category = models.CharField(max_length=80, blank=True)
    approval_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_data_approval_requests",
    )
    approval_requested_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_data_approvals",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_reason = models.TextField(blank=True)
    approval_expires_at = models.DateTimeField(null=True, blank=True)
    validation_celery_task_id = models.CharField(max_length=255, blank=True)
    import_celery_task_id = models.CharField(max_length=255, blank=True)
    downstream_celery_task_id = models.CharField(max_length=255, blank=True)
    domain_ingestion_run_type = models.CharField(max_length=80, blank=True)
    domain_ingestion_run_id = models.PositiveIntegerField(null=True, blank=True)
    surveillance_ingestion_run = models.ForeignKey(
        SurveillanceIngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_data_upload_batches",
    )
    population_exposure_ingestion_run = models.ForeignKey(
        PopulationExposureIngestionRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_data_upload_batches",
    )
    facility_readiness_ingestion_run_id = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_data_upload_batches",
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_data_confirmed_upload_batches",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["feed_key", "created_at"], name="risk_srcbatch_feed_created_idx"),
            models.Index(fields=["status", "created_at"], name="risk_srcbatch_status_idx"),
            models.Index(fields=["validation_status", "created_at"], name="risk_srcbatch_val_idx"),
            models.Index(fields=["source_type", "source_timestamp"], name="risk_srcbatch_source_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.feed_key} upload {self.public_id} [{self.status}]"


class SourceDataUploadArtifact(models.Model):
    upload_batch = models.ForeignKey(
        SourceDataUploadBatch,
        on_delete=models.CASCADE,
        related_name="artifacts",
    )
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    storage_backend = models.CharField(max_length=40, default="shared_filesystem")
    storage_path = models.CharField(max_length=500)
    retention_expires_at = models.DateTimeField(null=True, blank=True)
    redaction_state = models.CharField(max_length=40, default="raw")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["sha256", "created_at"], name="risk_srcart_sha_created_idx"),
            models.Index(fields=["retention_expires_at"], name="risk_srcart_retention_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} {self.sha256[:12]}"


class SourceDataValidationIssue(models.Model):
    SEVERITY_ERROR = "error"
    SEVERITY_WARNING = "warning"
    SEVERITY_INFO = "info"
    SEVERITY_CHOICES = [
        (SEVERITY_ERROR, "Error"),
        (SEVERITY_WARNING, "Warning"),
        (SEVERITY_INFO, "Info"),
    ]

    upload_batch = models.ForeignKey(
        SourceDataUploadBatch,
        on_delete=models.CASCADE,
        related_name="validation_issues",
    )
    row_number = models.PositiveIntegerField(null=True, blank=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    code = models.CharField(max_length=120)
    column_name = models.CharField(max_length=120, blank=True)
    message = models.TextField()
    safe_context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["severity", "row_number", "created_at"]
        indexes = [
            models.Index(fields=["upload_batch", "severity"], name="risk_srcissue_batch_sev_idx"),
            models.Index(fields=["code"], name="risk_srcissue_code_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.upload_batch.public_id} {self.severity}:{self.code}"


class SourceDataUploadEvent(models.Model):
    EVENT_TEMPLATE_DOWNLOADED = "template_downloaded"
    EVENT_UPLOAD_CREATED = "upload_created"
    EVENT_VALIDATION_STARTED = "validation_started"
    EVENT_VALIDATION_COMPLETED = "validation_completed"
    EVENT_CONFIRMATION_REQUESTED = "confirmation_requested"
    EVENT_IMPORT_STARTED = "import_started"
    EVENT_IMPORT_COMPLETED = "import_completed"
    EVENT_IMPORT_FAILED = "import_failed"
    EVENT_ERRORS_DOWNLOADED = "errors_downloaded"
    EVENT_DOWNSTREAM_ACTION_REQUESTED = "downstream_action_requested"
    EVENT_REPLACEMENT_REQUESTED = "replacement_requested"
    EVENT_UPLOAD_CANCELLED = "upload_cancelled"
    EVENT_CHOICES = [
        (EVENT_TEMPLATE_DOWNLOADED, "Template downloaded"),
        (EVENT_UPLOAD_CREATED, "Upload created"),
        (EVENT_VALIDATION_STARTED, "Validation started"),
        (EVENT_VALIDATION_COMPLETED, "Validation completed"),
        (EVENT_CONFIRMATION_REQUESTED, "Confirmation requested"),
        (EVENT_IMPORT_STARTED, "Import started"),
        (EVENT_IMPORT_COMPLETED, "Import completed"),
        (EVENT_IMPORT_FAILED, "Import failed"),
        (EVENT_ERRORS_DOWNLOADED, "Errors downloaded"),
        (EVENT_DOWNSTREAM_ACTION_REQUESTED, "Downstream action requested"),
        (EVENT_REPLACEMENT_REQUESTED, "Replacement requested"),
        (EVENT_UPLOAD_CANCELLED, "Upload cancelled"),
    ]

    upload_batch = models.ForeignKey(
        SourceDataUploadBatch,
        on_delete=models.CASCADE,
        related_name="events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_data_upload_events",
    )
    event_type = models.CharField(max_length=80, choices=EVENT_CHOICES)
    event_at = models.DateTimeField(default=timezone.now)
    ip_address_hash = models.CharField(max_length=64, blank=True)
    user_agent_hash = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-event_at", "-id"]
        indexes = [
            models.Index(fields=["upload_batch", "event_at"], name="risk_srcevent_batch_time_idx"),
            models.Index(fields=["event_type", "event_at"], name="risk_srcevent_type_time_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.upload_batch.public_id} {self.event_type}"


class SourceDataConnectorRun(models.Model):
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    connector_key = models.CharField(max_length=120)
    target_feed_key = models.CharField(max_length=80)
    feed_mode = models.CharField(max_length=40, default="api")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    source_name = models.CharField(max_length=160)
    source_ref = models.CharField(max_length=255, blank=True)
    fetched_record_count = models.PositiveIntegerField(default=0)
    upload_batch = models.ForeignKey(
        SourceDataUploadBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="connector_runs",
    )
    error_summary = models.TextField(blank=True)
    safe_metadata = models.JSONField(default=dict, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_data_connector_runs",
    )
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["connector_key", "started_at"], name="risk_srcconn_key_started_idx"),
            models.Index(fields=["target_feed_key", "status"], name="risk_srcconn_feed_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.connector_key} [{self.status}]"


class SourceDataFeedModeOverride(models.Model):
    MODE_API = "api"
    MODE_CSV = "csv"
    MODE_MANUAL = "manual"
    MODE_FALLBACK = "fallback"
    MODE_DEMO = "demo"
    MODE_CHOICES = [
        (MODE_API, "API"),
        (MODE_CSV, "CSV"),
        (MODE_MANUAL, "Manual"),
        (MODE_FALLBACK, "Fallback"),
        (MODE_DEMO, "Demo"),
    ]

    feed_key = models.CharField(max_length=80, unique=True)
    feed_mode = models.CharField(max_length=40, choices=MODE_CHOICES, default=MODE_CSV)
    authoritative_connector_key = models.CharField(max_length=120, blank=True)
    csv_upload_enabled = models.BooleanField(default=True)
    reason = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_data_feed_mode_overrides",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["feed_key"]
        indexes = [
            models.Index(fields=["feed_mode", "csv_upload_enabled"], name="risk_srcmode_mode_csv_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.feed_key} mode={self.feed_mode} csv={self.csv_upload_enabled}"


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
