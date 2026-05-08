import re


PHONE_CANDIDATE_PATTERN = re.compile(r"^\+?[0-9][0-9\s().-]{6,}$")
PHONE_IN_TEXT_PATTERN = re.compile(r"(?<!\d)(?:\+?254|0)\s?[17]\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\d)")
EMAIL_CANDIDATE_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EMAIL_IN_TEXT_PATTERN = re.compile(r"\b[^@\s]+@[^@\s]+\.[^@\s]+\b")

DIRECT_IDENTIFIER_METADATA_KEYS = {
    "address",
    "caregiver_name",
    "child_name",
    "contact",
    "contact_email",
    "contact_phone",
    "date_of_birth",
    "dob",
    "email",
    "external_id",
    "first_name",
    "full_name",
    "gps",
    "household_head_name",
    "id_number",
    "last_name",
    "mother_name",
    "name",
    "national_id",
    "passport_number",
    "patient_name",
    "phone",
    "phone_number",
    "precise_location",
    "provider_reference",
    "recipient",
    "recipient_email",
    "recipient_phone",
}
DIRECT_REFERENCE_METADATA_KEYS = {
    "actor_id",
    "audit_event_public_id",
    "contact_public_id",
    "contact_reference",
    "coverage_event_public_id",
    "coverage_request_public_id",
    "facility_contact_public_id",
    "preference_public_id",
    "provider_reference",
    "source_reference",
}
DIRECT_IDENTIFIER_SUBJECT_TOKENS = {
    "caregiver",
    "child",
    "client",
    "father",
    "household",
    "mother",
    "patient",
    "person",
}


def metadata_key_is_direct_reference(key: str) -> bool:
    normalized_key = str(key).lower()
    key_parts = set(normalized_key.split("_"))
    return normalized_key in DIRECT_REFERENCE_METADATA_KEYS or (
        "public" in key_parts and "id" in key_parts and {"ward", "risk", "score"}.isdisjoint(key_parts)
    )


def metadata_key_is_direct_identifier(key: str) -> bool:
    normalized_key = str(key).lower()
    key_parts = set(normalized_key.split("_"))
    if normalized_key in DIRECT_IDENTIFIER_METADATA_KEYS:
        return True
    if key_parts & {"email", "phone", "mobile", "msisdn", "address", "gps"}:
        return True
    if key_parts & {"national", "passport"} and "id" in key_parts:
        return True
    if {"birth", "date"}.issubset(key_parts) or "dob" in key_parts:
        return True
    if "name" in key_parts and key_parts & DIRECT_IDENTIFIER_SUBJECT_TOKENS:
        return True
    if "id" in key_parts and key_parts & DIRECT_IDENTIFIER_SUBJECT_TOKENS:
        return True
    return False


def user_can_view_direct_identifiers(user) -> bool:
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (
            getattr(user, "is_superuser", False)
            or getattr(user, "role", None) in {"ADMIN", "SUPERVISOR"}
        )
    )


def mask_phone_number(value: str) -> str:
    raw = (value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 4:
        return "redacted"
    last4 = digits[-4:]
    if digits.startswith("254") or raw.startswith("+254"):
        return f"+254******{last4}"
    return f"******{last4}"


def mask_email(value: str) -> str:
    raw = (value or "").strip()
    local, _, domain = raw.partition("@")
    if not local or not domain:
        return "redacted"
    return f"{local[:1]}***@{domain}"


def mask_contact_value(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if PHONE_CANDIDATE_PATTERN.match(raw):
        return mask_phone_number(raw)
    if EMAIL_CANDIDATE_PATTERN.match(raw):
        return mask_email(raw)
    return raw


def redact_field_health_text(value: str, *, can_view: bool) -> str:
    if can_view:
        return value or ""
    return ""


def redact_direct_identifiers_in_text(value: str, *, can_view: bool) -> str:
    text = value or ""
    if can_view:
        return text
    text = PHONE_IN_TEXT_PATTERN.sub("[redacted phone]", text)
    return EMAIL_IN_TEXT_PATTERN.sub("[redacted email]", text)


def redact_provider_identifier(value: str, *, can_view: bool) -> str:
    if can_view:
        return value or ""
    return ""


def serializer_user(serializer):
    request = serializer.context.get("request") if hasattr(serializer, "context") else None
    return getattr(request, "user", None)


def privacy_context(*, classification: str, redacted: bool, reason: str) -> dict:
    return {
        "classification": classification,
        "redacted": redacted,
        "reason": reason,
    }
