#!/usr/bin/env python3

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

path = ROOT / "scripts" / "run_direct_media_preparation_loop.py"
spec = importlib.util.spec_from_file_location("direct_media_preparation_loop", path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

calls = []

def runner(command, *, env=None):
    calls.append((list(command), env))
    return subprocess.CompletedProcess(
        command,
        0,
        stdout='{"status":"NO_READY_MEDIA"}\n',
        stderr="",
    )

result = module.execute(
    "night_scout",
    "ns_1800_direct_media",
    1,
    runner=runner,
)

assert calls
ingest = calls[0][0]
assert "scripts/ingest_direct_reference_media_reliable.py" in ingest
index = ingest.index("--max-assets")
assert ingest[index + 1] == "10"
assert "--apply" in ingest
assert "--confirm-ingest" in ingest
assert result["status"] == "NO_ELIGIBLE_MEDIA"

print("[OK] preparation loop preserves complete parent bundles up to cap 10")
