#!/usr/bin/env python3
"""Exactly three read-only editorial packages; no production clients imported."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from acquisition.models import SourcePostBundle  # noqa: E402
from build_media_first_review_pack import inspect_preview, selected_previews  # noqa: E402
from generation.content_quality_v2 import generate_media_first_caption, prepare_media_context  # noqa: E402
from generation.source_grounded_caption import (  # noqa: E402
    SourceGroundedCaptionService, account_rules,
)
from gemini_hybrid_client import GeminiHybridClient, provider_error_evidence
from evidence_context_caption import PrivacyBoundedGeminiGroundedProvider
from public_post_quality import voice_persona_validation  # noqa: E402

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
PRODUCTION_SECRETS = ("SPREADSHEET_ID", "SNS_MASTER_SHEET_ID", "SA_JSON_BASE64", "GCP_SA_JSON_BASE64",
                      "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET", "GITHUB_TOKEN", "THREADS_ACCESS_TOKEN")


def smoke_previews(document: str) -> list[dict]:
    previews = selected_previews(document)
    result = [next(row for row in previews if row["account_id"] == account) for account in ACCOUNTS]
    if len({row["media_asset_id"] for row in result}) != 3:
        raise ValueError("three_distinct_previews_required")
    return result


def relevance_review(media: dict, contract: dict, client: GeminiHybridClient) -> dict:
    context = prepare_media_context(media, account_id=media["account_id"])
    if context["visual_status"] != "VISUAL_VERIFIED":
        return {"status": "RELEVANCE_UNVERIFIED"}
    schema = {"type": "object", "properties": {
        **{key: {"type": "string"} for key in ("account_id", "reason", "audience_need", "content_pillar")},
        "status": {"type": "string", "enum": ["PASS", "RELEVANCE_UNVERIFIED"]},
        "anchor_fact_types": {"type": "array", "items": {"type": "string", "enum": [
            "visible_action", "key_moment", "visible_people_or_objects", "visible_text"]}},
    }, "required": ["account_id", "status", "reason", "audience_need", "content_pillar", "anchor_fact_types"]}
    prompt = (
        "検証済みの視覚事実と対象アカウントの読者・content pillarだけから関連性を判定。"
        "事実や音声、発言、効果を補完しない。ジャンルや人物の見た目だけではPASS不可。"
        "Nightは夜職女性の店・接客・条件・働き方の具体的な判断材料、"
        "Liverは次回配信で変えられる具体的な配信行動、Beautyは20〜30代女性の美容判断に役立つこと。"
        "不明や対象外ならRELEVANCE_UNVERIFIED。無理に関連付けない。JSONのみ。\n"
        + json.dumps({"account_contract": contract, "visual_facts": context["visual_facts"]}, ensure_ascii=False))
    try:
        return client.generate_json(model=os.environ.get("GEMINI_GENERATOR_MODEL", "gemini-3.5-flash"),
                                    prompt=prompt, schema=schema, operation="vision_smoke_relevance",
                                    account_id=media["account_id"])["data"]
    except RuntimeError as exc:
        return {"status": "RELEVANCE_UNVERIFIED", **provider_error_evidence(exc)}


def build_package(row: dict, directory: Path) -> dict:
    account = row["account_id"]
    config = json.loads((ROOT / "config/accounts" / f"{account}.json").read_text())
    contract = {**account_rules(account), "account_id": account,
                "content_pillars": config.get("content_categories", [])}
    inspected = inspect_preview(row, directory, account_content_contract=contract)
    vision = inspected.get("vision", {})
    required = ("visual_summary", "visible_people_or_objects", "visible_action", "key_moment", "main_topic")
    if vision.get("status") == "PASS" and not all(isinstance(vision.get(key), str) and vision[key].strip() for key in required):
        vision = {**vision, "status": "UNAVAILABLE", "failure_class": "invalid_response"}
    media = {**row, **vision, "media_type": "video", "content_hash": inspected.get("content_hash", ""),
             "vision_status": vision.get("status", "UNAVAILABLE"),
             "technical_status": "PASS" if inspected.get("status") == "PREVIEW_READ_OK" else "UNVERIFIED",
             "rights_status": "unknown", "permission_status": "unverified", "strict_relevance_review": True,
             "visual_evidence": {"status": "UNDERSTOOD" if vision.get("status") == "PASS" else "UNVERIFIED",
                                 "media_asset_id": row["media_asset_id"], "content_hash": inspected.get("content_hash", ""),
                                 "provider": vision.get("provider", "gemini"),
                                 "frame_hashes": [frame["sha256"] for frame in inspected.get("frames", [])]}}
    bundle = SourcePostBundle(source_post_id="", source_id="", target_account_id=account,
                              platform="", profile_url="", canonical_post_url="", external_post_id="",
                              original_post_text="", published_at="")
    client = GeminiHybridClient(max_attempts=1)
    media["account_relevance_review"] = relevance_review(media, contract, client)
    service = SourceGroundedCaptionService(PrivacyBoundedGeminiGroundedProvider(client=client),
                                          allow_deterministic_fallback=False, retry_primary_on_alignment_failure=False)
    result = generate_media_first_caption(
        media=media, account_id=account, account_content_contract=contract, recent_posts=[],
        editorial_draft=True, caption_generator=lambda **request: service.generate_media_context(bundle, **request))
    text = str(result.get("public_post_text") or "")
    style = voice_persona_validation(text, account) if text else {"status": "NOT_RUN"}
    return {**row, "vision": vision, "frames": media["visual_evidence"]["frame_hashes"],
            "result": result, "style": style, "fetch_status": inspected.get("status"),
            "failure_class": str(vision.get("failure_class") or result.get("provider_failure_class") or inspected.get("error_class") or "").upper()}


def summary(packages: list[dict]) -> dict:
    verified = sum(
        p["vision"].get("status") == "PASS"
        and p["result"].get("status") == "PASS"
        and p["result"].get("provider_name") == PrivacyBoundedGeminiGroundedProvider.provider_name
        and p["result"].get("provider_status") == "PASS"
        and bool(p["result"].get("public_post_text"))
        and p["result"].get("remove_media_test", {}).get("status") == "PASS"
        and p["result"].get("fabricated_experience_check", {}).get("status") == "PASS"
        for p in packages)
    return {
        "VISION_VERIFIED_COUNT": sum(p["result"].get("media_context", {}).get("visual_status") == "VISUAL_VERIFIED" for p in packages),
        "RELEVANCE_PASS_COUNT": sum(p["result"].get("account_relevance", {}).get("status") == "PASS" for p in packages),
        "CAPTION_GENERATED_COUNT": sum(bool(p["result"].get("public_post_text")) for p in packages),
        "GITHUB_MODELS_CALLS": 0,
        "VERIFIED_MEDIA_PACKAGE_COUNT": verified,
        "FABRICATED_EXPERIENCE_COUNT": sum(p["result"].get("fabricated_experience_check", {}).get("status") == "BLOCKED" for p in packages),
        "GENERIC_CAPTION_SELECTED_COUNT": sum(bool(p["result"].get("public_post_text")) and p["result"].get("remove_media_test", {}).get("generic_caption_risk") == "HIGH" for p in packages),
        "MEDIA_FIRST_QUALITY_PROVEN": "YES" if verified == 3 else "NO",
    }


def render(packages: list[dict]) -> str:
    lines = ["# Content Quality V2 Vision Smoke Review", "", "Internal editorial drafts only. No publish eligibility is granted.", ""]
    lines += [f"{key}={value}" for key, value in summary(packages).items()] + [""]
    for package in packages:
        result, vision = package["result"], package["vision"]
        context = result.get("media_context", {})
        anchor = result.get("remove_media_test", {})
        fields = {
            "ACCOUNT": package["account_id"], "MEDIA_ASSET_ID": package["media_asset_id"],
            "MEDIA_PREVIEW": package["preview_url"], "VISION_PROVIDER": vision.get("provider", "gemini"),
            "VISION_MODEL": vision.get("model", ""),
            "HTTP_STATUS": vision.get("http_status", ""),
            "PROVIDER_ERROR_TYPE": vision.get("provider_error_type", ""),
            "RESPONSE_SCHEMA_STATUS": vision.get("response_schema_status", "NOT_RUN"),
            "VISION_STATUS": vision.get("status", "NOT_RUN"), "REPRESENTATIVE_FRAME_HASHES": package["frames"],
            **{key.upper(): vision.get(key, "UNVERIFIED") for key in ("visual_summary", "visible_action", "key_moment", "main_topic")},
            "VISUAL_FACTS": context.get("visual_facts", []),
            "VISUAL_EVIDENCE_STATUS": context.get("visual_evidence", {}).get("status", "UNVERIFIED"),
            "EDITORIAL_DRAFT_ELIGIBILITY": result.get("editorial_draft_eligibility", {}),
            "PUBLISH_ELIGIBILITY": result.get("publish_eligibility", {}),
            "RELEVANCE_STATUS": result.get("account_relevance", {}).get("status", "NOT_RUN"),
            "WHY_THIS_ACCOUNT_SHOULD_POST_THIS": result.get("account_relevance", {}).get("why_this_account_should_post_this", "UNVERIFIED"),
            "POST_ANGLE_OPTIONS": result.get("post_angles", {}).get("options", []),
            "SELECTED_ANGLE": result.get("post_angles", {}).get("selected", {}),
            "ANCHOR_FACT_IDS": anchor.get("anchor_fact_ids", []),
            "PUBLIC_CAPTION": result.get("public_post_text") or "NOT_GENERATED_OR_REJECTED",
            "CAPTION_PROVIDER": result.get("provider_name", "NOT_RUN"),
            "CAPTION_PROVIDER_STATUS": result.get("provider_status", "NOT_RUN"),
            "MEDIA_ANCHOR_STATUS": anchor.get("media_anchor_status", "NOT_RUN"),
            "CLAIM_SUPPORT": result.get("claim_support", []), "REMOVE_MEDIA_TEST": anchor.get("status", "NOT_RUN"),
            "GENERIC_CAPTION_RISK": anchor.get("generic_caption_risk", "UNVERIFIED"),
            "FABRICATED_EXPERIENCE_CHECK": result.get("fabricated_experience_check", {"status": "NOT_RUN"}),
            "ACCOUNT_STYLE_CHECK": package["style"],
            "FAILURE_CLASS": package["failure_class"] or "NONE",
            "WARNINGS": [warning for warning in [package["failure_class"], *result.get("blocked_reasons", [])] if warning],
        }
        lines += [f"## {package['account_id']}", ""]
        for name, value in fields.items():
            lines += [f"{name}=", "", str(value) if isinstance(value, str) else json.dumps(value, ensure_ascii=False), ""]
        lines += ["OWNER_GRADE=[ ]A [ ]B [ ]C", "OWNER_REASON=", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true" or not os.environ.get("RUNNER_TEMP"):
        raise SystemExit("RUNNER_ONLY")
    if any(os.environ.get(key) for key in PRODUCTION_SECRETS):
        raise SystemExit("PRODUCTION_CREDENTIAL_PRESENT")
    for key in ("BUFFERED_POSTING_ENABLED", "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
                "ALLOW_MEDIA_POSTS", "ALLOW_CLOUDINARY_UPLOAD"):
        if os.environ.get(key, "false").lower() != "false":
            raise SystemExit("PRODUCTION_GATE_ENABLED")
    print("GEMINI_API_KEY_PRESENT=" + str(bool(os.environ.get("GEMINI_API_KEY"))).lower())
    previews = smoke_previews((ROOT / "docs/CONTENT_QUALITY_V2_REVIEW_PACK.md").read_text())
    root = Path(os.environ["RUNNER_TEMP"]) / "cq-v2-vision-smoke"
    packages = [build_package(row, root / row["account_id"]) for row in previews]
    review = render(packages)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(review, encoding="utf-8")
    print(review)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as handle:
            handle.write(review)
    # Irrelevant media is a valid Vision proof, but never a successful media package.
    vision_pass = summary(packages)["VISION_VERIFIED_COUNT"] == 3
    relevant_drafts_pass = all(p["result"].get("status") == "PASS" for p in packages
                              if p["result"].get("account_relevance", {}).get("status") == "PASS")
    return 0 if vision_pass and relevant_drafts_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
