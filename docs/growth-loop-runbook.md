# Growth Loop Runbook

## Scope

`scripts/run_growth_loop.py` orchestrates the safe v2 planning loop:

1. collect Threads metrics snapshots
2. generate PDCA candidates
3. plan source collection
4. plan media queue generation
5. run AUTO_READY dry-run

## Default Behavior

- Default is dry-run / `PLAN_ONLY`.
- AUTOPOST is always off in this runner.
- Real posting is not executed.
- X posting/fetch is not executed.
- beauty_account is blocked.
- media download/cut/upload is not executed.
- The runner reports `kill_switch_respected=true`; production automation must still check `config/auto_approval_rules.json`.

## Command

```bash
python3 scripts/run_growth_loop.py --dry-run --account-id all
```

`--apply` is blocked unless `--confirm-run` is also present, and should not be used until metrics, source collection, and AUTO_READY policies are reviewed.
