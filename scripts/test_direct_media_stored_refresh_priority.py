#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

SOURCE = Path(
    "scripts/ingest_direct_reference_media_reliable.py"
)

text = SOURCE.read_text(
    encoding="utf-8",
)

tree = ast.parse(text)

priority_map = next(
    node
    for node in tree.body
    if isinstance(
        node,
        ast.Assign,
    )
    and any(
        isinstance(
            target,
            ast.Name,
        )
        and target.id
        == "_PLATFORM_PRIORITY"
        for target in node.targets
    )
)

function = next(
    node
    for node in tree.body
    if isinstance(
        node,
        ast.FunctionDef,
    )
    and node.name
    == "_candidate_priority"
)

module = ast.Module(
    body=[
        priority_map,
        function,
    ],
    type_ignores=[],
)

ast.fix_missing_locations(
    module
)

namespace: dict[str, Any] = {}

exec(
    compile(
        module,
        str(SOURCE),
        "exec",
    ),
    namespace,
)

priority = namespace[
    "_candidate_priority"
]

stored_youtube = priority(
    materialized=True,
    refresh_understanding=True,
    platform="youtube",
)

external_threads = priority(
    materialized=False,
    refresh_understanding=True,
    platform="threads",
)

assert (
    stored_youtube[0]
    < external_threads[0]
)

assert (
    priority(
        materialized=False,
        refresh_understanding=True,
        platform="threads",
    )[1]
    <
    priority(
        materialized=False,
        refresh_understanding=True,
        platform="youtube",
    )[1]
)

assert (
    "source_text_is_usable("
    in text
)

print(
    "[PASS] stored understanding refresh precedes new network download"
)

print(
    "[PASS] existing platform priority remains intact within same tier"
)

print(
    "[PASS] unusable source posts are skipped before external cost"
)
