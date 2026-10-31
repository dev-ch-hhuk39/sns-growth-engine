#!/usr/bin/env python3
"""Synthetic Mac/SSH/download fixtures; never real permission or Golden proof."""
from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import base64
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import yt_dlp  # noqa: E402
import capture_owner_media_on_mac as mac  # noqa: E402
import owner_media_permission_authority as authority  # noqa: E402
from media.golden_evidence import validate_registered_binding  # noqa: E402

REVISION = "a" * 40
LOCAL_REVISION = "b" * 40
REQUEST = {"account_id": "liver_manager", "source_id": "unit_source", "source_handle": "owner",
           "canonical_url": "https://x.com/owner/status/123456", "revision": REVISION}
SOURCE = {"source_id": "unit_source", "source_platform": "x", "source_handle": "@owner",
          "source_url": "https://x.com/owner", "active": True, "target_account_ids": ["liver_manager"]}
BINDING = validate_registered_binding({**REQUEST, "url": REQUEST["canonical_url"]}, [SOURCE])["binding"]
METADATA = {"id": "media-id", "display_id": "123456", "uploader_id": "owner", "webpage_url": REQUEST["canonical_url"],
            "description": "Synthetic fixture only", "formats": [{"vcodec": "h264"}]}
RAW = b"synthetic bytes; video probe is mocked"
PROBE = {"video_stream_count": 1, "audio_stream_count": 1, "width": 1280, "height": 720, "duration_seconds": 30.0}


def response():
    return {"status": "ALLOW", "allowed": True, "operation": "download", "request_sha256": authority.request_hash(REQUEST),
            "revision": REVISION, "binding": BINDING, "verified_at": datetime.now(timezone.utc).isoformat(),
            "credentials_exported": False, "production_writes": False, "publish_authorized": False}


class AuthorityBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.runtime = self.root / "runtime"
        self.release = self.runtime / "releases" / REVISION
        for path in (self.runtime, self.runtime / "releases", self.runtime / "shared", self.runtime / "shared/locks",
                     self.release, self.release / "src", self.release / "scripts"):
            path.mkdir(mode=0o700)
        (self.runtime / "current").symlink_to(self.release, target_is_directory=True)
        (self.release / ".production-release").write_text(REVISION + "\n")
        (self.release / ".production-release").chmod(0o600)
        self.deploy = self.root / "deploy.lock"
        self.deploy.touch(mode=0o600)
        (self.runtime / "shared/locks/sheets-io.lock").touch(mode=0o600)

    def read(self, *, reasons=None, callback=None):
        verdict = callback or (lambda *_args: (BINDING, [] if reasons is None else reasons))
        with patch.object(authority, "RUNTIME_ROOT", self.runtime), patch.object(authority, "DEPLOY_LOCK", self.deploy), \
                patch.object(authority.sys, "platform", "linux"), \
                patch.object(authority.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=os.geteuid())), \
                patch.object(authority, "_permission_verdict", side_effect=verdict) as operation:
            value = authority.read_current_permission(REQUEST)
        return value, operation.call_count

    def test_default_plan_never_opens_runtime_or_connections(self):
        with patch.object(sys, "argv", ["authority", "--request-json", json.dumps(REQUEST)]), \
                patch.object(authority, "read_current_permission", side_effect=AssertionError("no read")), redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(authority.main(), 0)
        self.assertFalse(json.loads(stream.getvalue())["would_connect"])

    def test_exact_download_scope_and_fixed_safe_output(self):
        value, calls = self.read()
        self.assertEqual(value["status"], "ALLOW")
        self.assertEqual(calls, 1)
        self.assertFalse(value["credentials_exported"])
        self.assertFalse(value["production_writes"])
        self.assertFalse(value["publish_authorized"])
        self.assertEqual(value["operation"], "download")

    def test_foreign_accounts_extra_operations_and_malformed_revisions_are_rejected(self):
        for request in ({**REQUEST, "account_id": "beauty_account"}, {**REQUEST, "operation": "upload"},
                        {**REQUEST, "revision": ""}, {**REQUEST, "source_handle": "bad;command"}, {**REQUEST, "account_id": []}):
            with self.subTest(request=request), self.assertRaises(ValueError):
                authority.validate_request(request)

    def test_latest_revocation_is_a_denial_not_an_authorization(self):
        value, calls = self.read(reasons=["permission_revoked"])
        self.assertEqual(value["status"], "DENY")
        self.assertFalse(value["allowed"])
        self.assertEqual(calls, 1)

    def test_wrong_release_and_linked_marker_stop_before_credentials(self):
        marker = self.release / ".production-release"
        marker.write_text("c" * 40)
        value, calls = self.read()
        self.assertEqual(value["status"], "BLOCKED")
        self.assertEqual(calls, 0)
        marker.unlink()
        other = self.root / "marker"
        other.write_text(REVISION)
        marker.symlink_to(other)
        self.assertEqual(self.read()[1], 0)

    def test_busy_deployment_lock_stops_before_live_read(self):
        with self.deploy.open("rb") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            value, calls = self.read()
        self.assertEqual(value["status"], "BLOCKED")
        self.assertEqual(calls, 0)

    def test_pointer_drift_and_provider_errors_do_not_export_partial_success(self):
        def drift(*_args):
            (self.runtime / "current").unlink()
            (self.runtime / "current").symlink_to(self.runtime / "releases" / ("c" * 40))
            return BINDING, []
        self.assertEqual(self.read(callback=drift)[0]["status"], "BLOCKED")
        (self.runtime / "current").unlink()
        (self.runtime / "current").symlink_to(self.release)
        def fail(*_args):
            print("synthetic private connection detail")
            raise RuntimeError("synthetic private connection detail")
        with redirect_stdout(io.StringIO()) as output:
            value, _ = self.read(callback=fail)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("synthetic private", json.dumps(value))

    def test_connection_parser_never_executes_shell_or_reads_credential_paths(self):
        encoded = base64.b64encode(json.dumps({"type": "service_account", "project_id": "fixture"}).encode()).decode()
        path = self.runtime / "shared/runtime.env"
        path.write_text("SNS_MASTER_SHEET_ID='fixture-sheet'\nSA_JSON_BASE64='" + encoded + "'\nIGNORED_PROVIDER_SETTING='fixture'\n")
        path.chmod(0o600)
        with patch.object(authority, "RUNTIME_ROOT", self.runtime):
            sheet, credential = authority._sheet_configuration(os.geteuid())
        self.assertEqual(sheet, "fixture-sheet")
        self.assertEqual(credential["project_id"], "fixture")
        path.write_text(path.read_text() + "SNS_MASTER_SHEET_ID='ambiguous'\n")
        with patch.object(authority, "RUNTIME_ROOT", self.runtime), self.assertRaises(ValueError):
            authority._sheet_configuration(os.geteuid())

    def test_real_ledger_adapter_requires_latest_account_and_author_permission(self):
        import reference.source_registry
        import sheets_client
        base = {"source_id": "unit_source", "source_handle": "owner", "account_id": "liver_manager",
                "allowed_accounts": "liver_manager", "permission_status": "approved", "rights_status": "approved_creator_clip",
                "usage_mode": "direct_and_clip", "evidence_type": "offline_fixture", "evidence_reference": "fixture",
                "approved_by": "fixture", "approved_at": "2026-10-30T00:00:00+00:00", "revoked": "false",
                "allow_download": "true", "allow_cut": "false"}
        values = []
        class ReadOnlyFixtureClient:
            def __init__(self, _sheet, _credential, *, dry_run): self.dry_run = dry_run
            def _ws(self, logical):
                if logical != "media_permissions": raise AssertionError("unexpected table")
                return SimpleNamespace(get_all_values=lambda: values)
        for altered, allowed in (({}, True), ({"revoked": "true"}, False), ({"account_id": "beauty_account"}, False),
                                 ({"source_handle": "other"}, False), ({"allow_download": "false"}, False)):
            row = {**base, **altered}
            values = [list(row), list(row.values())]
            with patch.object(reference.source_registry, "load_registry", return_value=[SOURCE]), \
                    patch.object(sheets_client, "SheetsClient", ReadOnlyFixtureClient), \
                    patch.object(authority, "_sheet_configuration", return_value=("fixture", {})):
                binding, reasons = authority._permission_verdict(self.release, REQUEST, os.geteuid())
            self.assertEqual(binding["source_id"], "unit_source")
            self.assertEqual(not reasons, allowed, altered)


class MacCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.workspace.chmod(0o700)
        self.options = None
        self.metadata = deepcopy(METADATA)
        self.probe = deepcopy(PROBE)

    def run_capture(self, *, grants=None, local_revisions=None):
        owner = self
        class FakeDownloader:
            def __init__(self, options): owner.options = options
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def sanitize_info(self, value, *, remove_private_keys):
                if remove_private_keys is not True: raise AssertionError("private metadata must be removed")
                return deepcopy(value)
            def extract_info(self, _url, *, download):
                self.assert_download = download
                owner.options["match_filter"](owner.metadata, incomplete=True)
                owner.options["match_filter"](owner.metadata, incomplete=False)
                Path(owner.options["outtmpl"].replace("%(ext)s", "mp4")).write_bytes(RAW)
                owner.options["progress_hooks"][0]({"downloaded_bytes": len(RAW)})
                return owner.metadata
        with patch.object(mac.sys, "platform", "darwin"), patch.object(mac, "local_revision", side_effect=local_revisions or [LOCAL_REVISION, LOCAL_REVISION]), \
                patch.object(mac, "mac_resources", return_value=(32 * 1024**3, 4 * 1024**3)), \
                patch.object(mac, "version", return_value="2026.7.4"), patch.object(mac.shutil, "which", return_value="/trusted/tool"), \
                patch.object(mac, "authority_request", side_effect=grants or [response(), response(), response()]) as authorization, \
                patch.object(yt_dlp, "YoutubeDL", FakeDownloader), patch.dict(os.environ, {}), \
                patch("generation.video_clip_materializer.probe_media_streams", return_value=self.probe):
            result = mac.capture(BINDING, self.workspace, mac.AUTHORITY_HOST, REVISION, LOCAL_REVISION)
        return result, authorization.call_count

    def test_capture_is_raw_evidence_only_with_three_live_authority_reads(self):
        result, calls = self.run_capture()
        self.assertEqual(result["status"], "LOCAL_RAW_ARTIFACT_CAPTURED")
        self.assertEqual(calls, 3)
        self.assertEqual(result["content_hash"], hashlib.sha256(RAW).hexdigest())
        for flag in ("production_writes", "publish_authorized", "queue_created", "overall_goal_acceptance", "credentials_exported"):
            self.assertIs(result[flag], False)
        self.assertEqual(result["provider_calls"], 0)
        self.assertEqual(result["content_understanding"], "NOT_RUN")
        self.assertIsNone(self.options["cookiesfrombrowser"])
        self.assertFalse(self.options["continuedl"])
        self.assertEqual(self.options["retries"], 0)
        for path in self.workspace.glob("*/*.json"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_revocation_before_download_or_after_bytes_prevents_acceptance(self):
        for grants in ([response(), ValueError("denied")], [response(), response(), ValueError("revoked")]):
            with self.subTest(grants=len(grants)), TemporaryDirectory() as directory:
                self.workspace = Path(directory).resolve()
                self.workspace.chmod(0o700)
                with self.assertRaises(ValueError): self.run_capture(grants=grants)
                self.assertEqual(list(self.workspace.glob("*/*.result.json")), [])

    def test_wrong_author_and_wrong_native_id_stop_before_bytes(self):
        for key, value in (("uploader_id", "other_author"), ("display_id", "999999")):
            with self.subTest(key=key), TemporaryDirectory() as directory:
                self.workspace = Path(directory).resolve();self.workspace.chmod(0o700)
                self.metadata = {**METADATA, key: value}
                with self.assertRaises(ValueError): self.run_capture()
                self.assertEqual(list(self.workspace.glob("*/*.mp4")), [])

    def test_audio_missing_and_checkout_drift_are_not_success(self):
        self.probe = {**PROBE, "audio_stream_count": 0}
        with self.assertRaises(ValueError): self.run_capture()
        with TemporaryDirectory() as directory:
            self.workspace = Path(directory).resolve();self.workspace.chmod(0o700);self.probe = deepcopy(PROBE)
            with self.assertRaises(ValueError): self.run_capture(local_revisions=[LOCAL_REVISION, "c" * 40])

    def test_existing_attempt_is_never_overwritten_or_automatically_retried(self):
        self.run_capture()
        before = {path: path.read_bytes() for path in self.workspace.glob("*/*")}
        with self.assertRaises(ValueError): self.run_capture()
        self.assertEqual(before, {path: path.read_bytes() for path in self.workspace.glob("*/*")})

    def test_live_and_oversized_media_do_not_get_accepted(self):
        self.metadata = {**METADATA, "is_live": True}
        with self.assertRaises(ValueError): self.run_capture()
        self.assertEqual(list(self.workspace.glob("*/*.mp4")), [])
        with TemporaryDirectory() as directory:
            self.workspace = Path(directory).resolve();self.workspace.chmod(0o700);self.metadata = deepcopy(METADATA)
            with patch.object(mac, "MAX_MEDIA_BYTES", 1), self.assertRaises(ValueError): self.run_capture()
            self.assertEqual(list(self.workspace.glob("*/*.result.json")), [])

    def test_shared_workspace_and_linked_entries_are_rejected(self):
        self.workspace.chmod(0o755)
        with self.assertRaises(ValueError): mac.protected_workspace(self.workspace)
        self.workspace.chmod(0o700)
        (self.workspace / "linked").symlink_to(ROOT)
        with self.assertRaises(ValueError): mac.protected_workspace(self.workspace)

    def test_workspace_byte_quota_counts_sparse_files_without_deleting(self):
        path = self.workspace / "existing"
        with path.open("wb") as stream: stream.truncate(mac.MAX_WORKSPACE_BYTES)
        with self.assertRaises(ValueError): mac.protected_workspace(self.workspace)
        self.assertTrue(path.exists())

    def test_no_mac_or_low_memory_cannot_contact_authority(self):
        with patch.object(mac.sys, "platform", "linux"), patch.object(mac, "authority_request") as read:
            with self.assertRaises(ValueError): mac.capture(BINDING, self.workspace, mac.AUTHORITY_HOST, REVISION, LOCAL_REVISION)
            read.assert_not_called()

    def test_mac_available_memory_counts_inactive_pages_without_lowering_floor(self):
        total, available = mac.parse_mac_resources(str(32 * 1024**3),
            "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 1000.\nPages inactive: 200000.\n")
        self.assertEqual(total, 32 * 1024**3)
        self.assertEqual(available, 201000 * 16384)
        for vm in ("unknown", "(page size of 0 bytes)\nPages free: 100.\nPages inactive: 100.\n",
                   "(page size of 16384 bytes)\nPages free: 999999999.\nPages inactive: 100.\n"):
            with self.assertRaises(ValueError): mac.parse_mac_resources(str(total), vm)
        with patch.object(mac.sys, "platform", "darwin"), patch.object(mac, "local_revision", return_value=LOCAL_REVISION), \
                patch.object(mac, "mac_resources", return_value=(2 * 1024**3, 2 * 1024**3)), patch.object(mac, "authority_request") as read:
            with self.assertRaises(ValueError): mac.capture(BINDING, self.workspace, mac.AUTHORITY_HOST, REVISION, LOCAL_REVISION)
            read.assert_not_called()

    def test_default_cli_is_offline_and_foreign_or_deferred_sources_block(self):
        args = ["capture", "--account-id", "liver_manager", "--source-id", "unit_source", "--url", REQUEST["canonical_url"]]
        with patch.object(sys, "argv", args), patch.object(mac, "load_registry", return_value=[SOURCE]), \
                patch.object(mac, "capture", side_effect=AssertionError("no capture")), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(mac.main(), 0)
        self.assertFalse(json.loads(output.getvalue())["would_connect"])

    def test_authority_rejects_other_hosts_stale_wrong_binding_and_forged_operation(self):
        with self.assertRaises(ValueError): mac.authority_request("other-host", REQUEST, expected_local_revision=LOCAL_REVISION)
        mutations = [lambda row: row.update(request_sha256="c" * 64),
                     lambda row: row.update(operation="upload"),
                     lambda row: row.update(verified_at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()),
                     lambda row: row.update(binding={**BINDING, "source_handle": "other"})]
        for mutate in mutations:
            value = response();mutate(value)
            outputs = [subprocess.CompletedProcess([], 0, "# synthetic pinned source", ""), subprocess.CompletedProcess([], 0, json.dumps(value), "")]
            with patch.object(mac, "local_revision", return_value=LOCAL_REVISION), patch.object(mac.subprocess, "run", side_effect=outputs), self.assertRaises(ValueError):
                mac.authority_request(mac.AUTHORITY_HOST, REQUEST, expected_local_revision=LOCAL_REVISION)

    def test_isolated_worker_receives_no_provider_or_publishing_credentials(self):
        result = {"status": "LOCAL_RAW_ARTIFACT_CAPTURED", "production_writes": False, "publish_authorized": False,
                  "provider_calls": 0, "credentials_exported": False, "queue_created": False, "overall_goal_acceptance": False,
                  "account_id": "liver_manager", "platform": "x", "source_id": "unit_source", "content_hash": "a" * 64,
                  "content_understanding": "NOT_RUN"}
        process = SimpleNamespace(returncode=0, communicate=lambda **_kwargs: (json.dumps(result), ""))
        with patch.object(mac.subprocess, "Popen", return_value=process) as start, \
                patch.dict(os.environ, {"GEMINI_API_KEY": "synthetic-not-a-key", "THREADS_ACCESS_TOKEN": "synthetic-not-a-token"}):
            self.assertEqual(mac.isolated_capture(["--apply"]), result)
        self.assertEqual(set(start.call_args.kwargs["env"]) - {"SSH_AUTH_SOCK"}, {"PATH", "LANG", "YTDLP_NO_PLUGINS"})
        self.assertTrue(start.call_args.kwargs["start_new_session"])

    def test_timeout_kills_only_its_own_process_group(self):
        process = SimpleNamespace(pid=12345, communicate=lambda **_kwargs: None)
        calls = iter([subprocess.TimeoutExpired("synthetic", 900), ("", "")])
        def communicate(**_kwargs):
            value = next(calls)
            if isinstance(value, Exception): raise value
            return value
        process.communicate = communicate
        with patch.object(mac.subprocess, "Popen", return_value=process), patch.object(mac.os, "killpg") as kill:
            with self.assertRaises(ValueError): mac.isolated_capture(["--apply"])
        kill.assert_called_once_with(12345, mac.signal.SIGTERM)

    def test_worker_failure_does_not_echo_raw_stderr_or_output(self):
        process = SimpleNamespace(returncode=1, communicate=lambda **_kwargs: ("synthetic unpublished text", "synthetic diagnostic"))
        with patch.object(mac.subprocess, "Popen", return_value=process):
            with self.assertRaisesRegex(ValueError, "capture_worker_unverified"):
                mac.isolated_capture(["--apply"])

    def test_stable_digest_refuses_links_and_group_writable_files(self):
        path = self.workspace / "media.mp4";path.write_bytes(RAW);path.chmod(0o600)
        self.assertEqual(mac.stable_digest(path), hashlib.sha256(RAW).hexdigest())
        path.chmod(0o660)
        with self.assertRaises(ValueError): mac.stable_digest(path)
        path.chmod(0o600);(self.workspace / "linked").symlink_to(path)
        with self.assertRaises(ValueError): mac.stable_digest(self.workspace / "linked")

    def test_worker_environment_never_keeps_ambient_secrets(self):
        with patch.dict(os.environ, {"PATH": "/trusted/bin", "SA_JSON_BASE64": "fixture", "GEMINI_API_KEY": "fixture",
                                     "THREADS_ACCESS_TOKEN": "fixture", "PYTHONPATH": "/untrusted"}, clear=True):
            mac.scrub_worker_environment()
            self.assertEqual(dict(os.environ), {"PATH": "/trusted/bin", "YTDLP_NO_PLUGINS": "1"})


if __name__ == "__main__":
    unittest.main()
