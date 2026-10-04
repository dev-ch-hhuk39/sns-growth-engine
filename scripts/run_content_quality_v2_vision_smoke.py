#!/usr/bin/env python3
"""Selected historical read-only editorial packages; no production clients imported."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
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
from gemini_quota_diagnostics import FIELDS as QUOTA_FIELDS
from evidence_context_caption import PrivacyBoundedGeminiGroundedProvider
from public_post_quality import voice_persona_validation  # noqa: E402

ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
PRODUCTION_SECRETS = ("SPREADSHEET_ID", "SNS_MASTER_SHEET_ID", "SA_JSON_BASE64", "GCP_SA_JSON_BASE64",
                      "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET", "GITHUB_TOKEN", "THREADS_ACCESS_TOKEN")


class SmokeGeminiClient(GeminiHybridClient):
    """Debug-only bounded transport and evidence; no production client changes."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.caption_evidence = {}
        self.caption_candidate = {}
        self.last_evidence = {}
        path = ROOT / "docs/fixtures/content_quality_v2_smoke_evidence.json"
        self.quota_basis = json.loads(path.read_text()).get("model_quota", {}) if path.exists() else {}

    def fallback_allowed(self, model):
        basis = self.quota_basis
        rows = basis.get("quota_violations", [])
        if not rows or model != "gemini-3.5-flash":
            return False
        try:
            until = datetime.fromisoformat(basis["observed_at"].replace("Z", "+00:00")) + timedelta(seconds=basis["retry_delay_seconds"])
        except (KeyError, TypeError, ValueError):
            return False
        return datetime.now(timezone.utc) < until and all(
            row.get("quota_model") == model and "PerProjectPerModel" in row.get("quota_id", "")
            and row.get("rate_limit_class") in {"DAILY_QUOTA_EXHAUSTED", "MODEL_QUOTA_EXHAUSTED"}
            for row in rows)

    def generate_json(self, **kwargs):
        caption = kwargs.get("operation") == "direct_reference_caption_generation"
        if caption:
            kwargs["retry_profile"] = "vision_relevance"
            # Keep the existing schema and validators; reduce conflicting source
            # and marketing instructions for this visual-only editorial test.
            prompt = kwargs["prompt"]
            start = prompt.find('{"target_account_id":')
            if start >= 0:
                source, _ = json.JSONDecoder().raw_decode(prompt[start:])
                media = source.get("media_first_input", {})
                kwargs["prompt"] = (
                    "日本語の未公開Media投稿候補を作る。指定JSON schemaの全fieldを返す。"
                    "選ばれたvisual factとangleのみが事実の根拠。画面テキストの主観は主観のまま引用する。"
                    "public_post_textは100〜220文字、具体的な画面の観察→読者の判断ひとつ。CTAなし。"
                    "事実観察には『この動画』と短い正確な引用を使う。一般論や追加の原因・成果・体験を捏造しない。"
                    "Nightは男性スカウトの僕、Liverは女性マネージャーの私、Beautyは女友達で自然な絵文字1〜4。"
                    "本文を書いてから実在する主張をmain_claimsに正確に転記する。"
                    "main_claimsの各文をclaim_support.caption_claimにも同じ文で入れる。"
                    "source_evidenceはvisual fact内の正確な一節、anchor_fact_idsはそのfactのID。"
                    "要約・別表現をcaption_claimにしない。表現を飾るための実態・頻度・最上級を足さない。"
                    "自分の使用体験や投稿主の経験の横取りは厳禁。材料不足はblocked_reasonsへ。\n"
                    + json.dumps({"account_rules": source.get("account_rules", {}),
                                  "selected_post_angle": media.get("selected_post_angle", {}),
                                  "visual_facts": media.get("media_context", {}).get("visual_facts", []),
                                  "generation_attempt": source.get("generation_attempt", 0)}, ensure_ascii=False))
        original_model = kwargs.get("model", "")
        fallback = (caption or kwargs.get("operation") == "vision_smoke_relevance") and self.fallback_allowed(original_model)
        if fallback:
            kwargs["model"] = "gemini-3.1-flash-lite"
        decision = {"requested_model": original_model, "model": kwargs.get("model", ""),
                    "fallback_used": fallback, "fallback_basis_run": self.quota_basis.get("origin_run_id", "") if fallback else ""}
        try:
            result = super().generate_json(**kwargs)
            self.last_evidence = {**decision, "attempt_count": result.get("actual_requests", 0),
                                  "attempt_history": result.get("attempt_history", [])}
            if caption:
                self.caption_candidate = {key: result.get("data", {}).get(key) for key in ("public_post_text", "claim_support", "internal_analysis", "blocked_reasons")}
                self.caption_evidence = {**decision, "provider_status": "PASS", "provider_http_status": 200,
                    "model": result.get("model", ""), "attempt_count": result.get("actual_requests", 0),
                    "attempt_history": result.get("attempt_history", [])}
            return result
        except (RuntimeError, ValueError, TypeError) as exc:
            self.last_evidence = decision
            if caption:
                self.caption_evidence = {**decision, **provider_error_evidence(exc),
                    **getattr(exc, "quota_diagnostics", {}), "retry_status": getattr(exc, "retry_status", ""),
                    "attempt_count": getattr(exc, "attempt_count", 0),
                    "attempt_history": getattr(exc, "attempt_history", [])}
            raise


def smoke_previews(document: str, target_account: str = "all") -> list[dict]:
    if target_account not in (*ACCOUNTS, "all"):
        raise ValueError("invalid_target_account")
    accounts = ACCOUNTS if target_account == "all" else (target_account,)
    previews = selected_previews(document)
    result = [next(row for row in previews if row["account_id"] == account) for account in accounts]
    if len({row["media_asset_id"] for row in result}) != len(accounts):
        raise ValueError("distinct_selected_previews_required")
    return result


def relevance_review(media: dict, contract: dict, client: GeminiHybridClient) -> dict:
    context = prepare_media_context(media, account_id=media["account_id"])
    if context["visual_status"] != "VISUAL_VERIFIED":
        return {"status": "NOT_RUN", "provider_status": "NOT_RUN", "attempt_count": 0, "attempt_history": []}
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
        response = client.generate_json(model=os.environ.get("GEMINI_GENERATOR_MODEL", "gemini-3.5-flash"),
                                    prompt=prompt, schema=schema, operation="vision_smoke_relevance",
                                    account_id=media["account_id"], retry_profile="vision_relevance")
        return {**response["data"], "provider_status": "PASS", "provider_http_status": 200,
                "provider_error_type": "", "attempt_count": response.get("actual_requests", 0),
                "attempt_history": response.get("attempt_history", []),
                **getattr(client, "last_evidence", {})}
    except (RuntimeError, ValueError, TypeError) as exc:
        diagnostics = getattr(exc, "quota_diagnostics", {})
        safe = {key: diagnostics[key] for key in (*QUOTA_FIELDS, "quota_violations") if key in diagnostics}
        return {"status": "NOT_RUN", **provider_error_evidence(exc), **safe,
                "retry_status": getattr(exc, "retry_status", ""),
                **getattr(client, "last_evidence", {}),
                "attempt_history": getattr(exc, "attempt_history", []),
                "attempt_count": getattr(exc, "attempt_count", 0)}


def build_package(row: dict, directory: Path) -> dict:
    account = row["account_id"]
    config = json.loads((ROOT / "config/accounts" / f"{account}.json").read_text())
    contract = {**account_rules(account), "account_id": account,
                "content_pillars": config.get("content_categories", [])}
    evidence_path = ROOT / "docs/fixtures/content_quality_v2_smoke_evidence.json"
    saved = json.loads(evidence_path.read_text()).get("vision", []) if evidence_path.exists() else []
    evidence = next((p for p in saved if p.get("media_asset_id") == row["media_asset_id"] and p.get("account_id") == account), None)
    inspected = inspect_preview(row, directory, account_content_contract=contract, smoke_vision_evidence=evidence)
    vision = inspected.get("vision", {})
    required = ("visual_summary", "key_moment")
    if vision.get("status") == "PASS" and (not isinstance(vision.get("visible_action"), str)
            or not all(isinstance(vision.get(key), str) and vision[key].strip() for key in required)):
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
    client = SmokeGeminiClient(max_attempts=1)
    media["account_relevance_review"] = relevance_review(media, contract, client)
    service = SourceGroundedCaptionService(PrivacyBoundedGeminiGroundedProvider(client=client),
                                          allow_deterministic_fallback=False, retry_primary_on_alignment_failure=False)
    result = generate_media_first_caption(
        media=media, account_id=account, account_content_contract=contract, recent_posts=[],
        editorial_draft=True, caption_generator=lambda **request: service.generate_media_context(bundle, **request))
    text = str(result.get("public_post_text") or "")
    style = voice_persona_validation(text, account) if text else {"status": "NOT_RUN"}
    return {**row, "caption_candidate": client.caption_candidate, "caption_provider_evidence": client.caption_evidence,
            "smoke_vision_evidence": {"media_asset_id": row["media_asset_id"], "account_id": account,
                "content_hash": inspected.get("content_hash", ""), "vision": vision,
                "frame_hashes": media["visual_evidence"]["frame_hashes"]},
            "relevance_provider_evidence": media["account_relevance_review"], "vision": vision, "frames": media["visual_evidence"]["frame_hashes"],
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
        "TARGET_ACCOUNTS": [p.get("account_id", "") for p in packages],
        "VISION_TARGET_COUNT": len(packages),
        "VISION_VERIFIED_COUNT": sum(p["result"].get("media_context", {}).get("visual_status") == "VISUAL_VERIFIED" for p in packages),
        "RELEVANCE_PASS_COUNT": sum(p["result"].get("account_relevance", {}).get("status") == "PASS" for p in packages),
        "CAPTION_GENERATED_COUNT": sum(bool(p["result"].get("public_post_text")) for p in packages),
        "GITHUB_MODELS_CALLS": 0,
        "VERIFIED_MEDIA_PACKAGE_COUNT": verified,
        "FABRICATED_EXPERIENCE_COUNT": sum(p["result"].get("fabricated_experience_check", {}).get("status") == "BLOCKED" for p in packages),
        "GENERIC_CAPTION_SELECTED_COUNT": sum(bool(p["result"].get("public_post_text")) and p["result"].get("remove_media_test", {}).get("generic_caption_risk") == "HIGH" for p in packages),
        "MEDIA_FIRST_QUALITY_PROVEN": "YES" if packages and verified == len(packages) else "NO",
    }


def render(packages: list[dict]) -> str:
    lines = ["# Content Quality V2 Vision Smoke Review", "", "Internal editorial drafts only. No publish eligibility is granted.", ""]
    lines += [f"{key}={json.dumps(value) if isinstance(value, list) else value}" for key, value in summary(packages).items()] + [""]
    for package in packages:
        result, vision = package["result"], package["vision"]
        context = result.get("media_context", {})
        anchor = result.get("remove_media_test", {})
        caption_evidence = package.get("caption_provider_evidence", {})
        provider_failed = caption_evidence.get("provider_status") in {"UNAVAILABLE", "ERROR"}
        fields = {
            "MEDIA_FETCH_STATUS": package.get("fetch_status", ""),
            "SMOKE_VISION_EVIDENCE": package.get("smoke_vision_evidence", {}),
            "CAPTION_PROVIDER_EVIDENCE": caption_evidence,
            "CAPTION_CANDIDATE_FOR_REVIEW": package.get("caption_candidate", {}),
            "RELEVANCE_PROVIDER_EVIDENCE": package.get("relevance_provider_evidence", {}),
            "ACCOUNT": package["account_id"], "MEDIA_ASSET_ID": package["media_asset_id"],
            "MEDIA_PREVIEW": package["preview_url"], "VISION_PROVIDER": vision.get("provider", "gemini"),
            "VISION_MODEL": vision.get("model", ""),
            "HTTP_STATUS": vision.get("http_status", ""),
            "PROVIDER_ERROR_TYPE": vision.get("provider_error_type", ""),
            "RESPONSE_SCHEMA_STATUS": vision.get("response_schema_status", "NOT_RUN"),
            **{key.upper(): vision.get(key, "") for key in (
                "raw_response_type", "parse_stage", "schema_error", "missing_fields", "empty_fields",
                "field", "expected_type", "actual_type", "normalizations", "attempt_count")},
            "VISION_STATUS": vision.get("status", "NOT_RUN"), "REPRESENTATIVE_FRAME_HASHES": package["frames"],
            **{key.upper(): vision.get(key, "UNVERIFIED") for key in ("visual_summary", "visible_action", "key_moment", "main_topic")},
            "VISUAL_FACTS": context.get("visual_facts", []),
            "VISUAL_EVIDENCE_STATUS": context.get("visual_evidence", {}).get("status", "UNVERIFIED"),
            "EDITORIAL_DRAFT_ELIGIBILITY": result.get("editorial_draft_eligibility", {}),
            "PUBLISH_ELIGIBILITY": result.get("publish_eligibility", {}),
            "RELEVANCE_STATUS": result.get("account_relevance", {}).get("status", "NOT_RUN"),
            **{key.upper(): vision.get(key, "") for key in (
                "provider_http_status", "provider_error_status", "rate_limit_class", "quota_metric",
                "quota_id", "quota_model", "quota_location", "quota_limit_value", "retry_delay_seconds", "retry_status")},
            "QUOTA_VIOLATIONS": vision.get("quota_violations", []),
            "VISION_ATTEMPT_HISTORY": vision.get("attempt_history", []),
            "VISION_ATTEMPT_COUNT": vision.get("attempt_count", 0),
            **{"RELEVANCE_" + key.upper(): result.get("account_relevance", {}).get(key, "")
               for key in ("attempt_count", "review_status", "decision_class", "reason", "audience_need",
                           "content_pillar", "anchor_fact_types", "provider_status", "provider_http_status", "provider_error_type")},
            **{"RELEVANCE_" + key.upper(): package.get("relevance_provider_evidence", {}).get(key, [] if key in ("quota_violations", "attempt_history") else "")
               for key in ("provider_error_status", "rate_limit_class", "quota_metric", "quota_id", "quota_model",
                           "quota_location", "quota_limit_value", "retry_delay_seconds", "retry_status",
                           "quota_violations", "attempt_history")},
            "WHY_THIS_ACCOUNT_SHOULD_POST_THIS": result.get("account_relevance", {}).get("why_this_account_should_post_this", "UNVERIFIED"),
            "POST_ANGLE_OPTIONS": result.get("post_angles", {}).get("options", []),
            "SELECTED_ANGLE": result.get("post_angles", {}).get("selected", {}),
            "ANCHOR_FACT_IDS": anchor.get("anchor_fact_ids", []),
            "PUBLIC_CAPTION": result.get("public_post_text") or "NOT_GENERATED_OR_REJECTED",
            "CAPTION_PROVIDER": result.get("provider_name", "NOT_RUN"),
            "CAPTION_PROVIDER_STATUS": result.get("provider_status", "NOT_RUN"),
            "MEDIA_ANCHOR_STATUS": anchor.get("media_anchor_status", "NOT_RUN"),
            "CLAIM_SUPPORT": result.get("claim_support", []), "REMOVE_MEDIA_TEST": "NOT_RUN" if provider_failed else anchor.get("status", "NOT_RUN"),
            "GENERIC_CAPTION_RISK": "UNVERIFIED" if provider_failed else anchor.get("generic_caption_risk", "UNVERIFIED"),
            "FABRICATED_EXPERIENCE_CHECK": {"status": "NOT_RUN"} if provider_failed else result.get("fabricated_experience_check", {"status": "NOT_RUN"}),
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
    parser.add_argument("--target-account", choices=(*ACCOUNTS, "all"), default="all")
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
    previews = smoke_previews((ROOT / "docs/CONTENT_QUALITY_V2_REVIEW_PACK.md").read_text(), args.target_account)
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
    vision_pass = bool(packages) and summary(packages)["VISION_VERIFIED_COUNT"] == len(previews)
    relevant_drafts_pass = all(p["result"].get("status") == "PASS" for p in packages
                              if p["result"].get("account_relevance", {}).get("status") == "PASS")
    return 0 if vision_pass and relevant_drafts_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
