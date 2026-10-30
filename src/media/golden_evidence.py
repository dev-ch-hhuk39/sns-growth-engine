"""Pure identity and existing semantic-proof checks for physical Goldens.

The caller must select one local artifact, compute its actual SHA256, and
separately evaluate the latest permission ledger. These checks grant no rights
and do not authenticate arbitrarily fabricated metadata or analysis files.
No filesystem, provider, network, generation or publishing operation occurs.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from acquisition.x_exact_status import validate_exact_status_provenance
from generation.content_quality_v2 import understand_media_contract
from generation.media_platform_policy import OWNER_REFERENCE_ACCOUNTS, is_retired_source

_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
_HANDLE = re.compile(r"[A-Za-z0-9_.-]+\Z")
_CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_X_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
_YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _handle(value: Any) -> str:
    return _text(value).lstrip("@").lower()


def _true(value: Any) -> bool:
    return value is True or (type(value) is int and value == 1) or (
        isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"})


def _decision(reasons: list[str], **fields: Any) -> dict[str, Any]:
    return {"status": "BLOCKED" if reasons else "PASS", "reasons": sorted(set(reasons)), **fields}


def _url_parts(value: Any):
    try:
        parts = urlsplit(_text(value))
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.port not in (None, 443)):
            return None
        return parts
    except ValueError:
        return None


def _identity(value: Any) -> dict[str, str]:
    parts = _url_parts(value)
    if not parts:
        return {}
    host = parts.hostname.lower()
    if host in _X_HOSTS:
        match = re.fullmatch(r"/([A-Za-z0-9_]+)/status/(\d+)(?:/video/[1-9]\d*)?/?", parts.path)
        if match:
            handle, external = match.group(1).lower(), match.group(2)
            return {"platform": "x", "external_post_id": external, "source_handle": handle,
                    "canonical_url": f"https://x.com/{handle}/status/{external}"}
    if host in _YT_HOSTS:
        external = ""
        if host in {"youtu.be", "www.youtu.be"}:
            external = parts.path.strip("/")
        elif parts.path.rstrip("/") == "/watch":
            values = parse_qs(parts.query).get("v", [])
            external = values[0] if len(values) == 1 else ""
        else:
            match = re.fullmatch(r"/shorts/([A-Za-z0-9_-]{11})/?", parts.path)
            external = match.group(1) if match else ""
        if _VIDEO_ID.fullmatch(external):
            return {"platform": "youtube", "external_post_id": external, "source_handle": "",
                    "canonical_url": f"https://www.youtube.com/watch?v={external}"}
    return {}


def _profile(value: Any) -> dict[str, str]:
    parts = _url_parts(value)
    if not parts:
        return {}
    host, path = parts.hostname.lower(), unquote(parts.path).rstrip("/")
    if host in _X_HOSTS:
        match = re.fullmatch(r"/([A-Za-z0-9_]+)", path)
        if match:
            return {"platform": "x", "handle": match.group(1).lower(), "channel_id": ""}
    if host in _YT_HOSTS - {"youtu.be", "www.youtu.be"}:
        match = re.fullmatch(r"/@([^/]+)(?:/(?:videos|shorts|streams))?", path)
        if match and _HANDLE.fullmatch(match.group(1)):
            return {"platform": "youtube", "handle": match.group(1).lower(), "channel_id": ""}
        match = re.fullmatch(r"/channel/(UC[A-Za-z0-9_-]{22})(?:/(?:videos|shorts|streams))?", path)
        if match:
            return {"platform": "youtube", "handle": "", "channel_id": match.group(1)}
    return {}


def validate_registered_binding(item: Mapping[str, Any], registry_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Bind an individual X/YouTube post to one active registered owner source."""
    if not isinstance(item, Mapping):
        return _decision(["golden_item_invalid"], binding={})
    account, source_id = _text(item.get("account_id")), _text(item.get("source_id"))
    identity = _identity(item.get("url") or item.get("canonical_url"))
    reasons: list[str] = []
    if account not in OWNER_REFERENCE_ACCOUNTS:
        reasons.append("golden_account_not_managed")
    if not source_id:
        reasons.append("registered_source_id_required")
    if not identity:
        reasons.append("individual_x_or_youtube_url_required")
    declared = _text(item.get("platform"))
    if declared and declared != identity.get("platform"):
        reasons.append("golden_platform_mismatch")
    rows = [row for row in registry_rows if isinstance(row, Mapping) and _text(row.get("source_id")) == source_id]
    if len(rows) != 1:
        return _decision([*reasons, "registered_source_missing_or_ambiguous"], binding={})
    source = rows[0]
    if not _true(source.get("active")) or _true(source.get("blocked")):
        reasons.append("registered_source_inactive_or_blocked")
    if is_retired_source(dict(source)):
        reasons.append("registered_source_retired")
    targets = source.get("target_account_ids")
    if targets is None:
        targets = [source.get("target_account_id")]
    if not isinstance(targets, list) or account not in targets:
        reasons.append("registered_source_account_mismatch")
    profile_url = _text(source.get("canonical_url") or source.get("source_url"))
    profile = _profile(profile_url)
    platform = _text(source.get("source_platform") or source.get("platform"))
    platform = {"youtube_shorts": "youtube", "youtube_streams": "youtube",
                "youtube_playlist": "youtube"}.get(platform, platform)
    if not profile or platform != identity.get("platform") or profile.get("platform") != platform:
        reasons.append("registered_source_platform_or_profile_mismatch")
    registered_handle = _handle(source.get("source_handle")) or profile.get("handle", "")
    if profile.get("handle") and registered_handle != profile["handle"]:
        reasons.append("registered_source_handle_mismatch")
    if _handle(item.get("source_handle")) != registered_handle:
        reasons.append("golden_source_handle_mismatch")
    if identity.get("platform") == "x" and identity.get("source_handle") != registered_handle:
        reasons.append("registered_post_author_mismatch")
    channel_id = _text(source.get("channel_id")) or profile.get("channel_id", "")
    if channel_id and (not _CHANNEL_ID.fullmatch(channel_id)
                       or (profile.get("channel_id") and channel_id != profile["channel_id"])):
        reasons.append("registered_channel_id_mismatch")
    binding = {**identity, "account_id": account, "source_id": source_id,
               "source_handle": registered_handle, "registered_profile_url": profile_url,
               "registered_channel_id": channel_id}
    return _decision(reasons, binding=binding if not reasons else {})


def validate_metadata_provenance(binding: Mapping[str, Any], metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Require extracted post and author fields, never request-URL echoes alone."""
    if not isinstance(binding, Mapping) or not isinstance(metadata, Mapping) or not metadata:
        return _decision(["extracted_metadata_missing"])
    identity = _identity(binding.get("canonical_url"))
    if (not identity or identity.get("platform") != binding.get("platform")
            or identity.get("external_post_id") != binding.get("external_post_id")):
        return _decision(["golden_binding_identity_invalid"])
    reasons: list[str] = []
    expected_handle, external = _handle(binding.get("source_handle")), identity["external_post_id"]
    page_value = _text(metadata.get("webpage_url"))
    page = _identity(page_value)
    if page_value and (not page or page["canonical_url"] != identity["canonical_url"]):
        reasons.append("extracted_webpage_identity_mismatch")
    if identity["platform"] == "x":
        formats = metadata.get("formats")
        if not isinstance(formats, list):
            reasons.append("extracted_video_formats_invalid")
            formats = []
        legacy = validate_exact_status_provenance(identity["canonical_url"],
            {"source_handle": expected_handle}, {**metadata, "formats": formats})
        reasons.extend(legacy["reasons"])
        if _text(metadata.get("display_id")) != external:
            reasons.append("extracted_post_identity_missing_or_mismatch")
        authors = [_handle(metadata.get(key)) for key in ("uploader_id", "author_handle")
                   if _text(metadata.get(key))]
        if not authors and _text(metadata.get("channel_id")):
            authors.append(_handle(metadata["channel_id"]))
        if not authors:
            reasons.append("extracted_author_identity_missing")
        elif any(author != expected_handle for author in authors):
            reasons.append("extracted_author_mismatch")
    else:
        if _text(metadata.get("id")) != external:
            reasons.append("extracted_video_id_mismatch_or_missing")
        if not page:
            reasons.append("extracted_webpage_identity_missing")
        display_id = _text(metadata.get("display_id"))
        if display_id and display_id != external:
            reasons.append("extracted_display_id_mismatch")
        expected_channel = _text(binding.get("registered_channel_id"))
        channel = _text(metadata.get("channel_id"))
        if expected_channel and channel and channel != expected_channel:
            reasons.append("extracted_channel_id_mismatch")
        author_confirmed = bool(expected_channel and channel == expected_channel)
        for key in ("uploader_id", "author_handle"):
            raw = _text(metadata.get(key))
            if not raw:
                continue
            if _CHANNEL_ID.fullmatch(raw):
                if expected_channel:
                    author_confirmed |= raw == expected_channel
                    if raw != expected_channel:
                        reasons.append("extracted_author_mismatch")
            elif expected_handle:
                author_confirmed |= _handle(raw) == expected_handle
                if _handle(raw) != expected_handle:
                    reasons.append("extracted_author_mismatch")
        for key in ("uploader_url", "channel_url"):
            raw = _text(metadata.get(key))
            if not raw:
                continue
            profile = _profile(raw)
            if not profile or profile.get("platform") != "youtube":
                reasons.append("extracted_author_profile_invalid")
            elif profile.get("handle") and expected_handle:
                author_confirmed |= profile["handle"] == expected_handle
                if profile["handle"] != expected_handle:
                    reasons.append("extracted_author_mismatch")
            elif profile.get("channel_id") and expected_channel:
                author_confirmed |= profile["channel_id"] == expected_channel
                if profile["channel_id"] != expected_channel:
                    reasons.append("extracted_channel_id_mismatch")
        if not author_confirmed:
            reasons.append("extracted_author_identity_missing")
    return _decision(reasons)


def validate_semantic_evidence(binding: Mapping[str, Any], actual_sha256: str,
                               proof: Mapping[str, Any] | None) -> dict[str, Any]:
    """Validate complete, previously obtained Gemini proof bound to actual bytes."""
    empty = {"context": {}}
    if not isinstance(binding, Mapping) or not isinstance(proof, Mapping):
        return _decision(["semantic_evidence_missing"], **empty)
    if not isinstance(actual_sha256, str) or not _SHA256.fullmatch(actual_sha256):
        return _decision(["actual_file_sha256_invalid"], **empty)
    reasons: list[str] = []
    if type(proof.get("schema_version")) is not int or proof["schema_version"] != 1:
        reasons.append("semantic_schema_version_invalid")
    for key in ("account_id", "source_id", "external_post_id"):
        if not _text(binding.get(key)) or proof.get(key) != binding[key]:
            reasons.append(f"semantic_{key}_mismatch")
    identity, proof_identity = _identity(binding.get("canonical_url")), _identity(proof.get("canonical_url"))
    if not identity or proof_identity != identity:
        reasons.append("semantic_canonical_url_mismatch")
    expected_asset = _text(binding.get("media_asset_id")) or f"ma_{actual_sha256[:24]}"
    if proof.get("media_asset_id") != expected_asset:
        reasons.append("semantic_media_asset_id_mismatch")
    if proof.get("content_hash") != actual_sha256:
        reasons.append("semantic_content_hash_mismatch")
    analysis = proof.get("analysis")
    if not isinstance(analysis, Mapping):
        return _decision([*reasons, "semantic_analysis_missing"], **empty)
    if analysis.get("status") != "PASS":
        reasons.append("semantic_analysis_not_passed")
    evidence = analysis.get("visual_evidence")
    if not isinstance(evidence, Mapping):
        return _decision([*reasons, "semantic_visual_evidence_missing"], **empty)
    if evidence.get("content_hash") != actual_sha256:
        reasons.append("semantic_visual_content_hash_mismatch")
    if evidence.get("media_asset_id") != expected_asset:
        reasons.append("semantic_visual_media_asset_id_mismatch")
    if evidence.get("provider") != "gemini" or analysis.get("provider", "gemini") != "gemini":
        reasons.append("semantic_vision_provider_not_approved")
    if type(analysis.get("http_status")) is not int or analysis["http_status"] != 200:
        reasons.append("semantic_provider_http_not_success")
    hashes = evidence.get("frame_hashes")
    if (not isinstance(hashes, list) or not hashes
            or not all(isinstance(value, str) and _SHA256.fullmatch(value) for value in hashes)):
        reasons.append("semantic_frame_hashes_invalid")
    for key in ("account_id", "source_id", "canonical_url", "external_post_id", "media_asset_id", "content_hash"):
        if key in analysis and analysis[key] != proof.get(key):
            reasons.append(f"semantic_analysis_{key}_mismatch")
    media = {**analysis, "media_type": "video", "media_asset_id": expected_asset,
             "content_hash": actual_sha256}
    context = understand_media_contract(media, account_id=_text(binding.get("account_id")))
    if context["visual_status"] != "VISUAL_VERIFIED":
        reasons.append("semantic_visual_understanding_unverified")
    return _decision(reasons, context=context if not reasons else {})
