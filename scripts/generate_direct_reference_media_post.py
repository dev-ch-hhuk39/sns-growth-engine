#!/usr/bin/env python3
"""Generate a source-grounded public caption; never output private analysis."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
from acquisition.models import SourcePostBundle, stable_content_hash
from generation.source_grounded_caption import GitHubModelsGroundedProvider, SourceGroundedCaptionService
from public_post_quality import final_public_post_validator, public_preview
def main() -> int:
    parser = argparse.ArgumentParser(description="generate a validator-safe direct-media caption")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"]); parser.add_argument("--source-post-id", required=True); parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source-post-text", default="", help="private analysis input; never emitted")
    args = parser.parse_args()
    bundle = SourcePostBundle(
        source_post_id=args.source_post_id,
        source_id="cli_private_source",
        target_account_id=args.account_id,
        platform="threads",
        profile_url="https://www.threads.com/@private",
        canonical_post_url=f"https://www.threads.com/@private/post/{args.source_post_id}",
        external_post_id=args.source_post_id,
        original_post_text=args.source_post_text,
        published_at="",
        content_hash=stable_content_hash(args.source_post_text, []),
    )
    generated = SourceGroundedCaptionService(GitHubModelsGroundedProvider()).generate(
        bundle,
        account_id=args.account_id,
    )
    text = str(generated.get("public_post_text", ""))
    check = final_public_post_validator(text, args.account_id)
    alignment = generated.get("semantic_alignment", {})
    passed = generated.get("status") == "PASS" and check["status"] == "PASS"
    print(json.dumps({
        "status": "PLAN_ONLY" if passed else "BLOCKED",
        "source_post_id": args.source_post_id,
        "public_post_preview": public_preview(text),
        "public_post_validator": check["status"],
        "semantic_alignment": alignment,
        "caption_provider": generated.get("provider_name", ""),
        "blocked_reasons": generated.get("blocked_reasons", []) + check.get("blocked_reasons", []),
        "source_post_text_exposed": False,
    }, ensure_ascii=False, indent=2))
    return 0 if passed else 1
if __name__ == "__main__": raise SystemExit(main())
