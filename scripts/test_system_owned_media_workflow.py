#!/usr/bin/env python3
from pathlib import Path

text = (Path(__file__).resolve().parents[1] / ".github/workflows/system-owned-media-canaries.yml").read_text(encoding="utf-8")
assert "workflow_dispatch:" in text and "schedule:" not in text
assert "GENERATE_SYSTEM_OWNED_MEDIA" in text
assert "run_system_owned_media_canaries.py" in text
assert "create_missing_text_canaries.py --targets \"$TEXT_TARGETS\" --apply --confirm-text-canaries" in text
assert "media_content_types" in text and "text_targets" in text
assert 'PUBLISH_ENABLED: "false"' in text and 'ALLOW_REAL_THREADS_POST: "false"' in text
assert 'ALLOW_CLOUDINARY_UPLOAD: ${{ inputs.mode == \'apply\'' in text
assert "set -o pipefail" in text
print("PASS")
