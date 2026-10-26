#!/usr/bin/env python3
"""Build a complete, source-pinned review utility; never installs or runs it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    'scripts/publication_review_board.py',
    'scripts/sync_publication_review.py',
    'scripts/apply_publication_review_decisions.py',
    'scripts/sns_local_publication_review_job.py',
    'scripts/run_verified_review.py',
    'config/autonomous_mode.json',
)


def build_from_contents(contents: dict[str, bytes], destination: Path, revision: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('COMPONENT_COMMIT_REQUIRED')
    if set(contents) != set(FILES) or any(not isinstance(b, bytes) or len(b) > 200_000 for b in contents.values()):
        raise ValueError('COMPONENT_DEPENDENCY_SET_INCOMPLETE')
    policy = json.loads(contents['config/autonomous_mode.json'])
    if policy.get('allow_media_posts') is not False:
        raise ValueError('COMPONENT_MEDIA_POLICY_MUST_REMAIN_DISABLED')
    for name, body in contents.items():
        if name.endswith('.py'):
            compile(body, name, 'exec')
    if (not destination.is_absolute() or destination.exists() or destination.is_symlink()
            or destination.parent.is_symlink() or not destination.parent.is_dir()):
        raise ValueError('COMPONENT_DESTINATION_MUST_BE_NEW')
    destination.mkdir(mode=0o700)
    manifest = {'source_commit': revision,
                'files': {name: hashlib.sha256(contents[name]).hexdigest() for name in FILES}}
    for name in FILES:
        target = destination / name
        target.parent.mkdir(mode=0o700, exist_ok=True)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
        with os.fdopen(fd, 'wb') as out:
            out.write(contents[name])
            out.flush()
            os.fsync(out.fileno())
    fd = os.open(destination / 'manifest.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    with os.fdopen(fd, 'w') as out:
        json.dump(manifest, out, sort_keys=True, indent=2)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())
    for path in (destination / 'scripts', destination / 'config', destination):
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        path.chmod(0o555)
    return manifest


def build_from_git(destination: Path, revision: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('COMPONENT_COMMIT_REQUIRED')
    kind = subprocess.run(['git', 'cat-file', '-t', revision], cwd=ROOT,
                          capture_output=True, text=True, timeout=20, check=True)
    if kind.stdout.strip() != 'commit':
        raise ValueError('COMPONENT_COMMIT_REQUIRED')
    contents = {}
    for name in FILES:
        result = subprocess.run(['git', 'show', revision + ':' + name], cwd=ROOT,
                                capture_output=True, timeout=20, check=True)
        contents[name] = result.stdout
    return build_from_contents(contents, destination, revision)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build_from_git(args.out, args.revision)
    except Exception:
        print('SNS_REVIEW_COMPONENT_BUILD=BLOCKED')
        return 1
    print(json.dumps({'status': 'SOURCE_BUNDLE_ONLY', 'source_commit': args.revision,
                     'verified_files': len(result['files']), 'installed': False,
                     'sheets_writes': 0, 'posts': 0}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
