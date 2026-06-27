#!/usr/bin/env python3
"""import_threads_metrics_manual の純粋ER関数と再インポート重複防止を検証する（Sheets不要）。

- compute_engagement_rate: ER 計算の純粋関数
- save_pdca: 同じ result_id を2回流しても pdca_runs / suggestions を二重追記しない
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/import_threads_metrics_manual.py"


def _load():
    spec = importlib.util.spec_from_file_location("import_threads_metrics_manual", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class _FakeCell:
    def __init__(self, row):
        self.row = row


class _FakeWS:
    def __init__(self, headers):
        self.headers = headers
        self.rows: list[dict] = []
        self.append_count = 0

    def row_values(self, _n):
        return self.headers

    def find(self, value, in_column=None):
        col = self.headers[in_column - 1]
        for i, r in enumerate(self.rows):
            if str(r.get(col, "")) == value:
                return _FakeCell(i + 2)
        return None

    def append_row(self, values, value_input_option=None):
        self.append_count += 1
        self.rows.append(dict(zip(self.headers, values)))


class _FakeClient:
    def __init__(self):
        self.sheets = {
            "pdca_runs": _FakeWS(["run_id", "account_id", "best_er", "notes"]),
            "prompt_improvement_suggestions": _FakeWS(
                ["suggestion_id", "account_id", "status", "notes"]),
        }

    def _ws(self, logical):
        return self.sheets[logical]


def main() -> int:
    mod = _load()
    checks: list[tuple[str, bool]] = []

    # --- 純粋ER関数 ---
    checks.append(("ER=(likes+comments)/views", mod.compute_engagement_rate(200, 10, 10) == 0.1))
    checks.append(("views=0 は 0.0", mod.compute_engagement_rate(0, 5, 5) == 0.0))
    checks.append(("負views は 0.0", mod.compute_engagement_rate(-1, 5, 5) == 0.0))
    checks.append(("丸め4桁", mod.compute_engagement_rate(3, 1, 0) == round(1 / 3, 4)))

    # --- 重複防止 ---
    client = _FakeClient()
    row = {"result_id": "rid1", "account_id": "liver_manager", "views": 100, "likes": 8, "comments": 2}

    first = mod.save_pdca(client, row, "memo")
    checks.append(("初回 pdca 追記", first["pdca_appended"] is True))
    checks.append(("初回 suggestion 追記", first["suggestion_appended"] is True))
    checks.append(("初回 ER 計算", first["er"] == 0.1))

    second = mod.save_pdca(client, row, "memo")
    checks.append(("再インポートで pdca 追記しない", second["pdca_appended"] is False))
    checks.append(("再インポートで suggestion 追記しない", second["suggestion_appended"] is False))

    checks.append(("pdca_runs は1行だけ", client.sheets["pdca_runs"].append_count == 1))
    checks.append(("suggestions は1行だけ", client.sheets["prompt_improvement_suggestions"].append_count == 1))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
