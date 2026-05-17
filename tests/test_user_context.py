"""
Phase A (Hyperscaler) — unit tests for user_context.

Covers, per HYPERSCALER_PHASE_A_SPEC.md §4.1, USER_CONTEXT_INTERFACE_SPEC.md
§8, and DEC-20260515-002:

  * get_current_user_id(): env-driven; falls back to the sentinel UUID with a
    single one-shot warning; never None, never raises.
  * Sentinel UUID matches the migration DEFAULT clause (guards code↔SQL drift).
  * _BUILTIN_DEFAULTS resolve to the *current production values* (the
    single-user smoke test — Mark's existing behaviour is unaffected).
  * Unknown constant name raises KeyError, NOT silent None (fail-loud).
  * MODULE_LEVEL_INVARIANTS (Red Lines) cannot be overridden by a profile or
    by passing user_id.
  * MethodologyProfile has exactly ONE value (minervini_strict) per
    DEC-20260515-002.
  * Mutable defaults are deep-copied (caller cannot corrupt shared state).

Network is disabled by conftest's pytest-socket hook; this module imports no
heavy deps (user_context is a pure leaf module).
"""
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import user_context as uc


@pytest.fixture(autouse=True)
def _reset_module_state(monkeypatch):
    """Each test starts from a clean warning latch + empty cache."""
    monkeypatch.setattr(uc, "_warned", False)
    uc.invalidate_user_cache()
    yield
    uc.invalidate_user_cache()


# ── get_current_user_id ───────────────────────────────────────────────────────


def test_returns_env_when_set(monkeypatch):
    monkeypatch.setenv("DEFAULT_USER_ID", "11111111-1111-1111-1111-111111111111")
    assert uc.get_current_user_id() == "11111111-1111-1111-1111-111111111111"


def test_env_is_stripped(monkeypatch):
    monkeypatch.setenv("DEFAULT_USER_ID", "  22222222-2222-2222-2222-222222222222  ")
    assert uc.get_current_user_id() == "22222222-2222-2222-2222-222222222222"


def test_returns_sentinel_when_unset(monkeypatch):
    monkeypatch.delenv("DEFAULT_USER_ID", raising=False)
    assert uc.get_current_user_id() == uc.SENTINEL_USER_ID
    assert uc.SENTINEL_USER_ID == "00000000-0000-0000-0000-000000000001"


def test_returns_sentinel_when_blank(monkeypatch):
    monkeypatch.setenv("DEFAULT_USER_ID", "   ")
    assert uc.get_current_user_id() == uc.SENTINEL_USER_ID


def test_never_none_never_raises(monkeypatch):
    monkeypatch.delenv("DEFAULT_USER_ID", raising=False)
    val = uc.get_current_user_id()
    assert val is not None
    assert isinstance(val, str) and val


def test_warns_once_then_silent(monkeypatch, capsys):
    monkeypatch.delenv("DEFAULT_USER_ID", raising=False)
    uc.get_current_user_id()
    uc.get_current_user_id()
    uc.get_current_user_id()
    err = capsys.readouterr().err
    assert err.count("[user_context] DEFAULT_USER_ID unset") == 1


def test_no_warning_when_env_set(monkeypatch, capsys):
    monkeypatch.setenv("DEFAULT_USER_ID", uc.SENTINEL_USER_ID)
    uc.get_current_user_id()
    assert "[user_context]" not in capsys.readouterr().err


# ── Sentinel ↔ migration SQL drift guard ──────────────────────────────────────


def test_sentinel_matches_migration_default():
    """The Python sentinel literal must equal the SQL DEFAULT clause in BOTH
    Phase A migrations. Guards against silent code↔SQL drift."""
    root = Path(__file__).resolve().parents[1]
    for fname in ("003_add_user_id_to_trades.sql",
                  "004_add_user_id_to_audit_log.sql"):
        sql = (root / "migrations" / fname).read_text()
        m = re.search(r"DEFAULT\s+'([0-9a-fA-F-]{36})'", sql)
        assert m is not None, f"no DEFAULT uuid clause found in {fname}"
        assert m.group(1) == uc.SENTINEL_USER_ID, (
            f"{fname} DEFAULT {m.group(1)} != SENTINEL_USER_ID "
            f"{uc.SENTINEL_USER_ID}"
        )


def test_verify_migrations_lists_phase_a():
    """verify_migrations.py must know about 003/004 with their user_id column."""
    root = Path(__file__).resolve().parents[1]
    src = (root / "migrations" / "verify_migrations.py").read_text()
    assert "003_add_user_id_to_trades.sql" in src
    assert "004_add_user_id_to_audit_log.sql" in src


# ── Single-user smoke test — Mark's behaviour is unaffected (Mark directive #2)─

# These are the exact current production values, independently restated here so
# the test fails loudly if _BUILTIN_DEFAULTS ever drifts from the codebase.
_EXPECTED_PROD_CONSTANTS = {
    "live_alert_repeat_cooldown_sec":      45 * 60,
    "deviation_cooldown_sec":              3 * 3600,
    "giveback_cooldown_sec":               6 * 3600,
    "state_alert_cooldown_runner_sec":     4 * 3600,
    "state_alert_cooldown_broken_sec":     4 * 3600,
    "state_alert_cooldown_dead_money_sec": 12 * 3600,
    "sizing_leak_threshold":               0.65,
    "profit_checkpoints":                  [2.0, 3.0],
    "risk_ladder":                         [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00],
    "drawdown_trigger_pct":                -8.0,
    "drawdown_cut_to_pct":                 0.40,
    "drawdown_window_days":                30,
    "risk_settle_hours":                   48.0,
    "weekly_report_dow":                   5,
    "weekly_report_hour_il":               8,
    "weekly_report_minute_il":             30,
    "weekly_report_tz":                    "Asia/Jerusalem",
    "monthly_report_day":                  1,
    "monthly_report_hour_il":              8,
    "monthly_report_minute_il":            40,
    "algo_symbol_limits":                  {"QQQ": 10.0, "TSLA": 7.0, "JPM": 7.0,
                                            "PLTR": 6.0, "HOOD": 6.0},
    "algo_cluster_warning_pct":            30.0,
    "algo_cluster_critical_pct":           35.0,
    "setup_universe":                      ["VCP", "ALGO", "SWING", "EP"],
    "developer_menu_visible":              True,
    "addon_default_size_ratio":            0.40,
    "addon_min_open_r_for_addon":          1.0,
    "addon_hard_floor_ratio":              -0.25,
    "addon_chase_ext_limit":               0.07,
    "addon_max_size_vs_original":          1.0,
    "addon_max_size_vs_current":           0.50,
    "addon_min_cushion_ratio":             0.50,
    "daily_digest_utc_hour_start":         21,
    "daily_digest_utc_hour_end":           22,
    "daily_digest_days_of_week":           [0, 1, 2, 3, 4],
    "dist_window_days":                    12,
    "accum_window_days":                   10,
    "good_closes_window_days":             10,
    "trail_tight_r_threshold":             8.0,
    "trail_loose_r_threshold":             5.0,
    "trail_ma_buffer_pct":                 0.02,
    "trail_atr_factor":                    0.008,
    "position_card_density":               "default",
    "main_menu_buttons":                   ["📊 מצב תיק", "🔬 ניתוח",
                                            "📚 יומן", "❓ עזרה", "🛠️ מפתח"],
}


@pytest.mark.parametrize("name,expected", sorted(_EXPECTED_PROD_CONSTANTS.items()))
def test_single_user_smoke_constants_equal_production(monkeypatch, name, expected):
    """SMOKE TEST (Mark directive #2): with NO DEFAULT_USER_ID set, every
    resolved constant equals the current hard-coded production value. This
    proves the existing single user's behaviour is byte-identical when the
    touchpoints are later wired through get_user_constant()."""
    monkeypatch.delenv("DEFAULT_USER_ID", raising=False)
    assert uc.get_user_constant(name) == expected


def test_builtin_defaults_has_no_extra_keys():
    """_BUILTIN_DEFAULTS must contain exactly the documented production set —
    no stray keys that a touchpoint could later read with a drifted value."""
    assert set(uc._BUILTIN_DEFAULTS) == set(_EXPECTED_PROD_CONSTANTS)


def test_default_profile_is_marks_current_identity():
    monkeypatch_unset = os.environ.pop("DEFAULT_USER_ID", None)
    try:
        p = uc.get_user_profile()
        assert p.user_id == uc.SENTINEL_USER_ID
        assert p.display_name == "Mark"
        assert p.language == "he"
        assert p.timezone == "Asia/Jerusalem"
        assert p.methodology_profile == uc.MethodologyProfile.MINERVINI_STRICT
        assert p.constants == {}
    finally:
        if monkeypatch_unset is not None:
            os.environ["DEFAULT_USER_ID"] = monkeypatch_unset


# ── Fail-loud on unknown name ─────────────────────────────────────────────────


def test_unknown_constant_raises_keyerror_not_none():
    with pytest.raises(KeyError):
        uc.get_user_constant("not_a_real_constant")


def test_typo_does_not_silently_return_none():
    """A typo must be discoverable, never produce a silent None (which would,
    e.g., schedule a digest at midnight)."""
    with pytest.raises(KeyError):
        uc.get_user_constant("daily_digest_utc_hour_strat")  # deliberate typo


# ── MODULE_LEVEL_INVARIANTS — Red Lines cannot be overridden ──────────────────


def test_red_line_invariants_resolve_to_hardcoded_values():
    assert uc.get_user_constant("mix_algo_into_wr") is False
    assert uc.get_user_constant("admin_only_telegram") is True
    assert uc.get_user_constant("data_incomplete_in_stats") is False
    assert uc.get_user_constant("secure_runner_required") is True
    assert uc.get_user_constant("fallback_data_as_truth") is False


def test_invariants_ignore_user_id():
    for uid in ("any-uuid", uc.SENTINEL_USER_ID, "u-malicious", ""):
        assert uc.get_user_constant("mix_algo_into_wr", user_id=uid) is False
        assert uc.get_user_constant("admin_only_telegram", user_id=uid) is True


def test_invariants_cannot_be_overridden_by_profile_constants(monkeypatch):
    """A malicious/typo'd profile.constants entry MUST NOT shadow a Red Line."""
    malicious = uc.UserProfile(
        user_id="u-malicious",
        constants={
            "mix_algo_into_wr": True,
            "admin_only_telegram": False,
            "data_incomplete_in_stats": True,
            "secure_runner_required": False,
        },
    )
    monkeypatch.setattr(uc, "_load_profile_from_backend", lambda uid: malicious)
    uc.invalidate_user_cache()
    assert uc.get_user_constant("mix_algo_into_wr", user_id="u-malicious") is False
    assert uc.get_user_constant("admin_only_telegram", user_id="u-malicious") is True
    assert uc.get_user_constant("data_incomplete_in_stats", user_id="u-malicious") is False
    assert uc.get_user_constant("secure_runner_required", user_id="u-malicious") is True


def test_invariants_not_in_user_profile_fields():
    """Red Lines must NOT be UserProfile dataclass fields (Mark directive #1)."""
    field_names = set(uc.UserProfile.__dataclass_fields__)
    for inv in uc.MODULE_LEVEL_INVARIANTS:
        assert inv not in field_names


def test_invariants_not_in_builtin_defaults():
    """Red Lines must be unreachable via the tunable-constant path."""
    for inv in uc.MODULE_LEVEL_INVARIANTS:
        assert inv not in uc._BUILTIN_DEFAULTS


# ── Single methodology enum (DEC-20260515-002) ────────────────────────────────


def test_methodology_profile_has_exactly_one_value():
    values = [m.value for m in uc.MethodologyProfile]
    assert values == ["minervini_strict"]


def test_default_methodology_is_minervini_strict():
    assert uc._DEFAULT_PROFILE.methodology_profile is uc.MethodologyProfile.MINERVINI_STRICT


# ── Mutable default isolation ─────────────────────────────────────────────────


def test_mutable_list_default_is_deep_copied():
    ladder_a = uc.get_user_constant("risk_ladder")
    ladder_a.append(99.0)
    ladder_b = uc.get_user_constant("risk_ladder")
    assert ladder_b == [0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]
    assert 99.0 not in ladder_b


def test_mutable_dict_default_is_deep_copied():
    limits_a = uc.get_user_constant("algo_symbol_limits")
    limits_a["NVDA"] = 999.0
    limits_b = uc.get_user_constant("algo_symbol_limits")
    assert "NVDA" not in limits_b


# ── Profile override path (Phase B preview — not used in Phase A) ──────────────


def test_profile_constants_override_when_set(monkeypatch):
    custom = uc.UserProfile(
        user_id="u-test",
        constants={"live_alert_repeat_cooldown_sec": 1800},
    )
    monkeypatch.setattr(uc, "_load_profile_from_backend", lambda uid: custom)
    uc.invalidate_user_cache()
    assert uc.get_user_constant("live_alert_repeat_cooldown_sec", user_id="u-test") == 1800
    # Non-overridden key still resolves to the production default.
    assert uc.get_user_constant("risk_settle_hours", user_id="u-test") == 48.0


# ── Caching ───────────────────────────────────────────────────────────────────


def test_cache_serves_within_ttl(monkeypatch):
    calls = []

    def _backend(uid):
        calls.append(uid)
        return uc._DEFAULT_PROFILE

    monkeypatch.setattr(uc, "_load_profile_from_backend", _backend)
    uc.invalidate_user_cache()
    uc.get_user_profile("u-cache")
    uc.get_user_profile("u-cache")
    assert len(calls) == 1  # second call served from cache


def test_cache_refreshes_after_ttl(monkeypatch):
    calls = []
    fake_now = [1000.0]

    monkeypatch.setattr(uc.time, "time", lambda: fake_now[0])
    monkeypatch.setattr(
        uc, "_load_profile_from_backend",
        lambda uid: (calls.append(uid) or uc._DEFAULT_PROFILE),
    )
    uc.invalidate_user_cache()
    uc.get_user_profile("u-ttl")
    fake_now[0] += uc._CACHE_TTL_SEC + 1
    uc.get_user_profile("u-ttl")
    assert len(calls) == 2


# ── effective_profile_dump (debug helper) ─────────────────────────────────────


def test_effective_profile_dump_shape(monkeypatch):
    monkeypatch.delenv("DEFAULT_USER_ID", raising=False)
    dump = uc.effective_profile_dump()
    assert dump["user_id"] == uc.SENTINEL_USER_ID
    assert dump["profile"]["display_name"] == "Mark"
    assert dump["profile"]["methodology_profile"] == "minervini_strict"
    assert dump["invariants"]["mix_algo_into_wr"] is False
    assert dump["constants"]["risk_settle_hours"] == 48.0
    # Dump is a copy — mutating it must not corrupt module state.
    dump["constants"]["risk_ladder"].append(123.0)
    assert 123.0 not in uc.get_user_constant("risk_ladder")
