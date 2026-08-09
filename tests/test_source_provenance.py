from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from generation.source_provenance import build_source_context, classify_source_relation, reference_bridge_signal, registered_source_authorized, row_belongs_to_registered_source, validate_source_claims


def test_unknown_source_defaults_to_third_party() -> None:
    assert classify_source_relation({}, {}) == "third_party_reference"


def test_explicit_owned_marker_allows_first_party_relation() -> None:
    assert classify_source_relation({"rights_status": "owned"}, {}) == "owned_first_party"
    assert classify_source_relation({}, {"source_origin": "first_party"}) == "owned_first_party"


def test_third_party_institutional_self_claim_is_blocked() -> None:
    text = "\u79c1\u305f\u3061\u306e\u4e8b\u52d9\u6240\u3067\u306f\u3053\u306e\u65b9\u6cd5\u3092\u5b9f\u65bd\u3057\u3066\u3044\u307e\u3059"
    result = validate_source_claims(text, {"source_relation": "third_party_reference"})
    assert result["ok"] is False
    assert result["status"] == "FAIL_THIRD_PARTY_SELF_CLAIM"


def test_third_party_principle_level_agreement_is_allowed() -> None:
    text = "\u3053\u306e\u8003\u3048\u65b9\u306f\u672c\u5f53\u306b\u5927\u4e8b\u3002\u50d5\u305f\u3061\u3082\u3053\u3053\u306f\u610f\u8b58\u3057\u3066\u308b\u3002"
    result = validate_source_claims(text, {"source_relation": "third_party_reference"})
    assert result["ok"] is True


def test_source_context_does_not_infer_ownership_from_reuse_permission() -> None:
    ctx = build_source_context(
        {"rights_status": "allowed", "author_handle": "other_agency"},
        {"source_origin": "curated_reference", "source_name": "Other Agency"},
    )
    assert ctx["source_relation"] == "third_party_reference"


def test_third_party_reference_bridge_is_explicit_but_not_one_fixed_phrase() -> None:
    ctx = {"source_relation": "third_party_reference"}
    assert reference_bridge_signal("こういう事例を見ると、ここは本当に大事だよね。", ctx)["ok"] is True
    assert reference_bridge_signal("僕たちもここは意識してる。", ctx)["ok"] is True
    assert reference_bridge_signal("配信ではコメント設計が重要です。", ctx)["ok"] is False


def test_registered_reference_source_inherits_user_authorization() -> None:
    ref = {"source_id": "src-1", "active": "true", "blocked": "false", "handle": "@creator"}
    assert registered_source_authorized(ref) is True
    assert row_belongs_to_registered_source({"source_id": "src-1", "author_handle": "creator"}, ref) is True


def test_registered_source_does_not_authorize_obvious_third_party_repost() -> None:
    ref = {"source_id": "src-1", "active": "true", "blocked": "false", "handle": "@creator"}
    assert row_belongs_to_registered_source({"source_id": "src-1", "author_handle": "someone_else"}, ref) is False
    assert registered_source_authorized({"source_id": "src-1", "blocked": "true"}) is False
