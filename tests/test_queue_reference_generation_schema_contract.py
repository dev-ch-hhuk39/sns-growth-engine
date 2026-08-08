from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sheets_client import TAB_DEFINITIONS


REFERENCE_QUEUE_REQUIRED_FIELDS = {
    "schedule_date_jst",
    "theme",
    "visual_topic_confidence",
    "visual_topic_direct_confidence",
}


def test_queue_schema_persists_reference_generation_fields() -> None:
    headers = TAB_DEFINITIONS["queue"]
    missing = sorted(REFERENCE_QUEUE_REQUIRED_FIELDS - set(headers))
    assert missing == []
    assert len(headers) == len(set(headers))


def test_reference_generation_fields_have_stable_semantic_neighbors() -> None:
    headers = TAB_DEFINITIONS["queue"]
    assert headers.index("schedule_date_jst") > headers.index("business_date_jst")
    assert headers.index("theme") > headers.index("schedule_date_jst")
    assert headers.index("visual_topic_confidence") > headers.index("visual_topic")
    assert headers.index("visual_topic_direct_confidence") > headers.index("visual_topic_confidence")
