# SNS Growth Engine READY queue schema repair — 2026-10-21

## Verified source evidence

The production Google Sheets spreadsheet SNS自動投稿ツール has a 200-column 投稿キュー (queue) header with the persisted field content_type (column BY) but NO post_type column. The publication_review tab is a separate tab which does use the field post_type. This agrees with src/sheets_client.py TAB_DEFINITIONS. The src/sheets_record_reader.py read_records_safely returns the actual worksheet get_all_records dictionary without adding an alias.

Previously scripts/maintain_text_ready_inventory.py checks row.get(post_type) when deciding if a READY row is text-publishable. This is empty for real persisted queue rows, even when content_type has an explicitly allowed text type. The generated READY rejection diagnostics repeated the mismatch.

Read-only sample aggregates on 2026-10-21 JST show historical READY queue rows per account: night_scout=179; liver_manager=144; beauty_account=153. For the requested business dates 2026-10-21 through 2026-10-28, READY rows number 0 / 0 / 14 respectively. READY status or scheduled date alone never guarantees runtime publishability.

## Safe repair

Use actual persisted content_type when present. Preserve backward compatibility for strictly synthetic or legacy in-memory rows with post_type only. If both fields exist and differ, fail closed rather than reclassifying a media row or weakening safety. Use the same helper for both exact-slot READY inventory and sanitized rejection diagnostics.

DO NOT change exact account, slot ID, business date, validator PASS, media exclusion, final post text check, source/AI approval, or process_one(... dry_run=True, confirm_real_post=False). Do not modify queue data, owner decisions, pricing, tokens, or actual SNS posting.

The synthetic regression tests must verify persisted field compatibility, unapproved rows rejected, media route rejected, account/date/slot mismatch rejected, AI gate rejected and runtime dry-run rejected. Merge only after all PR CI and safety checks pass.

This repair fixes the known field mismatch only. It does not magically create READY on night_scout/liver_manager future slots, correct AI budget exhaustion, or prove the final live no-post READY SLO. See Issue #441 and owner completion Issue #439. Avoid another approximately 700MiB immutable deployment just for diagnostics if existing storage and rollback conditions make a bundled deploy safer.
