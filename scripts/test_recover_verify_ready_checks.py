#!/usr/bin/env python3
"""recover_production_sheets_threads_first.verify_state の READY 必須化チェックを検証する。

検証対象チェック（生成データは 0 READY のため live verify では空回りする。ここで合成
フィクスチャを差し込み、clean=True / violation=False を実際に発火させて回帰固定する）:
  - generated_candidates_not_ready_by_default
  - no_ready_for_x_or_beauty
  - no_media_required_without_media_url
  - no_unapproved_media_ready
  - no_reference_only_media_ready

重点（BLOCKER #1 回帰固定）:
  人間が approve_queue.py で承認した生成候補は status=READY かつ generation_mode が残るが、
  logs タブに queue_approved の証跡があるため誤検知しない（generated_candidates_not_ready_by_default=True）。

media は media_url 埋め込みだけでなく media_asset_id 参照でも権利チェックが効くことも固定する。
Sheets 不要。FakeClient で各タブの records を差し込んで verify_state を直接呼ぶ。
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/recover_production_sheets_threads_first.py"


def _load():
    spec = importlib.util.spec_from_file_location("recover_production_sheets_threads_first", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class _FakeWS:
    def __init__(self, rows):
        self.rows = rows

    def get_all_records(self):
        return [dict(r) for r in self.rows]


class _FakeClient:
    dry_run = True

    def __init__(self, tabs):
        self._tabs = tabs

    def _ws(self, logical):
        return _FakeWS(self._tabs.get(logical, []))


def _base_tabs():
    return {
        "accounts": [],
        "content_categories": [],
        "prompt_templates": [],
        "queue": [],
        "posted_results": [],
        "learning_rules": [],
        "media_assets": [],
        "source_accounts": [],
        "reference_sources": [],
        "source_account_posts": [],
        "reference_post_scores": [],
        "social_derivatives": [],
        "drafts": [],
        "prompt_improvement_suggestions": [],
        "logs": [],
    }


def main() -> int:
    mod = _load()
    checks: list[tuple[str, bool]] = []

    # === clean: READY チェックが全て True ===
    clean = _base_tabs()
    clean["queue"] = [
        # 手動 READY・threads・media なし → 全チェック安全
        {"queue_id": "q_manual", "account_id": "night_scout", "platform": "threads",
         "status": "READY", "generation_mode": "manual"},
        # 生成候補だが人間が承認済み（logs に queue_approved あり）→ 誤検知しない（BLOCKER #1）
        {"queue_id": "q_gen_approved", "account_id": "night_scout", "platform": "threads",
         "status": "READY", "generation_mode": "metrics_driven_candidate"},
        # 生成候補は通常 WAITING_REVIEW のまま（worker 非対象・承認不要）
        {"queue_id": "q_gen_waiting", "account_id": "night_scout", "platform": "threads",
         "status": "WAITING_REVIEW", "generation_mode": "metrics_driven_candidate"},
        # READY・media_asset_id 参照・権利クリア素材
        {"queue_id": "q_media_ok", "account_id": "night_scout", "platform": "threads",
         "status": "READY", "generation_mode": "manual",
         "media_required": "true", "media_asset_id": "m_ok"},
    ]
    clean["media_assets"] = [
        {"media_asset_id": "m_ok", "approval_status": "APPROVED", "status": "APPROVED",
         "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned",
         "cloudinary_url": "https://res.cloudinary.com/x/ok.png"},
    ]
    clean["logs"] = [
        {"operation": "queue_approved", "status": "OK",
         "message": "queue_approved: queue_id=q_gen_approved WAITING_REVIEW→READY",
         "details": "queue_id=q_gen_approved platform=threads reason='ok'"},
    ]
    res = mod.verify_state(_FakeClient(clean))["checks"]
    checks.append(("clean: generated_candidates_not_ready_by_default(承認済み生成READYは誤検知しない)",
                   res["generated_candidates_not_ready_by_default"] is True))
    checks.append(("clean: no_ready_for_x_or_beauty", res["no_ready_for_x_or_beauty"] is True))
    checks.append(("clean: no_media_required_without_media_url", res["no_media_required_without_media_url"] is True))
    checks.append(("clean: no_unapproved_media_ready", res["no_unapproved_media_ready"] is True))
    checks.append(("clean: no_reference_only_media_ready", res["no_reference_only_media_ready"] is True))

    # === violation: generated READY without approval trail ===
    v1 = _base_tabs()
    v1["queue"] = [
        {"queue_id": "q_gen_noapprove", "account_id": "night_scout", "platform": "threads",
         "status": "READY", "generation_mode": "metrics_driven_candidate"},
    ]
    # logs は空（承認証跡なし）→ 違反
    res = mod.verify_state(_FakeClient(v1))["checks"]
    checks.append(("bad: 承認証跡なしの生成READYは違反 (=False)",
                   res["generated_candidates_not_ready_by_default"] is False))

    # === violation: x / beauty が READY ===
    v2 = _base_tabs()
    v2["queue"] = [
        {"queue_id": "q_x", "account_id": "night_scout", "platform": "x",
         "status": "READY", "generation_mode": "manual"},
        {"queue_id": "q_beauty", "account_id": "beauty_account", "platform": "threads",
         "status": "READY", "generation_mode": "manual"},
    ]
    res = mod.verify_state(_FakeClient(v2))["checks"]
    checks.append(("bad: x/beauty の READY は違反 (=False)", res["no_ready_for_x_or_beauty"] is False))

    # === violation: media 必須なのに media 参照なし ===
    v3 = _base_tabs()
    v3["queue"] = [
        {"queue_id": "q_nomedia", "account_id": "night_scout", "platform": "threads",
         "status": "READY", "generation_mode": "manual",
         "media_required": "true", "media_url": "", "media_asset_id": ""},
    ]
    res = mod.verify_state(_FakeClient(v3))["checks"]
    checks.append(("bad: media必須でmedia参照なしは違反 (=False)",
                   res["no_media_required_without_media_url"] is False))

    # === violation: media_asset_id 参照先が未承認 ===
    v4 = _base_tabs()
    v4["queue"] = [
        {"queue_id": "q_unapproved_media", "account_id": "night_scout", "platform": "threads",
         "status": "READY", "generation_mode": "manual",
         "media_required": "true", "media_asset_id": "m_unapproved"},
    ]
    v4["media_assets"] = [
        {"media_asset_id": "m_unapproved", "approval_status": "WAITING_REVIEW", "status": "WAITING_REVIEW",
         "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned",
         "cloudinary_url": "https://res.cloudinary.com/x/pending.png"},
    ]
    res = mod.verify_state(_FakeClient(v4))["checks"]
    checks.append(("bad: media_asset_id参照先が未承認は違反 (=False)",
                   res["no_unapproved_media_ready"] is False))

    # === violation: media_asset_id 参照先が reference_only / no_reuse ===
    v5 = _base_tabs()
    v5["queue"] = [
        {"queue_id": "q_refonly_media", "account_id": "night_scout", "platform": "threads",
         "status": "READY", "generation_mode": "manual",
         "media_required": "true", "media_asset_id": "m_refonly"},
    ]
    v5["media_assets"] = [
        {"media_asset_id": "m_refonly", "approval_status": "APPROVED", "status": "APPROVED",
         "rights_policy": "owned", "reuse_policy": "no_reuse", "media_policy": "owned",
         "use_status": "REFERENCE_ONLY",
         "cloudinary_url": "https://res.cloudinary.com/x/ref.png"},
    ]
    res = mod.verify_state(_FakeClient(v5))["checks"]
    checks.append(("bad: media_asset_id参照先がreference_onlyは違反 (=False)",
                   res["no_reference_only_media_ready"] is False))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
