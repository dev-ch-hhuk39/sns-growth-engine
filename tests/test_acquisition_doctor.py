from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "acquisition_doctor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("acquisition_doctor", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_doctor_is_side_effect_free_and_never_reports_secret_values(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module.shutil, "which", lambda name: f"/usr/bin/{name}" if name == "python3" else None)
    report = module.build_report()
    serialized = json.dumps(report)
    assert report["side_effects"] is False
    assert report["secret_values_read"] is False
    assert "auth_token=" not in serialized
    assert "sessionid=" not in serialized
    assert "msToken=" not in serialized


def test_missing_optional_backends_do_not_make_doctor_fatal(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/python3" if name == "python3" else None)
    report = module.build_report()
    optional = {row["backend_id"]: row for row in report["backends"]}
    assert optional["twscrape"]["tool_status"] == "NOT_INSTALLED"
    assert "twscrape" not in report["primary_missing"]
