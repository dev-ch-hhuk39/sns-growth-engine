from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

NS_WF = ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml"
LM_WF = ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml"
MANUAL_WF = ROOT / ".github/workflows/autonomous-growth-loop.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def config() -> dict:
    return json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))


def media_config() -> dict:
    return json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))


def sources() -> list[dict]:
    return json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8"))["sources"]


def chiishunin() -> dict:
    matches = [s for s in sources() if s.get("source_id") == "src_ns_threads_user_chiishunin_s"]
    assert matches, "src_ns_threads_user_chiishunin_s missing"
    return matches[0]


def run_cmd(args: list[str]) -> str:
    p = subprocess.run(args, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert p.returncode == 0, p.stdout[-1200:] + p.stderr[-1200:]
    return p.stdout


def test_scheduled_workflows_exist() -> None:
    assert NS_WF.exists()
    assert LM_WF.exists()
    assert MANUAL_WF.exists()


def test_night_scout_workflow_schedule_enabled() -> None:
    text = read(NS_WF)
    for cron in ['"45 4 * * *"', '"45 6 * * *"', '"45 8 * * *"', '"45 11 * * *"', '"45 15 * * *"']:
        assert cron in text


def test_liver_manager_workflow_schedule_enabled() -> None:
    text = read(LM_WF)
    for cron in ['"45 0 * * *"', '"45 3 * * *"', '"45 6 * * *"', '"45 8 * * *"', '"45 11 * * *"']:
        assert cron in text


def test_manual_workflow_has_no_schedule() -> None:
    assert "schedule:" not in read(MANUAL_WF)
    assert "workflow_dispatch:" in read(MANUAL_WF)


def test_scheduled_workflows_apply_on_schedule() -> None:
    for wf in (NS_WF, LM_WF):
        text = read(wf)
        assert "github.event_name == 'schedule'" in text
        assert "--apply" in text and "--confirm-autonomous" in text
        assert "dry_run_only != 'true'" in text


def test_scheduled_workflows_have_jitter() -> None:
    for wf in (NS_WF, LM_WF):
        text = read(wf)
        assert "random.randint(0, 1800)" in text
        assert "Schedule jitter" in text


def test_workflow_permissions_declared() -> None:
    for wf in (NS_WF, LM_WF, MANUAL_WF):
        text = read(wf)
        assert "permissions:" in text
        assert "contents: read" in text
        assert "actions: read" in text


def test_scheduled_workflows_have_heartbeat() -> None:
    for wf in (NS_WF, LM_WF):
        text = read(wf)
        assert "Schedule heartbeat" in text
        assert "github.workflow" in text
        assert "github.event_name" in text
        assert "date -u" in text


def test_scheduled_workflows_have_dry_run_only_dispatch() -> None:
    for wf in (NS_WF, LM_WF):
        text = read(wf)
        assert "dry_run_only:" in text
        assert "Run dry-run and health summary only; never apply/post" in text
        assert "dry_run_only != 'true'" in text


def test_scheduled_workflows_have_concurrency() -> None:
    for wf in (NS_WF, LM_WF):
        text = read(wf)
        assert "concurrency:" in text
        assert "cancel-in-progress: false" in text


def test_scheduled_workflows_schedule_event_runs_apply() -> None:
    for wf in (NS_WF, LM_WF):
        text = read(wf)
        assert "(github.event_name == 'schedule' || github.event.inputs.confirm_autonomous == 'true')" in text
        assert "dry_run_only != 'true'" in text
        assert "--apply" in text
        assert "--confirm-autonomous" in text


def test_manual_workflow_no_schedule() -> None:
    test_manual_workflow_has_no_schedule()


def test_workflow_names_not_confusing() -> None:
    assert "name: Autonomous Growth Loop Night Scout" in read(NS_WF)
    assert "name: Autonomous Growth Loop Liver Manager" in read(LM_WF)
    assert "name: Autonomous Growth Loop\n" in read(MANUAL_WF)
    assert "ACCOUNT_ID: \"night_scout\"" in read(NS_WF)
    assert "ACCOUNT_ID: \"liver_manager\"" in read(LM_WF)


def test_actions_enablement_runbook_docs() -> None:
    text = read(ROOT / "docs/autonomous-mode-runbook.md")
    for needle in (
        "Autonomous Growth Loop Night Scout",
        "Autonomous Growth Loop Liver Manager",
        "Enable workflow",
        "dry_run_only",
        "Schedule heartbeat",
        "NO_READY_QUEUE",
    ):
        assert needle in text


def test_scheduled_workflows_env_gates_scoped() -> None:
    for wf in (NS_WF, LM_WF, MANUAL_WF):
        text = read(wf)
        assert 'PUBLISH_ENABLED: "false"' in text
        assert 'ALLOW_REAL_THREADS_POST: "false"' in text
        assert 'PUBLISH_ENABLED: "true"' in text
        assert 'ALLOW_REAL_THREADS_POST: "true"' in text
        assert 'ALLOW_REAL_X_POST: "false"' in text


def test_workflow_account_id_fixed() -> None:
    assert 'ACCOUNT_ID: "night_scout"' in read(NS_WF)
    assert 'ACCOUNT_ID: "liver_manager"' in read(LM_WF)


def test_autonomous_config_enabled() -> None:
    cfg = config()
    assert cfg["autonomous_mode_enabled"] is True
    assert cfg["auto_post_enabled"] is True


def test_kill_switch_false_by_default() -> None:
    assert config()["kill_switch"] is False


def test_account_specific_run_does_not_rotate_away() -> None:
    from run_autonomous_loop import build_autonomous_plan

    ns = build_autonomous_plan("night_scout")
    lm = build_autonomous_plan("liver_manager")
    assert ns["accounts"] == ["night_scout"]
    assert ns["selected_account"] == "night_scout"
    assert ns["account_rotation"]["strategy"] == "fixed_account_override"
    assert lm["accounts"] == ["liver_manager"]
    assert lm["selected_account"] == "liver_manager"


def test_run_autonomous_loop_night_scout_dry_run() -> None:
    out = run_cmd([sys.executable, "scripts/run_autonomous_loop.py", "--account-id", "night_scout", "--dry-run"])
    assert '"selected_account": "night_scout"' in out
    assert '"would_post": false' in out
    assert "public_post_preview" in out


def test_run_autonomous_loop_liver_manager_dry_run() -> None:
    out = run_cmd([sys.executable, "scripts/run_autonomous_loop.py", "--account-id", "liver_manager", "--dry-run"])
    assert '"selected_account": "liver_manager"' in out
    assert '"would_post": false' in out
    assert "public_post_preview" in out


def test_run_autonomous_loop_preflight_no_real_post() -> None:
    out = subprocess.run(
        [sys.executable, "scripts/run_autonomous_loop.py", "--account-id", "night_scout", "--preflight"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    assert '"mode": "preflight"' in out
    assert '"would_post": false' in out
    assert '"mode": "apply"' not in out


def test_process_threads_queue_reports_no_post_reason() -> None:
    text = read(ROOT / "scripts/process_threads_queue.py")
    assert '"status": "NO_POST"' in text
    assert '"reason": "NO_READY_QUEUE"' in text


def test_auto_approve_can_promote_safe_candidate() -> None:
    from auto_approve_queue import build_plan, load_rules
    from public_post_quality import generate_reader_facing_post
    from sheets_client import MockSheetsClient

    client = MockSheetsClient()
    body = generate_reader_facing_post("night_scout", 1)["public_post_text"]
    client.save_draft("night_scout", body.splitlines()[0], body, draft_id="d-safe", status="WAITING_REVIEW", generation_mode="safe_original_fallback_threads", media_strategy="none", media_reuse_risk="low", source_refs="")
    client.append_social_derivative({"derivative_id": "sd-safe", "draft_id": "d-safe", "account_id": "night_scout", "platform": "threads", "text": body, "status": "WAITING_REVIEW", "media_strategy": "none"})
    client.append_queue_item({"queue_id": "q-safe", "draft_id": "d-safe", "account_id": "night_scout", "platform": "threads", "status": "WAITING_REVIEW", "generation_mode": "safe_original_fallback_threads", "media_reuse_risk": "low", "priority": "1"})
    plan = build_plan(client, "night_scout", 1, load_rules())
    assert plan["approvable_count"] == 1, plan


def test_ready_queue_can_be_processed_text_only() -> None:
    from process_threads_queue import resolve_queue_media

    media = resolve_queue_media({"media_asset_id": "", "media_required": "false"})
    assert media["media_usable"] is False
    assert media["block_reason"] == ""


def test_posted_results_schema_required_columns() -> None:
    from sheets_client import TAB_DEFINITIONS

    cols = set(TAB_DEFINITIONS["posted_results"])
    for col in ("result_id", "queue_id", "draft_id", "account_id", "platform", "post_url", "posted_text", "status", "metrics_status", "real_post"):
        assert col in cols


def test_queue_schema_required_columns() -> None:
    from sheets_client import TAB_DEFINITIONS

    cols = set(TAB_DEFINITIONS["queue"])
    for col in ("queue_id", "draft_id", "account_id", "platform", "status", "auto_publish", "generation_mode", "media_asset_id", "auto_ready_by", "quality_score", "risk_score"):
        assert col in cols


def test_night_scout_public_post_reader_facing() -> None:
    from public_post_quality import final_public_post_validator, generate_reader_facing_post

    for i in range(1, 11):
        text = generate_reader_facing_post("night_scout", i)["public_post_text"]
        assert final_public_post_validator(text, "night_scout")["status"] == "PASS"


def test_liver_manager_public_post_reader_facing() -> None:
    from public_post_quality import final_public_post_validator, generate_reader_facing_post

    for i in range(1, 11):
        text = generate_reader_facing_post("liver_manager", i)["public_post_text"]
        assert final_public_post_validator(text, "liver_manager")["status"] == "PASS"


def test_public_post_never_contains_internal_terms() -> None:
    from public_post_quality import INTERNAL_LEAK_TERMS, generate_reader_facing_post

    for account in ("night_scout", "liver_manager"):
        for i in range(1, 11):
            text = generate_reader_facing_post(account, i)["public_post_text"].lower()
            assert not [t for t in INTERNAL_LEAK_TERMS if t.lower() in text]


def test_public_post_text_only_passed_to_publisher() -> None:
    text = read(ROOT / "scripts/process_threads_queue.py")
    assert "extract_public_post_text" in text
    assert "final_public_post_validator(text, account_id)" in text
    assert "publisher.publish(" in text and "text," in text


def test_daily_five_post_generation_variation() -> None:
    from public_post_quality import generate_reader_facing_post

    for account in ("night_scout", "liver_manager"):
        texts = [generate_reader_facing_post(account, i)["public_post_text"] for i in range(1, 6)]
        assert len(set(texts)) == 5


def test_no_source_fallback_generates_safe_public_post() -> None:
    from generate_threads_ideas_from_references import build_fallback_generation_rows
    from public_post_quality import final_public_post_validator

    rows = build_fallback_generation_rows(account_id="night_scout", top_n=2)
    assert len(rows["queue"]) == 2
    assert all(q["status"] == "WAITING_REVIEW" for q in rows["queue"])
    assert all(final_public_post_validator(d["body_md"], "night_scout")["status"] == "PASS" for d in rows["drafts"])


def test_reference_similarity_guard_still_blocks_copy() -> None:
    from generate_threads_ideas_from_references import original_text_similarity_guard

    text = "同じ文章をそのまま使うのは危険です。" * 5
    assert original_text_similarity_guard(text, text)["status"] == "BLOCKED"


def test_add_chiishunin_s_threads_source() -> None:
    s = chiishunin()
    assert s["source_url"] == "https://www.threads.com/@chiishunin_s"
    assert s["source_platform"] == "threads"


def test_chiishunin_s_source_target_night_scout() -> None:
    s = chiishunin()
    assert s["target_account_id"] == "night_scout"
    assert s["target_account_ids"] == ["night_scout"]


def test_chiishunin_s_source_no_media_pipeline() -> None:
    s = chiishunin()
    assert s["media_pipeline_eligible"] is False
    assert s["clip_enabled"] is False
    assert s["can_reuse_media"] is False
    assert s["allow_download"] is False
    assert s["allow_cut"] is False
    assert s["allow_upload"] is False


def test_chiishunin_s_source_reference_only() -> None:
    s = chiishunin()
    assert s["rights_status"] == "third_party_reference_only"
    assert s["reuse_policy"] == "reference_only"
    assert s["media_policy"] == "do_not_download"


def test_media_growth_does_not_break_autonomous_text_posting() -> None:
    cfg = config()
    media = media_config()
    assert cfg["auto_post_enabled"] is True
    assert cfg["allow_media_posts"] is False
    assert media["video_post_enabled"] is False


def test_source_video_discovery_apply_disabled_by_default() -> None:
    assert media_config()["source_video_discovery_apply_enabled"] is False


def test_download_cut_upload_video_post_still_gated() -> None:
    cfg = config()
    media = media_config()
    assert cfg["allow_video_download"] is False
    assert cfg["allow_video_cut"] is False
    assert cfg["allow_cloudinary_upload"] is False
    assert media["download_enabled"] is False
    assert media["cut_enabled"] is False
    assert media["upload_enabled"] is False
    assert media["video_post_enabled"] is False
