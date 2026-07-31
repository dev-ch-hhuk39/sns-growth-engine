#!/usr/bin/env python3
"""Generate original owned media canaries; never publish Threads posts.

Images, carousel cards, a silent short video and a separate short clip are
rendered from public post text only. No third-party image, logo, source media,
download, transcription or reference-only video is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
from media.social_card import render_text_card
from public_post_quality import final_public_post_validator, generate_production_post
from production_novelty import evaluate_candidate_novelty
from generation_quality_gates import evaluate_generation_quality, persisted_quality_evidence

ACCOUNTS = ("night_scout", "liver_manager")
BRANDS = {
    "night_scout": {"bg": (24, 19, 31), "fg": (250, 245, 255), "accent": (239, 112, 154)},
    "liver_manager": {"bg": (16, 37, 42), "fg": (239, 255, 251), "accent": (69, 196, 173)},
}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _text(
    account_id: str,
    *,
    batch_id: str,
    kind: str,
    attempt: int = 0,
    recent_posts: list[str] | None = None,
    excluded_topics: list[str] | None = None,
) -> tuple[str, dict[str, Any]]:
    generated = generate_production_post(
        account_id,
        batch_id=batch_id,
        content_type=kind,
        recent_posts=recent_posts or [],
        attempt=attempt,
        excluded_topics=excluded_topics or [],
    )
    text = str(generated.get("public_post_text", ""))
    if "GENERATION_PROVIDER_UNAVAILABLE" in generated.get("blocked_reasons", []):
        raise ValueError("GENERATION_PROVIDER_UNAVAILABLE")
    return text, generated


def _hook(text: str) -> str:
    return text.split("\n", 1)[0].strip()[:48]


def _compact(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or "").lower(), flags=re.UNICODE)


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[。！？!?\n]+", str(text or "")) if item.strip()]


def _post_design(text: str, generated: dict[str, Any]) -> dict[str, Any]:
    raw = dict(generated.get("post_design") or {})
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    hook = str(raw.get("hook_text") or (paragraphs[0] if paragraphs else text)).strip()
    body = str(raw.get("body_text") or (paragraphs[1] if len(paragraphs) > 1 else "")).strip()
    closing = str(raw.get("closing_text") or (paragraphs[-1] if len(paragraphs) > 1 else "")).strip()
    claims = [str(value).strip() for value in raw.get("key_claims", []) if str(value).strip()]
    if not claims:
        claims = [value for value in (hook, body, closing) if value]
    return {
        "design_version": str(raw.get("design_version") or "post_design_v1"),
        "feature_schema_version": str(raw.get("feature_schema_version") or "post_features_v1"),
        "account_id": str(raw.get("account_id") or ""),
        "content_type": str(raw.get("content_type") or ""),
        "source_topic": str(raw.get("source_topic") or generated.get("grounding_summary", {}).get("topic", "")),
        "primary_topic": str(raw.get("primary_topic") or generated.get("grounding_summary", {}).get("quality_topic", "")),
        "supporting_concepts": list(raw.get("supporting_concepts") or generated.get("grounding_summary", {}).get("concepts", [])),
        "hook_text": hook,
        "body_text": body,
        "closing_text": closing,
        "key_claims": claims,
        "cta_intent": str(raw.get("cta_intent") or ""),
        "structure_variant": str(raw.get("structure_variant") or generated.get("grounding_summary", {}).get("structure_variant", "")),
    }


def _split_body(body: str) -> list[str]:
    parts = _sentences(body)
    return parts or ([body.strip()] if body.strip() else [])


def _build_visual_plan(kind: str, design: dict[str, Any], *, attempt: int = 0) -> dict[str, Any]:
    """Build media from the accepted post design, never from a separate topic choice."""
    hook = str(design.get("hook_text", "")).strip()
    body = str(design.get("body_text", "")).strip()
    closing = str(design.get("closing_text", "")).strip()
    body_parts = _split_body(body)
    primary_topic = str(design.get("primary_topic", "")).strip()
    cta_intent = str(design.get("cta_intent", "")).strip()

    if kind == "direct_carousel":
        explanation = body_parts[0] if body_parts else body
        example = "。".join(body_parts[1:]).strip()
        if not example:
            example = body
        cards = [
            {"hook": hook, "body": "今回のポイント"},
            {"hook": "見るポイント", "body": explanation},
            {"hook": "具体的には", "body": example},
            {"hook": "次にすること", "body": closing},
        ]
    elif kind == "direct_video":
        cards = [{"hook": hook, "body": "\n\n".join(value for value in (body, closing) if value)}]
    elif kind == "generated_clip":
        cards = [{"hook": hook, "body": "\n\n".join(value for value in (body, closing) if value)}]
    else:
        cards = [{"hook": hook, "body": "\n\n".join(value for value in (body, closing) if value)}]

    visual_text = "\n\n".join(
        value
        for card in cards
        for value in (str(card.get("hook", "")).strip(), str(card.get("body", "")).strip())
        if value and value not in {"今回のポイント", "見るポイント", "具体的には", "次にすること"}
    )
    visual_claims = [str(value).strip() for value in design.get("key_claims", []) if str(value).strip()]
    return {
        "visual_plan_version": "visual_plan_v1",
        "feature_schema_version": str(design.get("feature_schema_version") or "post_features_v1"),
        "kind": kind,
        "attempt": attempt + 1,
        "primary_topic": primary_topic,
        "cta_intent": cta_intent,
        "cards": cards,
        "visual_text": visual_text,
        "visual_claims": visual_claims,
    }


def _render_card(account_id: str, card: dict[str, str], path: Path) -> None:
    brand = BRANDS[account_id]
    render_text_card(
        hook=str(card.get("hook", ""))[:72],
        body=str(card.get("body", "")),
        out_path=str(path),
        fmt="portrait",
        bg_color=brand["bg"],
        fg_color=brand["fg"],
        accent_color=brand["accent"],
    )


def _render_visual_plan(account_id: str, kind: str, plan: dict[str, Any], base: Path) -> list[Path]:
    cards = list(plan.get("cards") or [])
    if not cards:
        raise ValueError(f"EMPTY_VISUAL_PLAN:{account_id}:{kind}")
    if kind == "direct_image":
        path = base / "direct.png"
        _render_card(account_id, cards[0], path)
        return [path]
    if kind == "direct_carousel":
        paths = []
        for index, card in enumerate(cards, 1):
            path = base / f"carousel_{index}.png"
            _render_card(account_id, card, path)
            paths.append(path)
        return paths
    image_path = base / ("video.png" if kind == "direct_video" else "clip.png")
    _render_card(account_id, cards[0], image_path)
    output_path = base / ("short.mp4" if kind == "direct_video" else "clip.mp4")
    _video(image_path, output_path, seconds=10 if kind == "direct_video" else 8, clip=kind == "generated_clip")
    return [output_path]


def _video(image_path: Path, output_path: Path, *, seconds: int, clip: bool = False) -> None:
    filters = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,zoompan=z='min(zoom+0.0007,1.06)':d=1:s=1080x1920,fade=t=in:st=0:d=0.5,fade=t=out:st=%s:d=0.5" % max(1, seconds - 1)
    command = ["ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-t", str(seconds), "-vf", filters, "-r", "30", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output_path)]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _claim_match(claim: str, candidates: list[str]) -> tuple[bool, float, str]:
    from generation.semantic_alignment import lexical_similarity
    compact_claim = _compact(claim)
    best_score = 0.0
    best_candidate = ""
    for candidate in candidates:
        compact_candidate = _compact(candidate)
        exact = bool(compact_claim) and (
            compact_claim in compact_candidate or compact_candidate in compact_claim
        )
        score = 1.0 if exact else lexical_similarity(claim, candidate)
        if score > best_score:
            best_score = score
            best_candidate = candidate
    return best_score >= 0.72, round(best_score, 4), best_candidate


def _alignment(
    account_id: str,
    text: str,
    design: dict[str, Any],
    visual_plan: dict[str, Any],
    recent_posts: list[str],
) -> dict[str, Any]:
    """Verify caption/media agreement from explicit claim-level evidence."""
    from generation.semantic_alignment import lexical_similarity

    visual_text = str(visual_plan.get("visual_text", ""))
    visual_units = _sentences(visual_text)
    caption_units = _sentences(text)
    claims = [str(value).strip() for value in design.get("key_claims", []) if str(value).strip()]
    support = []
    for claim in claims:
        matched, score, evidence = _claim_match(claim, visual_units)
        support.append({
            "caption_claim": claim,
            "visual_evidence": evidence,
            "claim_visual_similarity": score,
            "verified": matched,
        })
    covered = sum(1 for item in support if item["verified"])
    coverage = covered / max(1, len(claims)) if claims else 0.0

    unsupported_visual = []
    for visual_claim in [str(value).strip() for value in visual_plan.get("visual_claims", []) if str(value).strip()]:
        matched, score, evidence = _claim_match(visual_claim, caption_units)
        if not matched:
            unsupported_visual.append({
                "visual_claim": visual_claim,
                "caption_evidence": evidence,
                "claim_caption_similarity": score,
            })

    recent = max((lexical_similarity(text, item) for item in recent_posts if item), default=0.0)
    declared_primary_topic = str(design.get("primary_topic", ""))
    visual_quality = evaluate_generation_quality(
        account_id,
        visual_text,
        [],
        primary_topic=declared_primary_topic,
        structure_variant=str(design.get("structure_variant", "")),
    )
    visual_hook_topic = str(visual_quality.get("hook_topic", "general"))
    visual_closing_topic = str(visual_quality.get("closing_topic", "general"))
    visual_topic_match = (
        str(visual_plan.get("primary_topic", "")) == declared_primary_topic
        and visual_hook_topic == declared_primary_topic
        and visual_closing_topic == declared_primary_topic
    )
    cta_match, cta_score, cta_evidence = _claim_match(
        str(design.get("closing_text", "")),
        visual_units,
    )
    score = round(
        0.62 * coverage
        + 0.18 * (1.0 if visual_topic_match else 0.0)
        + 0.10 * (1.0 if cta_match else 0.0)
        + 0.10 * (1.0 - recent),
        4,
    )
    reasons = []
    if coverage < 1.0:
        reasons.append("visual_claim_coverage_incomplete")
    if unsupported_visual:
        reasons.append("unsupported_visual_claims_present")
    if not visual_topic_match:
        reasons.append("visual_topic_mismatch")
    if not cta_match:
        reasons.append("visual_cta_mismatch")
    if recent > 0.75:
        reasons.append("recent_post_similarity_above_threshold")
    if score < 0.72:
        reasons.append("final_alignment_score_below_threshold")
    return {
        "alignment_status": "PASS" if not reasons else "BLOCKED",
        "final_alignment_score": score,
        "main_claim_coverage": round(coverage, 4),
        "unsupported_claim_count": len(unsupported_visual),
        "source_copy_similarity": 0.0,
        "recent_post_similarity": round(recent, 4),
        "media_primary_topic": str(design.get("primary_topic", "")),
        "visual_topic": visual_hook_topic if visual_hook_topic == visual_closing_topic else "mixed",
        "visual_topic_match": visual_topic_match,
        "visual_cta_match": cta_match,
        "visual_cta_similarity": cta_score,
        "visual_cta_evidence": cta_evidence,
        "claim_support": support,
        "unsupported_visual_claims": unsupported_visual,
        "alignment_blocked_reasons": reasons,
        "storyboard": visual_text,
        "visual_plan_version": str(visual_plan.get("visual_plan_version", "")),
        "visual_plan_attempt": int(visual_plan.get("attempt") or 0),
        "feature_schema_version": str(visual_plan.get("feature_schema_version", "")),
        "visual_text_hash": hashlib.sha256(visual_text.encode("utf-8")).hexdigest(),
    }


MEDIA_CONTENT_TYPES = ("direct_image", "direct_carousel", "direct_video", "generated_clip")


def build_specs(
    account_id: str,
    output_dir: Path,
    *,
    batch_id: str = "",
    recent_posts: list[str] | None = None,
    kinds: tuple[str, ...] = MEDIA_CONTENT_TYPES,
    seed_batch_candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    shared_batch_id = batch_id or f"fresh_{os.environ.get('GITHUB_RUN_ID') or datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    run_id = f"{shared_batch_id}_{account_id}"
    base = output_dir / account_id / run_id; base.mkdir(parents=True, exist_ok=True)
    seed_candidates = [dict(item) for item in (seed_batch_candidates or []) if str(item.get("account_id", account_id)) == account_id]
    history = list(recent_posts or []) + [str(item.get("public_post_text", "")) for item in seed_candidates if str(item.get("public_post_text", ""))]
    texts: dict[str, str] = {}
    generated: dict[str, dict[str, Any]] = {}
    qualities: dict[str, dict[str, Any]] = {}
    batch_candidates: list[dict[str, Any]] = list(seed_candidates)
    history_before_kind: dict[str, list[str]] = {}
    for kind in kinds:
        history_before_kind[kind] = list(history)
        selected = None
        # 5主題 × 6構造の決定論的な候補空間を探索する。
        # 5回だけではbatch hash次第で有効候補を発見できない。
        for attempt in range(30):
            text, output = _text(
                account_id,
                batch_id=shared_batch_id,
                kind=kind,
                attempt=attempt,
                recent_posts=history,
                excluded_topics=[str(item.get("primary_topic", "")) for item in batch_candidates],
            )
            novelty = evaluate_candidate_novelty(
                account_id=account_id,
                public_post_text=text,
                recent_posts=history,
                pending_queue=[],
            )
            primary_topic = str(output.get("grounding_summary", {}).get("quality_topic", ""))
            structure_variant = output.get("grounding_summary", {}).get("structure_variant", "")
            quality = evaluate_generation_quality(
                account_id,
                text,
                history,
                batch_compared=batch_candidates,
                structure_variant=structure_variant,
                primary_topic=primary_topic,
            )
            validation = final_public_post_validator(text, account_id=account_id)
            if novelty["status"] == "PASS" and quality["status"] == "PASS" and validation["status"] == "PASS":
                selected = (text, output, quality, validation)
                break
        if selected is None:
            raise ValueError(f"QUALITY_EXHAUSTED:{account_id}:{kind}")
        text, output, quality, validation = selected
        texts[kind] = text; generated[kind] = output; qualities[kind] = quality
        batch_candidates.append({
            "account_id": account_id,
            "candidate_id": f"canary_{shared_batch_id}_{account_id}_{kind}",
            "batch_id": shared_batch_id,
            "structure_variant": quality.get("structure_variant", ""),
            "primary_topic": quality.get("primary_topic", ""),
            "public_post_text": text,
        })
        history.append(text)
    files_by_kind: dict[str, list[Path]] = {}
    visual_plans: dict[str, dict[str, Any]] = {}
    alignments: dict[str, dict[str, Any]] = {}
    designs: dict[str, dict[str, Any]] = {}
    for kind in kinds:
        design = _post_design(texts[kind], generated[kind])
        designs[kind] = design
        selected_plan = None
        selected_alignment = None
        for visual_attempt in range(5):
            plan = _build_visual_plan(kind, design, attempt=visual_attempt)
            alignment = _alignment(
                account_id,
                texts[kind],
                design,
                plan,
                history_before_kind[kind],
            )
            if alignment["alignment_status"] == "PASS":
                selected_plan = plan
                selected_alignment = alignment
                break
        if selected_plan is None or selected_alignment is None:
            raise ValueError(f"MEDIA_PLAN_EXHAUSTED:{account_id}:{kind}")
        visual_plans[kind] = selected_plan
        alignments[kind] = selected_alignment
        files_by_kind[kind] = _render_visual_plan(account_id, kind, selected_plan, base)
    return [
        {
            "kind": kind,
            "canary_id": f"canary_{shared_batch_id}_{account_id}_{kind}",
            "files": files_by_kind[kind],
            "text": texts[kind],
            "run_id": run_id,
            "batch_id": shared_batch_id,
            "generation": generated[kind],
            "post_design": designs[kind],
            "visual_plan": visual_plans[kind],
            "alignment": alignments[kind],
            "quality": qualities[kind],
        }
        for kind in kinds
    ]


def _upload(path: Path, account_id: str, public_id: str, allow_upload: bool) -> str:
    if not allow_upload:
        return ""
    from config_loader import get_cloudinary_config
    from media.cloudinary_client import upload_to_cloudinary

    config = get_cloudinary_config()
    mime = "video/mp4" if path.suffix.lower() == ".mp4" else "image/png"
    return upload_to_cloudinary(path.read_bytes(), mime, public_id, config)


def _append(ws: Any, headers: list[str], rows: list[dict[str, Any]]) -> None:
    if rows: ws.append_rows([[str(row.get(header, "")) for header in headers] for row in rows], value_input_option="USER_ENTERED")


def _repair_legacy_all_scope(tabs: dict[str, tuple[Any, list[str], list[dict[str, Any]]]], account_id: str) -> int:
    """Repair only unposted generated rows from the initial all-account apply."""
    repairs = 0
    targets = {
        "source_posts": ("target_account_id", "source_id"),
        "media_permissions": ("account_id", "source_id"),
        "media_assets": ("account_id", "reference_post_id"),
        "source_videos": ("account_id", "source_id"),
        "video_clip_candidates": ("account_id", "clip_id"),
        "queue": ("account_id", "source_id"),
    }
    marker = f"system_owned_{account_id}_"
    for logical, (account_field, marker_field) in targets.items():
        ws, headers, rows = tabs[logical]
        if account_field not in headers:
            continue
        column = headers.index(account_field) + 1
        for row_index, row in enumerate(rows, start=2):
            if str(row.get(account_field, "")) != "all" or marker not in str(row.get(marker_field, "")):
                continue
            if logical == "queue" and str(row.get("status", "")).upper() not in {"WAITING_REVIEW", "DRAFT", "PLANNED"}:
                raise RuntimeError(f"legacy_generated_queue_not_safe_to_repair:{row.get('queue_id', '')}")
            ws.update_cell(row_index, column, account_id)
            if logical == "queue" and "target_account_id" in headers:
                target_column = headers.index("target_account_id") + 1
                ws.update_cell(row_index, target_column, account_id)
            repairs += 1
    return repairs


def _legacy_scope_remaining(tabs: dict[str, tuple[Any, list[str], list[dict[str, Any]]]], account_id: str) -> int:
    targets = {
        "source_posts": ("target_account_id", "source_id"),
        "media_permissions": ("account_id", "source_id"),
        "media_assets": ("account_id", "reference_post_id"),
        "source_videos": ("account_id", "source_id"),
        "video_clip_candidates": ("account_id", "clip_id"),
        "queue": ("account_id", "source_id"),
    }
    marker = f"system_owned_{account_id}_"
    return sum(
        1
        for logical, (account_field, marker_field) in targets.items()
        for row in tabs[logical][2]
        if str(row.get(account_field, "")) == "all" and marker in str(row.get(marker_field, ""))
    )


def apply_specs(specs: list[dict[str, Any]], account_id: str, *, upload: bool) -> dict[str, Any]:
    from config_loader import get_config
    from sheets_client import SheetsClient, TAB_DEFINITIONS
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    logicals = ("source_posts", "source_post_media", "media_permissions", "media_assets", "source_videos", "video_clip_candidates", "queue")
    tabs = {}
    for logical in logicals:
        client._ensure_tab(logical, TAB_DEFINITIONS[logical]); ws = client._ws(logical); tabs[logical] = (ws, ws.row_values(1), ws.get_all_records())
    existing_canaries = {str(row.get("canary_id", "")) for row in tabs["queue"][2]}
    posted_rows = [row for row in client._ws("posted_results").get_all_records() if str(row.get("account_id", "")) == account_id]
    pending_rows = [row for row in tabs["queue"][2] if str(row.get("account_id", "")) == account_id and str(row.get("status", "")).upper() in {"READY", "WAITING_REVIEW", "PROCESSING"}]
    used_hashes = {str(row.get("content_hash", "")) for row in tabs["media_assets"][2] if str(row.get("account_id", "")) == account_id}
    used_public_ids = {str(row.get("cloudinary_public_id", "")) for row in tabs["media_assets"][2] if str(row.get("account_id", "")) == account_id}
    now = _now(); created: dict[str, list[dict[str, Any]]] = {logical: [] for logical in logicals}; skipped = []
    for spec in specs:
        if spec["canary_id"] in existing_canaries:
            skipped.append(spec["canary_id"]); continue
        source_id = f"{spec['run_id']}_{spec['kind']}"; parent_id = f"sp_{source_id}"; permission_id = f"perm_{source_id}"
        files = [Path(value) for value in spec["files"]]; media_ids = [f"ma_{source_id}_{index}" for index in range(len(files))]
        hashes = [_sha(path) for path in files]
        planned_public_ids = {f"sns-growth/{account_id}/{media_id}" for media_id in media_ids}
        novelty = evaluate_candidate_novelty(account_id=account_id, public_post_text=spec["text"], recent_posts=posted_rows, pending_queue=pending_rows, media_hashes=hashes, used_media_hashes=used_hashes, used_public_ids=planned_public_ids & used_public_ids)
        if novelty["status"] != "PASS":
            return {"status": "NOVELTY_EXHAUSTED", "canary_id": spec["canary_id"], "novelty": novelty, "would_post": False}
        if spec.get("alignment", {}).get("alignment_status") != "PASS":
            return {"status": "BLOCKED", "canary_id": spec["canary_id"], "reason": "MEDIA_TEXT_ALIGNMENT_BLOCKED", "alignment": spec.get("alignment", {}), "would_post": False}
        if spec.get("quality", {}).get("status") != "PASS":
            return {"status": "QUALITY_EXHAUSTED", "canary_id": spec["canary_id"], "quality": spec.get("quality", {}), "would_post": False}
        urls = [_upload(path, account_id, f"sns-growth/{account_id}/{media_id}", upload) for path, media_id in zip(files, media_ids)]
        created["source_posts"].append({"source_post_id": parent_id, "source_id": source_id, "source_account_id": "system_generated", "target_account_id": account_id, "platform": "system_generated_owned", "original_post_text": spec["text"], "media_count": len(files), "media_type": "carousel" if len(files) > 1 else ("video" if files[0].suffix == ".mp4" else "image"), "discovered_at": now, "collection_backend": "system_owned_media", "rights_status": "owned", "permission_status": "approved", "permission_scope": "system_generated", "direct_media_reuse_allowed": True, "collection_status": "SYSTEM_GENERATED", "processing_status": "READY", "content_hash": hashlib.sha256(spec["text"].encode()).hexdigest(), "created_at": now, "updated_at": now})
        created["media_permissions"].append({"permission_id": permission_id, "source_id": source_id, "account_id": account_id, "usage_mode": "system_owned_media", "rights_status": "owned", "permission_status": "approved", "allow_download": False, "allow_cloudinary_storage": True, "allow_original_repost": True, "allow_transcription": False, "allow_analysis": True, "allow_cut": spec["kind"] in {"direct_video", "generated_clip"}, "allow_clip_repost": spec["kind"] in {"direct_video", "generated_clip"}, "allow_new_caption": True, "allow_edit": True, "evidence_type": "system_generated", "evidence_reference": spec["run_id"], "approved_by": "system", "approved_at": now, "revoked": False, "notes": "provider=pillow+ffmpeg; input_hash=" + hashlib.sha256(spec["text"].encode()).hexdigest(), "updated_at": now})
        clip_id = f"clip_{source_id}" if spec["kind"] == "generated_clip" else ""
        for index, (path, media_id, url) in enumerate(zip(files, media_ids, urls)):
            media_type = "video" if path.suffix == ".mp4" else "image"; hash_value = hashes[index]
            created["source_post_media"].append({"source_post_media_id": f"spm_{source_id}_{index}", "source_post_id": parent_id, "media_index": index, "original_media_url": "", "canonical_post_url": "", "acquisition_method": "system_generated", "resolver_backend": "pillow_ffmpeg", "media_type": media_type, "mime_type": "video/mp4" if media_type == "video" else "image/png", "width": "1080", "height": "1920" if media_type == "video" else "1350", "aspect_ratio": "9:16" if media_type == "video" else "4:5", "duration_seconds": "8" if spec["kind"] == "generated_clip" else ("10" if media_type == "video" else ""), "content_hash": hash_value, "cloudinary_status": "UPLOADED" if url else "PENDING", "storage_url": url, "rights_status": "owned", "permission_status": "approved", "reuse_status": "APPROVED", "media_asset_id": media_id, "created_at": now, "updated_at": now})
            created["media_assets"].append({"media_id": media_id, "account_id": account_id, "reference_post_id": parent_id, "source_platform": "system_generated_owned", "source_post_url": "", "original_media_url": "", "storage_provider": "cloudinary" if url else "", "storage_url": url, "cloudinary_public_id": f"sns-growth/{account_id}/{media_id}" if url else "", "media_type": media_type, "mime_type": "video/mp4" if media_type == "video" else "image/png", "width": "1080", "height": "1920" if media_type == "video" else "1350", "duration": "8" if spec["kind"] == "generated_clip" else ("10" if media_type == "video" else ""), "reuse_status": "owned", "media_reuse_risk": "low", "imitation_risk": "low", "local_path": str(path), "rights_status": "owned", "permission_status": "approved", "aspect_ratio": "9:16" if media_type == "video" else "4:5", "duration_seconds": "8" if spec["kind"] == "generated_clip" else ("10" if media_type == "video" else ""), "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned", "allow_upload": True, "upload_status": "UPLOADED" if url else "PENDING", "media_origin": "system_generated_owned", "provider_name": "pillow+ffmpeg", "provider_version": "v2", "input_hash": hashlib.sha256(spec["text"].encode()).hexdigest(), "content_hash": hash_value, "generated_at": now, "alignment_status": spec["alignment"]["alignment_status"], "final_alignment_score": spec["alignment"]["final_alignment_score"], "main_claim_coverage": spec["alignment"]["main_claim_coverage"], "unsupported_claim_count": spec["alignment"]["unsupported_claim_count"], "source_copy_similarity": spec["alignment"]["source_copy_similarity"], "recent_post_similarity": spec["alignment"]["recent_post_similarity"], "notes": f"content_hash={hash_value}; storyboard={spec['alignment']['storyboard']}"})
            created["media_assets"][-1].update({
                "feature_schema_version": spec["alignment"].get("feature_schema_version", ""),
                "media_primary_topic": spec["alignment"].get("media_primary_topic", ""),
                "visual_topic": spec["alignment"].get("visual_topic", ""),
                "visual_topic_match": spec["alignment"].get("visual_topic_match", False),
                "visual_cta_match": spec["alignment"].get("visual_cta_match", False),
                "visual_plan_version": spec["alignment"].get("visual_plan_version", ""),
                "visual_plan_attempt": spec["alignment"].get("visual_plan_attempt", ""),
                "visual_text_hash": spec["alignment"].get("visual_text_hash", ""),
                "claim_support_json": json.dumps(spec["alignment"].get("claim_support", []), ensure_ascii=False),
                "post_design_json": json.dumps(spec.get("post_design", {}), ensure_ascii=False),
                "visual_plan_json": json.dumps(spec.get("visual_plan", {}), ensure_ascii=False),
            })
            if clip_id:
                created["media_assets"][-1]["video_clip_id"] = clip_id
        if spec["kind"] == "generated_clip":
            clip_id = f"clip_{source_id}"; video_id = f"video_{source_id}"; created["source_videos"].append({"source_video_id": video_id, "source_id": source_id, "account_id": account_id, "platform": "system_generated_owned", "source_type": "generated", "video_id": video_id, "title": "System generated short video", "duration_seconds": "8", "rights_status": "owned", "permission_status": "approved", "discovery_status": "SYSTEM_GENERATED", "content_hash": _sha(files[0]), "local_path": str(files[0]), "discovered_at": now}); created["video_clip_candidates"].append({"clip_candidate_id": clip_id, "clip_id": clip_id, "source_video_id": video_id, "source_id": source_id, "account_id": account_id, "source_platform": "system_generated_owned", "start_seconds": "0", "end_seconds": "8", "duration_seconds": "8", "clip_status": "READY", "cut_status": "done", "local_clip_path": str(files[0]), "clip_media_asset_id": media_ids[0], "media_asset_id": media_ids[0], "storage_url": urls[0], "rights_status": "owned", "permission_status": "approved", "public_post_text": spec["text"], "public_post_validator_status": "PASS", "aspect_ratio": "9:16", "upload_status": "UPLOADED" if urls[0] else "PENDING", "post_status": "NOT_POSTED", "created_at": now})
        publisher_media_type = "CAROUSEL" if spec["kind"] == "direct_carousel" else ("VIDEO" if spec["kind"] in {"direct_video", "generated_clip"} else "IMAGE")
        quality_evidence = persisted_quality_evidence(spec["quality"])
        queue = {"queue_id": f"q_{source_id}", "batch_id": spec.get("batch_id", spec["run_id"]), "account_id": account_id, "target_account_id": account_id, "platform": "threads", "status": "WAITING_REVIEW", "generation_mode": "system_owned_media", "public_post_text": spec["text"], "validator_status": "PASS", "internal_leak_status": "PASS", "account_fit_status": "PASS", "source_id": source_id, "source_post_id": parent_id, "clip_candidate_id": clip_id, "media_asset_id": media_ids[0], "media_url": urls[0], "media_status": "ATTACHED" if urls[0] else "PENDING_UPLOAD", "media_required": True, "media_type": "video" if publisher_media_type == "VIDEO" else "image", "content_type": spec["kind"], "publisher_media_type": publisher_media_type, "media_origin": "system_generated_owned", "canary_id": spec["canary_id"], "content_hash": novelty["text_hash"], "alignment_status": spec["alignment"]["alignment_status"], "final_alignment_score": spec["alignment"]["final_alignment_score"], "main_claim_coverage": spec["alignment"]["main_claim_coverage"], "unsupported_claim_count": spec["alignment"]["unsupported_claim_count"], "source_copy_similarity": spec["alignment"]["source_copy_similarity"], "recent_post_similarity": spec["alignment"]["recent_post_similarity"], "caption_provider": spec["generation"]["generation_provider"], "caption_provider_version": spec["generation"]["generation_provider_version"], "generation_attempt": spec["generation"].get("generation_attempt", ""), "generation_rule_version": spec["generation"].get("generation_rule_version", ""), "generation_policy_json": json.dumps(spec["generation"].get("generation_policy", {}), ensure_ascii=False), "created_at": now, "updated_at": now, **quality_evidence}
        if publisher_media_type == "VIDEO":
            queue.update({
                "aspect_ratio": "9:16",
                "duration_seconds": (
                    "8"
                    if spec["kind"] == "generated_clip"
                    else "10"
                ),
            })
        queue.update({
            "feature_schema_version": spec["alignment"].get("feature_schema_version", ""),
            "hook_text": spec.get("post_design", {}).get("hook_text", ""),
            "body_text": spec.get("post_design", {}).get("body_text", ""),
            "closing_text": spec.get("post_design", {}).get("closing_text", ""),
            "cta_intent": spec.get("post_design", {}).get("cta_intent", ""),
            "key_claims_json": json.dumps(spec.get("post_design", {}).get("key_claims", []), ensure_ascii=False),
            "post_design_json": json.dumps(spec.get("post_design", {}), ensure_ascii=False),
            "visual_plan_json": json.dumps(spec.get("visual_plan", {}), ensure_ascii=False),
            "media_primary_topic": spec["alignment"].get("media_primary_topic", ""),
            "visual_topic": spec["alignment"].get("visual_topic", ""),
            "visual_topic_match": spec["alignment"].get("visual_topic_match", False),
            "visual_cta_match": spec["alignment"].get("visual_cta_match", False),
            "visual_plan_version": spec["alignment"].get("visual_plan_version", ""),
            "visual_plan_attempt": spec["alignment"].get("visual_plan_attempt", ""),
            "visual_text_hash": spec["alignment"].get("visual_text_hash", ""),
            "claim_support_json": json.dumps(spec["alignment"].get("claim_support", []), ensure_ascii=False),
            "alignment_blocked_reasons": json.dumps(spec["alignment"].get("alignment_blocked_reasons", []), ensure_ascii=False),
        })
        if len(media_ids) > 1: queue.update({"media_asset_ids_json": json.dumps(media_ids), "media_urls_json": json.dumps(urls), "media_types_json": json.dumps(["image"] * len(media_ids))})
        created["queue"].append(queue)
    for logical, rows in created.items(): _append(tabs[logical][0], tabs[logical][1], rows)
    verify = {logical: len(rows) for logical, rows in created.items()}
    queue_ids = {str(row["queue_id"]) for row in created["queue"]}
    media_ids = {str(row["media_id"]) for row in created["media_assets"]}
    stored_queue_ids = {str(row.get("queue_id", "")) for row in client._ws("queue").get_all_records()}
    stored_media_ids = {str(row.get("media_id", "")) for row in client._ws("media_assets").get_all_records()}
    missing_queue_ids = sorted(queue_ids - stored_queue_ids)
    missing_media_ids = sorted(media_ids - stored_media_ids)
    read_after_write = {
        "status": "PASS" if not missing_queue_ids and not missing_media_ids else "PARTIAL_FAILURE",
        "missing_queue_ids": missing_queue_ids,
        "missing_media_ids": missing_media_ids,
    }
    return {
        "status": "APPLIED" if read_after_write["status"] == "PASS" else "PARTIAL_FAILURE",
        "created": verify,
        "repaired_legacy_rows": 0,
        "skipped_canaries": skipped,
        "cloudinary_uploaded": sum(1 for row in created["media_assets"] if row.get("storage_url")),
        "would_post": False,
        "read_after_write": read_after_write,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", choices=["all", *ACCOUNTS], default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-system-owned-media", action="store_true")
    parser.add_argument("--content-types", default=",".join(MEDIA_CONTENT_TYPES), help="comma-separated media content types")
    parser.add_argument("--batch-id", default="", help="shared batch id; use the same value to reproduce an approved design manifest")
    args = parser.parse_args()
    if args.apply and not args.confirm_system_owned_media:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-system-owned-media", "would_post": False})); return 1
    upload = args.apply and os.environ.get("ALLOW_CLOUDINARY_UPLOAD", "").lower() == "true"
    if args.apply and not upload:
        print(json.dumps({"status": "BLOCKED", "reason": "ALLOW_CLOUDINARY_UPLOAD=true required for apply", "would_post": False})); return 1
    accounts = ACCOUNTS if args.account_id == "all" else (args.account_id,)
    content_types = tuple(value.strip() for value in args.content_types.split(",") if value.strip())
    if not content_types or any(value not in MEDIA_CONTENT_TYPES for value in content_types):
        print(json.dumps({"status": "BLOCKED", "reason": "invalid_content_type", "would_post": False})); return 1
    shared_batch_id = args.batch_id or f"fresh_{os.environ.get('GITHUB_RUN_ID') or datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    specs_by_account = {account: build_specs(account, ROOT / "output/system_owned_media", batch_id=shared_batch_id, kinds=content_types) for account in accounts}
    all_specs = [spec for specs in specs_by_account.values() for spec in specs]
    if args.apply:
        account_results = {}
        for account in accounts:
            result = None
            # A collision with live Sheets state must be resolved before a
            # queue row exists. Re-render with a new batch; never weaken the
            # final publisher idempotency guard or reuse an existing asset.
            for attempt in range(5):
                specs = specs_by_account[account] if attempt == 0 else build_specs(
                    account,
                    ROOT / "output/system_owned_media",
                    batch_id=f"{shared_batch_id}_retry{attempt}",
                    kinds=content_types,
                )
                result = apply_specs(specs, account, upload=True)
                if result.get("status") != "NOVELTY_EXHAUSTED":
                    break
            account_results[account] = result or {"status": "NOVELTY_EXHAUSTED", "would_post": False}
        result = {
            "status": "APPLIED" if all(item["status"] == "APPLIED" for item in account_results.values()) else "PARTIAL_FAILURE",
            "accounts": account_results,
            "cloudinary_uploaded": sum(int(item["cloudinary_uploaded"]) for item in account_results.values()),
            "would_post": False,
        }
    else:
        result = {
            "status": "PLAN_ONLY",
            "account_id": args.account_id,
            "generated_specs": [
                {
                    "canary_id": spec["canary_id"],
                    "kind": spec["kind"],
                    "files": [str(path) for path in spec["files"]],
                    "content_hashes": [_sha(Path(path)) for path in spec["files"]],
                    "post_design": spec.get("post_design", {}),
                    "visual_plan": spec.get("visual_plan", {}),
                    "quality": spec.get("quality", {}),
                    "alignment": spec["alignment"],
                    "generation_provider": spec["generation"]["generation_provider"],
                }
                for spec in all_specs
            ],
            "would_upload": False,
            "would_post": False,
        }
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result["status"] in {"PLAN_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
