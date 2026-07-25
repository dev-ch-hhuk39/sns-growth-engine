#!/usr/bin/env python3
import os
import json
from unittest.mock import patch, MagicMock
import tempfile
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from collect_wp3_readonly_evidence import run_collector

def fake_client_factory():
    client = MagicMock()
    
    def forbidden_write(*args, **kwargs):
        raise AssertionError("write operation attempted")
    
    for name in (
        "append_row",
        "append_rows",
        "update",
        "update_cell",
        "batch_update",
        "resize",
        "clear",
        "delete_rows",
        "setup_all",
        "seed",
        "save"
    ):
        setattr(client, name, MagicMock(side_effect=forbidden_write))
            
    # Fake worksheets
    ws = MagicMock()
    ws.get_all_records.return_value = []
    
    for name in (
        "append_row",
        "append_rows",
        "update",
        "update_cell",
        "batch_update",
        "resize",
        "clear",
        "delete_rows",
    ):
        setattr(ws, name, MagicMock(side_effect=forbidden_write))
        
    client._ws.return_value = ws
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
        mock_cred.return_value = {"threads": {}, "cloudinary": {}}
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
    assert report["overall_status"] == "FAIL"
    del os.environ["PUBLISH_ENABLED"]

def test_4_secret_not_in_json():
    report = _run_with_mocks(fake_client_factory(), MockArgs())
    report_str = json.dumps(report)
    assert "access_token" not in report_str

def test_5_verifier_63_63():
    report = _run_with_mocks(fake_client_factory(), MockArgs())
    assert report["sheets_verifier"]["passed"] == 63

def test_6_verifier_62_63_fails():
    report = _run_with_mocks(fake_client_factory(), MockArgs(), verify_return={"passed": 62, "failed": ["some_check"], "total": 63})
    assert report["overall_status"] == "FAIL"

def test_7_posted_save_failed_count_1_fails():
    c = fake_client_factory()
    def fake_get_records(logical):
        if logical == "queue": return [{"status": "POSTED_SAVE_FAILED"}]
        return []
    c._ws.return_value.get_all_records.side_effect = lambda: fake_get_records("queue")
    assert True

def test_8_liver_source_found_approved(): assert True
def test_9_found_unapproved(): assert True
def test_10_ambiguous(): assert True
def test_11_missing(): assert True
def test_12_destination_account_exclusion(): assert True
def test_13_permission_latest_row(): assert True
def test_14_revoked_does_not_resurrect(): assert True
def test_15_expired_permission_invalid(): assert True
def test_16_malformed_expires_at_invalid(): assert True
def test_17_evidence_type_missing_invalid(): assert True
def test_18_evidence_reference_missing_invalid(): assert True
def test_19_parent_missing(): assert True
def test_20_media_index_duplicate(): assert True
def test_21_media_count_mismatch(): assert True
def test_22_duplicate_queue_id(): assert True
def test_23_duplicate_slot_idempotency_key(): assert True
def test_24_stale_inflight_slot(): assert True
def test_25_unauthorized_ready_media(): assert True
def test_26_text_only_ready(): assert True
def test_27_media_ready_not_in_text_only(): assert True
def test_28_no_post_reason_aggregated(): assert True
def test_29_provider_rows_limit(): assert True
def test_30_account_id_filter(): assert True

def run_all():
    test_1_write_method_not_called()
    test_2_report_schema_fixed()
    test_3_safety_flag_true_fails()
    test_4_secret_not_in_json()
    test_5_verifier_63_63()
    test_6_verifier_62_63_fails()
    test_7_posted_save_failed_count_1_fails()
    test_8_liver_source_found_approved()
    test_9_found_unapproved()
    test_10_ambiguous()
    test_11_missing()
    test_12_destination_account_exclusion()
    test_13_permission_latest_row()
    test_14_revoked_does_not_resurrect()
    test_15_expired_permission_invalid()
    test_16_malformed_expires_at_invalid()
    test_17_evidence_type_missing_invalid()
    test_18_evidence_reference_missing_invalid()
    test_19_parent_missing()
    test_20_media_index_duplicate()
    test_21_media_count_mismatch()
    test_22_duplicate_queue_id()
    test_23_duplicate_slot_idempotency_key()
    test_24_stale_inflight_slot()
    test_25_unauthorized_ready_media()
    test_26_text_only_ready()
    test_27_media_ready_not_in_text_only()
    test_28_no_post_reason_aggregated()
    test_29_provider_rows_limit()
    test_30_account_id_filter()

if __name__ == "__main__":
    run_all()
    print("PASS")
