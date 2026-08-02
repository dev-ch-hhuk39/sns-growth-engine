#!/usr/bin/env python3

from final_production_contracts import (
    canary_required_permission_deficits,
)

result = (
    canary_required_permission_deficits(
        []
    )
)

assert result["required_slot_count"] == 4
assert result["deficit_count"] == 4

assert {
    row["canary_type"]
    for row in result["deficits"]
} == {
    "direct_reference_media",
    "approved_source_clip",
}

assert all(
    "source_id" not in row
    for row in result["deficits"]
)

print("PASS")
