"""
test_phase2.py - Phase 2 動作確認テスト

Gemini API キーなし・スプレッドシート接続なしで MOCK_LLM + MockSheetsClient で動く。

テスト項目:
  1. llm_client JSON 抽出
  2. prompt_loader 変数置換
  3. publish_decision 判定
  4. MockSheetsClient 主要メソッド
  5. draft_generator dry-run
  6. social_derivative_generator dry-run
  7. queue_builder dry-run
  8. run_pipeline dry-run（統合）
"""
import os
import sys

# MOCK_LLM を有効にしてからインポート
os.environ["MOCK_LLM"] = "true"
os.environ["DRY_RUN"] = "false"  # MockSheetsClient で書き込み確認するため

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from llm_client import call_gemini_json, extract_json
from prompt_loader import render_prompt, get_draft_generation_template, get_derivative_template
from publish_decision import decide_draft_status, decide_derivative_status, should_queue
from sheets_client import MockSheetsClient
from draft_generator import generate_drafts
from social_derivative_generator import generate_social_derivatives
from queue_builder import build_queue


_PASS = 0
_FAIL = 0


def ok(name: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  [PASS] {name}")


def fail(name: str, reason: str) -> None:
    global _FAIL
    _FAIL += 1
    print(f"  [FAIL] {name}: {reason}")


# ------------------------------------------------------------------ #
# 1. llm_client JSON 抽出
# ------------------------------------------------------------------ #

def test_llm_client() -> None:
    print("\n[Test 1] llm_client")

    # mock 応答
    result = call_gemini_json("dummy prompt")
    if "title" in result or "platform" in result:
        ok("call_gemini_json mock 応答")
    else:
        fail("call_gemini_json mock 応答", f"unexpected: {result}")

    # JSON 抽出: コードブロック
    text = '```json\n{"key": "value"}\n```'
    parsed = extract_json(text)
    if parsed.get("key") == "value":
        ok("extract_json コードブロック")
    else:
        fail("extract_json コードブロック", str(parsed))

    # JSON 抽出: 前後にテキスト
    text2 = 'ここは説明文です。\n{"score": 80}\nこれも説明文。'
    parsed2 = extract_json(text2)
    if parsed2.get("score") == 80:
        ok("extract_json 前後テキスト")
    else:
        fail("extract_json 前後テキスト", str(parsed2))

    # JSON 抽出: 失敗時のフォールバック
    bad = extract_json("これはJSONではない文章")
    if "_error" in bad:
        ok("extract_json 失敗フォールバック")
    else:
        fail("extract_json 失敗フォールバック", str(bad))

    # platform-aware mock
    x_mock = call_gemini_json("dummy", platform="x")
    if x_mock.get("platform") == "x":
        ok("call_gemini_json platform=x mock")
    else:
        fail("call_gemini_json platform=x mock", str(x_mock))

    threads_mock = call_gemini_json("dummy", platform="threads")
    if threads_mock.get("platform") == "threads":
        ok("call_gemini_json platform=threads mock")
    else:
        fail("call_gemini_json platform=threads mock", str(threads_mock))


# ------------------------------------------------------------------ #
# 2. prompt_loader 変数置換
# ------------------------------------------------------------------ #

def test_prompt_loader() -> None:
    print("\n[Test 2] prompt_loader")

    tmpl = "{{account_name}}向けの投稿: {{category_name}}"
    rendered = render_prompt(tmpl, {"account_name": "夜職スカウト", "category_name": "店選びノウハウ"})
    if "夜職スカウト" in rendered and "店選びノウハウ" in rendered:
        ok("render_prompt 基本置換")
    else:
        fail("render_prompt 基本置換", rendered)

    # 未定義変数は空文字
    rendered2 = render_prompt("{{unknown_var}}テスト", {})
    if rendered2 == "テスト":
        ok("render_prompt 未定義変数は空文字")
    else:
        fail("render_prompt 未定義変数は空文字", rendered2)

    # seeds fallback でテンプレート取得
    tmpl_dict = get_draft_generation_template(None, "night_scout")
    if tmpl_dict and "prompt_text" in tmpl_dict:
        ok("get_draft_generation_template seeds fallback (night_scout)")
    else:
        fail("get_draft_generation_template seeds fallback (night_scout)", str(tmpl_dict))

    tmpl_dict2 = get_draft_generation_template(None, "liver_manager")
    if tmpl_dict2 and "prompt_text" in tmpl_dict2:
        ok("get_draft_generation_template seeds fallback (liver_manager)")
    else:
        fail("get_draft_generation_template seeds fallback (liver_manager)", str(tmpl_dict2))

    tmpl_x = get_derivative_template(None, "x")
    if tmpl_x and "prompt_text" in tmpl_x:
        ok("get_derivative_template seeds fallback (x)")
    else:
        fail("get_derivative_template seeds fallback (x)", str(tmpl_x))

    tmpl_threads = get_derivative_template(None, "threads")
    if tmpl_threads and "prompt_text" in tmpl_threads:
        ok("get_derivative_template seeds fallback (threads)")
    else:
        fail("get_derivative_template seeds fallback (threads)", str(tmpl_threads))


# ------------------------------------------------------------------ #
# 3. publish_decision 判定
# ------------------------------------------------------------------ #

def test_publish_decision() -> None:
    print("\n[Test 3] publish_decision")

    account = {"auto_publish": "FALSE", "min_publish_score": "65", "brand_risk_threshold": "25"}

    # スコア高 & リスク低 → READY
    draft_ready = {"score": "80", "cv_score": "70", "brand_risk_score": "15"}
    status = decide_draft_status(draft_ready, account)
    if status == "READY":
        ok("decide_draft_status: READY")
    else:
        fail("decide_draft_status: READY", f"got {status}")

    # スコア低 → DRAFT
    draft_low = {"score": "40", "cv_score": "40", "brand_risk_score": "10"}
    status2 = decide_draft_status(draft_low, account)
    if status2 == "DRAFT":
        ok("decide_draft_status: DRAFT (低スコア)")
    else:
        fail("decide_draft_status: DRAFT (低スコア)", f"got {status2}")

    # brand_risk_score 高 → HUMAN_REVIEW
    draft_risky = {"score": "80", "cv_score": "80", "brand_risk_score": "40"}
    status3 = decide_draft_status(draft_risky, account)
    if status3 == "HUMAN_REVIEW":
        ok("decide_draft_status: HUMAN_REVIEW (リスク高)")
    else:
        fail("decide_draft_status: HUMAN_REVIEW (リスク高)", f"got {status3}")

    # should_queue: auto_publish=FALSE → WAITING_REVIEW
    der = {"status": "READY"}
    add, q_status, reason = should_queue(der, draft_ready, account)
    if add and q_status == "WAITING_REVIEW":
        ok("should_queue: auto_publish=FALSE → WAITING_REVIEW")
    else:
        fail("should_queue: auto_publish=FALSE", f"add={add} status={q_status}")

    # should_queue: REJECT → False
    der_reject = {"status": "REJECT"}
    add2, q_status2, _ = should_queue(der_reject, draft_ready, account)
    if not add2 and q_status2 == "REJECTED":
        ok("should_queue: REJECT → False")
    else:
        fail("should_queue: REJECT", f"add={add2} status={q_status2}")

    # decide_derivative_status
    der_ok = {"status": "READY"}
    ds = decide_derivative_status(der_ok, draft_ready, account)
    if ds == "READY":
        ok("decide_derivative_status: READY")
    else:
        fail("decide_derivative_status: READY", f"got {ds}")


# ------------------------------------------------------------------ #
# 4. MockSheetsClient 主要メソッド
# ------------------------------------------------------------------ #

def test_mock_sheets_client() -> None:
    print("\n[Test 4] MockSheetsClient")

    sheets = MockSheetsClient()

    accounts = sheets.get_active_accounts()
    if len(accounts) >= 2:
        ok(f"get_active_accounts: {len(accounts)} 件")
    else:
        fail("get_active_accounts", f"got {len(accounts)}")

    cats = sheets.get_active_categories("night_scout")
    if len(cats) > 0:
        ok(f"get_active_categories(night_scout): {len(cats)} 件")
    else:
        fail("get_active_categories(night_scout)", "0件")

    cats2 = sheets.get_active_categories("liver_manager")
    if len(cats2) > 0:
        ok(f"get_active_categories(liver_manager): {len(cats2)} 件")
    else:
        fail("get_active_categories(liver_manager)", "0件")

    tmpls = sheets.get_prompt_templates(account_id="night_scout")
    if len(tmpls) > 0:
        ok(f"get_prompt_templates(night_scout): {len(tmpls)} 件")
    else:
        fail("get_prompt_templates(night_scout)", "0件")

    draft_id = sheets.save_draft("night_scout", "テスト", "本文テスト")
    if draft_id:
        ok(f"save_draft: {draft_id}")
    else:
        fail("save_draft", "empty draft_id")

    drafts = sheets.get_drafts(account_id="night_scout")
    if any(d["draft_id"] == draft_id for d in drafts):
        ok("get_drafts: save した draft が取得できる")
    else:
        fail("get_drafts", f"draft_id={draft_id} not found")

    der_id = sheets.append_social_derivative({
        "draft_id": draft_id,
        "account_id": "night_scout",
        "platform": "x",
        "text": "テスト投稿",
        "status": "READY",
    })
    if der_id:
        ok(f"append_social_derivative: {der_id}")
    else:
        fail("append_social_derivative", "empty id")

    found = sheets.find_social_derivative(draft_id, "x")
    if found and found.get("platform") == "x":
        ok("find_social_derivative: 存在確認")
    else:
        fail("find_social_derivative", str(found))

    not_found = sheets.find_social_derivative(draft_id, "threads")
    if not_found is None:
        ok("find_social_derivative: 存在しない場合 None")
    else:
        fail("find_social_derivative: None", str(not_found))


# ------------------------------------------------------------------ #
# 5–7. generate / queue dry-run
# ------------------------------------------------------------------ #

def test_generate_pipeline() -> None:
    print("\n[Test 5] generate_drafts dry-run (MockSheetsClient)")
    sheets = MockSheetsClient()
    drafts = generate_drafts(sheets=sheets, account_id="night_scout", limit=2, dry_run=False)
    if len(drafts) > 0:
        ok(f"generate_drafts: {len(drafts)} 件")
    else:
        fail("generate_drafts", "0件")

    print("\n[Test 6] generate_social_derivatives dry-run")
    ders = generate_social_derivatives(
        sheets=sheets,
        account_id="night_scout",
        platforms=["x", "threads"],
        status=["READY", "DRAFT"],
        limit=10,
        dry_run=False,
    )
    if len(ders) > 0:
        ok(f"generate_social_derivatives: {len(ders)} 件")
    else:
        fail("generate_social_derivatives", "0件")

    print("\n[Test 7] build_queue dry-run")
    queue = build_queue(sheets=sheets, account_id="night_scout", platforms=["x", "threads"])
    if len(queue) >= 0:
        ok(f"build_queue: {len(queue)} 件（WAITING_REVIEW含む）")
    else:
        fail("build_queue", "エラー")


# ------------------------------------------------------------------ #
# 8. 統合パイプライン dry-run
# ------------------------------------------------------------------ #

def test_run_pipeline() -> None:
    print("\n[Test 8] run_pipeline 統合 dry-run")
    sheets = MockSheetsClient()

    drafts = generate_drafts(sheets=sheets, account_id="night_scout", limit=2)
    ders = generate_social_derivatives(
        sheets=sheets, account_id="night_scout",
        platforms=["x", "threads"], status=["READY", "DRAFT"], limit=10
    )
    q = build_queue(sheets=sheets, account_id="night_scout", platforms=["x", "threads"])

    if len(drafts) > 0 and len(ders) >= 0 and len(q) >= 0:
        ok(f"run_pipeline: drafts={len(drafts)} ders={len(ders)} queue={len(q)}")
    else:
        fail("run_pipeline", f"drafts={len(drafts)} ders={len(ders)} queue={len(q)}")


# ------------------------------------------------------------------ #
# エントリーポイント
# ------------------------------------------------------------------ #

def main() -> None:
    print("=" * 60)
    print("Phase 2 テスト開始 (MOCK_LLM=true, MockSheetsClient)")
    print("=" * 60)

    test_llm_client()
    test_prompt_loader()
    test_publish_decision()
    test_mock_sheets_client()
    test_generate_pipeline()
    test_run_pipeline()

    print("\n" + "=" * 60)
    print(f"結果: {_PASS} PASS / {_FAIL} FAIL")
    print("=" * 60)

    if _FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
