#!/usr/bin/env python3
"""Guard the scheduled Threads token refresh ordering and shared-store contract."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/refresh-threads-tokens.yml"
workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
steps = workflow["jobs"]["refresh"]["steps"]
steps_by_name = {step["name"]: step for step in steps if "name" in step}

checks: list[tuple[str, bool]] = []


def run(name: str) -> str:
    return steps_by_name[name].get("run", "")


names = [step.get("name", "") for step in steps]
checks.extend(
    [
        (
            "pinned CLI bootstrap with checksum precedes secret capability probe",
            names.index("Bootstrap pinned GitHub CLI")
            < names.index("Preflight GitHub Secret write capability")
            and "version=\"2.101.0\"" in run("Bootstrap pinned GitHub CLI")
            and "sha256sum --check --status" in run("Bootstrap pinned GitHub CLI")
            and "$RUNNER_TEMP" in run("Bootstrap pinned GitHub CLI")
            and "/usr/local" not in run("Bootstrap pinned GitHub CLI"),
        ),
        (
            "secret write capability is tested and temporary probe is deleted",
            "gh secret set \"$probe_name\"" in run("Preflight GitHub Secret write capability")
            and "gh secret delete \"$probe_name\"" in run("Preflight GitHub Secret write capability")
            and "--env production" in run("Preflight GitHub Secret write capability")
            and "cleanup()" in run("Preflight GitHub Secret write capability")
            and "echo \"GitHub Secret write and cleanup capability: PASS\""
            in run("Preflight GitHub Secret write capability"),
        ),
        (
            "all selected current tokens are dry-run checked before refresh",
            names.index("Preflight GitHub Secret write capability")
            < names.index("Preflight current Threads tokens")
            < names.index("[night_scout] Refresh token")
            and 'all) accounts="night_scout liver_manager beauty_account"' in run(
                "Preflight current Threads tokens"
            )
            and 'python3 scripts/refresh_threads_token.py --account-id "$account" --dry-run'
            in run("Preflight current Threads tokens"),
        ),
        (
            "secret updates read the shared runtime token store",
            all(
                f'TOKEN_FILE="$THREADS_TOKEN_STORE_DIR/{account}.json"' in run(
                    f"[{account}] Update GitHub Secret"
                )
                and "--env production" in run(f"[{account}] Update GitHub Secret")
                and f'.account_id == "{account}"' in run(f"[{account}] Update GitHub Secret")
                and "stat -c '%a' \"$TOKEN_FILE\"" in run(f"[{account}] Update GitHub Secret")
                and "gh secret list" in run(f"[{account}] Update GitHub Secret")
                for account in ("night_scout", "liver_manager", "beauty_account")
            )
            and 'TOKEN_FILE="data/threads_tokens/' not in WORKFLOW.read_text(encoding="utf-8"),
        ),
        (
            "each refresh happens before its matching GitHub Secret update",
            all(
                names.index(f"[{account}] Refresh token")
                < names.index(f"[{account}] Update GitHub Secret")
                for account in ("night_scout", "liver_manager", "beauty_account")
            ),
        ),
        (
            "workflow does not add posting operations or print token values",
            "threads_publisher" not in WORKFLOW.read_text(encoding="utf-8")
            and "public_post" not in WORKFLOW.read_text(encoding="utf-8")
            and "cat \"$TOKEN_FILE\"" not in WORKFLOW.read_text(encoding="utf-8"),
        ),
    ]
)

failed = [name for name, passed in checks if not passed]
for name, passed in checks:
    print(f"{'PASS' if passed else 'FAIL'}: {name}")
print(f"PASS: {len(checks) - len(failed)}/{len(checks)}")
raise SystemExit(1 if failed else 0)
