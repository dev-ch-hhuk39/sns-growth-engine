#!/usr/bin/env python3
"""6J narrow gspread values transport: one pinned reporting-only fixed row.

The code can perform a Google Sheets values.update only when an independent
server-side delivery engine supplies a verified destination and current
one-use write attempt. Do NOT instantiate with a production worksheet from
a developer shell. This is not a server endpoint, scheduler or an SNS writer.
Google Sheets values.update provides no cross-store atomic CAS; the delivery
engine must persist PREPARED before invoking this, quarantine uncertain
responses and require separate read-only reconciliation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from media_managed_queue_writer import _hash as projection_hash
from media_mirror_rehearsal import SHEET_ID, TAB

SCHEMA = "sns_sheet_read_only_mirror_preview_v1"
HEADERS = (
    "schema", "account_id", "slot_id", "queue_id",
    "writer_version", "writer_event_sha256", "shadow_event_sha256",
    "queue_sha256", "writer_state", "view_only",
    "publish_authorized", "projection_sha256",
)
SHA = re.compile(r"[0-9a-f]{64}\Z")


class FixedRowMirrorBlocked(ValueError):
    """Sanitized error code; never include provider response or cell data."""


@dataclass(frozen=True)
class ReportingRowTarget:
    """Server-loaded policy, never built from a request body."""
    reporting_spreadsheet_id: str
    operational_spreadsheet_id: str
    reporting_tab: str
    row_number: int

    def validate(self) -> None:
        if (not isinstance(self.reporting_spreadsheet_id, str)
                or SHEET_ID.fullmatch(self.reporting_spreadsheet_id) is None
                or not isinstance(self.operational_spreadsheet_id, str)
                or SHEET_ID.fullmatch(self.operational_spreadsheet_id) is None
                or self.reporting_spreadsheet_id == self.operational_spreadsheet_id
                or not isinstance(self.reporting_tab, str)
                or TAB.fullmatch(self.reporting_tab) is None
                or type(self.row_number) is not int
                or not 2 <= self.row_number <= 10000):
            raise FixedRowMirrorBlocked("mirror_fixed_target_invalid")


def preview_to_row(preview: dict[str, Any]) -> list[str]:
    """No user content, formulas, captions, media URLs, tokens or original proofs."""
    if (not isinstance(preview, dict)
            or set(preview) != {
                "schema", "account_id", "slot_id", "queue_id",
                "writer_version", "writer_event_sha256", "shadow_event_sha256",
                "queue_sha256", "writer_state", "view_only",
                "ready_transitions_performed", "publish_authorized",
            }
            or preview.get("schema") != SCHEMA
            or preview.get("view_only") is not True
            or preview.get("publish_authorized") is not False
            or preview.get("ready_transitions_performed") is not False
            or type(preview.get("writer_version")) is not int
            or not 1 <= preview["writer_version"] <= 128
            or preview.get("writer_state") not in {
                "MANAGED_BLOCKED", "HOLD_BLOCKED",
                "ARCHIVED_BLOCKED", "CONFLICT_BLOCKED",
            }
            or any(
                not isinstance(preview.get(k), str)
                or SHA.fullmatch(preview[k]) is None
                for k in (
                    "writer_event_sha256", "shadow_event_sha256",
                    "queue_sha256",
                )
            )):
        raise FixedRowMirrorBlocked("mirror_projection_invalid")
    for key in ("account_id", "slot_id", "queue_id"):
        value = preview[key]
        if (not isinstance(value, str) or not 1 <= len(value) <= 128
                or re.fullmatch(r"[A-Za-z0-9_.:-]+", value) is None):
            raise FixedRowMirrorBlocked("mirror_projection_identity_invalid")
    return [
        SCHEMA, preview["account_id"], preview["slot_id"], preview["queue_id"],
        str(preview["writer_version"]), preview["writer_event_sha256"],
        preview["shadow_event_sha256"], preview["queue_sha256"],
        preview["writer_state"], "TRUE", "FALSE", projection_hash(preview),
    ]


def row_to_preview(values: list[str]) -> dict[str, Any] | None:
    """Reject unexpected formulas, shape, metadata or forged digest."""
    if values == [] or not any(value != "" for value in values):
        return None
    if (len(values) != len(HEADERS)
            or any(type(v) is not str for v in values)
            or values[0] != SCHEMA
            or not re.fullmatch(r"[1-9][0-9]{0,2}", values[4])
            or values[9:11] != ["TRUE", "FALSE"]
            or not SHA.fullmatch(values[11])):
        raise FixedRowMirrorBlocked("mirror_external_row_invalid")
    preview = {
        "schema": values[0], "account_id": values[1],
        "slot_id": values[2], "queue_id": values[3],
        "writer_version": int(values[4]),
        "writer_event_sha256": values[5],
        "shadow_event_sha256": values[6], "queue_sha256": values[7],
        "writer_state": values[8], "view_only": True,
        "ready_transitions_performed": False,
        "publish_authorized": False,
    }
    if preview_to_row(preview) != values:
        raise FixedRowMirrorBlocked("mirror_external_row_hash_mismatch")
    return preview


class GspreadReportingFixedRow:
    """Narrow transport given a trusted, separately scoped worksheet object.

    The *engine*, not an external caller, loads and checks a ReportingRowTarget
    from the protected DB before making one network attempt. This adapter
    never creates a worksheet or spreadsheet, searches for a row, or appends.
    """

    def __init__(self, *, worksheet: Any, target: ReportingRowTarget) -> None:
        if not isinstance(target, ReportingRowTarget):
            raise FixedRowMirrorBlocked("mirror_fixed_target_invalid")
        target.validate()
        self.worksheet, self.target = worksheet, target
        # A direct worksheet cannot claim that its Google credentials match
        # a separate Drive ACL probe. Keep it unbound until constructed
        # from an authenticated client by the trusted server.
        self.auth_credentials = None
        self.factory_credential_bound = False

    @classmethod
    def from_trusted_client(
        cls, *, client: Any, target: ReportingRowTarget,
    ) -> "GspreadReportingFixedRow":
        """Network-capable constructor, never called by tests or runtime yet."""
        if not isinstance(target, ReportingRowTarget):
            raise FixedRowMirrorBlocked("mirror_fixed_target_invalid")
        target.validate()
        # Bind the *same credential object* for an independently verified
        # Drive/Sheets metadata probe. A caller-supplied worksheet alone does
        # not prove principal identity, and cannot satisfy Phase 6L preflight.
        credentials = getattr(client, "auth", None)
        if credentials is None:
            raise FixedRowMirrorBlocked("mirror_client_credentials_missing")
        worksheet = client.open_by_key(target.reporting_spreadsheet_id).worksheet(
            target.reporting_tab
        )
        adapter = cls(worksheet=worksheet, target=target)
        adapter.auth_credentials = credentials
        adapter.factory_credential_bound = True
        return adapter

    def _metadata(self) -> None:
        w = self.worksheet
        t = self.target
        if (getattr(w, "spreadsheet_id", None) != t.reporting_spreadsheet_id
                or getattr(w, "title", None) != t.reporting_tab
                or type(getattr(w, "row_count", None)) is not int
                or w.row_count < t.row_number
                or type(getattr(w, "col_count", None)) is not int
                or w.col_count < len(HEADERS)):
            raise FixedRowMirrorBlocked("mirror_reporting_worksheet_mismatch")

    def read(self) -> dict[str, Any] | None:
        """Exact reporting range; never infer a second destination."""
        self._metadata()
        try:
            header = self.worksheet.get(
                "A1:L1", value_render_option="FORMULA",
            )
            raw = self.worksheet.get(
                f"A{self.target.row_number}:L{self.target.row_number}",
                value_render_option="FORMULA",
            )
        except Exception:
            raise FixedRowMirrorBlocked("mirror_reporting_read_failed") from None
        if header != [list(HEADERS)]:
            raise FixedRowMirrorBlocked("mirror_reporting_header_untrusted")
        if raw == [] or raw == [[]]:
            return None
        if (not isinstance(raw, list) or len(raw) != 1
                or not isinstance(raw[0], list)):
            raise FixedRowMirrorBlocked("mirror_reporting_shape_invalid")
        # Formula strings cannot pass the strict row checksum.
        return row_to_preview(raw[0])

    def write_once(self, preview: dict[str, Any]) -> None:
        """Called only AFTER durable PREPARED and version comparison by engine.

        This is a PUT, not provider-side CAS. Never retry here. Any exception
        is outcome UNKNOWN until a new, independently authenticated readback.
        """
        self._metadata()
        row = preview_to_row(preview)
        try:
            self.worksheet.update(
                range_name=(
                    f"A{self.target.row_number}:L{self.target.row_number}"
                ), values=[row], value_input_option="RAW",
            )
        except Exception:
            raise FixedRowMirrorBlocked("mirror_reporting_write_outcome_unknown") from None
