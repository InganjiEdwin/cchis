from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from risk.models import WardGeometryDatasetVersion, WardGeometryFeature


User = get_user_model()


def resolve_operator(username: str | None):
    if not username:
        return None
    operator = User.objects.filter(username=username).first()
    if operator is None:
        raise ValueError(f"Operator username not found: {username}")
    return operator


def sync_canonical_ward_geometry_fields(*, dataset_slug: str, dry_run: bool = False) -> dict:
    version = (
        WardGeometryDatasetVersion.objects.select_related("dataset")
        .filter(dataset__slug=dataset_slug, is_active=True)
        .order_by("-activated_at", "-id")
        .first()
    )
    if version is None:
        raise WardGeometryDatasetVersion.DoesNotExist(
            f"No active managed ward geometry version found for dataset '{dataset_slug}'."
        )

    features = list(
        WardGeometryFeature.objects.filter(dataset_version=version).select_related("ward").order_by("ward_id")
    )
    if not features:
        raise WardGeometryDatasetVersion.DoesNotExist(
            f"No managed ward geometry features found for active version '{version.version_label}'."
        )

    updated = 0
    unchanged = 0
    missing_centroids = 0

    with transaction.atomic():
        for feature in features:
            ward = feature.ward
            changed_fields = []
            if ward.boundary != feature.geometry:
                ward.boundary = feature.geometry
                changed_fields.append("boundary")
            if ward.centroid != feature.centroid:
                ward.centroid = feature.centroid
                changed_fields.append("centroid")
            if feature.centroid is None:
                missing_centroids += 1

            if changed_fields:
                if not dry_run:
                    ward.save(update_fields=changed_fields)
                updated += 1
            else:
                unchanged += 1

        if dry_run:
            transaction.set_rollback(True)

    return {
        "dataset_slug": dataset_slug,
        "version_label": version.version_label,
        "updated": updated,
        "unchanged": unchanged,
        "missing_centroids": missing_centroids,
        "dry_run": dry_run,
    }


def activate_geometry_version(
    *,
    dataset_slug: str,
    version_label: str,
    operator_username: str | None = None,
    notes: str = "",
    sync_canonical_fields: bool = True,
):
    operator = resolve_operator(operator_username)
    with transaction.atomic():
        version = (
            WardGeometryDatasetVersion.objects.select_related("dataset")
            .select_for_update()
            .get(dataset__slug=dataset_slug, version_label=version_label)
        )
        WardGeometryDatasetVersion.objects.filter(dataset=version.dataset, is_active=True).exclude(pk=version.pk).update(
            is_active=False
        )
        version.is_active = True
        version.activated_at = timezone.now()
        version.activated_by = operator
        if notes:
            version.notes = notes
        version.save(update_fields=["is_active", "activated_at", "activated_by", "notes"])
    sync_summary = None
    if sync_canonical_fields:
        sync_summary = sync_canonical_ward_geometry_fields(dataset_slug=dataset_slug, dry_run=False)
    return version, sync_summary


def summarize_dataset_versions(*, dataset_slug: str) -> list[dict]:
    versions = (
        WardGeometryDatasetVersion.objects.select_related("dataset", "activated_by", "imported_by")
        .filter(dataset__slug=dataset_slug)
        .order_by("-is_active", "-activated_at", "-imported_at", "-id")
    )
    return [
        {
            "dataset_slug": version.dataset.slug,
            "dataset_name": version.dataset.name,
            "version_label": version.version_label,
            "is_active": version.is_active,
            "feature_count": version.feature_count,
            "expected_feature_count": version.expected_feature_count,
            "source_name": version.source_name,
            "source_url": version.source_url,
            "source_license": version.source_license,
            "source_crs": version.source_crs,
            "imported_at": version.imported_at.isoformat() if version.imported_at else None,
            "imported_by": version.imported_by.username if version.imported_by else None,
            "activated_at": version.activated_at.isoformat() if version.activated_at else None,
            "activated_by": version.activated_by.username if version.activated_by else None,
            "missing_source_wards": version.missing_source_wards,
            "notes": version.notes,
        }
        for version in versions
    ]
