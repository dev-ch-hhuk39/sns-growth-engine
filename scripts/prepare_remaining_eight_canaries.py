#!/usr/bin/env python3
"""Prepare the exact remaining eight production canaries without publishing.

The atomic batch contains, for both night_scout and liver_manager:
- reference_text
- direct_video
- direct_carousel
- generated_clip

Dry-run never writes Sheets, uploads media, or publishes.
Apply requires an exact batch id, approved manifest hash, explicit confirmation,
and ALLOW_CLOUDINARY_UPLOAD=true. Apply still never publishes Threads posts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from create_missing_text_canaries import _append as append_text_rows
from create_missing_text_canaries import build_rows as build_text_rows
from run_system_owned_media_canaries import apply_specs, build_specs

ACCOUNTS = ("night_scout", "liver_manager")
TEXT_KIND = "reference_text"
MEDIA_KINDS = ("direct_video", "direct_carousel", "generated_clip")
REMAINING_TYPES = (TEXT_KIND, *MEDIA_KINDS)

CONFIRMATION = "PREPARE_APPROVED_REMAINING_EIGHT"
MANIFEST_VERSION = "remaining_eight_manifest_v1"


def _row_text(row: dict[str, Any]) -> str:
    return str(
        row.get("posted_text")
        or row.get("public_post_text")
        or row.get("text")
        or ""
    ).strip()


ACTIVE_GENERATION_STATUSES = {
    "READY",
    "WAITING_REVIEW",
    "PROCESSING",
}


def _generation_history(
    account_id: str,
    posted_results: list[dict[str, Any]],
    existing_queue: list[dict[str, Any]],
) -> list[str]:
    """Combine posted and active pending text without duplicates."""
    history: list[str] = []
    seen: set[str] = set()

    sources = (
        (posted_results, False),
        (existing_queue, True),
    )

    for rows, require_active in sources:
        for row in rows:
            if str(row.get("account_id", "")) != account_id:
                continue
            if (
                require_active
                and str(row.get("status", "")).upper()
                not in ACTIVE_GENERATION_STATUSES
            ):
                continue

            value = _row_text(row)
            if not value or value in seen:
                continue

            seen.add(value)
            history.append(value)

    return history


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_object(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _text_candidate(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_id": str(row["account_id"]),
        "content_type": TEXT_KIND,
        "canary_id": str(row["canary_id"]),
        "queue_id": str(row["queue_id"]),
        "batch_id": str(row["batch_id"]),
        "public_post_text": str(row["public_post_text"]),
        "content_hash": str(row["content_hash"]),
        "primary_topic": str(row["primary_topic"]),
        "structure_variant": str(row["structure_variant"]),
        "quality_gate_version": str(row["quality_gate_version"]),
        "feature_schema_version": str(row.get("feature_schema_version", "")),
        "post_design": _json_object(row.get("post_design_json")),
        "visual_plan": {},
        "visual_text_hash": "",
        "media_files": [],
        "media_content_hashes": [],
        "quality": {
            "status": "PASS",
            "batch_diversity_status": row.get("batch_diversity_status", ""),
            "topic_coherence_status": row.get("topic_coherence_status", ""),
            "topic_confidence": row.get("topic_confidence", ""),
            "hook_topic_match": row.get("hook_topic_match", ""),
            "closing_topic_match": row.get("closing_topic_match", ""),
            "shared_hook_detected": row.get("shared_hook_detected", ""),
            "shared_closing_detected": row.get("shared_closing_detected", ""),
        },
    }


def _media_candidate(spec: dict[str, Any]) -> dict[str, Any]:
    files = [Path(value) for value in spec["files"]]
    kind = str(spec["kind"])
    return {
        "account_id": str(spec["post_design"]["account_id"]),
        "content_type": kind,
        "canary_id": str(spec["canary_id"]),
        "queue_id": f"q_{spec['run_id']}_{kind}",
        "batch_id": str(spec["batch_id"]),
        "public_post_text": str(spec["text"]),
        "content_hash": hashlib.sha256(
            str(spec["text"]).encode("utf-8")
        ).hexdigest(),
        "primary_topic": str(spec["quality"]["primary_topic"]),
        "structure_variant": str(spec["quality"]["structure_variant"]),
        "quality_gate_version": str(spec["quality"]["quality_gate_version"]),
        "feature_schema_version": str(
            spec["alignment"].get("feature_schema_version", "")
        ),
        "post_design": spec["post_design"],
        "visual_plan": spec["visual_plan"],
        "visual_text_hash": str(
            spec["alignment"].get("visual_text_hash", "")
        ),
        "media_files": [str(path) for path in files],
        "media_content_hashes": [_sha(path) for path in files],
        "quality": spec["quality"],
        "alignment": spec["alignment"],
    }


def _manifest_payload(
    batch_id: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized = []
    for item in sorted(
        candidates,
        key=lambda row: (
            str(row["account_id"]),
            str(row["content_type"]),
        ),
    ):
        normalized.append({
            "account_id": item["account_id"],
            "content_type": item["content_type"],
            "canary_id": item["canary_id"],
            "batch_id": item["batch_id"],
            "public_post_text": item["public_post_text"],
            "content_hash": item["content_hash"],
            "primary_topic": item["primary_topic"],
            "structure_variant": str(item["structure_variant"]),
            "quality_gate_version": item["quality_gate_version"],
            "feature_schema_version": item.get(
                "feature_schema_version",
                "",
            ),
            "post_design": item.get("post_design", {}),
            "visual_plan": item.get("visual_plan", {}),
            "visual_text_hash": item.get("visual_text_hash", ""),
            "media_content_hashes": item.get(
                "media_content_hashes",
                [],
            ),
        })
    return {
        "manifest_version": MANIFEST_VERSION,
        "batch_id": batch_id,
        "candidates": normalized,
    }


def _manifest_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _truthy(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {
        "1",
        "true",
        "yes",
        "pass",
    }


def _contract(
    batch_id: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    reasons: list[str] = []

    expected = {
        (account, kind)
        for account in ACCOUNTS
        for kind in REMAINING_TYPES
    }
    actual = {
        (str(row.get("account_id", "")),
         str(row.get("content_type", "")))
        for row in candidates
    }

    if actual != expected:
        reasons.append("exact_remaining_eight_candidate_set_missing")
    if len(candidates) != 8:
        reasons.append("candidate_count_must_equal_eight")
    if {str(row.get("batch_id", "")) for row in candidates} != {batch_id}:
        reasons.append("mixed_batch_ids")
    if len({
        str(row.get("canary_id", ""))
        for row in candidates
    }) != len(candidates):
        reasons.append("duplicate_canary_id")
    if len({
        str(row.get("content_hash", ""))
        for row in candidates
    }) != len(candidates):
        reasons.append("duplicate_public_text_hash")

    account_checks: dict[str, Any] = {}

    for account in ACCOUNTS:
        rows = [
            row for row in candidates
            if row.get("account_id") == account
        ]
        topics = {
            str(row.get("primary_topic", ""))
            for row in rows
        }
        structures = {
            str(row.get("structure_variant", ""))
            for row in rows
        }
        account_reasons: list[str] = []

        if len(rows) != 4:
            account_reasons.append("candidate_count_must_equal_four")
        if len(topics) != 4:
            account_reasons.append("primary_topics_must_be_distinct")
        if len(structures) != 4:
            account_reasons.append("structure_variants_must_be_distinct")

        for row in rows:
            kind = str(row.get("content_type", ""))
            quality = dict(row.get("quality") or {})

            if str(quality.get("status", "")).upper() != "PASS":
                account_reasons.append(f"{kind}:quality_not_pass")
            if str(
                quality.get("batch_diversity_status", "")
            ).upper() != "PASS":
                account_reasons.append(
                    f"{kind}:batch_diversity_not_pass"
                )
            if str(
                quality.get("topic_coherence_status", "")
            ).upper() != "PASS":
                account_reasons.append(
                    f"{kind}:topic_coherence_not_pass"
                )

            if kind in MEDIA_KINDS:
                alignment = dict(row.get("alignment") or {})
                files = [
                    str(value)
                    for value in row.get("media_files", [])
                ]
                hashes = [
                    str(value)
                    for value in row.get(
                        "media_content_hashes",
                        [],
                    )
                ]

                if str(
                    alignment.get("alignment_status", "")
                ).upper() != "PASS":
                    account_reasons.append(
                        f"{kind}:alignment_not_pass"
                    )
                if float(
                    alignment.get("main_claim_coverage", 0)
                ) < 1.0:
                    account_reasons.append(
                        f"{kind}:claim_coverage_incomplete"
                    )
                if int(
                    alignment.get("unsupported_claim_count", 1)
                ) != 0:
                    account_reasons.append(
                        f"{kind}:unsupported_claims"
                    )
                if not _truthy(
                    alignment.get("visual_topic_match")
                ):
                    account_reasons.append(
                        f"{kind}:visual_topic_mismatch"
                    )
                if not _truthy(
                    alignment.get("visual_cta_match")
                ):
                    account_reasons.append(
                        f"{kind}:visual_cta_mismatch"
                    )

                if len(files) != len(hashes) or not files:
                    account_reasons.append(
                        f"{kind}:media_hash_contract_failed"
                    )

                if kind == "direct_carousel":
                    if len(files) < 2 or not all(
                        Path(value).suffix.lower() == ".png"
                        for value in files
                    ):
                        account_reasons.append(
                            "direct_carousel:invalid_media_bundle"
                        )
                elif len(files) != 1 or Path(
                    files[0]
                ).suffix.lower() != ".mp4":
                    account_reasons.append(
                        f"{kind}:expected_one_mp4"
                    )

        account_checks[account] = {
            "status": (
                "PASS" if not account_reasons else "BLOCKED"
            ),
            "topics": sorted(topics),
            "structure_variants": sorted(structures),
            "reasons": sorted(set(account_reasons)),
        }
        reasons.extend(
            f"{account}:{reason}"
            for reason in account_reasons
        )

    media_hashes = [
        value
        for row in candidates
        for value in row.get("media_content_hashes", [])
    ]
    if len(media_hashes) != len(set(media_hashes)):
        reasons.append("duplicate_media_content_hash")

    return {
        "status": "PASS" if not reasons else "BLOCKED",
        "expected_candidate_count": 8,
        "actual_candidate_count": len(candidates),
        "account_checks": account_checks,
        "blocked_reasons": sorted(set(reasons)),
    }


def build_remaining_eight(
    existing: list[dict[str, Any]],
    posted_results: list[dict[str, Any]],
    *,
    batch_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    generation_existing = [
        row for row in existing
        if str(row.get("batch_id", "")) != batch_id
    ]

    text_rows: list[dict[str, Any]] = []
    media_specs: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []

    for account in ACCOUNTS:
        text_result = build_text_rows(
            generation_existing,
            posted_results,
            targets=((account, TEXT_KIND),),
            batch_id=batch_id,
        )
        if (
            text_result.get("status") != "PLAN_ONLY"
            or len(text_result.get("rows", [])) != 1
        ):
            return {
                "status": "TEXT_PREPARATION_BLOCKED",
                "batch_id": batch_id,
                "account_id": account,
                "detail": text_result,
                "would_post": False,
            }

        text_row = dict(text_result["rows"][0])
        text_rows.append(text_row)
        candidates.append(_text_candidate(text_row))

        account_recent = _generation_history(
            account,
            posted_results,
            generation_existing,
        )

        specs = build_specs(
            account,
            output_dir,
            batch_id=batch_id,
            recent_posts=account_recent,
            kinds=MEDIA_KINDS,
            seed_batch_candidates=[text_row],
        )

        if len(specs) != 3:
            return {
                "status": "MEDIA_PREPARATION_BLOCKED",
                "batch_id": batch_id,
                "account_id": account,
                "would_post": False,
            }

        media_specs.extend(specs)
        candidates.extend(
            _media_candidate(spec)
            for spec in specs
        )

    contract = _contract(batch_id, candidates)
    manifest = _manifest_payload(batch_id, candidates)

    return {
        "status": (
            "READY_FOR_REMAINING_EIGHT_APPLY"
            if contract["status"] == "PASS"
            else "REMAINING_EIGHT_CONTRACT_BLOCKED"
        ),
        "batch_id": batch_id,
        "manifest_version": MANIFEST_VERSION,
        "design_manifest_hash": _manifest_hash(manifest),
        "contract": contract,
        "candidates": candidates,
        "manifest": manifest,
        "text_rows": text_rows,
        "media_specs": media_specs,
        "would_write": False,
        "would_upload": False,
        "would_post": False,
    }


def _read_sheets(
    *,
    dry_run: bool,
) -> tuple[Any, list[dict[str, Any]], list[dict[str, Any]]]:
    from config_loader import get_config
    from sheets_client import SheetsClient, TAB_DEFINITIONS

    cfg = get_config()
    client = SheetsClient(
        cfg["sheet_id"],
        cfg["sa_dict"],
        dry_run=dry_run,
    )

    for logical in ("queue", "posted_results"):
        client._ensure_tab(logical, TAB_DEFINITIONS[logical])

    return (
        client,
        client._ws("queue").get_all_records(),
        client._ws("posted_results").get_all_records(),
    )


def _media_ready(row: dict[str, Any], kind: str) -> bool:
    if str(row.get("media_status", "")).upper() not in {
        "ATTACHED",
        "UPLOADED",
    }:
        return False

    if kind == "direct_carousel":
        try:
            urls = json.loads(
                str(row.get("media_urls_json") or "[]")
            )
        except json.JSONDecodeError:
            return False
        return isinstance(urls, list) and len(urls) >= 2 and all(urls)

    return bool(str(row.get("media_url", "")).strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--expected-manifest-hash", default="")
    parser.add_argument("--confirm-remaining-eight", default="")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    if not args.use_sheets:
        result = {
            "status": "BLOCKED",
            "reason": "--use-sheets is required",
            "would_post": False,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    if args.apply and (
        not args.batch_id
        or not args.expected_manifest_hash
        or args.confirm_remaining_eight != CONFIRMATION
    ):
        result = {
            "status": "BLOCKED",
            "reason": (
                "apply requires exact batch id, manifest hash, "
                "and PREPARE_APPROVED_REMAINING_EIGHT"
            ),
            "would_post": False,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    batch_id = args.batch_id or (
        "fresh_remaining_eight_"
        + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    )

    if not re.fullmatch(r"fresh_[A-Za-z0-9_-]+", batch_id):
        result = {
            "status": "BLOCKED",
            "reason": (
                "batch_id_must_start_with_fresh_"
                "and_use_safe_characters"
            ),
            "would_post": False,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    client, existing, posted = _read_sheets(
        dry_run=not args.apply
    )

    result = build_remaining_eight(
        existing,
        posted,
        batch_id=batch_id,
        output_dir=ROOT / "output/system_owned_media",
    )

    text_rows = result.pop("text_rows", [])
    media_specs = result.pop("media_specs", [])

    if (
        result.get("status")
        == "READY_FOR_REMAINING_EIGHT_APPLY"
        and args.apply
    ):
        if (
            result.get("design_manifest_hash")
            != args.expected_manifest_hash
        ):
            result = {
                "status": "MANIFEST_MISMATCH",
                "batch_id": batch_id,
                "expected_manifest_hash": (
                    args.expected_manifest_hash
                ),
                "actual_manifest_hash": result.get(
                    "design_manifest_hash",
                    "",
                ),
                "would_post": False,
            }
        elif os.environ.get(
            "ALLOW_CLOUDINARY_UPLOAD",
            "",
        ).lower() != "true":
            result = {
                "status": "BLOCKED",
                "reason": (
                    "ALLOW_CLOUDINARY_UPLOAD=true required"
                ),
                "would_post": False,
            }
        else:
            media_results = {}
            for account in ACCOUNTS:
                account_specs = [
                    spec
                    for spec in media_specs
                    if spec["post_design"]["account_id"]
                    == account
                ]
                media_results[account] = apply_specs(
                    account_specs,
                    account,
                    upload=True,
                )

            text_result = append_text_rows(
                client,
                text_rows,
            )

            stored = client._ws("queue").get_all_records()
            by_canary = {
                str(row.get("canary_id", "")): row
                for row in stored
            }
            expected = {
                str(candidate["canary_id"])
                for candidate in result["candidates"]
            }
            missing = sorted(
                expected - set(by_canary)
            )
            wrong_batch = sorted(
                canary
                for canary in expected
                if canary in by_canary
                and str(
                    by_canary[canary].get("batch_id", "")
                ) != batch_id
            )
            media_not_ready = sorted(
                str(candidate["canary_id"])
                for candidate in result["candidates"]
                if candidate["content_type"] in MEDIA_KINDS
                and (
                    candidate["canary_id"] not in by_canary
                    or not _media_ready(
                        by_canary[candidate["canary_id"]],
                        candidate["content_type"],
                    )
                )
            )

            success = (
                text_result.get("status") == "APPLIED"
                and all(
                    item.get("status") == "APPLIED"
                    for item in media_results.values()
                )
                and not missing
                and not wrong_batch
                and not media_not_ready
            )

            result.update({
                "status": (
                    "APPLIED"
                    if success
                    else "PARTIAL_FAILURE"
                ),
                "media_registration": media_results,
                "text_registration": text_result,
                "read_after_write": {
                    "status": (
                        "PASS"
                        if (
                            not missing
                            and not wrong_batch
                            and not media_not_ready
                        )
                        else "FAIL"
                    ),
                    "expected_canary_count": 8,
                    "missing_canary_ids": missing,
                    "wrong_batch_canary_ids": wrong_batch,
                    "media_not_ready_canary_ids": (
                        media_not_ready
                    ),
                },
                "would_write": True,
                "would_upload": True,
                "would_post": False,
            })

    if args.output:
        args.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        args.output.write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        result["output_path"] = str(args.output)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    return (
        0
        if result.get("status") in {
            "READY_FOR_REMAINING_EIGHT_APPLY",
            "APPLIED",
        }
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
