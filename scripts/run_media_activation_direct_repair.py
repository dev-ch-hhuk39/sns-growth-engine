#!/usr/bin/env python3
"""Repair one exact permissioned Direct media item without queue or READY mutation.

The runner binds an operational repair to the exact source post, source-post media
row and preflight manifest hash. Dry-run is read-only. Apply mode delegates only
the exact media ingestion to the existing permission-aware ingester, then proves
that queue and posted-result state did not change.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

ACCOUNTS = ("night_scout", "liver_manager")
ROUTE = "direct_reference_media"
SCHEMA_VERSION = "media_activation_exact_direct_repair_v1"

ALWAYS_FORBIDDEN_TRUE_ENV = (
    "PUBLISH_ENABLED",
    "ALLOW_REAL_X_POST",
    "ALLOW_REAL_THREADS_POST",
    "ALLOW_MEDIA_POSTS",
    "ALLOW_REAL_THREADS_VIDEO_POST",
    "ALLOW_VIDEO_CUT",
    "ALLOW_TRANSCRIPTION_API",
    "GITHUB_MODELS_ENABLED",
    "ENABLE_SENTENCE_TRANSFORMERS",
)

REPAIR_ENV = (
    "ALLOW_VIDEO_DOWNLOAD",
    "ALLOW_CLOUDINARY_UPLOAD",
    "ALLOW_LOCAL_TRANSCRIPTION",
)

PROTECTED_LOGICALS = (
    "queue",
    "posted_results",
)

ID_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{1,240}")
HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _true(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "pass"}


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _validate_identifier(label: str, value: str) -> str:
    text = _text(value)
    if not ID_PATTERN.fullmatch(text):
        raise ValueError(f"invalid_{label}")
    return text


def _validate_hash(label: str, value: str) -> str:
    text = _text(value).lower()
    if not HASH_PATTERN.fullmatch(text):
        raise ValueError(f"invalid_{label}")
    return text


def safety_blockers(
    environ: Mapping[str, str] | None = None,
    *,
    apply: bool,
) -> list[str]:
    source = os.environ if environ is None else environ
    blockers = [
        f"{name}=true"
        for name in ALWAYS_FORBIDDEN_TRUE_ENV
        if _true(source.get(name))
    ]
    if apply:
        blockers.extend(
            f"{name}=not_true"
            for name in REPAIR_ENV
            if not _true(source.get(name))
        )
    else:
        blockers.extend(
            f"{name}=true_in_dry_run"
            for name in REPAIR_ENV
            if _true(source.get(name))
        )
    return blockers


def _manifest_by_account(
    report: Mapping[str, Any],
    account_id: str,
) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in report.get("manifests", [])
        if isinstance(row, Mapping)
        and _text(row.get("account_id")) == account_id
    ]
    if len(rows) != 1:
        raise ValueError(
            f"direct_manifest_account_count_invalid:{account_id}:{len(rows)}"
        )
    return rows[0]


def validate_repair_target(
    report: Mapping[str, Any],
    *,
    account_id: str,
    source_post_id: str,
    source_post_media_id: str,
    expected_manifest_hash: str,
) -> dict[str, Any]:
    account_id = _validate_identifier("account_id", account_id)
    source_post_id = _validate_identifier("source_post_id", source_post_id)
    source_post_media_id = _validate_identifier(
        "source_post_media_id",
        source_post_media_id,
    )
    expected_manifest_hash = _validate_hash(
        "expected_manifest_hash",
        expected_manifest_hash,
    )

    if account_id not in ACCOUNTS:
        raise ValueError(f"unsupported_account_id:{account_id}")
    if _text(report.get("read_status")) != "READ_ONLY_COMPLETE":
        raise ValueError("manifest_not_read_only_complete")
    if _text(report.get("manifest_route")) != ROUTE:
        raise ValueError("manifest_route_mismatch")
    if report.get("planned_external_operations"):
        raise ValueError("manifest_external_operations_present")
    if report.get("executable_commands"):
        raise ValueError("manifest_executable_commands_present")

    safety = report.get("safety")
    if not isinstance(safety, Mapping):
        raise ValueError("manifest_safety_missing")
    unsafe = sorted(
        _text(key)
        for key, value in safety.items()
        if value is not False
    )
    if unsafe:
        raise ValueError("manifest_safety_not_false:" + ",".join(unsafe))

    manifest = _manifest_by_account(report, account_id)
    if _text(manifest.get("manifest_hash")) != expected_manifest_hash:
        raise ValueError("manifest_hash_mismatch")
    if _text(manifest.get("content_route")) != ROUTE:
        raise ValueError("account_manifest_route_mismatch")
    if manifest.get("external_operations"):
        raise ValueError("account_manifest_external_operations_present")
    if manifest.get("executable_commands"):
        raise ValueError("account_manifest_executable_commands_present")

    selected = manifest.get("selected_candidate")
    if not isinstance(selected, Mapping):
        raise ValueError("selected_candidate_missing")
    if _text(selected.get("source_post_id")) != source_post_id:
        raise ValueError("selected_source_post_id_mismatch")

    gate = manifest.get("permission_gate")
    if not isinstance(gate, Mapping):
        raise ValueError("permission_gate_missing")
    if _text(gate.get("status")) != "PASS_ACTIVE_PERMISSION":
        raise ValueError("active_permission_required")
    if gate.get("active_permission_present") is not True:
        raise ValueError("active_permission_boolean_required")
    if gate.get("media_repair_may_begin") is not True:
        raise ValueError("media_repair_not_authorized")
    if gate.get("missing_or_unverified_flags"):
        raise ValueError("permission_scope_incomplete")

    status = _text(manifest.get("manifest_status"))
    if status != "EVIDENCE_REPAIR_SPEC_READY_FOR_HUMAN_REVIEW":
        raise ValueError(f"manifest_not_repairable:{status or 'EMPTY'}")

    steps = [
        dict(step)
        for step in manifest.get("repair_steps", [])
        if isinstance(step, Mapping)
    ]
    if not steps:
        raise ValueError("repair_steps_missing")
    if not any(
        _text(step.get("target_id")) == source_post_media_id
        for step in steps
    ):
        raise ValueError("source_post_media_not_in_repair_manifest")
    if any(
        _text(step.get("status")) != "REVIEWABLE_AFTER_PERMISSION"
        for step in steps
    ):
        raise ValueError("repair_step_not_reviewable")
    if any(step.get("execution_allowed") is not False for step in steps):
        raise ValueError("manifest_execution_flag_not_false")
    if any(_text(step.get("executable_command")) for step in steps):
        raise ValueError("manifest_contains_executable_command")

    return manifest


def fingerprint_rows(rows: Sequence[Mapping[str, Any]]) -> str:
    normalized = [
        dict(row)
        for row in rows
        if isinstance(row, Mapping)
    ]
    normalized.sort(key=_stable_json)
    return _sha(normalized)


def protected_snapshot(
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    missing = [
        logical
        for logical in PROTECTED_LOGICALS
        if logical not in datasets
    ]
    if missing:
        raise ValueError(
            "protected_snapshot_missing:" + ",".join(sorted(missing))
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "fingerprints": {
            logical: fingerprint_rows(datasets[logical])
            for logical in PROTECTED_LOGICALS
        },
        "row_counts": {
            logical: len(
                [
                    row
                    for row in datasets[logical]
                    if isinstance(row, Mapping)
                ]
            )
            for logical in PROTECTED_LOGICALS
        },
    }


def assert_protected_unchanged(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> None:
    for logical in PROTECTED_LOGICALS:
        before_hash = _text(
            before.get("fingerprints", {}).get(logical)
        )
        after_hash = _text(
            after.get("fingerprints", {}).get(logical)
        )
        before_count = before.get("row_counts", {}).get(logical)
        after_count = after.get("row_counts", {}).get(logical)
        if before_hash != after_hash or before_count != after_count:
            raise RuntimeError(f"protected_state_changed:{logical}")


def _read_records(client: Any, logical: str) -> list[dict[str, Any]]:
    from sheets_client import TAB_DEFINITIONS
    from sheets_record_reader import read_records_safely

    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    return [
        dict(row)
        for row in read_records_safely(client, logical)
    ]


def _load_client(*, dry_run: bool) -> Any:
    from config_loader import get_config
    from sheets_client import SheetsClient

    config = get_config()
    return SheetsClient(
        config["sheet_id"],
        config["sa_dict"],
        dry_run=dry_run,
    )


def _load_datasets(
    client: Any,
    logicals: Sequence[str],
) -> dict[str, list[dict[str, Any]]]:
    return {
        logical: _read_records(client, logical)
        for logical in logicals
    }


def resolve_exact_source_rows(
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    account_id: str,
    source_post_id: str,
    source_post_media_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    media_rows = [
        dict(row)
        for row in datasets.get("source_post_media", [])
        if _text(row.get("source_post_media_id"))
        == source_post_media_id
    ]
    if len(media_rows) != 1:
        raise ValueError(
            "source_post_media_count_invalid:"
            f"{source_post_media_id}:{len(media_rows)}"
        )
    media = media_rows[0]
    if _text(media.get("source_post_id")) != source_post_id:
        raise ValueError("source_post_media_parent_mismatch")

    post_rows = [
        dict(row)
        for row in datasets.get("source_posts", [])
        if _text(row.get("source_post_id")) == source_post_id
    ]
    if len(post_rows) != 1:
        raise ValueError(
            f"source_post_count_invalid:{source_post_id}:{len(post_rows)}"
        )
    post = post_rows[0]
    target_account = _text(
        post.get("target_account_id") or post.get("account_id")
    )
    if target_account != account_id:
        raise ValueError("source_post_account_mismatch")
    if _text(post.get("source_id")) == "":
        raise ValueError("source_id_missing")
    if _text(media.get("media_type")).lower() not in {
        "image",
        "video",
    }:
        raise ValueError("unsupported_media_type")
    if not _text(
        media.get("original_media_url")
        or media.get("canonical_post_url")
    ).startswith("https://"):
        raise ValueError("source_media_https_url_required")
    return post, media


def _extract_json_object(output: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    starts = [
        index
        for index, char in enumerate(output)
        if char == "{"
    ]
    for start in reversed(starts):
        try:
            value, end = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            continue
        if output[start + end :].strip():
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError("ingest_json_output_missing")


def run_exact_ingest(
    *,
    account_id: str,
    source_post_media_id: str,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "ingest_direct_reference_media.py"),
        "--source-post-media-id",
        source_post_media_id,
        "--account-id",
        account_id,
        "--max-assets",
        "1",
        "--apply",
        "--confirm-ingest",
    ]
    run = subprocess.run(
        command,
        cwd=ROOT,
        env=dict(os.environ if environ is None else environ),
        text=True,
        capture_output=True,
        timeout=3300,
        check=False,
    )
    if run.returncode:
        raise RuntimeError(
            "exact_ingest_failed:"
            f"exit={run.returncode}:"
            f"stdout_tail={run.stdout[-2000:]}:"
            f"stderr_tail={run.stderr[-2000:]}"
        )
    result = _extract_json_object(run.stdout)
    if _text(result.get("status")) not in {
        "INGESTED_BUNDLE",
        "ALREADY_INGESTED",
    }:
        raise RuntimeError(
            "exact_ingest_unexpected_status:"
            + (_text(result.get("status")) or "EMPTY")
        )
    return result


def validate_post_repair(
    report: Mapping[str, Any],
    *,
    account_id: str,
    source_post_id: str,
    source_post_media_id: str,
) -> dict[str, Any]:
    manifest = _manifest_by_account(report, account_id)
    selected = manifest.get("selected_candidate", {})
    if _text(selected.get("source_post_id")) != source_post_id:
        raise RuntimeError("post_repair_selected_source_changed")
    gate = manifest.get("permission_gate", {})
    if _text(gate.get("status")) != "PASS_ACTIVE_PERMISSION":
        raise RuntimeError("post_repair_permission_not_active")
    remaining = [
        dict(step)
        for step in manifest.get("repair_steps", [])
        if isinstance(step, Mapping)
        and _text(step.get("target_id")) == source_post_media_id
    ]
    if remaining:
        kinds = ",".join(
            sorted(_text(step.get("kind")) for step in remaining)
        )
        raise RuntimeError(
            "target_repair_steps_remaining:" + kinds
        )
    return manifest


def _write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--account-id",
        required=True,
        choices=ACCOUNTS,
    )
    parser.add_argument("--source-post-id", required=True)
    parser.add_argument("--source-post-media-id", required=True)
    parser.add_argument("--expected-manifest-hash", required=True)
    parser.add_argument("--use-sheets", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-repair", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.use_sheets:
        raise SystemExit("--use-sheets is required")
    if args.apply and not args.confirm_repair:
        raise SystemExit("--confirm-repair is required with --apply")
    if args.dry_run and args.confirm_repair:
        raise SystemExit("--confirm-repair is invalid with --dry-run")

    blockers = safety_blockers(apply=args.apply)
    if blockers:
        print(
            json.dumps(
                {
                    "status": "BLOCKED_UNSAFE_ENV",
                    "blocked_reasons": blockers,
                },
                ensure_ascii=False,
            )
        )
        return 1

    account_id = _validate_identifier(
        "account_id",
        args.account_id,
    )
    source_post_id = _validate_identifier(
        "source_post_id",
        args.source_post_id,
    )
    source_post_media_id = _validate_identifier(
        "source_post_media_id",
        args.source_post_media_id,
    )
    expected_manifest_hash = _validate_hash(
        "expected_manifest_hash",
        args.expected_manifest_hash,
    )

    from build_media_activation_direct_repair_manifest import (
        load_production_manifest,
    )

    before_manifest_report = load_production_manifest()
    before_account_manifest = validate_repair_target(
        before_manifest_report,
        account_id=account_id,
        source_post_id=source_post_id,
        source_post_media_id=source_post_media_id,
        expected_manifest_hash=expected_manifest_hash,
    )

    client = _load_client(dry_run=not args.apply)
    datasets = _load_datasets(
        client,
        (
            "source_posts",
            "source_post_media",
            *PROTECTED_LOGICALS,
        ),
    )
    post, media = resolve_exact_source_rows(
        datasets,
        account_id=account_id,
        source_post_id=source_post_id,
        source_post_media_id=source_post_media_id,
    )
    before_protected = protected_snapshot(datasets)

    base_report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PLAN_READY" if args.dry_run else "RUNNING",
        "mode": "dry_run" if args.dry_run else "apply",
        "account_id": account_id,
        "source_post_id": source_post_id,
        "source_post_media_id": source_post_media_id,
        "source_id": _text(post.get("source_id")),
        "platform": _text(post.get("platform")),
        "media_type": _text(media.get("media_type")).lower(),
        "before_manifest_hash": _text(
            before_account_manifest.get("manifest_hash")
        ),
        "before_repair_step_count": len(
            before_account_manifest.get("repair_steps", [])
        ),
        "protected_before": before_protected,
        "ingest_result": {},
        "after_manifest_hash": "",
        "after_manifest_status": "",
        "after_repair_step_count": "",
        "effects": {
            "production_write": args.apply,
            "sheets_write": args.apply,
            "permission_mutation": False,
            "media_download": args.apply,
            "media_cut": False,
            "media_upload": args.apply,
            "caption_generation": False,
            "queue_write": False,
            "ready_transition": False,
            "workflow_dispatch": False,
            "sns_post": False,
        },
    }

    if args.dry_run:
        base_report["report_hash"] = _sha(base_report)
        _write_report(args.output, base_report)
        print("=== MEDIA ACTIVATION EXACT DIRECT REPAIR ===")
        print("STATUS=PLAN_READY")
        print(f"ACCOUNT_ID={account_id}")
        print(f"SOURCE_POST_ID={source_post_id}")
        print(f"SOURCE_POST_MEDIA_ID={source_post_media_id}")
        print(
            "EXPECTED_MANIFEST_HASH="
            + expected_manifest_hash
        )
        print(
            "REPAIR_STEP_COUNT="
            + str(base_report["before_repair_step_count"])
        )
        print(f"REPORT={args.output}")
        print("PASS: exact candidate and active permission verified")
        print("PASS: dry-run performed no write or media operation")
        return 0

    ingest_result = run_exact_ingest(
        account_id=account_id,
        source_post_media_id=source_post_media_id,
    )

    after_client = _load_client(dry_run=True)
    after_datasets = _load_datasets(
        after_client,
        PROTECTED_LOGICALS,
    )
    after_protected = protected_snapshot(after_datasets)
    assert_protected_unchanged(
        before_protected,
        after_protected,
    )

    after_manifest_report = load_production_manifest()
    after_account_manifest = validate_post_repair(
        after_manifest_report,
        account_id=account_id,
        source_post_id=source_post_id,
        source_post_media_id=source_post_media_id,
    )

    base_report.update(
        {
            "status": "REPAIR_COMPLETE",
            "ingest_result": ingest_result,
            "protected_after": after_protected,
            "after_manifest_hash": _text(
                after_account_manifest.get("manifest_hash")
            ),
            "after_manifest_status": _text(
                after_account_manifest.get("manifest_status")
            ),
            "after_repair_step_count": len(
                after_account_manifest.get("repair_steps", [])
            ),
        }
    )
    base_report["report_hash"] = _sha(base_report)
    _write_report(args.output, base_report)

    print("=== MEDIA ACTIVATION EXACT DIRECT REPAIR ===")
    print("STATUS=REPAIR_COMPLETE")
    print(f"ACCOUNT_ID={account_id}")
    print(f"SOURCE_POST_ID={source_post_id}")
    print(f"SOURCE_POST_MEDIA_ID={source_post_media_id}")
    print(
        "INGEST_STATUS="
        + _text(ingest_result.get("status"))
    )
    print(
        "AFTER_MANIFEST_STATUS="
        + base_report["after_manifest_status"]
    )
    print(
        "AFTER_REPAIR_STEP_COUNT="
        + str(base_report["after_repair_step_count"])
    )
    print(f"REPORT={args.output}")
    print("PASS: exact permissioned media repair completed")
    print("PASS: queue and posted results remained unchanged")
    print("PASS: no READY transition or SNS post")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
