"""Controlled, non-deserializing handling of registered model artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.conf import settings


SUPPORTED_ARTIFACT_FORMATS = frozenset({"joblib", "onnx", "pickle"})
SUPPORTED_ARTIFACT_SCHEMES = frozenset({"file", "local"})
ARTIFACT_CHUNK_SIZE = 1024 * 1024


def _error(code: str, **details) -> dict:
    return {"code": code, **details}


def _controlled_root() -> Path:
    return Path(getattr(settings, "MODEL_ARTIFACT_ROOT", "/var/lib/cchis/model_artifacts")).expanduser().resolve()


def _path_from_location(location: str) -> tuple[Path | None, str | None]:
    value = (location or "").strip()
    if not value:
        return None, "artifact_location_missing"
    parsed = urlparse(value)
    if parsed.scheme:
        if parsed.scheme not in SUPPORTED_ARTIFACT_SCHEMES:
            return None, "artifact_storage_scheme_unsupported"
        if parsed.netloc and parsed.netloc not in {"", "localhost"}:
            return None, "artifact_storage_host_unsupported"
        raw_path = unquote(parsed.path)
    else:
        raw_path = value
    if not raw_path:
        return None, "artifact_location_missing"
    try:
        return Path(raw_path).expanduser().resolve(strict=True), None
    except (OSError, RuntimeError):
        return None, "artifact_not_found"


def _format_from_path(path: Path, requested_format: str = "") -> str:
    normalized = (requested_format or "").strip().lower().lstrip(".")
    if normalized:
        return normalized
    return {
        ".joblib": "joblib",
        ".onnx": "onnx",
        ".pkl": "pickle",
        ".pickle": "pickle",
    }.get(path.suffix.lower(), "")


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def inspect_artifact(
    *,
    location: str,
    expected_sha256: str = "",
    expected_size_bytes: int | None = None,
    artifact_format: str = "",
) -> dict:
    """Return integrity facts and stable blockers without loading/deserializing the artifact."""

    path, location_error = _path_from_location(location)
    if location_error:
        return {"valid": False, "blockers": [_error(location_error)]}
    assert path is not None
    root = _controlled_root()
    if not _is_within_root(path, root):
        return {"valid": False, "blockers": [_error("artifact_outside_controlled_root")]}
    if not path.is_file():
        return {"valid": False, "blockers": [_error("artifact_not_regular_file")]}

    resolved_format = _format_from_path(path, artifact_format)
    blockers = []
    if resolved_format not in SUPPORTED_ARTIFACT_FORMATS:
        blockers.append(_error("artifact_format_unsupported", artifact_format=resolved_format))

    size_bytes = path.stat().st_size
    digest = hashlib.sha256()
    try:
        with path.open("rb") as artifact_file:
            for chunk in iter(lambda: artifact_file.read(ARTIFACT_CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError:
        blockers.append(_error("artifact_unreadable"))
        return {"valid": False, "blockers": blockers}
    sha256 = digest.hexdigest()

    normalized_expected_sha256 = (expected_sha256 or "").strip().lower()
    if not normalized_expected_sha256:
        blockers.append(_error("artifact_sha256_required"))
    elif normalized_expected_sha256 != sha256:
        blockers.append(_error("artifact_sha256_mismatch"))
    if expected_size_bytes is not None and int(expected_size_bytes) != size_bytes:
        blockers.append(_error("artifact_size_mismatch"))

    return {
        "valid": not blockers,
        "blockers": blockers,
        "artifact_format": resolved_format,
        "artifact_size_bytes": size_bytes,
        "artifact_sha256": sha256,
        "artifact_name": path.name,
        "artifact_location": f"file://{path}",
    }


def verify_registry_artifact(entry) -> dict:
    return inspect_artifact(
        location=getattr(entry, "artifact_location", ""),
        expected_sha256=getattr(entry, "artifact_sha256", ""),
        expected_size_bytes=getattr(entry, "artifact_size_bytes", None),
        artifact_format=getattr(entry, "artifact_format", ""),
    )


def sanitized_artifact_evidence(entry, inspection: dict | None = None) -> dict:
    inspection = inspection or verify_registry_artifact(entry)
    location = str(getattr(entry, "artifact_location", "") or "")
    path = Path(urlparse(location).path).name if location else ""
    return {
        "artifact_present": bool(location),
        "artifact_name": path or None,
        "artifact_format": getattr(entry, "artifact_format", "") or inspection.get("artifact_format", ""),
        "artifact_size_bytes": getattr(entry, "artifact_size_bytes", 0),
        "artifact_sha256": getattr(entry, "artifact_sha256", "") or None,
        "integrity_valid": bool(inspection.get("valid")),
        "integrity_blocker_codes": [item.get("code") for item in inspection.get("blockers", [])],
    }
