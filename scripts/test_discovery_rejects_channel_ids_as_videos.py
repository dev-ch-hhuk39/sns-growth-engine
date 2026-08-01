#!/usr/bin/env python3
"""Verify individual-video ID validation semantically.

This test intentionally uses Python AST rather than checking source-code
formatting. Line wrapping and parentheses must not change the result.
"""

from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import discover_approved_source_videos as discovery


def is_name(
    node: ast.AST,
    expected: str,
) -> bool:
    return isinstance(node, ast.Name) and node.id == expected


def is_constant(
    node: ast.AST,
    expected: object,
) -> bool:
    return isinstance(node, ast.Constant) and node.value == expected


def platform_check(
    node: ast.AST,
    expected: str,
) -> bool:
    return (
        isinstance(node, ast.Compare)
        and is_name(node.left, "platform")
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.Eq)
        and len(node.comparators) == 1
        and is_constant(
            node.comparators[0],
            expected,
        )
    )


def youtube_length_check(
    node: ast.AST,
) -> bool:
    return (
        isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Call)
        and is_name(node.left.func, "len")
        and len(node.left.args) == 1
        and is_name(
            node.left.args[0],
            "video_id",
        )
        and len(node.ops) == 1
        and isinstance(node.ops[0], ast.NotEq)
        and len(node.comparators) == 1
        and is_constant(
            node.comparators[0],
            11,
        )
    )


def tiktok_numeric_check(
    node: ast.AST,
) -> bool:
    return (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.Not)
        and isinstance(node.operand, ast.Call)
        and isinstance(
            node.operand.func,
            ast.Attribute,
        )
        and node.operand.func.attr == "isdigit"
        and is_name(
            node.operand.func.value,
            "video_id",
        )
        and not node.operand.args
    )


def condition_parts(
    node: ast.AST,
) -> list[ast.AST]:
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return list(node.values)

    return [node]


source = textwrap.dedent(inspect.getsource(discovery.discover_source_videos_real))

tree = ast.parse(source)

youtube_found = False
tiktok_found = False

for node in ast.walk(tree):
    if not isinstance(node, ast.If):
        continue

    parts = condition_parts(node.test)

    if any(
        platform_check(
            part,
            "youtube",
        )
        for part in parts
    ) and any(youtube_length_check(part) for part in parts):
        youtube_found = True

    if any(
        platform_check(
            part,
            "tiktok",
        )
        for part in parts
    ) and any(tiktok_numeric_check(part) for part in parts):
        tiktok_found = True


checks = [
    (
        "youtube discovery requires " "11 character video id",
        youtube_found,
    ),
    (
        "tiktok discovery requires " "numeric video id",
        tiktok_found,
    ),
]

failed = [name for name, ok in checks if not ok]

for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} " f"{name}")

print(f"PASS: {len(checks) - len(failed)} " f"/ FAIL: {len(failed)}")

raise SystemExit(1 if failed else 0)
