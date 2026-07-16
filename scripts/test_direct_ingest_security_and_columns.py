#!/usr/bin/env python3
import socket
import tempfile
from pathlib import Path
from unittest.mock import patch

import ingest_direct_reference_media as ingest

public_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("142.250.1.1", 443))]
private_dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
with patch.object(ingest.socket, "getaddrinfo", return_value=public_dns):
    public_origin = ingest.safe_https_url("https://www.youtube.com/watch?v=abc")
    public_stream = ingest.safe_https_url("https://rr1.googlevideo.com/videoplayback", stream_url=True)
with patch.object(ingest.socket, "getaddrinfo", return_value=private_dns):
    private_blocked = not ingest.safe_https_url("https://www.youtube.com/watch?v=abc")

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    mp4 = root / "sample.mp4"
    png = root / "sample.png"
    bad = root / "bad.bin"
    mp4.write_bytes(b"\x00\x00\x00\x18ftypisom")
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    bad.write_bytes(b"not-media")
    magic_ok = ingest.magic_mime(mp4) == "video/mp4" and ingest.magic_mime(png) == "image/png" and ingest.magic_mime(bad) == ""

checks = [
    ("https approved origin", public_origin),
    ("resolved provider stream approved", public_stream),
    ("private resolved IP blocked", private_blocked),
    ("unknown host blocked", not ingest.safe_https_url("https://example.invalid/video")),
    ("http blocked", not ingest.safe_https_url("http://www.youtube.com/watch?v=abc")),
    ("magic mime enforced", magic_ok),
    ("AA and AB columns supported", ingest.col_letter(27) == "AA" and ingest.col_letter(28) == "AB"),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
