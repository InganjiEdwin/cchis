from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from risk.source_data.phase_auditor import (
    IMPLEMENTATION_CLAIM_CHECKS,
    PHASE_NAMES,
    run_source_data_phase_audit,
)


class SourceDataPhaseAuditorTests(TestCase):
    def _write_claimed_artifacts(self, repo_root: Path) -> None:
        artifact_content: dict[Path, set[str]] = {}
        for check in IMPLEMENTATION_CLAIM_CHECKS:
            path = repo_root / check.path
            artifact_content.setdefault(path, set()).update(check.required_substrings)

        for path, required_substrings in artifact_content.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(sorted(required_substrings)), encoding="utf-8")

    def test_auditor_passes_when_claimed_phase_artifacts_exist(self):
        with TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._write_claimed_artifacts(repo_root)

            report = run_source_data_phase_audit(repo_root)

            self.assertTrue(report.passed)
            self.assertEqual({phase.phase for phase in report.phases}, set(PHASE_NAMES))
            claimed_phases = {phase.phase for phase in report.phases if phase.claim_status == "claimed_implemented"}
            self.assertEqual(claimed_phases, {0, 1, 2, 10})

    def test_auditor_reports_missing_claimed_artifact_as_gap(self):
        with TemporaryDirectory() as directory:
            repo_root = Path(directory)
            self._write_claimed_artifacts(repo_root)
            (repo_root / "backend/risk/source_data/phase0.py").unlink()

            report = run_source_data_phase_audit(repo_root)
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

            report = run_source_data_phase_audit(repo_root)
            phase_ten = next(phase for phase in report.phases if phase.phase == 10)

            self.assertFalse(report.passed)
            self.assertTrue(any("phase10_plan_section:incomplete" in gap for gap in phase_ten.gaps))
