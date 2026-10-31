#!/usr/bin/env python3
"""Synthetic files/permissions exercise gates, never establish live acceptance."""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import evaluate_reference_first_completion as completion  # noqa: E402
import verify_physical_media_goldens as golden  # noqa: E402

REVISION = "a" * 40
ACCOUNTS = ("night_scout", "liver_manager")
PROBE = {"video_stream_count": 1, "audio_stream_count": 1, "width": 1280,
         "height": 720, "duration_seconds": 30.0}


class OwnerArtifactVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "config").mkdir()
        self.directories = {platform: self.root / platform for platform in ("x", "youtube")}
        for directory in self.directories.values():
            directory.mkdir(mode=0o700)
        self.manifest = {"x_exact_statuses": [], "youtube_goldens": [], "tiktok_goldens": []}
        self.registry, self.permissions = [], []
        for platform in self.directories:
            for index, account in enumerate(ACCOUNTS):
                handle = account + "_owner"
                native = str(123450 + index) if platform == "x" else ("abcdefghijk" if index == 0 else "1234567890A")
                profile = "https://x.com/" + handle if platform == "x" else "https://www.youtube.com/@" + handle
                url = profile + "/status/" + native if platform == "x" else "https://www.youtube.com/watch?v=" + native
                source = account + "_" + platform
                item = {"account_id": account, "source_id": source, "source_handle": "@" + handle, "url": url}
                self.manifest["x_exact_statuses" if platform == "x" else "youtube_goldens"].append(item)
                self.registry.append({"source_id": source, "source_platform": platform, "source_handle": "@" + handle,
                                      "source_url": profile, "target_account_ids": [account], "active": True})
                self.permissions.append({"source_id": source, "source_handle": handle, "account_id": account,
                    "allowed_accounts": [account], "permission_status": "approved", "rights_status": "approved_creator_clip",
                    "usage_mode": "direct_and_clip", "evidence_type": "offline_fixture", "evidence_reference": "synthetic",
                    "approved_by": "fixture", "approved_at": "2026-10-30T00:00:00+00:00", "revoked": False,
                    **{flag: True for flag in ("allow_download", "allow_cloudinary_storage", "allow_original_repost", "allow_new_caption")}})
                summary = ("時給だけでなく控除と続けやすさを確認し、店の条件と手取りの差を説明する。" if account == "night_scout"
                           else "初見が入ったら短く挨拶し、今の話題を一言添えてコメントしやすい入口を作る。")
                data = (source + ": synthetic bytes, ffprobe mocked").encode()
                path = self.directories[platform] / (source + "_" + native + ".mp4")
                path.write_bytes(data)
                metadata = {"id": native if platform == "youtube" else "separate-media-id", "display_id": native,
                            "webpage_url": url, "uploader_id": handle, "description": summary,
                            "formats": [{"vcodec": "h264"}]}
                path.with_suffix(".info.json").write_text(json.dumps(metadata))
                digest = hashlib.sha256(data).hexdigest()
                asset = "ma_" + digest[:24]
                proof = {"schema_version": 1, "account_id": account, "source_id": source, "canonical_url": url,
                    "external_post_id": native, "media_asset_id": asset, "content_hash": digest,
                    "analysis": {"status": "PASS", "vision_status": "PASS", "provider": "gemini", "http_status": 200,
                        "response_schema_status": "PASS", "visual_summary": summary, "visible_action": summary,
                        "key_moment": summary, "visual_facts": [{"id": "VF1", "type": "visible_action", "text": summary}],
                        "visual_evidence": {"status": "UNDERSTOOD", "provider": "gemini", "frame_hashes": ["b" * 64],
                                            "content_hash": digest, "media_asset_id": asset}}}
                path.with_suffix(".understanding.json").write_text(json.dumps(proof))
        self.write_manifest()

    def write_manifest(self):
        (self.root / "config/physical_media_goldens.json").write_text(json.dumps(self.manifest))

    def verify(self, *, permissions=None):
        reads = [self.permissions, self.permissions] if permissions is None else permissions
        with patch.object(golden, "ROOT", self.root), patch.object(golden, "load_registry", return_value=self.registry), \
                patch.object(golden, "_permission_rows", side_effect=reads) as reader, \
                patch.object(golden, "probe_media_streams", return_value=PROBE):
            result = golden.verify_owner_goldens(self.directories)
        return result, reader.call_count

    def test_default_is_offline_without_client_or_artifact_access(self):
        with patch.object(golden, "get_config", side_effect=AssertionError("no connection")):
            result = golden.verify_owner_goldens()
        self.assertEqual(result["status"], "NOT_RUN")
        self.assertFalse(result["publish_authorized"])

    def test_current_both_account_xy_files_and_proof_reach_verification_only(self):
        result, reads = self.verify()
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(len(result["checks"]), 4)
        self.assertEqual(reads, 2)
        self.assertFalse(result["overall_goal_acceptance"])
        self.assertFalse(result["publish_authorized"])
        self.assertFalse(result["production_writes"])
        self.assertEqual(result["provider_calls"], 0)
        self.assertNotIn("public_post_preview", json.dumps(result))

    def test_relative_partial_missing_and_linked_directories_do_not_connect(self):
        linked = self.root / "linked"
        linked.symlink_to(self.directories["x"], target_is_directory=True)
        for directories in ({"x": self.directories["x"]}, {"x": Path("."), "youtube": self.directories["youtube"]},
                            {**self.directories, "x": linked}, {**self.directories, "x": self.root / "absent"}):
            with self.subTest(directories=directories), patch.object(golden, "_permission_rows", side_effect=AssertionError("no read")):
                self.assertEqual(golden.verify_owner_goldens(directories)["status"], "BLOCKED")

    def test_missing_artifact_stops_before_live_permissions(self):
        next(self.directories["x"].glob("*.mp4")).unlink()
        result, reads = self.verify()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(reads, 0)

    def test_missing_account_or_duplicate_manifest_cannot_narrow_required_coverage(self):
        original = deepcopy(self.manifest)
        for altered in ([], [original["youtube_goldens"][0]], original["youtube_goldens"] * 2):
            self.manifest = {**deepcopy(original), "youtube_goldens": altered}
            self.write_manifest()
            result, reads = self.verify()
            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(reads, 0)

    def test_deferred_tiktok_is_not_required_or_opened(self):
        self.manifest["tiktok_goldens"] = [{"account_id": "liver_manager", "url": "https://www.tiktok.com/@unknown/video/1"}]
        self.write_manifest()
        result, _ = self.verify()
        self.assertEqual(result["status"], "PASS", result)
        self.assertTrue(all(row["platform"] in {"x", "youtube"} for row in result["checks"]))

    def test_missing_semantic_sidecar_blocks_despite_valid_av(self):
        next(self.directories["x"].glob("*.understanding.json")).unlink()
        result, reads = self.verify()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(reads, 0)

    def test_public_directory_cannot_supply_completion_evidence(self):
        self.directories["x"].chmod(0o777)
        result, reads = self.verify()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(reads, 0)

    def test_group_writable_evidence_cannot_supply_completion_evidence(self):
        next(self.directories["x"].glob("*.understanding.json")).chmod(0o660)
        result, reads = self.verify()
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(reads, 0)

    def test_bytes_changed_after_one_item_passes_cannot_keep_prior_success(self):
        verify_item = golden.verify_item
        changed = False
        path = next(self.directories["x"].glob("*.mp4"))
        def change_after_verification(*args, **kwargs):
            nonlocal changed
            row = verify_item(*args, **kwargs)
            if not changed:
                path.write_bytes(b"changed after successful item verification")
                changed = True
            return row
        with patch.object(golden, "verify_item", side_effect=change_after_verification):
            result, _ = self.verify()
        self.assertEqual(result["status"], "BLOCKED")

    def test_permission_revocation_during_local_verification_is_rechecked(self):
        revoked = deepcopy(self.permissions)
        revoked[0]["revoked"] = True
        result, reads = self.verify(permissions=[self.permissions, revoked])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(reads, 2)

    def test_second_read_failure_cannot_keep_prior_success(self):
        result, reads = self.verify(permissions=[self.permissions, RuntimeError("private provider detail")])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(reads, 2)
        self.assertNotIn("private provider detail", json.dumps(result))

    def test_late_missing_account_and_author_scope_are_blocked(self):
        for key in ("account_id", "source_handle"):
            altered = deepcopy(self.permissions)
            altered[0][key] = ""
            result, _ = self.verify(permissions=[self.permissions, altered])
            self.assertEqual(result["status"], "BLOCKED", key)

    def test_dry_run_and_mock_client_modes_cannot_read_live_evidence(self):
        for dry_run, mock in ((True, "false"), (False, " true ")):
            with patch.object(golden, "get_config", return_value={"dry_run": dry_run}), \
                    patch.dict(os.environ, {"MOCK_SHEETS": mock}), patch.object(golden, "SheetsClient") as client:
                with self.assertRaises(ValueError):
                    golden._permission_rows(True)
                client.assert_not_called()

    def test_factory_substitute_cannot_claim_a_real_permission_read(self):
        with patch.object(golden, "get_config", return_value={"sheet_id": "synthetic", "sa_dict": {}, "dry_run": False}), \
                patch.dict(os.environ, {"MOCK_SHEETS": "false"}), patch.object(golden, "SheetsClient", return_value=object()):
            with self.assertRaises(ValueError):
                golden._permission_rows(True)

    def test_aggregate_requires_every_existing_quality_gate_and_human_review(self):
        row = {key: "PASS" for key in ("registered_source", "artifact_binding", "technical_bytes", "content_understanding",
               "effective_permission", "source_validation", "persona_generation", "generation_quality", "media_text_quality", "public_validation")}
        row.update(queue_status="WAITING_REVIEW", publisher_eligible=False, preserve_source=True)
        for key in row:
            altered = deepcopy(row)
            altered.pop(key)
            with self.subTest(key=key), patch.object(golden, "verify_item", return_value=altered):
                result, _ = self.verify()
                self.assertEqual(result["status"], "BLOCKED")


class CompletionBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.approval = self.root / "approval.json"
        self.write_approval(REVISION)
        self.proof = {"status": "PASS", "checks": [{"account_id": account, "platform": platform, "status": "PASS"}
                     for account in ACCOUNTS for platform in ("x", "youtube")]}

    def write_approval(self, revision):
        self.approval.write_text(json.dumps({"status": "APPROVED", "production_write_approval": True,
                                            "implementation_head": revision}))
        self.approval.chmod(0o600)

    def evaluate(self, *, proof=None, revision=REVISION, permission_status="PASS", failed_count=0):
        with patch.object(completion, "_implementation_revision", return_value=revision), \
                patch.object(completion, "_current_owner_physical_evidence", return_value=self.proof if proof is None else proof), \
                patch.object(completion, "_x_permission_state", return_value={"status": permission_status, "blocker": False,
                    "registry_mismatches": [], "duplicate_candidate_handles": []}), \
                patch.object(completion, "evaluate_capabilities", return_value={"status": "PASS", "passed": 1,
                    "required": 1, "code_complete": 1, "code_required": 1}):
            return completion.evaluate(repository_tests_result={"status": "PASS", "test_count": 1108, "failed_count": failed_count},
                                       production_approval_path=self.approval)

    def test_synthetic_current_xy_proof_and_bound_approval_cover_both_accounts(self):
        result = self.evaluate()
        self.assertTrue(result["active_scope_live_evidence_complete"])
        self.assertTrue(result["production_evidence_complete"])

    def test_historical_av_declarations_never_substitute_for_current_verification(self):
        result = self.evaluate(proof={"status": "NOT_RUN", "checks": []})
        self.assertFalse(result["active_scope_live_evidence_complete"])
        self.assertFalse(result["production_evidence_complete"])
        self.assertEqual(result["completion_status"], "SOFTWARE_COMPLETE_EXTERNAL_BLOCKERS_ONLY")

    def test_partial_account_coverage_blocks_completion(self):
        proof = deepcopy(self.proof)
        proof["checks"].pop()
        result = self.evaluate(proof=proof)
        self.assertFalse(result["active_scope_live_evidence_complete"])
        self.assertFalse(result["production_evidence_complete"])

    def test_blocked_verification_invalidates_even_pass_rows(self):
        self.assertFalse(self.evaluate(proof={**self.proof, "status": "BLOCKED"})["production_evidence_complete"])

    def test_permission_failure_is_not_an_authorization_when_blocker_false(self):
        self.assertFalse(self.evaluate(permission_status="FAIL")["production_evidence_complete"])

    def test_empty_matching_revision_cannot_authorize(self):
        self.write_approval("")
        self.assertFalse(self.evaluate(revision="")["production_evidence_complete"])

    def test_malformed_matching_revision_cannot_authorize(self):
        self.write_approval("unverified")
        self.assertFalse(self.evaluate(revision="unverified")["production_evidence_complete"])

    def test_wrong_revision_and_failed_repository_remain_blocked(self):
        self.write_approval("b" * 40)
        self.assertFalse(self.evaluate()["production_evidence_complete"])
        self.write_approval(REVISION)
        self.assertFalse(self.evaluate(failed_count=1)["production_evidence_complete"])

    def test_revision_change_during_verification_invalidates_approval(self):
        with patch.object(completion, "_implementation_revision", side_effect=[REVISION, "b" * 40]), \
                patch.object(completion, "_current_owner_physical_evidence", return_value=self.proof):
            result = completion.evaluate(repository_tests_result={"status": "PASS", "test_count": 1108, "failed_count": 0},
                                         production_approval_path=self.approval)
        self.assertFalse(result["implementation_revision_stable"])
        self.assertFalse(result["production_write_approval_external_blocker"]["status"] == "PASS")

    def test_default_evaluator_does_not_request_physical_access(self):
        with patch.object(golden, "verify_owner_goldens", side_effect=AssertionError("no physical access")):
            result = completion.evaluate(repository_tests_result={"status": "PASS", "test_count": 1108, "failed_count": 0})
        self.assertEqual(result["current_owner_physical_verification"]["status"], "NOT_RUN")

    def test_explicit_physical_failure_is_a_failed_result_even_when_software_passes(self):
        with patch.object(completion, "_current_owner_physical_evidence", return_value={"status": "BLOCKED", "checks": []}):
            result = completion.evaluate(repository_tests_result={"status": "PASS", "test_count": 1108, "failed_count": 0},
                physical_golden_directories={"x": self.root, "youtube": self.root})
        self.assertTrue(result["software_complete"])
        self.assertEqual(result["status"], "FAIL")

    def test_cli_reports_failed_requested_verification_as_nonzero(self):
        args = ["evaluator", "--verify-existing-owner-goldens", "--x-dir", "/private/tmp/x", "--youtube-dir", "/private/tmp/y"]
        with patch.object(sys, "argv", args), patch.object(completion, "evaluate", return_value={"status": "FAIL", "completion_status": "synthetic"}), redirect_stdout(io.StringIO()):
            self.assertEqual(completion.main(), 1)

    def test_cli_requires_explicit_verification_and_both_directories(self):
        for flags in (["--x-dir", "/private/tmp"], ["--verify-existing-owner-goldens"],
                      ["--verify-existing-owner-goldens", "--youtube-dir", "/private/tmp"]):
            with patch.object(sys, "argv", ["evaluator", *flags]), patch.object(completion, "evaluate") as evaluate, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    completion.main()
                self.assertEqual(raised.exception.code, 2)
                evaluate.assert_not_called()

    def test_cli_explicit_mode_passes_exact_directories(self):
        args = ["evaluator", "--verify-existing-owner-goldens", "--x-dir", "/private/tmp/x", "--youtube-dir", "/private/tmp/y"]
        with patch.object(sys, "argv", args), patch.object(completion, "evaluate", return_value={"status": "PASS", "completion_status": "synthetic"}) as evaluate, redirect_stdout(io.StringIO()):
            self.assertEqual(completion.main(), 0)
        self.assertEqual(evaluate.call_args.kwargs["physical_golden_directories"], {"x": Path("/private/tmp/x"), "youtube": Path("/private/tmp/y")})

    def release(self):
        root = self.root / "releases" / REVISION
        root.mkdir(parents=True)
        marker = root / ".production-release"
        marker.write_text(REVISION + "\n")
        marker.chmod(0o600)
        return root, marker

    def test_immutable_release_marker_binds_without_git(self):
        root, marker = self.release()
        for value in (REVISION, REVISION + "\n"):
            marker.write_text(value)
            with patch.object(completion, "ROOT", root), patch.object(completion, "_git", side_effect=AssertionError("no ancestor git")):
                self.assertEqual(completion._implementation_revision(), REVISION)

    def test_missing_invalid_linked_and_writable_markers_never_fall_back_to_git(self):
        root, marker = self.release()
        for value in ("b" * 40, REVISION + "\x00", REVISION + "\n\n", "A" * 40):
            marker.write_text(value)
            with patch.object(completion, "ROOT", root), patch.object(completion, "_git", side_effect=AssertionError("no fallback")):
                self.assertEqual(completion._implementation_revision(), "")
        marker.write_text(REVISION)
        marker.chmod(0o620)
        with patch.object(completion, "ROOT", root):
            self.assertEqual(completion._implementation_revision(), "")
        marker.chmod(0o600)
        marker.unlink()
        with patch.object(completion, "ROOT", root):
            self.assertEqual(completion._implementation_revision(), "")
        original = self.root / "original"
        original.write_text(REVISION)
        marker.symlink_to(original)
        with patch.object(completion, "ROOT", root):
            self.assertEqual(completion._implementation_revision(), "")

    def test_hardlinked_marker_and_parent_checkout_are_refused(self):
        root, marker = self.release()
        os.link(marker, self.root / "linked")
        with patch.object(completion, "ROOT", root):
            self.assertEqual(completion._implementation_revision(), "")
        with patch.object(completion, "ROOT", self.root), patch.object(completion, "_git", return_value=str(self.root.parent)):
            self.assertEqual(completion._implementation_revision(), "")

    def test_checkout_revision_requires_successful_clean_status(self):
        def git(*args):
            return str(self.root) if args == ("rev-parse", "--show-toplevel") else REVISION
        for returncode, output, expected in ((0, "", REVISION), (0, " M scripts/changed.py", ""), (1, "", "")):
            state = subprocess.CompletedProcess([], returncode, output, "")
            with patch.object(completion, "ROOT", self.root), patch.object(completion, "_git", side_effect=git), \
                    patch.object(completion.subprocess, "run", return_value=state):
                self.assertEqual(completion._implementation_revision(), expected)

    def test_marker_replacement_during_read_is_refused(self):
        root, marker = self.release()
        original_open = os.open
        def replace_after_open(path, flags):
            descriptor = original_open(path, flags)
            marker.unlink()
            marker.write_text(REVISION)
            return descriptor
        with patch.object(completion, "ROOT", root), patch.object(completion.os, "open", side_effect=replace_after_open):
            self.assertEqual(completion._implementation_revision(), "")


if __name__ == "__main__":
    unittest.main()
