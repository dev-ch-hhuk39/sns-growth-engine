#!/usr/bin/env python3
"""Build a local, read-only Content Quality V2 owner review pack."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from generation.content_quality_v2 import (  # noqa: E402
    build_post_package,
    hard_gate,
    load_policy,
    rank_candidate,
    repair_style_only,
)
from generation_quality_gates import evaluate_generation_quality  # noqa: E402
from public_post_quality import final_public_post_validator  # noqa: E402

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")


def _norm(text: str) -> str:
    return re.sub(r"[\s、。，．！？!?・:：;；()（）「」『』【】]", "", text).lower()


def _liver_draft_style_variant(text: str, index: int) -> tuple[str, str]:
    """Add sparse, meaning-preserving punctuation/style variety to review drafts only."""
    if index == 1 and "かも。" in text:
        return text.replace("かも。", "かも？", 1), "rhetorical_question"
    if index == 2:
        varied, count = re.subn(r"(次の配信[^。\n]*。)", r"\1💡", text, count=1)
        if count:
            return varied, "contextual_emoji"
    if index == 3 and "よね。" in text:
        return text.replace("よね。", "よね！", 1), "warm_emphasis"
    return text, "neutral"


def _liver_style_signature(text: str) -> tuple[int, int, int, int]:
    emojis = ("☺️", "💡", "✨", "🌱", "🫶")
    return (
        int("！" in text or "!" in text),
        int("？" in text or "?" in text),
        sum(text.count(emoji) for emoji in emojis),
        len([line for line in text.splitlines() if line.strip()]),
    )


def _media_selection_rank(row: dict[str, Any], account: str) -> float:
    understanding = row.get("media_understanding")
    if not isinstance(understanding, dict):
        understanding = {"visual_status": "VISUAL_UNVERIFIED"}
    rank = rank_candidate({
        "quality_components": row.get("quality_components", {}),
        "media_understanding": understanding,
        "generic_caption_risk": row.get("generic_caption_risk", "UNKNOWN"),
    }, account_id=account)
    return float(rank["quality_rank"])


def text_candidates() -> dict[str, list[dict[str, Any]]]:
    policy = load_policy()
    limit = max(1, int(policy["draft_pack"]["text_per_account"]))
    source = json.loads((ROOT / "config/offline_original_posts.json").read_text(encoding="utf-8"))
    output: dict[str, list[dict[str, Any]]] = {}
    for account in ACCOUNTS:
        ranked: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, original in enumerate(source.get(account, []), start=1):
            repair = repair_style_only(str(original), account)
            text = repair["public_post_text"]
            key = _norm(text)
            if not text or not key or key in seen:
                continue
            validation = final_public_post_validator(text, account)
            gate = hard_gate({"account_id": account, "target_account_id": account,
                              "platform": "threads", "public_post_text": text},
                             account_id=account, public_validation=validation)
            if gate["status"] != "PASS":
                continue
            diversity = evaluate_generation_quality(
                account, text, [], batch_compared=[row["text"] for row in ranked],
            )
            voice = validation.get("voice_persona_check", {})
            rank = rank_candidate({
                "candidate_id": f"{account}-{index}",
                "quality_components": {
                    "reader_value": validation.get("reader_value_score", 45),
                    "account_relevance": validation.get("account_fit_score", 45),
                    "naturalness": validation.get("naturalness_score", 45),
                    "persona_evidence": voice.get("score", validation.get("account_fit_score", 45)),
                    "topic_coherence": diversity.get("topic_coherence_score", 45),
                    "media_caption_relevance": 45,
                    "concrete_evidence": 45,
                    "novelty": max(0, 100 - float(diversity.get("full_text_similarity_score", 0) or 0) * 100),
                    "cta_fit": max(0, 100 - float(validation.get("cta_pressure_score", 0) or 0)),
                    "style_diversity": 100 if diversity.get("batch_diversity_status") == "PASS" else 55,
                },
                "warnings": list(diversity.get("diversity_blocked_reasons", []))
                    + list(diversity.get("topic_blocked_reasons", [])),
            }, account_id=account)
            candidate_id = f"draft-{account}-{hashlib.sha256(text.encode()).hexdigest()[:12]}"
            ranked.append({
                "candidate_id": candidate_id,
                "account_id": account,
                "route": "offline_original_text",
                "status": "DRAFT_ONLY",
                "text": text,
                "content_hash": hashlib.sha256(text.encode()).hexdigest(),
                "repair_count": repair["repair_count"],
                "repair": repair["repairs"],
                "hard_gate": gate,
                "public_validator": validation["status"],
                "internal_leak": validation.get("internal_leak_check", {}).get("status", "UNVERIFIED"),
                "account_fit": validation.get("account_fit_check", {}).get("status", "UNVERIFIED"),
                "legacy_quality": diversity.get("status", "WARN_ONLY"),
                **rank,
            })
            seen.add(key)
        ranked.sort(key=lambda row: (-float(row["quality_rank"]), row["candidate_id"]))
        selected = ranked[:limit]
        if account == "liver_manager":
            for index, candidate in enumerate(selected):
                candidate["text"], candidate["draft_style_variant"] = _liver_draft_style_variant(
                    candidate["text"], index,
                )
                # Revalidate the final display text, not its pre-style source.
                validation = final_public_post_validator(candidate["text"], account)
                gate = hard_gate(
                    {"account_id": account, "target_account_id": account,
                     "platform": "threads", "public_post_text": candidate["text"]},
                    account_id=account, public_validation=validation,
                )
                candidate["public_validator"] = validation["status"]
                candidate["hard_gate"] = gate
                candidate["content_hash"] = hashlib.sha256(candidate["text"].encode()).hexdigest()
                candidate["candidate_id"] = f"draft-{account}-{candidate['content_hash'][:12]}"
                candidate["internal_leak"] = validation.get("internal_leak_check", {}).get("status", "UNVERIFIED")
                candidate["account_fit"] = validation.get("account_fit_check", {}).get("status", "UNVERIFIED")
            signatures = {_liver_style_signature(candidate["text"]) for candidate in selected}
            style_score = round(100 * len(signatures) / max(1, len(selected)))
            for candidate in selected:
                candidate["batch_style_diversity_score"] = style_score
                candidate["batch_style_diversity_status"] = "PASS" if style_score >= 60 else "WARN"
                candidate["quality_rank_components"]["style_diversity"] = style_score
                candidate.update(rank_candidate({
                    "quality_components": candidate["quality_rank_components"],
                    "warnings": candidate["warnings"] + ([] if style_score >= 60 else ["LIVER_STYLE_DIVERSITY_LOW"]),
                }, account_id=account))
        if account == "beauty_account":
            phrase_count = sum("個人的には" in candidate["text"] for candidate in selected)
            for candidate in selected:
                candidate["repeated_cliche_count_in_batch"] = max(0, phrase_count - 1)
                if phrase_count > 1:
                    candidate["warnings"] = sorted(set(candidate["warnings"] + ["REPEATED_CLICHE個人的には"]))
        output[account] = selected
    return output


def media_candidates(snapshot_path: Path) -> dict[str, list[dict[str, Any]]]:
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    rows = snapshot.get("review_rows", [])
    output: dict[str, list[dict[str, Any]]] = {}
    for account in ACCOUNTS:
        unique: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row.get("account_id") != account:
                continue
            asset_id = str(row.get("media_asset_id") or "").strip()
            preview = str(row.get("media_preview_url") or "").strip()
            if not asset_id or not preview or asset_id in unique:
                continue
            unique[asset_id] = dict(row)
        limit = max(1, int(load_policy()["draft_pack"]["media_packages_per_account"]))
        selected = list(unique.values())
        selected.sort(key=lambda row: (-_media_selection_rank(row, account), str(row.get("media_asset_id", ""))))
        selected = selected[:limit]
        packages: list[dict[str, Any]] = []
        for index, row in enumerate(selected, 1):
            media = {
                "media_asset_id": row["media_asset_id"],
                "media_type": str(row.get("media_type") or "unknown").lower(),
                "vision_status": "UNAVAILABLE",
                "transcript_status": "UNAVAILABLE",
            }
            caption = ""
            validator = {"status": "UNVERIFIED", "blocked_reasons": []}
            media_validation = {
                "hard_gate_status": "BLOCKED",
                "hard_gate_blocked_reasons": ["rights_status_not_approved", "permission_status_not_approved"],
            }
            package = build_post_package(
                account_id=account,
                media=media,
                public_caption=caption,
                hard_gate_result={"status": "BLOCKED", "hard_gate_reasons": ["rights_or_permission_unverified"]},
                quality_components=row.get("quality_components", {
                    "media_caption_relevance": 0, "concrete_evidence": 0,
                }),
            )
            gate = hard_gate({
                "account_id": account, "target_account_id": account, "platform": "threads",
                "public_post_text": caption, "media_required": True,
                "rights_status": row.get("rights_status", "unknown"),
                "permission_status": row.get("permission_status", "unknown"),
                "media_asset_id": row.get("media_asset_id"), "media_url": row.get("media_preview_url"),
            }, account_id=account, public_validation=validator, media_validation=media_validation)
            packages.append({
                "candidate_id": f"media-{account}-{index}-{hashlib.sha256(str(row['media_asset_id']).encode()).hexdigest()[:10]}",
                "account_id": account,
                "status": "DRAFT_ONLY",
                "media_asset_id": row["media_asset_id"],
                "media_type": row.get("media_type", "unknown"),
                "media_preview_url": row.get("media_preview_url", ""),
                "historical_source_id": row.get("source_id", ""),
                "historical_source_url": row.get("source_url", ""),
                "historical_caption_not_reused": row.get("caption", ""),
                "public_caption": "NOT_GENERATED: VISUAL_UNVERIFIED; do not publish until visual evidence is reviewed",
                "media_understanding": package["media_understanding"],
                "why_this_account_should_post_this": package["why_this_account_should_post_this"],
                "post_angle_options": package["post_angle_options"],
                "post_angle": package["post_angle"],
                "hook": "UNVERIFIED",
                "cta": "UNVERIFIED",
                "claim_support": [],
                "media_anchor": package["media_anchor"],
                "generic_caption_risk": package["generic_caption_risk"],
                "hard_gate": gate,
                "quality_rank": package["quality_rank"],
                "quality_rank_components": package["quality_rank_components"],
                "warnings": sorted(set(package["warnings"] + ["CURRENT_PERMISSION_NOT_REVERIFIED", "CAPTION_WITHHELD_PENDING_VISUAL_EVIDENCE"])),
                "fallback": "No alternate media or text was substituted in this media package.",
                "legacy_validator_snapshot": row.get("validator_status", ""),
            })
        output[account] = packages
    return output


def render(snapshot_path: Path) -> str:
    draft_policy = load_policy()["draft_pack"]
    text_limit = int(draft_policy["text_per_account"])
    media_limit = int(draft_policy["media_packages_per_account"])
    texts = text_candidates()
    media = media_candidates(snapshot_path)
    lines = [
        "# Content Quality V2 Review Pack", "",
        "Local-only owner review artifact. DRAFT_ONLY; no READY or production queue write. Generated from the checked-in offline text catalog and a read-only historical review snapshot. No external provider, Sheets, Threads, X, or Cloudinary was called.", "",
        "## Status and limits", "",
        "- Content V2 policy sets `draft_only=true`, `publishing_enabled=false`.",
        "- Historical media rows are candidates for visual review only. Rights/permission were not re-read; no media is asserted as currently usable.",
        "- Visual evidence was not available in the snapshot; all media packages are `VISUAL_UNVERIFIED`, captions withheld, and hard-gated from reuse.",
        "- Review previews link to historical Cloudinary URLs only; this pack performs no upload or fetch.",
        "- The pack shows at most 5 distinct text drafts and 5 distinct media previews per account. Missing media are not duplicated to fill the sample.",
        "- Media without stored vision evidence remain `VISUAL_UNVERIFIED`; captions are withheld instead of inferred from transcript or historical caption text.", "",
    ]
    totals: dict[str, Any] = {"broken_japanese": 0, "fabricated_experience": 0,
                              "unsupported_high_risk": 0, "internal_leak": 0, "beauty_emoji_compliant": 0}
    for account in ACCOUNTS:
        lines += [f"## {account} — text drafts ({len(texts[account])}/{text_limit})", ""]
        for index, candidate in enumerate(texts[account], 1):
            lines += [f"### {index:02d}. `{candidate['candidate_id']}`", "",
                      f"- Route: `{candidate['route']}`; status: `{candidate['status']}`; hash: `{candidate['content_hash']}`",
                      f"- Hard gate: `{candidate['hard_gate']['status']}`; public validator: `{candidate['public_validator']}`; internal leak: `{candidate['internal_leak']}`; account fit: `{candidate['account_fit']}`",
                      f"- Quality rank: `{candidate['quality_rank']}`; components: `{json.dumps(candidate['quality_rank_components'], ensure_ascii=False, sort_keys=True)}`; warnings: `{', '.join(candidate['warnings']) or 'none'}`",
                      f"- Style repair count: `{candidate['repair_count']}`; display style: `{candidate.get('draft_style_variant', 'catalog')}`; batch style diversity: `{candidate.get('batch_style_diversity_status', 'RANKED')}` `{candidate.get('batch_style_diversity_score', 'n/a')}`; candidate count is one local source row; no queue ID was persisted.",
                      "- OWNER_GRADE: `[ ] A [ ] B [ ] C`; OWNER_REASON=; OWNER_EDIT_NOTES=", "", candidate["text"], ""]
            reasons = candidate["hard_gate"]["hard_gate_reasons"]
            totals["broken_japanese"] += "broken_japanese" in reasons
            totals["fabricated_experience"] += any("fabricated" in r or "experience_reassigned" in r for r in reasons)
            totals["unsupported_high_risk"] += "unsupported_high_risk_factual_claim" in reasons
            totals["internal_leak"] += any("internal" in r for r in reasons)
            if account == "beauty_account":
                allowed = __import__("generation.content_quality_v2", fromlist=["load_policy"]).load_policy()["accounts"][account]["emoji_allowed"]
                emoji_count = sum(candidate["text"].count(emoji) for emoji in allowed)
                totals["beauty_emoji_compliant"] += 1 <= emoji_count <= 4
    for account in ACCOUNTS:
        lines += [f"## {account} — media packages ({len(media[account])}/{media_limit})", ""]
        for index, item in enumerate(media[account], 1):
            lines += [f"### {index:02d}. `{item['candidate_id']}`", "",
                      f"- Asset: `{item['media_asset_id']}` (`{item['media_type']}`); preview: [{item['media_asset_id']}]({item['media_preview_url']})",
                      f"- Historical source: `{item['historical_source_id']}` {str(item['historical_source_url']).strip()}".rstrip(),
                      "- MediaUnderstanding: `VISUAL_UNVERIFIED`; what viewer sees/hears: `UNVERIFIED`.",
                      f"- Why relevant: {item['why_this_account_should_post_this']}",
                      f"- Post angles: `{json.dumps(item['post_angle_options'], ensure_ascii=False)}`; selected angle: `{item['post_angle']}`",
                      f"- Caption: {item['public_caption']}",
                      f"- Media anchor / remove-media test: `{item['media_anchor']}`; fabricated-experience check: `NOT_APPLICABLE_CAPTION_WITHHELD`.",
                      f"- Hard gate: `{item['hard_gate']['status']}` `{item['hard_gate']['hard_gate_reasons']}`; quality rank: `{item['quality_rank']}`; generic-caption risk: `{item['generic_caption_risk']}`",
                      f"- Warnings: `{', '.join(item['warnings'])}`; status: `DRAFT_ONLY`; no READY, reuse, or upload.",
                      "- OWNER_GRADE: `[ ] A [ ] B [ ] C`; OWNER_REASON=; OWNER_EDIT_NOTES=", ""]
        if len(media[account]) < media_limit:
            lines += [f"- BLOCKER: only {len(media[account])} distinct snapshot assets; {media_limit-len(media[account])} additional unique asset(s) are unavailable. No duplication applied.", ""]
    lines += ["## Aggregate evaluation", "",
              f"- Text drafts: Night `{len(texts['night_scout'])}`, Liver `{len(texts['liver_manager'])}`, Beauty `{len(texts['beauty_account'])}` ({text_limit * len(ACCOUNTS)} requested; at most {text_limit}/account).",
              f"- Media packages: Night `{len(media['night_scout'])}`, Liver `{len(media['liver_manager'])}`, Beauty `{len(media['beauty_account'])}` ({media_limit * len(ACCOUNTS)} requested; at most {media_limit}/account).",
              f"- Hard-gate counts among selected text drafts: broken Japanese `{totals['broken_japanese']}`, fabricated experience `{totals['fabricated_experience']}`, unsupported high-risk fact `{totals['unsupported_high_risk']}`, internal/private leak `{totals['internal_leak']}`.",
              f"- Beauty emoji compliance after repair: `{round(100 * totals['beauty_emoji_compliant'] / max(1,len(texts['beauty_account'])))}%`.",
              "- This is not production acceptance: media understanding, current media permissions, caption/media alignment, and unique Beauty media inventory remain unverified.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True, help="local read-only publication review snapshot JSON")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/CONTENT_QUALITY_V2_REVIEW_PACK.md")
    args = parser.parse_args()
    document = render(args.snapshot)
    args.output.write_text(document, encoding="utf-8")
    print(json.dumps({"status": "DRAFT_ONLY", "output": str(args.output),
                      "post_writes": False, "text_counts": {a: len(text_candidates()[a]) for a in ACCOUNTS},
                      "media_counts": {a: len(media_candidates(args.snapshot)[a]) for a in ACCOUNTS}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
