#!/usr/bin/env python3
"""Exercise the host shell using an isolated runtime and offline child doubles.

Only the fixed deployment-lock pathname is relocated in a private copy of the
shell source. The fake flock takes real OS locks; no production path, provider,
credential or network is accessed. No mock output is production evidence.
"""
from __future__ import annotations

import base64
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "scripts/run_buffered_auto_ready_host.sh"
REVISION = "a" * 40
OTHER_REVISION = "b" * 40
ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
SCRIPTS = (
    "auto_ready_draft_preflight.py", "recover_production_sheets_threads_first.py",
    "maintain_text_ready_inventory.py", "ready_inventory_diagnostics.py",
    "ready_evergreen_bank_summary.py", "run_autopilot_loop.py",
)
NO_POST_FLAGS = (
    "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_THREADS_VIDEO_POST",
    "ALLOW_REAL_X_POST", "ALLOW_MEDIA_POSTS", "ALLOW_THREADS_CAROUSEL",
    "ALLOW_THREADS_MIXED_CAROUSEL", "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT",
    "ALLOW_CLOUDINARY_UPLOAD", "ALLOW_TRANSCRIPTION_API", "ALLOW_LOCAL_TRANSCRIPTION",
    "GITHUB_MODELS_ENABLED", "MOCK_LLM", "MOCK_SHEETS", "DRY_RUN",
)
PROVIDER_KEYS = (
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
    "GITHUB_TOKEN", "GH_TOKEN", "GITHUB_MODELS_TOKEN", "GITHUB_MODELS_API_KEY",
)


def executable(path: Path, body: str) -> None:
    path.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
    path.chmod(0o700)


class FakeRuntime:
    def __init__(self, directory: str):
        self.base = Path(directory).resolve()
        self.root = self.base / "runtime"
        self.release = self.root / "releases" / REVISION
        self.shared = self.root / "shared"
        self.locks = self.shared / "locks"
        self.locks.mkdir(parents=True)
        (self.release / "scripts").mkdir(parents=True)
        (self.release / ".venv/bin").mkdir(parents=True)
        (self.release / "config").mkdir()
        (self.release / ".production-release").write_text(REVISION + "\n")
        (self.root / "current").symlink_to(self.release, target_is_directory=True)
        for script in SCRIPTS:
            (self.release / "scripts" / script).write_text("# offline placeholder\n")
        self.policy = self.release / "config/autonomous_mode.json"
        self.policy.write_text(json.dumps({
            "kill_switch": False, "production_publish_activation_approved": True,
            "auto_ready_enabled": True, "allowed_accounts": list(ACCOUNTS),
        }))
        self.config = self.shared / "runtime.env"
        self.write_config()
        self.trace = self.base / "trace.jsonl"
        self.deploy_lock = self.base / "deployment.lock"
        self.deploy_lock.touch()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.wrapper = self.base / "host.sh"
        source = HOST.read_text(encoding="utf-8")
        target = "shared_deploy_lock=/run/lock/chadult-production-deploy.lock"
        if source.count(target) != 1:
            raise AssertionError("fixed deploy-lock test relocation must be exact")
        self.wrapper.write_text(source.replace(
            target, "shared_deploy_lock=" + shlex.quote(str(self.deploy_lock)),
        ))
        executable(self.bin / "flock", """
import fcntl, json, os, sys
fd = int(sys.argv[-1])
operation = fcntl.LOCK_SH if '-s' in sys.argv else fcntl.LOCK_EX
fcntl.flock(fd, operation | fcntl.LOCK_NB)
with open(os.environ['TEST_CAPTURE'], 'a') as out:
    out.write(json.dumps({'tool': 'flock', 'fd': fd}) + '\\n')
""")
        executable(self.bin / "timeout", """
import os, sys
os.execvpe(sys.argv[2], sys.argv[2:], os.environ)
""")
        executable(self.bin / "readlink", """
import json, os, sys
resolved = os.path.realpath(sys.argv[-1])
with open(os.environ['TEST_CAPTURE'], 'a') as out:
    out.write(json.dumps({'tool': 'resolve', 'path': resolved}) + '\\n')
if os.environ.get('TEST_MOVE_CURRENT'):
    current = sys.argv[-1]
    os.unlink(current)
    os.symlink(os.environ['TEST_MOVE_CURRENT'], current)
print(resolved)
""")
        executable(self.release / ".venv/bin/python", """
import fcntl, json, os, pathlib, sys
args = sys.argv[1:]
if args and args[0] == '-B':
    args = args[1:]
name = pathlib.Path(args[0]).name
if name == '-':
    os.execv(sys.executable, [sys.executable, '-B', *args])
locks_held = []
paths = [os.environ['TEST_DEPLOY_LOCK'],
         os.environ['BUFFERED_RUNTIME_ROOT'] + '/shared/locks/sheets-io.lock',
         os.environ['BUFFERED_RUNTIME_ROOT'] + '/shared/locks/' + os.environ['TEST_ACCOUNT'] + '.lock']
for path in paths:
    with open(path, 'a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            locks_held.append(True)
        else:
            locks_held.append(False)
            fcntl.flock(handle, fcntl.LOCK_UN)
if name == 'maintain_text_ready_inventory.py':
    stage = 'bank' if '--evergreen-bank' in args else 'inventory'
elif name == 'run_autopilot_loop.py':
    stage = 'ready'
elif name == 'recover_production_sheets_threads_first.py':
    stage = 'verify'
else:
    stage = name
record = {'script': name, 'stage': stage, 'args': args[1:],
          'path': args[0], 'cwd': os.getcwd(), 'locks_held': locks_held,
          'revision': os.environ.get('CODE_REVISION'),
          'flags': {key: os.environ.get(key) for key in json.loads(os.environ['TEST_NO_POST_FLAGS'])},
          'provider_keys_present': any(os.environ.get(key) for key in json.loads(os.environ['TEST_PROVIDER_KEYS']))}
if os.environ.get('TEST_CONFIG_LOADER'):
    import runpy, types
    # Exercise actual alias precedence without reading any dotenv files.
    dotenv = types.ModuleType('dotenv')
    dotenv.load_dotenv = lambda: None
    sys.modules['dotenv'] = dotenv
    cfg = runpy.run_path(os.environ['TEST_CONFIG_LOADER'])['get_config']()
    record['resolved_sheet_id'] = cfg['sheet_id']
    record['resolved_sa_fixture'] = cfg['sa_dict']['fixture_id']
with open(os.environ['TEST_CAPTURE'], 'a') as out:
    out.write(json.dumps(record) + '\\n')
print('PRIVATE_UNPUBLISHED_QUEUE_AND_PROVIDER_DETAIL')
print('PRIVATE_UNPUBLISHED_STDERR', file=sys.stderr)
if os.environ.get('TEST_FAIL_STAGE') in (name, stage):
    raise SystemExit(23)
""")

    def write_config(self, **updates: str | None) -> None:
        values: dict[str, str | None] = {
            "AUTO_READY_WRITE_APPROVED": "true",
            "AUTO_READY_ACTIONS_DISABLED_ATTESTED": "true",
            "BEAUTY_ACTIVATION_APPROVED": "true",
            "SA_JSON_BASE64": "offline-placeholder-not-a-credential",
            "SNS_MASTER_SHEET_ID": "offline-placeholder-workbook",
            "PUBLISH_ENABLED": "true",
            "ALLOW_REAL_THREADS_POST": "true",
            "MOCK_LLM": "true",
            "GEMINI_API_KEY": "offline-paid-provider-placeholder",
            "GOOGLE_API_KEY": "offline-paid-provider-alias-placeholder",
        }
        values.update(updates)
        self.config.write_text("\n".join(
            key + "=" + shlex.quote(value)
            for key, value in values.items() if value is not None
        ) + "\n")
        self.config.chmod(0o600)

    def execute(self, *args: str, account: str = "night_scout", shell_trace: bool = False, **extra_env: str):
        env = {
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            "HOME": str(self.base),
            "BUFFERED_RUNTIME_ROOT": str(self.root),
            "TEST_CAPTURE": str(self.trace),
            "TEST_DEPLOY_LOCK": str(self.deploy_lock),
            "TEST_ACCOUNT": account,
            "TEST_NO_POST_FLAGS": json.dumps(NO_POST_FLAGS),
            "TEST_PROVIDER_KEYS": json.dumps(PROVIDER_KEYS),
            # Forged caller grants and keys must never authorize execution.
            "AUTO_READY_WRITE_APPROVED": "true",
            "AUTO_READY_ACTIONS_DISABLED_ATTESTED": "true",
            "BEAUTY_ACTIVATION_APPROVED": "true",
            "GOOGLE_API_KEY": "forged-caller-key",
            "GITHUB_TOKEN": "forged-caller-key",
        }
        env.update(extra_env)
        return subprocess.run(
            ["bash", *(["-x"] if shell_trace else []), str(self.wrapper), "--account-id", account, *args],
            cwd=self.base, env=env, capture_output=True, text=True, timeout=12,
            check=False,
        )

    def records(self):
        return [json.loads(line) for line in self.trace.read_text().splitlines()] if self.trace.exists() else []

    def children(self):
        return [row for row in self.records() if "script" in row]


APPLY = ("--apply", "--confirm-auto-ready", "--reuse-only")


class AutoReadyHostTests(unittest.TestCase):
    def test_finite_original_profile_plan_is_offline_and_not_paid_or_full_equivalence(self):
        result=self.runtime.execute('--plan','--offline-original-only')
        self.assertEqual(result.returncode,0,result.stderr)
        packet=json.loads(result.stdout)
        self.assertEqual(packet['profile'],'finite_owned_original_catalog')
        self.assertTrue(packet['generation_supported'])
        for key in ('paid_generation_supported','hosted_workflow_equivalent','would_connect','would_write','would_post'):
            self.assertFalse(packet[key])
        self.assertEqual(self.runtime.records(),[])

    def test_finite_original_profile_needs_its_own_protected_consent(self):
        result=self.runtime.execute('--apply','--confirm-auto-ready','--offline-original-only',
            AUTO_READY_OFFLINE_GENERATION_APPROVED='true')
        self.assertEqual(result.returncode,77,result.stderr)
        self.assertIn('finite-original generation approval',result.stderr)
        self.assertEqual(self.runtime.children(),[])

    def test_finite_original_and_reuse_profiles_cannot_be_combined(self):
        result=self.runtime.execute(*APPLY,'--offline-original-only')
        self.assertEqual(result.returncode,64,result.stderr)
        self.assertEqual(self.runtime.records(),[])

    def test_finite_original_profile_uses_only_offline_commands_and_no_post_ready_path(self):
        self.runtime.write_config(AUTO_READY_OFFLINE_GENERATION_APPROVED='true')
        for account in ACCOUNTS:
            with self.subTest(account=account):
                self.runtime.trace.unlink(missing_ok=True)
                result=self.runtime.execute('--apply','--confirm-auto-ready','--offline-original-only',account=account)
                self.assertEqual(result.returncode,0,result.stderr)
                children=self.runtime.children()
                inventory=next(row for row in children if row['stage']=='inventory')
                bank=next(row for row in children if row['stage']=='bank')
                ready=next(row for row in children if row['stage']=='ready')
                self.assertIn('--offline-original-only',inventory['args'])
                self.assertNotIn('--reuse-only',inventory['args'])
                self.assertIn('--bank-offline-only',bank['args'])
                self.assertNotIn('--bank-reuse-only',bank['args'])
                self.assertIn('--skip-real-post',ready['args'])
                self.assertIn('--ready-only',ready['args'])
                for row in children:
                    self.assertFalse(row['provider_keys_present'])
                    self.assertEqual(row['locks_held'],[True,True,True])
                    self.assertTrue(all(value=='false' for value in row['flags'].values()))
                self.assertIn('AUTO_READY_OFFLINE_ORIGINAL_COMPLETE',result.stdout)

    def test_finite_original_reserve_failure_cannot_claim_completion(self):
        self.runtime.write_config(AUTO_READY_OFFLINE_GENERATION_APPROVED='true')
        result=self.runtime.execute('--apply','--confirm-auto-ready','--offline-original-only',TEST_FAIL_STAGE='bank')
        self.assertEqual(result.returncode,1,result.stderr)
        self.assertNotIn('AUTO_READY_OFFLINE_ORIGINAL_COMPLETE',result.stdout)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sns-auto-ready-offline-")
        self.addCleanup(self.temp.cleanup)
        self.runtime = FakeRuntime(self.temp.name)

    def test_default_plan_never_sources_credentials_or_acquires_locks(self):
        marker = Path(self.temp.name) / "config-was-sourced"
        self.runtime.config.write_text("touch " + shlex.quote(str(marker)) + "\n")
        for account in ACCOUNTS:
            result = self.runtime.execute(account=account)
            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            self.assertEqual(plan["account_id"], account)
            for field in ("would_connect", "would_write", "would_post", "generation_supported", "hosted_workflow_equivalent"):
                self.assertIs(plan[field], False)
        self.assertFalse(marker.exists())
        self.assertEqual(self.runtime.records(), [])

    def test_exact_account_scopes_and_arguments(self):
        for account in ("all", "", "unknown", "../night_scout", "night_scout;echo unsafe"):
            self.assertEqual(self.runtime.execute(account=account).returncode, 64)
        for args in (
            ("--apply",), ("--dry-run",), ("--plan", "--confirm-auto-ready"),
            (*APPLY, "--confirm-readonly"), ("--dry-run", "--confirm-readonly", "--reuse-only"),
            ("--max-ready", "4"), ("--max-bank-allocations", "7"),
            ("--horizon-hours", "168"), ("--trigger", "github_schedule_recovery"),
            ("--trigger", "xserver_cron", "--horizon-hours", "6"),
            ("--dry-run", "--plan"), ("--allow-paid-generation",),
        ):
            with self.subTest(args=args):
                self.assertEqual(self.runtime.execute(*args).returncode, 64)
        self.assertEqual(self.runtime.children(), [])

    def test_ordinary_apply_fails_before_credentials_or_writes(self):
        result = self.runtime.execute("--apply", "--confirm-auto-ready")
        self.assertEqual(result.returncode, 78)
        self.assertIn("full-generation host mode unavailable", result.stderr)
        self.assertEqual(self.runtime.records(), [])

    def test_missing_or_forged_protected_grants_are_denied(self):
        for missing in ("AUTO_READY_WRITE_APPROVED", "AUTO_READY_ACTIONS_DISABLED_ATTESTED"):
            with self.subTest(missing=missing):
                self.runtime.write_config(**{missing: None})
                result = self.runtime.execute(*APPLY)
                self.assertEqual(result.returncode, 77, result.stderr)
                self.assertEqual(self.runtime.children(), [])
        self.runtime.write_config(AUTO_READY_WRITE_APPROVED="TRUE")
        self.assertEqual(self.runtime.execute(*APPLY).returncode, 77)

    def test_caller_selected_approval_file_cannot_grant_permission(self):
        self.runtime.write_config(AUTO_READY_WRITE_APPROVED=None)
        alternate = Path(self.temp.name) / "caller.env"
        alternate.write_text("AUTO_READY_WRITE_APPROVED=true\nAUTO_READY_ACTIONS_DISABLED_ATTESTED=true\n")
        alternate.chmod(0o600)
        result = self.runtime.execute(*APPLY, BUFFERED_RUNTIME_ENV_FILE=str(alternate))
        self.assertEqual(result.returncode, 77)
        self.assertEqual(self.runtime.children(), [])

    def test_real_loader_uses_protected_spreadsheet_despite_caller_legacy_alias(self):
        fixture = base64.b64encode(json.dumps({"fixture_id": "protected-sa"}).encode()).decode()
        self.runtime.write_config(SA_JSON_BASE64=fixture, SNS_MASTER_SHEET_ID=None,
                                  SPREADSHEET_ID="protected-spreadsheet")
        result = self.runtime.execute(*APPLY,
                                      NOTE_MASTER_SHEET_ID="forged-caller-workbook",
                                      GCP_SA_JSON=json.dumps({"fixture_id": "forged-caller-sa"}),
                                      TEST_CONFIG_LOADER=str(ROOT / "src/config_loader.py"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.runtime.children())
        for row in self.runtime.children():
            self.assertEqual(row["resolved_sheet_id"], "protected-spreadsheet")
            self.assertEqual(row["resolved_sa_fixture"], "protected-sa")

    def test_caller_raw_or_unsupported_path_credentials_never_replace_protected_credentials(self):
        for unsupported_path in (None, "/unused/unsupported-credentials.json"):
            with self.subTest(unsupported_path=unsupported_path):
                self.runtime.write_config(SA_JSON_BASE64=None, GCP_SA_JSON_BASE64=None,
                                          GCP_SA_JSON=None, GOOGLE_APPLICATION_CREDENTIALS=unsupported_path)
                result = self.runtime.execute(*APPLY, GCP_SA_JSON=json.dumps({"fixture_id": "caller"}))
                self.assertEqual(result.returncode, 78, result.stderr)
                self.assertIn("protected Sheets configuration", result.stderr)
                self.assertEqual(self.runtime.children(), [])

    def test_real_loader_accepts_protected_raw_credentials_and_legacy_sheet_alias(self):
        self.runtime.write_config(SA_JSON_BASE64=None, SNS_MASTER_SHEET_ID=None,
                                  GCP_SA_JSON=json.dumps({"fixture_id": "protected-raw-sa"}),
                                  NOTE_MASTER_SHEET_ID="protected-legacy-sheet")
        result = self.runtime.execute(*APPLY,
                                      SNS_MASTER_SHEET_ID="forged-caller-workbook",
                                      GCP_SA_JSON=json.dumps({"fixture_id": "forged-caller-sa"}),
                                      TEST_CONFIG_LOADER=str(ROOT / "src/config_loader.py"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.runtime.children())
        for row in self.runtime.children():
            self.assertEqual(row["resolved_sheet_id"], "protected-legacy-sheet")
            self.assertEqual(row["resolved_sa_fixture"], "protected-raw-sa")

    def test_beauty_write_requires_separate_protected_activation(self):
        self.runtime.write_config(BEAUTY_ACTIVATION_APPROVED=None)
        result = self.runtime.execute(*APPLY, account="beauty_account")
        self.assertEqual(result.returncode, 77)
        self.assertIn("Beauty", result.stderr)
        self.assertEqual(self.runtime.children(), [])

    def test_private_runtime_and_real_lock_boundary_fail_closed(self):
        self.runtime.config.chmod(0o644)
        self.assertEqual(self.runtime.execute(*APPLY).returncode, 77)
        self.runtime.config.chmod(0o600)
        self.runtime.deploy_lock.unlink()
        self.runtime.deploy_lock.symlink_to(self.runtime.config)
        self.assertEqual(self.runtime.execute(*APPLY).returncode, 78)
        self.assertEqual(self.runtime.children(), [])

    def test_wrong_release_marker_rejects_before_any_child(self):
        (self.runtime.release / ".production-release").write_text(OTHER_REVISION)
        result = self.runtime.execute(*APPLY)
        self.assertEqual(result.returncode, 78)
        self.assertEqual(self.runtime.children(), [])
        rows = self.runtime.records()
        self.assertEqual(rows[0], {"tool": "flock", "fd": 8})
        self.assertEqual(rows[1]["tool"], "resolve")

    def test_missing_release_or_entrypoint_rejects(self):
        (self.runtime.release / "scripts/run_autopilot_loop.py").unlink()
        self.assertEqual(self.runtime.execute(*APPLY).returncode, 78)
        self.assertEqual(self.runtime.children(), [])

    def test_trusted_venv_interpreter_toolcache_symlink_is_executable(self):
        toolcache = self.runtime.base / "approved-toolcache/bin"
        toolcache.mkdir(parents=True)
        interpreter = self.runtime.release / ".venv/bin/python"
        target = toolcache / "python3.11"
        interpreter.rename(target)
        interpreter.symlink_to(target)
        result = self.runtime.execute(*APPLY)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(interpreter.is_symlink())
        self.assertTrue(self.runtime.children())
        self.assertIn("AUTO_READY_REUSE_ONLY_COMPLETE", result.stdout)

    def test_shell_tracing_stops_before_protected_config_is_sourced(self):
        sentinel = "PRIVATE_CONFIG_TRACE_SENTINEL"
        self.runtime.write_config(SA_JSON_BASE64=sentinel, GEMINI_API_KEY=sentinel)
        for settings in ({"shell_trace": True}, {"SHELLOPTS": "xtrace"}):
            with self.subTest(settings=settings):
                result = self.runtime.execute(*APPLY, **settings)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn(sentinel, result.stdout + result.stderr)
                self.assertNotIn("source ", result.stderr)
                self.assertIn("AUTO_READY_REUSE_ONLY_COMPLETE", result.stdout)

    def test_retargeted_current_cannot_change_pinned_execution(self):
        other = self.runtime.root / "releases" / OTHER_REVISION
        other.mkdir()
        result = self.runtime.execute(*APPLY, TEST_MOVE_CURRENT=str(other))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.runtime.root / "current").resolve(), other)
        self.assertTrue(self.runtime.children())
        for child in self.runtime.children():
            self.assertTrue(child["path"].startswith(str(self.runtime.release) + "/"))
            self.assertEqual(child["cwd"], str(self.runtime.release))
            self.assertEqual(child["revision"], REVISION)

    def test_reuse_apply_preserves_stage_order_locks_flags_and_private_output(self):
        result = self.runtime.execute(*APPLY, "--max-ready", "3", "--max-bank-allocations", "6")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("PRIVATE_UNPUBLISHED", result.stdout + result.stderr)
        self.assertIn("hosted_workflow_equivalent=false", result.stdout)
        children = self.runtime.children()
        self.assertEqual([row["stage"] for row in children], [
            "auto_ready_draft_preflight.py", "verify", "inventory",
            "ready_inventory_diagnostics.py", "bank", "ready_evergreen_bank_summary.py",
            "ready", "verify",
        ])
        for child in children:
            self.assertEqual(child["locks_held"], [True, True, True])
            self.assertEqual(child["flags"], dict.fromkeys(NO_POST_FLAGS, "false"))
            self.assertFalse(child["provider_keys_present"])
            if child["stage"] not in ("ready_evergreen_bank_summary.py",):
                self.assertIn("night_scout", child["args"])
        inventory = next(row for row in children if row["stage"] == "inventory")
        self.assertIn("--reuse-only", inventory["args"])
        self.assertIn("--max-bank-allocations", inventory["args"])
        bank = next(row for row in children if row["stage"] == "bank")
        self.assertIn("--bank-reuse-only", bank["args"])
        ready = next(row for row in children if row["stage"] == "ready")
        self.assertEqual(ready["args"], [
            "--apply", "--confirm-run", "--account-id", "night_scout", "--auto-ready",
            "--ready-only", "--max-ready", "3", "--max-posts", "1", "--use-sheets",
            "--skip-real-post", "--summary-only",
        ])
        self.assertEqual(list(self.runtime.shared.glob("auto-ready.*")), [])

    def test_all_three_accounts_have_guarded_reuse_profile(self):
        for account in ACCOUNTS:
            with self.subTest(account=account):
                result = self.runtime.execute(*APPLY, account=account)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_six_hour_profile_skips_bank_without_claiming_full_parity(self):
        result = self.runtime.execute(*APPLY, "--horizon-hours", "6")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("bank", [row["stage"] for row in self.runtime.children()])
        self.assertIn("hosted_workflow_equivalent=false", result.stdout)

    def test_confirmed_readonly_preview_never_invokes_writer(self):
        self.runtime.write_config(AUTO_READY_WRITE_APPROVED=None, AUTO_READY_ACTIONS_DISABLED_ATTESTED=None)
        result = self.runtime.execute("--dry-run", "--confirm-readonly")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([row["stage"] for row in self.runtime.children()], [
            "inventory", "ready_inventory_diagnostics.py",
        ])
        inventory = self.runtime.children()[0]
        self.assertIn("--dry-run", inventory["args"])
        self.assertNotIn("--apply", inventory["args"])
        self.assertEqual(inventory["locks_held"], [True, True, True])
        self.assertFalse(inventory["provider_keys_present"])

    def test_preflight_and_inventory_failure_stop_later_writers(self):
        for stage in ("auto_ready_draft_preflight.py", "inventory"):
            with self.subTest(stage=stage):
                self.runtime.trace.unlink(missing_ok=True)
                result = self.runtime.execute(*APPLY, TEST_FAIL_STAGE=stage)
                self.assertEqual(result.returncode, 23)
                stages = [row["stage"] for row in self.runtime.children()]
                self.assertNotIn("ready", stages)
                self.assertNotIn("bank", stages)
                self.assertNotIn("PRIVATE_UNPUBLISHED", result.stdout + result.stderr)

    def test_config_kill_switch_blocks_before_sheets_or_writer(self):
        policy = json.loads(self.runtime.policy.read_text())
        policy["kill_switch"] = True
        self.runtime.policy.write_text(json.dumps(policy))
        result = self.runtime.execute(*APPLY)
        self.assertEqual(result.returncode, 78)
        self.assertEqual([row["stage"] for row in self.runtime.children()], ["auto_ready_draft_preflight.py"])

    def test_bank_failure_continues_strict_delivery_but_remains_failure(self):
        result = self.runtime.execute(*APPLY, TEST_FAIL_STAGE="bank")
        self.assertEqual(result.returncode, 1, result.stderr)
        stages = [row["stage"] for row in self.runtime.children()]
        self.assertIn("ready", stages)
        self.assertEqual(stages.count("verify"), 3)
        self.assertIn("AUTO_READY_EVERGREEN_RESERVE_INCOMPLETE", result.stderr)
        self.assertNotIn("AUTO_READY_REUSE_ONLY_COMPLETE", result.stdout)

    def test_strict_ready_failure_cannot_be_reported_as_complete(self):
        result = self.runtime.execute(*APPLY, TEST_FAIL_STAGE="ready")
        self.assertEqual(result.returncode, 23)
        self.assertNotIn("AUTO_READY_REUSE_ONLY_COMPLETE", result.stdout)
        self.assertEqual(self.runtime.children()[-1]["stage"], "ready")


if __name__ == "__main__":
    unittest.main()
