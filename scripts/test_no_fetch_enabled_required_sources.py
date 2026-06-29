#!/usr/bin/env python3
from required_source_url_checks import assert_no_fetch_enabled_required_sources, run_checks


if __name__ == "__main__":
    raise SystemExit(run_checks([
        ("required sources never fetch/download/cut/upload", assert_no_fetch_enabled_required_sources),
    ]))
