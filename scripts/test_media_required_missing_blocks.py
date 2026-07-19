#!/usr/bin/env python3
"""media_required=true なのに使える media_url が無い行は投稿せず
DRY_RUN_BLOCKED / MEDIA_REQUIRED_MISSING を返すことを検証する（Sheets書き込みなし）。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/process_threads_queue.py"


def _load():
    spec = importlib.util.spec_from_file_location("process_threads_queue", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


_LOGS_HEADERS = ["log_id", "timestamp", "account_id", "operation", "level", "status", "message", "details"]


class _FakeWS:
    def __init__(self, rows, headers=None):
        self._rows = rows
        self._headers = headers or (list(rows[0].keys()) if rows else [])

    def get_all_records(self):
        return [dict(r) for r in self._rows]

    def row_values(self, _n):
        return self._headers

    def append_row(self, values, value_input_option=None):
        self._rows.append(dict(zip(self._headers, values)))


class _FakeClient:
    """タブごとに _FakeWS を永続保持する（append が次回も見える・id が安定）。"""

    def __init__(self, tabs):
        self._ws_by_tab = {
            logical: _FakeWS(rows, _LOGS_HEADERS if logical == "logs" else None)
            for logical, rows in tabs.items()
        }

    def _ws(self, logical):
        if logical not in self._ws_by_tab:
            self._ws_by_tab[logical] = _FakeWS([], _LOGS_HEADERS if logical == "logs" else [])
        return self._ws_by_tab[logical]


def main() -> int:
    mod = _load()
    rqm = mod.resolve_queue_media
    checks: list[tuple[str, bool]] = []

    # block_reason 判定（純粋関数）
    checks.append(("required+url無し→block", rqm({"media_required": "true"})["block_reason"] == "MEDIA_REQUIRED_MISSING"))
    checks.append(("required+PENDING→block", rqm({"media_required": "true", "media_url": "https://x/p.png", "media_status": "PENDING"})["block_reason"] == "MEDIA_REQUIRED_MISSING"))
    checks.append(("required+ATTACHED+url→非block", rqm({"media_required": "true", "media_url": "https://x/a.png", "media_status": "ATTACHED"})["block_reason"] == ""))
    checks.append(("required無し→非block", rqm({"media_url": ""})["block_reason"] == ""))

    drafts = [{
        "draft_id": "d1",
        "body_md": (
            "夜職で店を選ぶときは、時給だけで決めると続けにくくなることがあります。\n\n"
            "客層や出勤ペース、相談のしやすさまで確認して、自分が無理なく続けられる環境かを整理することが大切です。"
        ),
    }]
    client = _FakeClient({"social_derivatives": [], "drafts": drafts, "posted_results": [], "logs": []})

    # process_one: media_required=true・url無し → DRY_RUN_BLOCKED（dry-run）
    row = {"queue_id": "q1", "draft_id": "d1", "account_id": "night_scout",
           "platform": "threads", "media_required": "true"}
    out = mod.process_one(client, row, dry_run=True, confirm_real_post=False)
    checks.append(("dry-run: status=DRY_RUN_BLOCKED", out["status"] == "DRY_RUN_BLOCKED"))
    checks.append(("dry-run: reason=MEDIA_REQUIRED_MISSING", out["reason"] == "MEDIA_REQUIRED_MISSING"))

    # process_one: real モードでも投稿に到達せずブロックされる
    out_real = mod.process_one(client, row, dry_run=False, confirm_real_post=True)
    checks.append(("real: status=DRY_RUN_BLOCKED", out_real["status"] == "DRY_RUN_BLOCKED"))

    # 後方互換: media_required 無しの通常行はブロックされない（DRY_RUN になる）
    row_plain = {"queue_id": "q2", "draft_id": "d1", "account_id": "night_scout", "platform": "threads"}
    out_plain = mod.process_one(client, row_plain, dry_run=True, confirm_real_post=False)
    checks.append(("通常行はブロックされない", out_plain["status"] == "DRY_RUN"))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
