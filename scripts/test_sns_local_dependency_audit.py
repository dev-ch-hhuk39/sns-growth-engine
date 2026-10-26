#!/usr/bin/env python3
"""Offline security audit tests: fail closed, redact private provider content."""
import unittest
from unittest.mock import patch
import sns_local_dependency_audit as scanner

class OSVDependencyAuditTests(unittest.TestCase):
    def test_vulnerable_and_private_fields(self):
        packages=[("example-lib","1.0"),("safe-lib","2.0")]
        response={"results":[{"vulns":[{"id":"GHSA-example","summary":"PRIVATE_TEXT"}]},{}]}
        result=scanner.evaluate(packages,response)
        self.assertEqual(result["status"],"VULNERABILITIES_FOUND")
        self.assertEqual(result["vulnerable_packages"],[{"package":"example-lib","advisories":1}])
        self.assertNotIn("PRIVATE_TEXT",str(result))
        self.assertFalse(result["packages_changed"])

    def test_clean(self):
        self.assertEqual(scanner.evaluate([("abc","1")],{"results":[{}]})["status"],"PASS")

    def test_invalid_input_never_passes(self):
        for result in ({"results":[]},{"results":[None]},{"results":[{"vulns":"bad"}]}):
            with self.subTest(result=result),self.assertRaises(ValueError):
                scanner.evaluate([("example","1")],result)

    def test_provider_errors_fail_closed(self):
        with patch.object(scanner,"installed_packages",return_value=[("example","1")]),patch.object(
            scanner,"fetch",side_effect=RuntimeError("PRIVATE_TOKEN")
        ):
            self.assertEqual(scanner.main(),1)

if __name__=="__main__":
    unittest.main()
