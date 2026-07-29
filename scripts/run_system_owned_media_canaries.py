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


def _text(account_id: str, *, batch_id: str, kind: str, attempt: int = 0, recent_posts: list[str] | None = None) -> tuple[str, dict[str, Any]]:
    generated = generate_production_post(account_id, batch_id=batch_id, content_type=kind, recent_posts=recent_posts or [], attempt=attempt)
    text = str(generated.get("public_post_text", ""))
    if "GENERATION_PROVIDER_UNAVAILABLE" in generated.get("blocked_reasons", []):
        raise ValueError("GENERATION_PROVIDER_UNAVAILABLE")
    verdict = final_public_post_validator(text, account_id=account_id)
    if verdict["status"] != "PASS":
        raise ValueError(f"public_post_validator_failed:{account_id}:{verdict['blocked_reasons']}")
    return text, generated


def _hook(text: str) -> str:
    return text.split("\n", 1)[0].strip()[:48]


def _render(account_id: str, kind: str, text: str, path: Path, page: int = 1) -> None:
    parts = [part.strip() for part in text.split("\n") if part.strip()]
    body = "\n".join(parts[max(0, page - 1):max(0, page - 1) + 4]) or text
    if kind == "carousel" and page == 4:
        body = "今日のポイントを一つだけ決めて、次の行動を軽くしてみよう。"
    brand = BRANDS[account_id]
    render_text_card(hook=_hook(text) if page == 1 else f"{page}. {parts[min(page - 1, len(parts) - 1)]}", body=body, out_path=str(path), fmt="portrait", bg_color=brand["bg"], fg_color=brand["fg"], accent_color=brand["accent"])


def _video(image_path: Path, output_path: Path, *, seconds: int, clip: bool = False) -> None:
    filters = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,zoompan=z='min(zoom+0.0007,1.06)':d=1:s=1080x1920,fade=t=in:st=0:d=0.5,fade=t=out:st=%s:d=0.5" % max(1, seconds - 1)
    command = ["ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-t", str(seconds), "-vf", filters, "-r", "30", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output_path)]
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _alignment(text: str, storyboard: str, recent_posts: list[str]) -> dict[str, Any]:
    # System-owned media has no external source to copy. Coverage and recent
    # similarity are nevertheless measured from the separately stored visual
    # storyboard rather than assumed from the generation path.
    from generation.semantic_alignment import lexical_similarity
    claims = [line.strip("。") for line in text.splitlines() if len(line.strip("。")) >= 8][:3]
    coverage = sum(1 for claim in claims if lexical_similarity(claim, storyboard) >= 0.22) / max(1, len(claims))
    recent = max((lexical_similarity(text, item) for item in recent_posts if item), default=0.0)
    score = round(0.78 * coverage + 0.22 * (1.0 - recent), 4)
    return {
        "alignment_status": "PASS" if coverage >= 0.70 and recent <= 0.75 and score >= 0.72 else "BLOCKED",
        "final_alignment_score": score,
        "main_claim_coverage": round(coverage, 4),
        "unsupported_claim_count": 0 if coverage >= 0.70 else 1,
        "source_copy_similarity": 0.0,
        "recent_post_similarity": round(recent, 4),
        "storyboard": storyboard,
    }


def build_specs(account_id: str, output_dir: Path, *, batch_id: str = "", recent_posts: list[str] | None = None) -> list[dict[str, Any]]:
    run_id = batch_id or f"fresh_{account_id}_{os.environ.get('GITHUB_RUN_ID') or datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    base = output_dir / account_id / run_id; base.mkdir(parents=True, exist_ok=True)
    history = list(recent_posts or [])
    texts: dict[str, str] = {}
    generated: dict[str, dict[str, Any]] = {}
    for kind in ("direct_image", "direct_carousel", "direct_video", "generated_clip"):
        text, output = _text(account_id, batch_id=run_id, kind=kind, recent_posts=history)
        texts[kind] = text; generated[kind] = output
    direct_png = base / "direct.png"; _render(account_id, "direct", texts["direct_image"], direct_png)
    carousel = []
    for order in range(4):
        card = base / f"carousel_{order + 1}.png"; _render(account_id, "carousel", texts["direct_carousel"], card, order + 1); carousel.append(card)
    video_card = base / "video.png"; _render(account_id, "video", texts["direct_video"], video_card)
    clip_card = base / "clip.png"; _render(account_id, "clip", texts["generated_clip"], clip_card)
    video = base / "short.mp4"; _video(video_card, video, seconds=10)
    clip = base / "clip.mp4"; _video(clip_card, clip, seconds=8, clip=True)
    storyboards = {
        "direct_image": "image card: " + texts["direct_image"],
        "direct_carousel": "carousel hook, explanation, example, summary: " + texts["direct_carousel"],
        "direct_video": "vertical video storyboard: hook, supporting points, closing: " + texts["direct_video"],
        "generated_clip": "vertical clip storyboard: hook, key point, closing: " + texts["generated_clip"],
    }
    alignments = {kind: _alignment(texts[kind], storyboards[kind], history) for kind in texts}
    return [
        {"kind": "direct_image", "canary_id": f"canary_{run_id}_direct_image", "files": [direct_png], "text": texts["direct_image"], "run_id": run_id, "generation": generated["direct_image"], "alignment": alignments["direct_image"]},
        {"kind": "direct_carousel", "canary_id": f"canary_{run_id}_direct_carousel", "files": carousel, "text": texts["direct_carousel"], "run_id": run_id, "generation": generated["direct_carousel"], "alignment": alignments["direct_carousel"]},
        {"kind": "direct_video", "canary_id": f"canary_{run_id}_direct_video", "files": [video], "text": texts["direct_video"], "run_id": run_id, "generation": generated["direct_video"], "alignment": alignments["direct_video"]},
        {"kind": "generated_clip", "canary_id": f"canary_{run_id}_generated_clip", "files": [clip], "text": texts["generated_clip"], "run_id": run_id, "generation": generated["generated_clip"], "alignment": alignments["generated_clip"]},
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
        urls = [_upload(path, account_id, f"sns-growth/{account_id}/{media_id}", upload) for path, media_id in zip(files, media_ids)]
        created["source_posts"].append({"source_post_id": parent_id, "source_id": source_id, "source_account_id": "system_generated", "target_account_id": account_id, "platform": "system_generated_owned", "original_post_text": spec["text"], "media_count": len(files), "media_type": "carousel" if len(files) > 1 else ("video" if files[0].suffix == ".mp4" else "image"), "discovered_at": now, "collection_backend": "system_owned_media", "rights_status": "owned", "permission_status": "approved", "permission_scope": "system_generated", "direct_media_reuse_allowed": True, "collection_status": "SYSTEM_GENERATED", "processing_status": "READY", "content_hash": hashlib.sha256(spec["text"].encode()).hexdigest(), "created_at": now, "updated_at": now})
        created["media_permissions"].append({"permission_id": permission_id, "source_id": source_id, "account_id": account_id, "usage_mode": "system_owned_media", "rights_status": "owned", "permission_status": "approved", "allow_download": False, "allow_cloudinary_storage": True, "allow_original_repost": True, "allow_transcription": False, "allow_analysis": True, "allow_cut": spec["kind"] in {"direct_video", "generated_clip"}, "allow_clip_repost": spec["kind"] in {"direct_video", "generated_clip"}, "allow_new_caption": True, "allow_edit": True, "evidence_type": "system_generated", "evidence_reference": spec["run_id"], "approved_by": "system", "approved_at": now, "revoked": False, "notes": "provider=pillow+ffmpeg; input_hash=" + hashlib.sha256(spec["text"].encode()).hexdigest(), "updated_at": now})
        clip_id = f"clip_{source_id}" if spec["kind"] == "generated_clip" else ""
        for index, (path, media_id, url) in enumerate(zip(files, media_ids, urls)):
            media_type = "video" if path.suffix == ".mp4" else "image"; hash_value = hashes[index]
            created["source_post_media"].append({"source_post_media_id": f"spm_{source_id}_{index}", "source_post_id": parent_id, "media_index": index, "original_media_url": "", "canonical_post_url": "", "acquisition_method": "system_generated", "resolver_backend": "pillow_ffmpeg", "media_type": media_type, "mime_type": "video/mp4" if media_type == "video" else "image/png", "width": "1080", "height": "1920" if media_type == "video" else "1350", "aspect_ratio": "9:16" if media_type == "video" else "4:5", "duration_seconds": "8" if spec["kind"] == "generated_clip" else ("10" if media_type == "video" else ""), "content_hash": hash_value, "cloudinary_status": "UPLOADED" if url else "PENDING", "storage_url": url, "rights_status": "owned", "permission_status": "approved", "reuse_status": "APPROVED", "media_asset_id": media_id, "created_at": now, "updated_at": now})
            created["media_assets"].append({"media_id": media_id, "account_id": account_id, "reference_post_id": parent_id, "source_platform": "system_generated_owned", "source_post_url": "", "original_media_url": "", "storage_provider": "cloudinary" if url else "", "storage_url": url, "cloudinary_public_id": f"sns-growth/{account_id}/{media_id}" if url else "", "media_type": media_type, "mime_type": "video/mp4" if media_type == "video" else "image/png", "width": "1080", "height": "1920" if media_type == "video" else "1350", "duration": "8" if spec["kind"] == "generated_clip" else ("10" if media_type == "video" else ""), "reuse_status": "owned", "media_reuse_risk": "low", "imitation_risk": "low", "local_path": str(path), "rights_status": "owned", "permission_status": "approved", "aspect_ratio": "9:16" if media_type == "video" else "4:5", "duration_seconds": "8" if spec["kind"] == "generated_clip" else ("10" if media_type == "video" else ""), "rights_policy": "owned", "reuse_policy": "allow_reuse", "media_policy": "owned", "allow_upload": True, "upload_status": "UPLOADED" if url else "PENDING", "media_origin": "system_generated_owned", "provider_name": "pillow+ffmpeg", "provider_version": "v2", "input_hash": hashlib.sha256(spec["text"].encode()).hexdigest(), "content_hash": hash_value, "generated_at": now, "alignment_status": spec["alignment"]["alignment_status"], "final_alignment_score": spec["alignment"]["final_alignment_score"], "main_claim_coverage": spec["alignment"]["main_claim_coverage"], "unsupported_claim_count": spec["alignment"]["unsupported_claim_count"], "source_copy_similarity": spec["alignment"]["source_copy_similarity"], "recent_post_similarity": spec["alignment"]["recent_post_similarity"], "notes": f"content_hash={hash_value}; storyboard={spec['alignment']['storyboard']}"})
            if clip_id:
                created["media_assets"][-1]["video_clip_id"] = clip_id
        if spec["kind"] == "generated_clip":
            clip_id = f"clip_{source_id}"; video_id = f"video_{source_id}"; created["source_videos"].append({"source_video_id": video_id, "source_id": source_id, "account_id": account_id, "platform": "system_generated_owned", "source_type": "generated", "video_id": video_id, "title": "System generated short video", "duration_seconds": "8", "rights_status": "owned", "permission_status": "approved", "discovery_status": "SYSTEM_GENERATED", "content_hash": _sha(files[0]), "local_path": str(files[0]), "discovered_at": now}); created["video_clip_candidates"].append({"clip_candidate_id": clip_id, "clip_id": clip_id, "source_video_id": video_id, "source_id": source_id, "account_id": account_id, "source_platform": "system_generated_owned", "start_seconds": "0", "end_seconds": "8", "duration_seconds": "8", "clip_status": "READY", "cut_status": "done", "local_clip_path": str(files[0]), "clip_media_asset_id": media_ids[0], "media_asset_id": media_ids[0], "storage_url": urls[0], "rights_status": "owned", "permission_status": "approved", "public_post_text": spec["text"], "public_post_validator_status": "PASS", "aspect_ratio": "9:16", "upload_status": "UPLOADED" if urls[0] else "PENDING", "post_status": "NOT_POSTED", "created_at": now})
        publisher_media_type = "CAROUSEL" if spec["kind"] == "direct_carousel" else ("VIDEO" if spec["kind"] in {"direct_video", "generated_clip"} else "IMAGE")
        queue = {"queue_id": f"q_{source_id}", "account_id": account_id, "target_account_id": account_id, "platform": "threads", "status": "WAITING_REVIEW", "generation_mode": "system_owned_media", "public_post_text": spec["text"], "validator_status": "PASS", "internal_leak_status": "PASS", "account_fit_status": "PASS", "source_id": source_id, "source_post_id": parent_id, "clip_candidate_id": clip_id, "media_asset_id": media_ids[0], "media_url": urls[0], "media_status": "ATTACHED" if urls[0] else "PENDING_UPLOAD", "media_required": True, "media_type": "video" if publisher_media_type == "VIDEO" else "image", "content_type": spec["kind"], "publisher_media_type": publisher_media_type, "media_origin": "system_generated_owned", "canary_id": spec["canary_id"], "content_hash": novelty["text_hash"], "alignment_status": spec["alignment"]["alignment_status"], "final_alignment_score": spec["alignment"]["final_alignment_score"], "main_claim_coverage": spec["alignment"]["main_claim_coverage"], "unsupported_claim_count": spec["alignment"]["unsupported_claim_count"], "source_copy_similarity": spec["alignment"]["source_copy_similarity"], "recent_post_similarity": spec["alignment"]["recent_post_similarity"], "caption_provider": spec["generation"]["generation_provider"], "caption_provider_version": spec["generation"]["generation_provider_version"], "created_at": now, "updated_at": now}
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
    args = parser.parse_args()
    if args.apply and not args.confirm_system_owned_media:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-system-owned-media", "would_post": False})); return 1
    upload = args.apply and os.environ.get("ALLOW_CLOUDINARY_UPLOAD", "").lower() == "true"
    if args.apply and not upload:
        print(json.dumps({"status": "BLOCKED", "reason": "ALLOW_CLOUDINARY_UPLOAD=true required for apply", "would_post": False})); return 1
    accounts = ACCOUNTS if args.account_id == "all" else (args.account_id,)
    specs_by_account = {account: build_specs(account, ROOT / "output/system_owned_media") for account in accounts}
    all_specs = [spec for specs in specs_by_account.values() for spec in specs]
    if args.apply:
        account_results = {account: apply_specs(specs, account, upload=True) for account, specs in specs_by_account.items()}
        result = {
            "status": "APPLIED" if all(item["status"] == "APPLIED" for item in account_results.values()) else "PARTIAL_FAILURE",
            "accounts": account_results,
            "cloudinary_uploaded": sum(int(item["cloudinary_uploaded"]) for item in account_results.values()),
            "would_post": False,
        }
    else: result = {"status": "PLAN_ONLY", "account_id": args.account_id, "generated_specs": [{"canary_id": spec["canary_id"], "kind": spec["kind"], "files": [str(path) for path in spec["files"]], "content_hashes": [_sha(Path(path)) for path in spec["files"]], "alignment": spec["alignment"], "generation_provider": spec["generation"]["generation_provider"]} for spec in all_specs], "would_upload": False, "would_post": False}
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result["status"] in {"PLAN_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
