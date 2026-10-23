# SNS Growth Engine evergreen bank failure receipts

The 2026-10-23 02:04 JST AUTO_READY scheduled run on public main
26d7491f failed: night_scout delivery coverage was 2/3; liver_manager
and beauty_account failed emergency evergreen-bank top-up. The public
receipts contained no usable shortage count or safe failure class.

This patch makes existing bank summaries report only:
- account is the validated workflow argument, never a field copied from drafts;
- usable/minimum are validated bounded integer counts, not queue data;
- cause is a hardcoded finite internal classification; unknown strings
  become UNCLASSIFIED rather than printing service-provider responses;
- when the command produces invalid JSON, classify its private stderr
  using the existing safe classifier while keeping raw stderr and drafts
  in temporary private files.

Any shortfall, wrong account, invalid report, failure to prove no posting
or corrupt counts remains nonzero. This is a diagnostic improvement and
**not** a relaxation of approval, final-post validation, paid AI budgets,
quality gates, per-account isolation or provider error handling.

No additional scheduled runs or paid provider calls are introduced. Private
stdout/stderr are deleted via EXIT trap; public logs are still allowlisted.
The missing validated candidates must be addressed based on the next
classified scheduled failure or a bounded audited candidate review,
not by bypassing the final validator or automatically posting drafts.
