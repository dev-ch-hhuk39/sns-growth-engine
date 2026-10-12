#!/usr/bin/env python3
"""Phase 5B-6K: read-only Drive/Sheets ACL evidence for a pinned mirror target.

This probe is NEVER an activation permit and never calls a mutation API.
The caller supplies a separately approved Google service credential. We do
not discover credentials, modify sharing, create Sheets, or write to cells.
Google Drive capabilities are current-principal observations, not a proof
about all inherited sharing or future ACL changes.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from media_mirror_sheets_adapter import ReportingRowTarget

_SHEET_MIME = "application/vnd.google-apps.spreadsheet"
_EMAIL = re.compile(r"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,80}\Z")
_DRIVE_FIELDS = "id,mimeType,trashed,capabilities(canEdit,canModifyContent)"
_SHEETS_FIELDS = (
    "spreadsheetId,sheets(properties(sheetId,title,sheetType,"
    "gridProperties(rowCount,columnCount)))"
)
_MAX_RESPONSE = 32_768


class MirrorAclPreflightBlocked(ValueError):
    """Only stable, sanitized codes; no provider response bodies or tokens."""


class ReadOnlyGoogleMirrorMetadata:
    """Only fixed Drive files.get and Sheets spreadsheets.get metadata.

    An injected HTTPS session is used for isolated tests. The default
    AuthorizedSession is created ONLY when a trusted caller explicitly
    invokes a read and supplies the same server-owned credential object.
    No ADC lookup, service account key loading or refresh side effects
    occur during module import or constructor evaluation.
    """

    def __init__(self, *, credentials: Any, session: Any = None) -> None:
        email = getattr(credentials, "service_account_email", None)
        if not isinstance(email, str) or _EMAIL.fullmatch(email) is None:
            raise MirrorAclPreflightBlocked("mirror_preflight_principal_invalid")
        self.credentials = credentials
        self.principal_email = email
        self._session = session

    def _get(self, url: str, *, params: dict[str, str]) -> dict[str, Any]:
        try:
            session = self._session
            if session is None:
                from google.auth.transport.requests import AuthorizedSession

                session = AuthorizedSession(self.credentials)
                self._session = session
            response = session.get(
                url, params=params, timeout=8, allow_redirects=False,
            )
            if response.status_code != 200:
                raise MirrorAclPreflightBlocked("mirror_preflight_provider_denied")
            body = response.content
            if not isinstance(body, bytes) or len(body) > _MAX_RESPONSE:
                raise MirrorAclPreflightBlocked("mirror_preflight_response_untrusted")
            document = json.loads(body)
            if type(document) is not dict:
                raise MirrorAclPreflightBlocked("mirror_preflight_response_untrusted")
            return document
        except MirrorAclPreflightBlocked:
            raise
        except Exception:
            raise MirrorAclPreflightBlocked("mirror_preflight_provider_unavailable") from None

    def file_capabilities(self, spreadsheet_id: str) -> dict[str, Any]:
        """GET for EXACT configured file ID; no list/search or write endpoints."""
        from media_mirror_rehearsal import SHEET_ID

        if not isinstance(spreadsheet_id, str) or not SHEET_ID.fullmatch(
            spreadsheet_id
        ):
            raise MirrorAclPreflightBlocked("mirror_preflight_file_id_invalid")
        return self._get(
            f"https://www.googleapis.com/drive/v3/files/{spreadsheet_id}",
            params={
                "fields": _DRIVE_FIELDS, "supportsAllDrives": "true",
            },
        )

    def spreadsheet_structure(self, spreadsheet_id: str) -> dict[str, Any]:
        from media_mirror_rehearsal import SHEET_ID

        if not isinstance(spreadsheet_id, str) or not SHEET_ID.fullmatch(
            spreadsheet_id
        ):
            raise MirrorAclPreflightBlocked("mirror_preflight_file_id_invalid")
        return self._get(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}",
            params={"fields": _SHEETS_FIELDS, "includeGridData": "false"},
        )


def _check_file(metadata: dict[str, Any], *, identifier: str, can_edit: bool) -> None:
    capabilities = metadata.get("capabilities") if type(metadata) is dict else None
    if (type(metadata) is not dict
            or metadata.get("id") != identifier
            or metadata.get("mimeType") != _SHEET_MIME
            or metadata.get("trashed") is not False
            or type(capabilities) is not dict
            or capabilities.get("canEdit") is not can_edit
            or capabilities.get("canModifyContent") is not can_edit):
        raise MirrorAclPreflightBlocked("mirror_preflight_acl_not_proven")


def _check_tab(structure: dict[str, Any], target: ReportingRowTarget) -> None:
    if (type(structure) is not dict
            or structure.get("spreadsheetId") != target.reporting_spreadsheet_id
            or type(structure.get("sheets")) is not list):
        raise MirrorAclPreflightBlocked("mirror_preflight_sheet_metadata_untrusted")
    matching = []
    for item in structure["sheets"]:
        properties = item.get("properties") if type(item) is dict else None
        if type(properties) is dict and properties.get("title") == target.reporting_tab:
            matching.append(properties)
    if len(matching) != 1:
        raise MirrorAclPreflightBlocked("mirror_preflight_tab_not_unique")
    tab = matching[0]
    grid = tab.get("gridProperties")
    if (type(tab.get("sheetId")) is not int
            or tab["sheetId"] < 0
            or tab.get("sheetType") != "GRID"
            or type(grid) is not dict
            or type(grid.get("rowCount")) is not int
            or type(grid.get("columnCount")) is not int
            or grid["rowCount"] < target.row_number
            or grid["columnCount"] < 12):
        raise MirrorAclPreflightBlocked("mirror_preflight_tab_invalid")


def read_only_acl_preflight(
    *, client: ReadOnlyGoogleMirrorMetadata,
    target: ReportingRowTarget,
    expected_principal_email: str,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    """Checks current-principal ACL on both files; NEVER enables writes."""
    if not isinstance(client, ReadOnlyGoogleMirrorMetadata):
        raise MirrorAclPreflightBlocked("mirror_preflight_client_invalid")
    if not isinstance(target, ReportingRowTarget):
        raise MirrorAclPreflightBlocked("mirror_preflight_target_invalid")
    try:
        target.validate()
    except Exception:
        raise MirrorAclPreflightBlocked("mirror_preflight_target_invalid") from None
    if (not isinstance(expected_principal_email, str)
            or not _EMAIL.fullmatch(expected_principal_email)
            or expected_principal_email != client.principal_email):
        raise MirrorAclPreflightBlocked("mirror_preflight_principal_mismatch")
    now = observed_at or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise MirrorAclPreflightBlocked("mirror_preflight_clock_invalid")

    # Both metadata requests MUST use the SAME credential-bound client.
    original = client.file_capabilities(target.operational_spreadsheet_id)
    _check_file(original, identifier=target.operational_spreadsheet_id, can_edit=False)
    reporting = client.file_capabilities(target.reporting_spreadsheet_id)
    _check_file(reporting, identifier=target.reporting_spreadsheet_id, can_edit=True)
    _check_tab(
        client.spreadsheet_structure(target.reporting_spreadsheet_id), target,
    )
    identifier = json.dumps(
        [
            client.principal_email, target.operational_spreadsheet_id,
            target.reporting_spreadsheet_id, target.reporting_tab,
            target.row_number,
        ],
        ensure_ascii=True, separators=(",", ":"),
    )
    return {
        "status": "READ_ONLY_ACL_PASSED_NOT_ACTIVATED",
        "evidence_sha256": hashlib.sha256(identifier.encode("ascii")).hexdigest(),
        "observed_at": now.astimezone(timezone.utc).isoformat(
            timespec="seconds"
        ),
        "provider_metadata_checks": 3,
        "reporting_write_authorized": False,
        "operational_queue_modified": False,
        "sns_publish_authorized": False,
        "requires_separate_operator_approval": True,
    }
