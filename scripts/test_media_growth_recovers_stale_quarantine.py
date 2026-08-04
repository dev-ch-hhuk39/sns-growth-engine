#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
import run_media_growth_engine as growth
mapped = growth._clip_row_for_sheets({
    'clip_candidate_id': 'clip_chunked_02', 'clip_id': 'clip_chunked_02',
    'source_video_id': 'sv_chunked', 'transcript_id': 'tr_sv_chunked_merged',
    'account_id': 'night_scout', 'transcript_grounded': True,
    'transcript_excerpt': 'キャバ嬢として出勤する店舗を選ぶ時は、時給と客層を確認して自分が働く環境を比べます。',
    'start_seconds': 623.279, 'end_seconds': 661.36,
    'public_post_validator_status': 'PASS', 'alignment_status': 'PASS',
    'source_evidence_status': 'PASS', 'clip_status': 'WAITING_REVIEW',
    'reviewer_status': 'WAITING_REVIEW',
})
old = {
    **mapped, 'transcript_id': 'tr_sv_chunked', 'retry_count': '2',
    'last_error': 'old_pipeline_failure', 'failure_signature': 'old-signature',
    'same_failure_count': '2', 'quarantined_at': '2026-08-01T00:00:00+00:00',
    'quarantine_reason': 'old_pipeline_failure', 'notes': 'old candidate',
}
merged = growth._recover_stale_quarantine(old=old, mapped=mapped, merged={**old, **mapped}, evidence_changed=True)
second_old = {**merged, 'quarantined_at': '2026-08-02T00:00:00+00:00', 'quarantine_reason': 'new_real_failure'}
second = growth._recover_stale_quarantine(old=second_old, mapped=mapped, merged=dict(second_old), evidence_changed=True)
checks = [
    ('actual merged transcript ID is preserved', mapped['transcript_id'] == 'tr_sv_chunked_merged'),
    ('material repair clears stale quarantine', merged['quarantined_at'] == '' and merged['same_failure_count'] == '0'),
    ('recovery marker is persisted', growth.STALE_QUARANTINE_RECOVERY_MARKER in merged['notes']),
    ('same recovery is not repeated forever', second['quarantined_at'] == '2026-08-02T00:00:00+00:00'),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
