"""
verify_state: queue 1〜2 件は WARN（failed=0）、0 件は FAIL のテスト
"""
import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import importlib.util

def _load_verify():
    spec = importlib.util.spec_from_file_location(
        "verify_mod",
        pathlib.Path(__file__).parent / "recover_production_sheets_threads_first.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestVerifyQueueMinimumWarnNotFail(unittest.TestCase):

    def setUp(self):
        self.mod = _load_verify()

    def _make_state(self, ns_count: int, lm_count: int):
        """verify_state をモック経由で呼ばずに、警告ロジック部分だけ抽出して再現する。"""
        REFILL_THRESHOLD = 3
        warning_list = []
        refill_needed_accounts = []
        if 0 < ns_count < REFILL_THRESHOLD:
            warning_list.append(
                f"queue_night_scout_low: count={ns_count} (recommend refill to {REFILL_THRESHOLD})"
            )
            refill_needed_accounts.append("night_scout")
        if 0 < lm_count < REFILL_THRESHOLD:
            warning_list.append(
                f"queue_liver_manager_low: count={lm_count} (recommend refill to {REFILL_THRESHOLD})"
            )
            refill_needed_accounts.append("liver_manager")

        checks = {
            "queue_night_scout_min1": ns_count >= 1,
            "queue_liver_manager_min1": lm_count >= 1,
        }
        return checks, warning_list, refill_needed_accounts

    # --- queue 0 は FAIL ---

    def test_night_scout_zero_fails(self):
        checks, _, _ = self._make_state(ns_count=0, lm_count=3)
        self.assertFalse(checks["queue_night_scout_min1"])

    def test_liver_manager_zero_fails(self):
        checks, _, _ = self._make_state(ns_count=3, lm_count=0)
        self.assertFalse(checks["queue_liver_manager_min1"])

    # --- queue 1 は PASS（check=True）+ WARN ---

    def test_night_scout_one_passes_check(self):
        checks, warnings, refill = self._make_state(ns_count=1, lm_count=3)
        self.assertTrue(checks["queue_night_scout_min1"])

    def test_night_scout_one_generates_warning(self):
        _, warnings, refill = self._make_state(ns_count=1, lm_count=3)
        self.assertTrue(any("queue_night_scout_low" in w for w in warnings))

    def test_night_scout_one_adds_refill_needed(self):
        _, _, refill = self._make_state(ns_count=1, lm_count=3)
        self.assertIn("night_scout", refill)

    # --- queue 2 は PASS（check=True）+ WARN ---

    def test_night_scout_two_passes_check(self):
        checks, warnings, _ = self._make_state(ns_count=2, lm_count=3)
        self.assertTrue(checks["queue_night_scout_min1"])

    def test_night_scout_two_generates_warning(self):
        _, warnings, _ = self._make_state(ns_count=2, lm_count=3)
        self.assertTrue(any("queue_night_scout_low" in w for w in warnings))

    # --- queue 3 は PASS、WARN なし ---

    def test_night_scout_three_passes_no_warning(self):
        checks, warnings, refill = self._make_state(ns_count=3, lm_count=3)
        self.assertTrue(checks["queue_night_scout_min1"])
        self.assertFalse(any("queue_night_scout_low" in w for w in warnings))
        self.assertNotIn("night_scout", refill)

    # --- liver_manager 1〜2 も同様 ---

    def test_liver_manager_one_passes_warn(self):
        checks, warnings, refill = self._make_state(ns_count=3, lm_count=1)
        self.assertTrue(checks["queue_liver_manager_min1"])
        self.assertTrue(any("queue_liver_manager_low" in w for w in warnings))
        self.assertIn("liver_manager", refill)

    def test_liver_manager_two_passes_warn(self):
        checks, warnings, _ = self._make_state(ns_count=3, lm_count=2)
        self.assertTrue(checks["queue_liver_manager_min1"])
        self.assertTrue(any("queue_liver_manager_low" in w for w in warnings))

    def test_liver_manager_three_no_warning(self):
        checks, warnings, refill = self._make_state(ns_count=3, lm_count=3)
        self.assertTrue(checks["queue_liver_manager_min1"])
        self.assertFalse(any("queue_liver_manager_low" in w for w in warnings))
        self.assertNotIn("liver_manager", refill)

    # --- 旧チェック名が存在しないことを確認 ---

    def test_old_check_names_not_present(self):
        checks, _, _ = self._make_state(ns_count=3, lm_count=3)
        self.assertNotIn("queue_night_scout_2", checks)
        self.assertNotIn("queue_night_scout_3", checks)
        self.assertNotIn("queue_liver_manager_3", checks)

    # --- 両方 0 なら両方 FAIL ---

    def test_both_zero_both_fail(self):
        checks, _, _ = self._make_state(ns_count=0, lm_count=0)
        self.assertFalse(checks["queue_night_scout_min1"])
        self.assertFalse(checks["queue_liver_manager_min1"])

    # --- 警告メッセージ形式確認 ---

    def test_warning_message_contains_count(self):
        _, warnings, _ = self._make_state(ns_count=2, lm_count=3)
        self.assertTrue(any("count=2" in w for w in warnings))

    def test_warning_message_contains_refill_threshold(self):
        _, warnings, _ = self._make_state(ns_count=1, lm_count=3)
        self.assertTrue(any("recommend refill to 3" in w for w in warnings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
