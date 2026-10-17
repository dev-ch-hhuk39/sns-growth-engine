"""SNS immutable release disk headroom is measured before and after dependency staging.

These tests inspect code paths; the shared VPS gate itself is verified on the VPS
under the ops-owned preflight. No service or production data is changed by tests.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts/install_buffered_production_runtime.sh"
DEPLOY = ROOT / "scripts/deploy_buffered_runtime_transaction.sh"
WORKFLOW = ROOT / ".github/workflows/deploy-buffered-production-runtime.yml"


class ImmutableReleaseCapacityTests(unittest.TestCase):
    def test_new_stage_requires_9_gib(self):
        source = INSTALL.read_text(encoding="utf-8")
        guard = 'if [[ "$STAGE_ONLY" == "true" && ! -d "$target" ]]; then'
        self.assertIn(guard, source)
        self.assertIn('check_chadult_vps_deploy_preflight.sh" --min-free-gib 9', source)
        self.assertLess(source.index(guard), source.index('stage="$(mktemp -d'))

    def test_existing_scheduler_mode_does_not_require_new_stage_headroom(self):
        source = INSTALL.read_text(encoding="utf-8")
        self.assertIn('if [[ "$SCHEDULER_ONLY" == "true" ]]; then', source)
        guard_start = source.index('if [[ "$STAGE_ONLY" == "true" && ! -d "$target" ]]; then')
        guard_end = source.index("\nfi", guard_start)
        self.assertNotIn('"$SCHEDULER_ONLY"', source[guard_start:guard_end])

    def test_stage_checks_8_gib_before_promotion(self):
        source = INSTALL.read_text(encoding="utf-8")
        marker = '-r "$stage/requirements-media-runtime.txt"'
        self.assertLess(source.index(marker), source.index('check_chadult_vps_deploy_preflight.sh" --min-free-gib 8', source.index(marker)))
        self.assertLess(source.index('check_chadult_vps_deploy_preflight.sh" --min-free-gib 8', source.index(marker)), source.index('mv "$stage" "$target"'))

    def test_interrupted_stage_remains_only_owned_cleanup(self):
        source = INSTALL.read_text(encoding="utf-8")
        self.assertIn('trap cleanup_owned_stage EXIT', source)
        self.assertIn('[[ -n "$stage" && -d "$stage" && ! -L "$stage" &&', source)
        self.assertIn('rm -rf -- "$stage"', source)

    def test_global_deploy_transaction_uses_9_gib(self):
        source = DEPLOY.read_text(encoding="utf-8")
        self.assertIn('check_chadult_vps_deploy_preflight.sh" --min-free-gib 9', source)
        self.assertIn('flock -x -w 600 9', source)

    def test_github_job_preflights_at_9_gib(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("scripts/check_chadult_vps_deploy_preflight.sh --min-free-gib 9", source)
        self.assertIn("runs-on: [self-hosted, Linux, X64]", source)

    def test_no_implicit_posting_change(self):
        source = DEPLOY.read_text(encoding="utf-8")
        self.assertIn("requested_posting=", source)
        self.assertIn('case "$requested_posting" in true|false)', source)
        self.assertIn("completed=true", source)


if __name__ == "__main__":
    unittest.main()
