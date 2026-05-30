"""
test_phase213_216.py — Phase 2.13〜2.16 動作確認テスト

テスト項目:
  1. TAB_DEFINITIONS の新規列確認（generation_jobs / drafts / social_derivatives / queue）
  2. generation_planner: 比率計算・候補選択・ジョブレコード構築
  3. SheetsClient / MockSheetsClient の generation_jobs メソッド
  4. reference_based_generator: プロンプト構築・レスポンスパース・生成フロー
  5. approval_scorer: 各スコア計算・総合判定
  6. text_policy との統合（FAIL → WAITING_REVIEW）
  7. フィクスチャ読み込み確認
  8. check_pipeline_integrity の新フィールド定数確認
"""
from __future__ import annotations

import json
import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

os.environ["MOCK_LLM"] = "true"

from sheets_client import TAB_DEFINITIONS, MockSheetsClient
from generation.generation_planner import (
    plan_daily_counts,
    allocate_generation_modes,
    select_reference_candidates,
    score_reference_candidate,
    build_generation_job,
    build_generation_job_records,
    plan_generation_jobs,
    create_generation_jobs_for_account,
)
from generation.reference_based_generator import (
    build_reference_based_prompt,
    build_original_hypothesis_prompt,
    parse_generation_response,
    generate_from_reference,
    generate_original_hypothesis,
    normalize_generated_draft,
    execute_generation_job,
    execute_generation_jobs,
)
from generation.approval_scorer import (
    calculate_buzz_potential_score,
    calculate_conversion_potential_score,
    calculate_brand_risk_score,
    calculate_imitation_risk,
    calculate_media_reuse_risk,
    calculate_confidence_level,
    should_auto_approve,
    calculate_ai_publish_recommendation,
    score_generated_post,
    _text_overlap_ratio,
)
from text_policy import check_text_policy

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
# 1. TAB_DEFINITIONS 新規列確認
# ------------------------------------------------------------------ #

def test_tab_definitions_phase213_216() -> None:
    print("\n[Test 1] TAB_DEFINITIONS Phase 2.13-2.16 新規列確認")

    checks = {
        "generation_jobs": [
            "reference_post_id", "reference_post_score_id", "media_asset_id",
            "status", "generated_draft_id", "generated_at",
        ],
        "drafts": [
            "generation_mode", "hypothesis", "media_strategy",
            "imitation_risk", "media_reuse_risk",
            "buzz_potential_score", "conversion_potential_score",
            "confidence_level", "ai_publish_recommendation",
        ],
        "social_derivatives": [
            "char_count", "text_policy_status", "media_asset_id", "media_strategy",
        ],
        "queue": [
            "generation_mode", "confidence_level", "ai_publish_recommendation",
            "media_asset_id", "text_policy_status",
        ],
    }

    for tab, required_cols in checks.items():
        cols = TAB_DEFINITIONS.get(tab, [])
        for col in required_cols:
            if col in cols:
                ok(f"TAB_DEFINITIONS['{tab}'] に '{col}'")
            else:
                fail(f"TAB_DEFINITIONS['{tab}'] に '{col}'", f"定義なし。実際: {cols}")


# ------------------------------------------------------------------ #
# 2. generation_planner
# ------------------------------------------------------------------ #

def test_generation_planner() -> None:
    print("\n[Test 2] generation_planner")

    # plan_daily_counts
    ref, orig = plan_daily_counts(3, 0.8)
    if ref == 2 and orig == 1:
        ok("plan_daily_counts(3, 0.8) → (2, 1)")
    else:
        fail("plan_daily_counts(3, 0.8)", f"({ref}, {orig})")

    ref, orig = plan_daily_counts(10, 0.8)
    if ref == 8 and orig == 2:
        ok("plan_daily_counts(10, 0.8) → (8, 2)")
    else:
        fail("plan_daily_counts(10, 0.8)", f"({ref}, {orig})")

    ref, orig = plan_daily_counts(1, 0.8)
    if ref + orig == 1:
        ok("plan_daily_counts(1, 0.8) → 合計1件")
    else:
        fail("plan_daily_counts(1, 0.8)", f"({ref}, {orig})")

    # allocate_generation_modes
    modes = allocate_generation_modes(5, 0.8)
    if len(modes) == 5:
        ok(f"allocate_generation_modes(5, 0.8): 5件")
    else:
        fail("allocate_generation_modes(5, 0.8): 件数", str(len(modes)))

    ref_count = modes.count("reference_based")
    orig_count = modes.count("original_hypothesis")
    if ref_count == 4 and orig_count == 1:
        ok(f"allocate_generation_modes(5, 0.8): ref=4, orig=1")
    else:
        fail("allocate_generation_modes mode counts", f"ref={ref_count}, orig={orig_count}")

    # score_reference_candidate
    s = {"buzz_score": 80.0, "account_percentile": 0.9}
    score = score_reference_candidate(s)
    expected = 80.0 * 0.7 + 0.9 * 0.3
    if abs(score - expected) < 0.01:
        ok(f"score_reference_candidate → {score:.2f}")
    else:
        fail("score_reference_candidate", f"{score} != {expected}")

    # select_reference_candidates
    scores = [
        {"score_id": "s1", "reference_post_id": "p1", "buzz_score": 85.0, "account_percentile": 0.8},
        {"score_id": "s2", "reference_post_id": "p2", "buzz_score": 70.0, "account_percentile": 0.6},
        {"score_id": "s3", "reference_post_id": "p3", "buzz_score": 40.0, "account_percentile": 0.3},
    ]
    candidates = select_reference_candidates(scores, min_score=50.0, count=2)
    if len(candidates) == 2:
        ok(f"select_reference_candidates: 2件選択")
    else:
        fail("select_reference_candidates: 件数", str(len(candidates)))

    # min_score フィルタ確認
    candidates_filtered = select_reference_candidates(scores, min_score=80.0, count=2)
    if len(candidates_filtered) == 1:
        ok("select_reference_candidates: min_score=80 → 1件")
    else:
        fail("select_reference_candidates: min_score filter", str(len(candidates_filtered)))

    # 除外確認
    candidates_excluded = select_reference_candidates(
        scores, min_score=50.0, count=2, used_reference_ids={"p1"}
    )
    if all(c.get("reference_post_id") != "p1" for c in candidates_excluded):
        ok("select_reference_candidates: used_reference_ids 除外OK")
    else:
        fail("select_reference_candidates: 除外失敗", str(candidates_excluded))

    # build_generation_job
    job = build_generation_job(account_id="night_scout", platform="x")
    required_keys = ["job_id", "account_id", "platform", "generation_mode",
                     "reference_based_ratio", "original_hypothesis_ratio",
                     "daily_target_count", "status",
                     "reference_post_id", "reference_post_score_id", "generated_draft_id"]
    for k in required_keys:
        if k in job:
            ok(f"build_generation_job: '{k}' キー存在")
        else:
            fail(f"build_generation_job: '{k}' キー存在", str(list(job.keys())))

    if job["status"] == "pending":
        ok("build_generation_job: status=pending デフォルト")
    else:
        fail("build_generation_job: status", job["status"])

    # plan_generation_jobs
    jobs = plan_generation_jobs(
        account_id="night_scout",
        platform="x",
        scores=scores,
        daily_target_count=3,
    )
    if len(jobs) == 3:
        ok("plan_generation_jobs: 3件生成")
    else:
        fail("plan_generation_jobs: 件数", str(len(jobs)))

    modes_in_jobs = [j["generation_mode"] for j in jobs]
    if "reference_based" in modes_in_jobs:
        ok("plan_generation_jobs: reference_based モード存在")
    else:
        fail("plan_generation_jobs: reference_based 不在", str(modes_in_jobs))

    # create_generation_jobs_for_account
    all_jobs = create_generation_jobs_for_account(
        account_id="night_scout",
        platforms=["x", "threads"],
        scores=scores,
        daily_target_count=2,
    )
    if len(all_jobs) == 4:
        ok("create_generation_jobs_for_account: x+threads 4件")
    else:
        fail("create_generation_jobs_for_account: 件数", str(len(all_jobs)))


# ------------------------------------------------------------------ #
# 3. MockSheetsClient generation_jobs
# ------------------------------------------------------------------ #

def test_mock_sheets_generation_jobs() -> None:
    print("\n[Test 3] MockSheetsClient.generation_jobs メソッド")

    client = MockSheetsClient()

    # save / get / find
    job = build_generation_job(account_id="night_scout", platform="x")
    job_id = job["job_id"]

    result = client.save_generation_job(job)
    if result:
        ok("save_generation_job: True 返却")
    else:
        fail("save_generation_job: 戻り値", str(result))

    found = client.find_generation_job_by_id(job_id)
    if found and found.get("job_id") == job_id:
        ok("find_generation_job_by_id: 発見")
    else:
        fail("find_generation_job_by_id", str(found))

    jobs = client.get_generation_jobs(account_id="night_scout")
    if len(jobs) == 1:
        ok("get_generation_jobs: 1件取得")
    else:
        fail("get_generation_jobs", str(len(jobs)))

    # update
    client.update_generation_job(job_id, status="done", generated_draft_id="d-test-001")
    updated = client.find_generation_job_by_id(job_id)
    if updated and updated.get("status") == "done":
        ok("update_generation_job: status=done に更新")
    else:
        fail("update_generation_job: status", str(updated))

    if updated and updated.get("generated_draft_id") == "d-test-001":
        ok("update_generation_job: generated_draft_id 更新")
    else:
        fail("update_generation_job: generated_draft_id", str(updated))

    # upsert
    job["notes"] = "updated"
    client.save_generation_job(job)
    all_jobs = client.get_generation_jobs()
    if len(all_jobs) == 1:
        ok("save_generation_job upsert: 件数変化なし")
    else:
        fail("save_generation_job upsert: 件数", str(len(all_jobs)))

    # save_generation_jobs
    jobs_batch = [
        build_generation_job(account_id="night_scout", platform="x"),
        build_generation_job(account_id="night_scout", platform="threads"),
    ]
    result = client.save_generation_jobs(jobs_batch)
    if result["saved"] == 2 and result["errors"] == 0:
        ok(f"save_generation_jobs: saved={result['saved']}")
    else:
        fail("save_generation_jobs", str(result))

    # platform フィルタ
    x_jobs = client.get_generation_jobs(platform="x")
    if all(j["platform"] == "x" for j in x_jobs):
        ok("get_generation_jobs platform フィルタ: x のみ")
    else:
        fail("get_generation_jobs platform フィルタ", str([j["platform"] for j in x_jobs]))

    # status フィルタ
    pending_jobs = client.get_generation_jobs(status="pending")
    if all(str(j.get("status", "")).lower() == "pending" for j in pending_jobs):
        ok("get_generation_jobs status フィルタ: pending のみ")
    else:
        fail("get_generation_jobs status フィルタ", str([j.get("status") for j in pending_jobs]))


# ------------------------------------------------------------------ #
# 4. reference_based_generator
# ------------------------------------------------------------------ #

def test_reference_based_generator() -> None:
    print("\n[Test 4] reference_based_generator")

    account = {
        "account_id": "night_scout",
        "target_persona": "夜職を検討中の20代女性",
        "tone": "共感・信頼",
        "main_genre": "夜職情報",
    }
    score = {
        "hook_style": "リスト型",
        "content_angle": "ノウハウ",
        "why_it_grew": "具体的な数字と共感要素",
        "replay_tip": "リスト形式で即実践できる内容",
        "buzz_score": 80.0,
    }
    job = build_generation_job(
        account_id="night_scout",
        platform="x",
        generation_mode="reference_based",
        reference_post_id="p-test",
        reference_post_score_id="s-test",
    )

    # プロンプト構築
    prompt_ref = build_reference_based_prompt(job, score, account, "x")
    if "120文字以内" in prompt_ref and "リスト型" in prompt_ref:
        ok("build_reference_based_prompt: 文字数制約・スコア情報含む")
    else:
        fail("build_reference_based_prompt: 内容", prompt_ref[:100])

    prompt_orig = build_original_hypothesis_prompt(job, account, "x")
    if "120文字以内" in prompt_orig:
        ok("build_original_hypothesis_prompt: 文字数制約含む")
    else:
        fail("build_original_hypothesis_prompt: 文字数制約なし", prompt_orig[:100])

    # Threads プロンプト
    prompt_th = build_reference_based_prompt(job, score, account, "threads")
    if "500文字以内" in prompt_th:
        ok("build_reference_based_prompt Threads: 500文字制約含む")
    else:
        fail("build_reference_based_prompt Threads: 文字数制約なし", prompt_th[:100])

    # parse_generation_response
    raw = {"content": "テスト投稿", "title": "タイトル", "media_strategy": "none"}
    parsed = parse_generation_response(raw)
    if parsed["content"] == "テスト投稿" and parsed["media_strategy"] == "none":
        ok("parse_generation_response: dict入力OK")
    else:
        fail("parse_generation_response: dict", str(parsed))

    raw_str = '{"content": "JSON文字列テスト", "media_strategy": "none"}'
    parsed_str = parse_generation_response(raw_str)
    if parsed_str["content"] == "JSON文字列テスト":
        ok("parse_generation_response: 文字列入力OK")
    else:
        fail("parse_generation_response: 文字列", str(parsed_str))

    # generate_from_reference（MOCK_LLM=true）
    result = generate_from_reference(job, score, account, "x")
    if "content" in result and result.get("generation_mode") == "reference_based":
        ok("generate_from_reference: content生成・generation_mode=reference_based")
    else:
        fail("generate_from_reference", str(result.keys()))

    if "text_policy_status" in result:
        ok(f"generate_from_reference: text_policy_status={result['text_policy_status']!r}")
    else:
        fail("generate_from_reference: text_policy_status なし", str(result))

    # generate_original_hypothesis（MOCK_LLM=true）
    job_orig = build_generation_job(
        account_id="night_scout", platform="x", generation_mode="original_hypothesis"
    )
    result_orig = generate_original_hypothesis(job_orig, account, "x")
    if result_orig.get("generation_mode") == "original_hypothesis":
        ok("generate_original_hypothesis: generation_mode=original_hypothesis")
    else:
        fail("generate_original_hypothesis: generation_mode", str(result_orig.get("generation_mode")))

    # normalize_generated_draft
    gen_result = {"content": "テスト投稿文", "title": "テスト", "generation_mode": "reference_based",
                  "text_policy_status": "OK", "media_strategy": "none", "generation_notes": "mock"}
    draft = normalize_generated_draft(gen_result, job, "night_scout")
    if "draft_id" in draft and draft["status"] == "DRAFT":
        ok("normalize_generated_draft: DRAFT status")
    else:
        fail("normalize_generated_draft: status", str(draft.get("status")))

    # FAIL → WAITING_REVIEW
    gen_fail = {**gen_result, "text_policy_status": "FAIL"}
    draft_fail = normalize_generated_draft(gen_fail, job, "night_scout")
    if draft_fail["status"] == "WAITING_REVIEW":
        ok("normalize_generated_draft: text_policy=FAIL → WAITING_REVIEW")
    else:
        fail("normalize_generated_draft: FAIL status", str(draft_fail.get("status")))

    # execute_generation_job（dry-run）
    mock_client = MockSheetsClient()
    exec_result = execute_generation_job(
        job=job,
        scores_by_id={"s-test": score},
        account=account,
        client=mock_client,
        dry_run=True,
    )
    if exec_result.get("job_id") == job["job_id"] and exec_result.get("draft_id"):
        ok("execute_generation_job: dry-run実行OK")
    else:
        fail("execute_generation_job: dry-run", str(exec_result))

    # execute_generation_jobs（dry-run）
    jobs_list = [job, job_orig]
    exec_results = execute_generation_jobs(
        jobs=jobs_list,
        scores=[{**score, "score_id": "s-test"}],
        account=account,
        client=mock_client,
        dry_run=True,
    )
    if len(exec_results) == 2:
        ok("execute_generation_jobs: 2件処理")
    else:
        fail("execute_generation_jobs: 件数", str(len(exec_results)))


# ------------------------------------------------------------------ #
# 5. approval_scorer
# ------------------------------------------------------------------ #

def test_approval_scorer() -> None:
    print("\n[Test 5] approval_scorer")

    reference_score = {"buzz_score": 80.0}
    draft_ok = {
        "body_md": "キャバを始めたての子に必ず伝えること。店選びを間違えると大きな差が生まれる。",
        "platform": "x",
        "cta_text": "相談はDMで",
        "generation_mode": "reference_based",
    }

    # buzz_potential_score
    buzz = calculate_buzz_potential_score(draft_ok, reference_score)
    if 0 <= buzz <= 100:
        ok(f"calculate_buzz_potential_score: {buzz:.1f}")
    else:
        fail("calculate_buzz_potential_score: 範囲外", str(buzz))

    # reference_based でボーナスが入る
    draft_orig = {**draft_ok, "generation_mode": "original_hypothesis", "cta_text": ""}
    buzz_orig = calculate_buzz_potential_score(draft_orig, reference_score)
    if buzz > buzz_orig:
        ok("buzz_potential_score: reference_based > original_hypothesis（CTA・モードボーナス反映）")
    else:
        fail("buzz_potential_score: ボーナス反映", f"ref={buzz:.1f} vs orig={buzz_orig:.1f}")

    # conversion_potential_score
    conv = calculate_conversion_potential_score(draft_ok)
    if 0 <= conv <= 100:
        ok(f"calculate_conversion_potential_score: {conv:.1f}")
    else:
        fail("calculate_conversion_potential_score: 範囲外", str(conv))

    conv_no_cta = calculate_conversion_potential_score({**draft_ok, "cta_text": ""})
    if conv > conv_no_cta:
        ok("conversion_potential_score: CTA有 > CTA無")
    else:
        fail("conversion_potential_score: CTA差", f"{conv:.1f} vs {conv_no_cta:.1f}")

    # brand_risk_score
    draft_with_risk = {**draft_ok, "imitation_risk": "high"}
    risk = calculate_brand_risk_score(draft_with_risk)
    if 0 <= risk <= 1.0:
        ok(f"calculate_brand_risk_score: {risk:.3f}")
    else:
        fail("calculate_brand_risk_score: 範囲外", str(risk))

    risk_low = calculate_brand_risk_score({**draft_ok, "imitation_risk": "low"})
    if risk > risk_low:
        ok("brand_risk_score: high > low")
    else:
        fail("brand_risk_score: リスク差", f"high={risk:.3f} vs low={risk_low:.3f}")

    # imitation_risk
    ir = calculate_imitation_risk({"imitation_risk": "medium"})
    if ir == "medium":
        ok("calculate_imitation_risk: medium")
    else:
        fail("calculate_imitation_risk", ir)

    ir_from_ref = calculate_imitation_risk({}, {"imitation_risk": "high"})
    if ir_from_ref == "high":
        ok("calculate_imitation_risk: from reference_post")
    else:
        fail("calculate_imitation_risk: reference fallback", ir_from_ref)

    ir_unknown = calculate_imitation_risk({})
    if ir_unknown == "unknown":
        ok("calculate_imitation_risk: unknown fallback")
    else:
        fail("calculate_imitation_risk: unknown", ir_unknown)

    # media_reuse_risk
    mrr = calculate_media_reuse_risk({"media_reuse_risk": "low"})
    if mrr == "low":
        ok("calculate_media_reuse_risk: low")
    else:
        fail("calculate_media_reuse_risk", mrr)

    # confidence_level
    cl_high = calculate_confidence_level(75.0, 0.2, "OK")
    if cl_high == "HIGH":
        ok("calculate_confidence_level: HIGH")
    else:
        fail("calculate_confidence_level: HIGH", cl_high)

    cl_medium = calculate_confidence_level(55.0, 0.4, "WARN")
    if cl_medium == "MEDIUM":
        ok("calculate_confidence_level: MEDIUM")
    else:
        fail("calculate_confidence_level: MEDIUM", cl_medium)

    cl_low = calculate_confidence_level(30.0, 0.8, "FAIL")
    if cl_low == "LOW":
        ok("calculate_confidence_level: LOW")
    else:
        fail("calculate_confidence_level: LOW", cl_low)

    # should_auto_approve
    if should_auto_approve(85.0, 80.0):
        ok("should_auto_approve: 85 >= 80 → True")
    else:
        fail("should_auto_approve: 85 >= 80", "False")

    if not should_auto_approve(75.0, 80.0):
        ok("should_auto_approve: 75 < 80 → False")
    else:
        fail("should_auto_approve: 75 < 80", "True")

    # ai_publish_recommendation
    rec = calculate_ai_publish_recommendation("HIGH", "low", 0.2)
    if rec == "recommend":
        ok("calculate_ai_publish_recommendation: HIGH → recommend")
    else:
        fail("calculate_ai_publish_recommendation: HIGH", rec)

    rec_review = calculate_ai_publish_recommendation("HIGH", "high", 0.2)
    if rec_review == "review":
        ok("calculate_ai_publish_recommendation: imitation_risk=high → review")
    else:
        fail("calculate_ai_publish_recommendation: high imitation", rec_review)

    rec_reject = calculate_ai_publish_recommendation("LOW", "low", 0.3)
    if rec_reject == "reject":
        ok("calculate_ai_publish_recommendation: LOW → reject")
    else:
        fail("calculate_ai_publish_recommendation: LOW", rec_reject)

    # score_generated_post
    score_result = score_generated_post(
        draft=draft_ok,
        reference_score=reference_score,
        auto_approve_threshold=80.0,
        platform="x",
    )
    required_keys = [
        "buzz_potential_score", "conversion_potential_score",
        "brand_risk_score", "imitation_risk", "media_reuse_risk",
        "text_policy_status", "confidence_level",
        "ai_publish_recommendation", "suggested_status",
    ]
    for k in required_keys:
        if k in score_result:
            ok(f"score_generated_post: '{k}' キー存在")
        else:
            fail(f"score_generated_post: '{k}' 欠損", str(list(score_result.keys())))

    # _text_overlap_ratio
    ratio = _text_overlap_ratio("hello world", "hello world")
    if ratio == 1.0:
        ok("_text_overlap_ratio: 同一文字列 → 1.0")
    else:
        fail("_text_overlap_ratio: 同一", str(ratio))

    ratio_diff = _text_overlap_ratio("hello world", "completely different")
    if ratio_diff < 0.5:
        ok(f"_text_overlap_ratio: 異なる文字列 → {ratio_diff:.2f}")
    else:
        fail("_text_overlap_ratio: 異なる", str(ratio_diff))


# ------------------------------------------------------------------ #
# 6. text_policy 統合
# ------------------------------------------------------------------ #

def test_text_policy_integration() -> None:
    print("\n[Test 6] text_policy 統合チェック")

    # X: 140字以下 → OK/WARN
    short_x = "あ" * 100
    policy = check_text_policy(short_x, "x")
    if policy.status == "OK":
        ok("text_policy X 100字: OK")
    else:
        fail("text_policy X 100字", policy.status)

    # X: 141字以上 → FAIL
    long_x = "あ" * 141
    policy_fail = check_text_policy(long_x, "x")
    if policy_fail.status == "FAIL":
        ok("text_policy X 141字: FAIL")
    else:
        fail("text_policy X 141字", policy_fail.status)

    # FAIL → normalize_generated_draft で WAITING_REVIEW
    from generation.generation_planner import build_generation_job
    job = build_generation_job("night_scout", "x")
    gen = {
        "content": "あ" * 141,
        "title": "",
        "generation_mode": "reference_based",
        "text_policy_status": "FAIL",
        "media_strategy": "none",
        "generation_notes": "",
    }
    draft = normalize_generated_draft(gen, job, "night_scout")
    if draft["status"] == "WAITING_REVIEW":
        ok("text_policy FAIL → draft.status=WAITING_REVIEW")
    else:
        fail("text_policy FAIL → WAITING_REVIEW", draft["status"])

    # score_generated_post で confidence=LOW
    draft_long = {"body_md": "あ" * 141, "platform": "x", "cta_text": ""}
    scored = score_generated_post(draft_long, platform="x")
    if scored["text_policy_status"] == "FAIL":
        ok("score_generated_post: text_policy_status=FAIL")
    else:
        fail("score_generated_post: text_policy_status", scored["text_policy_status"])

    if scored["confidence_level"] == "LOW":
        ok("score_generated_post: FAIL policy → confidence=LOW")
    else:
        fail("score_generated_post: confidence_level", scored["confidence_level"])


# ------------------------------------------------------------------ #
# 7. フィクスチャ読み込み確認
# ------------------------------------------------------------------ #

def test_fixtures() -> None:
    print("\n[Test 7] フィクスチャ読み込み確認")

    fixtures = [
        "fixtures/sample_generation_jobs.json",
        "fixtures/sample_generated_posts.json",
    ]
    for fixture_path in fixtures:
        full_path = os.path.join(_V2_ROOT, fixture_path)
        if os.path.exists(full_path):
            with open(full_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                ok(f"{fixture_path}: {len(data)}件ロード")
            else:
                fail(f"{fixture_path}: 空または不正形式", str(type(data)))
        else:
            fail(f"{fixture_path}: ファイルが存在しない", full_path)

    # sample_generation_jobs の必須フィールド確認
    jobs_path = os.path.join(_V2_ROOT, "fixtures/sample_generation_jobs.json")
    if os.path.exists(jobs_path):
        with open(jobs_path, encoding="utf-8") as f:
            jobs = json.load(f)
        required = ["job_id", "account_id", "platform", "generation_mode", "status"]
        for r in required:
            if all(r in j for j in jobs):
                ok(f"sample_generation_jobs: '{r}' 全行に存在")
            else:
                fail(f"sample_generation_jobs: '{r}' 欠損行あり", "")


# ------------------------------------------------------------------ #
# 8. check_pipeline_integrity の新定数確認
# ------------------------------------------------------------------ #

def test_pipeline_integrity_constants() -> None:
    print("\n[Test 8] check_pipeline_integrity 新定数確認")

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_pipeline_integrity",
        os.path.join(_V2_ROOT, "scripts", "check_pipeline_integrity.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    checks = [
        ("VALID_GENERATION_JOB_STATUSES", {"pending", "in_progress", "done", "failed"}),
        ("VALID_CONFIDENCE_LEVELS", {"HIGH", "MEDIUM", "LOW"}),
        ("VALID_AI_RECOMMENDATIONS", {"recommend", "review", "reject"}),
        ("VALID_TEXT_POLICY_STATUSES", {"OK", "WARN", "FAIL"}),
    ]
    for const_name, expected_values in checks:
        const = getattr(module, const_name, None)
        if const is None:
            fail(f"check_pipeline_integrity.{const_name}", "定数が存在しない")
            continue
        for v in expected_values:
            if v in const:
                ok(f"{const_name} に '{v}'")
            else:
                fail(f"{const_name} に '{v}'", str(const))


# ------------------------------------------------------------------ #
# エントリーポイント
# ------------------------------------------------------------------ #

def main() -> None:
    print("=" * 60)
    print("Phase 2.13-2.16 テスト開始")
    print("=" * 60)

    test_tab_definitions_phase213_216()
    test_generation_planner()
    test_mock_sheets_generation_jobs()
    test_reference_based_generator()
    test_approval_scorer()
    test_text_policy_integration()
    test_fixtures()
    test_pipeline_integrity_constants()

    print("\n" + "=" * 60)
    print(f"結果: {_PASS} PASS / {_FAIL} FAIL")
    print("=" * 60)

    if _FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
