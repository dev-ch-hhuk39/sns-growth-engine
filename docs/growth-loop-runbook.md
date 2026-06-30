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

## Real Data Collection Dry-Run (2026-06-30)

`run_growth_loop.py` can now pass real public collection outputs into the existing scoring / idea planning functions without writing Sheets or posting.

```bash
python3 scripts/run_growth_loop.py --dry-run --account-id all \
  --metric-post-url "https://www.threads.com/@ran.liver_pro/post/DaMbCLQiXLs" \
  --metric-post-url "https://www.threads.com/@kyaba_consul_mizu/post/DaNToTqgQ7i" \
  --source-url "https://www.threads.com/@ran.liver_pro/post/DaMbCLQiXLs" \
  --source-url "https://www.threads.com/@kyaba_consul_mizu/post/DaNToTqgQ7i" \
  --fetch-real
```

Expected behavior:

- Threads metrics collection returns `UNAVAILABLE` when public HTML does not expose trusted counts. Unknown values stay `null`; confirmed zero is never invented.
- Threads source collection can produce `source_account_posts`-shaped rows from public OG metadata, with `can_reuse_media=false`.
- `real_collection_pipeline` reports source posts, score count, and `WAITING_REVIEW` candidate count.
- AUTOPOST remains off. No real post, media download, cut, upload, or X action is performed.

Use `--use-sheets` only when intentionally reading existing Sheets state. Do not bulk-enable `fetch_enabled=true`; use `--source-url` or a small reviewed set first.
