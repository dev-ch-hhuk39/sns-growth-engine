#!/usr/bin/env python3
from recover_production_sheets_threads_first import scope_verification_to_text_inventory

verification = {
    "checks": {
        "queue_ids_unique": True,
        "ready_is_only_postable_status": True,
        "media_no_unapproved_upload": False,
        "media_approved_rows_rights_clear": False,
        "media_uploaded_only_if_approved": False,
    },
    "failed": [
        "media_no_unapproved_upload",
        "media_approved_rows_rights_clear",
        "media_uploaded_only_if_approved",
    ],
}
scoped = scope_verification_to_text_inventory(verification)
assert scoped["failed"] == []
assert scoped["verification_scope"]["mode"] == "TEXT_INVENTORY"
assert set(scoped["verification_scope"]["historical_media_failures"]) == set(verification["failed"])

verification["failed"].append("queue_ids_unique")
scoped = scope_verification_to_text_inventory(verification)
assert scoped["failed"] == ["queue_ids_unique"]
print("PASS test_text_inventory_verification_scope.py")
