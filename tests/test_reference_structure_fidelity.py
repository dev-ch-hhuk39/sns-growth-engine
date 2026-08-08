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




def test_text_reference_structure_guard_blocks_major_collapse() -> None:
    source = "Hook?\n\nReason one.\n\nReason two.\n\nClose."
    draft = "One short replacement."
    result = ref.reference_structure_fidelity(source, draft, source_platform="threads")
    assert result["applicable"] is True
    assert result["pass"] is False
    assert result["reason"] == "source structure collapsed too far"


def test_japanese_sentence_units_are_detected_without_spaces() -> None:
    units = ref._structure_units("最初の問い？理由です。次の理由です。最後です。")
    assert len(units) == 4

def test_video_transcript_uses_semantic_not_layout_guard() -> None:
    result = ref.reference_structure_fidelity("long transcript", "short post", source_platform="youtube")
    assert result["pass"] is True
    assert result["applicable"] is False
