#!/usr/bin/env python3
"""全 .github/workflows/*.yml の publish 系安全フラグを横断検証する。

既存の test_github_actions_dry_run_workflow.py は v2-dry-run-check.yml 1 本のみを
検査していた。本テストは「全ワークフローが既定で実投稿・実アップロード・実ダウンロード
を行わない（実アクションは必ず人手の confirm 入力でゲートされる）」という不変条件を
全ファイル横断で固定する回帰テスト。

不変条件:
  1. workflow / job スコープの env では監視フラグは literal "false" のみ
     （このスコープは全 step に無条件適用されるため "true" を許さない）。
  2. step スコープ env で literal "true" を設定するなら、その step は confirm を
     参照する if: ガードを持つこと。
  3. step env を ${{ }} 条件式でフラグ設定するなら、式に confirm を含むこと
     （既定 false を保証）。
  4. --confirm-real-post / --confirm-upload / --confirm-download / --confirm-cut を
     含む run: は、step の if: か run: 本文が confirm ガードを持つこと。
  5. Scheduled production is allowed only for the explicit account-scoped
     text/media workflows below. Their dry-run, kill switch, fixed account,
     confirmation/trigger guard, and step-scoped env are checked separately.

Sheets / 外部 API 不要。YAML 構造とファイル内容のみを検査する。
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

# 既定で false でなければならない監視フラグ。
WATCHED_FLAGS = [
    "PUBLISH_ENABLED",
    "ALLOW_REAL_X_POST",
    "ALLOW_REAL_THREADS_POST",
    "ALLOW_TRANSCRIPTION_API",
    "ALLOW_CLOUDINARY_UPLOAD",
    "ALLOW_VIDEO_DOWNLOAD",
    "ALLOW_VIDEO_CUT",
    "ALLOW_MEDIA_POSTS",
    "ALLOW_REAL_THREADS_VIDEO_POST",
]
# 実アクションを起こす confirm コマンド（--confirm-post は dry-run と併用される
# ため対象外。実投稿/実アップロード/実ダウンロード/実切り抜きの 4 種を対象）。
REAL_ACTION_CMDS = [
    "--confirm-real-post",
    "--confirm-upload",
    "--confirm-download",
    "--confirm-cut",
]


def _has_confirm(text: str) -> bool:
    """if: 条件や run: 本文に confirm ゲートが含まれるか（大文字小文字無視）。"""
    return "confirm" in (text or "").lower()


def _flag_value_str(value) -> str:
    """env 値を文字列化（bool True/False も小文字文字列に正規化）。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _is_template_expr(value) -> bool:
    return isinstance(value, str) and "${{" in value


def _get_on(wf: dict):
    """YAML 1.1 では `on:` が bool True キーにパースされるため両対応。"""
    if True in wf:
        return wf[True]
    return wf.get("on")


def _iter_scope_envs(wf: dict):
    """workflow / job スコープ env を (scope_label, env_dict) で列挙。"""
    if isinstance(wf.get("env"), dict):
        yield ("workflow", wf["env"])
    for job_name, job in (wf.get("jobs") or {}).items():
        if isinstance(job, dict) and isinstance(job.get("env"), dict):
            yield (f"job:{job_name}", job["env"])


def _iter_steps(wf: dict):
    """全 job の step を (job_name, step_dict) で列挙。"""
    for job_name, job in (wf.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict):
                yield (job_name, step)


def check_workflow(path: Path) -> list[tuple[str, bool]]:
    text = path.read_text(encoding="utf-8")
    wf = yaml.safe_load(text)
    name = path.name
    checks: list[tuple[str, bool]] = []

    # --- 不変条件 1: workflow/job スコープ env はフラグを true にしない ---
    for scope, env in _iter_scope_envs(wf):
        for flag in WATCHED_FLAGS:
            if flag in env:
                val = _flag_value_str(env[flag]).lower()
                ok = val == "false"
                checks.append(
                    (f"{name} [{scope}] {flag} は false（実値={val}）", ok)
                )

    # --- 不変条件 2/3: step スコープ env のフラグ設定 ---
    for job_name, step in _iter_steps(wf):
        env = step.get("env") or {}
        if not isinstance(env, dict):
            continue
        step_label = step.get("name", "(no-name)")
        if_cond = step.get("if", "")
        for flag in WATCHED_FLAGS:
            if flag not in env:
                continue
            raw = env[flag]
            if _is_template_expr(raw):
                # 条件式: confirm を含めば既定 false が保証される。
                ok = _has_confirm(raw)
                checks.append(
                    (f"{name} step[{step_label}] {flag} 条件式は confirm でゲート", ok)
                )
            elif _flag_value_str(raw).lower() == "true":
                # literal true: step if: が confirm を参照していること。
                ok = _has_confirm(if_cond)
                checks.append(
                    (f"{name} step[{step_label}] {flag}=true は if: confirm ゲート", ok)
                )
            # literal false はそのまま安全。

    # --- 不変条件 4: 実アクション confirm コマンドはゲートされる ---
    for job_name, step in _iter_steps(wf):
        run = step.get("run", "") or ""
        if_cond = step.get("if", "")
        step_label = step.get("name", "(no-name)")
        used = [c for c in REAL_ACTION_CMDS if c in run]
        if not used:
            continue
        # ゲート判定の前に実アクションコマンド自体を run から除去する。
        # （--confirm-real-post 等のフラグ名に "confirm" が含まれるため、コマンド自身で
        #   ゲート成立と誤判定する vacuous pass を防ぐ。）
        run_wo_cmds = run
        for c in REAL_ACTION_CMDS:
            run_wo_cmds = run_wo_cmds.replace(c, "")
        # step if: が confirm を参照、または run 本文（コマンド除去後）に confirm
        # バッシュガード（例: $CONFIRM_REAL_POST / confirm=yes）がある。
        ok = _has_confirm(if_cond) or _has_confirm(run_wo_cmds)
        for cmd in used:
            checks.append(
                (f"{name} step[{step_label}] {cmd} は confirm ゲート", ok)
            )

    # --- 不変条件 5: schedule トリガは実アクションを一切持たない ---
    # 例外: autonomous-growth-loop.yml は初回Actions apply成功後の明示方針として、
    # scheduleでもThreads text-only applyを許可する。ただしdry-run先行、kill_switch、
    # X/media/download/cut/upload/transcription禁止、confirm/schedule if gateを必須にする。
    on_val = _get_on(wf)
    has_schedule = isinstance(on_val, dict) and "schedule" in on_val
    if has_schedule:
        if name in {"autonomous-growth-loop-night-scout.yml", "autonomous-growth-loop-liver-manager.yml"}:
            if name == "autonomous-growth-loop-night-scout.yml":
                expected = ['cron: "2 5 * * *"', 'cron: "2 7 * * *"', 'cron: "2 16 * * *"']
            else:
                expected = ['cron: "4 1 * * *"', 'cron: "4 4 * * *"', 'cron: "4 12 * * *"']
            checks.append((f"{name} [schedule] account slots cron", all(slot in text for slot in expected)))
            checks.append((f"{name} [schedule] dry-run step exists", "Dry-run autonomous plan" in text))
            checks.append((f"{name} [schedule] no idle delay", "random.randint" not in text and "time.sleep" not in text))
            checks.append((f"{name} [schedule] delayed event is diagnostic only", "Diagnose schedule delay" in text and "steps.schedule_window.outputs.in_window" not in text))
            checks.append((f"{name} [schedule] kill_switch guard exists", "kill_switch" in text))
            checks.append((f"{name} [schedule] schedule or confirm apply gate", "github.event_name == 'schedule' || github.event.inputs.confirm_autonomous == 'true'" in text))
            checks.append((f"{name} [schedule] X/media flags remain false", all(flag in text for flag in [
                'ALLOW_REAL_X_POST: "false"',
                'ALLOW_VIDEO_DOWNLOAD: "false"',
                'ALLOW_VIDEO_CUT: "false"',
                'ALLOW_CLOUDINARY_UPLOAD: "false"',
                'ALLOW_TRANSCRIPTION_API: "false"',
            ])))
            return checks
        if name in {"direct-reference-media-liver-manager.yml", "direct-reference-media-night-scout.yml"}:
            account_id = "liver_manager" if "liver" in name else "night_scout"
            cron = 'cron: "4 7 * * *"' if account_id == "liver_manager" else 'cron: "2 9 * * *"'
            checks.append((f"{name} [schedule] fixed direct-media account", f'ACCOUNT_ID: "{account_id}"' in text))
            checks.append((f"{name} [schedule] direct-media slot cron", cron in text))
            checks.append((f"{name} [schedule] prepared-only dispatch and fallback", "Dry-run prepared inventory" in text and "--post-ready" in text and "--fallback-to-text" in text and "acquire_approved_source_posts.py" not in text and "ingest_direct_reference_media.py" not in text))
            checks.append((f"{name} [schedule] delayed schedule remains dispatchable", "Diagnose schedule delay" in text and "steps.schedule_window.outputs.in_window" not in text))
            checks.append((f"{name} [schedule] scoped media posting gates", all(flag in text for flag in ['PUBLISH_ENABLED: "true"', 'ALLOW_REAL_THREADS_POST: "true"', 'ALLOW_MEDIA_POSTS: "true"', 'ALLOW_REAL_THREADS_VIDEO_POST: "true"'])))
            checks.append((f"{name} [schedule] no download/cut/upload", all(flag in text for flag in ['ALLOW_VIDEO_DOWNLOAD: "false"', 'ALLOW_VIDEO_CUT: "false"', 'ALLOW_CLOUDINARY_UPLOAD: "false"'])))
            return checks
        if name == "content-slot-recovery.yml":
            checks.append((f"{name} [schedule] 30-minute recovery cron", 'cron: "0,30 * * * *"' in text))
            checks.append((f"{name} [schedule] dry-run and explicit backfill worker", "--dry-run" in text and "--confirm-backfill" in text))
            checks.append((f"{name} [schedule] scoped READY dispatcher gates", all(flag in text for flag in ['PUBLISH_ENABLED: "true"', 'ALLOW_REAL_THREADS_POST: "true"', 'ALLOW_MEDIA_POSTS: "true"', 'ALLOW_REAL_THREADS_VIDEO_POST: "true"'])))
            checks.append((f"{name} [schedule] X/heavy media operations remain blocked", all(flag in text for flag in ['ALLOW_REAL_X_POST: "false"', 'ALLOW_VIDEO_DOWNLOAD: "false"', 'ALLOW_VIDEO_CUT: "false"', 'ALLOW_CLOUDINARY_UPLOAD: "false"', 'ALLOW_TRANSCRIPTION_API: "false"'])))
            return checks
        if name in {"media-growth-production.yml", "media-growth-production-night-scout.yml"}:
            account_id = "liver_manager" if name == "media-growth-production.yml" else "night_scout"
            cron = 'cron: "20 22 * * *"' if name == "media-growth-production.yml" else 'cron: "20 2 * * *"'
            checks.append((f"{name} [schedule] fixed media account", f'ACCOUNT_ID: "{account_id}"' in text))
            checks.append((f"{name} [schedule] daily one-slot cron", cron in text))
            checks.append((f"{name} [schedule] kill_switch guard exists", "kill_switch" in text))
            checks.append((f"{name} [schedule] dedicated confirmation gate", "confirm_production_media" in text))
            checks.append((f"{name} [schedule] approved production runner only", "run_media_production_pipeline.py" in text))
            checks.append((f"{name} [schedule] X/transcription remain false", 'ALLOW_REAL_X_POST: "false"' in text and 'ALLOW_TRANSCRIPTION_API: "false"' in text))
            checks.append((f"{name} [schedule] prepare-only media gates", all(flag in text for flag in [
                'ALLOW_VIDEO_DOWNLOAD: "true"',
                'ALLOW_VIDEO_CUT: "true"',
                'ALLOW_CLOUDINARY_UPLOAD: "true"',
                '--prepare-only',
                'ALLOW_MEDIA_POSTS: "false"',
                'ALLOW_REAL_THREADS_VIDEO_POST: "false"',
            ])))
            return checks
        if name in {"media-growth-post-liver-manager.yml", "media-growth-post-night-scout.yml"}:
            account_id = "liver_manager" if name.endswith("liver-manager.yml") else "night_scout"
            cron = 'cron: "4 9 * * *"' if account_id == "liver_manager" else 'cron: "2 12 * * *"'
            checks.append((f"{name} [schedule] fixed media account", f'ACCOUNT_ID: "{account_id}"' in text))
            checks.append((f"{name} [schedule] media slot cron", cron in text))
            checks.append((f"{name} [schedule] dry run and delayed-event dispatch", "Dry-run saved media plan" in text and "Diagnose schedule delay" in text and "steps.schedule_window.outputs.in_window" not in text and "time.sleep" not in text))
            checks.append((f"{name} [schedule] kill switch and saved-only runner", "kill_switch" in text and "--post-saved-media" in text))
            checks.append((f"{name} [schedule] scoped posting gates", all(flag in text for flag in [
                'PUBLISH_ENABLED: "true"', 'ALLOW_REAL_THREADS_POST: "true"',
                'ALLOW_MEDIA_POSTS: "true"', 'ALLOW_REAL_THREADS_VIDEO_POST: "true"',
            ])))
            checks.append((f"{name} [schedule] no download/cut/upload", all(flag in text for flag in [
                'ALLOW_VIDEO_DOWNLOAD: "false"', 'ALLOW_VIDEO_CUT: "false"', 'ALLOW_CLOUDINARY_UPLOAD: "false"',
            ])))
            return checks
        if name == "media-transcription-production.yml":
            checks.append((f"{name} [schedule] liver_manager only", 'ACCOUNT_ID: "liver_manager"' in text))
            checks.append((f"{name} [schedule] daily transcription cron", 'cron: "10 15 * * *"' in text))
            checks.append((f"{name} [schedule] dry-run first", "Dry-run transcription plan" in text))
            checks.append((f"{name} [schedule] kill_switch guard exists", "kill_switch" in text))
            checks.append((f"{name} [schedule] schedule or confirm transcription gate", "github.event_name == 'schedule' || github.event.inputs.confirm_transcription == 'true'" in text))
            checks.append((f"{name} [schedule] no post/cut/upload gates", all(flag in text for flag in [
                'PUBLISH_ENABLED: "false"',
                'ALLOW_REAL_THREADS_POST: "false"',
                'ALLOW_REAL_X_POST: "false"',
                'ALLOW_VIDEO_CUT: "false"',
                'ALLOW_CLOUDINARY_UPLOAD: "false"',
                'ALLOW_MEDIA_POSTS: "false"',
                'ALLOW_REAL_THREADS_VIDEO_POST: "false"',
                'ALLOW_TRANSCRIPTION_API: "false"',
            ])))
            checks.append((f"{name} [schedule] local transcription download scoped", 'ALLOW_VIDEO_DOWNLOAD: "true"' in text and 'ALLOW_LOCAL_TRANSCRIPTION: "true"' in text))
            checks.append((f"{name} [schedule] bounded transcription", "--limit 1" in text))
            return checks
        if name == "direct-media-preparation.yml":
            checks.append((f"{name} [schedule] two approved account preparations", "night_scout" in text and "liver_manager" in text))
            checks.append((f"{name} [schedule] download and Cloudinary are ingest-step scoped", 'ALLOW_VIDEO_DOWNLOAD: "true"' in text and 'ALLOW_CLOUDINARY_UPLOAD: "true"' in text and "--confirm-ingest" in text))
            checks.append((f"{name} [schedule] READY-only preparation", "--prepare-only" in text and "--confirm-direct-media" in text))
            checks.append((f"{name} [schedule] never publishes or cuts", all(flag in text for flag in [
                'PUBLISH_ENABLED: "false"', 'ALLOW_REAL_THREADS_POST: "false"',
                'ALLOW_MEDIA_POSTS: "false"', 'ALLOW_REAL_THREADS_VIDEO_POST: "false"',
                'ALLOW_VIDEO_CUT: "false"', 'ALLOW_REAL_X_POST: "false"',
            ]) and "--confirm-real-post" not in text))
            return checks
        # ファイル全体で literal "true" フラグ無し。
        lower = text.lower()
        for flag in WATCHED_FLAGS:
            # `FLAG: "true"` の literal 出現を素朴に検出（条件式は対象外）。
            literal_true = f'{flag.lower()}: "true"' in lower or f"{flag.lower()}: 'true'" in lower
            checks.append(
                (f"{name} [schedule] {flag} literal true 無し", not literal_true)
            )
        for cmd in REAL_ACTION_CMDS:
            checks.append(
                (f"{name} [schedule] {cmd} 無し", cmd not in text)
            )

    return checks


def main() -> int:
    files = sorted(WORKFLOW_DIR.glob("*.yml"))
    checks: list[tuple[str, bool]] = []

    checks.append((f"workflows ディレクトリに *.yml が存在（{len(files)} 本）", len(files) >= 1))

    for path in files:
        checks.extend(check_workflow(path))

    failed = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {n}")
    print(f"\n検査ワークフロー: {len(files)} 本")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
