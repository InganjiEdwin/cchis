from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


PHONE_NUMBER_PATTERN = re.compile(
    r"(?<!\d)(?:\+?254|0)\s?[17]\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\d)",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
DIRECT_ID_LABEL_PATTERN = re.compile(
    r"\b(?:national\s*id|id\s*number|passport|birth\s*certificate|nhif|nssf)\b",
    re.IGNORECASE,
)
DIRECT_NAME_LABEL_PATTERN = re.compile(
    r"\b(?:patient|child|caregiver|mother|father|household|household\s*head)\s*(?:full\s*)?name\b",
    re.IGNORECASE,
)
EXACT_LOCATION_PATTERN = re.compile(
    r"\b(?:gps|gps\s*pin|coordinates?|latitude|longitude|lat/long|exact\s*(?:household\s*)?location|household\s*location)\b",
    re.IGNORECASE,
)
UNSUPPORTED_MEDICAL_NOTE_PATTERN = re.compile(
    r"\b(?:diagnosis|clinical\s*notes?|medical\s*notes?|lab\s*results?|test\s*results?|patient\s*history)\b",
    re.IGNORECASE,
)

UNSAFE_STRUCTURED_KEYS = {
    "address",
    "caregiver_name",
    "child_name",
    "clinical_notes",
    "coordinates",
    "diagnosis",
    "email",
    "exact_address",
    "exact_location",
    "full_name",
    "gps",
    "household_head_name",
    "household_location",
    "household_member_name",
    "household_name",
    "id_number",
    "lab_result",
    "lab_results",
    "latitude",
    "longitude",
    "medical_notes",
    "mother_name",
    "national_id",
    "passport_number",
    "patient_history",
    "patient_name",
    "phone",
    "phone_number",
    "precise_location",
    "test_result",
    "test_results",
}

PII_SAFE_REJECTION_MESSAGE = (
    "Remove direct identifiers, contact details, exact household locations, and unsupported medical notes before submitting."
)


@dataclass(frozen=True)
class PrivacyMinimizationFinding:
    location: str
    reason: str


class PrivacyMinimizationViolation(ValueError):
    def __init__(self, findings: Sequence[PrivacyMinimizationFinding]):
        self.findings = tuple(findings)
        details = "; ".join(f"{finding.location}: {finding.reason}" for finding in self.findings)
        super().__init__(f"{PII_SAFE_REJECTION_MESSAGE} {details}")


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _unsafe_key_reason(key: object) -> str:
    normalized = _normalized_key(key)
    if normalized in UNSAFE_STRUCTURED_KEYS:
        return "unsupported direct identifier or sensitive field key"
    if "household" in normalized and any(part in normalized for part in ("name", "phone", "address", "gps", "location")):
        return "household identifiers are not collected in this workflow"
    if any(part in normalized for part in ("patient_name", "child_name", "caregiver_name", "national_id")):
        return "patient or child identifiers are not collected in this workflow"
    if any(part in normalized for part in ("latitude", "longitude", "coordinate", "gps")):
        return "exact household locations are not collected in this workflow"
    return ""


def unsafe_pii_findings_in_text(value: object, *, location: str) -> tuple[PrivacyMinimizationFinding, ...]:
    text = str(value or "").strip()
    if not text:
        return ()

    findings: list[PrivacyMinimizationFinding] = []
    checks = (
        (PHONE_NUMBER_PATTERN, "direct phone numbers belong in explicit contact fields, not free text"),
        (EMAIL_PATTERN, "email addresses belong in explicit contact fields, not free text"),
        (DIRECT_ID_LABEL_PATTERN, "national or government identifiers are not collected in this workflow"),
        (DIRECT_NAME_LABEL_PATTERN, "patient, child, caregiver, or household names are not collected here"),
        (EXACT_LOCATION_PATTERN, "exact household location or GPS fields are not collected here"),
        (UNSUPPORTED_MEDICAL_NOTE_PATTERN, "free-text medical notes need a reviewed, supported workflow"),
    )
    for pattern, reason in checks:
        if pattern.search(text):
            findings.append(PrivacyMinimizationFinding(location=location, reason=reason))

    return tuple(findings)


def unsafe_pii_findings_in_mapping(value: object, *, location: str) -> tuple[PrivacyMinimizationFinding, ...]:
    findings: list[PrivacyMinimizationFinding] = []

    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            nested_location = f"{location}.{key}"
            key_reason = _unsafe_key_reason(key)
            if key_reason:
                findings.append(PrivacyMinimizationFinding(location=nested_location, reason=key_reason))
            findings.extend(unsafe_pii_findings_in_mapping(nested_value, location=nested_location))
        return tuple(findings)

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested_value in enumerate(value):
            findings.extend(unsafe_pii_findings_in_mapping(nested_value, location=f"{location}[{index}]"))
        return tuple(findings)

    if isinstance(value, str):
        findings.extend(unsafe_pii_findings_in_text(value, location=location))

    return tuple(findings)


def ensure_pii_safe_text(value: object, *, location: str) -> None:
    findings = unsafe_pii_findings_in_text(value, location=location)
    if findings:
        raise PrivacyMinimizationViolation(findings)


def ensure_pii_safe_mapping(value: object, *, location: str) -> None:
    findings = unsafe_pii_findings_in_mapping(value, location=location)
    if findings:
        raise PrivacyMinimizationViolation(findings)
