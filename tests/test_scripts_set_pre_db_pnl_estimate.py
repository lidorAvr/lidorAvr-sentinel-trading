"""
Test the CLI helper that manages `pre_db_realized_pnl_estimate` in
sentinel_config.json.

Pin behaviour:
  - --show on a file without the field: reports "(unset)".
  - <value>: sets the field, atomic write.
  - <value>: preserves other keys + indentation.
  - --clear: removes the field.
  - Missing file: exit code 1, error to stderr.
  - Non-numeric value: exit code 2.
  - SENTINEL_CONFIG_PATH env var overrides the default path.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "set_pre_db_pnl_estimate.py"


def _run(args, *, cfg_path=None, cwd=None):
    """Invoke the helper script and return (returncode, stdout, stderr)."""
    env = os.environ.copy()
    if cfg_path is not None:
        env["SENTINEL_CONFIG_PATH"] = str(cfg_path)
    res = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
        cwd=str(cwd) if cwd else None,
    )
    return res.returncode, res.stdout, res.stderr


@pytest.fixture
def tmp_cfg(tmp_path):
    """A fresh sentinel_config.json fixture."""
    cfg = tmp_path / "sentinel_config.json"
    cfg.write_text(json.dumps({
        "total_deposited": 7500.0,
        "risk_pct_input": 0.5,
    }, indent=2) + "\n", encoding="utf-8")
    return cfg


class TestShow:
    def test_show_on_clean_config_reports_unset(self, tmp_cfg):
        rc, out, err = _run(["--show"], cfg_path=tmp_cfg)
        assert rc == 0
        assert "(unset" in out
        # Reference fields surface for the operator.
        assert "total_deposited" in out

    def test_show_on_set_config_reports_value(self, tmp_cfg):
        data = json.loads(tmp_cfg.read_text())
        data["pre_db_realized_pnl_estimate"] = 495.67
        tmp_cfg.write_text(json.dumps(data, indent=2))
        rc, out, err = _run(["--show"], cfg_path=tmp_cfg)
        assert rc == 0
        assert "495.67" in out


class TestSet:
    def test_set_writes_value(self, tmp_cfg):
        rc, out, err = _run(["495.67"], cfg_path=tmp_cfg)
        assert rc == 0
        assert "After:" in out and "495.67" in out
        data = json.loads(tmp_cfg.read_text())
        assert data["pre_db_realized_pnl_estimate"] == 495.67

    def test_set_negative_value(self, tmp_cfg):
        # Pre-deploy LOSSES — signed negative.
        rc, out, err = _run(["-200.5"], cfg_path=tmp_cfg)
        assert rc == 0
        data = json.loads(tmp_cfg.read_text())
        assert data["pre_db_realized_pnl_estimate"] == -200.5

    def test_set_preserves_other_keys(self, tmp_cfg):
        _run(["495.67"], cfg_path=tmp_cfg)
        data = json.loads(tmp_cfg.read_text())
        # Existing keys still present.
        assert data["total_deposited"] == 7500.0
        assert data["risk_pct_input"] == 0.5

    def test_set_overwrites_existing(self, tmp_cfg):
        _run(["100.0"], cfg_path=tmp_cfg)
        rc, out, err = _run(["250.0"], cfg_path=tmp_cfg)
        assert rc == 0
        # before/after both surface in the diff.
        assert "100.00" in out  # before
        assert "250.00" in out  # after
        data = json.loads(tmp_cfg.read_text())
        assert data["pre_db_realized_pnl_estimate"] == 250.0

    def test_set_invalid_value_exits_with_code_2(self, tmp_cfg):
        rc, out, err = _run(["not_a_number"], cfg_path=tmp_cfg)
        assert rc == 2
        assert "Invalid value" in err

    def test_set_rounds_to_2_decimal_places(self, tmp_cfg):
        _run(["495.6789"], cfg_path=tmp_cfg)
        data = json.loads(tmp_cfg.read_text())
        assert data["pre_db_realized_pnl_estimate"] == 495.68


class TestClear:
    def test_clear_removes_field(self, tmp_cfg):
        _run(["495.67"], cfg_path=tmp_cfg)
        rc, out, err = _run(["--clear"], cfg_path=tmp_cfg)
        assert rc == 0
        data = json.loads(tmp_cfg.read_text())
        assert "pre_db_realized_pnl_estimate" not in data

    def test_clear_when_absent_is_a_no_op(self, tmp_cfg):
        rc, out, err = _run(["--clear"], cfg_path=tmp_cfg)
        assert rc == 0
        assert "already absent" in out or "nothing to clear" in out


class TestErrorPaths:
    def test_missing_file_exits_with_code_1(self, tmp_path):
        non_existent = tmp_path / "missing.json"
        rc, out, err = _run(["--show"], cfg_path=non_existent)
        assert rc == 1
        assert "not found" in err

    def test_malformed_json_exits_with_code_1(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json")
        rc, out, err = _run(["--show"], cfg_path=bad)
        assert rc == 1
        assert "Malformed" in err

    def test_no_arguments_exits_nonzero(self, tmp_cfg):
        # argparse requires one of --show / --clear / <value>.
        rc, out, err = _run([], cfg_path=tmp_cfg)
        assert rc != 0


class TestAtomicWrite:
    def test_temp_files_cleaned_up(self, tmp_cfg):
        # After a successful write, the temp file is renamed away —
        # no lingering .sentinel_config_*.tmp in the directory.
        _run(["495.67"], cfg_path=tmp_cfg)
        leftover = list(tmp_cfg.parent.glob(".sentinel_config_*.tmp"))
        assert leftover == [], f"unexpected temp files: {leftover}"
