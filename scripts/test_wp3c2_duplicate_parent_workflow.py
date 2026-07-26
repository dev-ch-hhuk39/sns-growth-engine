import unittest
import os
import yaml
import json

class TestWP3C2DuplicateWorkflow(unittest.TestCase):
    def test_workflow_contracts(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".github", "workflows", "wp3c2-duplicate-parent-inspection.yml")
        with open(path, "r") as f:
            w = yaml.safe_load(f)
            
        on_val = w.get("on") if "on" in w else w.get(True)
        self.assertIn("workflow_dispatch", on_val)
        self.assertNotIn("schedule", on_val)
        self.assertEqual(w["permissions"]["contents"], "read")
        
        job = w["jobs"]["inspect_duplicate"]
        self.assertEqual(job["environment"], "production")
        
        env = w["env"]
        self.assertEqual(str(env["PUBLISH_ENABLED"]).lower(), "false")
        self.assertEqual(str(env["ALLOW_REAL_THREADS_POST"]).lower(), "false")
        
        step_run = ""
        for step in job["steps"]:
            if "run" in step and "inspect_wp3c_duplicate_parent.py" in step["run"]:
                step_run = step["run"]
                
        self.assertIn("WP3C2_SAFE_DUPLICATE_INSPECTION_JSON=", step_run)
        
        self.assertNotIn("actions/upload-artifact", json.dumps(job))

if __name__ == '__main__':
    unittest.main()
