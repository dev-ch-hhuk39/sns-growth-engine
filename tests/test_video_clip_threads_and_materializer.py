from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from generation import video_clip_generator as gen
from generation.video_clip_materializer import build_ffmpeg_command, parse_timecode, validate_bounds


def candidate(**overrides):
    row = {
        "clip_id": "clip-1",
        "source_video_id": "sv-1",
        "rights_status": "allowed",
        "permission_status": "granted",
        "media_reuse_risk": "low",
        "start_seconds": "10",
        "end_seconds": "25",
        "transcript_excerpt": "example",
    }
    row.update(overrides)
    return row


def test_clip_generation_is_account_aware_and_threads_only() -> None:
    for account_id in ("night_scout", "liver_manager"):
        prompt = gen._build_system_prompt(account_id)
        assert account_id in prompt
        output = gen.generate_from_clip(candidate(), {"account_id": account_id}, mock_llm=True)
        assert output["threads_text"]
        assert "x_text" not in output
        saved = gen.save_clip_generation_result(None, candidate(), output, account_id=account_id, dry_run=True)
        assert saved["platform"] == "threads"
        assert len(saved["queue_ids"]) == 1


def test_rights_block_prevents_queue_candidate() -> None:
    output = gen.generate_from_clip(candidate(), {"account_id": "liver_manager"}, mock_llm=True)
    saved = gen.save_clip_generation_result(None, candidate(rights_status="not_allowed"), output, account_id="liver_manager", dry_run=True)
    assert saved["rights_blocked"] is True
    assert saved["queue_ids"] == []


def test_ffmpeg_command_is_bounded_and_non_shell() -> None:
    assert parse_timecode("01:02.5") == 62.5
    assert validate_bounds(10, 25) == 15
    cmd = build_ffmpeg_command("in.mp4", "out.mp4", 10, 25)
    assert cmd[0] == "ffmpeg"
    assert "-ss" in cmd and "-t" in cmd
    assert "in.mp4" in cmd and "out.mp4" in cmd
    assert all(";" not in part for part in cmd)


def test_real_clip_generation_uses_call_gemini_json_prompt_keyword(monkeypatch) -> None:
    import llm_client

    captured = {}

    def fake_call_gemini_json(prompt, *, system_prompt=None, **kwargs):
        captured["prompt"] = prompt
        captured["system_prompt"] = system_prompt
        captured["kwargs"] = kwargs
        return {
            "threads_text": "実呼び出し経路のテスト投稿",
            "title": "テスト",
            "hypothesis": "test",
            "media_strategy": "video_clip",
        }

    monkeypatch.setattr(llm_client, "call_gemini_json", fake_call_gemini_json)
    result = gen.generate_from_clip(candidate(), {"account_id": "liver_manager"}, mock_llm=False)
    assert result["threads_text"]
    assert captured["prompt"]
    assert captured["system_prompt"]
    assert "user_prompt" not in captured["kwargs"]
