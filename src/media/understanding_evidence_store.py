"""Retain complete existing video-understanding proof in an explicit host store.

This is a local persistence boundary, not a provider or authorization service.
Only the two managed X/YouTube video routes are supported. No runtime root is
discovered or defaulted, and stored proof never grants media rights. Callers
must independently bind an existing asset and evaluate current permissions.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any
import uuid

from generation.media_platform_policy import OWNER_REFERENCE_ACCOUNTS, normalize_platform
from media.golden_evidence import validate_registered_binding, validate_semantic_evidence
from reference.source_registry import load_registry

MAX_EVIDENCE_BYTES = 2 * 1024**2
MAX_STORE_BYTES = 64 * 1024**2
MAX_STORE_RECEIPTS = 512
STORE_DIRECTORY = "media-understanding-evidence"
LOCK_FILE = ".store.lock"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9_.:-]{1,256}\Z")
_IDENTITY_FIELDS = (
    "account_id", "source_id", "platform", "source_handle", "registered_profile_url",
    "registered_channel_id", "source_post_id", "source_post_media_id", "media_index",
    "canonical_url", "external_post_id", "media_asset_id", "content_hash",
)


class EvidenceStoreBlocked(ValueError):
    """A fixed reason code, without source contents or private filesystem paths."""


def _result(status: str, reasons: Iterable[str] = (), **extra: Any) -> dict[str, Any]:
    return {"status": status, "reasons": sorted(set(reasons)), **extra}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceStoreBlocked("evidence_duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise EvidenceStoreBlocked("evidence_nonfinite_json")


def _decode(encoded: bytes) -> dict[str, Any]:
    if not 0 < len(encoded) <= MAX_EVIDENCE_BYTES:
        raise EvidenceStoreBlocked("evidence_size_limit")
    value = json.loads(encoded, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    if not isinstance(value, dict):
        raise EvidenceStoreBlocked("evidence_payload_invalid")
    return value


def _preflight(runtime_root: str | Path | None, post: Mapping[str, Any], media: Mapping[str, Any]):
    if runtime_root is None or (isinstance(runtime_root, str) and not runtime_root.strip()):
        return _result("NOT_CONFIGURED")
    if not isinstance(runtime_root, (str, Path)) or not Path(runtime_root).is_absolute():
        return _result("BLOCKED", ["explicit_absolute_runtime_root_required"])
    if not isinstance(post, Mapping) or not isinstance(media, Mapping):
        return _result("BLOCKED", ["source_context_invalid"])
    account = _text(post.get("target_account_id") or post.get("account_id"))
    account_values = {_text(post.get(key)) for key in ("target_account_id", "account_id") if _text(post.get(key))}
    if len(account_values) > 1 and account_values.intersection(OWNER_REFERENCE_ACCOUNTS):
        return _result("BLOCKED", ["media_account_identity_mismatch"])
    canonical = _text(post.get("canonical_post_url"))
    platform = normalize_platform(post.get("platform") or post.get("source_platform"), canonical)
    media_type = _text(media.get("media_type")).lower()
    if account in OWNER_REFERENCE_ACCOUNTS:
        for key in ("account_id", "target_account_id"):
            if _text(media.get(key)) and _text(media[key]) != account:
                return _result("BLOCKED", ["media_account_identity_mismatch"])
        inferred = normalize_platform("", canonical)
        for owner in (post, media):
            for key in ("platform", "source_platform"):
                if (_text(owner.get(key)) and inferred
                        and normalize_platform(owner[key], canonical) != inferred):
                    return _result("BLOCKED", ["media_platform_identity_mismatch"])
        post_media_type = _text(post.get("media_type")).lower()
        if post_media_type in {"image", "video"} and media_type in {"image", "video"} and post_media_type != media_type:
            return _result("BLOCKED", ["media_type_identity_mismatch"])
    if account not in OWNER_REFERENCE_ACCOUNTS or platform not in {"x", "youtube"} or media_type != "video":
        return _result("NOT_APPLICABLE")
    return None


def _binding(post: Mapping[str, Any], media: Mapping[str, Any], content_hash: str, *,
             require_stored_asset: bool, registry_rows: Iterable[Mapping[str, Any]] | None):
    if not isinstance(content_hash, str) or not _SHA256.fullmatch(content_hash):
        raise EvidenceStoreBlocked("actual_content_hash_required")
    source_post_id = _text(post.get("source_post_id"))
    media_id = _text(media.get("source_post_media_id"))
    if (not _ID.fullmatch(source_post_id) or not _ID.fullmatch(media_id)
            or _text(media.get("source_post_id")) != source_post_id):
        raise EvidenceStoreBlocked("media_parent_identity_mismatch")
    if _text(media.get("reference_post_id")) and _text(media["reference_post_id"]) != source_post_id:
        raise EvidenceStoreBlocked("asset_parent_identity_mismatch")
    raw_index = media.get("media_index")
    if type(raw_index) is int and raw_index >= 0:
        media_index = str(raw_index)
    elif isinstance(raw_index, str) and re.fullmatch(r"0|[1-9][0-9]*", raw_index):
        media_index = raw_index
    else:
        raise EvidenceStoreBlocked("media_index_invalid")
    account = _text(post.get("target_account_id") or post.get("account_id"))
    for owner in (post, media):
        for key in ("account_id", "target_account_id"):
            if _text(owner.get(key)) and _text(owner[key]) != account:
                raise EvidenceStoreBlocked("media_account_identity_mismatch")
    if _text(media.get("source_id")) and _text(media["source_id"]) != _text(post.get("source_id")):
        raise EvidenceStoreBlocked("media_source_identity_mismatch")
    item = {"account_id": account, "source_id": _text(post.get("source_id")),
            "platform": normalize_platform(post.get("platform") or post.get("source_platform"),
                                           _text(post.get("canonical_post_url"))),
            "url": _text(post.get("canonical_post_url")),
            "source_handle": _text(post.get("author_handle"))}
    rows = list(load_registry(preserve_duplicates=True) if registry_rows is None else registry_rows)
    decision = validate_registered_binding(item, rows)
    if decision["status"] != "PASS":
        raise EvidenceStoreBlocked("registered_source_binding_unverified")
    bound = decision["binding"]
    if _text(post.get("external_post_id")) != bound["external_post_id"]:
        raise EvidenceStoreBlocked("post_external_identity_mismatch")
    media_decision = validate_registered_binding({**item, "url": _text(media.get("canonical_post_url"))}, rows)
    if (media_decision["status"] != "PASS"
            or media_decision["binding"]["canonical_url"] != bound["canonical_url"]):
        raise EvidenceStoreBlocked("media_canonical_identity_mismatch")
    for key in ("platform", "source_platform"):
        if (_text(media.get(key)) and normalize_platform(media[key], _text(media.get("canonical_post_url")))
                != bound["platform"]):
            raise EvidenceStoreBlocked("media_platform_identity_mismatch")
    stored_hash = _text(media.get("content_hash"))
    if (require_stored_asset and not stored_hash) or (stored_hash and stored_hash != content_hash):
        raise EvidenceStoreBlocked("media_content_hash_mismatch")
    for key in ("resolved_content_hash", "asset_content_hash", "understanding_content_hash"):
        if _text(media.get(key)) and _text(media[key]) != content_hash:
            raise EvidenceStoreBlocked("media_content_hash_mismatch")
    prior_understanding = media.get("media_understanding")
    if (isinstance(prior_understanding, Mapping) and _text(prior_understanding.get("content_hash"))
            and _text(prior_understanding["content_hash"]) != content_hash):
        raise EvidenceStoreBlocked("media_content_hash_mismatch")
    asset_ids = {_text(media.get(key)) for key in ("media_asset_id", "media_id") if _text(media.get(key))}
    if len(asset_ids) > 1 or (require_stored_asset and not asset_ids):
        raise EvidenceStoreBlocked("media_asset_identity_mismatch")
    asset_id = next(iter(asset_ids)) if asset_ids else f"ma_{content_hash[:24]}"
    if not _ID.fullmatch(asset_id):
        raise EvidenceStoreBlocked("media_asset_identity_mismatch")
    return {**bound, "source_post_id": source_post_id, "source_post_media_id": media_id,
            "media_index": media_index, "media_asset_id": asset_id, "content_hash": content_hash}


def _key(binding: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical({key: binding[key] for key in _IDENTITY_FIELDS})).hexdigest()


def _validate_envelope(binding: Mapping[str, Any], envelope: Mapping[str, Any]) -> None:
    if set(envelope) != {"schema_version", "analysis", *_IDENTITY_FIELDS}:
        raise EvidenceStoreBlocked("evidence_envelope_fields_invalid")
    if any(envelope.get(key) != binding[key] for key in _IDENTITY_FIELDS):
        raise EvidenceStoreBlocked("evidence_identity_mismatch")
    analysis = envelope.get("analysis")
    if isinstance(analysis, Mapping) and any(
        key in analysis and analysis[key] != binding[key] for key in _IDENTITY_FIELDS
    ):
        raise EvidenceStoreBlocked("analysis_identity_mismatch")
    semantic = validate_semantic_evidence(binding, binding["content_hash"], envelope)
    if semantic["status"] != "PASS":
        raise EvidenceStoreBlocked("semantic_understanding_unverified")


def _check_directory(fd: int, *, private: bool = False) -> None:
    info = os.fstat(fd)
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
            or (stat.S_IMODE(info.st_mode) != 0o700 if private else bool(info.st_mode & 0o022))):
        raise EvidenceStoreBlocked("evidence_directory_untrusted")


@contextmanager
def _store(runtime_root: str | Path, *, create: bool):
    path = Path(runtime_root)
    if ".." in path.parts or path.resolve(strict=True) != path:
        raise EvidenceStoreBlocked("evidence_runtime_root_untrusted")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    root_fd = shared_fd = store_fd = None
    try:
        root_fd = os.open(path, flags)
        _check_directory(root_fd)
        shared_fd = os.open("shared", flags, dir_fd=root_fd)
        _check_directory(shared_fd)
        if create:
            try:
                os.mkdir(STORE_DIRECTORY, mode=0o700, dir_fd=shared_fd)
                os.fsync(shared_fd)
            except FileExistsError:
                pass
        store_fd = os.open(STORE_DIRECTORY, flags, dir_fd=shared_fd)
        _check_directory(store_fd, private=True)
        yield store_fd
        for name, parent_fd, descriptor in ((path, None, root_fd), ("shared", root_fd, shared_fd),
                                             (STORE_DIRECTORY, shared_fd, store_fd)):
            named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            opened = os.fstat(descriptor)
            if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
                raise EvidenceStoreBlocked("evidence_directory_changed")
            _check_directory(descriptor, private=descriptor == store_fd)
    finally:
        for descriptor in (store_fd, shared_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)


def _file_identity(info: os.stat_result):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
            or not 0 < info.st_size <= MAX_EVIDENCE_BYTES):
        raise EvidenceStoreBlocked("evidence_file_untrusted")
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _read(store_fd: int, name: str) -> dict[str, Any]:
    before = _file_identity(os.stat(name, dir_fd=store_fd, follow_symlinks=False))
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=store_fd)
    with os.fdopen(fd, "rb") as stream:
        if _file_identity(os.fstat(stream.fileno())) != before:
            raise EvidenceStoreBlocked("evidence_file_changed")
        encoded = stream.read(MAX_EVIDENCE_BYTES + 1)
        if _file_identity(os.fstat(stream.fileno())) != before:
            raise EvidenceStoreBlocked("evidence_file_changed")
    if _file_identity(os.stat(name, dir_fd=store_fd, follow_symlinks=False)) != before:
        raise EvidenceStoreBlocked("evidence_file_changed")
    return _decode(encoded)


@contextmanager
def _exclusive_store_lock(store_fd: int):
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(LOCK_FILE, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=store_fd)
        os.fchmod(fd, 0o600)
        os.fsync(store_fd)
    except FileExistsError:
        fd = os.open(LOCK_FILE, flags, dir_fd=store_fd)
    try:
        info = os.fstat(fd)
        named = os.stat(LOCK_FILE, dir_fd=store_fd, follow_symlinks=False)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size != 0
                or (named.st_dev, named.st_ino) != (info.st_dev, info.st_ino)):
            raise EvidenceStoreBlocked("evidence_lock_untrusted")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise EvidenceStoreBlocked("evidence_store_busy") from None
        yield
        named = os.stat(LOCK_FILE, dir_fd=store_fd, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (info.st_dev, info.st_ino):
            raise EvidenceStoreBlocked("evidence_lock_changed")
    finally:
        os.close(fd)


def _check_capacity(store_fd: int, incoming_bytes: int) -> None:
    total = count = inspected = 0
    with os.scandir(store_fd) as entries:
        for entry in entries:
            inspected += 1
            if inspected > MAX_STORE_RECEIPTS + 1:
                raise EvidenceStoreBlocked("evidence_store_capacity_exceeded")
            if entry.name == LOCK_FILE:
                continue
            if not re.fullmatch(r"[0-9a-f]{64}\.json", entry.name):
                raise EvidenceStoreBlocked("evidence_store_unknown_entry")
            identity = _file_identity(entry.stat(follow_symlinks=False))
            total += identity[2]
            count += 1
            if total + incoming_bytes > MAX_STORE_BYTES or count >= MAX_STORE_RECEIPTS:
                raise EvidenceStoreBlocked("evidence_store_capacity_exceeded")
    if incoming_bytes > MAX_STORE_BYTES:
        raise EvidenceStoreBlocked("evidence_store_capacity_exceeded")


def _publish(store_fd: int, name: str, encoded: bytes, envelope: Mapping[str, Any],
             binding: Mapping[str, Any]) -> bool:
    with _exclusive_store_lock(store_fd):
        try:
            existing = _read(store_fd, name)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            _validate_envelope(binding, existing)
            if existing != envelope:
                raise EvidenceStoreBlocked("evidence_conflict_no_overwrite")
            return True
        _check_capacity(store_fd, len(encoded))
        temporary, reused = ".prepared-" + uuid.uuid4().hex, False
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=store_fd)
        try:
            with os.fdopen(fd, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, name, src_dir_fd=store_fd, dst_dir_fd=store_fd, follow_symlinks=False)
            except FileExistsError:
                reused = True
        finally:
            os.unlink(temporary, dir_fd=store_fd)
            os.fsync(store_fd)
        stored = _read(store_fd, name)
        _validate_envelope(binding, stored)
        if stored != envelope:
            raise EvidenceStoreBlocked("evidence_conflict_no_overwrite")
        return reused


def prepare_understanding_evidence_root(runtime_root: str | Path | None) -> dict[str, Any]:
    """Check private storage before an explicitly requested provider operation."""
    if not isinstance(runtime_root, (str, Path)) or not str(runtime_root).strip() or not Path(runtime_root).is_absolute():
        return _result("BLOCKED", ["explicit_absolute_runtime_root_required"])
    try:
        with _store(runtime_root, create=True) as store_fd:
            with _exclusive_store_lock(store_fd):
                _check_capacity(store_fd, 0)
        return _result("PASS")
    except EvidenceStoreBlocked as exc:
        return _result("BLOCKED", [str(exc)])
    except (OSError, ValueError, TypeError):
        return _result("BLOCKED", ["evidence_store_unverified"])


def save_understanding_evidence(runtime_root: str | Path | None, post: Mapping[str, Any],
                                media: Mapping[str, Any], analysis: Mapping[str, Any], *,
                                content_hash: str,
                                registry_rows: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Save one complete existing analysis; never overwrite an unknown outcome."""
    early = _preflight(runtime_root, post, media)
    if early is not None:
        return early
    try:
        binding = _binding(post, media, content_hash, require_stored_asset=False, registry_rows=registry_rows)
        encoded = _canonical({"schema_version": 1, **binding, "analysis": analysis})
        envelope = _decode(encoded)
        _validate_envelope(binding, envelope)
        evidence_key = _key(binding)
        with _store(runtime_root, create=True) as store_fd:
            reused = _publish(store_fd, evidence_key + ".json", encoded, envelope, binding)
        return _result("PASS", evidence_key=evidence_key, reused=reused)
    except EvidenceStoreBlocked as exc:
        return _result("BLOCKED", [str(exc)])
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        return _result("BLOCKED", ["evidence_store_unverified"])


def load_understanding_evidence(runtime_root: str | Path | None, post: Mapping[str, Any],
                                media: Mapping[str, Any], *, content_hash: str,
                                registry_rows: Iterable[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Read exact bound proof; never initialize storage or reconstruct vision."""
    early = _preflight(runtime_root, post, media)
    if early is not None:
        return early
    try:
        binding = _binding(post, media, content_hash, require_stored_asset=True, registry_rows=registry_rows)
        evidence_key = _key(binding)
        with _store(runtime_root, create=False) as store_fd:
            envelope = _read(store_fd, evidence_key + ".json")
        _validate_envelope(binding, envelope)
        return _result("PASS", evidence_key=evidence_key, analysis=envelope["analysis"])
    except EvidenceStoreBlocked as exc:
        return _result("BLOCKED", [str(exc)])
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        return _result("BLOCKED", ["evidence_store_unverified"])
