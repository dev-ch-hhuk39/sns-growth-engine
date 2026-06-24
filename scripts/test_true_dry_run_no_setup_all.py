#!/usr/bin/env python3
"""Validate queue/refill dry-run paths do not call setup_all or write methods."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(name: str) -> str:
    return (ROOT / "scripts" / name).read_text(encoding="utf-8")


def _calls_setup_all_under_dry_run_guard(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = ast.unparse(node.test)
            if "args.dry_run" in test and "not args.dry_run" not in test:
                body_module = ast.Module(body=node.body, type_ignores=[])
                for child in ast.walk(body_module):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute):
                        if child.func.attr == "setup_all":
                            return True
    return False


def _has_setup_all_only_in_else(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "setup_all":
            parent_ok = False
            for maybe_if in ast.walk(tree):
                if isinstance(maybe_if, ast.If) and node in list(ast.walk(ast.Module(body=maybe_if.orelse, type_ignores=[]))):
                    parent_ok = "args.dry_run" in ast.unparse(maybe_if.test)
            if not parent_ok:
                return False
    return True


def main() -> int:
    process = _source("process_threads_queue.py")
    refill = _source("refill_threads_queue.py")
    metrics = _source("import_threads_metrics_manual.py")
    checks = [
        ("process dry-run says read-only", "[READ_ONLY]" in process and '"read_only": True' in process),
        ("refill dry-run says read-only", "[READ_ONLY]" in refill and '"read_only": True' in refill),
        ("process setup_all not under dry-run branch", not _calls_setup_all_under_dry_run_guard(process)),
        ("refill setup_all not under dry-run branch", not _calls_setup_all_under_dry_run_guard(refill)),
        ("process setup_all only else branch", _has_setup_all_only_in_else(process)),
        ("refill setup_all only else branch", _has_setup_all_only_in_else(refill)),
        ("metrics import has no setup_all", ".setup_all(" not in metrics),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
