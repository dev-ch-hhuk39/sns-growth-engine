"""Static regression checks for standalone immutable release capacity gates."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "scripts/install_buffered_production_runtime.sh"
DEPLOY = ROOT / "scripts/deploy_buffered_runtime_transaction.sh"
WORKFLOW = ROOT / ".github/workflows/deploy-buffered-production-runtime.yml"


class ImmutableReleaseCapacityTests(unittest.TestCase):
    def test_new_stage_requires_9_gib(self):
        src = INSTALL.read_text(encoding="utf-8")
        guard = 'if [[ "$STAGE_ONLY" == "true" && ! -d "$target" ]]; then'
        self.assertIn(guard, src)
        start = src.index(guard)
        self.assertLess(start, src.index('stage="$(mktemp -d'))
        self.assertIn('check_chadult_vps_deploy_preflight.sh" --min-free-gib 9',
                      src[start:src.index("\nfi", start)])

    def test_scheduler_only_does_not_enter_new_stage_reserve_guard(self):
        src = INSTALL.read_text(encoding="utf-8")
        guard = 'if [[ "$STAGE_ONLY" == "true" && ! -d "$target" ]]; then'
        block = src[src.index(guard):src.index("\nfi", src.index(guard))]
        self.assertNotIn('"$SCHEDULER_ONLY"', block)

    def test_after_stage_preflight_before_persisting_candidate(self):
        src = INSTALL.read_text(encoding="utf-8")
        deps = '-r "$stage/requirements-media-runtime.txt"'
        post = 'check_chadult_vps_deploy_preflight.sh" --min-free-gib 8'
        self.assertLess(src.index(deps), src.index(post, src.index(deps)))
        self.assertLess(src.index(post, src.index(deps)), src.index('mv "$stage" "$target"'))

    def test_failed_owned_stage_is_cleaned_and_release_untouched(self):
        src = INSTALL.read_text(encoding="utf-8")
        self.assertIn('trap cleanup_owned_stage EXIT', src)
        self.assertIn('rm -rf -- "$stage"', src)
        self.assertIn('! -L "$stage"', src)

    def test_transaction_requires_9_gib_and_keeps_poststage_check(self):
        src = DEPLOY.read_text(encoding="utf-8")
        self.assertIn('check_chadult_vps_deploy_preflight.sh" --min-free-gib 9', src)
        self.assertLess(src.index('--min-free-gib 8'), src.index('promoted=true'))

    def test_workflow_requires_9_gib(self):
        src = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('check_chadult_vps_deploy_preflight.sh --min-free-gib 9', src)

    def test_no_posting_mode_or_pointer_mutation_added_by_installer(self):
        src = INSTALL.read_text(encoding="utf-8")
        self.assertIn('if [[ "$STAGE_ONLY" == "true" ]]; then', src)
        self.assertIn('exit 0', src)
        self.assertNotIn('BUFFERED_POSTING_ENABLED=true', src)


if __name__ == "__main__":
    unittest.main()
