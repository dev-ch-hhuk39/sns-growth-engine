#!/usr/bin/env python3
"""Offline token lifecycle tests: scopes, authenticity, no secret logs, fail closed."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime,timedelta
from unittest.mock import patch
import unittest

import sns_local_threads_token_renewal as app


class TokenRenewalTests(unittest.TestCase):
    def test_refresher_uses_bearer_not_url(self):
        captured = []
        class Reply:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self,*args):
                return None
            def read(self,n):
                return b'{"access_token":"NEW_PRIVATE_TOKEN","expires_in":5184000}'
        class Opener:
            def open(self,req,timeout):
                captured.append(req)
                return Reply()
        with patch.object(app.urllib.request,"build_opener",return_value=Opener()):
            token,secs=app.refresh_api("OLD_PRIVATE_TOKEN")
        self.assertEqual(token,"NEW_PRIVATE_TOKEN")
        self.assertEqual(secs,5184000)
        self.assertEqual(captured[0].full_url,app.URL)
        self.assertNotIn("PRIVATE_TOKEN",captured[0].full_url)
        self.assertEqual(captured[0].get_header("Authorization"),"Bearer OLD_PRIVATE_TOKEN")

    def test_unknown_or_malformed_fails_closed(self):
        class Reply:
            status = 200
            def __enter__(self):return self
            def __exit__(self,*args):return None
            def read(self,n):return b'{"access_token":"SENSITIVE","expires_in":false}'
        class Opener:
            def open(self,*args,**kwargs):return Reply()
        with patch.object(app.urllib.request,"build_opener",return_value=Opener()):
            with self.assertRaises(app.TokenBlocked):
                app.refresh_api("OLD_PRIVATE")
        with self.assertRaises(app.TokenBlocked):
            app.refresh_api("")

    def test_expiration_and_file_symlink(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(app,"STORE",Path(tmp)):
            a="night_scout"
            self.assertTrue(app.renewal_due(a,datetime.now(app.JST)))
            d={"account_id":a,"expires_at":(datetime.now(app.JST)+timedelta(days=40)).isoformat()}
            (Path(tmp)/(a+".json")).write_text(json.dumps(d))
            self.assertFalse(app.renewal_due(a,datetime.now(app.JST)))
            (Path(tmp)/(a+".json")).unlink()
            (Path(tmp)/(a+".json")).symlink_to(Path(tmp)/"nonexistent")
            with self.assertRaises(app.TokenBlocked):
                app.renewal_due(a,datetime.now(app.JST))

    def test_failed_verification_never_refreshes(self):
        with tempfile.TemporaryDirectory() as tmp:
            c={a:{"access_token":"token"+a,"user_id":str(i+1)}
               for i,a in enumerate(app.ACCOUNTS)}
            env={"BUFFERED_POSTING_ENABLED":"false",**{
                 "THREADS_HANDLE_"+a.upper():"handle"+str(i) for i,a in enumerate(app.ACCOUNTS)}}
            with patch.dict(os.environ,env), patch.object(app,"STORE",Path(tmp)),\
                 patch.object(app,"resolve_credentials",side_effect=lambda a:c[a]),\
                 patch.object(app,"_verify_live_identity",return_value={"status":"CREDENTIAL_BLOCKED"}),\
                 patch.object(app,"refresh_api") as api:
                with self.assertRaises(app.TokenBlocked):
                    app.run(apply=True)
                api.assert_not_called()

    def test_quarantine_prevents_repeated_refresh(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(app,"STORE",Path(tmp)):
            app.quarantine("liver_manager")
            self.assertTrue((Path(tmp)/".refresh-unknown-liver_manager").exists())
            app.quarantine("liver_manager")
            self.assertNotIn("PRIVATE", (Path(tmp)/".refresh-unknown-liver_manager").read_text())


if __name__ == "__main__":
    unittest.main()
