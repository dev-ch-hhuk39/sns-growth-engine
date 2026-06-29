#!/usr/bin/env python3
from required_source_url_checks import assert_required_present, run_checks


if __name__ == "__main__":
    raise SystemExit(run_checks([
        ("required source URLs present", assert_required_present),
    ]))
