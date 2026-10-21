#!/usr/bin/env python3
"""No-production-I/O SNS-only storage-lifecycle audit regression suite."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sns_storage_lifecycle_audit import (
    StorageAuditBlocked, audited_release_inventory, audit,
    MIN_STAGE_FREE_BYTES, MIN_POST_STAGE_FREE_BYTES,
)

C = "a" * 40
P = "b" * 40
E = "c" * 40
O = "d" * 40
S = "e" * 40


class StorageLifecycleReadOnly(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix="sns-lifecycle-")
        self.addCleanup(work.cleanup)
        base = Path(work.name)
        self.runner = base / "sns-growth-engine"
        self.runner.mkdir()
        self.data = base / "sns-data"
        self.data.mkdir()
        self.root = self.runner / ".buffered-runtime"
        self.releases = self.root / "releases"
        self.releases.mkdir(parents=True)
        (self.root / "shared").mkdir()
        now = time.time()
        self.now = now
        for sha, age in ((C, 1), (P, 2), (E, 3), (O, 15), (S, 16)):
            self.release(sha, age)
        (self.root / "current").symlink_to(self.releases / C)
        (self.root / "previous").symlink_to(self.releases / P)

    def release(self, sha, age, *, healthy=True):
        item = self.releases / sha
        item.mkdir()
        (item / ".production-release").write_text(sha, encoding="ascii")
        if healthy:
            executable = item / ".venv" / "bin"
            executable.mkdir(parents=True)
            (executable / "python").symlink_to(sys.executable)
        os.utime(item, (self.now - age * 86400, self.now - age * 86400))
        return item

    def test_read_only_3_recovery_layers_and_one_explicit_old_candidate(self):
        before = {p.name for p in self.releases.iterdir()}
        report = audited_release_inventory(self.root, now=self.now)
        self.assertEqual(report["pointers"]["current"], C)
        self.assertEqual(report["pointers"]["previous"], P)
        self.assertIsNone(report["pointers"]["pending"])
        self.assertEqual(report["emergency_recovery_sha"], E)
        self.assertEqual(set(report["review_candidates"]), {O, S})
        self.assertEqual(report["max_manual_releases_per_approval"], 2)
        self.assertEqual(report["grace_period_hold_count"], 0)
        self.assertTrue(all(
            candidate["cleanup_eligible_after_utc"] for candidate in report["releases"]
            if candidate["marker_valid"]
        ))
        self.assertEqual({p.name for p in self.releases.iterdir()}, before)
        self.assertTrue((self.releases / O).is_dir())

    def test_warn_at_existing_9gib_gate_without_deletion(self):
        free = MIN_STAGE_FREE_BYTES - 1
        r = audit(self.root, self.runner, self.data,
                  allow_test_roots=True, now=self.now,
                  disk_total=50 * 1024**3, disk_free=free)
        self.assertEqual(r["status"], "CAPACITY_WARNING")
        self.assertEqual(r["before_stage_9gib_gate"], "BLOCKED")
        self.assertEqual(r["after_stage_8gib_gate"], "PASS")
        self.assertFalse(r["deletion_performed"])
        self.assertFalse(r["automated_deletion_enabled"])
        self.assertEqual(r["shared_docker_containerd"], "OUT_OF_SCOPE_NO_WRITE")
        self.assertEqual(r["review_candidates"], [O, S])
        self.assertEqual(r["owned_subtree_allocated_bytes"]["pip_cache"], 0)
        r = audit(self.root, self.runner, self.data, allow_test_roots=True,
                  now=self.now, disk_total=50 * 1024**3,
                  disk_free=MIN_POST_STAGE_FREE_BYTES - 1)
        self.assertEqual(r["after_stage_8gib_gate"], "BLOCKED")

    def test_media_limit_can_block_without_blocking_9gib_pre_stage(self):
        # Use the existing configured 80% threshold, independent of the
        # 9-GiB minimum for immutable staging. Do not change either policy.
        total = 100 * 1024**3
        free = 11 * 1024**3
        result = audit(self.root, self.runner, self.data,
                       allow_test_roots=True, now=self.now,
                       disk_total=total, disk_free=free)
        self.assertEqual(result["before_stage_9gib_gate"], "PASS")
        self.assertEqual(result["media_prepare_stop_percent"], 80.0)
        self.assertEqual(result["disk_used_percent"], 89.0)
        self.assertEqual(result["media_preparation_disk_gate"], "BLOCKED")
        self.assertEqual(result["status"], "CAPACITY_WARNING")
        self.assertFalse(result["deletion_performed"])
        result = audit(self.root, self.runner, self.data,
                       allow_test_roots=True, now=self.now,
                       disk_total=total, disk_free=21 * 1024**3)
        self.assertEqual(result["media_preparation_disk_gate"], "PASS")
        self.assertEqual(result["status"], "PASS")

    def test_pending_pointer_never_becomes_removable(self):
        (self.root / "pending").symlink_to(self.releases / O)
        report = audited_release_inventory(self.root, now=self.now)
        self.assertEqual(report["pointers"]["pending"], O)
        self.assertEqual(report["review_candidates"], [S])

    def test_recent_and_incomplete_releases_protected(self):
        item = self.releases / O
        os.utime(item, (self.now - 4 * 86400, self.now - 4 * 86400))
        report = audited_release_inventory(self.root, now=self.now)
        self.assertEqual(next(x for x in report["releases"] if x["sha"] == O)["protected_reason"],
                         "SEVEN_DAY_GRACE")
        (self.releases / S / ".venv" / "bin" / "python").unlink()
        report = audited_release_inventory(self.root, now=self.now)
        self.assertEqual(next(x for x in report["releases"] if x["sha"] == S)["protected_reason"],
                         "CANDIDATE_REQUIRES_APPROVAL_AND_IN_USE_SCAN")
        self.assertIn(S, report["review_candidates"])
        details = next(x for x in report["review_candidates_details"] if x["sha"] == S)
        self.assertFalse(details["full_recovery_release"])
        # An incomplete release without a valid exact marker is never eligible.
        (self.releases / S / ".production-release").write_text("not-owned")
        report = audited_release_inventory(self.root, now=self.now)
        self.assertNotIn(S, report["review_candidates"])
        self.assertEqual(next(x for x in report["releases"] if x["sha"] == S)["protected_reason"],
                         "FORENSIC_HOLD_UNVERIFIED_IDENTITY")

    def test_recent_marker_verified_partial_is_held_for_seven_days(self):
        (self.releases / O / ".venv" / "bin" / "python").unlink()
        os.utime(self.releases / O, (self.now - 3 * 86400, self.now - 3 * 86400))
        report = audited_release_inventory(self.root, now=self.now)
        record = next(x for x in report["releases"] if x["sha"] == O)
        self.assertEqual(record["protected_reason"], "INCOMPLETE_SEVEN_DAY_GRACE")
        self.assertEqual(
            len([x for x in report["grace_period_hold_sha"] if x["sha"] == O]), 1
        )
        self.assertIsNotNone(record["cleanup_eligible_after_utc"])
        self.assertNotIn(O, report["review_candidates"])
        self.assertEqual(report["minimum_release_age_days"], 7)

    def test_fails_closed_on_pointer_escape_and_broken_pointer(self):
        (self.root / "current").unlink()
        (self.root / "current").symlink_to(self.data)
        with self.assertRaisesRegex(StorageAuditBlocked, "POINTER_OUT_OF_SCOPE"):
            audited_release_inventory(self.root, now=self.now)
        (self.root / "current").unlink()
        (self.root / "current").symlink_to(self.releases / ("f" * 40))
        with self.assertRaisesRegex(StorageAuditBlocked, "POINTER_BROKEN"):
            audited_release_inventory(self.root, now=self.now)

    def test_emergency_missing_prevents_normal_inventory(self):
        for sha in (E, O, S):
            (self.releases / sha / ".venv" / "bin" / "python").unlink()
        with self.assertRaisesRegex(StorageAuditBlocked, "EMERGENCY_RELEASE_UNAVAILABLE"):
            audited_release_inventory(self.root, now=self.now)

    def test_root_symlink_and_production_scope_are_rejected(self):
        with self.assertRaisesRegex(StorageAuditBlocked, "PRODUCTION_SCOPE_REQUIRED"):
            audit(self.root, self.runner, self.data)
        linked = self.runner / ".buffered-runtime-shadow"
        linked.symlink_to(self.root)
        with self.assertRaisesRegex(StorageAuditBlocked, "RUNTIME_SCOPE_INVALID"):
            audited_release_inventory(linked, now=self.now)

    def test_scheduled_workflow_is_main_only_no_delete_and_fourteen_day_artifact(self):
        import yaml
        file = Path(__file__).resolve().parents[1] / ".github/workflows/sns-storage-lifecycle.yml"
        source = file.read_text(encoding="utf-8")
        data = yaml.safe_load(source)
        trigger = data.get("on", data.get(True))
        self.assertEqual(trigger["schedule"][0]["cron"], "45 17 * * *")
        self.assertIn("workflow_dispatch", trigger)
        self.assertEqual(data["permissions"], {"contents": "read"})
        job = data["jobs"]["audit"]
        self.assertEqual(job["runs-on"], ["self-hosted", "Linux", "X64"])
        self.assertEqual(job["if"], "github.ref == 'refs/heads/main'")
        self.assertEqual(job["env"]["PUBLISH_ENABLED"], "false")
        self.assertEqual(job["env"]["ALLOW_REAL_THREADS_POST"], "false")
        self.assertEqual(job["env"]["ALLOW_REAL_X_POST"], "false")
        self.assertIn("sns_storage_lifecycle_audit.py", source)
        self.assertIn("grace_period_hold_count", source)
        self.assertIn("approval-gated cleanup", source)
        self.assertIn("media_preparation_disk_gate", source)
        self.assertIn("configured disk usage limit", source)
        self.assertIn("--summary-only", source)
        self.assertNotIn("--confirm-cleanup", source)
        self.assertNotIn("shutil.rmtree(", source)
        self.assertNotIn("docker prune", source)
        self.assertEqual(job["steps"][-1]["with"]["retention-days"], 14)

    def test_manual_capacity_recovery_accepts_one_exact_sha_without_deletion(self):
        import yaml
        file = Path(__file__).resolve().parents[1] / ".github/workflows/production-capacity-recovery.yml"
        source = file.read_text(encoding="utf-8")
        data = yaml.safe_load(source)
        trigger = data.get("on", data.get(True))
        self.assertIs(trigger["workflow_dispatch"]["inputs"]["obsolete_release_two"]["required"], False)
        self.assertIs(trigger["workflow_dispatch"]["inputs"]["confirm_cleanup"]["default"], False)
        job = data["jobs"]["recover"]
        self.assertIn('if [ -n "$OBSOLETE_TWO" ]; then', source)
        self.assertIn('args+=(--target "$OBSOLETE_TWO")', source)
        self.assertIn('args+=(--confirm-cleanup)', source)
        self.assertEqual(job["if"], "github.ref == 'refs/heads/main'")

    def test_release_deploy_only_monitors_storage_after_completed_success(self):
        text = (Path(__file__).resolve().parents[1] / "scripts/deploy_buffered_runtime_transaction.sh").read_text()
        self.assertLess(text.index("completed=true"), text.index("sns_storage_lifecycle_audit.py"))
        self.assertIn("--summary-only", text)
        self.assertNotIn("--confirm-cleanup", text)

    def test_baseline_is_exact_numeric_evidence_not_authorization(self):
        file = Path(__file__).resolve().parents[1] / "config/sns_storage_lifecycle_baseline_20261020.json"
        data = json.loads(file.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["metrics"]["release_allocated_bytes"], 4559065088)
        self.assertEqual(data["metrics"]["disk_free_bytes"], 9532727296)
        self.assertIn("not a deletion authorization", data["note"])

    def test_no_network_docker_delete_or_env_reads_in_source(self):
        text = (Path(__file__).parent / "sns_storage_lifecycle_audit.py").read_text()
        for banned in ("shutil.rmtree(", "os.remove(", "subprocess.run(['docker'",
                       "subprocess.run(['curl'", ".read_text(encoding='utf-8')"):
            self.assertNotIn(banned, text)
        self.assertIn("READ_ONLY", text)
        self.assertIn("last_used_at", text)


if __name__ == "__main__":
    unittest.main()
