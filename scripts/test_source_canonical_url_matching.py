#!/usr/bin/env python3
from required_source_url_checks import assert_canonical_matching, run_checks


if __name__ == "__main__":
    raise SystemExit(run_checks([
        ("required source canonical URL matching", assert_canonical_matching),
    ]))
