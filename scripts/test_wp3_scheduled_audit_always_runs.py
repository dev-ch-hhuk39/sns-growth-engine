#!/usr/bin/env python3
from pathlib import Path
import yaml

path = Path('.github/workflows/wp3-production-readonly-verification.yml')
text = path.read_text(encoding='utf-8')
doc = yaml.safe_load(text)

assert 'workflow_dispatch' in doc.get(True, {}), doc.get(True, {})
assert 'schedule' not in doc.get(True, {}), doc.get(True, {})

job = doc['jobs']['readonly_verification']
steps = job['steps']
by_name = {step.get('name'): step for step in steps}

collector = by_name['Collect Read-Only Evidence']
audit = by_name['Audit Scheduled Autopost Candidates']
preserve = by_name['Preserve WP3 evidence failure after audit']

assert collector.get('continue-on-error') is True
assert collector.get('id') == 'collector'
assert audit.get('id') == 'scheduled_audit'
assert audit.get('if') == 'always()'
assert preserve.get('if') == "always() && steps.collector.outcome == 'failure'"
assert 'WP3_READONLY_EVIDENCE_FAILED_AFTER_SCHEDULED_AUDIT' in preserve['run']
assert 'exit 1' in preserve['run']

names = [step.get('name') for step in steps]
assert names.index('Collect Read-Only Evidence') < names.index('Audit Scheduled Autopost Candidates')
assert names.index('Audit Scheduled Autopost Candidates') < names.index('Preserve WP3 evidence failure after audit')

for key in (
    'PUBLISH_ENABLED',
    'ALLOW_REAL_THREADS_POST',
    'ALLOW_REAL_X_POST',
    'ALLOW_VIDEO_DOWNLOAD',
    'ALLOW_VIDEO_CUT',
    'ALLOW_CLOUDINARY_UPLOAD',
    'ALLOW_MEDIA_POSTS',
    'ALLOW_REAL_THREADS_VIDEO_POST',
    'ALLOW_TRANSCRIPTION_API',
):
    assert str(doc['env'][key]).lower() == 'false', (key, doc['env'][key])

for forbidden in (
    'process_threads_queue.py',
    'threads_publisher.py',
    '--confirm-real-post',
    '--confirm-upload',
    '--confirm-download',
    '--confirm-cut',
):
    assert forbidden not in text, forbidden

print('PASS test_wp3_scheduled_audit_always_runs.py')
