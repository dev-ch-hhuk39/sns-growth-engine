#!/usr/bin/env python3
from required_source_url_checks import assert_required_x_manual_only, run_checks


if __name__ == "__main__":
    raise SystemExit(run_checks([
        ("required X sources manual/reference only", assert_required_x_manual_only),
    ]))
