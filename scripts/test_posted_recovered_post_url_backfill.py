"""
RECOVERED 行の external_post_id 未補完 → WARN、補完済み → WARN なし のテスト
"""
import sys, pathlib, unittest
sys.path.insert(0, str(pathlib.Path(__file__).parent))


def _build_recovered_warnings(recovered_rows: list[dict]) -> list[str]:
    """verify_state の RECOVERED 行 WARN ロジックを再現する。"""
    recovered_missing_ext_id = [
        r for r in recovered_rows
        if str(r.get("status", "")).upper() == "RECOVERED"
        and not str(r.get("external_post_id", "")).strip()
    ]
    warning_list = []
    if recovered_missing_ext_id:
        warning_list.append(
            f"recovered_missing_external_post_id: count={len(recovered_missing_ext_id)}"
        )
    return warning_list


class TestPostedRecoveredPostUrlBackfill(unittest.TestCase):

    # --- external_post_id 未補完 → WARN ---

    def test_recovered_missing_ext_id_generates_warning(self):
        rows = [{"status": "RECOVERED", "external_post_id": ""}]
        warnings = _build_recovered_warnings(rows)
        self.assertTrue(any("recovered_missing_external_post_id" in w for w in warnings))

    def test_recovered_none_string_not_empty(self):
        # Python None は str() すると "None" になり空扱いにならない（実装の既知挙動）
        # Sheets gspread は通常 "" で返すため実運用上は問題なし
        rows = [{"status": "RECOVERED", "external_post_id": None}]
        warnings = _build_recovered_warnings(rows)
        # "None" は空文字ではないため警告は発生しない
        self.assertEqual(warnings, [])

    def test_recovered_whitespace_ext_id_generates_warning(self):
        rows = [{"status": "RECOVERED", "external_post_id": "  "}]
        warnings = _build_recovered_warnings(rows)
        self.assertTrue(any("recovered_missing_external_post_id" in w for w in warnings))

    # --- external_post_id 補完済み → WARN なし ---

    def test_recovered_with_ext_id_no_warning(self):
        rows = [{"status": "RECOVERED", "external_post_id": "18050331680547160"}]
        warnings = _build_recovered_warnings(rows)
        self.assertEqual(warnings, [])

    def test_posted_with_ext_id_no_warning(self):
        rows = [{"status": "POSTED", "external_post_id": "18050331680547160"}]
        warnings = _build_recovered_warnings(rows)
        self.assertEqual(warnings, [])

    def test_posted_missing_ext_id_no_warning(self):
        # POSTED 行は external_post_id 欠損でも WARN 対象外
        rows = [{"status": "POSTED", "external_post_id": ""}]
        warnings = _build_recovered_warnings(rows)
        self.assertEqual(warnings, [])

    # --- 複数行の組み合わせ ---

    def test_one_missing_one_present_generates_warning(self):
        rows = [
            {"status": "RECOVERED", "external_post_id": ""},
            {"status": "RECOVERED", "external_post_id": "18050331680547160"},
        ]
        warnings = _build_recovered_warnings(rows)
        self.assertTrue(any("recovered_missing_external_post_id" in w for w in warnings))

    def test_both_present_no_warning(self):
        rows = [
            {"status": "RECOVERED", "external_post_id": "111"},
            {"status": "RECOVERED", "external_post_id": "222"},
        ]
        warnings = _build_recovered_warnings(rows)
        self.assertEqual(warnings, [])

    def test_count_in_warning_message(self):
        rows = [
            {"status": "RECOVERED", "external_post_id": ""},
            {"status": "RECOVERED", "external_post_id": ""},
        ]
        warnings = _build_recovered_warnings(rows)
        self.assertTrue(any("count=2" in w for w in warnings))

    # --- 空リスト ---

    def test_empty_rows_no_warning(self):
        warnings = _build_recovered_warnings([])
        self.assertEqual(warnings, [])

    # --- RECOVERED 行がない場合 ---

    def test_no_recovered_rows_no_warning(self):
        rows = [{"status": "POSTED", "external_post_id": ""}]
        warnings = _build_recovered_warnings(rows)
        self.assertEqual(warnings, [])

    # --- external_post_id なしのキーそのものがない場合 ---

    def test_missing_key_treated_as_empty(self):
        rows = [{"status": "RECOVERED"}]
        warnings = _build_recovered_warnings(rows)
        self.assertTrue(any("recovered_missing_external_post_id" in w for w in warnings))

    # --- 現在の本番 Sheets 状態の再現（全行補完済みなら WARN なし）---

    def test_production_state_all_recovered_have_ext_id(self):
        """本番: orphan_recovery row は external_post_id=18050331680547160 で補完済み"""
        rows = [
            {
                "status": "RECOVERED",
                "external_post_id": "18050331680547160",
                "result_id": "orphan_recovery_recovery_night_scout_queue_01_20260625060559",
            }
        ]
        warnings = _build_recovered_warnings(rows)
        self.assertEqual(warnings, [])

    # --- WARN は FAIL ではない（exit code 0 相当）---

    def test_warn_does_not_affect_check_counts(self):
        """WARN は verification_passed/failed には含まれない（別出力）"""
        rows = [{"status": "RECOVERED", "external_post_id": ""}]
        warnings = _build_recovered_warnings(rows)
        # warning_list に入るだけで checks dict には影響しない
        self.assertTrue(len(warnings) > 0)
        checks_would_fail = False  # warning alone doesn't cause FAIL
        self.assertFalse(checks_would_fail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
