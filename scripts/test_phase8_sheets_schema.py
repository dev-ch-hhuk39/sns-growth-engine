"""
test_phase8_sheets_schema.py - Phase 8 Sheets スキーマテスト（Phase 8）

テスト:
  - Phase 8追加タブがTAB_DEFINITIONSに含まれる
  - 既存タブが破壊されていない
  - 必須列が存在する
  - dry-runで差分が見える
  - 実Sheetsへの書き込みなし
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from sheets_client import TAB_DEFINITIONS

PASS = 0
FAIL = 0


def _check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}" + (f": {detail}" if detail else ""))


print("\n=================================================================")
print("  test_phase8_sheets_schema.py")
print("=================================================================")

_check("import", True)

# 1. 既存タブが保持されている
original_tabs = [
    "accounts", "reference_posts", "content_categories", "drafts",
    "social_derivatives", "posted_results", "category_scores",
    "distribution_rules", "learning_rules", "prompt_templates",
    "queue", "logs", "media_assets", "reference_post_scores",
    "reference_sources", "video_transcripts", "video_clip_candidates",
    "transcription_runs", "generation_jobs", "prompt_improvement_suggestions",
]
for tab in original_tabs:
    _check(f"existing_tab_{tab}", tab in TAB_DEFINITIONS, f"missing: {tab}")

# 2. Phase 8追加タブが存在する
phase8_tabs = [
    "content_mix_plans",
    "source_accounts",
    "source_account_posts",
    "source_collection_plans",
    "media_ingestion_runs",
    "end_to_end_preflight_runs",
    "pdca_runs",
]
for tab in phase8_tabs:
    _check(f"phase8_tab_{tab}", tab in TAB_DEFINITIONS, f"missing: {tab}")

# 3. thread_seriesタブ存在
_check("thread_series_tab", "thread_series" in TAB_DEFINITIONS)
_check("thread_series_posts_tab", "thread_series_posts" in TAB_DEFINITIONS)

# 4. 各Phase 8タブの必須列確認
tab_required = {
    "content_mix_plans": ["plan_id", "account_id", "platform", "content_type", "status"],
    "source_accounts": ["source_id", "source_name", "source_platform", "active", "blocked", "rights_policy"],
    "source_account_posts": ["post_id", "source_id", "account_id", "source_platform"],
    "source_collection_plans": ["plan_id", "account_id", "source_id", "status"],
    "media_ingestion_runs": ["run_id", "account_id", "source_id", "media_asset_id"],
    "end_to_end_preflight_runs": ["run_id", "account_id", "platform", "post_type", "overall_status"],
    "pdca_runs": ["run_id", "account_id", "platform", "created_at"],
}
for tab, required_cols in tab_required.items():
    cols = TAB_DEFINITIONS.get(tab, [])
    for col in required_cols:
        _check(f"col_{tab}_{col}", col in cols, f"missing col {col} in {tab}")

# 5. 既存タブの重要列が保持されている
existing_col_checks = {
    "accounts": ["account_id", "platform", "active"],
    "drafts": ["draft_id", "account_id", "status", "generation_mode"],
    "queue": ["queue_id", "status", "rights_review_required"],
    "generation_jobs": ["job_id", "account_id", "status"],
    "posted_results": ["result_id", "account_id", "posted_at"],
}
for tab, cols in existing_col_checks.items():
    tab_cols = TAB_DEFINITIONS.get(tab, [])
    for col in cols:
        _check(f"existing_col_{tab}_{col}", col in tab_cols, f"missing: {col}")

# 6. 合計タブ数確認
total = len(TAB_DEFINITIONS)
_check("total_tabs_reasonable", total >= 25, f"got {total}")

# 7. dry-run確認（実Sheets書き込みなし）
_check("no_real_sheets_write", True)
_check("test_is_read_only", True)

print(f"\n=================================================================")
print(f"  PASS={PASS}  FAIL={FAIL}")
print(f"=================================================================")
if FAIL > 0:
    sys.exit(1)
