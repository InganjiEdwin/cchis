from __future__ import annotations

import hashlib
import re
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils import timezone

from risk.models import SourceDataUploadArtifact, SourceDataUploadBatch
from risk.source_data.registry import source_data_feed_definition


SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_upload_filename(filename: str) -> str:
    name = Path(filename or "source-data-upload.csv").name
    return SAFE_FILENAME_RE.sub("_", name).strip("._") or "source-data-upload.csv"


def source_data_upload_root() -> Path:
    return Path(settings.SOURCE_DATA_UPLOAD_ROOT)


def artifact_storage_path(batch: SourceDataUploadBatch, filename: str) -> Path:
    safe_name = safe_upload_filename(filename)
    return source_data_upload_root() / str(batch.public_id) / safe_name


def _write_uploaded_file(uploaded_file: UploadedFile, destination: Path) -> tuple[int, str]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    sha256 = hashlib.sha256()
    size = 0
    with destination.open("wb") as output:
        for chunk in uploaded_file.chunks():
            output.write(chunk)
            sha256.update(chunk)
            size += len(chunk)
    return size, sha256.hexdigest()


@transaction.atomic
def create_source_data_upload_batch(
    *,
    uploaded_file: UploadedFile,
    created_by,
    metadata: dict[str, Any],
) -> SourceDataUploadBatch:
    feed_key = str(metadata["feed_key"])
    definition = source_data_feed_definition(feed_key)
    replaces_upload = metadata.get("replaces_upload")
    batch = SourceDataUploadBatch.objects.create(
        feed_key=definition.feed_key,
        domain=definition.domain,
        source_type=definition.source_type,
        source_name=str(metadata["source_name"]),
        source_ref=str(metadata.get("source_ref") or ""),
        source_timestamp=metadata.get("source_timestamp"),
        release_version=str(metadata.get("release_version") or ""),
        reporting_period_start=metadata.get("reporting_period_start"),
        reporting_period_end=metadata.get("reporting_period_end"),
        correction_mode=str(metadata.get("correction_mode") or ""),
        replacement_reason=str(metadata.get("replacement_reason") or ""),
        operator_note=str(metadata.get("operator_note") or ""),
        replaces_upload=replaces_upload,
        created_by=created_by,
        metadata={
            "phase": "phase_2_upload_and_dry_validation",
            "required_metadata": list(definition.required_metadata),
            "template_url": definition.template_url,
        },
    )

    destination = artifact_storage_path(batch, uploaded_file.name)
    size_bytes, sha256 = _write_uploaded_file(uploaded_file, destination)
    retention_days = settings.SOURCE_DATA_RAW_UPLOAD_RETENTION_DAYS
    artifact = SourceDataUploadArtifact.objects.create(
        upload_batch=batch,
        original_filename=safe_upload_filename(uploaded_file.name),
        content_type=getattr(uploaded_file, "content_type", "") or "",
        size_bytes=size_bytes,
        sha256=sha256,
        storage_backend=settings.SOURCE_DATA_UPLOAD_STORAGE_BACKEND,
        storage_path=str(destination),
        retention_expires_at=timezone.now() + timedelta(days=retention_days),
    )

    duplicate_artifact = (
        SourceDataUploadArtifact.objects.select_related("upload_batch")
        .filter(sha256=sha256)
        .exclude(upload_batch=batch)
        .order_by("-created_at")
        .first()
    )
    duplicate_metadata_batch = (
        SourceDataUploadBatch.objects.filter(
            feed_key=batch.feed_key,
            source_name=batch.source_name,
            source_ref=batch.source_ref,
            source_timestamp=batch.source_timestamp,
            release_version=batch.release_version,
            reporting_period_start=batch.reporting_period_start,
            reporting_period_end=batch.reporting_period_end,
        )
        .exclude(id=batch.id)
        .order_by("-created_at")
        .first()
    )
    if duplicate_artifact:
        batch.duplicate_of = duplicate_artifact.upload_batch
        batch.metadata = {
            **batch.metadata,
            "duplicate_file_sha256": sha256,
            "duplicate_upload_public_id": str(duplicate_artifact.upload_batch.public_id),
        }
        batch.save(update_fields=["duplicate_of", "metadata", "updated_at"])
    if duplicate_metadata_batch:
        if batch.duplicate_of_id is None:
            batch.duplicate_of = duplicate_metadata_batch
        batch.metadata = {
            **batch.metadata,
            "duplicate_metadata_upload_public_id": str(duplicate_metadata_batch.public_id),
        }
        batch.save(update_fields=["duplicate_of", "metadata", "updated_at"])

    return batch


def latest_upload_artifact(batch: SourceDataUploadBatch) -> SourceDataUploadArtifact:
    artifact = batch.artifacts.order_by("-created_at").first()
    if artifact is None:
        raise ValueError("Upload batch has no stored artifact.")
    return artifact
