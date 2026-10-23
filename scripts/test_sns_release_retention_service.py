#!/usr/bin/env python3
"""SNS-only unattended TTL planner; pure synthetic safety tests."""
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import subprocess
import tempfile
import unittest

import sns_release_retention_service as service

CURRENT="a"*40
PREVIOUS="b"*40
EMERGENCY="c"*40
PINNED=service.PINNED_EMERGENCY_SHA


def inventory():
    states = [
        (CURRENT, "POINTER", 755000000, 0),
        (PREVIOUS, "POINTER", 755000000, 0),
        (EMERGENCY, "EMERGENCY_RECOVERY", 755000000, 4),
        (PINNED, "ONE_DAY_GRACE", 755000000, 0),
        ("d"*40, "ONE_DAY_GRACE", 800000000, 0),
        ("e"*40, "CANDIDATE_REQUIRES_APPROVAL_AND_IN_USE_SCAN", 500000000, 8),
        ("f"*40, "CANDIDATE_REQUIRES_APPROVAL_AND_IN_USE_SCAN", 700000000, 9),
        ("1"*40, "CANDIDATE_REQUIRES_APPROVAL_AND_IN_USE_SCAN", 600000000, 10),
    ]
    return {
        "pointers": {"current": CURRENT, "previous": PREVIOUS, "pending": None},
        "emergency_recovery_sha": EMERGENCY,
        "releases": [{
            "sha": sha, "protected_reason": reason, "allocated_bytes": size,
            "age_days": age, "marker_valid": True,
        } for sha,reason,size,age in states],
    }


class ReleaseRetentionTests(unittest.TestCase):
    def test_selects_largest_aged_sns_sha_with_four_item_cap(self):
        self.assertEqual(
            service.choose_targets(inventory()), ["f"*40, "1"*40, "e"*40])

    def test_pinned_old_emergency_is_never_deleted(self):
        data=inventory()
        for row in data["releases"]:
            if row["sha"]==PINNED:
                row["protected_reason"]="CANDIDATE_REQUIRES_APPROVAL_AND_IN_USE_SCAN"
                row["age_days"]=45
        self.assertNotIn(PINNED, service.choose_targets(data))

    def test_protects_live_previous_pending_emergency(self):
        data=inventory()
        data["pointers"]["pending"]="e"*40
        data["releases"][5]["protected_reason"]="CANDIDATE_REQUIRES_APPROVAL_AND_IN_USE_SCAN"
        self.assertNotIn("e"*40, service.choose_targets(data))
        self.assertEqual(service.choose_targets(data),["f"*40,"1"*40])

    def test_duplicate_or_malformed_sha_blocks(self):
        data=inventory()
        data["releases"].append(dict(data["releases"][0]))
        with self.assertRaisesRegex(service.RetentionBlocked,"IDENTITY"):
            service.choose_targets(data)
        data=inventory()
        data["releases"][4]["sha"]="../../another-service"
        with self.assertRaisesRegex(service.RetentionBlocked,"IDENTITY"):
            service.choose_targets(data)

    def test_age_unverified_blocks(self):
        data=inventory()
        data["releases"][5]["age_days"]=0
        with self.assertRaisesRegex(service.RetentionBlocked,"AGE"):
            service.choose_targets(data)

    def test_wrong_owner_environment_blocks_apply(self):
        with patch.object(service.sys,"platform","darwin"),\
             patch.object(service.os,"geteuid",return_value=501):
            with self.assertRaisesRegex(service.RetentionBlocked,"ROOT"):
                service.run(confirm=True)

    def test_backup_gate_checks_recent_root_owned_producer_and_health(self):
        def stub(args,**kw):
            if args[1]=="is-enabled":
                return SimpleNamespace(returncode=0, stdout="enabled\n")
            return SimpleNamespace(returncode=0,stdout=(
                "Result=success\nExecMainStatus=0\n"
                "ExecMainExitTimestampMonotonic=900000000\n"))
        with patch.object(service.sys,"platform","linux"),\
             patch.object(service.os,"geteuid",return_value=0),\
             patch.object(service.subprocess,"run",side_effect=stub):
            service.manual_backup_gate(now_monotonic_us=910000000)

    def test_failed_or_stale_shared_backup_blocks(self):
        def failed(args,**kw):
            return SimpleNamespace(returncode=0,stdout=(
                "Result=failure\nExecMainStatus=1\n"
                "ExecMainExitTimestampMonotonic=900000000\n"))
        with patch.object(service.sys,"platform","linux"),\
             patch.object(service.os,"geteuid",return_value=0),\
             patch.object(service.subprocess,"run",side_effect=failed):
            with self.assertRaisesRegex(service.RetentionBlocked,"FAILED"):
                service.manual_backup_gate(now_monotonic_us=910000000)
        def stale(args,**kw):
            return SimpleNamespace(returncode=0,stdout=(
                "Result=success\nExecMainStatus=0\n"
                "ExecMainExitTimestampMonotonic=900000000\n"))
        with patch.object(service.sys,"platform","linux"),\
             patch.object(service.os,"geteuid",return_value=0),\
             patch.object(service.subprocess,"run",side_effect=stale):
            with self.assertRaisesRegex(service.RetentionBlocked,"TOO_OLD"):
                service.manual_backup_gate(now_monotonic_us=900000000+38*3600*1000000)

    def test_apply_uses_existing_bounded_pruner_after_backup_check(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=Path(directory)/".buffered-runtime"
            runtime.mkdir()
            data=inventory()
            with patch.object(service,"ROOT",runtime),\
                 patch.object(service.sys,"platform","linux"),\
                 patch.object(service.os,"geteuid",return_value=0),\
                 patch.object(service.audit,"audited_release_inventory",return_value=data),\
                 patch.object(service,"manual_backup_gate") as backup,\
                 patch.object(service.prune,"run",return_value={
                     "removed_releases":["f"*40,"1"*40,"e"*40],
                     "recovered_bytes":1234}) as prune:
                report=service.run(confirm=True)
            backup.assert_called_once_with()
            prune.assert_called_once_with(runtime,CURRENT,["f"*40,"1"*40,"e"*40],confirm=True)
            self.assertEqual(report["removed_count"],3)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["freed_bytes"],1234)

    def test_pruner_incomplete_receipt_is_not_false_success(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=Path(directory)/".buffered-runtime"
            runtime.mkdir()
            data=inventory()
            with patch.object(service,"ROOT",runtime), \
                 patch.object(service.sys,"platform","linux"), \
                 patch.object(service.os,"geteuid",return_value=0), \
                 patch.object(service.audit,"audited_release_inventory",return_value=data), \
                 patch.object(service,"manual_backup_gate"), \
                 patch.object(service.prune,"run",return_value={
                     "removed_releases":["f"*40], "recovered_bytes":1234}):
                with self.assertRaisesRegex(service.RetentionBlocked,"RECEIPT_MISMATCH"):
                    service.run(confirm=True)

    def test_audit_mode_never_deletes_or_queries_backup_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime=Path(directory)/".buffered-runtime"
            runtime.mkdir()
            with patch.object(service,"ROOT",runtime),\
                 patch.object(service.sys,"platform","linux"),\
                 patch.object(service.os,"geteuid",return_value=0),\
                 patch.object(service.audit,"audited_release_inventory",return_value=inventory()),\
                 patch.object(service,"manual_backup_gate") as backup,\
                 patch.object(service.prune,"run") as prune:
                report=service.run(confirm=False)
            self.assertEqual(report["mode"],"AUDIT")
            self.assertEqual(report["removed_count"],0)
            backup.assert_not_called()
            prune.assert_not_called()

    def test_no_candidates_no_deletion_even_on_apply(self):
        data=inventory()
        for row in data["releases"]:
            if row["sha"] not in (CURRENT,PREVIOUS,EMERGENCY,PINNED):
                row["protected_reason"]="ONE_DAY_GRACE"
        with tempfile.TemporaryDirectory() as directory:
            runtime=Path(directory)/".buffered-runtime"
            runtime.mkdir()
            with patch.object(service,"ROOT",runtime),\
                 patch.object(service.sys,"platform","linux"),\
                 patch.object(service.os,"geteuid",return_value=0),\
                 patch.object(service.audit,"audited_release_inventory",return_value=data),\
                 patch.object(service,"manual_backup_gate") as backup,\
                 patch.object(service.prune,"run") as prune:
                result=service.run(confirm=True)
            self.assertEqual(result["candidates"],0)
            prune.assert_not_called()
            backup.assert_not_called()

    def test_service_scope_and_schedule(self):
        root=Path(__file__).resolve().parents[1]
        u=(root/"ops/systemd/sns-growth-release-retention.service").read_text()
        t=(root/"ops/systemd/sns-growth-release-retention.timer").read_text()
        self.assertIn("User=root",u)
        self.assertIn("ProtectSystem=strict",u)
        self.assertIn("NoNewPrivileges=true",u)
        self.assertIn("/usr/local/libexec/chadult-sns-retention",u)
        self.assertIn("ReadWritePaths=/opt/github-runners/sns-growth-engine/",u)
        self.assertIn("OnCalendar=*-*-* 18:25:00 Asia/Tokyo",t)
        self.assertIn("Persistent=true",t)
        self.assertNotIn("restic forget",u+t)

if __name__=="__main__":
    unittest.main()
