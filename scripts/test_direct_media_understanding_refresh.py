#!/usr/bin/env python3
"""Legacy uploaded videos receive one bounded understanding refresh."""
from __future__ import annotations

import os
import sys
import hashlib
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import ingest_direct_reference_media as core  # noqa: E402
import ingest_direct_reference_media_reliable as reliable  # noqa: E402


class Worksheet:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def get_all_records(self) -> list[dict[str, str]]:
        return [dict(row) for row in self.rows]


class Client:
    def __init__(self, transcript_status: str) -> None:
        self.rows = {
            "source_posts": [{
                "source_post_id": "post-1",
                "source_id": "source-1",
                "target_account_id": "night_scout",
                "platform": "youtube",
            }],
            "source_post_media": [{
                "source_post_media_id": "media-1",
                "source_post_id": "post-1",
                "media_index": "0",
                "media_type": "video",
                "original_media_url": "https://www.youtube.com/watch?v=video1",
                "canonical_post_url": "https://www.youtube.com/watch?v=video1",
                "cloudinary_status": "UPLOADED",
                "storage_url": "https://res.cloudinary.com/demo/video/upload/video1.mp4",
                "media_asset_id": "asset-1",
                "download_status": "DOWNLOADED",
                "created_at": "2026-08-01T00:00:00+00:00",
            }],
            "source_media_understanding": [{
                "understanding_id": "understanding-1",
                "source_post_media_id": "media-1",
                "status": "PASS",
                "transcript_status": transcript_status,
                "transcript_hash": "",
                "transcript_text": "",
            }],
        }

    def _ws(self, name: str) -> Worksheet:
        return Worksheet(self.rows[name])


PERMISSIONS = [{
    "source_id": "source-1",
    "account_id": "night_scout",
    "permission_status": "approved",
    "rights_status": "approved_creator_clip",
    "allow_download": "true",
    "allow_cloudinary_storage": "true",
    "allow_original_repost": "true",
    "allow_new_caption": "true",
    "evidence_type": "owner_contract",
    "evidence_reference": "fixture",
    "approved_by": "owner",
    "approved_at": "2026-08-01T00:00:00+00:00",
    "revoked": "false",
}]

original_env = os.environ.get("ALLOW_LOCAL_TRANSCRIPTION")
try:
    os.environ["ALLOW_LOCAL_TRANSCRIPTION"] = "true"
    pending = Client("")
    media = pending.rows["source_post_media"][0]
    understanding = pending.rows["source_media_understanding"][0]

    assert core.media_understanding_needs_refresh(media, understanding)
    assert core.select_pending_media_id(
        pending,
        "night_scout",
        permissions=PERMISSIONS,
    ) == "media-1"
    assert reliable.select_pending_media_id(
        pending,
        "night_scout",
        permissions=PERMISSIONS,
    ) == "media-1"

    missing = Client("")
    missing.rows["source_media_understanding"] = []
    assert core.media_understanding_needs_refresh(
        missing.rows["source_post_media"][0],
        None,
    )
    assert core.select_pending_media_id(
        missing,
        "night_scout",
        permissions=PERMISSIONS,
    ) == "media-1"
    assert reliable.select_pending_media_id(
        missing,
        "night_scout",
        permissions=PERMISSIONS,
    ) == "media-1"

    completed = Client("UNAVAILABLE")
    assert not core.media_understanding_needs_refresh(
        completed.rows["source_post_media"][0],
        completed.rows["source_media_understanding"][0],
    )
    assert core.select_pending_media_id(
        completed,
        "night_scout",
        permissions=PERMISSIONS,
    ) == ""
    assert reliable.select_pending_media_id(
        completed,
        "night_scout",
        permissions=PERMISSIONS,
    ) == ""
finally:
    if original_env is None:
        os.environ.pop("ALLOW_LOCAL_TRANSCRIPTION", None)
    else:
        os.environ["ALLOW_LOCAL_TRANSCRIPTION"] = original_env


media_bytes = b"existing-approved-video"
digest = hashlib.sha256(media_bytes).hexdigest()
media_row = {
    **Client("").rows["source_post_media"][0],
    "content_hash": digest,
}
understanding_row = {
    **Client("").rows["source_media_understanding"][0],
    "content_hash": digest,
}
post_row = Client("").rows["source_posts"][0]
originals = {
    name: getattr(core, name)
    for name in (
        "ROOT",
        "record",
        "safe_https_url",
        "download_source_media",
        "magic_mime",
        "probe_video",
        "analyze_local_media",
        "upsert_media_understanding",
        "update_media_row",
    )
}
try:
    os.environ["ALLOW_LOCAL_TRANSCRIPTION"] = "true"
    with tempfile.TemporaryDirectory() as temporary:
        core.ROOT = Path(temporary)

        def fake_record(_client, logical, _key, _value):
            if logical == "source_media_understanding":
                return dict(understanding_row)
            if logical == "source_post_media":
                return dict(media_row)
            raise AssertionError(logical)

        def fake_download(*, path, **_kwargs):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(media_bytes)
            return "fixture"

        def fake_update(_client, _media_id, fields):
            media_row.update(fields)

        core.record = fake_record
        core.safe_https_url = lambda _url, stream_url=False: True
        core.download_source_media = fake_download
        core.magic_mime = lambda _path: "video/mp4"
        core.probe_video = lambda _path: {"duration_seconds": "20"}
        core.analyze_local_media = lambda *_args, **_kwargs: {
            "status": "PASS",
            "provider": "fixture",
            "transcript_status": "UNAVAILABLE",
        }
        core.upsert_media_understanding = (
            lambda *_args, **_kwargs: "understanding-1"
        )
        core.update_media_row = fake_update

        result = core.ingest_one(object(), post_row, media_row)
        assert result["status"] == "UNDERSTANDING_REFRESHED", result
        assert result["media_asset_id"] == "asset-1", result
        assert result["content_hash"] == digest, result
        assert media_row["cloudinary_status"] == "UPLOADED", media_row
        assert media_row["understanding_id"] == "understanding-1", media_row
finally:
    for name, value in originals.items():
        setattr(core, name, value)
    if original_env is None:
        os.environ.pop("ALLOW_LOCAL_TRANSCRIPTION", None)
    else:
        os.environ["ALLOW_LOCAL_TRANSCRIPTION"] = original_env

print("PASS test_direct_media_understanding_refresh.py")
