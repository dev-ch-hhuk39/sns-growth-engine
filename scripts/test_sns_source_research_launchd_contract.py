#!/usr/bin/env python3
"""Source research must be public, bounded and independent of GitHub Actions."""
from pathlib import Path
import plistlib
import unittest

ROOT=Path(__file__).resolve().parents[1]
PLIST=ROOT/"ops/launchd/com.chadult.sns.source-research-preview.plist"
SCRIPT=(ROOT/"scripts/run_local_source_research_preview.sh").read_text()
SRC=(ROOT/"scripts/sns_local_source_research_preview.py").read_text()


class DailySourceResearchContract(unittest.TestCase):
    def test_launchd_daily_and_private_logs(self):
        d=plistlib.loads(PLIST.read_bytes())
        self.assertEqual(d["Label"],"com.chadult.sns.source-research-preview")
        self.assertEqual(d["StartCalendarInterval"],{"Hour":4,"Minute":27})
        self.assertFalse(d["RunAtLoad"])
        self.assertIn("chadult-sns-source-research",d["StandardOutPath"])
        self.assertIn("run_local_source_research_preview.sh",d["ProgramArguments"][1])

    def test_explicit_no_publish_no_pay_no_sheets(self):
        for switch in ("PUBLISH_ENABLED=false","ALLOW_REAL_THREADS_POST=false",
                       "ALLOW_VIDEO_DOWNLOAD=false","ALLOW_CLOUDINARY_UPLOAD=false",
                       "ALLOW_MEDIA_POSTS=false"):
            self.assertIn(switch,SCRIPT)
        self.assertIn("reference_only",SRC)
        self.assertIn("do_not_download",SRC)
        self.assertIn("WAITING_REVIEW",SRC)
        self.assertIn("sheets_writes",SRC)
        self.assertIn("paid_ai",SRC)
        self.assertNotIn("gspread",SRC)
        self.assertNotIn("sheets_client",SRC)


if __name__=="__main__":
    unittest.main()
