#!/usr/bin/env python3
import discover_approved_source_videos as d

def main() -> int:
    original = d.load_sources
    d.load_sources = lambda: [{
        "source_id": "src_lm_yt_user_001", "target_account_id": "liver_manager",
        "source_platform": "youtube", "source_type": "channel", "source_url": "https://youtube.com/channel/x",
        "rights_status": "unknown", "permission_status": "approved",
        "permission_evidence_type": "user_asserted_permission", "permission_evidence_note": "ok",
    }]
    try:
        p = d.build_discovery_plan("liver_manager")
    finally:
        d.load_sources = original
    ok = p["source_results"][0]["blocked_reasons"] == ["rights_status_not_media_approved"] and p["new_video_count"] == 0
    print(f"  {'PASS' if ok else 'FAIL'} discover blocks unapproved sources")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
