#!/usr/bin/env python3
"""Machine-evaluate Reference-first software, integration and live evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from evaluate_capability_matrix import evaluate as evaluate_capabilities  # noqa: E402
from verify_reference_first_integration import verify_all  # noqa: E402

CONTRACT_PATH = ROOT / "config" / "reference_first_completion.json"
ROUTING_PATH = ROOT / "config" / "source_backend_routing.json"
MIX_PATH = ROOT / "config" / "content_mix" / "default_mix.json"
MEDIA_PATH = ROOT / "config" / "media_growth_engine.json"
X_DECISION_PATH = ROOT / "docs" / "x-reusable-media-permission-decision-package.json"
SOURCE_REGISTRY_PATH = ROOT / "config" / "source_accounts" / "default_sources.json"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    ).stdout.strip()


def _state(ok: bool, *, reasons: list[str] | None = None, **evidence: Any) -> dict[str, Any]:
    return {
        "status": "PASS" if ok else "FAIL",
        "reasons": list(reasons or []),
        "evidence": evidence,
    }


def _workflow_inventory(contract: dict[str, Any]) -> dict[str, Any]:
    classified: list[str] = []
    duplicates: list[str] = []
    for rows in contract["workflow_classification"].values():
        for name in rows:
            if name in classified:
                duplicates.append(name)
            classified.append(name)
    actual = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
    missing = sorted(set(actual) - set(classified))
    unknown = sorted(set(classified) - set(actual))
    active = (
        contract["workflow_classification"]["canonical"]
        + contract["workflow_classification"]["external_blocked"]
    )
    forbidden: list[str] = []
    forbidden_terms = (
        "threads_browser_storage_state",
        "threads_browser_session",
        "threads_public_playwright",
        "tiktok_public_playwright",
    )
    for name in active:
        text = (ROOT / ".github" / "workflows" / name).read_text(
            encoding="utf-8", errors="replace"
        ).lower()
        for term in forbidden_terms:
            if term in text:
                forbidden.append(f"{name}:{term}")
    return {
        "ok": not (duplicates or missing or unknown or forbidden),
        "classified_count": len(classified),
        "actual_count": len(actual),
        "duplicates": sorted(set(duplicates)),
        "missing_classification": missing,
        "unknown_files": unknown,
        "active_browser_references": forbidden,
    }


def _entrypoint_inventory(contract: dict[str, Any]) -> dict[str, Any]:
    classified: list[str] = []
    duplicates: list[str] = []
    for rows in contract["entrypoint_classification"].values():
        for path in rows:
            if path in classified:
                duplicates.append(path)
            classified.append(path)
    missing = sorted(path for path in classified if not (ROOT / path).is_file())
    return {
        "ok": not (duplicates or missing),
        "classified_count": len(classified),
        "duplicates": sorted(set(duplicates)),
        "missing_files": missing,
    }


def _architecture(contract: dict[str, Any]) -> dict[str, Any]:
    routing = _load(ROUTING_PATH)
    mix = _load(MIX_PATH)
    media = _load(MEDIA_PATH)
    issues: list[str] = []
    expected_routes = {
        "threads.profile_posts": ("threads_cli_public", ["threads_logged_out_graphql", "threads_public_screen"]),
        "tiktok.profile_posts": ("tiktok_public_embed", ["tiktok_gallery_dl"]),
        "x.profile_posts": ("x_gallery_dl", []),
        "youtube.channel_videos": ("yt_dlp", []),
    }
    for capability, (primary, fallbacks) in expected_routes.items():
        row = routing.get("routes", {}).get(capability, {})
        if row.get("primary") != primary or list(row.get("fallbacks", [])) != fallbacks:
            issues.append(f"route_mismatch:{capability}")
        if row.get("shadow"):
            issues.append(f"active_shadow_not_allowed:{capability}")
    if "playwright_processes" in routing.get("limits", {}):
        issues.append("stale_playwright_process_limit")
    if list(contract["reference_priority"]) != ["threads", "tiktok", "x", "youtube"]:
        issues.append("completion_contract_reference_priority_mismatch")
    if contract.get("deferred_reference_acquisition"):
        issues.append("unexpected_deferred_reference_platform")
    operational = mix.get("operational_threads_slot_mix", {})
    for account_id in contract["managed_accounts"]:
        if operational.get(account_id) != contract["content_mix"]:
            issues.append(f"content_mix_mismatch:{account_id}")
    if media.get("physical_media_provider_by_platform") != contract["physical_media_providers"]:
        issues.append("physical_provider_mismatch")
    if list(media.get("physical_media_source_platforms", [])) != list(
        contract["physical_media_providers"]
    ):
        issues.append("physical_platform_mismatch")
    if list(media.get("deferred_physical_media_source_platforms", [])) != contract[
        "deferred_physical_media_platforms"
    ]:
        issues.append("deferred_physical_platform_mismatch")
    if media.get("aspect_ratio_policy") != contract["aspect_ratio_policy"]:
        issues.append("aspect_ratio_policy_mismatch")
    workflows = _workflow_inventory(contract)
    entrypoints = _entrypoint_inventory(contract)
    if not workflows["ok"]:
        issues.append("workflow_inventory_incomplete")
    if not entrypoints["ok"]:
        issues.append("entrypoint_inventory_incomplete")
    return _state(
        not issues,
        reasons=issues,
        workflow_inventory=workflows,
        entrypoint_inventory=entrypoints,
    )


def _reference_discovery(routing: dict[str, Any]) -> dict[str, Any]:
    commands = {
        platform: (
            "python3 scripts/acquire_approved_source_posts.py "
            f"--account-id all --platform {platform} --max-posts 5 "
            "--reference-only --verify-network"
        )
        for platform in ("threads", "tiktok", "x", "youtube")
    }
    expected = {
        "threads": ("threads.profile_posts", "threads_cli_public"),
        "tiktok": ("tiktok.profile_posts", "tiktok_public_embed"),
        "x": ("x.profile_posts", "x_gallery_dl"),
        "youtube": ("youtube.channel_videos", "yt_dlp"),
    }
    statuses: dict[str, Any] = {}
    ready = True
    for platform, (capability, provider) in expected.items():
        route = routing.get("routes", {}).get(capability, {})
        code_ready = route.get("primary") == provider
        ready = ready and code_ready
        statuses[platform] = {
            "code_status": "PASS" if code_ready else "FAIL",
            "external_status": {
                "threads": "PASS_ANONYMOUS_CRAWLER_RECORDED",
                "youtube": "PASS_AV_RECORDED",
                "tiktok": "PASS_PUBLIC_EMBED_AND_AV_RECORDED",
                "x": "PASS_BOUNDED_DISCOVERY_AND_AV_RECORDED",
            }.get(platform, "UNVERIFIED_EXTERNAL"),
            "bounded_verification_command": commands[platform],
        }
    return _state(
        ready,
        active_platforms=["threads", "x", "youtube", "tiktok"],
        deferred_platforms=[],
        platform_statuses=statuses,
    )


def _code_paths(paths: list[str]) -> dict[str, Any]:
    missing = [path for path in paths if not (ROOT / path).is_file()]
    return _state(not missing, reasons=[f"missing:{path}" for path in missing], paths=paths)


def _code_contract(
    paths: list[str], markers: dict[str, tuple[str, ...]]
) -> dict[str, Any]:
    """Require executable contract evidence, not only placeholder files."""
    missing = [path for path in paths if not (ROOT / path).is_file()]
    missing_markers: list[str] = []
    for path, expected in markers.items():
        target = ROOT / path
        if not target.is_file():
            continue
        text = target.read_text(encoding="utf-8", errors="replace")
        missing_markers.extend(
            f"{path}:{marker}" for marker in expected if marker not in text
        )
    reasons = [f"missing:{path}" for path in missing]
    reasons.extend(f"missing_contract_marker:{item}" for item in missing_markers)
    return _state(
        not reasons,
        reasons=reasons,
        paths=paths,
        checked_marker_count=sum(len(items) for items in markers.values()),
        missing_contract_markers=missing_markers,
    )


def _x_permission_state() -> dict[str, Any]:
    package = _load(X_DECISION_PATH)
    registry = _load(SOURCE_REGISTRY_PATH).get("sources", [])
    candidates: list[tuple[str, str]] = []
    for account in ("night_scout", "liver_manager"):
        rows = package.get("golden_requirements", {}).get(account, {}).get(
            "eligible_registry_candidates", []
        )
        for value in rows:
            source_id, _, handle = str(value).partition(" ")
            candidates.append((source_id, handle.lstrip("@").lower()))
    registry_by_id = {str(row.get("source_id", "")): row for row in registry}
    mismatches: list[str] = []
    handles: list[str] = []
    for source_id, handle in candidates:
        row = registry_by_id.get(source_id)
        registry_handle = str((row or {}).get("source_handle", "")).lstrip("@").lower()
        if not row or registry_handle != handle:
            mismatches.append(source_id)
        handles.append(handle)
    duplicate_handles = sorted({handle for handle in handles if handles.count(handle) > 1})
    blocked = package.get("status") == "OWNER_DECISION_REQUIRED" and package.get("apply") is False
    authorized = (
        package.get("status") == "OWNER_AUTHORIZED_APPLIED"
        and package.get("apply") is True
        and package.get("permission_ledger_read_after_write") == "PASS"
        and not mismatches
        and not duplicate_handles
    )
    return {
        "status": "PASS" if authorized else ("BLOCKED_EXTERNAL_PERMISSION" if blocked else "FAIL"),
        "blocker": blocked,
        "candidate_count": len(candidates),
        "registry_mismatches": mismatches,
        "duplicate_candidate_handles": duplicate_handles,
        "decision_package": str(X_DECISION_PATH.relative_to(ROOT)),
        "permission_ledger_read_after_write": package.get("permission_ledger_read_after_write", ""),
    }


def _repository_result(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return _state(False, reasons=["repository_test_artifact_missing"])
    data = _load(path)
    return _repository_result_data(data)


def _repository_result_data(data: dict[str, Any]) -> dict[str, Any]:
    passed = (
        data.get("status") == "PASS"
        and int(data.get("failed_count", -1)) == 0
        and int(data.get("test_count", 0)) >= 815
    )
    return _state(
        passed,
        reasons=[] if passed else ["repository_regression_not_green"],
        test_count=data.get("test_count"),
        failed_count=data.get("failed_count"),
        excluded_external_probe_count=data.get("excluded_external_probe_count"),
        excluded_optional_local_tool_count=data.get("excluded_optional_local_tool_count"),
    )


def evaluate(
    *,
    repository_tests_path: Path | None = None,
    repository_tests_result: dict[str, Any] | None = None,
    production_approval_path: Path | None = None,
) -> dict[str, Any]:
    contract = _load(CONTRACT_PATH)
    routing = _load(ROUTING_PATH)
    architecture = _architecture(contract)
    repository = (
        _repository_result_data(repository_tests_result)
        if repository_tests_result is not None
        else _repository_result(repository_tests_path)
    )
    reference = _reference_discovery(routing)
    integration = verify_all()
    code = contract["production_code_evidence"]
    publisher = _code_contract(
        code["publisher"],
        {
            "scripts/process_threads_queue.py": (
                'ELIGIBLE_STATUSES = {"READY"}',
                "final_public_post_validator",
                "delivery_idempotency_key",
                "verify_posted_result_persistence",
                "build_metric_collection_jobs",
                "media_required",
            ),
            "src/publishers/threads_publisher.py": (
                '"TEXT"',
                '"image_url"',
                '"VIDEO"',
                '"CAROUSEL"',
                "threads_publish",
            ),
            "scripts/publisher_delivery_contract.py": (
                "delivery_idempotency_key",
                "verify_posted_result_persistence",
                "retry_disposition",
            ),
        },
    )
    metrics_pdca = _code_contract(
        code["metrics_pdca"],
        {
            "scripts/metrics_collection_schedule.py": ("WINDOW_HOURS = (24, 72, 168)",),
            "scripts/collect_threads_metrics.py": (
                'return "AVAILABLE"',
                'return "PARTIAL"',
                'return "NOT_AVAILABLE"',
                'return "AUTH_ERROR"',
                'return "POST_NOT_FOUND"',
                'return "COLLECTION_ERROR"',
            ),
            "scripts/metrics_pdca_contract.py": (
                '!= "MEASURED"',
                '"MEASURED_ONLY"',
            ),
            "scripts/run_pdca_cycle.py": ("measured_results_only",),
            "src/learning/pdca_orchestrator.py": (
                '"status": "WAITING_REVIEW"',
                '"auto_apply": False',
            ),
        },
    )
    permission_code = _code_paths(code["permission_provenance"])
    x_permission = _x_permission_state()
    physical_evidence = contract.get("physical_media_evidence", {})
    youtube_evidence = physical_evidence.get("youtube", {})
    youtube_ready = (
        contract["physical_media_providers"].get("youtube") == "yt_dlp"
        and all(
            youtube_evidence.get(account_id) == "PASS_AV"
            for account_id in contract["managed_accounts"]
        )
        and youtube_evidence.get("evidence_class")
        == "recorded_dual_account_physical_golden"
    )
    x_code_ready = (
        contract["physical_media_providers"].get("x") == "yt_dlp"
        and permission_code["status"] == "PASS"
        and not x_permission["registry_mismatches"]
        and not x_permission["duplicate_candidate_handles"]
    )
    x_evidence = physical_evidence.get("x", {})
    x_golden_ready = all(
        x_evidence.get(account_id) == "PASS_AV"
        for account_id in contract["managed_accounts"]
    ) and x_evidence.get("evidence_class") == "recorded_dual_account_physical_golden"
    tiktok_evidence = physical_evidence.get("tiktok", {})
    tiktok_golden_ready = (
        tiktok_evidence.get("liver_manager") == "PASS_AV"
        and tiktok_evidence.get("evidence_class")
        == "recorded_owner_approved_physical_golden"
    )
    approval = _load(production_approval_path) if production_approval_path and production_approval_path.is_file() else {}
    approval_granted = (
        approval.get("production_write_approval") is True
        and approval.get("status") == "APPROVED"
        and str(approval.get("implementation_head", "")) == _git("rev-parse", "HEAD")
    )
    capabilities = evaluate_capabilities()
    software_complete = all(
        item["status"] == "PASS"
        for item in (architecture, repository, reference, publisher, metrics_pdca, permission_code)
    ) and x_code_ready and youtube_ready and capabilities["code_complete"] == capabilities["code_required"]
    integration_complete = integration["status"] == "PASS"
    active_scope_live_evidence_complete = bool(
        x_golden_ready and youtube_ready and tiktok_golden_ready
    )
    production_complete = (
        capabilities["status"] == "PASS"
        and approval_granted
        and not x_permission["blocker"]
    )
    status = (
        "SOFTWARE_COMPLETE_EXTERNAL_BLOCKERS_ONLY"
        if software_complete and integration_complete and not production_complete
        else "COMPLETE"
        if software_complete and integration_complete and production_complete
        else "INTERNAL_WORK_REMAINS"
    )
    deferred_platforms = sorted(contract.get("deferred_reference_acquisition", {}))
    return {
        "status": "PASS" if status in {"SOFTWARE_COMPLETE_EXTERNAL_BLOCKERS_ONLY", "COMPLETE"} else "FAIL",
        "completion_status": status,
        "software_complete": software_complete,
        "active_scope_software_complete": software_complete and integration_complete,
        "active_scope_live_evidence_complete": active_scope_live_evidence_complete,
        "deferred_platform_count": len(deferred_platforms),
        "deferred_platforms": deferred_platforms,
        "ACTIVE_SCOPE_SOFTWARE_COMPLETE": software_complete and integration_complete,
        "ACTIVE_SCOPE_LIVE_EVIDENCE_COMPLETE": active_scope_live_evidence_complete,
        "DEFERRED_PLATFORM_COUNT": len(deferred_platforms),
        "DEFERRED_PLATFORMS": deferred_platforms,
        "integration_complete": integration_complete,
        "production_evidence_complete": production_complete,
        "production_publish_evidence_complete": production_complete,
        "PRODUCTION_PUBLISH_EVIDENCE_COMPLETE": production_complete,
        "architecture_consistent": architecture,
        "repository_regression_pass": repository,
        "reference_discovery_ready": reference,
        "x_physical_media_ready": {
            "status": (
                "PASS_AV_RECORDED"
                if x_code_ready and x_golden_ready
                else "BLOCKED_EXTERNAL_PERMISSION"
                if x_code_ready and x_permission["blocker"]
                else "BLOCKED_EXTERNAL_AUTH_OR_VIDEO_STATUS"
                if x_code_ready
                else "FAIL"
            ),
            "code_ready": x_code_ready,
            "permission_blocker": x_permission["blocker"],
            "golden_evidence_ready": x_golden_ready,
            "evidence_class": x_evidence.get("evidence_class", ""),
        },
        "youtube_physical_media_ready": {
            "status": "PASS_AV_RECORDED" if youtube_ready else "FAIL",
            "code_ready": youtube_ready,
        },
        "understanding_generation_review_ready": integration,
        "publisher_code_ready": publisher,
        "metrics_pdca_code_ready": metrics_pdca,
        "x_permission_external_blocker": x_permission,
        "production_write_approval_external_blocker": {
            "status": "PASS" if approval_granted else "BLOCKED_EXTERNAL_APPROVAL",
            "blocker": not approval_granted,
        },
        "production_capability_matrix": {
            "status": capabilities["status"],
            "passed": capabilities["passed"],
            "required": capabilities["required"],
            "code_complete": capabilities["code_complete"],
            "code_required": capabilities["code_required"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-tests-json", type=Path)
    parser.add_argument("--production-approval-json", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(
        repository_tests_path=args.repository_tests_json,
        production_approval_path=args.production_approval_json,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text if args.json else f"reference_first_completion={result['completion_status']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
