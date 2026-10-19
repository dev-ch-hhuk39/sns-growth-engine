#!/usr/bin/env python3
"""Secure, atomic persistence for per-account Threads tokens.

Only the existing, account-scoped token file may be replaced. Never print
tokens, follow token-file symlinks, or leave partial JSON after a failed write.
"""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any, Mapping

SUPPORTED_ACCOUNTS = frozenset({"night_scout", "liver_manager", "beauty_account"})


class TokenStoreError(RuntimeError):
    """A token-store safety precondition was not met."""


def token_path(directory: Path, account_id: str) -> Path:
    if account_id not in SUPPORTED_ACCOUNTS:
        raise TokenStoreError("unsupported_threads_account")
    return Path(directory) / (account_id + ".json")


def _guard_directory(directory: Path) -> None:
    if directory.is_symlink():
        raise TokenStoreError("token_store_directory_symlink")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = directory.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise TokenStoreError("token_store_directory_not_regular")
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise TokenStoreError("token_store_directory_other_writable")


def _guard_existing(path: Path) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise TokenStoreError("token_file_not_regular_or_hardlinked")


def store_token(directory: Path, account_id: str, data: Mapping[str, Any]) -> Path:
    """Commit one validated token JSON with 0600 permissions and os.replace.

    Any failure before replace preserves the old file. A failure after replace
    is a visible error; callers must not assume a GitHub Secret was updated.
    """
    path = token_path(directory, account_id)
    if data.get("account_id") != account_id:
        raise TokenStoreError("token_account_mismatch")
    token = data.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise TokenStoreError("token_value_missing")
    _guard_directory(path.parent)
    _guard_existing(path)
    fd: int | None = None
    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix="." + account_id + ".", suffix=".tmp", dir=path.parent
        )
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            fd = None
            json.dump(dict(data), stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        # Recheck before replacement in case another actor changed the target.
        _guard_existing(path)
        os.replace(temp_name, path)
        temp_name = None
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if fd is not None:
            os.close(fd)
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
    return path
