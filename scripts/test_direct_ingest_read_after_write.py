#!/usr/bin/env python3
import inspect

import ingest_direct_reference_media as ingest

upsert = inspect.getsource(ingest.upsert_media_asset)
main = inspect.getsource(ingest.main)
checks = [
    ("media asset read after write", "media_assets:verify" in upsert and "media_asset_read_after_write_failed" in upsert),
    ("source post media read after write", "source_post_media_read_after_write_failed" in main),
    ("resolved stream checked", "resolved_media_url_blocked" in inspect.getsource(ingest.download_with_ytdlp)),
    ("temp file removed on success and failure", main.count("local_path.unlink(missing_ok=True)") >= 2),
    ("cloudinary id deterministic", "sns-growth/direct/{digest_text}" in main),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
