# Scoped runtime reads after metrics aftercare

The optional `--with-health-check` stage in
`scripts/run_buffered_metrics_aftercare_host.sh` checks the existing queue,
posted-results, metrics-job and metric-snapshot tables for one selected
`night_scout` or `liver_manager` account. It runs last under the same deployment,
Sheets and account locks and uses the same verified immutable release. Its
script must be a regular, non-linked file in that release. Default behavior and
existing independent write approvals are unchanged. Beauty is rejected for this
new option before runtime configuration is loaded.

The stage invokes:

```sh
python scripts/check_autonomous_health.py --account-id night_scout \
  --dry-run --use-sheets --strict-runtime
```

This strict mode requires both read-only flags and one supported account before
configuration or provider access. It directly constructs a real read-only
Sheets client, never sets up or repairs a tab, rejects mocks, and validates
required headers, row shapes and unambiguous account-bound identities. Optional
attribution, Bank and media tables are not prerequisites. A missing table,
failed read, invalid schema or ambiguous account identity returns `BLOCKED` and
a nonzero exit with a fixed reason. Dependencies' diagnostic text is suppressed;
the result contains only selected-account counts and fixed status fields.

`READ_OK` proves only those scoped read contracts. Empty tables can correctly
return zero rows; this does not prove available READY stock, completed metrics,
publication safety, hosted-workflow equivalence or production acceptance. The
legacy advisory health mode retains its existing behavior. The host's offline
plan connects to no provider; confirmed preview/apply modes run the check once,
with child diagnostics kept private. Any failed stage stops without an automatic
retry or a final successful aftercare receipt. Previously applied metrics are
not rolled back or resent because a subsequent read fails.

Offline verification covers real shell invocation, continuous locks and pinned
release selection, both selected accounts, no configuration access in pure
plans, unsupported-account denial, absent/linked scripts, child-failure
propagation, private diagnostics, real-client construction at the mocked network
boundary, partial read failure, invalid headers/rows and identity ambiguity.
These tests are source evidence only. No live health check, Sheets write,
provider generation, timer change, token update or publication is performed by
this source change. Final full Mac quality gate passed 1,101/1,101 repository scripts and 619/619 workflow safety checks, fatal Ruff, compile, diff and history secret scan. The existing eight external and three optional exclusions are unchanged. Focused strict health15, shell integration12 and host policy16 tests passed, with independent review finding no required fixes.

## Subsequent real read-only verification

The installed CLI was subsequently invoked once per account on immutable runtime
`1d4b2070cf0f61812bdf75a15ec8d44f54799723`, with deployment, shared Sheets and
selected-account locks held for each invocation. Night and Liver both returned
`READ_OK`, `strict_runtime_reads_verified` and exit0. All four existing core
tables passed actual provider reads, required-header validation and scoped
account/identity consistency checks.

Only fixed metadata and counts were returned; no row text or authentication
material was disclosed. Time and memory were bounded. These invocations made no
Sheets mutation, SNS post, Threads token update, generation, media operation or
timer change. They exercised the installed strict CLI directly, without running
the metrics preview/apply or feedback stages of the complete aftercare wrapper.

This is real read-contract evidence, not READY stock, metric completion,
feedback/PDCA success, rights, real reference/media Golden, schedule migration,
hosted-workflow equivalence or overall production acceptance. Detailed receipts
remain private. The formal goal status was not edited.
