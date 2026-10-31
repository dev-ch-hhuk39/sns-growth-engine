# Mac owner media capture

The owner will keep the VPS at its current memory size and handle disk cleanup
in another chat. Heavy media work can use the authorized 32GiB Mac. Existing
VPS media resource floors remain enforced; this source does not start that
heavy VPS entrypoint, install schedules or disable hosted fallbacks.

## Connected stages

`capture_owner_media_on_mac.py` binds one exact registered source, account and
native X/YouTube post. Default execution is an offline plan. An explicitly
confirmed run uses the existing owner-approved SSH alias to execute the tested
read-only authority program from a pinned Git object on the VPS. The helper
uses the exact existing immutable runtime, shared deployment/Sheets locks and
its protected connection configuration. Only the source-specific download
verdict and fixed binding fields return to the Mac. No Sheets/API/publishing
credentials are copied to the Mac, and no credential files are auto-discovered.

Before downloading, the actual extracted author/native-post metadata must
match the registered source. The authority reads the latest ledger immediately
before the download and again after capture. Revocation, scope mismatch,
unknown identity, unavailable reads or release drift prevent acceptance.
Retweets, quotes and third-party author mismatches retain existing denials.
Threads/TikTok new physical capture remains deferred.

The Mac requires at least 4GiB total and 1.5GiB available memory, pinned yt-dlp
2026.7.4 and installed FFmpeg/ffprobe. Available memory counts free plus inactive
pages, consistent with the primary psutil OS X implementation:
[psutil OS X memory implementation](https://github.com/giampaolo/psutil/blob/master/psutil/arch/osx/mem.c). This is a
memory-statistic correction, not a change to the existing thresholds.

The download worker receives only minimal execution/SSH-agent locator state;
provider and publishing credentials are scrubbed. Browser/cookie/PO-token
plugins are disabled. A separate process group has a 15-minute deadline and
is terminated on timeout. No platform-authentication workaround is added.

## Operation

Offline plan, with an already registered exact source:

```bash
python3 scripts/capture_owner_media_on_mac.py \
  --account-id liver_manager \
  --source-id src_lm_x_cand_001 \
  --url https://x.com/meg_lsm/status/1738178096464064991
```

Only after the specific download is authorized, using tested clean source and
the independently inspected current runtime revision:

```bash
python3 scripts/capture_owner_media_on_mac.py \
  --account-id liver_manager \
  --source-id src_lm_x_cand_001 \
  --url https://x.com/meg_lsm/status/1738178096464064991 \
  --apply --confirm-download \
  --authority-host '<existing-approved-SSH-alias>' \
  --expected-local-revision '<verified-40hex-local-revision>' \
  --expected-runtime-revision '<inspected-40hex-current-runtime>' \
  --workspace /absolute/existing-private-capture-workspace
```

The workspace must already be owned by the executing user, mode 0700, without
linked components. Existing attempts are never overwritten or automatically
retried. A shared private lock serializes capture. Quota counts existing files;
300MiB per completed media, a 3GiB workspace bound, 512 entries and 2GiB free
disk admission prevent unbounded accumulation. No retention deletion is added.
Failures preserve unknown attempts for explicit inspection. The process needs
the Mac awake; this is not a verified 24/7 scheduled-workflow replacement.

## Evidence and remaining acceptance

Accepted RAW bytes, a same-basename extracted `.info.json` and private request/
result records are stored under `workspace/x` or `workspace/youtube`. Every file
is private and actual byte hashes are checked through stable file identities.
These flat directories fit the current physical verifier's input layout.

`LOCAL_RAW_ARTIFACT_CAPTURED` never asserts complete content understanding,
current full media reuse rights, human approval, READY or overall acceptance.
There is no synthetic `.understanding.json`, provider call, Cloudinary upload,
production Sheets mutation, timer change or SNS publication. Real full Gemini
proof, normalized parent/asset identity, current operation-specific rights,
human review/READY reserves, remaining schedules and approved publishing plus
measured observation still require their existing gates. The explicit full
physical verifier remains blocked until those actual inputs exist.

Focused source verification currently passes 26 synthetic boundary/adapter/
download/process tests. They include real private files with mocked provider
transports and probes and do not prove live media or permission. Full source
regression is recorded before delivery. Formal goal status is untouched.
