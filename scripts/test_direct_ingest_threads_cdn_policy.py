#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
import ingest_direct_reference_media as ingest

ingest.socket.getaddrinfo = lambda *args, **kwargs: [(None, None, None, None, ("8.8.8.8", 443))]
checks = {"threads CDN is permitted": ingest.safe_https_url("https://scontent-nrt1-1.cdninstagram.com/x.jpg", stream_url=True),
          "private IP denied": not ingest.safe_https_url("https://127.0.0.1/x.jpg", stream_url=True),
          "plain http denied": not ingest.safe_https_url("http://scontent-nrt1-1.cdninstagram.com/x.jpg", stream_url=True)}
for name, ok in checks.items(): print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
