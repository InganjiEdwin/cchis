import json
from collections import defaultdict
from datetime import date
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from risk.source_data.phase_auditor import (
    AcceptedGap,
    IMPLEMENTATION_CLAIM_CHECKS,
    PHASE_AUDIT_CONTRACT,
    PHASE_NAMES,
    CLAIMED_IMPLEMENTED,
    run_source_data_phase_audit,
)


class SourceDataPhaseTenAuditorTests(SimpleTestCase):
    def _write_claimed_artifacts(self, repo_root: Path) -> None:
        artifact_content: dict[Path, set[str]] = defaultdict(set)
        for check in IMPLEMENTATION_CLAIM_CHECKS:
            artifact_content[repo_root / check.path].update(check.required_substrings)

        for path, required_substrings in artifact_content.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(sorted(required_substrings)), encoding="utf-8")

    def test_auditor_lists_all_phases_and_passes_when_claimed_artifacts_exist(self):
        with TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._write_claimed_artifacts(repo_root)

            report = run_source_data_phase_audit(repo_root, today=date(2026, 5, 5))

            self.assertTrue(report.passed)
            self.assertEqual({phase.phase for phase in report.phases}, set(PHASE_NAMES))
            self.assertEqual(
                {phase.phase for phase in report.phases if phase.claim_status == CLAIMED_IMPLEMENTED},
                set(PHASE_NAMES),
            )
            self.assertEqual(report.summary["claimed_implemented_count"], 11)
            self.assertGreaterEqual(report.summary["check_count"], 50)

    def test_auditor_reports_missing_claimed_artifact_as_gap(self):
        with TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._write_claimed_artifacts(repo_root)
            (repo_root / "backend/risk/source_data/phase0.py").unlink()

            report = run_source_data_phase_audit(repo_root, today=date(2026, 5, 5))
            phase_zero = next(phase for phase in report.phases if phase.phase == 0)

            self.assertFalse(report.passed)
            self.assertTrue(any("phase0_contract_module:missing" in gap for gap in phase_zero.gaps))

    def test_auditor_reports_incomplete_claimed_artifact_as_gap(self):
        with TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._write_claimed_artifacts(repo_root)
            (repo_root / "docs/SOURCE_DATA_OPS_SURFACE_IMPLEMENTATION_PLAN.md").write_text(
                "## Phase 10: External Audit And Gap Closure\n",
                encoding="utf-8",
            )

            report = run_source_data_phase_audit(repo_root, today=date(2026, 5, 5))
            phase_ten = next(phase for phase in report.phases if phase.phase == 10)
            incomplete_check = next(check for check in phase_ten.checks if check.check_id == "phase10_plan_section")

            self.assertFalse(report.passed)
            self.assertTrue(any("phase10_plan_section:incomplete" in gap for gap in phase_ten.gaps))
            self.assertIn(
                "compare claimed implementation artifacts against the repository",
                incomplete_check.missing_substrings,
            )

    def test_auditor_reports_forbidden_claimed_artifact_content_as_gap(self):
        with TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._write_claimed_artifacts(repo_root)
            validation_path = repo_root / "backend/risk/source_data/validation.py"
            validation_path.write_text(
                validation_path.read_text(encoding="utf-8")
                + '\n"sample_rows": inspection.get("sample_rows")\n',
                encoding="utf-8",
            )

            report = run_source_data_phase_audit(repo_root, today=date(2026, 5, 5))
            phase_two = next(phase for phase in report.phases if phase.phase == 2)
            validation_check = next(check for check in phase_two.checks if check.check_id == "phase2_dry_validation")

            self.assertFalse(report.passed)
            self.assertTrue(any("phase2_dry_validation:incomplete" in gap for gap in phase_two.gaps))
            self.assertIn('"sample_rows": inspection.get', validation_check.forbidden_substrings_present)

    def test_accepted_gap_requires_owner_reason_and_expiry(self):
        with TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._write_claimed_artifacts(repo_root)
            (repo_root / "backend/risk/source_data/phase0.py").unlink()

            accepted_report = run_source_data_phase_audit(
                repo_root,
                accepted_gaps=(
                    AcceptedGap(
                        phase=0,
                        check_id="phase0_contract_module",
                        owner="source-data-owner",
                        reason="Documented temporary packaging issue.",
                        expires_at="2026-06-01",
                    ),
                ),
                today=date(2026, 5, 5),
            )
            phase_zero = next(phase for phase in accepted_report.phases if phase.phase == 0)
            accepted_check = next(check for check in phase_zero.checks if check.check_id == "phase0_contract_module")

            self.assertTrue(accepted_report.passed)
            self.assertEqual(accepted_check.status, "accepted_missing")
            self.assertEqual(accepted_report.summary["accepted_gap_count"], 1)

            expired_report = run_source_data_phase_audit(
                repo_root,
                accepted_gaps=(
                    AcceptedGap(
                        phase=0,
                        check_id="phase0_contract_module",
                        owner="",
                        reason="",
                        expires_at="2026-05-01",
                    ),
                ),
                today=date(2026, 5, 5),
            )
            expired_check = next(
                check
                for phase in expired_report.phases
                for check in phase.checks
                if check.check_id == "phase0_contract_module"
            )

            self.assertFalse(expired_report.passed)
            self.assertIn("accepted_gap_owner_required", expired_check.acceptance_errors)
            self.assertIn("accepted_gap_reason_required", expired_check.acceptance_errors)
            self.assertIn("accepted_gap_expired", expired_check.acceptance_errors)

    def test_report_is_metadata_only(self):
        with TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._write_claimed_artifacts(repo_root)

            payload = json.dumps(run_source_data_phase_audit(repo_root, today=date(2026, 5, 5)).as_dict())

            self.assertNotIn("+254712345678", payload)
            self.assertNotIn("raw_row", payload)
            self.assertNotIn("stockout_notes_value", payload)

    def test_management_command_outputs_json_report(self):
        with TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._write_claimed_artifacts(repo_root)
            stdout = StringIO()

            call_command(
                "audit_source_data_phases",
                repo_root=str(repo_root),
                format="json",
                stdout=stdout,
            )
            payload = json.loads(stdout.getvalue())

            self.assertTrue(payload["passed"])
            self.assertEqual(payload["summary"]["claimed_implemented_count"], 11)

        with TemporaryDirectory() as empty_directory:
            with self.assertRaises(CommandError):
                call_command(
                    "audit_source_data_phases",
                    repo_root=empty_directory,
                    strict=True,
                    stdout=StringIO(),
                )

        with TemporaryDirectory() as empty_directory:
            with self.settings(SOURCE_DATA_PHASE_AUDIT_REQUIRED=True):
                with self.assertRaises(CommandError):
                    call_command(
                        "audit_source_data_phases",
                        repo_root=empty_directory,
                        stdout=StringIO(),
                    )

    def test_phase_contract_has_a_claim_for_every_named_phase(self):
        self.assertEqual({contract.phase for contract in PHASE_AUDIT_CONTRACT}, set(PHASE_NAMES))
        for contract in PHASE_AUDIT_CONTRACT:
            self.assertEqual(contract.name, PHASE_NAMES[contract.phase])
            self.assertTrue(contract.checks)
            self.assertTrue(all(check.phase == contract.phase for check in contract.checks))
