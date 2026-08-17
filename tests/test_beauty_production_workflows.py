from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))


def _load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _workflow(name: str) -> tuple[dict, str]:
    path = ROOT / ".github" / "workflows" / name
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text), text


def test_beauty_workflow_prepares_then_publishes_only_reviewed_ready_rows() -> None:
    data, text = _workflow("beauty-threads-production.yml")
    trigger = data.get("on") or data.get(True)
    assert trigger["schedule"] == [
        {"cron": "30 0 * * *"},
        {"cron": "30 9 * * *"},
        {"cron": "30 2 * * *"},
        {"cron": "30 11 * * *"},
    ]
    assert "--apply --confirm-prepare" in text
    assert "WAITING_REVIEW" in text
    assert "process_threads_queue.py --account-id beauty_account" in text
    assert "BEAUTY_PRODUCTION_ENABLED: \"true\"" in text
    assert "ALLOW_REAL_X_POST: \"false\"" in text
    assert "ALLOW_MEDIA_POSTS: \"false\"" in text
    assert "auto_approve_queue.py" not in text
    assert "Repository-wide Sheets diagnostic" in text
    assert "continue-on-error: true" in text
    assert "Strict Beauty queue and publisher preflight" in text
    assert text.count("recover_production_sheets_threads_first.py --verify-only") == 1
    assert "posted_results read-after-write" in text
    assert "queue-level read-after-write" in text


def test_token_refresh_workflow_includes_beauty_without_logging_token() -> None:
    _, text = _workflow("refresh-threads-tokens.yml")
    assert "beauty_account" in text
    assert "THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT" in text
    assert "refresh_threads_token.py --account-id beauty_account --confirm-refresh" in text
    assert "gh secret set THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT" in text
    assert "echo $THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT" not in text


def test_beauty_publisher_requires_config_and_dedicated_runtime_gate(monkeypatch, tmp_path) -> None:
    worker = _load_script("process_threads_queue.py")
    monkeypatch.delenv("BEAUTY_PRODUCTION_ENABLED", raising=False)
    allowed, reason = worker.beauty_publish_gate(dry_run=True)
    assert allowed is False
    assert reason == "beauty_production_config_not_enabled"
    config = tmp_path / "beauty.json"
    config.write_text(
        '{"status":"review_required_production","scheduled_publish_enabled":true,'
        '"real_post_enabled":true,"auto_ready_enabled":false}',
        encoding="utf-8",
    )
    monkeypatch.setattr(worker, "BEAUTY_PIPELINE_CONFIG", config)
    assert worker.beauty_publish_gate(dry_run=True) == (True, "")
    allowed, reason = worker.beauty_publish_gate(dry_run=False)
    assert allowed is False
    assert "BEAUTY_PRODUCTION_ENABLED" in reason
    monkeypatch.setenv("BEAUTY_PRODUCTION_ENABLED", "true")
    assert worker.beauty_publish_gate(dry_run=False) == (True, "")


def test_beauty_generated_candidate_is_never_ready(monkeypatch) -> None:
    prepare = _load_script("prepare_beauty_review_candidates.py")
    monkeypatch.setenv("GEMINI_API_KEY", "set-for-test")
    monkeypatch.setattr(
        prepare,
        "call_gemini_json",
        lambda *_args, **_kwargs: {
            "public_post_text": (
                "夕方のベースメイクが崩れる日は、ファンデを増やす前に朝の保湿量を見直してみて。\n\n"
                "私も重ねるほど安心だと思っていたけど、なじむ前に塗るとヨレやすいんだよね。"
                "保湿を薄くのばして少し待ち、ファンデは頬の中心から少量ずつ。まずは塗る量だけ変えると比べやすいよ。"
            ),
            "primary_topic": "ベースメイク前の保湿量",
        },
    )
    candidate = prepare.generate_candidate(slot_index=0, sequence_number=1)
    row = prepare.queue_row(candidate)
    assert candidate["status"] == "WAITING_REVIEW"
    assert row["status"] == "WAITING_REVIEW"
    assert row["auto_publish"] == "false"
    assert row["media_required"] == "false"
    assert row["validator_status"] == "PASS"


def test_beauty_secrets_are_referenced_by_name_only() -> None:
    _, beauty = _workflow("beauty-threads-production.yml")
    assert "${{ secrets.THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT }}" in beauty
    assert "${{ secrets.THREADS_USER_ID_BEAUTY_ACCOUNT }}" in beauty
    assert "${{ secrets.THREADS_HANDLE_BEAUTY_ACCOUNT }}" in beauty
    assert "access_token=" not in beauty.lower()
