import json

from django.core.management.base import BaseCommand, CommandError

from risk.ward_geometry_ops import activate_geometry_version


class Command(BaseCommand):
    help = "Activate a managed ward geometry dataset version explicitly."

    def add_arguments(self, parser):
        parser.add_argument("--dataset-slug", default="migori-ward-boundaries", help="Dataset slug to activate within.")
        parser.add_argument("--version-label", required=True, help="Dataset version label to activate.")
        parser.add_argument(
            "--operator-username",
            default="",
            help="Optional username to record as the activation operator.",
        )
        parser.add_argument(
            "--notes",
            default="",
            help="Optional activation notes or rollback reason.",
        )
        parser.add_argument(
            "--skip-sync",
            action="store_true",
            help="Skip syncing canonical Ward.boundary and Ward.centroid from the newly active version.",
        )

    def handle(self, *args, **options):
        dataset_slug = options["dataset_slug"].strip()
        version_label = options["version_label"].strip()
        operator_username = options["operator_username"].strip() or None
        notes = options["notes"].strip()
        skip_sync = options["skip_sync"]

        if not dataset_slug:
            raise CommandError("dataset-slug is required.")
        if not version_label:
            raise CommandError("version-label is required.")

        try:
            version, sync_summary = activate_geometry_version(
                dataset_slug=dataset_slug,
                version_label=version_label,
                operator_username=operator_username,
                notes=notes,
                sync_canonical_fields=not skip_sync,
            )
        except Exception as error:
            raise CommandError(str(error)) from error

        self.stdout.write(
            self.style.SUCCESS(
                json.dumps(
                    {
                        "dataset_slug": version.dataset.slug,
                        "version_label": version.version_label,
                        "is_active": version.is_active,
                        "activated_at": version.activated_at.isoformat() if version.activated_at else None,
                        "activated_by": version.activated_by.username if version.activated_by else None,
                        "notes": version.notes,
                        "sync_summary": sync_summary,
                    },
                    indent=2,
                )
            )
        )
