import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder

from risk.source_data.phase_auditor import run_source_data_phase_audit


class Command(BaseCommand):
    help = "Audit source-data ops implementation phase claims against repository artifacts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--repo-root",
            default=None,
            help="Repository root to audit. Defaults to the project root inferred from the auditor module.",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format for the audit report.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit with an error when the phase audit reports unaccepted gaps.",
        )

    def handle(self, *args, **options):
        report = run_source_data_phase_audit(options["repo_root"])

        if options["format"] == "json":
            self.stdout.write(json.dumps(report.as_dict(), cls=DjangoJSONEncoder, indent=2, sort_keys=True))
        else:
            self.stdout.write(f"Source-data phase audit: {'passed' if report.passed else 'failed'}")
            self.stdout.write(f"Summary: {report.summary}")
            for phase in report.phases:
                self.stdout.write(
                    f"- Phase {phase.phase}: {phase.claim_status}; "
                    f"checks={len(phase.checks)} gaps={len(phase.gaps)} accepted={len(phase.accepted_gaps)}"
                )
                for gap in phase.gaps:
                    self.stdout.write(f"  gap={gap}")
                for accepted_gap in phase.accepted_gaps:
                    self.stdout.write(f"  accepted={accepted_gap}")

        strict_required = options["strict"] or getattr(settings, "SOURCE_DATA_PHASE_AUDIT_REQUIRED", False)
        if strict_required and not report.passed:
            raise CommandError("Source-data phase audit finished with unaccepted gaps.")
