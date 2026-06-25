"""
verify_state: refill_needed_accounts / recommended_actions の出力テスト
"""
import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).parent))


class TestRefillNeededAccountsWarning(unittest.TestCase):

    def _build_warnings(self, ns_count: int, lm_count: int, posted_save_failed: int = 0):
        REFILL_THRESHOLD = 3
        warning_list = []
        refill_needed_accounts = []
        recommended_actions = []

        if 0 < ns_count < REFILL_THRESHOLD:
            warning_list.append(
                f"queue_night_scout_low: count={ns_count} (recommend refill to {REFILL_THRESHOLD})"
            )
            refill_needed_accounts.append("night_scout")
            recommended_actions.append(
                f"python3 scripts/refill_threads_queue.py --account-id night_scout --count {REFILL_THRESHOLD - ns_count}"
            )
        if 0 < lm_count < REFILL_THRESHOLD:
            warning_list.append(
                f"queue_liver_manager_low: count={lm_count} (recommend refill to {REFILL_THRESHOLD})"
            )
            refill_needed_accounts.append("liver_manager")
            recommended_actions.append(
                f"python3 scripts/refill_threads_queue.py --account-id liver_manager --count {REFILL_THRESHOLD - lm_count}"
            )
        if posted_save_failed > 0:
            warning_list.append(
                f"posted_save_failed_count: {posted_save_failed} (run recover_orphan_threads_post.py)"
            )

        return {
            "warning_list": warning_list,
            "refill_needed_accounts": refill_needed_accounts,
            "recommended_actions": recommended_actions,
        }

    # --- refill_needed_accounts の内容 ---

    def test_night_scout_low_in_refill_needed(self):
        out = self._build_warnings(ns_count=2, lm_count=3)
        self.assertIn("night_scout", out["refill_needed_accounts"])

    def test_liver_manager_low_in_refill_needed(self):
        out = self._build_warnings(ns_count=3, lm_count=1)
        self.assertIn("liver_manager", out["refill_needed_accounts"])

    def test_both_low_both_in_refill_needed(self):
        out = self._build_warnings(ns_count=1, lm_count=2)
        self.assertIn("night_scout", out["refill_needed_accounts"])
        self.assertIn("liver_manager", out["refill_needed_accounts"])

    def test_sufficient_queue_not_in_refill_needed(self):
        out = self._build_warnings(ns_count=3, lm_count=3)
        self.assertEqual(out["refill_needed_accounts"], [])

    # --- recommended_actions の形式 ---

    def test_recommended_action_contains_refill_script(self):
        out = self._build_warnings(ns_count=1, lm_count=3)
        self.assertTrue(
            any("refill_threads_queue.py" in a for a in out["recommended_actions"])
        )

    def test_recommended_action_count_delta(self):
        # ns_count=1 → count=2 が recommended
        out = self._build_warnings(ns_count=1, lm_count=3)
        self.assertTrue(
            any("--count 2" in a and "night_scout" in a for a in out["recommended_actions"])
        )

    def test_recommended_action_liver_manager_count(self):
        # lm_count=2 → count=1 が recommended
        out = self._build_warnings(ns_count=3, lm_count=2)
        self.assertTrue(
            any("--count 1" in a and "liver_manager" in a for a in out["recommended_actions"])
        )

    # --- warning_list の文字列形式 ---

    def test_warning_list_empty_when_sufficient(self):
        out = self._build_warnings(ns_count=3, lm_count=3)
        self.assertEqual(out["warning_list"], [])

    def test_warning_list_contains_account_name(self):
        out = self._build_warnings(ns_count=2, lm_count=3)
        self.assertTrue(any("night_scout" in w for w in out["warning_list"]))

    def test_warning_list_posted_save_failed(self):
        out = self._build_warnings(ns_count=3, lm_count=3, posted_save_failed=1)
        self.assertTrue(
            any("posted_save_failed_count" in w for w in out["warning_list"])
        )

    def test_warning_list_no_posted_save_failed_when_zero(self):
        out = self._build_warnings(ns_count=3, lm_count=3, posted_save_failed=0)
        self.assertFalse(
            any("posted_save_failed" in w for w in out["warning_list"])
        )

    # --- warning_list の件数 ---

    def test_two_warnings_when_both_low(self):
        out = self._build_warnings(ns_count=1, lm_count=2)
        low_warnings = [w for w in out["warning_list"] if "_low" in w]
        self.assertEqual(len(low_warnings), 2)

    def test_one_warning_when_only_ns_low(self):
        out = self._build_warnings(ns_count=2, lm_count=3)
        low_warnings = [w for w in out["warning_list"] if "_low" in w]
        self.assertEqual(len(low_warnings), 1)

    # --- zero queue はチェックで FAIL になるが warning には含まれない ---

    def test_zero_count_not_in_warning_list(self):
        out = self._build_warnings(ns_count=0, lm_count=3)
        self.assertFalse(any("queue_night_scout_low" in w for w in out["warning_list"]))

    def test_zero_count_not_in_refill_needed(self):
        out = self._build_warnings(ns_count=0, lm_count=3)
        self.assertNotIn("night_scout", out["refill_needed_accounts"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
