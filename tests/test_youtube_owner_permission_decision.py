from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/seed_owner_attested_media_permissions.py"
SPEC = importlib.util.spec_from_file_location("owner_permission_seed", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_youtube_owner_decision_is_exactly_two_registered_identities() -> None:
    path = ROOT / "config/youtube_source_permissions_20260811.json"
    decision = module.load_owner_decision(path)
    selected = module.decision_sources(decision)
    assert {(row["source_id"], row["source_handle"], row["account_id"]) for row in selected} == {
        ("src_ns_yt_cand_006", "@ichijo_hibiki", "night_scout"),
        ("src_lm_yt_cand_001", "@suu-san_pococha", "liver_manager"),
    }
    assert all((row.get("source_platform") or row.get("platform")) == "youtube" for row in selected)


def test_youtube_permission_rows_enable_required_scope_without_expiry() -> None:
    decision = module.load_owner_decision(ROOT / "config/youtube_source_permissions_20260811.json")
    rows = [module.permission_row(source, "2026-08-11T12:00:00+09:00", decision) for source in module.decision_sources(decision)]
    for row in rows:
        assert all(module.truthy(row[flag]) for flag in module.DECISION_REQUIRED_FLAGS)
        assert row["rights_status"] == "approved_creator_clip"
        assert row["permission_status"] == "approved"
        assert row["allowed_platforms"] == "threads"
        assert row["expires_at"] == ""
        assert "exact two YouTube source accounts" in row["evidence_reference"]


def test_decision_does_not_generalize_to_another_youtube_source() -> None:
    decision = json.loads((ROOT / "config/youtube_source_permissions_20260811.json").read_text())
    try:
        module.decision_sources(decision, {"src_ns_yt_cand_001"})
    except ValueError as exc:
        assert str(exc) == "requested_source_not_in_decision:src_ns_yt_cand_001"
    else:
        raise AssertionError("unlisted YouTube source must not receive permission")
