#!/usr/bin/env python3
"""Offline shell integration: fake immutable runtime, real advisory locks.

No credentials or providers are used. Fixture executables record the actual
CLI/environment and test lock ownership across the complete host invocation.
"""
from __future__ import annotations

import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "scripts/run_buffered_acquisition_host.sh"
SHA = "a" * 40
OTHER_SHA = "b" * 40
OFF_GATES = (
    "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
    "ALLOW_REAL_THREADS_VIDEO_POST", "ALLOW_MEDIA_POSTS",
    "ALLOW_THREADS_CAROUSEL", "ALLOW_THREADS_MIXED_CAROUSEL",
    "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT", "ALLOW_CLOUDINARY_UPLOAD",
    "ALLOW_TRANSCRIPTION_API", "ALLOW_LOCAL_TRANSCRIPTION",
)
AI_KEYS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "FIRECRAWL_API_KEY")
SHEETS_KEYS = (
    "GCP_SA_JSON_BASE64", "SA_JSON_BASE64", "SPREADSHEET_ID",
    "SNS_MASTER_SHEET_ID", "NOTE_MASTER_SHEET_ID", "GCP_SA_JSON", "GOOGLE_APPLICATION_CREDENTIALS",
)
IMPORT_KEYS = ("PYTHONPATH", "PYTHONHOME")

FAKE_FLOCK = r'''
import fcntl, json, os, pathlib, sys
fd = int(sys.argv[-1])
with open(os.environ["FAKE_EVENTS"], "a") as out:
    out.write(json.dumps({"event": "flock", "fd": fd}) + "\n")
if os.environ.get("FAKE_BUSY_FD") == str(fd):
    raise SystemExit(75)
if fd == 8 and os.environ.get("FAKE_PROMOTE_AT_LOCK"):
    current = pathlib.Path(os.environ["BUFFERED_RUNTIME_ROOT"]) / "current"
    current.unlink()
    current.symlink_to(os.environ["FAKE_PROMOTE_AT_LOCK"])
operation = fcntl.LOCK_SH if "-s" in sys.argv else fcntl.LOCK_EX
try:
    fcntl.flock(fd, operation | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit(75)
'''

FAKE_READLINK = r'''
import json, os, pathlib, sys
resolved = str(pathlib.Path(sys.argv[-1]).resolve())
with open(os.environ["FAKE_EVENTS"], "a") as out:
    out.write(json.dumps({"event": "resolve", "path": resolved}) + "\n")
if os.environ.get("FAKE_MOVE_AFTER_RESOLVE"):
    current = pathlib.Path(sys.argv[-1])
    current.unlink()
    current.symlink_to(os.environ["FAKE_MOVE_AFTER_RESOLVE"])
print(resolved)
'''

FAKE_RUNTIME = r'''
import fcntl, json, os, pathlib, sys
keys = json.loads(os.environ["FAKE_ENV_KEYS"])
locks = []
for filename in json.loads(os.environ["FAKE_LOCK_FILES"]):
    with open(filename, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            locks.append(True)
        else:
            locks.append(False)
row = {"argv": sys.argv[1:], "env": {key: os.environ.get(key) for key in keys},
       "locks_held": locks}
if os.environ.get("FAKE_CONFIG_LOADER"):
    import runpy, types
    # Exercise the real loader without allowing dotenv to search local files.
    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None
    sys.modules["dotenv"] = dotenv
    cfg = runpy.run_path(os.environ["FAKE_CONFIG_LOADER"])["get_config"]()
    row["resolved_sheet_id"] = cfg["sheet_id"]
    row["resolved_sa_fixture"] = cfg["sa_dict"]["fixture_id"]
with open(os.environ["FAKE_CALLS"], "a") as out:
    out.write(json.dumps(row) + "\n")
if "--apply" in sys.argv:
    raise SystemExit(int(os.environ.get("FAKE_APPLY_EXIT", "0")))
raise SystemExit(int(os.environ.get("FAKE_PLAN_EXIT", "0")))
'''


class AcquisitionHostTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="sns-acquisition-offline-")
        self.addCleanup(self.temporary.cleanup)
        # Canonical path also makes /tmp -> /private/tmp on macOS explicit.
        self.base = Path(self.temporary.name).resolve()
        self.runtime = self.base / "runtime"
        self.locks = self.runtime / "shared/locks"
        self.locks.mkdir(parents=True)
        self.runtime_env = self.runtime / "shared/runtime.env"
        self.deploy_lock = self.base / "deploy.lock"
        self.deploy_lock.touch()
        self.calls = self.base / "calls.jsonl"
        self.events = self.base / "events.jsonl"
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.release = self.make_release(SHA)
        (self.runtime / "current").symlink_to(self.release)
        self.wrapper = self.base / "host.sh"
        source = HOST.read_text(encoding="utf-8")
        self.assertEqual(source.count('shared_deploy_lock="/run/lock/chadult-production-deploy.lock"'), 1)
        self.wrapper.write_text(source.replace(
            'shared_deploy_lock="/run/lock/chadult-production-deploy.lock"',
            f'shared_deploy_lock="{self.deploy_lock}"',
        ), encoding="utf-8")
        self.executable(self.bin / "flock", FAKE_FLOCK)
        self.executable(self.bin / "readlink", FAKE_READLINK)
        self.executable(self.bin / "timeout", "import os, sys\nos.execv(sys.argv[2], sys.argv[2:])\n")
        self.executable(self.bin / "stat", f'''
import os, sys
if os.environ.get("FAKE_OWNER_UID") and "%u" in sys.argv:
    print(os.environ["FAKE_OWNER_UID"])
else:
    os.execv({shutil.which("stat")!r}, [{shutil.which("stat")!r}, *sys.argv[1:]])
''')
        self.write_consent()

    def executable(self, path: Path, body: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Isolate fake executables themselves so hostile caller import hooks
        # cannot interfere before the wrapper reaches its protected-env gate.
        path.write_text(f"#!{sys.executable} -I\n{body}", encoding="utf-8")
        path.chmod(0o755)

    def make_release(self, sha: str) -> Path:
        release = self.runtime / "releases" / sha
        (release / "scripts").mkdir(parents=True)
        (release / ".production-release").write_text(sha + "\n", encoding="utf-8")
        for name in ("acquire_approved_source_posts.py", "acquire_approved_source_posts_failsoft.py"):
            (release / "scripts" / name).write_text("# offline placeholder\n", encoding="utf-8")
        self.executable(release / ".venv/bin/python", FAKE_RUNTIME)
        return release

    def write_consent(self, **overrides: str | None) -> None:
        values = {
            "ACQUISITION_WRITE_APPROVED": "true",
            "ACQUISITION_ACTIONS_DISABLED_ATTESTED": "true",
            "ACQUISITION_APPROVED_ACCOUNT": "night_scout",
            "ACQUISITION_APPROVED_SCOPE": "approved",
            "ACQUISITION_APPROVED_PLATFORM": "x",
            "ACQUISITION_APPROVED_RELEASE": SHA,
            "SA_JSON_BASE64": "protected-offline-sa-sentinel",
            "SPREADSHEET_ID": "protected-offline-sheet-sentinel",
            **{key: "true" for key in OFF_GATES},
            **{key: "offline-placeholder" for key in AI_KEYS},
        }
        values.update(overrides)
        self.runtime_env.write_text("".join(
            f"{key}={shlex.quote(value)}\n" for key, value in values.items() if value is not None
        ), encoding="utf-8")
        self.runtime_env.chmod(0o600)

    def execute(self, *args: str, account: str = "night_scout", scope: str = "approved",
                platform: str = "x", extra_env: dict[str, str] | None = None):
        env = {
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            "BUFFERED_RUNTIME_ROOT": str(self.runtime),
            "FAKE_CALLS": str(self.calls), "FAKE_EVENTS": str(self.events),
            "FAKE_ENV_KEYS": json.dumps([
                *OFF_GATES, *AI_KEYS, *SHEETS_KEYS, *IMPORT_KEYS,
                "BEAUTY_PRODUCTION_ENABLED",
                "CODE_REVISION", "PRODUCTION_RUNTIME_RELEASE", "PRODUCTION_TRIGGER",
            ]),
            "FAKE_LOCK_FILES": json.dumps([
                str(self.deploy_lock), str(self.locks / "sheets-io.lock"),
                str(self.locks / f"{account}.lock"),
            ]),
        }
        env.update(extra_env or {})
        return subprocess.run([
            "bash", str(self.wrapper), "--account-id", account, "--scope", scope,
            "--platform", platform, *args,
        ], cwd=ROOT, env=env, capture_output=True, text=True, check=False, timeout=10)

    def recorded(self, path: Path | None = None) -> list[dict]:
        target = path or self.calls
        return [json.loads(line) for line in target.read_text().splitlines()] if target.exists() else []

    def apply(self, **kwargs):
        return self.execute("--apply", "--confirm-acquisition", **kwargs)

    def test_default_plan_has_exact_scope_without_runtime_or_env_access(self):
        shutil.rmtree(self.runtime)
        for account in ("night_scout", "liver_manager", "beauty_account"):
            for platform in ("x", "youtube"):
                with self.subTest(account=account, platform=platform):
                    result = self.execute(account=account, scope="reference-only", platform=platform)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    payload = json.loads(result.stdout)
                    self.assertEqual(payload["status"], "PLAN_ONLY")
                    self.assertEqual(payload["account_id"], account)
                    self.assertEqual(payload["scope"], "reference-only")
                    self.assertIn("--reference-only", payload["command"])
                    for key in ("would_connect", "would_write", "would_post", "physical_media", "hosted_workflow_parity"):
                        self.assertFalse(payload[key])
        self.assertFalse(self.events.exists())
        self.assertFalse(self.calls.exists())

    def test_argument_scope_and_mode_denials_are_offline(self):
        cases = [
            {"account": value} for value in ("all", "unknown", "../night_scout", "")
        ] + [
            {"platform": value} for value in ("all", "threads", "tiktok", "")
        ] + [{"scope": ""}, {"scope": "automatic"}, {"account": "beauty_account"}]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.execute(**kwargs).returncode, 64)
        for args in (
            ("--apply",), ("--confirm-acquisition",), ("--plan", "--apply"),
            ("--apply", "--plan"), ("--plan", "--plan"),
            ("--apply", "--confirm-acquisition", "--confirm-acquisition"),
            ("--trigger", "github_schedule_recovery"), ("--dry-run",),
            ("--verify-network",), ("--shadow",), ("--force-backfill",),
            ("--scope", "reference-only"), ("--platform", "youtube"),
        ):
            with self.subTest(args=args):
                self.assertEqual(self.execute(*args).returncode, 64)
        self.assertFalse(self.events.exists())

    def test_scan_cap_is_bounded_and_never_shell_interpolated(self):
        for cap in ("0", "31", "-1", "01", "1.0", "", "2; touch injected"):
            with self.subTest(cap=cap):
                self.assertEqual(self.execute("--max-posts", cap).returncode, 64)
        for cap in ("1", "12", "30"):
            self.assertEqual(json.loads(self.execute("--max-posts", cap).stdout)["max_posts_per_source"], int(cap))

    def test_protected_consent_cannot_be_spoofed_by_caller_or_env_override(self):
        for key in ("ACQUISITION_WRITE_APPROVED", "ACQUISITION_ACTIONS_DISABLED_ATTESTED"):
            with self.subTest(key=key):
                self.write_consent(**{key: None})
                result = self.apply(extra_env={key: "true", "BUFFERED_RUNTIME_ENV_FILE": "/unused/caller.env"})
                self.assertEqual(result.returncode, 77, result.stderr)
                self.assertEqual(self.recorded(), [])
        for key, wrong in (
            ("ACQUISITION_APPROVED_ACCOUNT", "liver_manager"),
            ("ACQUISITION_APPROVED_SCOPE", "reference-only"),
            ("ACQUISITION_APPROVED_PLATFORM", "youtube"),
            ("ACQUISITION_APPROVED_RELEASE", OTHER_SHA),
        ):
            with self.subTest(key=key):
                self.write_consent(**{key: wrong})
                self.assertEqual(self.apply(extra_env={key: "night_scout"}).returncode, 77)
        self.assertEqual(self.recorded(), [])

    def test_apply_records_one_plan_one_write_and_all_locks_and_disabled_operations(self):
        result = self.execute("--max-posts", "30", "--trigger", "xserver_cron", "--apply", "--confirm-acquisition")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.recorded()
        self.assertEqual(len(calls), 2)
        expected = [str(self.release / "scripts/acquire_approved_source_posts_failsoft.py"),
                    "--account-id", "night_scout", "--platform", "x", "--max-posts", "30"]
        self.assertEqual(calls[0]["argv"], expected + ["--dry-run"])
        self.assertEqual(calls[1]["argv"], expected + ["--apply", "--confirm-acquisition"])
        for row in calls:
            self.assertEqual(row["locks_held"], [True, True, True])
            self.assertEqual(row["env"]["CODE_REVISION"], SHA)
            self.assertEqual(row["env"]["PRODUCTION_RUNTIME_RELEASE"], str(self.release))
            self.assertEqual(row["env"]["PRODUCTION_TRIGGER"], "xserver_cron")
            self.assertEqual(row["env"]["BEAUTY_PRODUCTION_ENABLED"], "false")
            self.assertTrue(all(row["env"][key] == "false" for key in OFF_GATES))
            self.assertTrue(all(row["env"][key] == "" for key in AI_KEYS))
        events = self.recorded(self.events)
        self.assertEqual(events[0], {"event": "flock", "fd": 8})
        self.assertEqual(events[1]["event"], "resolve")

    def test_caller_credentials_and_import_hooks_cannot_replace_protected_config(self):
        caller = {key: "untrusted-caller-sentinel" for key in (*SHEETS_KEYS, *IMPORT_KEYS, *AI_KEYS)}
        for missing in (
            {"SA_JSON_BASE64": None},
            {"SPREADSHEET_ID": None},
        ):
            with self.subTest(missing=missing):
                self.write_consent(**missing)
                result = self.apply(extra_env=caller)
                self.assertEqual(result.returncode, 78, result.stderr)
                self.assertIn("protected Sheets configuration", result.stderr)
                self.assertEqual(self.recorded(), [])
        self.write_consent()
        result = self.apply(extra_env=caller)
        self.assertEqual(result.returncode, 0, result.stderr)
        for row in self.recorded():
            self.assertEqual(row["env"]["SA_JSON_BASE64"], "protected-offline-sa-sentinel")
            self.assertEqual(row["env"]["SPREADSHEET_ID"], "protected-offline-sheet-sentinel")
            for key in ("GCP_SA_JSON_BASE64", "SNS_MASTER_SHEET_ID", "GOOGLE_APPLICATION_CREDENTIALS", *IMPORT_KEYS):
                self.assertIsNone(row["env"][key], key)
            self.assertTrue(all(row["env"][key] == "" for key in AI_KEYS))

    def test_real_loader_uses_protected_spreadsheet_despite_caller_legacy_alias(self):
        fixture = base64.b64encode(json.dumps({"fixture_id": "protected-sa"}).encode()).decode()
        self.write_consent(SA_JSON_BASE64=fixture)
        result = self.apply(extra_env={
            "NOTE_MASTER_SHEET_ID": "forged-caller-workbook",
            "GCP_SA_JSON": json.dumps({"fixture_id": "forged-caller-sa"}),
            "FAKE_CONFIG_LOADER": str(ROOT / "src/config_loader.py"),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.recorded()), 2)
        for row in self.recorded():
            self.assertEqual(row["resolved_sheet_id"], "protected-offline-sheet-sentinel")
            self.assertEqual(row["resolved_sa_fixture"], "protected-sa")
            self.assertIsNone(row["env"]["NOTE_MASTER_SHEET_ID"])
            self.assertIsNone(row["env"]["GCP_SA_JSON"])

    def test_caller_raw_or_unsupported_path_credentials_never_replace_protected_credentials(self):
        for unsupported_path in (None, "/unused/unsupported-credentials.json"):
            with self.subTest(unsupported_path=unsupported_path):
                self.write_consent(SA_JSON_BASE64=None, GCP_SA_JSON_BASE64=None,
                                   GCP_SA_JSON=None, GOOGLE_APPLICATION_CREDENTIALS=unsupported_path)
                result = self.apply(extra_env={"GCP_SA_JSON": json.dumps({"fixture_id": "caller"})})
                self.assertEqual(result.returncode, 78, result.stderr)
                self.assertIn("protected Sheets configuration", result.stderr)
                self.assertEqual(self.recorded(), [])

    def test_real_loader_accepts_protected_raw_credentials_and_legacy_sheet_alias(self):
        self.write_consent(SA_JSON_BASE64=None, GCP_SA_JSON=json.dumps({"fixture_id": "protected-raw-sa"}),
                           SPREADSHEET_ID=None, NOTE_MASTER_SHEET_ID="protected-legacy-sheet")
        result = self.apply(extra_env={
            "SNS_MASTER_SHEET_ID": "forged-caller-workbook",
            "GCP_SA_JSON": json.dumps({"fixture_id": "forged-caller-sa"}),
            "FAKE_CONFIG_LOADER": str(ROOT / "src/config_loader.py"),
        })
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.recorded()), 2)
        for row in self.recorded():
            self.assertEqual(row["resolved_sheet_id"], "protected-legacy-sheet")
            self.assertEqual(row["resolved_sa_fixture"], "protected-raw-sa")

    def test_reference_only_preserves_explicit_beauty_activation(self):
        for account in ("liver_manager", "beauty_account"):
            with self.subTest(account=account):
                self.calls.unlink(missing_ok=True)
                self.write_consent(ACQUISITION_APPROVED_ACCOUNT=account,
                                   ACQUISITION_APPROVED_SCOPE="reference-only",
                                   ACQUISITION_APPROVED_PLATFORM="youtube",
                                   BEAUTY_ACTIVATION_APPROVED="yes")
                result = self.apply(account=account, scope="reference-only", platform="youtube")
                self.assertEqual(result.returncode, 0, result.stderr)
                for row in self.recorded():
                    self.assertIn("--reference-only", row["argv"])
                    self.assertEqual(row["env"]["BEAUTY_PRODUCTION_ENABLED"],
                                     "true" if account == "beauty_account" else "false")
        self.calls.unlink()
        self.write_consent(ACQUISITION_APPROVED_ACCOUNT="beauty_account",
                           ACQUISITION_APPROVED_SCOPE="reference-only")
        result = self.apply(account="beauty_account", scope="reference-only",
                            extra_env={"BEAUTY_ACTIVATION_APPROVED": "true",
                                       "BEAUTY_PRODUCTION_ENABLED": "true"})
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertEqual(self.recorded(), [])

    def test_current_moved_before_lock_is_resolved_after_lock_and_requires_new_consent(self):
        other = self.make_release(OTHER_SHA)
        result = self.apply(extra_env={"FAKE_PROMOTE_AT_LOCK": str(other)})
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertEqual(self.recorded(), [])
        self.assertEqual(self.recorded(self.events)[1]["path"], str(other))

    def test_current_move_after_resolution_cannot_change_validated_execution(self):
        other = self.make_release(OTHER_SHA)
        result = self.apply(extra_env={"FAKE_MOVE_AFTER_RESOLVE": str(other)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.runtime / "current").resolve(), other)
        self.assertEqual(len(self.recorded()), 2)
        for row in self.recorded():
            self.assertEqual(row["argv"][0], str(self.release / "scripts/acquire_approved_source_posts_failsoft.py"))
            self.assertEqual(row["env"]["CODE_REVISION"], SHA)

    def test_preflight_rejects_invalid_release_and_unprotected_environment(self):
        marker = self.release / ".production-release"
        marker.write_text(OTHER_SHA, encoding="utf-8")
        self.assertEqual(self.apply().returncode, 78)
        marker.write_text(SHA, encoding="utf-8")
        self.runtime_env.chmod(0o644)
        self.assertEqual(self.apply().returncode, 77)
        self.runtime_env.chmod(0o600)
        actual_env = self.base / "linked.env"
        self.runtime_env.rename(actual_env)
        self.runtime_env.symlink_to(actual_env)
        self.assertEqual(self.apply().returncode, 78)
        self.assertEqual(self.recorded(), [])

    def test_shared_parent_symlink_and_untrusted_config_owner_fail_before_runtime(self):
        result = self.apply(extra_env={"FAKE_OWNER_UID": str(os.geteuid() + 1)})
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertIn("owner-protected 0600", result.stderr)
        self.assertEqual(self.recorded(), [])
        shared = self.runtime / "shared"
        actual_shared = self.runtime / "real-shared"
        shared.rename(actual_shared)
        shared.symlink_to(actual_shared)
        result = self.apply()
        self.assertEqual(result.returncode, 78, result.stderr)
        self.assertIn("protected runtime environment", result.stderr)
        self.assertEqual(self.recorded(), [])

    def test_locked_or_linked_lock_denials_do_not_launch_runtime(self):
        for fd in ("8", "9", "7"):
            with self.subTest(fd=fd):
                self.assertEqual(self.apply(extra_env={"FAKE_BUSY_FD": fd}).returncode, 75)
                self.assertEqual(self.recorded(), [])
        (self.locks / "sheets-io.lock").unlink()
        (self.locks / "sheets-io.lock").symlink_to(self.deploy_lock)
        self.assertEqual(self.apply().returncode, 78)

    def test_critical_failure_and_unknown_write_exit_propagate_without_retry(self):
        result = self.apply(extra_env={"FAKE_PLAN_EXIT": "19"})
        self.assertEqual(result.returncode, 19, result.stderr)
        self.assertEqual(len(self.recorded()), 1)
        self.assertIn("--dry-run", self.recorded()[0]["argv"])
        self.calls.unlink()
        result = self.apply(extra_env={"FAKE_APPLY_EXIT": "23"})
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertIn("do not retry blindly", result.stderr)
        self.assertEqual(len(self.recorded()), 2)
        self.assertNotIn("[OK]", result.stdout)

    def test_source_uses_existing_failsoft_cli_without_workflow_or_physical_actions(self):
        source = HOST.read_text(encoding="utf-8")
        self.assertIn("acquire_approved_source_posts_failsoft.py", source)
        for forbidden in ("gh workflow", "crontab", "systemctl", "git push", "run_media_production_pipeline.py"):
            self.assertNotIn(forbidden, source)
        x_adapter = (ROOT / "src/acquisition/x_gallerydl.py").read_text(encoding="utf-8")
        self.assertIn('"--no-download"', x_adapter)
        for path in ("ytdlp.py", "enrichment.py"):
            adapter = (ROOT / "src/acquisition" / path).read_text(encoding="utf-8")
            self.assertIn('"skip_download": True', adapter)
            self.assertIn("download=False", adapter)


if __name__ == "__main__":
    unittest.main()
