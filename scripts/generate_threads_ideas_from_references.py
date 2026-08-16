#!/usr/bin/env python3
"""参考素材から Threads 投稿案を生成する標準 CLI（薄い入口）。

内部では既存スクリプトを再利用する:
  - --source references : generate_from_references.py（参考投稿から生成）
  - --source clips      : generate_from_video_clips.py（切り抜き候補から生成）

安全方針（プロジェクト CLAUDE.md 準拠）:
  - 既定はプランのみ（PLAN_ONLY）。委譲実行は --apply かつ --confirm-generate。
  - 投稿先は threads のみ（X は将来対応のみ・本 CLI からは生成しない）。
  - 本 CLI は「生成」だけを行う。委譲先（generate_from_references.py /
    generate_from_video_clips.py）は候補を作るだけで投稿 worker を呼ばない。
  - 生成候補は WAITING_REVIEW（レビュー待ち）で書き込まれる。worker の
    ELIGIBLE_STATUSES（={READY}）には含まれないため、生成直後は投稿されない。
    投稿されるには次の多層ゲートを通る:
      1. 生成候補は WAITING_REVIEW であり worker 非対象（worker は READY のみ拾う）。
      2. 本 CLI も委譲先も投稿処理を一切呼ばない（生成専用）。
      3. READY への昇格は approve_queue.py による人間承認、または
         auto_approve_queue.py による validator PASS / text-only / cap/cooldown PASS の
         AUTO_READY のみ。生成系CLIは READY を直接書かない。
      4. 実投稿には別経路 worker の三重ゲート（--confirm-real-post かつ
         PUBLISH_ENABLED=true かつ ALLOW_REAL_THREADS_POST=true）が必要。
         scheduled applyではworkflow apply step内だけ true になり、ローカルdry-runでは false。
      5. beauty_account / X は本 CLI で BLOCKED。
  - READYゲート: approve_queue.py（人間）または auto_approve_queue.py（AUTO_READY）。
    worker が READY のみを eligible 扱いすることで、生成と投稿を分離する。
  - beauty_account は対象外。
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from public_post_quality import (  # noqa: E402
    final_public_post_validator,
    generate_production_post,
    reader_facing_template_count,
)

CLI_NAME = "generate_threads_ideas_from_references"
ALLOWED_ACCOUNTS = {"night_scout", "liver_manager"}
ALLOWED_PLATFORMS = {"threads"}
# worker が拾うステータス（process_threads_queue.py の ELIGIBLE_STATUSES と一致させる）。
# READY のみが worker 対象。生成候補(WAITING_REVIEW)は worker 非対象であることを明示する。
ELIGIBLE_STATUSES = {"READY"}
# 委譲先が実際に書き込む候補ステータス（両委譲先とも WAITING_REVIEW 固定）。
CANDIDATE_STATUS = "WAITING_REVIEW"
# 実投稿に必要なゲート（scheduled apply step内だけtrue化される）。
REAL_POST_GATES = ["--confirm-real-post", "PUBLISH_ENABLED=true", "ALLOW_REAL_THREADS_POST=true"]
# READYレビューゲート（WAITING_REVIEW → READY/REJECTED）。
READY_GATE = "approve_queue.py or auto_approve_queue.py"
SIMILARITY_BLOCK_THRESHOLD = 0.62
MAX_QUOTE_CHARS = 80
from generation_quality_gates import batch_diversity_validator, evaluate_generation_quality, persisted_quality_evidence  # noqa: E402
from generation.reference_source_rewriter import (  # noqa: E402
    ReferenceRewriteError,
    reference_source_eligibility,
    rewrite_reference_post,
)
from generation.reference_generation_adapter import build_current_reference_generation_inputs  # noqa: E402
from learning.feature_attribution import preferred_primary_topics  # noqa: E402


ALLOWED_TRANSFORMATION_TYPES = {
    "structure_reference",
    "hook_reference",
    "topic_reference",
    "owned_media_caption",
}

DELEGATES = {
    "references": "scripts/generate_from_references.py",
    "clips": "scripts/generate_from_video_clips.py",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_")[:90]


def _to_float(value: Any) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _post_text(post: dict[str, Any]) -> str:
    return str(post.get("post_text") or post.get("text") or post.get("content") or "").strip()


def _normalize_for_similarity(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "").lower())


def original_text_similarity_guard(
    original_text: str,
    generated_text: str,
    *,
    threshold: float = SIMILARITY_BLOCK_THRESHOLD,
) -> dict[str, Any]:
    """Block drafts that are too close to reference wording."""
    original = _normalize_for_similarity(original_text)
    generated = _normalize_for_similarity(generated_text)
    if not original or not generated:
        return {"status": "PASS", "similarity": 0.0, "threshold": threshold, "reason": ""}
    similarity = difflib.SequenceMatcher(None, original, generated).ratio()
    copied_fragments = []
    matcher = difflib.SequenceMatcher(None, original, generated)
    for match in matcher.get_matching_blocks():
        if match.size >= 24:
            copied_fragments.append(original[match.a:match.a + match.size])
    copied_chars = sum(len(x) for x in copied_fragments)
    blocked = similarity >= threshold or copied_chars > MAX_QUOTE_CHARS
    return {
        "status": "BLOCKED" if blocked else "PASS",
        "similarity": round(similarity, 4),
        "threshold": threshold,
        "copied_chars": copied_chars,
        "quote_limit": MAX_QUOTE_CHARS,
        "reason": "generated_text is too similar to source text" if blocked else "",
    }


def direct_copy_block(original_text: str, generated_text: str) -> bool:
    return original_text_similarity_guard(original_text, generated_text)["status"] == "BLOCKED"


def build_rewritten_post_candidate(
    *,
    account_id: str,
    original_text: str,
    generated_text: str,
    transformation_type: str = "structure_reference",
    source_ref: str = "",
) -> dict[str, Any]:
    if transformation_type not in ALLOWED_TRANSFORMATION_TYPES:
        return {"status": "BLOCKED", "reason": "unsupported transformation_type", "transformation_type": transformation_type}
    guard = original_text_similarity_guard(original_text, generated_text)
    if guard["status"] == "BLOCKED":
        return {
            "status": "BLOCKED",
            "reason": guard["reason"],
            "transformation_type": transformation_type,
            "similarity_guard": guard,
            "generated_text": "",
            "candidate_status": "",
        }
    return {
        "status": "WAITING_REVIEW",
        "account_id": account_id,
        "generated_text": generated_text,
        "transformation_type": transformation_type,
        "similarity_guard": guard,
        "source_credit": "internal_reference_only",
        "source_ref": source_ref,
        "candidate_status": CANDIDATE_STATUS,
        "auto_publish": False,
    }




def build_thread_body(account_id: str, post: dict[str, Any], score: dict[str, Any], index: int) -> str:
    """Build a source-grounded reader-facing post using the real source text."""
    output = rewrite_reference_post(
        account_id=account_id,
        source=post,
        source_score=score,
        target_platform="threads",
        slot_theme="reference_text",
    )
    body = str(output["public_post_text"])
    validation = final_public_post_validator(body, account_id)
    if validation["status"] != "PASS":
        raise ValueError(f"public post failed validation: {validation['blocked_reasons']}")
    return body


def _feature_fields(output: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    design = dict(output.get("post_design") or {})
    policy = dict(output.get("generation_policy") or {})
    return {
        "batch_id": output.get("generation_batch_id", ""),
        "feature_schema_version": output.get("feature_schema_version", ""),
        "hook_text": design.get("hook_text", ""),
        "body_text": design.get("body_text", ""),
        "closing_text": design.get("closing_text", ""),
        "cta_intent": design.get("cta_intent", ""),
        "key_claims_json": json.dumps(design.get("key_claims", []), ensure_ascii=False),
        "post_design_json": json.dumps(design, ensure_ascii=False),
        "generation_policy_json": json.dumps(policy, ensure_ascii=False),
        "generation_attempt": output.get("generation_attempt", ""),
        "generation_rule_version": output.get("generation_rule_version", ""),
        **persisted_quality_evidence(quality),
    }


def _reference_quality(
    account_id: str,
    text: str,
    compared: list[dict[str, Any] | str],
    *,
    batch_compared: list[dict[str, Any] | str],
    structure_variant: str | int = "",
) -> dict[str, Any]:
    """Reference-specific quality: semantic fidelity replaces canned topic taxonomy.

    Account/persona safety is still enforced by final_public_post_validator.
    Diversity remains deterministic. The source-grounded Gemini judge is the
    topic-coherence authority for reference posts so arbitrary real source
    topics are not forced into the legacy fixed taxonomy.
    """
    diversity = batch_diversity_validator(
        account_id,
        text,
        compared,
        batch_compared=batch_compared,
        structure_variant=structure_variant,
    )
    passed = diversity["batch_diversity_status"] == "PASS"
    return {
        **diversity,
        "primary_topic": "source_grounded",
        "supporting_topics": [],
        "topic_confidence": 1.0,
        "primary_topic_evidence_score": 1,
        "primary_topic_direct_confidence": 1.0,
        "topic_coherence_status": "PASS",
        "topic_coherence_score": 100,
        "off_topic_sentence_count": 0,
        "off_topic_sentences": [],
        "hook_topic": "source_grounded",
        "closing_topic": "source_grounded",
        "visual_topic": "general",
        "visual_topic_confidence": 0.0,
        "visual_topic_direct_confidence": 0.0,
        "hook_topic_match": True,
        "closing_topic_match": True,
        "visual_topic_match": True,
        "topic_blocked_reasons": [],
        "quality_gate_version": "generation_quality_v3",
        "status": "PASS" if passed else "BLOCKED",
    }


def _structure_units(value: str) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if len(paragraphs) > 1:
        return paragraphs
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return lines
    sentences = [part.strip() for part in re.split(r"(?<=[.!?。！？])\s*", text) if part.strip()]
    return sentences or [text]


def reference_structure_fidelity(
    source_text: str,
    draft_text: str,
    *,
    source_platform: str = "",
    minimum_score: float = 0.55,
) -> dict[str, Any]:
    platform = str(source_platform or "").strip().lower()
    if platform in {"youtube", "youtube_shorts", "tiktok"}:
        return {
            "pass": True,
            "applicable": False,
            "score": 1.0,
            "minimum_score": minimum_score,
            "reason": "video transcript uses semantic fidelity; text-post layout preservation is not applicable",
        }
    source_units = _structure_units(source_text)
    draft_units = _structure_units(draft_text)
    if not source_units or not draft_units:
        return {
            "pass": False,
            "applicable": True,
            "score": 0.0,
            "minimum_score": minimum_score,
            "reason": "missing source or draft structure units",
        }
    count_score = min(len(source_units), len(draft_units)) / max(len(source_units), len(draft_units))
    if len(source_units) >= 3 and count_score < 0.5:
        return {
            "pass": False,
            "applicable": True,
            "score": round(count_score, 4),
            "minimum_score": minimum_score,
            "source_unit_count": len(source_units),
            "draft_unit_count": len(draft_units),
            "reason": "source structure collapsed too far",
        }
    source_list = bool(re.search(r"(?m)^\s*(?:[-*]|[0-9]+[.)])\s+", source_text))
    draft_list = bool(re.search(r"(?m)^\s*(?:[-*]|[0-9]+[.)])\s+", draft_text))
    if source_list and not draft_list:
        return {
            "pass": False,
            "applicable": True,
            "score": 0.0,
            "minimum_score": minimum_score,
            "source_unit_count": len(source_units),
            "draft_unit_count": len(draft_units),
            "reason": "source list structure was lost",
        }
    list_score = 1.0 if source_list == draft_list else 0.0
    source_question = bool(re.search(r"[?]", source_text))
    draft_question = bool(re.search(r"[?]", draft_text))
    question_score = 1.0 if source_question == draft_question else 0.5

    def bucket(unit: str) -> int:
        size = len(unit)
        if size <= 45:
            return 0
        if size <= 100:
            return 1
        return 2

    hook_score = 1.0 if bucket(source_units[0]) == bucket(draft_units[0]) else 0.5
    close_score = 1.0 if bucket(source_units[-1]) == bucket(draft_units[-1]) else 0.5
    score = round(
        0.50 * count_score
        + 0.15 * list_score
        + 0.10 * question_score
        + 0.15 * hook_score
        + 0.10 * close_score,
        4,
    )
    return {
        "pass": score >= minimum_score,
        "applicable": True,
        "score": score,
        "minimum_score": minimum_score,
        "source_unit_count": len(source_units),
        "draft_unit_count": len(draft_units),
        "reason": "structure preserved" if score >= minimum_score else "source structure drifted too far",
    }


def build_generation_rows(
    *,
    account_id: str,
    posts: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    top_n: int,
    slot_id: str = "",
    post_type: str = "reference_text",
    theme: str = "",
    schedule_date_jst: str = "",
    history: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    posts_by_id = {str(p.get("post_id", "")): p for p in posts}
    usable_scores = [
        s for s in scores
        if str(s.get("account_id", "")) == account_id
        and str(s.get("reference_post_id") or s.get("collected_post_id", "")) in posts_by_id
    ]
    usable_scores.sort(key=lambda s: _to_float(s.get("total_score")), reverse=True)
    created = now_iso()
    drafts: list[dict[str, Any]] = []
    derivatives: list[dict[str, Any]] = []
    queues: list[dict[str, Any]] = []
    recent = [str(value) for value in (history or []) if str(value)]
    accepted: list[dict[str, Any]] = []
    batch_id = f"scheduled_{account_id}_{schedule_date_jst or datetime.now(timezone.utc).strftime('%Y%m%d')}_{slot_id or 'reference'}"
    generation_attempts = 0
    max_generation_attempts = max(top_n * 2, top_n + 2)
    for score in usable_scores:
        if len(queues) >= top_n:
            break
        ref_id = str(score.get("reference_post_id") or score.get("collected_post_id", ""))
        post = posts_by_id[ref_id]
        eligibility = reference_source_eligibility(post)
        if not eligibility["eligible"]:
            print(
                f"[reference-rewrite] skip source={ref_id}: ineligible={eligibility['reason']}",
                file=sys.stderr,
            )
            continue
        if generation_attempts >= max_generation_attempts:
            print(
                f"[reference-rewrite] stop after {generation_attempts} Gemini generation attempts; target={top_n}",
                file=sys.stderr,
            )
            break
        generation_attempts += 1
        i = generation_attempts
        stable = _safe_id(f"{account_id}_{ref_id}")
        draft_id = f"idea_{stable}"
        derivative_id = f"sd_{stable}_threads"
        queue_id = f"q_{stable}_threads"
        try:
            output = rewrite_reference_post(
                account_id=account_id,
                source=post,
                source_score=score,
                target_platform="threads",
                slot_theme=post_type,
            )
        except ReferenceRewriteError as exc:
            message = str(exc)
            print(f"[reference-rewrite] skip source={ref_id}: {message}", file=sys.stderr)
            # _call_gemini already performs bounded retry/backoff for retryable
            # 429 responses. If it still returns RESOURCE_EXHAUSTED, moving to
            # another source only burns more quota/rate-limit budget. Stop the
            # current batch and fail closed; a later scheduled run may retry.
            if "Gemini API returned HTTP 429" in message and "RESOURCE_EXHAUSTED" in message:
                print(
                    "[reference-rewrite] stop batch: Gemini 429 remained after bounded retries",
                    file=sys.stderr,
                )
                break
            continue
        body = str(output.get("public_post_text", ""))
        structure_fidelity = reference_structure_fidelity(
            _post_text(post),
            body,
            source_platform=str(post.get("source_platform") or post.get("platform") or ""),
        )
        if not structure_fidelity["pass"]:
            print(
                f"[reference-rewrite] skip source={ref_id}: structure_fidelity={structure_fidelity['score']}",
                file=sys.stderr,
            )
            continue
        validation = final_public_post_validator(body, account_id)
        quality = _reference_quality(
            account_id, body, recent + accepted, batch_compared=accepted,
            structure_variant=output.get("grounding_summary", {}).get("structure_variant", ""),
        )
        if validation["status"] != "PASS" or quality["status"] != "PASS":
            continue
        output["generation_batch_id"] = batch_id
        output["generation_attempt"] = i
        output["generation_rule_version"] = "source_grounded_gemini_v1"
        feature_fields = _feature_fields(output, quality)
        candidate = build_rewritten_post_candidate(
            account_id=account_id,
            original_text=_post_text(post),
            generated_text=body,
            transformation_type="structure_reference",
            source_ref=ref_id,
        )
        if candidate["status"] == "BLOCKED":
            continue
        similarity_guard = candidate["similarity_guard"]
        title = body.splitlines()[0][:80]
        drafts.append({
            "draft_id": draft_id,
            "created_at": created,
            "account_id": account_id,
            "title": title,
            "body_md": body,
            "content": body,
            "cta_text": "必要ならプロフィールから相談",
            "source_refs": ref_id,
            "status": CANDIDATE_STATUS,
            "generation_model": CLI_NAME,
            "generation_mode": post_type,
            "content_route": post_type,
            "source_content_route": "",
            "source_generation_mode": "",
            "source_result_id": "",
            "media_strategy": "none",
            "imitation_risk": "low",
            "media_reuse_risk": "not_applicable",
            "transformation_type": "structure_reference",
            "source_credit": "internal_reference_only",
            "similarity_score": str(similarity_guard["similarity"]),
            "direct_copy_guard": similarity_guard["status"],
            "buzz_potential_score": str(score.get("total_score", "")),
            "conversion_potential_score": str(score.get("cta_score", "")),
            "confidence_level": "medium",
            "ai_publish_recommendation": CANDIDATE_STATUS,
            "notes": "Generated from actual source content with semantic-fidelity gating. AUTO_READY or human review required. No third-party media reuse.",
        })
        derivatives.append({
            "derivative_id": derivative_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "platform": "threads",
            "text": body,
            "hashtags": "",
            "status": CANDIDATE_STATUS,
            "reason": "AUTO_READY evaluation or human review required before READY.",
            "created_at": created,
            "char_count": str(len(body)),
            "text_policy_status": "PENDING",
            "media_strategy": "none",
            "transformation_type": "structure_reference",
            "source_credit": "internal_reference_only",
            "similarity_score": str(similarity_guard["similarity"]),
        })
        queues.append({
            "queue_id": queue_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "target_account_id": account_id,
            "platform": "threads",
            "scheduled_at": "",
            "priority": str(60 + i),
            "status": CANDIDATE_STATUS,
            "error": "",
            "created_at": created,
            "processed_at": "",
            "auto_publish": "false",
            "generation_mode": "reference_score_to_threads",
            "content_type": post_type,
            "content_route": post_type,
            "source_content_route": "",
            "source_generation_mode": "",
            "source_result_id": "",
            "confidence_level": "medium",
            "ai_publish_recommendation": CANDIDATE_STATUS,
            "media_asset_id": "",
            "text_policy_status": "PENDING",
            "rights_status": "not_required",
            "permission_status": "not_required",
            "rights_review_required": "false",
            "media_reuse_risk": "not_applicable",
            "public_post_text": body,
            "internal_analysis": f"Generated from reference_score_to_threads for source_id={post.get('source_id', '')}; public_post_text only is publishable.",
            "source_id": post.get("source_id", ""),
            "source_url": post.get("post_url", ""),
            "generated_by": CLI_NAME,
            "slot_id": slot_id, "theme": theme, "schedule_date_jst": schedule_date_jst,
            "validator_status": validation["status"],
            "internal_leak_status": validation["internal_leak_check"]["status"],
            "account_fit_status": validation["account_fit_check"]["status"],
            "public_post_quality_score": str(validation["public_post_quality_score"]),
            "reader_value_score": str(validation["reader_value_score"]),
            "naturalness_score": str(validation["naturalness_score"]),
            "cta_pressure_score": str(validation["cta_pressure_score"]),
            **feature_fields,
            "rejected_reason": "",
            "blocked_reason": "",
            "updated_at": created,
        })
        accepted.append({
            "account_id": account_id, "candidate_id": queue_id, "batch_id": batch_id,
            "primary_topic": quality.get("primary_topic", ""),
            "structure_variant": quality.get("structure_variant", ""),
            "public_post_text": body,
        })
        recent.append(body)
    for q in queues:
        assert q["status"] not in ELIGIBLE_STATUSES, "generated queue must not be worker-selectable"
        assert q["auto_publish"] == "false"
    return {"drafts": drafts, "social_derivatives": derivatives, "queue": queues}


def _fallback_template_index(offset: int, account_id: str, *, slot_id: str = "", schedule_date_jst: str = "", history: list[str] | None = None, reason: str = "") -> int:
    """Rotate safe original templates across daily runs without source data."""
    jst = timezone(timedelta(hours=9))
    now = datetime.now(timezone.utc).astimezone(jst)
    count = max(1, reader_facing_template_count(account_id))
    date_seed = schedule_date_jst or now.strftime("%Y-%m-%d")
    history_seed = sum(sum(map(ord, text[:120])) for text in (history or [])[-30:])
    seed = sum(map(ord, f"{account_id}|{slot_id}|{date_seed}|{reason}")) + history_seed
    return ((seed + offset * 7) % count) + 1


# Keep fallback generation bounded while allowing the strict validator,
# topic-coherence, diversity and duplicate gates to reject unsuitable
# local compositions. No quality threshold is relaxed.
FALLBACK_ATTEMPTS_PER_SLOT = 64


def build_fallback_generation_rows(
    *,
    account_id: str,
    top_n: int,
    slot_id: str = "",
    post_type: str = "original_text",
    content_route: str = "",
    theme: str = "",
    schedule_date_jst: str = "",
    history: list[str] | None = None,
    fallback_reason: str = "reference_unavailable",
    preferred_topics: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build safe reader-facing original candidates when reference data is empty.

    This is the production recovery path for scheduled autonomous posting: it
    keeps the public text separate, validates it, writes WAITING_REVIEW only,
    and lets auto_approve_queue decide whether it may become READY.
    """
    resolved_content_route = (
        str(content_route or post_type).strip()
        or post_type
    )
    created = now_iso()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    drafts: list[dict[str, Any]] = []
    derivatives: list[dict[str, Any]] = []
    queues: list[dict[str, Any]] = []
    recent = [str(value) for value in (history or []) if str(value)]
    accepted: list[dict[str, Any]] = []
    batch_id = f"scheduled_{account_id}_{schedule_date_jst or datetime.now(timezone.utc).strftime('%Y%m%d')}_{slot_id or fallback_reason}"
    for i in range(1, max(1, top_n) + 1):
        selected = None
        for attempt in range(FALLBACK_ATTEMPTS_PER_SLOT):
            output = generate_production_post(
                account_id,
                batch_id=batch_id,
                content_type=post_type,
                recent_posts=recent,
                attempt=attempt + i - 1,
                excluded_topics=[str(row.get("primary_topic", "")) for row in accepted],
                preferred_topics=preferred_topics or [],
            )
            body = str(output.get("public_post_text", ""))
            validation = final_public_post_validator(body, account_id)
            quality = evaluate_generation_quality(
                account_id, body, recent + accepted, batch_compared=accepted,
                structure_variant=output.get("grounding_summary", {}).get("structure_variant", ""),
                primary_topic=output.get("grounding_summary", {}).get("quality_topic", ""),
            )
            duplicate = any(original_text_similarity_guard(old, body)["status"] == "BLOCKED" for old in recent[-30:])
            if body and validation["status"] == "PASS" and quality["status"] == "PASS" and not duplicate:
                selected = (output, body, validation, quality)
                break
        if selected is None:
            continue
        output, body, validation, quality = selected
        feature_fields = _feature_fields(output, quality)
        stable = _safe_id(f"{account_id}_fallback_{stamp}_{i}")
        draft_id = f"idea_{stable}"
        derivative_id = f"sd_{stable}_threads"
        queue_id = f"q_{stable}_threads"
        title = body.splitlines()[0][:80]
        drafts.append({
            "draft_id": draft_id,
            "created_at": created,
            "account_id": account_id,
            "title": title,
            "body_md": body,
            "content": body,
            "cta_text": "必要ならプロフィールから相談",
            "source_refs": "",
            "status": CANDIDATE_STATUS,
            "generation_model": CLI_NAME,
            "generation_mode": post_type,
            "content_route": resolved_content_route,
            "source_content_route": "",
            "source_generation_mode": "",
            "source_result_id": "",
            "media_strategy": "none",
            "imitation_risk": "low",
            "media_reuse_risk": "not_applicable",
            "transformation_type": "original_hypothesis",
            "source_credit": "none",
            "similarity_score": "0.0",
            "direct_copy_guard": "PASS",
            "buzz_potential_score": "",
            "conversion_potential_score": "",
            "confidence_level": "medium",
            "ai_publish_recommendation": CANDIDATE_STATUS,
            "notes": "Safe original fallback for autonomous text-only posting when reference rows are empty.",
        })
        derivatives.append({
            "derivative_id": derivative_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "platform": "threads",
            "text": body,
            "hashtags": "",
            "status": CANDIDATE_STATUS,
            "reason": "AUTO_READY evaluation required before posting.",
            "created_at": created,
            "char_count": str(len(body)),
            "text_policy_status": "PASS",
            "media_strategy": "none",
            "transformation_type": "original_hypothesis",
            "source_credit": "none",
            "similarity_score": "0.0",
        })
        queues.append({
            "queue_id": queue_id,
            "draft_id": draft_id,
            "account_id": account_id,
            "target_account_id": account_id,
            "platform": "threads",
            "scheduled_at": "",
            "priority": str(50 + i),
            "status": CANDIDATE_STATUS,
            "error": "",
            "created_at": created,
            "processed_at": "",
            "auto_publish": "false",
            "generation_mode": post_type,
            "content_type": post_type,
            "content_route": resolved_content_route,
            "source_content_route": "",
            "source_generation_mode": "",
            "source_result_id": "",
            "confidence_level": "medium",
            "ai_publish_recommendation": CANDIDATE_STATUS,
            "media_asset_id": "",
            "text_policy_status": "PASS",
            "rights_status": "not_required",
            "permission_status": "not_required",
            "rights_review_required": "false",
            "media_reuse_risk": "not_applicable",
            "public_post_text": body,
            "internal_analysis": "Safe original fallback; public_post_text only is publishable.",
            "source_id": "",
            "source_url": "",
            "generated_by": CLI_NAME,
            "slot_id": slot_id,
            "theme": theme,
            "schedule_date_jst": schedule_date_jst,
            "validator_status": validation["status"],
            "internal_leak_status": validation["internal_leak_check"]["status"],
            "account_fit_status": validation["account_fit_check"]["status"],
            "public_post_quality_score": str(validation["public_post_quality_score"]),
            "reader_value_score": str(validation["reader_value_score"]),
            "naturalness_score": str(validation["naturalness_score"]),
            "cta_pressure_score": str(validation["cta_pressure_score"]),
            **feature_fields,
            "rejected_reason": "",
            "blocked_reason": "",
            "updated_at": created,
        })
        accepted.append({
            "account_id": account_id, "candidate_id": queue_id, "batch_id": batch_id,
            "primary_topic": quality.get("primary_topic", ""),
            "structure_variant": quality.get("structure_variant", ""),
            "public_post_text": body,
        })
        recent.append(body)
    return {"drafts": drafts, "social_derivatives": derivatives, "queue": queues}


LOCKED_GENERATION_STATUSES = {"READY", "PROCESSING", "POSTED", "MEDIA_READY"}


def _row_status(row: dict[str, Any]) -> str:
    return str(row.get("status") or row.get("ai_publish_recommendation") or "").strip().upper()


def _append_missing(client: Any, logical: str, key: str, rows: list[dict[str, Any]]) -> dict[str, int]:
    if not rows:
        return {"added": 0, "skipped": 0, "refreshed": 0}
    from gspread.utils import rowcol_to_a1

    # Keep the physical Sheets schema synchronized before serializing a
    # generated row. Without this, fields present in the row dictionary but
    # absent from the header are silently discarded.
    ensure_tab = getattr(
        client,
        "_ensure_tab",
        None,
    )

    if callable(ensure_tab):
        from sheets_client import (
            TAB_DEFINITIONS,
        )

        if logical not in TAB_DEFINITIONS:
            raise KeyError(
                f"unknown logical tab: {logical}"
            )

        ws = ensure_tab(
            logical,
            TAB_DEFINITIONS[logical],
        )
    else:
        # Minimal test adapters may expose only _ws.
        ws = client._ws(logical)

    headers = ws.row_values(1)
    existing_rows: dict[str, tuple[int, dict[str, Any]]] = {}
    for row_number, existing in enumerate(ws.get_all_records(), start=2):
        existing_rows[str(existing.get(key, ""))] = (row_number, dict(existing))
    added = skipped = refreshed = 0
    update_ranges: list[dict[str, Any]] = []
    append_values: list[list[str]] = []
    for row in rows:
        row_key = str(row.get(key, ""))
        existing_info = existing_rows.get(row_key)
        if existing_info:
            row_number, existing = existing_info
            if _row_status(existing) in LOCKED_GENERATION_STATUSES:
                skipped += 1
                continue
            refreshed_row = {**existing, **row}
            update_ranges.append({
                "range": f"{rowcol_to_a1(row_number, 1)}:{rowcol_to_a1(row_number, len(headers))}",
                "values": [[str(refreshed_row.get(h, "")) for h in headers]],
            })
            existing_rows[row_key] = (row_number, refreshed_row)
            refreshed += 1
            continue
        append_values.append([str(row.get(h, "")) for h in headers])
        existing_rows[row_key] = (-1, dict(row))
        added += 1
    if update_ranges:
        batch_update = getattr(ws, "batch_update", None)
        if callable(batch_update):
            batch_update(update_ranges, value_input_option="USER_ENTERED")
        else:
            # Keep the helper compatible with minimal worksheet adapters while
            # production gspread still receives one bounded batch request.
            for update in update_ranges:
                row_number = int(re.match(r"[A-Z]+(\d+):", update["range"]).group(1))
                values = update["values"][0]
                for col, value in enumerate(values, start=1):
                    ws.update_cell(row_number, col, str(value))
    if append_values:
        ws.append_rows(append_values, value_input_option="USER_ENTERED")
    return {"added": added, "skipped": skipped, "refreshed": refreshed}


def measured_pdca_snapshots(
    metric_snapshots: list[dict[str, Any]],
    posted_results: list[dict[str, Any]],
    *,
    account_id: str,
) -> list[dict[str, Any]]:
    """Return only measured snapshots tied to valid Threads posts."""

    valid_results = {
        str(
            row.get(
                "result_id",
                "",
            )
        )
        for row in posted_results
        if (
            str(
                row.get(
                    "account_id",
                    "",
                )
            )
            == account_id
            and str(
                row.get(
                    "platform",
                    "threads",
                )
            ).lower()
            == "threads"
            and str(
                row.get(
                    "status",
                    "",
                )
            ).upper()
            == "POSTED"
            and str(
                row.get(
                    "result_id",
                    "",
                )
            ).strip()
        )
    }

    required_metrics = (
        "views",
        "likes",
        "comments",
    )

    selected = [
        dict(row)
        for row in metric_snapshots
        if (
            str(
                row.get(
                    "account_id",
                    "",
                )
            )
            == account_id
            and str(
                row.get(
                    "platform",
                    "threads",
                )
            ).lower()
            == "threads"
            and str(
                row.get(
                    "metrics_status",
                    "",
                )
            ).upper()
            == "MEASURED"
            and str(
                row.get(
                    "result_id",
                    "",
                )
            )
            in valid_results
            and all(
                str(
                    row.get(
                        metric,
                        "",
                    )
                ).strip()
                != ""
                for metric in required_metrics
            )
        )
    ]

    selected.sort(
        key=lambda row: (
            str(
                row.get(
                    "collected_at",
                    "",
                )
            ),
            str(
                row.get(
                    "snapshot_id",
                    "",
                )
            ),
        ),
        reverse=True,
    )

    return selected



PDCA_STRUCTURE_STRATEGIES = (
    "同じテーマで、読者が次に抱く疑問へ答える",
    "成功した切り口を、初心者向けの具体例に置き換える",
    "同じ悩みを、失敗回避の観点から説明する",
    "結論を先に示し、実行手順を短く整理する",
    "比較形式に変えて、判断基準を分かりやすくする",
    "読者が今日試せる一つの行動に絞る",
)

PDCA_PUBLIC_DISCLOSURE_PATTERNS = (
    r"前回の投稿",
    r"前回[^\n。]{0,30}(?:表示|いいね|コメント)",
    r"表示\s*\d+\s*件?",
    r"いいね\s*\d+\s*件",
    r"コメント\s*\d+\s*件",
    r"前回を上回るか",
    r"実測(?:値|結果)",
)


def pdca_public_text_policy(text: str) -> dict[str, Any]:
    """Keep metrics and prior-post analysis out of reader-facing copy."""

    value = str(text or "").strip()
    hits = [
        pattern
        for pattern in PDCA_PUBLIC_DISCLOSURE_PATTERNS
        if re.search(pattern, value, re.IGNORECASE)
    ]
    return {
        "status": "PASS" if value and not hits else "BLOCKED",
        "blocked_patterns": hits,
        "reason": "" if value and not hits else "pdca_internal_learning_disclosed_in_public_text",
    }


def _pdca_metric_int(
    value: Any,
) -> int:
    try:
        return max(
            0,
            int(
                float(
                    str(
                        value
                        if value is not None
                        else 0
                    ).strip()
                    or "0"
                )
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0


def _pdca_result_text(
    row: dict[str, Any],
) -> str:
    for field in (
        "posted_text",
        "public_post_text",
        "content",
        "text",
        "body_md",
        "caption",
    ):
        value = str(
            row.get(
                field,
                "",
            )
        ).strip()

        if value:
            return value

    return ""


def _pdca_snapshot_sort_key(
    row: dict[str, Any],
) -> tuple[int, str, str]:
    return (
        _pdca_metric_int(
            row.get(
                "collection_window_hours",
                0,
            )
        ),
        str(
            row.get(
                "collected_at",
                "",
            )
        ),
        str(
            row.get(
                "snapshot_id",
                "",
            )
        ),
    )


def build_measured_pdca_inputs(
    *,
    measured_rows: list[dict[str, Any]],
    posted_results: list[dict[str, Any]],
    account_id: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    """Convert measured owned posts into standard generation inputs."""

    if account_id not in ALLOWED_ACCOUNTS:
        raise ValueError("unsupported_pdca_account_id")

    posted_by_result = {
        str(
            row.get(
                "result_id",
                "",
            )
        ): dict(row)
        for row in posted_results
        if (
            str(
                row.get(
                    "account_id",
                    "",
                )
            )
            == account_id
            and str(row.get("platform", "threads")).lower() == "threads"
            and str(row.get("status", "")).upper() == "POSTED"
            and str(
                row.get(
                    "result_id",
                    "",
                )
            ).strip()
        )
    }

    latest_by_result: dict[
        str,
        dict[str, Any],
    ] = {}

    for snapshot in measured_rows:
        if (
            str(snapshot.get("account_id", "")) != account_id
            or str(snapshot.get("platform", "threads")).lower() != "threads"
            or str(snapshot.get("metrics_status", "")).upper() != "MEASURED"
        ):
            continue
        result_id = str(
            snapshot.get(
                "result_id",
                "",
            )
        ).strip()

        if (
            not result_id
            or result_id
            not in posted_by_result
        ):
            continue

        existing = latest_by_result.get(
            result_id
        )

        if (
            existing is None
            or _pdca_snapshot_sort_key(
                snapshot
            )
            > _pdca_snapshot_sort_key(
                existing
            )
        ):
            latest_by_result[result_id] = (
                dict(snapshot)
            )

    ranked: list[dict[str, Any]] = []

    for result_id, snapshot in (
        latest_by_result.items()
    ):
        posted = posted_by_result[
            result_id
        ]

        source_text = _pdca_result_text(
            posted
        )

        if not source_text:
            continue

        views = _pdca_metric_int(
            snapshot.get("views")
        )

        likes = _pdca_metric_int(
            snapshot.get("likes")
        )

        comments = _pdca_metric_int(
            snapshot.get("comments")
        )

        reposts = _pdca_metric_int(
            snapshot.get("reposts")
        )

        quotes = _pdca_metric_int(
            snapshot.get("quotes")
        )

        engagement_actions = (
            likes
            + comments
            + reposts
            + quotes
        )
        engagement_rate = (
            engagement_actions / views
            if views > 0
            else 0.0
        )

        # A zero-signal row cannot support a claim that a pattern worked.
        # Keep the PDCA slot fail closed until owned-post evidence contains at
        # least one measured reaction.
        if views <= 0 or engagement_actions <= 0:
            continue

        source_route = str(
            posted.get(
                "content_route",
                "",
            )
            or posted.get(
                "content_type",
                "",
            )
            or "unknown"
        )

        source_generation_mode = str(
            posted.get(
                "generation_mode",
                "",
            )
            or "unknown"
        )

        ranked.append(
            {
                "account_id": account_id,
                "result_id": result_id,
                "source_text": source_text,
                "source_route": (
                    source_route
                ),
                "source_generation_mode": (
                    source_generation_mode
                ),
                "source_url": str(
                    posted.get(
                        "post_url",
                        "",
                    )
                ),
                "theme": str(
                    posted.get(
                        "theme",
                        "",
                    )
                ),
                "views": views,
                "likes": likes,
                "comments": comments,
                "reposts": reposts,
                "quotes": quotes,
                "engagement_rate": (
                    engagement_rate
                ),
                "collected_at": str(
                    snapshot.get(
                        "collected_at",
                        "",
                    )
                ),
            }
        )

    ranked.sort(
        key=lambda row: (
            float(
                row[
                    "engagement_rate"
                ]
            ),
            int(row["views"]),
            str(row["collected_at"]),
        ),
        reverse=True,
    )

    posts: list[dict[str, Any]] = []
    scores: list[dict[str, Any]] = []
    source_meta: dict[
        str,
        dict[str, Any],
    ] = {}

    for rank, item in enumerate(
        ranked,
        1,
    ):
        result_id = str(
            item["result_id"]
        )

        source_meta[result_id] = dict(
            item
        )

        for variant, strategy in enumerate(
            PDCA_STRUCTURE_STRATEGIES,
            1,
        ):
            synthetic_post_id = (
                f"pdca_metric_"
                f"{_safe_id(result_id)}_"
                f"{variant:02d}"
            )

            posts.append(
                {
                    "account_id": account_id,
                    "post_id": (
                        synthetic_post_id
                    ),
                    "post_text": (
                        item["source_text"]
                    ),
                    "title": (
                        "アカウント内で学習した構成を"
                        "新規投稿に反映する。"
                        f"公開本文の方針: {strategy}"
                    ),
                    "category": (
                        item["source_route"]
                    ),
                    "source_id": result_id,
                    "post_url": (
                        item["source_url"]
                    ),
                    "pdca_learning_only": True,
                }
            )

            total_score = (
                float(
                    item[
                        "engagement_rate"
                    ]
                )
                * 1_000_000
                + int(item["views"])
                - rank
                - variant / 100
            )

            scores.append(
                {
                    "account_id": (
                        account_id
                    ),
                    "reference_post_id": (
                        synthetic_post_id
                    ),
                    "total_score": (
                        total_score
                    ),
                    "cta_score": (
                        item["comments"]
                    ),
                    "reusable_pattern": (
                        strategy
                    ),
                    "reason": (
                        f"{account_id}だけのMEASURED自社投稿から"
                        "内部学習した構成を、過去投稿や"
                        "metricsに言及しない新規本文へ反映する"
                    ),
                }
            )

    return (
        posts,
        scores,
        source_meta,
    )



def build_measured_pdca_public_text(
    *,
    account_id: str,
    meta: dict[str, Any],
) -> str:
    """Build a standalone fallback from learning, never a metrics report."""

    if account_id not in ALLOWED_ACCOUNTS:
        raise ValueError("unsupported_pdca_account_id")
    source = str(meta.get("source_text", "")).replace("\\n", "\n").strip()
    if account_id == "night_scout":
        if any(term in source for term in ("時給", "控除", "手取り")):
            text = (
                "体入で時給だけを見て決めると、給料日に『思ったより残らない』ってなることが結構ある。\n\n"
                "僕が入店前に見るのは、控除の種類、早上がりの扱い、バックが付く条件。この3つなんだよね。\n\n"
                "表示時給より、同じ出勤ペースで実際にいくら残るかを見る。ここまで聞いてから選ぶ方が、自分に合う店を見つけやすいよ。"
            )
        else:
            text = (
                "店選びで条件が良く見えても、客層と出勤ペースが合わないと続きにくい。\n\n"
                "僕なら体入の日に、忙しい時間帯、早上がりの条件、担当に相談しやすいかを見る。\n\n"
                "時給の高さだけじゃなく、自分が無理なく続けられるかで決めるのが大事だよ。"
            )
    else:
        text = (
            "配信の終わりに『また来てね』だけで終わると、初見さんは次に来る理由を作りにくい。\n\n"
            "私なら最後の1分で、次の配信時間と話すテーマを一つだけ伝えるかな。予定が分かると、今日初めて来た人も戻りやすいんだよね。\n\n"
            "次回予告は長くしなくて大丈夫。『明日21時に○○の話をするよ』まで用意してみてね。"
        )
    policy = pdca_public_text_policy(text)
    if policy["status"] != "PASS":
        raise ValueError(policy["reason"])
    return text


def apply_measured_pdca_lineage(
    rows: dict[
        str,
        list[dict[str, Any]],
    ],
    *,
    account_id: str = "",
    source_meta: dict[
        str,
        dict[str, Any],
    ],
    top_n: int,
) -> dict[
    str,
    list[dict[str, Any]],
]:
    """Keep only requested candidates and mark their real metric lineage."""

    if account_id not in ALLOWED_ACCOUNTS:
        raise ValueError("unsupported_pdca_account_id")

    selected_queues = [
        dict(row)
        for row in rows.get(
            "queue",
            [],
        )[:max(1, top_n)]
    ]

    selected_draft_ids = {
        str(
            row.get(
                "draft_id",
                "",
            )
        )
        for row in selected_queues
    }

    queue_meta_by_draft: dict[
        str,
        dict[str, Any],
    ] = {}

    for queue in selected_queues:
        if str(queue.get("account_id", "")).strip() != account_id:
            raise ValueError("pdca_queue_account_mismatch")
        result_id = str(
            queue.get(
                "source_id",
                "",
            )
        ).strip()

        meta = source_meta.get(
            result_id,
            {},
        )
        if str(meta.get("account_id", "")) != account_id:
            raise ValueError("pdca_source_account_mismatch")
        public_text = str(queue.get("public_post_text", "")).strip()
        if not public_text:
            public_text = build_measured_pdca_public_text(account_id=account_id, meta=meta)
        public_policy = pdca_public_text_policy(public_text)
        if public_policy["status"] != "PASS":
            raise ValueError(public_policy["reason"])
        public_validation = final_public_post_validator(public_text, account_id)
        if public_validation["status"] != "PASS":
            raise ValueError("pdca_public_post_validator_blocked")
        queue["public_post_text"] = public_text
        queue["key_claims_json"] = "[]"

        queue[
            "generation_mode"
        ] = "metrics_driven_pdca_text"

        queue["content_type"] = (
            "pdca_text"
        )

        queue["content_route"] = (
            "pdca_text"
        )

        queue["source_result_id"] = (
            result_id
        )

        queue[
            "source_content_route"
        ] = str(
            meta.get(
                "source_route",
                "",
            )
        )

        queue[
            "source_generation_mode"
        ] = str(
            meta.get(
                "source_generation_mode",
                "",
            )
        )

        queue["transformation_type"] = "metrics_learned_original"

        queue["source_credit"] = "internal_learning_only"
        queue["pdca_learning_account_id"] = account_id
        queue["pdca_learning_scope_id"] = f"account:{account_id}"
        queue["pdca_public_text_policy_status"] = "PASS"
        queue["metrics_disclosure_status"] = "PASS"

        queue["confidence_level"] = (
            "high"
        )

        queue["text_policy_status"] = (
            "PASS"
        )

        queue["internal_analysis"] = (
            f"Account-isolated learning for {account_id}. "
            f"source_result_id={result_id}; "
            f"engagement_rate="
            f"{meta.get('engagement_rate', 0):.6f}; "
            "metrics and prior-post analysis are internal only; "
            "public_post_text is a standalone new post."
        )

        queue_meta_by_draft[
            str(
                queue.get(
                    "draft_id",
                    "",
                )
            )
        ] = {
            "result_id": result_id,
            **meta,
        }

    queue_text_by_draft = {
        str(row.get("draft_id", "")): str(row.get("public_post_text", ""))
        for row in selected_queues
    }

    selected_drafts = []

    for row in rows.get(
        "drafts",
        [],
    ):
        draft_id = str(
            row.get(
                "draft_id",
                "",
            )
        )

        if draft_id not in (
            selected_draft_ids
        ):
            continue

        copied = dict(row)
        pdca_text = queue_text_by_draft.get(draft_id, "")
        if pdca_text:
            copied["body_md"] = pdca_text
            copied["content"] = pdca_text
            copied["title"] = pdca_text.splitlines()[0][:80]
        meta = queue_meta_by_draft.get(
            draft_id,
            {},
        )

        copied[
            "generation_mode"
        ] = "metrics_driven_pdca_text"

        copied["content_route"] = (
            "pdca_text"
        )

        copied["source_result_id"] = (
            meta.get(
                "result_id",
                "",
            )
        )

        copied[
            "source_content_route"
        ] = meta.get(
            "source_route",
            "",
        )

        copied[
            "source_generation_mode"
        ] = meta.get(
            "source_generation_mode",
            "",
        )

        copied["transformation_type"] = "metrics_learned_original"

        copied["source_credit"] = "internal_learning_only"

        copied["confidence_level"] = (
            "high"
        )

        copied["notes"] = (
            f"Account-isolated PDCA learning for {account_id}. "
            "Metrics remain internal; public text is a standalone new post. "
            "WAITING_REVIEW only."
        )

        selected_drafts.append(
            copied
        )

    selected_derivatives = []

    for row in rows.get(
        "social_derivatives",
        [],
    ):
        draft_id = str(
            row.get(
                "draft_id",
                "",
            )
        )

        if draft_id not in (
            selected_draft_ids
        ):
            continue

        copied = dict(row)
        pdca_text = queue_text_by_draft.get(draft_id, "")
        if pdca_text:
            copied["text"] = pdca_text
            copied["char_count"] = str(len(pdca_text))

        copied["transformation_type"] = "metrics_learned_original"

        copied["source_credit"] = "internal_learning_only"

        copied["text_policy_status"] = (
            "PASS"
        )

        copied["reason"] = (
            "Account-isolated learned pattern applied to a new standalone post. "
            "Review required."
        )

        selected_derivatives.append(
            copied
        )

    return {
        "drafts": selected_drafts,
        "social_derivatives": (
            selected_derivatives
        ),
        "queue": selected_queues,
    }


def build_measured_pdca_generation_rows(
    *,
    account_id: str,
    measured_rows: list[dict[str, Any]],
    posted_results: list[dict[str, Any]],
    top_n: int,
    slot_id: str,
    theme: str,
    schedule_date_jst: str,
    history: list[str],
) -> dict[
    str,
    list[dict[str, Any]],
]:
    (
        posts,
        scores,
        source_meta,
    ) = build_measured_pdca_inputs(
        measured_rows=measured_rows,
        posted_results=posted_results,
        account_id=account_id,
    )

    if not posts or not scores:
        return {
            "drafts": [],
            "social_derivatives": [],
            "queue": [],
        }

    generated = build_generation_rows(
        account_id=account_id,
        posts=posts,
        scores=scores,
        top_n=len(scores),
        slot_id=slot_id,
        post_type="pdca_text",
        theme=theme,
        schedule_date_jst=(
            schedule_date_jst
        ),
        history=history,
    )

    return apply_measured_pdca_lineage(
        generated,
        account_id=account_id,
        source_meta=source_meta,
        top_n=top_n,
    )


def attach_pdca_activation_evidence(
    rows: dict[
        str,
        list[dict[str, Any]],
    ],
    *,
    account_id: str,
    measured_rows: list[dict[str, Any]],
    posted_results: list[dict[str, Any]],
    stamp: str,
) -> dict[str, list[dict[str, Any]]]:
    """Attach fresh canary identity and measured-result lineage."""

    copied = {
        key: [
            dict(row)
            for row in value
        ]
        for key, value in rows.items()
    }

    if not measured_rows:
        return copied

    latest = max(
        measured_rows,
        key=lambda row: (
            str(
                row.get(
                    "collected_at",
                    "",
                )
            ),
            str(
                row.get(
                    "snapshot_id",
                    "",
                )
            ),
        ),
    )

    source_result_id = str(
        latest.get(
            "result_id",
            "",
        )
    )

    posted_by_result = {
        str(
            row.get(
                "result_id",
                "",
            )
        ): dict(row)
        for row in posted_results
        if str(
            row.get(
                "result_id",
                "",
            )
        ).strip()
    }

    for index, row in enumerate(
        copied.get("queue", []),
        1,
    ):
        row["canary_id"] = (
            f"canary_fresh_{account_id}_"
            f"pdca_text_{stamp}_"
            f"{index:02d}"
        )

        row["content_type"] = (
            "pdca_text"
        )

        row["content_route"] = (
            "pdca_text"
        )

        row["generation_mode"] = (
            "metrics_driven_pdca_text"
        )

        row_source_result_id = str(
            row.get(
                "source_result_id",
                "",
            )
            or source_result_id
        )

        source_result = (
            posted_by_result.get(
                row_source_result_id,
                {},
            )
        )

        row["source_result_id"] = (
            row_source_result_id
        )

        row["source_content_route"] = (
            source_result.get(
                "content_route",
                "",
            )
            or source_result.get(
                "content_type",
                "",
            )
            or row.get(
                "source_content_route",
                "",
            )
        )

        row[
            "source_generation_mode"
        ] = (
            source_result.get(
                "generation_mode",
                "",
            )
            or row.get(
                "source_generation_mode",
                "",
            )
        )

    return copied


def run_reference_generation(
    account_id: str,
    top_n: int,
    *,
    apply: bool,
    slot_id: str = "",
    post_type: str = "reference_text",
    theme: str = "",
    schedule_date_jst: str = "",
    require_measured_pdca: bool = False,
    include_preview_rows: bool = False,
    video_only_reference: bool = False,
    client: Any | None = None,
) -> dict[str, Any]:
    from sheets_record_reader import read_records_safely

    if client is None:
        from config_loader import get_config
        from sheets_client import SheetsClient

        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)

    # Canonical source-of-truth handoff. Do not generate from the stale
    # source_account_posts/reference_post_scores mirror. Video transcript text
    # is joined at read time and never copied back into source_posts.
    canonical_source_posts = [
        dict(row) for row in read_records_safely(client, "source_posts")
    ]
    source_post_media = [
        dict(row) for row in read_records_safely(client, "source_post_media")
    ]
    video_parent_ids = {
        str(row.get("source_post_id", "")).strip()
        for row in source_post_media
        if str(row.get("media_type", "")).strip().lower() == "video"
        and str(row.get("source_post_id", "")).strip()
    }
    threads_video_parent_count = len({
        str(row.get("source_post_id", "")).strip()
        for row in canonical_source_posts
        if str(row.get("source_post_id", "")).strip() in video_parent_ids
        and str(row.get("platform", "")).strip().lower() == "threads"
    })
    if video_only_reference:
        canonical_source_posts = [
            row for row in canonical_source_posts
            if str(row.get("source_post_id", "")).strip() in video_parent_ids
            and str(row.get("platform", "")).strip().lower() == "threads"
        ]
    source_videos = [
        dict(row) for row in read_records_safely(client, "source_videos")
    ]
    video_transcripts = [
        dict(row) for row in read_records_safely(client, "video_transcripts")
    ]
    adapted_reference_inputs = build_current_reference_generation_inputs(
        account_id=account_id,
        source_posts=canonical_source_posts,
        source_videos=source_videos,
        transcripts=video_transcripts,
    )
    posts = list(adapted_reference_inputs["posts"])
    scores = list(adapted_reference_inputs["scores"])
    reference_input_diagnostics = dict(adapted_reference_inputs["diagnostics"])
    posted_results_all = read_records_safely(client, "posted_results")
    posted_results = [
        dict(row)
        for row in posted_results_all
        if str(row.get("account_id", "")) == account_id
    ]

    history = [
        str(
            row.get(
                "posted_text",
                "",
            )
        )
        for row in posted_results
    ]
    try:
        strategy_rows = read_records_safely(client, "strategy_state")
    except Exception:
        strategy_rows = []
    preferred_topics = preferred_primary_topics(strategy_rows, account_id)
    metric_snapshots = [
        dict(row)
        for row in read_records_safely(client, "metric_snapshots")
        if str(row.get("account_id", "")) == account_id
    ]

    media_metric_rows = [
        dict(row)
        for row in read_records_safely(client, "media_metrics")
        if str(row.get("account_id", "")) == account_id
    ]

    metric_rows = [
        *metric_snapshots,
        *media_metric_rows,
    ]
    from generation.context_selector import select_generation_context
    category_scores = [
        dict(row)
        for row in read_records_safely(client, "category_scores")
        if str(row.get("account_id", "")) == account_id
    ]
    learning_rules = [
        dict(row)
        for row in read_records_safely(client, "learning_rules")
        if str(row.get("account_id", "")) == account_id
    ]
    context = select_generation_context(
        account_id=account_id,
        posted_results=[dict(row) for row in posted_results_all],
        metric_rows=metric_rows,
        category_scores=category_scores,
        learning_rules=learning_rules,
        requested_theme=theme,
    )
    effective_theme = str(context["selected_theme"])
    measured = measured_pdca_snapshots(
        metric_snapshots,
        posted_results,
        account_id=account_id,
    )

    if (
        post_type == "pdca_text"
        and require_measured_pdca
        and not measured
    ):
        return {
            "status": "NO_DATA",
            "account_id": account_id,
            "post_type": post_type,
            "candidate_count": 0,
            "measured_metric_count": 0,
            "reason": (
                "measured_metrics_required_"
                "for_pdca_activation"
            ),
            "worker_selectable": False,
            "real_post_possible_now": False,
        }

    strict_measured_pdca = (
        post_type == "pdca_text"
        and require_measured_pdca
    )

    fallback_used = False

    if strict_measured_pdca:
        rows = (
            build_measured_pdca_generation_rows(
                account_id=account_id,
                measured_rows=measured,
                posted_results=(
                    posted_results
                ),
                top_n=top_n,
                slot_id=slot_id,
                theme=effective_theme,
                schedule_date_jst=(
                    schedule_date_jst
                ),
                history=history,
            )
        )

        if not rows["queue"]:
            return {
                "status": "NO_DATA",
                "account_id": account_id,
                "post_type": post_type,
                "candidate_count": 0,
                "measured_metric_count": (
                    len(measured)
                ),
                "reason": (
                    "measured_pdca_generation_"
                    "failed_quality_gate"
                ),
                "worker_selectable": False,
                "real_post_possible_now": (
                    False
                ),
            }

    elif post_type == "original_text":
        fallback_used = True

        rows = build_fallback_generation_rows(
            account_id=account_id,
            top_n=top_n,
            slot_id=slot_id,
            post_type="original_text",
            content_route=post_type,
            theme=effective_theme,
            schedule_date_jst=(
                schedule_date_jst
            ),
            history=history,
            fallback_reason=(
                "original_text_slot"
            ),
            preferred_topics=(
                preferred_topics
            ),
        )

    elif (
        post_type == "pdca_text"
        and not measured
    ):
        fallback_used = True

        rows = build_fallback_generation_rows(
            account_id=account_id,
            top_n=top_n,
            slot_id=slot_id,
            post_type="original_text",
            content_route=post_type,
            theme=theme,
            schedule_date_jst=(
                schedule_date_jst
            ),
            history=history,
            fallback_reason=(
                "pdca_metrics_unavailable"
            ),
            preferred_topics=(
                preferred_topics
            ),
        )

    else:
        rows = build_generation_rows(
            account_id=account_id,
            posts=posts,
            scores=scores,
            top_n=top_n,
            slot_id=slot_id,
            post_type=post_type,
            theme=effective_theme,
            schedule_date_jst=(
                schedule_date_jst
            ),
            history=history,
        )

        if (
            not rows["queue"]
            and post_type == "reference_text"
            and (
                video_only_reference
                or slot_id in {"ns_1400_reference", "lm_1300_reference"}
            )
        ):
            return {
                "status": "NO_DATA",
                "account_id": account_id,
                "post_type": post_type,
                "candidate_count": 0,
                "measured_metric_count": len(measured),
                "reason": (
                    "video_reference_source_required"
                    if video_only_reference
                    else "reference_source_required_for_reference_slot"
                ),
                "worker_selectable": False,
                "real_post_possible_now": False,
            }

        if not rows["queue"]:
            rows = (
                build_fallback_generation_rows(
                    account_id=account_id,
                    top_n=top_n,
                    slot_id=slot_id,
                    post_type=(
                        "original_text"
                    ),
                    content_route=post_type,
                    theme=theme,
                    schedule_date_jst=(
                        schedule_date_jst
                    ),
                    history=history,
                    fallback_reason=(
                        "scheduled_route_"
                        "generation_empty"
                    ),
                    preferred_topics=(
                        preferred_topics
                    ),
                )
            )

            fallback_used = True

    if (
        post_type == "pdca_text"
        and require_measured_pdca
    ):
        rows = (
            attach_pdca_activation_evidence(
                rows,
                account_id=account_id,
                measured_rows=measured,
                posted_results=(
                    posted_results
                ),
                stamp=datetime.now(
                    timezone.utc
                ).strftime(
                    "%Y%m%d%H%M%S"
                ),
            )
        )

    summary = {
        "status": "PLAN_ONLY",
        "account_id": account_id,
        "source_posts": len(posts),
        "source_scores": len(scores),
        "reference_input_source": "source_posts_current",
        "reference_media_filter": "video_only" if video_only_reference else "any",
        "video_reference_parent_count": threads_video_parent_count,
        "reference_input_diagnostics": reference_input_diagnostics,
        "candidate_count": len(rows["queue"]),
        "candidate_status": CANDIDATE_STATUS,
        "fallback_original_used": fallback_used,
        "pdca_generation_source": (
            "measured_owned_post"
            if strict_measured_pdca
            else ""
        ),
        "pdca_metric_input_applied": (
            strict_measured_pdca
            and bool(rows["queue"])
        ),
        "queue_ids": [r["queue_id"] for r in rows["queue"]],
        "candidate_content_routes": sorted({
            str(row.get("content_route", ""))
            for row in rows["queue"]
            if str(row.get("content_route", ""))
        }),
        "candidate_generation_modes": sorted({
            str(row.get("generation_mode", ""))
            for row in rows["queue"]
            if str(row.get("generation_mode", ""))
        }),
        "worker_selectable": False,
        "real_post_possible_now": False,
        "slot_id": slot_id,
        "post_type": post_type,
        "theme": theme,
        "effective_theme": effective_theme,
        "generation_context": {key: value for key, value in context.items() if key not in {"avoid_recent_texts"}},
        "measured_metric_count": len(measured),
        "require_measured_pdca": (
            require_measured_pdca
        ),
        "pdca_fallback_to_original": post_type == "pdca_text" and not measured,
        "preferred_primary_topics": preferred_topics,
        "strategy_policy_active": bool(preferred_topics),
    }
    if not apply:
        if include_preview_rows:
            preview_fields = (
                "queue_id", "account_id", "target_account_id", "platform",
                "generation_mode", "content_type", "content_route",
                "source_content_route", "source_generation_mode",
                "source_result_id", "transformation_type", "source_credit",
                "source_id", "source_url", "public_post_text", "slot_id",
                "theme", "schedule_date_jst", "rights_status",
                "permission_status", "rights_review_required",
                "media_reuse_risk", "validator_status",
                "internal_leak_status", "account_fit_status",
                "generation_policy_json", "claim_support_json",
                "key_claims_json", "internal_analysis",
            )
            summary["preview_queue"] = [
                {key: row.get(key, "") for key in preview_fields}
                for row in rows.get("queue", [])[:max(1, top_n)]
            ]
        return summary
    if not rows["queue"]:
        return {**summary, "status": "NO_DATA", "reason": "reference posts/scores and fallback candidates are missing"}
    ops = {
        "drafts": _append_missing(client, "drafts", "draft_id", rows["drafts"]),
        "social_derivatives": _append_missing(client, "social_derivatives", "derivative_id", rows["social_derivatives"]),
        "queue": _append_missing(client, "queue", "queue_id", rows["queue"]),
    }
    queue_writes = sum(int(ops["queue"].get(k, 0)) for k in ("added", "refreshed"))
    fallback_topup_used = False
    fallback_ops: dict[str, dict[str, int]] = {}
    if (
        queue_writes == 0
        and not strict_measured_pdca
    ):
        fallback_rows = build_fallback_generation_rows(
            account_id=account_id,
            top_n=top_n,
            slot_id=slot_id,
            post_type="original_text",
            content_route=post_type,
            theme=theme,
            schedule_date_jst=schedule_date_jst,
            history=history,
            fallback_reason="scheduled_route_topup",
            preferred_topics=preferred_topics,
        )
        fallback_topup_used = bool(fallback_rows["queue"])
        fallback_ops = {
            "drafts": _append_missing(client, "drafts", "draft_id", fallback_rows["drafts"]),
            "social_derivatives": _append_missing(client, "social_derivatives", "derivative_id", fallback_rows["social_derivatives"]),
            "queue": _append_missing(client, "queue", "queue_id", fallback_rows["queue"]),
        }
    return {
        **summary,
        "status": "GENERATED",
        "fallback_topup_used": fallback_topup_used,
        "applied_operations": ops,
        "fallback_topup_operations": fallback_ops,
    }


def build_plan(args: argparse.Namespace) -> dict[str, Any]:
    """委譲プランを純粋関数で組み立てる（Sheets/LLM 不要・テスト対象）。"""
    if args.account_id == "beauty_account":
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "beauty_account は対象外（draft_only）"}
    if args.platform not in ALLOWED_PLATFORMS:
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "platform は threads のみ（X は将来対応）"}
    if args.source not in DELEGATES:
        return {"status": "BLOCKED", "cli": CLI_NAME, "reason": "source は references / clips のみ"}

    apply = bool(args.apply)
    confirm = bool(args.confirm_generate)
    will_run = apply and confirm
    delegate = DELEGATES[args.source]

    if args.source == "references":
        argv = ["--account-id", args.account_id, "--platform", args.platform, "--top-n", str(args.top_n)]
        if not will_run:
            argv += ["--mock", "--dry-run"]
    else:  # clips
        argv = ["--account-id", args.account_id, "--limit", str(args.top_n)]
        if will_run:
            argv += ["--use-sheets"]
        else:
            argv += ["--mock-llm"]

    plan = {
        "status": "WILL_RUN" if will_run else "PLAN_ONLY",
        "cli": CLI_NAME,
        "account_id": args.account_id,
        "platform": args.platform,
        "source": args.source,
        "delegate_script": delegate,
        "delegate_argv": argv,
        "safety": {
            # 委譲先は WAITING_REVIEW で書く。worker は READY のみを拾う。
            "candidate_status": CANDIDATE_STATUS,
            "worker_selectable": CANDIDATE_STATUS in ELIGIBLE_STATUSES,
            # 本 CLI / 委譲先は生成専用で投稿経路を一切持たない（最重要不変条件）。
            "delegate_posts": False,
            # 実投稿は別 worker の三重ゲートが必要。現状すべて禁止 → 不可能。
            "real_post_requires": REAL_POST_GATES,
            "real_post_possible_now": False,
            "ready_gate": f"{READY_GATE} (WAITING_REVIEW → READY/REJECTED)",
            "platform": args.platform,
        },
        "notes": (
            "本 CLI は生成専用（投稿しない）。候補は WAITING_REVIEW で書かれ worker 非対象。"
            "READY化は approve_queue.py または validator/cap/cooldownを通す auto_approve_queue.py のみ。"
            "実投稿には別 worker の三重ゲートが必要。"
            "threads のみ。実行は --apply --confirm-generate。"
        ),
    }
    # 最重要不変条件: 本 CLI は投稿せず生成のみ（委譲先も投稿経路を持たない）。
    assert plan["safety"]["delegate_posts"] is False
    assert plan["safety"]["real_post_possible_now"] is False
    return plan


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="generate Threads ideas from references (thin wrapper, gated)")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager", "beauty_account"])
    parser.add_argument("--platform", default="threads")
    parser.add_argument("--source", default="references", choices=["references", "clips"])
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="explicit PLAN_ONLY mode (default unless --apply)")
    parser.add_argument("--apply", action="store_true", help="run delegate (needs --confirm-generate)")
    parser.add_argument("--confirm-generate", action="store_true")
    parser.add_argument("--slot-id", default="")
    parser.add_argument("--post-type", default="reference_text", choices=["original_text", "reference_text", "pdca_text"])
    parser.add_argument("--theme", default="")
    parser.add_argument("--schedule-date-jst", default="")
    parser.add_argument(
        "--include-preview-queue",
        action="store_true",
        help="Include sanitized in-memory queue candidates in PLAN_ONLY output.",
    )
    parser.add_argument(
        "--require-measured-pdca",
        action="store_true",
        help=(
            "Do not create pdca_text "
            "activation candidates until "
            "MEASURED evidence exists."
        ),
    )
    parser.add_argument(
        "--video-only-reference",
        action="store_true",
        help="Use only source_posts with an ordered video child; still creates text-only review candidates.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    plan = build_plan(args)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if plan["status"] == "BLOCKED":
        return 1
    if plan["status"] == "PLAN_ONLY" and args.dry_run and plan["source"] == "references":
        result = run_reference_generation(
            plan["account_id"],
            args.top_n,
            apply=False,
            slot_id=args.slot_id,
            post_type=args.post_type,
            theme=args.theme,
            schedule_date_jst=(
                args.schedule_date_jst
            ),
            require_measured_pdca=(
                args.require_measured_pdca
            ),
            include_preview_rows=(
                args.include_preview_queue
            ),
            video_only_reference=args.video_only_reference,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if plan["status"] != "WILL_RUN":
        return 0
    if plan["source"] == "references":
        result = run_reference_generation(
            plan["account_id"],
            args.top_n,
            apply=True,
            slot_id=args.slot_id,
            post_type=args.post_type,
            theme=args.theme,
            schedule_date_jst=(
                args.schedule_date_jst
            ),
            require_measured_pdca=(
                args.require_measured_pdca
            ),
            video_only_reference=args.video_only_reference,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] in {"GENERATED", "NO_DATA"} else 1
    # Clip generation remains delegated; it does not post.
    import subprocess
    cmd = [sys.executable, str(ROOT / plan["delegate_script"]), *plan["delegate_argv"]]
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
