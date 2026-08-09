"""Source ownership/provenance helpers for reference-derived content.

Rights to reuse a media object do not imply that the source people, agency,
results, or programs belong to the target account. Unknown relation is treated
as third-party reference by default.
"""
from __future__ import annotations

import re
from typing import Any

OWNED_MARKERS = {
    "owned",
    "owner",
    "internal",
    "first_party",
    "first-party",
    "self",
    "self_owned",
    "company_owned",
    "our_account",
    "system_generated_owned",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _marker(value: Any) -> str:
    return _text(value).lower().replace(" ", "_")


def classify_source_relation(
    source_video: dict[str, Any] | None = None,
    reference_source: dict[str, Any] | None = None,
) -> str:
    video = source_video or {}
    source = reference_source or {}
    values = [
        source.get("source_origin"),
        source.get("source_scope"),
        source.get("source_type"),
        source.get("source_mode"),
        source.get("ownership_status"),
        video.get("source_origin"),
        video.get("source_scope"),
        video.get("source_type"),
        video.get("ownership_status"),
        video.get("rights_status"),
    ]
    if any(_marker(value) in OWNED_MARKERS for value in values):
        return "owned_first_party"
    return "third_party_reference"


def build_source_context(
    source_video: dict[str, Any] | None = None,
    reference_source: dict[str, Any] | None = None,
) -> dict[str, str]:
    video = source_video or {}
    source = reference_source or {}
    return {
        "source_relation": classify_source_relation(video, source),
        "source_name": _text(source.get("source_name") or video.get("author_handle") or video.get("title"))[:160],
        "source_author_handle": _text(video.get("author_handle") or source.get("handle"))[:120],
        "source_origin": _text(source.get("source_origin"))[:80],
        "source_scope": _text(source.get("source_scope"))[:80],
    }


def normalize_source_context(value: dict[str, Any] | None) -> dict[str, str]:
    raw = dict(value or {})
    relation = _text(raw.get("source_relation"))
    if relation not in {"owned_first_party", "third_party_reference"}:
        relation = "third_party_reference"
    return {
        "source_relation": relation,
        "source_name": _text(raw.get("source_name"))[:160],
        "source_author_handle": _text(raw.get("source_author_handle"))[:120],
        "source_origin": _text(raw.get("source_origin"))[:80],
        "source_scope": _text(raw.get("source_scope"))[:80],
    }


# These patterns intentionally target institutional ownership/result claims,
# not simple principle-level agreement such as "we also pay attention to this".
_THIRD_PARTY_SELF_CLAIM_PATTERNS = (
    re.compile(
        r"(?:\u79c1\u305f\u3061|\u50d5\u305f\u3061|\u3046\u3061|\u5f53\u793e|\u5f0a\u793e)"
        r"(?:\u306e\u4e8b\u52d9\u6240|\u306e\u4f1a\u793e|\u306e\u30c1\u30fc\u30e0|\u306e\u6240\u5c5e|\u3067\u306f)"
    ),
    re.compile(
        r"(?:\u79c1\u305f\u3061|\u50d5\u305f\u3061|\u3046\u3061|\u5f53\u793e|\u5f0a\u793e).{0,32}"
        r"(?:\u5b9f\u7e3e|\u9054\u6210|\u58f2\u4e0a|\u30c0\u30a4\u30e4|\u6708\u53ce|\u6240\u5c5e\u30e9\u30a4\u30d0\u30fc|\u6240\u5c5e\u30ad\u30e3\u30b9\u30c8)"
    ),
)



_REFERENCE_BRIDGE_TERMS = (
    "こんな感じで",
    "こういう感じで",
    "こういうの",
    "こういう動き",
    "こういう事例",
    "こういう考え方",
    "この考え方",
    "この部分",
    "この話",
    "この動画",
    "この投稿",
    "見ていると",
    "見てると",
    "参考になる",
    "大事だよね",
    "大事なんだよね",
    "僕たちも",
    "僕も",
    "うちでも",
)


def reference_bridge_signal(text: str, source_context: dict[str, Any] | None) -> dict[str, Any]:
    """Require an explicit reaction/reference cue for third-party commentary.

    This is intentionally broader than one fixed phrase. The goal is to make it
    obvious that the account is reacting to someone else's source instead of
    silently presenting the source as its own achievement.
    """
    ctx = normalize_source_context(source_context)
    if ctx["source_relation"] == "owned_first_party":
        return {"ok": True, "status": "NOT_REQUIRED_OWNED_SOURCE", "hits": []}
    value = str(text or "")
    hits = [term for term in _REFERENCE_BRIDGE_TERMS if term in value]
    return {
        "ok": bool(hits),
        "status": "PASS_REFERENCE_BRIDGE" if hits else "FAIL_REFERENCE_BRIDGE_MISSING",
        "hits": hits,
    }

def validate_source_claims(text: str, source_context: dict[str, Any] | None) -> dict[str, Any]:
    ctx = normalize_source_context(source_context)
    if ctx["source_relation"] == "owned_first_party":
        return {"ok": True, "status": "PASS_OWNED_SOURCE", "matches": []}
    matches: list[str] = []
    for pattern in _THIRD_PARTY_SELF_CLAIM_PATTERNS:
        match = pattern.search(str(text or ""))
        if match:
            matches.append(match.group(0))
    return {
        "ok": not matches,
        "status": "PASS_THIRD_PARTY_COMMENTARY" if not matches else "FAIL_THIRD_PARTY_SELF_CLAIM",
        "matches": matches,
    }



def _auth_bool(value: Any, *, default: bool = False) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "y", "on", "enabled", "active", "allowed", "approved", "granted"}:
        return True
    if raw in {"0", "false", "no", "n", "off", "disabled", "inactive", "blocked", "denied", "rejected"}:
        return False
    return default


def registered_source_authorized(reference_source: dict[str, Any] | None) -> bool:
    """Treat a user-designated active reference source as authorized for clipping/quote review."""
    row = dict(reference_source or {})
    if not str(row.get("source_id") or "").strip():
        return False
    if _auth_bool(row.get("blocked"), default=False):
        return False
    if str(row.get("active") or "").strip() and not _auth_bool(row.get("active"), default=True):
        return False
    return True


def row_belongs_to_registered_source(row: dict[str, Any] | None, reference_source: dict[str, Any] | None) -> bool:
    """Require exact source_id and reject an observable author-handle mismatch."""
    child = dict(row or {})
    ref = dict(reference_source or {})
    if not registered_source_authorized(ref):
        return False
    source_id = str(ref.get("source_id") or "").strip()
    if str(child.get("source_id") or "").strip() != source_id:
        return False
    def norm_handle(value: Any) -> str:
        return str(value or "").strip().lower().lstrip("@").rstrip("/")
    ref_handle = norm_handle(ref.get("handle") or ref.get("author_handle"))
    child_handle = norm_handle(child.get("author_handle"))
    if ref_handle and child_handle and ref_handle != child_handle:
        return False
    return True
