# Phase 5B-6AA/AB — X network stop and offline Sheets writer cutover plan

Date: 2026-10-13 JST. Mac-local continuation after commit 0afd6a9.
This is source/test work only: not production cutover, deployment, or approval.

## Confirmed issues

The current GOAL.md and AGENTS.md exclude outbound X posting, but
historical XPublisher, factory selection, and publish_queue CLI remained
operable if environment and OAuth flags were all enabled. This conflicted
with the current scope. The frozen legacy Sheets mutation inventory
also lacked a prioritized migration work plan.

## Phase 6AA: X posting blocked at four independent boundaries

1. Source-owned active_platform_policy permits only Threads for real
   outbound posting. No environment value can enable X.
2. Legacy publish_queue CLI refuses the real X route before opening
   Sheets, publisher or credentials.
3. Publisher factory returns a non-posting safety-stop publisher for X.
4. Both XPublisher.publish(dry_run=False) and the low-level
   _publish_with_oauth1 HTTP function independently fail closed.

Historical adapter source, error classifier and dry-run validation remain
available for compatibility; production X publication and real HTTP were
not exercised. X remains available as a separately authorized reference
research source: this does not broaden its rights or media permissions.

Historical mocked-success tests have been changed to verify that all
legacy environment switches cannot cause real network calls, external
post IDs, posted_results writes or operational queue status changes.
Threads media authorization and account boundaries are unchanged.

## Phase 6AB: legacy writer classification (read-only)

scripts/plan_legacy_writer_cutover.py verifies the frozen 6H AST mutation
baseline against the current repository and produces a deterministic
workstream classification:

- P0_PUBLISH_AND_RESULT: publisher and posted-result recovery
- P0_QUEUE_AND_APPROVAL: queue creation, review, READY, scheduling
- P1_SCHEMA_AND_RECOVERY: schema repair and source identity recovery
- P1_METRICS_AND_FEEDBACK: metric jobs, reservations, strategy writes
- P2_UPSTREAM_AND_OTHER: all remaining observed writer routes

Every observed route remains NOT_MIGRATED and cutover_authorized=false.
Unknown/unclassified paths stay in P2, never disappear. Counts and paths
come from actual AST scan and the frozen baseline, not guessed statuses.
The classification is not an exhaustive runtime inventory: external
services, dynamic calls and cron still require independent inspection.
Even an empty mutation inventory cannot activate cutover.

Example safe local command:

    python3 scripts/plan_legacy_writer_cutover.py \
      --output /tmp/sns-legacy-writer-cutover-plan.json

The command exits 2 intentionally and refuses report destinations
inside the Git checkout. No Google, SQLite or SNS operation is performed.
It cannot approve migration or activate disabled publisher sinks.

## Remaining actual operations (not completed here)

- Choose authoritative queue and per-account cutover order with Owner/Ops.
- Verify provider service identity, ACL, MFA and egress destinations.
- Discover non-repo writers and disable/serialize them per reviewed family.
- Back up and restore actual data; reconcile historical unknown results.
- Migrate each writer group behind an operational transaction/CAS/lease,
  with real readback; never retry unknown posting outcomes blindly.
- Run rights/identity checks immediately before live publishing, canaries
  only with explicit operator authorization, and real 24h/72h/168h metrics.
- Release and rollback ownership stays in the separate common VPS chat.

## Tests

New offline unit suite: scripts/test_x_scope_and_legacy_cutover_plan.py.
Existing X Phase3D, 6A media interlock, frozen 6H inventory and local
focused/full quality gate also validate the changed behavior.
No Actions CI, Codex, public GitHub push, VPS mutation, real Sheet write,
real X/Threads post or paid API usage took place in this batch.

## Final local verification (2026-10-13 JST)

- Frozen AST inventory after preceding commits: **68 Python files, 165
  AST mutation call sites**, all NOT_MIGRATED; workstream counts P0=71,
  P1=24, P2=70. This differs from the historical first 6H capture (66/163)
  and is based on the actual currently frozen inventory, not estimated.
- New adversarial X/product policy and cutover-planner unit tests: 8 PASS.
- Legacy Phase3C: 34 PASS; Phase3D: 34 PASS, now testing the current
  X-disabled contract instead of historic mocked live X success.
- Final full Mac-local offline repository regression: **987/987 scripts PASS**.
  Static workflow, Ruff fatal, Python compile, Git diff and local gitleaks:
  all PASS. External credentialed probes and optional tools are excluded
  under the repository's existing QA policy.
- The initial full run found one Phase3C factory expectation for the old
  XPublisher route (986/987). The fixture was updated to require the stronger
  current owner policy; both focused and final full suite then passed.
  No production security guard was weakened to make a test pass.
- Local test report: /tmp/sns-20261013-6aa-ab-full-final.json, with
  repository_result.json under /tmp/sns-20261013-6aa-ab-full-final-logs/.
  These ephemeral files are not production evidence and were not committed.
