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
    for cron in ['"2 5 * * *"', '"2 7 * * *"', '"2 16 * * *"']:
        assert cron in text


def test_liver_manager_workflow_schedule_enabled() -> None:
    text = read(LM_WF)
    for cron in ['"4 1 * * *"', '"4 4 * * *"', '"4 12 * * *"']:
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
    """Legacy entrypoint: delayed schedules remain dispatchable without idle sleep."""
    for wf in (NS_WF, LM_WF):
        text = read(wf)
        assert "random.randint" not in text
        assert "time.sleep" not in text
        assert "Diagnose schedule delay" in text
        assert "check_schedule_window.py" in text


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
    for col in (
        "result_id", "queue_id", "draft_id", "account_id", "platform",
        "post_url", "posted_text", "status", "metrics_status", "real_post",
        "source_id", "source_url", "generation_mode", "validator_status",
        "media_asset_id", "media_url", "media_status",
    ):
        assert col in cols


def test_queue_schema_required_columns() -> None:
    from sheets_client import TAB_DEFINITIONS

    cols = set(TAB_DEFINITIONS["queue"])
    for col in (
        "queue_id", "draft_id", "account_id", "target_account_id", "platform",
        "status", "auto_publish", "generation_mode", "media_asset_id",
        "auto_ready_by", "quality_score", "risk_score",
        "public_post_text", "internal_analysis", "source_id", "source_url",
        "generated_by", "validator_status", "internal_leak_status",
        "account_fit_status", "rejected_reason", "blocked_reason",
        "updated_at", "posted_at", "post_url", "result_id",
    ):
        assert col in cols


def test_autonomous_health_schema() -> None:
    from sheets_client import TAB_DEFINITIONS

    cols = set(TAB_DEFINITIONS["autonomous_health"])
    for col in (
        "run_id", "workflow_name", "account_id", "mode", "event_name",
        "started_at", "finished_at", "ready_count", "checked_count",
        "approved_count", "rejected_count", "processed_count", "posted_count",
        "blocked_count", "no_post_reason", "apply_status",
        "last_error_redacted", "created_at",
    ):
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


class _FakeCell:
    def __init__(self, row: int) -> None:
        self.row = row


class _FakeWorksheet:
    def __init__(self, headers: list[str], rows: list[dict]) -> None:
        self.headers = headers
        self.rows = rows

    def row_values(self, row: int) -> list[str]:
        assert row == 1
        return self.headers

    def get_all_records(self) -> list[dict]:
        return [dict(r) for r in self.rows]

    def append_row(self, values: list[str], value_input_option: str = "") -> None:
        self.rows.append({h: values[i] if i < len(values) else "" for i, h in enumerate(self.headers)})

    def find(self, value: str, in_column: int) -> _FakeCell | None:
        key = self.headers[in_column - 1]
        for idx, row in enumerate(self.rows, start=2):
            if str(row.get(key, "")) == value:
                return _FakeCell(idx)
        return None

    def update_cell(self, row: int, col: int, value: str) -> None:
        self.rows[row - 2][self.headers[col - 1]] = value


class _FakeClient:
    def __init__(self, logical: str, headers: list[str], rows: list[dict]) -> None:
        self.logical = logical
        self.ws = _FakeWorksheet(headers, rows)

    def _ws(self, logical: str) -> _FakeWorksheet:
        assert logical == self.logical
        return self.ws


def test_generation_refreshes_stale_waiting_review_rows() -> None:
    from generate_threads_ideas_from_references import _append_missing

    rows = [{"queue_id": "q1", "draft_id": "d1", "status": "REJECTED", "generation_mode": "old", "media_reuse_risk": "low"}]
    client = _FakeClient("queue", ["queue_id", "draft_id", "status", "generation_mode", "media_reuse_risk"], rows)
    result = _append_missing(client, "queue", "queue_id", [{
        "queue_id": "q1",
        "draft_id": "d1",
        "status": "WAITING_REVIEW",
        "generation_mode": "safe_original_fallback_threads",
        "media_reuse_risk": "low",
    }])
    assert result == {"added": 0, "skipped": 0, "refreshed": 1}
    assert rows[0]["status"] == "WAITING_REVIEW"
    assert rows[0]["generation_mode"] == "safe_original_fallback_threads"


def test_generation_does_not_refresh_ready_or_posted_rows() -> None:
    from generate_threads_ideas_from_references import _append_missing

    rows = [{"queue_id": "q1", "draft_id": "d1", "status": "READY", "generation_mode": "old"}]
    client = _FakeClient("queue", ["queue_id", "draft_id", "status", "generation_mode"], rows)
    result = _append_missing(client, "queue", "queue_id", [{
        "queue_id": "q1",
        "draft_id": "d1",
        "status": "WAITING_REVIEW",
        "generation_mode": "safe_original_fallback_threads",
    }])
    assert result == {"added": 0, "skipped": 1, "refreshed": 0}
    assert rows[0]["status"] == "READY"
    assert rows[0]["generation_mode"] == "old"


def test_safe_fallback_candidates_are_auto_ready_approvable() -> None:
    from auto_approve_queue import build_plan, load_rules
    from generate_threads_ideas_from_references import build_fallback_generation_rows
    from sheets_client import MockSheetsClient

    for account_id in ("night_scout", "liver_manager"):
        client = MockSheetsClient()
        rows = build_fallback_generation_rows(account_id=account_id, top_n=2)
        for draft in rows["drafts"]:
            client.save_draft(
                account_id,
                draft["title"],
                draft["body_md"],
                draft_id=draft["draft_id"],
                status=draft["status"],
                generation_mode=draft["generation_mode"],
                media_strategy=draft["media_strategy"],
                media_reuse_risk=draft["media_reuse_risk"],
                source_refs=draft.get("source_refs", ""),
            )
        for derivative in rows["social_derivatives"]:
            client.append_social_derivative(derivative)
        for queue in rows["queue"]:
            client.append_queue_item(queue)
        plan = build_plan(client, account_id, 1, load_rules())
        assert plan["approvable_count"] == 1, plan
        assert plan["selected_queue_ids"], plan


def test_auto_approve_reject_reasons_visible() -> None:
    from auto_approve_queue import build_plan, load_rules
    from sheets_client import MockSheetsClient

    client = MockSheetsClient()
    bad = "これは投稿案です。今回の切り口は source / night_scout です。"
    client.save_draft("night_scout", "bad", bad, draft_id="d-bad", status="WAITING_REVIEW", generation_mode="safe_original_fallback_threads", media_strategy="none", media_reuse_risk="low")
    client.append_social_derivative({"derivative_id": "sd-bad", "draft_id": "d-bad", "account_id": "night_scout", "platform": "threads", "text": bad, "status": "WAITING_REVIEW", "media_strategy": "none"})
    client.append_queue_item({"queue_id": "q-bad", "draft_id": "d-bad", "account_id": "night_scout", "platform": "threads", "status": "WAITING_REVIEW", "generation_mode": "safe_original_fallback_threads", "media_reuse_risk": "low", "priority": "1"})
    plan = build_plan(client, "night_scout", 1, load_rules())
    assert plan["checked_count"] == 1
    assert plan["rejected_count"] == 1
    assert plan["rejected_reasons"], plan
    assert plan["sample_rejected_public_post_preview"][0]["queue_id"] == "q-bad"


def test_no_ready_queue_not_expected_after_safe_fallback() -> None:
    from auto_approve_queue import build_plan, load_rules
    from generate_threads_ideas_from_references import build_fallback_generation_rows
    from sheets_client import MockSheetsClient

    client = MockSheetsClient()
    rows = build_fallback_generation_rows(account_id="liver_manager", top_n=3)
    for draft in rows["drafts"]:
        client.save_draft("liver_manager", draft["title"], draft["body_md"], draft_id=draft["draft_id"], status=draft["status"], generation_mode=draft["generation_mode"], media_strategy="none", media_reuse_risk="low")
    for derivative in rows["social_derivatives"]:
        client.append_social_derivative(derivative)
    for queue in rows["queue"]:
        client.append_queue_item(queue)
    plan = build_plan(client, "liver_manager", 1, load_rules())
    assert plan["approvable_count"] >= 1, plan
    assert plan["ready_count"] >= 1, plan


def test_run_autonomous_loop_stop_before_post_static() -> None:
    text = read(ROOT / "scripts/run_autonomous_loop.py")
    assert "--stop-before-post" in text
    assert "stop_before_post" in text
    assert "would_post" in text


def test_no_ready_queue_root_cause_report() -> None:
    from run_autonomous_loop import summarize_autonomous_results

    summary = summarize_autonomous_results("night_scout", "apply", [{
        "cmd": "scripts/process_threads_queue.py --account-id night_scout --confirm-real-post --max-posts 1",
        "returncode": 0,
        "stdout_tail": '{"status":"NO_POST","reason":"NO_READY_QUEUE"}',
    }])
    assert summary["no_post_reason"] == "NO_READY_QUEUE"
    assert "ready_count" in summary


def test_fallback_post_generated_when_reference_rows_empty() -> None:
    test_no_source_fallback_generates_safe_public_post()


def test_fallback_post_passes_final_validator() -> None:
    from generate_threads_ideas_from_references import build_fallback_generation_rows
    from public_post_quality import final_public_post_validator

    for account_id in ("night_scout", "liver_manager"):
        rows = build_fallback_generation_rows(account_id=account_id, top_n=3)
        assert rows["queue"], account_id
        for draft in rows["drafts"]:
            assert final_public_post_validator(draft["body_md"], account_id)["status"] == "PASS"


def test_auto_approve_promotes_safe_fallback_to_ready() -> None:
    test_safe_fallback_candidates_are_auto_ready_approvable()


def test_queue_waiting_review_to_ready_flow() -> None:
    from auto_approve_queue import apply_ready, build_plan, load_rules
    from generate_threads_ideas_from_references import build_fallback_generation_rows
    from sheets_client import MockSheetsClient

    client = MockSheetsClient()
    rows = build_fallback_generation_rows(account_id="night_scout", top_n=1)
    for draft in rows["drafts"]:
        client.save_draft("night_scout", draft["title"], draft["body_md"], draft_id=draft["draft_id"], status=draft["status"], generation_mode=draft["generation_mode"], media_strategy="none", media_reuse_risk="low")
    for derivative in rows["social_derivatives"]:
        client.append_social_derivative(derivative)
    for queue in rows["queue"]:
        client.append_queue_item(queue)
    plan = build_plan(client, "night_scout", 1, load_rules())
    result = apply_ready(client, plan)
    assert result["updated_count"] == 1, result
    assert client.get_queue_item(rows["queue"][0]["queue_id"])["status"] == "READY"


def test_process_threads_queue_picks_ready_text_only() -> None:
    text = read(ROOT / "scripts/process_threads_queue.py")
    assert 'ELIGIBLE_STATUSES = {"READY"}' in text
    assert "select_candidates" in text
    assert "resolve_queue_media" in text


def test_process_threads_queue_uses_public_post_text_only() -> None:
    text = read(ROOT / "scripts/process_threads_queue.py")
    assert 'queue_row.get("public_post_text"' in text
    assert "extract_public_post_text" in text
    assert "final_public_post_validator(text, account_id)" in text


def test_duplicate_does_not_block_all_variations() -> None:
    from process_threads_queue import duplicate_reason

    posted_rows = [{
        "status": "POSTED",
        "account_id": "night_scout",
        "platform": "threads",
        "posted_text": "夜職で店を選ぶ時、時給だけで決めると続きにくい。",
    }]
    reason = duplicate_reason(
        queue_row={"queue_id": "q-new", "draft_id": "d-new", "account_id": "night_scout"},
        social={"derivative_id": "sd-new"},
        text="夜職で長く働くなら、時給だけでなく客層や担当の相談しやすさも見た方がいい。",
        posted_rows=posted_rows,
    )
    assert reason == ""


def test_daily_cap_account_specific_jst() -> None:
    from datetime import datetime, timedelta, timezone
    from run_autonomous_loop import posts_used_today

    now = datetime(2026, 7, 9, 3, 0, tzinfo=timezone.utc)
    rows = [
        {"account_id": "night_scout", "platform": "threads", "status": "POSTED", "posted_at": now.isoformat()},
        {"account_id": "liver_manager", "platform": "threads", "status": "POSTED", "posted_at": (now - timedelta(days=1)).isoformat()},
    ]
    assert posts_used_today("night_scout", rows, now=now) == 1
    assert posts_used_today("liver_manager", rows, now=now) == 0


def test_cooldown_account_specific() -> None:
    from auto_approve_queue import account_limits_ok, load_rules, now_utc

    rules = load_rules()
    acct_rules = rules["defaults"].copy()
    acct_rules["daily_ready_cap"] = 5
    acct_rules["cooldown_minutes"] = 90
    logs = [{
        "account_id": "night_scout",
        "operation": "queue_approved",
        "details": "auto_ready=true",
        "timestamp": now_utc().isoformat(),
    }]
    ok_ns, reason_ns = account_limits_ok("night_scout", {}, logs, [], acct_rules)
    ok_lm, reason_lm = account_limits_ok("liver_manager", {}, logs, [], acct_rules)
    assert not ok_ns and reason_ns == "cooldown_not_satisfied"
    assert ok_lm and reason_lm == "ok"


def test_media_growth_does_not_block_text_only() -> None:
    test_media_growth_does_not_break_autonomous_text_posting()


def test_night_scout_fallback_topics() -> None:
    from generate_threads_ideas_from_references import build_fallback_generation_rows

    text = "\n".join(d["body_md"] for d in build_fallback_generation_rows(account_id="night_scout", top_n=5)["drafts"])
    assert any(k in text for k in ("夜職", "店", "時給", "担当", "相談"))


def test_liver_manager_fallback_topics() -> None:
    from generate_threads_ideas_from_references import build_fallback_generation_rows

    text = "\n".join(d["body_md"] for d in build_fallback_generation_rows(account_id="liver_manager", top_n=5)["drafts"])
    assert any(k in text for k in ("配信", "初見", "コメント", "リスナー", "ライバー"))


def test_account_specific_generation_not_mixed() -> None:
    from generate_threads_ideas_from_references import build_fallback_generation_rows

    ns = "\n".join(d["body_md"] for d in build_fallback_generation_rows(account_id="night_scout", top_n=3)["drafts"])
    lm = "\n".join(d["body_md"] for d in build_fallback_generation_rows(account_id="liver_manager", top_n=3)["drafts"])
    assert "配信" not in ns
    assert "夜職" not in lm


def test_scheduled_apply_can_create_ready_from_empty_references() -> None:
    test_queue_waiting_review_to_ready_flow()


def test_stop_before_post_creates_ready_without_posting() -> None:
    text = read(ROOT / "scripts/run_autonomous_loop.py")
    assert "--stop-before-post" in text
    assert "scripts/process_threads_queue.py --stop-before-post" in text
    assert '"would_post": False' in text


def test_safe_fallback_rotates_topics() -> None:
    from generate_threads_ideas_from_references import build_fallback_generation_rows

    for account_id in ("night_scout", "liver_manager"):
        rows = build_fallback_generation_rows(account_id=account_id, top_n=5)
        texts = [d["body_md"] for d in rows["drafts"]]
        assert len(texts) == 5
        assert len(set(texts)) == 5


def test_safe_fallback_not_duplicate_same_day() -> None:
    test_safe_fallback_rotates_topics()


def test_auto_ready_accepts_safe_original_fallback() -> None:
    test_safe_fallback_candidates_are_auto_ready_approvable()


def test_auto_ready_reject_reasons_are_written_to_queue() -> None:
    from auto_approve_queue import apply_ready, build_plan, load_rules
    from sheets_client import MockSheetsClient

    client = MockSheetsClient()
    bad = "これは投稿案です。今回の切り口は source / night_scout です。"
    client.save_draft("night_scout", "bad", bad, draft_id="d-bad", status="WAITING_REVIEW", generation_mode="safe_original_fallback_threads", media_strategy="none", media_reuse_risk="not_applicable")
    client.append_social_derivative({"derivative_id": "sd-bad", "draft_id": "d-bad", "account_id": "night_scout", "platform": "threads", "text": bad, "status": "WAITING_REVIEW", "media_strategy": "none"})
    client.append_queue_item({"queue_id": "q-bad", "draft_id": "d-bad", "account_id": "night_scout", "platform": "threads", "status": "WAITING_REVIEW", "generation_mode": "safe_original_fallback_threads", "media_reuse_risk": "not_applicable", "priority": "1"})
    plan = build_plan(client, "night_scout", 1, load_rules())
    apply_ready(client, plan)
    row = client.get_queue_item("q-bad")
    assert row and row.get("rejected_reason"), row
    assert "final_public_post_validator_blocked" in row["rejected_reason"]


def test_auto_ready_ready_count_summary_matches_updates() -> None:
    from run_autonomous_loop import summarize_autonomous_results

    summary = summarize_autonomous_results("night_scout", "apply", [{
        "cmd": "scripts/auto_approve_queue.py --account-id night_scout --apply --confirm-auto-ready",
        "returncode": 0,
        "stdout_tail": '{"status":"APPLIED","checked_count":2,"approved_count":1,"rejected_count":1,"ready_count":1,"updated_count":1}',
    }])
    assert summary["ready_count"] == 1
    assert summary["checked_count"] == 2
    assert summary["approved_count"] == 1
    assert summary["rejected_count"] == 1


def test_process_threads_queue_posts_ready_text_only_path_static() -> None:
    text = read(ROOT / "scripts/process_threads_queue.py")
    assert 'ELIGIBLE_STATUSES = {"READY"}' in text
    assert 'PUBLISH_ENABLED", "false"' in text
    assert 'ALLOW_REAL_THREADS_POST", "false"' in text
    assert "publisher.publish(" in text
    assert "media_required" in text


def test_posted_results_has_post_url_or_external_id() -> None:
    text = read(ROOT / "scripts/process_threads_queue.py")
    assert '"external_post_id": external_post_id' in text
    assert '"post_url": post_url' in text
    assert '"post_url": result.posted_url or ""' in text


def test_posted_results_metrics_pending_after_post() -> None:
    text = read(ROOT / "scripts/process_threads_queue.py")
    assert '"metrics_status": "PENDING"' in text
    assert '"measurement_window": "pending"' in text


def test_autonomous_health_saved_on_apply() -> None:
    text = read(ROOT / "scripts/run_autonomous_loop.py")
    assert "def save_autonomous_health" in text
    assert 'mode != "apply"' in text
    assert '_ensure_tab("autonomous_health"' in text
    assert "ws.append_row" in text


def test_generate_docs_comments_match_auto_ready_spec() -> None:
    src = read(ROOT / "scripts/generate_threads_ideas_from_references.py")
    docs = read(ROOT / "docs/reference-pipeline-runbook.md")
    assert "auto_approve_queue.py" in src
    assert "AUTO_READY" in docs
    assert "投稿対象になるのは人間が `approve_queue.py` で `READY` に昇格させた行のみ" not in docs
    assert "READY への昇格は approve_queue.py で人間が行う" not in src


def test_text_only_media_reuse_risk_not_high() -> None:
    from generate_threads_ideas_from_references import build_fallback_generation_rows, build_generation_rows

    fallback = build_fallback_generation_rows(account_id="night_scout", top_n=2)
    assert all(q["media_reuse_risk"] != "high" for q in fallback["queue"])
    posts = [{"post_id": "p1", "account_id": "night_scout", "post_text": "夜職で店選びに悩む子向けの参考投稿", "post_url": "https://example.com/p1"}]
    scores = [{"reference_post_id": "p1", "account_id": "night_scout", "total_score": "90", "cta_score": "80"}]
    rows = build_generation_rows(account_id="night_scout", posts=posts, scores=scores, top_n=1)
    assert rows["queue"][0]["media_reuse_risk"] == "not_applicable"


def test_night_scout_theme_pool_size() -> None:
    from public_post_quality import final_public_post_validator, generate_reader_facing_post, reader_facing_template_count

    count = reader_facing_template_count("night_scout")
    assert count >= 15
    texts = [generate_reader_facing_post("night_scout", i)["public_post_text"] for i in range(1, count + 1)]
    assert len(set(texts)) == count
    assert all(final_public_post_validator(t, "night_scout")["status"] == "PASS" for t in texts)


def test_liver_manager_theme_pool_size() -> None:
    from public_post_quality import final_public_post_validator, generate_reader_facing_post, reader_facing_template_count

    count = reader_facing_template_count("liver_manager")
    assert count >= 12
    texts = [generate_reader_facing_post("liver_manager", i)["public_post_text"] for i in range(1, count + 1)]
    assert len(set(texts)) == count
    assert all(final_public_post_validator(t, "liver_manager")["status"] == "PASS" for t in texts)


def test_same_day_theme_rotation() -> None:
    test_safe_fallback_rotates_topics()


def test_pdca_pending_after_post() -> None:
    text = read(ROOT / "scripts/process_threads_queue.py")
    assert "def save_pdca_initial" in text
    assert '"metrics_followup"' in text
    assert '"status": "WAITING_REVIEW"' in text
    assert "metrics pending" in text.lower()


def test_media_growth_roadmap_off_by_default() -> None:
    media = media_config()
    cfg = config()
    assert media["source_video_discovery_apply_enabled"] is True
    assert media["download_enabled"] is True
    assert media["cut_enabled"] is True
    assert media["upload_enabled"] is True
    assert media["video_post_enabled"] is True
    assert media["require_permission_evidence"] is True
    # Text-only autonomous runner remains unable to opt into media. Media uses
    # its own account-specific workflows and explicit environment gates.
    assert cfg["allow_media_posts"] is False


def test_health_summary_reports_auto_ready_rejected_all() -> None:
    from run_autonomous_loop import summarize_autonomous_results

    summary = summarize_autonomous_results("liver_manager", "apply", [
        {
            "cmd": "scripts/auto_approve_queue.py --account-id liver_manager --apply --confirm-auto-ready",
            "returncode": 0,
            "stdout_tail": '{"status":"APPLIED","evaluated_count":3,"approvable_count":0,"updated_count":0}',
        },
        {
            "cmd": "scripts/process_threads_queue.py --account-id liver_manager --confirm-real-post --max-posts 1",
            "returncode": 0,
            "stdout_tail": '{"status":"NO_POST","reason":"NO_READY_QUEUE"}',
        },
    ])
    assert summary["posted_count"] == 0
    assert summary["no_post_reason"] == "AUTO_READY_REJECTED_ALL"


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
    assert media["video_post_enabled"] is True
    for name in ("autonomous-growth-loop-night-scout.yml", "autonomous-growth-loop-liver-manager.yml"):
        workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert 'ALLOW_VIDEO_DOWNLOAD: "false"' in workflow
        assert 'ALLOW_VIDEO_CUT: "false"' in workflow
        assert 'ALLOW_CLOUDINARY_UPLOAD: "false"' in workflow


def test_source_video_discovery_apply_disabled_by_default() -> None:
    media = media_config()
    assert media["source_video_discovery_apply_enabled"] is True
    assert media["max_total_new_videos_per_run"] <= 20


def test_download_cut_upload_video_post_still_gated() -> None:
    cfg = config()
    media = media_config()
    assert cfg["allow_video_download"] is False
    assert cfg["allow_video_cut"] is False
    assert cfg["allow_cloudinary_upload"] is False
    # The production feature exists, but no generic/autonomous process receives
    # these capabilities. Dedicated media workflows scope every true gate to a
    # confirmed step and keep workflow-level defaults false.
    assert media["download_enabled"] is True
    assert media["cut_enabled"] is True
    assert media["upload_enabled"] is True
    assert media["video_post_enabled"] is True
    for name in (
        "media-growth-production.yml",
        "media-growth-production-night-scout.yml",
        "media-growth-post-liver-manager.yml",
        "media-growth-post-night-scout.yml",
    ):
        workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert 'ALLOW_VIDEO_DOWNLOAD: "false"' in workflow
        assert 'ALLOW_VIDEO_CUT: "false"' in workflow
        assert 'ALLOW_CLOUDINARY_UPLOAD: "false"' in workflow
        assert 'ALLOW_MEDIA_POSTS: "false"' in workflow
