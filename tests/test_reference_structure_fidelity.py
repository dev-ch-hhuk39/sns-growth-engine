from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import generate_threads_ideas_from_references as ref


def test_text_reference_structure_guard_accepts_similar_shape() -> None:
    source = "Hook?\n\nReason one.\n\nReason two.\n\nClose."
    draft = "New hook?\n\nFirst reason.\n\nSecond reason.\n\nNew close."
    result = ref.reference_structure_fidelity(source, draft, source_platform="threads")
    assert result["pass"] is True
    assert result["applicable"] is True


def test_video_transcript_uses_semantic_not_layout_guard() -> None:
    result = ref.reference_structure_fidelity("long transcript", "short post", source_platform="youtube")
    assert result["pass"] is True
    assert result["applicable"] is False
