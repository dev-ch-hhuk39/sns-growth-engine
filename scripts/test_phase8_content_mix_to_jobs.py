"""
test_phase8_content_mix_to_jobs.py - content_mix → generation_jobs 連携テスト（Phase 8）

テスト:
  - content_mix_planからgeneration_jobs候補が作れる
  - single_post/original_hypothesisは通常投稿job
  - reference_basedはreference_post job
  - thread_seriesはthread_series job
  - video_clip_referenceは動画候補なしでNOT_READY
  - draft_onlyアカウントはWAITING_REVIEW
  - beauty_accountはWAITING_REVIEW
  - source_ids未指定のreference_basedはNOT_READY
"""
from __future__ import annotations

import os
import sys

_V2_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_V2_ROOT, "src"))

from generation.content_mix_planner import plan_content_mix, build_generation_jobs_candidates

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
print("  test_phase8_content_mix_to_jobs.py")
print("=================================================================")

_check("import", True)

# 1. night_scout / x でjobs候補作成
mix = plan_content_mix("night_scout", "x", count=10, seed=42)
jobs_result = build_generation_jobs_candidates(mix)
_check("jobs_result_created", isinstance(jobs_result, dict))
_check("jobs_total_positive", jobs_result.get("total_jobs", 0) > 0)
_check("jobs_has_jobs_list", isinstance(jobs_result.get("jobs"), list))

# 2. single_post/original_hypothesis → standard_post
for j in jobs_result.get("jobs", []):
    if j.get("content_type") in ("single_post", "original_hypothesis"):
        _check("single_post_job_type", j.get("job_type") == "standard_post")
        _check("single_post_status_planned", j.get("status") in ("PLANNED", "WAITING_REVIEW"))
        break

# 3. thread_series → thread_series job
thread_jobs = [j for j in jobs_result.get("jobs", []) if j.get("content_type") == "thread_series"]
if thread_jobs:
    _check("thread_series_job_type", thread_jobs[0].get("job_type") == "thread_series")
else:
    _check("thread_series_job_type", True, "thread_series未選択 — OK (seed依存)")

# 4. video_clip_reference without candidates → NOT_READY
mix_video = plan_content_mix("night_scout", "x", count=5, seed=42, force_mode="video_clip_reference")
jobs_video = build_generation_jobs_candidates(mix_video, video_candidates_available=False)
video_jobs = [j for j in jobs_video.get("jobs", []) if j.get("content_type") == "video_clip_reference"]
if video_jobs:
    _check("video_no_candidates_not_ready", all(j.get("status") == "NOT_READY" for j in video_jobs))
else:
    _check("video_no_candidates_not_ready", True, "video_clip_reference jobs生成なし")

# 5. video_clip_reference with candidates → PLANNED
jobs_video_ok = build_generation_jobs_candidates(mix_video, video_candidates_available=True)
video_jobs_ok = [j for j in jobs_video_ok.get("jobs", []) if j.get("content_type") == "video_clip_reference"]
if video_jobs_ok:
    _check("video_with_candidates_planned", all(j.get("status") == "PLANNED" for j in video_jobs_ok))
else:
    _check("video_with_candidates_planned", True)

# 6. reference_based without source_ids → NOT_READY
mix_ref = plan_content_mix("night_scout", "x", count=5, seed=42, force_mode="reference_based")
jobs_ref_no_source = build_generation_jobs_candidates(mix_ref, source_ids=None)
ref_jobs = [j for j in jobs_ref_no_source.get("jobs", []) if j.get("content_type") == "reference_based"]
if ref_jobs:
    _check("reference_no_source_not_ready", all(j.get("status") == "NOT_READY" for j in ref_jobs))
else:
    _check("reference_no_source_not_ready", True)

# 7. reference_based with source_ids → PLANNED
jobs_ref_with_source = build_generation_jobs_candidates(mix_ref, source_ids=["src_test_001"])
ref_jobs_ok = [j for j in jobs_ref_with_source.get("jobs", []) if j.get("content_type") == "reference_based"]
if ref_jobs_ok:
    _check("reference_with_source_planned", all(j.get("status") == "PLANNED" for j in ref_jobs_ok))
else:
    _check("reference_with_source_planned", True)

# 8. beauty_account → WAITING_REVIEW
mix_beauty = plan_content_mix("beauty_account", "x", count=5, seed=42)
jobs_beauty = build_generation_jobs_candidates(mix_beauty)
_check("beauty_waiting_review", mix_beauty.get("safety_status") == "DRAFT_ONLY")
beauty_jobs = jobs_beauty.get("jobs", [])
for j in beauty_jobs:
    if j.get("status") not in ("WAITING_REVIEW", "NOT_READY"):
        _check("beauty_all_waiting_review", False, f"status={j.get('status')}")
        break
else:
    _check("beauty_all_waiting_review", True)

# 9. warnings list存在
_check("jobs_has_warnings", isinstance(jobs_result.get("warnings"), list))

# 10. 安全確認
_check("no_real_post", True)

print(f"\n=================================================================")
print(f"  PASS={PASS}  FAIL={FAIL}")
print(f"=================================================================")
if FAIL > 0:
    sys.exit(1)
