# Bind immutable deployment to the inspected current release

The existing deployment transaction accepts optional
`--expected-current-revision <40 lowercase hexadecimal characters>`. Use it
when approval and preflight were based on a particular running revision. The
transaction takes the administrator's global exclusive deployment lock before
checking the live pointer. A deployment that changed `current` while this
invocation waited for that lock cannot be overwritten using the old expectation.

The expected release must be a non-linked directory at the canonical owned
release path, with a regular non-linked release marker. The marker must contain
the exact SHA with one terminal LF, or the legacy bare SHA. Normalizing command
substitution is deliberately avoided: NUL bytes, extra newlines, CRLF, invalid
encoding and trailing data are not valid release identities.

A missing, malformed or duplicate argument fails before any runtime mutation.
A current/marker/path mismatch fails while holding the lock, before resource
preflight, environment creation, cron capture, candidate installation, shared
CLI setup or activation. Diagnostics contain fixed reasons, not marker contents.
No expected revision is inferred from the new candidate or silently updated.

Omitting the option preserves the existing caller contract. The option grants
no deployment or publishing approval, does not validate credentials, and does
not replace backup, capacity, dependency, provider, rollback or publication
gates. Existing 9GiB/8GiB resource floors, posting-OFF handover, scheduler opt-in,
protected settings and retained releases are unchanged.

Offline shell simulations use actual kernel locks to change the current
pointer while a transaction waits. Refusal preserves pointers, files, modes,
inodes, timestamps, environment and cron state, and invokes no candidate child.
Matching standard and legacy markers still permit the existing simulated
promotion and rollback paths. All previous simulation cases remain. Focused
simulation19, shell syntax, compile, fatal Ruff and diff checks pass. Final full Mac quality gate passed 1,101/1,101 repository scripts and
619/619 workflow safety checks, fatal Ruff, compile, diff and history secret
scan; existing exclusions unchanged. Independent review found no required fixes.
These are source tests,
not evidence of a real deployment or production acceptance.
