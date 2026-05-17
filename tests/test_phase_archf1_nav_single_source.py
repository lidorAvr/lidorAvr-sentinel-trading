"""
Phase Arch-F1 — NAV → target-risk single-source parity (Sprint-25 F1).

Authored BEFORE the risk_monitor reader de-dup. It freezes TODAY's behavior
as the oracle so the de-dup (risk_monitor importing bot_helpers'
get_account_settings, deleting its byte-identical local copy + bare `except:`)
is provably parity-preserving.

Scope (PHASE_ARCHF1_SCOPE.md, Decision A = Honest, Decision B = OUT):
  1. Reader parity — bot_helpers.get_account_settings vs the risk_monitor
     reader for: present / missing / corrupt-JSON / valid-without-`nav`
     sentinel_config.json. The corrupt-config result of BOTH is captured
     explicitly (the Decision-A evidence).
  2. (acc_size, target_risk) parity — bot_helpers.get_nav_and_risk() vs the
     risk_monitor.py:604-607 acc_size/target_risk block, for the same
     nav_info / account_settings inputs (math UNTOUCHED by this phase).
  3. Post-de-dup structure — risk_monitor uses the shared reader; no private
     byte-identical local copy; no bare `except:` in the reader path.
  4. Corrupt-config policy pin — Decision A = Honest. The parity oracle shows
     the resolved fallback dict on a corrupt config is IDENTICAL between the
     old local bare-`except:` copy and bot_helpers' `except Exception:` reader
     (JSONDecodeError is an Exception, caught by both) → the de-dup is pure
     byte-preserving polish on this edge; the only bare-vs-Exception
     divergence is for non-Exception BaseException (KeyboardInterrupt /
     SystemExit), which a corrupt JSON file never raises. This test PINS that
     corrupt-config fallback dict so a future change has an oracle.

No existing test is weakened; this file only ADDs.
"""
import sys, os, json, types
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Stub ONLY the heavy transport deps before importing the modules under
# test. engine_core MUST stay the REAL module: bot_helpers / risk_monitor
# import it cleanly, the parity tests patch bh.ec.get_nav_with_freshness on
# the real object, and stubbing engine_core in sys.modules at collection time
# would poison other suites that use the real engine_core (test isolation).
# This mirrors conftest.mock_telegram_bot (telebot/supabase/dotenv only).
for _mod in ("telebot", "supabase", "dotenv"):
    if _mod not in sys.modules:
        sys.modules[_mod] = types.ModuleType(_mod)
if not getattr(sys.modules["supabase"], "create_client", None):
    sys.modules["supabase"].create_client = lambda *a, **k: None
if not getattr(sys.modules["dotenv"], "load_dotenv", None):
    sys.modules["dotenv"].load_dotenv = lambda *a, **k: None
if not getattr(sys.modules["telebot"], "TeleBot", None):
    sys.modules["telebot"].TeleBot = type(
        "TeleBot", (), {"__init__": lambda *a, **k: None})

import bot_helpers as bh
import risk_monitor as rm


# The expected fallback dict both readers return when the config is
# missing OR corrupt. This is the documented contract literal.
_FALLBACK = {"total_deposited": 7500.0, "risk_pct_input": 0.5}


def _both_readers():
    """The two readers under test.

    bot_helpers.get_account_settings is the shared reader. risk_monitor's
    reader is whatever name risk_monitor exposes — pre-de-dup that is its
    own byte-identical local copy with a bare `except:`; post-de-dup it is
    the same shared bot_helpers reader. Parity must hold in BOTH states.
    """
    return {
        "bot_helpers": bh.get_account_settings,
        "risk_monitor": rm.get_account_settings,
    }


# ── 1. Reader parity: present / missing / corrupt / valid-without-nav ─────────

class TestReaderParity:

    def test_present_valid_config_identical(self, tmp_path, monkeypatch):
        (tmp_path / "sentinel_config.json").write_text(
            json.dumps({"nav": 12345.0, "total_deposited": 9000.0,
                        "risk_pct_input": 0.75}),
            encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        readers = _both_readers()
        bh_res = readers["bot_helpers"]()
        rm_res = readers["risk_monitor"]()
        assert bh_res == rm_res
        assert bh_res == {"nav": 12345.0, "total_deposited": 9000.0,
                          "risk_pct_input": 0.75}

    def test_missing_config_identical_fallback(self, tmp_path, monkeypatch):
        # tmp_path has no sentinel_config.json
        monkeypatch.chdir(tmp_path)
        readers = _both_readers()
        bh_res = readers["bot_helpers"]()
        rm_res = readers["risk_monitor"]()
        assert bh_res == rm_res == _FALLBACK

    def test_corrupt_json_identical_fallback_DECISION_A_EVIDENCE(
            self, tmp_path, monkeypatch):
        """Decision-A crux. Capture BOTH readers' result on a corrupt
        sentinel_config.json. JSONDecodeError is an Exception, so the old
        risk_monitor bare-`except:` copy AND bot_helpers' `except Exception:`
        both catch it and return the identical fallback dict → de-dup is
        pure byte-preserving polish on this edge. This assertion is the
        Decision-A evidence AND the policy pin (Decision A = Honest)."""
        (tmp_path / "sentinel_config.json").write_text(
            '{ this is not valid json ,,, ', encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        readers = _both_readers()
        bh_corrupt = readers["bot_helpers"]()
        rm_corrupt = readers["risk_monitor"]()
        # Both resolve the corrupt config to the SAME honest fallback dict.
        assert bh_corrupt == rm_corrupt
        # Pin the exact corrupt-config behavior (Decision A = Honest:
        # bot_helpers/account_state-consistent fallback, not a divergent
        # swallow that yields a different resolved value).
        assert bh_corrupt == _FALLBACK
        assert rm_corrupt == _FALLBACK

    def test_valid_config_without_nav_identical(self, tmp_path, monkeypatch):
        (tmp_path / "sentinel_config.json").write_text(
            json.dumps({"total_deposited": 6000.0, "risk_pct_input": 0.4}),
            encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        readers = _both_readers()
        bh_res = readers["bot_helpers"]()
        rm_res = readers["risk_monitor"]()
        assert bh_res == rm_res
        assert "nav" not in bh_res
        assert bh_res == {"total_deposited": 6000.0, "risk_pct_input": 0.4}


# ── 2. (acc_size, target_risk) parity: get_nav_and_risk vs rm:604-607 ─────────

def _rm_604_607(nav_info, account_settings):
    """The risk_monitor.py:604-607 acc_size / target_risk block, replicated
    verbatim as the oracle. This phase does NOT touch this math; the test
    asserts bot_helpers.get_nav_and_risk produces the identical pair."""
    acc_size = nav_info["nav"] if nav_info["ok"] else float(
        account_settings.get("total_deposited", 7500.0))
    target_risk_pct = float(account_settings.get("risk_pct_input", 0.5))
    target_risk_usd = acc_size * (target_risk_pct / 100)
    return acc_size, target_risk_usd


class TestAccSizeTargetRiskParity:

    @pytest.mark.parametrize("nav_info,settings", [
        ({"nav": 10000.0, "ok": True, "is_stale": False,
          "freshness_label": "fresh"},
         {"total_deposited": 8000.0, "risk_pct_input": 0.5}),
        ({"nav": 0.0, "ok": False, "is_stale": True,
          "freshness_label": "stale"},
         {"total_deposited": 7500.0, "risk_pct_input": 0.5}),
        ({"nav": 25000.0, "ok": True, "is_stale": True,
          "freshness_label": "stale"},
         {"total_deposited": 9000.0, "risk_pct_input": 1.0}),
        ({"nav": 999.0, "ok": False, "is_stale": True,
          "freshness_label": "crit"},
         {"total_deposited": 12345.0, "risk_pct_input": 0.25}),
        # account_settings missing keys → both fall to the same defaults
        ({"nav": 5000.0, "ok": False, "is_stale": True,
          "freshness_label": "x"},
         {}),
    ])
    def test_identical_acc_size_and_target_risk(self, nav_info, settings):
        with patch.object(bh.ec, "get_nav_with_freshness",
                          return_value=nav_info):
            acc_bh, risk_bh, _ = bh.get_nav_and_risk(settings)
        acc_or, risk_or = _rm_604_607(nav_info, settings)
        assert acc_bh == acc_or
        assert risk_bh == risk_or


# ── 3. Post-de-dup structure: shared reader, no local copy, no bare except ────

class TestSharedReaderDedup:

    def test_risk_monitor_reader_is_bot_helpers_shared_reader(self):
        """After de-dup risk_monitor must resolve get_account_settings to
        the SAME shared bot_helpers function object (imported, not a private
        byte-identical re-definition)."""
        assert rm.get_account_settings is bh.get_account_settings

    def test_no_private_bare_except_reader_copy_in_risk_monitor(self):
        """The byte-identical local config-reader copy with the bare
        `except:` must be gone from risk_monitor's own source. We check the
        function's defining module rather than risk_monitor's text so a mere
        re-export survives but a re-definition fails."""
        import inspect
        defining_module = getattr(rm.get_account_settings, "__module__", "")
        assert defining_module == "bot_helpers", (
            f"risk_monitor.get_account_settings still defined in "
            f"{defining_module!r}; expected the shared bot_helpers reader")
        src = inspect.getsource(rm.get_account_settings)
        # The shared reader uses `except Exception:`, never a bare `except:`.
        assert "except Exception:" in src
        assert "\n    except:" not in src and "\texcept:" not in src
