from __future__ import annotations

from collections.abc import Mapping, Sequence
from numbers import Number


COMPLETION_EVIDENCE_BOILERPLATE_KEYS = {
    "actor",
    "actor_id",
    "captured_at",
    "captured_by",
    "captured_by_id",
    "captured_via",
    "created_at",
    "metadata",
    "operator",
    "operator_id",
    "schema",
    "schema_version",
    "source",
    "status",
    "submitted_at",
    "updated_at",
}


def completion_evidence_has_substance(evidence) -> bool:
    if not isinstance(evidence, Mapping):
        return False
    return any(
        _evidence_value_has_substance(value, key=str(key))
        for key, value in evidence.items()
        if str(key).strip()
    )


def _evidence_value_has_substance(value, *, key: str = "") -> bool:
    normalized_key = key.strip().lower()
    if normalized_key in COMPLETION_EVIDENCE_BOILERPLATE_KEYS:
        return False
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, bool):
        return value
    if isinstance(value, Number):
        return True
    if isinstance(value, Mapping):
        return any(
            _evidence_value_has_substance(nested_value, key=str(nested_key))
            for nested_key, nested_value in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_evidence_value_has_substance(item) for item in value)
    return bool(value)
