#!/usr/bin/env python3
"""recover_production_sheets_threads_first.verify_state の新規 media/metrics チェックを検証。

新規チェック:
  - media_approved_rows_rights_clear: APPROVED media は権利クリアであること
  - media_uploaded_only_if_approved: upload 済み media は承認済みのみ
  - metrics_candidates_not_postable: metrics 由来候補は worker 非対象 status
  - metrics_suggestions_waiting_review: metrics 由来提案は WAITING_REVIEW

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
    """他チェックは無視するが、verify_state が読む全タブを最低限用意する。"""
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
    }


def main() -> int:
    mod = _load()
    checks: list[tuple[str, bool]] = []

    # --- クリーンなケース: 4チェックすべて True ---
    clean = _base_tabs()
    clean["media_assets"] = [
        # APPROVED かつ権利クリア
        {"media_asset_id": "m_ok", "approval_status": "APPROVED", "status": "APPROVED",
         "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned",
         "cloudinary_url": "https://res.cloudinary.com/x/ok.png"},
        # self_generated・未 upload
        {"media_asset_id": "m_self", "status": "SELF_GENERATED",
         "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned"},
    ]
    clean["queue"] = [
        {"queue_id": "q1", "generation_mode": "metrics_driven_candidate", "status": "DRAFT"},
        # 境界ピン留め: refill / clip 由来候補は設計上 WAITING_REVIEW（worker eligible）で書かれる。
        # これらは metrics チェックを発火させてはならない（誤検知すると正常な補充キューで FAIL する）。
        {"queue_id": "q_refill", "generation_mode": "refill_seed", "status": "WAITING_REVIEW"},
        {"queue_id": "q_clip", "generation_mode": "video_clip_reference", "status": "WAITING_REVIEW"},
        {"queue_id": "q_seed", "generation_mode": "threads_first_manual_seed", "status": "WAITING_REVIEW"},
    ]
    clean["prompt_improvement_suggestions"] = [
        {"suggestion_id": "s1", "source": "generate_next_queue_from_metrics", "status": "WAITING_REVIEW"},
        {"suggestion_id": "s2", "source": "import_threads_metrics_manual", "status": "WAITING_REVIEW"},
    ]
    clean["source_account_posts"] = [
        # 参考のみ・流用不可（許諾未確認）→ 安全
        {"post_id": "p1", "use_status": "REFERENCE_ONLY", "rights_status": "unknown", "can_reuse_media": "false"},
        # 流用可だが許諾が明示されている → 安全
        {"post_id": "p2", "use_status": "IDEA_SEED", "rights_status": "owned", "can_reuse_media": "true"},
    ]
    clean["reference_post_scores"] = [
        # 流用リスク高 → REFERENCE_ONLY 推奨・投稿可ステータスなし → 安全
        {"score_id": "qs1", "reuse_risk_score": "3.0", "recommended_use": "REFERENCE_ONLY"},
        {"score_id": "qs2", "reuse_risk_score": "1.0", "recommended_use": "IDEA_SEED"},
    ]
    res = mod.verify_state(_FakeClient(clean))["checks"]
    checks.append(("clean: media_approved_rows_rights_clear", res["media_approved_rows_rights_clear"] is True))
    checks.append(("clean: media_uploaded_only_if_approved", res["media_uploaded_only_if_approved"] is True))
    checks.append(("clean: metrics_candidates_not_postable", res["metrics_candidates_not_postable"] is True))
    # 境界回帰: refill_seed / video_clip_reference / manual_seed は設計上 WAITING_REVIEW で
    # worker eligible に書かれる。metrics チェックはこれらを誤検知してはならない（上の clean
    # キューに 3 行とも WAITING_REVIEW で含まれているのに True であることがそれを保証する）。
    checks.append(("clean(境界): refill/clip/seed の WAITING_REVIEW は metrics チェックを発火しない",
                   res["metrics_candidates_not_postable"] is True))
    checks.append(("clean: metrics_suggestions_waiting_review", res["metrics_suggestions_waiting_review"] is True))
    checks.append(("clean: reference_posts_use_status_safe", res["reference_posts_use_status_safe"] is True))
    checks.append(("clean: reference_posts_reuse_rights_safe", res["reference_posts_reuse_rights_safe"] is True))
    checks.append(("clean: reference_scores_high_risk_reference_only", res["reference_scores_high_risk_reference_only"] is True))
    checks.append(("clean: reference_scores_not_postable", res["reference_scores_not_postable"] is True))

    # --- 違反ケース: 各チェックが False になる ---
    bad = _base_tabs()
    bad["media_assets"] = [
        # APPROVED なのに no_reuse（権利クリアでない）
        {"media_asset_id": "m_bad1", "approval_status": "APPROVED", "status": "APPROVED",
         "rights_policy": "owned", "reuse_policy": "no_reuse", "media_policy": "owned"},
        # upload 済み（cloudinary_url あり）なのに未承認
        {"media_asset_id": "m_bad2", "approval_status": "WAITING_REVIEW", "status": "WAITING_REVIEW",
         "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned",
         "cloudinary_url": "https://res.cloudinary.com/x/leak.png"},
    ]
    bad["queue"] = [
        # metrics 候補なのに投稿対象 status
        {"queue_id": "q2", "generation_mode": "metrics_driven_candidate", "status": "WAITING_REVIEW"},
    ]
    bad["prompt_improvement_suggestions"] = [
        # metrics 由来なのに自動適用されている
        {"suggestion_id": "s3", "source": "generate_next_queue_from_metrics", "status": "APPLIED"},
    ]
    bad["source_account_posts"] = [
        # 参考投稿に投稿可ステータス（危険）
        {"post_id": "pb1", "use_status": "WAITING_REVIEW", "rights_status": "owned", "can_reuse_media": "false"},
        # 流用可なのに許諾未確認（危険）
        {"post_id": "pb2", "use_status": "REFERENCE_ONLY", "rights_status": "unknown", "can_reuse_media": "true"},
    ]
    bad["reference_post_scores"] = [
        # 流用リスク高なのに IDEA_SEED 推奨（危険）かつ投稿可ステータス
        {"score_id": "qsb", "reuse_risk_score": "3.5", "recommended_use": "IDEA_SEED", "status": "PLANNED"},
    ]
    res = mod.verify_state(_FakeClient(bad))["checks"]
    checks.append(("bad: media_approved_rows_rights_clear=False", res["media_approved_rows_rights_clear"] is False))
    checks.append(("bad: media_uploaded_only_if_approved=False", res["media_uploaded_only_if_approved"] is False))
    checks.append(("bad: metrics_candidates_not_postable=False", res["metrics_candidates_not_postable"] is False))
    checks.append(("bad: metrics_suggestions_waiting_review=False", res["metrics_suggestions_waiting_review"] is False))
    checks.append(("bad: reference_posts_use_status_safe=False", res["reference_posts_use_status_safe"] is False))
    checks.append(("bad: reference_posts_reuse_rights_safe=False", res["reference_posts_reuse_rights_safe"] is False))
    checks.append(("bad: reference_scores_high_risk_reference_only=False", res["reference_scores_high_risk_reference_only"] is False))
    checks.append(("bad: reference_scores_not_postable=False", res["reference_scores_not_postable"] is False))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
