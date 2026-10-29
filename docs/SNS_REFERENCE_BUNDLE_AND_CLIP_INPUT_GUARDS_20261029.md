# Validate source bundles, persisted parents and clip evidence

The normalized source-post validator now rejects children whose canonical post
URL differs from their parent, empty or duplicate child identities, non-integer
or negative media indices, and tuples that are not strictly increasing.
Boolean indices are rejected even though Python treats bool as an int subclass.
Original indices may have gaps: the real X metadata adapter can omit an unsafe
media URL while preserving positions such as `[0, 2]`. Validation never sorts,
renumbers or silently removes a child.

The real persistence path rejects an invalid bundle before appending a parent
or its media. It also checks existing and same-batch parent bindings: a
canonical URL, parent ID, source or target account mismatch cannot skip the
parent and then append orphan children. All existing ambiguous bindings are
retained for validation, rather than allowing the last row to hide conflicts.
Missing stored ownership evidence fails closed. Exact existing-parent repeats,
missing-child additions and the existing volatile Threads URL refresh remain
supported; no child is reparented and no rights are inferred. This does not
redesign the source-scoped IDs or migrate stored data.

Clip eligibility now parses evidence flags explicitly. Boolean true, existing
true/1/yes string forms and integer 1 from Sheets numericising are supported.
False, unknown, missing and unsupported values cannot confirm source
understanding or clip suitability. Scores must be finite: NaN, infinity and
overflowing conversions cannot pass the existing minimum of 85. The actual
candidate selector falls back only for absent, None or empty score fields.
Explicit zero or false standalone/confidence values cannot be replaced by a
higher legacy ranking score. Genuinely missing fields on legacy READY rows
remain supported. No new score ceiling or route weights are introduced.

Threads profile metadata now carries the provider-supplied author through the
actual collection CLI into the normalized row and parent. The previous missing
field caused a KeyError before persistence. An explicitly missing author stays
missing; the registered profile cannot stand in for the actual post author.
Discovery remains non-browser, and this change does not enable physical media.

The actual candidate selector checks permission and rights independently.
Valid understanding evidence cannot authorize download, transformation, upload,
reposting or publication. Account isolation, permission/provenance checks,
review boundaries and publisher controls remain in place.

Offline regressions cover both managed accounts, valid X mixed-media gaps and
YouTube, actual X adapter omission behavior, actual persistence collisions and
zero-append refusal, Sheets flag types, finite/nonfinite and zero scores,
legacy fallback, WAITING_REVIEW isolation, actual caller rights denial, and
actual Threads profile CLI composition without writes. Focused suites pass
22 normalized/persistence cases, 11 router/caller cases and 6 Threads collector
cases, with adjacent regressions and independent review. Full Mac validation
passes 1,101/1,101 repository scripts, 619/619 workflow safety checks, fatal Ruff,
compile, diff and secret scans. Existing eight external and three optional
exclusions remain unchanged. Validation is recorded in the handoff. These tests are not production Golden evidence or
media-reuse authorization.
