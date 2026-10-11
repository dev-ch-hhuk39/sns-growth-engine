#!/usr/bin/env python3
"""Bounded cleanup of old, marked SNS-only interrupted install stages."""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import time
from pathlib import Path

ROOT = Path('/opt/github-runners/sns-growth-engine/.buffered-runtime')
STAGE = re.compile(r'\.stage-([0-9a-f]{40})\.[a-zA-Z0-9]{6}\Z')
MIN_AGE = 7 * 86400


def candidates(runtime_root: Path, *, now: float | None = None) -> list[Path]:
    if runtime_root.name != '.buffered-runtime' or runtime_root.is_symlink():
        raise ValueError('unsafe_runtime_scope')
    releases = runtime_root / 'releases'
    if not releases.is_dir() or releases.is_symlink():
        raise ValueError('unsafe_releases_scope')
    protected: set[Path] = set()
    for name in ('current', 'previous', 'pending'):
        pointer = runtime_root / name
        if pointer.exists() or pointer.is_symlink():
            if not pointer.is_symlink():
                raise ValueError('non_symlink_release_pointer')
            target = pointer.resolve(strict=True)
            if target.parent != releases.resolve(strict=True):
                raise ValueError('pointer_outside_releases')
            protected.add(target)
    now = time.time() if now is None else now
    found = []
    for entry in releases.iterdir():
        match = STAGE.fullmatch(entry.name)
        if match is None or entry.is_symlink() or not entry.is_dir() or entry.resolve() in protected:
            continue
        marker = entry / '.sns-deploy-stage-owned'
        if (not marker.is_file() or marker.is_symlink() or
                marker.read_text(encoding='utf-8').strip() != match.group(1)):
            continue
        if now - entry.stat().st_mtime < MIN_AGE:
            continue
        found.append(entry)
    return sorted(found, key=lambda p: p.stat().st_mtime)[:2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, default=ROOT)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-owned-stage-cleanup', action='store_true')
    opts = parser.parse_args()
    try:
        paths = candidates(opts.runtime_root)
        removed = []
        if opts.apply:
            if not opts.confirm_owned_stage_cleanup:
                raise ValueError('explicit_cleanup_confirmation_required')
            # Called only from the already cross-VPS-locked deploy transaction.
            for path in paths:
                # Revalidate immediately before deletion. No wildcard deletes.
                if path not in candidates(opts.runtime_root):
                    raise ValueError('stage_scope_changed')
                from prune_obsolete_runtime_releases import assert_not_in_use
                assert_not_in_use([path])
                shutil.rmtree(path)
                removed.append(path.name)
        print(json.dumps({'mode': 'APPLY' if opts.apply else 'DRY_RUN',
                          'eligible_count': len(paths), 'removed': removed,
                          'scope': 'sns_owned_stage_only'}, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'BLOCKED', 'reason': type(exc).__name__}))
        return 78


if __name__ == '__main__':
    raise SystemExit(main())
