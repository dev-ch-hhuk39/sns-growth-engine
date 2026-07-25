#!/usr/bin/env python3
import os
import json
from unittest.mock import patch, MagicMock
import tempfile
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from collect_wp3_readonly_evidence import run_collector, WorksheetNotFound

def fake_client_factory(custom_ws=None):
    client = MagicMock()
    def forbidden_write(*args, **kwargs): raise AssertionError("write operation attempted")
    for name in ("append_row", "append_rows", "update", "update_cell", "batch_update", "resize", "clear", "delete_rows", "setup_all", "seed", "save"):
        setattr(client, name, MagicMock(side_effect=forbidden_write))
    
    def ws_mock(name):
        ws = MagicMock()
        records = custom_ws.get(name, []) if custom_ws else []
        ws.get_all_records.return_value = records
        for n in ("append_row", "append_rows", "update", "update_cell", "batch_update", "resize", "clear", "delete_rows"):
            setattr(ws, n, MagicMock(side_effect=forbidden_write))
        return ws
        
    client._ws.side_effect = ws_mock
    return client

class MockArgs:
    def __init__(self):
        self.output = tempfile.mktemp()
        self.account_id = "all"
        self.max_provider_rows = 20

def _run_with_mocks(fake_client, mock_args, verify_return=None):
    with patch('collect_wp3_readonly_evidence.get_config') as mock_config, \
         patch('collect_wp3_readonly_evidence.SheetsClient') as mock_client_cls, \
         patch('collect_wp3_readonly_evidence._refresh_ws_cache'), \
         patch('collect_wp3_readonly_evidence.verify_state') as mock_verify, \
         patch('collect_wp3_readonly_evidence.credential_status') as mock_cred:
         
        mock_config.return_value = {"sheet_id": "fake", "sa_dict": {}}
        mock_client_cls.return_value = fake_client
        mock_verify.return_value = verify_return or {"passed": 63, "failed": [], "total": 63, "warnings": {}, "counts": {}}
        mock_cred.return_value = {"threads": {"night_scout": {"publish_credentials": "SET"}, "liver_manager": {"publish_credentials": "SET"}}, "cloudinary": {}}
        run_collector(mock_args)
        
    with open(mock_args.output, "r") as f:
        return json.load(f)

def test_1_write_method_not_called():
    report = _run_with_mocks(fake_client_factory(), MockArgs())
    assert report["overall_status"] != "FAIL_EXCEPTION"

def test_2_report_schema_fixed():
    report = _run_with_mocks(fake_client_factory(), MockArgs())
    assert report["schema_version"] == 1
    assert "generated_at" in report
    assert report["mode"] == "READ_ONLY"

def test_3_safety_flag_true_fails():
    os.environ["PUBLISH_ENABLED"] = "true"
    report = _run_with_mocks(fake_client_factory(), MockArgs())
    assert "SAFETY_FLAG_TRUE" in report["status_reasons"]
    del os.environ["PUBLISH_ENABLED"]

def test_4_secret_not_in_json():
    report = _run_with_mocks(fake_client_factory(), MockArgs())
    assert "access_token" not in json.dumps(report)

def test_5_verifier_63_63():
    report = _run_with_mocks(fake_client_factory(), MockArgs())
    assert report["sheets_verifier"]["passed"] == 63

def test_6_verifier_62_63_fails():
    report = _run_with_mocks(fake_client_factory(), MockArgs(), verify_return={"passed": 62, "failed": ["some_check"], "total": 63})
    assert "SHEETS_VERIFIER_FAILED" in report["status_reasons"]

def test_7_posted_save_failed_count_1_fails():
    report = _run_with_mocks(fake_client_factory({"queue": [{"status": "POSTED_SAVE_FAILED"}]}), MockArgs())
    assert "POSTED_SAVE_FAILED" in report["status_reasons"]

def test_8_liver_source_found_approved():
    db = {"source_accounts": [{"platform": "threads", "target_account_id": "liver_manager", "source_url": "t.net/@a", "active": "true", "blocked": "false", "review_status": "APPROVED"}]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert report["liver_threads_source_classification"] == "FOUND_APPROVED"

def test_9_found_unapproved():
    db = {"source_accounts": [{"platform": "threads", "target_account_id": "liver_manager", "source_url": "t.net/@a", "active": "false"}]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert report["liver_threads_source_classification"] == "FOUND_UNAPPROVED"

def test_10_ambiguous():
    db = {"source_accounts": [{"platform": "threads", "target_account_id": "liver_manager", "source_url": "t.net/@a", "active": "true", "review_status": "PENDING"}]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert report["liver_threads_source_classification"] == "AMBIGUOUS"

def test_11_missing():
    report = _run_with_mocks(fake_client_factory(), MockArgs())
    assert report["liver_threads_source_classification"] == "MISSING"

def test_12_destination_account_exclusion():
    db = {
        "accounts": [{"account_id": "night_scout", "threads_handle": "@me"}],
        "source_accounts": [{"platform": "threads", "target_account_id": "night_scout", "source_url": "https://threads.net/@me"}]
    }
    args = MockArgs(); args.account_id = "night_scout"
    report = _run_with_mocks(fake_client_factory(db), args)
    assert len(report["source_inventory"]["night_scout"]["excluded_destination_accounts"]) == 1
    assert len(report["source_inventory"]["night_scout"]["threads_source_accounts"]) == 0

def test_13_threads_url_normalization():
    db = {
        "accounts": [{"account_id": "night_scout", "threads_handle": "me"}],
        "source_accounts": [
            {"platform": "threads", "target_account_id": "night_scout", "source_url": "https://www.threads.com/@me?x=1"}
        ]
    }
    args = MockArgs(); args.account_id = "night_scout"
    report = _run_with_mocks(fake_client_factory(db), args)
    assert len(report["source_inventory"]["night_scout"]["excluded_destination_accounts"]) == 1

def test_14_latest_permission_selection():
    db = {"media_permissions": [
        {"source_id": "s1", "approved_at": "2", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y"},
        {"source_id": "s1", "approved_at": "1", "permission_status": "denied", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y"}
    ]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert report["permissions"]["s1"]["valid"] == True

def test_15_revoked_latest_row():
    db = {"media_permissions": [
        {"source_id": "s1", "approved_at": "1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y"},
        {"source_id": "s1", "approved_at": "2", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y", "revoked": "true"}
    ]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert report["permissions"]["s1"]["valid"] == False
    assert "REVOKED" in report["permissions"]["s1"]["invalid_reasons"]

def test_16_denied_latest_row():
    db = {"media_permissions": [
        {"source_id": "s1", "approved_at": "1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y"},
        {"source_id": "s1", "approved_at": "2", "permission_status": "denied", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y"}
    ]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert report["permissions"]["s1"]["valid"] == False
    assert "PERMISSION_STATUS_NOT_APPROVED" in report["permissions"]["s1"]["invalid_reasons"]

def test_17_expired():
    db = {"media_permissions": [
        {"source_id": "s1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y", "expires_at": "2000-01-01T00:00:00Z"}
    ]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert report["permissions"]["s1"]["valid"] == False
    assert "EXPIRED" in report["permissions"]["s1"]["invalid_reasons"]

def test_18_malformed_expiry():
    db = {"media_permissions": [
        {"source_id": "s1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y", "expires_at": "bad-date"}
    ]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert report["permissions"]["s1"]["valid"] == False
    assert "MALFORMED_EXPIRES_AT" in report["permissions"]["s1"]["invalid_reasons"]

def test_19_evidence_type_missing():
    db = {"media_permissions": [
        {"source_id": "s1", "permission_status": "approved", "rights_status": "allowed", "evidence_reference": "y"}
    ]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert report["permissions"]["s1"]["valid"] == False
    assert "MISSING_EVIDENCE_TYPE" in report["permissions"]["s1"]["invalid_reasons"]

def test_20_evidence_reference_missing():
    db = {"media_permissions": [
        {"source_id": "s1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x"}
    ]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert report["permissions"]["s1"]["valid"] == False
    assert "MISSING_EVIDENCE_REFERENCE" in report["permissions"]["s1"]["invalid_reasons"]

def test_21_parent_missing():
    db = {"source_post_media": [{"source_post_id": "p1", "media_index": "1"}]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert any(f["reason"] == "PARENT_NOT_FOUND" for f in report["integrity"]["parent_integrity_failures"])

def test_22_media_index_duplicate():
    db = {
        "source_posts": [{"source_post_id": "p1", "target_account_id": "all", "media_count": 2}],
        "source_post_media": [{"source_post_id": "p1", "media_index": "1"}, {"source_post_id": "p1", "media_index": "1"}]
    }
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert any(f["reason"] == "DUPLICATE_MEDIA_INDEX" for f in report["integrity"]["parent_integrity_failures"])

def test_23_media_count_mismatch():
    db = {
        "source_posts": [{"source_post_id": "p1", "target_account_id": "all", "media_count": 5}],
        "source_post_media": [{"source_post_id": "p1", "media_index": "1"}]
    }
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert any(f["reason"] == "MEDIA_COUNT_MISMATCH" for f in report["integrity"]["parent_integrity_failures"])

def test_24_duplicate_queue_id():
    db = {"queue": [{"queue_id": "q1"}, {"queue_id": "q1"}]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert "q1" in report["integrity"]["duplicate_queue_ids"]

def test_25_duplicate_slot_key():
    db = {"content_slot_runs": [{"idempotency_key": "k1"}, {"idempotency_key": "k1"}]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert "k1" in report["integrity"]["duplicate_slot_idempotency_keys"]

def test_26_stale_slot():
    db = {"content_slot_runs": [{"slot_run_id": "sr1", "status": "RUNNING", "lease_expires_at": "2000-01-01T00:00:00Z"}]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert "sr1" in report["integrity"]["stale_inflight_slots"]

def test_27_text_only_ready_exclusion():
    db = {"queue": [{"queue_id": "q1", "status": "READY", "platform": "threads", "target_account_id": "all"}]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert len(report["integrity"]["unauthorized_ready_media"]) == 0

def test_28_direct_media_authorized():
    db = {
        "queue": [{"queue_id": "q1", "status": "READY", "platform": "threads", "target_account_id": "all", "media_required": "true", "media_asset_id": "m1", "validator_status": "PASS", "alignment_status": "PASS", "unsupported_claim_count": 0, "source_id": "s1"}],
        "media_assets": [{"media_id": "m1"}],
        "media_permissions": [{"source_id": "s1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y", "allow_original_repost": "true"}]
    }
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert len(report["integrity"]["unauthorized_ready_media"]) == 0

def test_29_direct_media_unauthorized():
    db = {
        "queue": [{"queue_id": "q1", "status": "READY", "platform": "threads", "target_account_id": "all", "media_required": "true", "media_asset_id": "m1", "validator_status": "PASS", "alignment_status": "PASS", "unsupported_claim_count": 0, "source_id": "s1"}],
        "media_assets": [{"media_id": "m1"}],
        "media_permissions": [{"source_id": "s1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y", "allow_original_repost": "false"}]
    }
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert "ORIGINAL_REPOST_NOT_ALLOWED" in report["integrity"]["unauthorized_ready_media"][0]["reasons"]

def test_30_generated_clip_authorized():
    db = {
        "queue": [{"queue_id": "q1", "status": "READY", "platform": "threads", "target_account_id": "all", "media_required": "true", "media_asset_id": "m1", "validator_status": "PASS", "alignment_status": "PASS", "unsupported_claim_count": 0, "source_id": "s1", "media_origin": "generated_clip"}],
        "media_assets": [{"media_id": "m1"}],
        "media_permissions": [{"source_id": "s1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y", "allow_clip_repost": "true"}]
    }
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert len(report["integrity"]["unauthorized_ready_media"]) == 0

def test_31_generated_clip_unauthorized():
    db = {
        "queue": [{"queue_id": "q1", "status": "READY", "platform": "threads", "target_account_id": "all", "media_required": "true", "media_asset_id": "m1", "validator_status": "PASS", "alignment_status": "PASS", "unsupported_claim_count": 0, "source_id": "s1", "media_origin": "generated_clip"}],
        "media_assets": [{"media_id": "m1"}],
        "media_permissions": [{"source_id": "s1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y", "allow_clip_repost": "false"}]
    }
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert "CLIP_REPOST_NOT_ALLOWED" in report["integrity"]["unauthorized_ready_media"][0]["reasons"]

def test_32_media_id_resolution():
    db = {
        "queue": [{"queue_id": "q1", "status": "READY", "platform": "threads", "target_account_id": "all", "media_asset_id": "m1", "validator_status": "PASS", "alignment_status": "PASS", "unsupported_claim_count": 0, "source_id": "s1"}],
        "media_assets": [{"media_id": "m1"}],
        "media_permissions": [{"source_id": "s1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y", "allow_original_repost": "true"}]
    }
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert len(report["integrity"]["unauthorized_ready_media"]) == 0

def test_33_source_video_id_resolution():
    db = {
        "queue": [{"queue_id": "q1", "status": "READY", "platform": "threads", "target_account_id": "all", "media_asset_id": "m1", "validator_status": "PASS", "alignment_status": "PASS", "unsupported_claim_count": 0, "source_video_id": "sv1"}],
        "source_videos": [{"source_video_id": "sv1", "source_id": "s1"}],
        "media_assets": [{"media_id": "m1"}],
        "media_permissions": [{"source_id": "s1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y", "allow_clip_repost": "true"}]
    }
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert len(report["integrity"]["unauthorized_ready_media"]) == 0

def test_34_cloudinary_storage_required():
    db = {
        "queue": [{"queue_id": "q1", "status": "READY", "platform": "threads", "target_account_id": "all", "media_asset_id": "m1", "validator_status": "PASS", "alignment_status": "PASS", "unsupported_claim_count": 0, "source_id": "s1"}],
        "media_assets": [{"media_id": "m1", "storage_provider": "cloudinary"}],
        "media_permissions": [{"source_id": "s1", "permission_status": "approved", "rights_status": "allowed", "evidence_type": "x", "evidence_reference": "y", "allow_original_repost": "true", "allow_cloudinary_storage": "false"}]
    }
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert "CLOUDINARY_STORAGE_NOT_ALLOWED" in report["integrity"]["unauthorized_ready_media"][0]["reasons"]

def test_35_no_post_reason_aggregated():
    db = {"content_slot_runs": [{"account_id": "night_scout", "no_post_reason": "R1"}, {"account_id": "night_scout", "no_post_reason": "R1"}, {"account_id": "night_scout", "no_post_reason": "R2"}]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert report["text_pipeline"]["night_scout"]["no_post_reasons"] == {"R1": 2, "R2": 1}

def test_36_provider_row_limit():
    db = {"provider_runs": [{"source_id": f"s{i}", "created_at": str(i)} for i in range(50)]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert len(report["provider_routing"]["provider_runs"]) == 20

def test_37_account_id_filter():
    args = MockArgs()
    args.account_id = "night_scout"
    db = {"queue": [{"target_account_id": "night_scout", "status": "WAITING_REVIEW"}, {"target_account_id": "liver_manager", "status": "WAITING_REVIEW"}]}
    report = _run_with_mocks(fake_client_factory(db), args)
    assert report["text_pipeline"]["night_scout"]["waiting_review_count"] == 1
    assert "liver_manager" not in report["text_pipeline"]

def test_38_missing_tab():
    def missing_mock(name): raise WorksheetNotFound(name)
    c = fake_client_factory()
    c._ws.side_effect = missing_mock
    report = _run_with_mocks(c, MockArgs())
    assert "queue" in report["missing_tabs"]

def test_39_read_error():
    def err_mock(name): raise Exception("random error")
    c = fake_client_factory()
    c._ws.side_effect = err_mock
    report = _run_with_mocks(c, MockArgs())
    assert any(e["tab"] == "queue" for e in report["read_errors"])

def test_40_status_reason_codes():
    db = {"queue": [{"status": "POSTED_SAVE_FAILED"}]}
    report = _run_with_mocks(fake_client_factory(db), MockArgs())
    assert "POSTED_SAVE_FAILED" in report["status_reasons"]
    assert report["overall_status"] == "FAIL"

def run_all():
    for name, func in globals().items():
        if name.startswith("test_") and callable(func):
            func()

if __name__ == "__main__":
    run_all()
    print("PASS")
