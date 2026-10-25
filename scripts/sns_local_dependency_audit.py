#!/usr/bin/env python3
"""Read-only OSV vulnerability audit of installed Python dependencies on SNS VPS."""
from __future__ import annotations
import json
import re
import sys
from importlib import metadata
from urllib import request

OSV_QUERY_BATCH = "https://api.osv.dev/v1/querybatch"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9+_.!-]{0,119}\Z")

def installed_packages() -> list[tuple[str, str]]:
    found = {}
    for dist in metadata.distributions():
        name = str(dist.metadata.get("Name") or "")
        version = str(dist.version or "")
        if NAME.fullmatch(name) and VERSION.fullmatch(version):
            found[re.sub(r"[-_.]+", "-", name).lower()] = (name, version)
    result = sorted(found.values(), key=lambda row: row[0].lower())
    if not 1 <= len(result) <= 300:
        raise ValueError("INVALID_RUNTIME_INVENTORY")
    return result

def fetch(packages: list[tuple[str, str]]) -> dict:
    # Sends only public package names and versions; never paths or credentials.
    body = json.dumps({"queries": [
        {"package": {"name": name, "ecosystem": "PyPI"}, "version": version}
        for name, version in packages
    ]}).encode("utf-8")
    req = request.Request(OSV_QUERY_BATCH, data=body, method="POST",
                          headers={"Content-Type": "application/json",
                                   "User-Agent": "Chadult-SNS-Security-Audit/1"})
    with request.urlopen(req, timeout=25) as response:
        if response.status != 200:
            raise ValueError("OSV_HTTP_INVALID")
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("OSV_RESPONSE_TOO_LARGE")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("OSV_REPORT_INVALID")
    return data

def evaluate(packages: list[tuple[str, str]], response: dict) -> dict:
    results = response["results"]
    if not isinstance(results, list) or len(results) != len(packages):
        raise ValueError("OSV_REPORT_SCOPE_MISMATCH")
    affected = []
    for (name, _), row in zip(packages, results):
        if not isinstance(row, dict):
            raise ValueError("OSV_REPORT_ROW_INVALID")
        vulns = row.get("vulns", [])
        if not isinstance(vulns, list) or len(vulns) > 300:
            raise ValueError("OSV_REPORT_VULNS_INVALID")
        if vulns:
            affected.append({"package": name, "advisories": len(vulns)})
    return {
        "status": "VULNERABILITIES_FOUND" if affected else "PASS",
        "packages_checked": len(packages), "ecosystem": "PyPI",
        "vulnerable_packages": affected, "packages_changed": False,
        "data_deleted": False
    }

def main() -> int:
    try:
        packages = installed_packages()
        result = evaluate(packages, fetch(packages))
    except Exception:
        result = {"status": "BLOCKED_UNVERIFIED", "packages_changed": False,
                  "data_deleted": False}
    print("SNS_OSV_DEPENDENCY_AUDIT=" + json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["status"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
