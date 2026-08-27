#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

SOURCE = Path(
    "scripts/run_direct_reference_media_pipeline.py"
)

text = SOURCE.read_text(
    encoding="utf-8"
)

tree = ast.parse(text)

constant = next(
    node
    for node in tree.body
    if isinstance(node, ast.Assign)
    and any(
        isinstance(target, ast.Name)
        and target.id
        == "LEGACY_DOWNSTREAM_QUEUE_RETRY_CUTOFF_DATE"
        for target in node.targets
    )
)

function = next(
    node
    for node in tree.body
    if isinstance(node, ast.FunctionDef)
    and node.name
    == "_legacy_downstream_blocked_queue_recoverable"
)

module = ast.Module(
    body=[
        constant,
        function,
    ],
    type_ignores=[],
)

ast.fix_missing_locations(
    module
)

namespace: dict[str, Any] = {
    "Any": Any,
}

exec(
    compile(
        module,
        str(SOURCE),
        "exec",
    ),
    namespace,
)

check = namespace[
    "_legacy_downstream_blocked_queue_recoverable"
]

asset_id = (
    "asset_legacy_downstream"
)

legacy = {
    "media_asset_id": asset_id,
    "generation_mode":
        "direct_reference_media",
    "validator_status":
        "BLOCKED",
    "account_fit_status":
        "",
    "text_policy_status":
        "",
    "business_date_jst":
        "2026-08-25",
}

assert check(
    legacy,
    {asset_id},
) is True

assert check(
    {
        **legacy,
        "business_date_jst":
            "2026-08-27",
    },
    {asset_id},
) is False

assert check(
    legacy,
    set(),
) is False

assert check(
    {
        **legacy,
        "generation_mode":
            "reference_text",
    },
    {asset_id},
) is False

assert check(
    {
        **legacy,
        "validator_status":
            "",
    },
    {asset_id},
) is False

assert (
    "recoverable_legacy_asset_ids"
    in text
)

assert (
    "not _legacy_downstream_blocked_queue_recoverable("
    in text
)

print(
    "[PASS] pre-fix downstream-blocked queue gets one bounded retry"
)

print(
    "[PASS] same asset becomes terminal again for post-fix blocked queue"
)
