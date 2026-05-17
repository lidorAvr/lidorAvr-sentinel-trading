"""Sprint-23 Wave-2 — probe "message too long" (Telegram 400) split test.

Gate: docs/teams/MARK_SPRINT23_RULINGS.md 10-item Wave-2 checklist
(items 4,5,6,7) + docs/teams/SPRINT23_DESIGN.md §4. DEC-20260516-020.

Proven defect: telegram_bot.py:318 builds the full probe string and the
single bot.send_message at :319-320 sends it plain-text in ONE message; the
~20-campaign × 2-window output exceeds Telegram's 4096-char hard cap →
`Bad Request: message is too long`.

Fix under test: the additive module-level helper
`telegram_bot._send_probe_chunks(chat_id, text)` — loss-free, plain-text
(NO parse_mode), window-then-`\n` boundary split, per-part RTL re-prefix,
reply_markup on the LAST part ONLY, short input → exactly ONE send
(byte-identical to the pre-Sprint-23 behaviour).

Asserts:
  (a) loss-free / order / no campaign row split — concatenated parts
      (stripping injected per-part RTL + re-inserting the cosmetic
      inter-window "\\n\\n") reproduce the original exactly; every
      campaign line present once, in order, never split;
  (b) every part <= 3900;
  (c) NO parse_mode on ANY probe part;
  (d) reply_markup only on the LAST part;
  (e) short string → exactly ONE send (unchanged behaviour);
  (f) RTL prefix (U+200F) on every part;
  (g) period_data_probe.py byte-identical (git diff empty);
  (h) tests/test_sprint21_wave2.py §A1 READ-ONLY / §A3 no-secrets AST
      contract still green (collected & passing alongside this file).

bot.send_message is mocked — this test NEVER touches Telegram.
"""
import os
import subprocess
import sys

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Sprint-25 A1 — commit-state-AGNOSTIC byte-lock baseline (replaces the
# old `git diff -- period_data_probe.py` working-tree-vs-index source,
# EMPTY/vacuous on every clean CI checkout). See tests/_byte_lock_baseline.py.
from tests._byte_lock_baseline import assert_byte_identical

# ── Mock heavy deps before importing telegram_bot (mirrors the proven
#    tests/test_developer_menu.py bootstrap) ────────────────────────────────
for _mod in ("telebot", "telebot.types", "supabase", "dotenv",
             "adaptive_risk_engine", "engine_core", "telegram_formatters"):
    sys.modules.setdefault(_mod, MagicMock())

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")

import telegram_bot as tb           # noqa: E402
import period_data_probe as probe   # noqa: E402

_RTL = probe._RTL                   # U+200F — == bot_core.RTL (parity proven)
LIMIT = 3900                        # ⟨MARK:3900⟩ — ratified, Mark Ruling 4
_REPO_ROOT = os.path.dirname(os.path.dirname(__file__))
_SENTINEL_MENU = "<<DEV_MENU_KB>>"  # distinct, identity-checkable marker


# ── Spy bot ─────────────────────────────────────────────────────────────────

class _SpyBot:
    """Captures every send_message(chat_id, text, **kwargs)."""

    def __init__(self):
        self.calls = []  # list[(chat_id, text, kwargs)]

    def send_message(self, chat_id, text, **kwargs):
        self.calls.append((chat_id, text, kwargs))
        return MagicMock(message_id=len(self.calls))


@pytest.fixture
def spy(monkeypatch):
    s = _SpyBot()
    monkeypatch.setattr(tb, "bot", s)
    monkeypatch.setattr(tb, "get_developer_menu", lambda: _SENTINEL_MENU)
    return s


# ── Synthetic probe-shaped fixtures ─────────────────────────────────────────

def _campaign_line(window, i):
    # ~120-char-ish per-campaign line; campaign_id contains '_' (the exact
    # Markdown-hostile shape — proves NO parse_mode is required/used).
    return (f"{window} • HOOD_926039554{i:02d} • SYM{i:02d} • "
            f"R=+{i % 5}.{i % 10} • PnL=+{i * 13}.{i % 100:02d}$ • "
            f"entry=12{i:02d}.50 • IRP=11{i:02d}.00 • SL=10{i:02d}.25")


def _window_block(window, n):
    lines = [f"{window}-head — פירוט קמפיין —"]
    lines += [_campaign_line(window, i) for i in range(n)]
    lines.append(f"{window}-summary — WS-C: n_recoverable=0")
    return "\n".join(lines)


def _big_probe(n_each=60):
    """Mirror build_probe_report(None): _RTL+W + "\\n\\n" + _RTL + M, >4096."""
    weekly = _window_block("שבועי", n_each)
    monthly = _window_block("חודשי", n_each)
    s = _RTL + weekly + "\n\n" + _RTL + monthly
    assert len(s) > 4096, "fixture must exceed Telegram's hard cap"
    return s, weekly, monthly


def _all_campaign_lines(weekly, monthly):
    out = []
    for blk in (weekly, monthly):
        out += [ln for ln in blk.split("\n") if " • HOOD_" in ln]
    return out


# ── (e) short string → exactly ONE send (unchanged behaviour) ───────────────

class TestShortSingleSend:
    def test_short_probe_is_one_send_with_markup_no_parse_mode(self, spy):
        short = _RTL + "שבועי-head\nשבועי • HOOD_1 • ok\nשבועי-summary"
        assert len(short) <= LIMIT
        ret = tb._send_probe_chunks(777, short)

        assert len(spy.calls) == 1, "short input must be exactly ONE send"
        chat_id, text, kw = spy.calls[0]
        assert chat_id == 777
        assert text == short, "short send must be byte-identical to original"
        assert "parse_mode" not in kw, "probe send must be plain-text"
        assert kw.get("reply_markup") is _SENTINEL_MENU
        assert ret is not None

    def test_exactly_at_limit_still_single_send(self, spy):
        s = _RTL + "x" * (LIMIT - len(_RTL))
        assert len(s) == LIMIT
        tb._send_probe_chunks(1, s)
        assert len(spy.calls) == 1
        assert spy.calls[0][1] == s
        assert "parse_mode" not in spy.calls[0][2]


# ── (a)(b)(c)(d)(f) the over-limit split ────────────────────────────────────

class TestOverLimitSplit:
    def _run(self, spy):
        s, weekly, monthly = _big_probe(60)
        tb._send_probe_chunks(42, s)
        return s, weekly, monthly, [c[1] for c in spy.calls], spy.calls

    def test_multiple_parts_emitted(self, spy):
        s, _w, _m, parts, _ = self._run(spy)
        assert len(parts) >= 2, "an over-cap probe must split into >1 part"

    # (b)
    def test_every_part_within_limit(self, spy):
        _s, _w, _m, parts, _ = self._run(spy)
        for i, p in enumerate(parts):
            assert len(p) <= LIMIT, f"part {i} len={len(p)} > {LIMIT}"

    # (f)
    def test_every_part_rtl_prefixed(self, spy):
        _s, _w, _m, parts, _ = self._run(spy)
        for i, p in enumerate(parts):
            assert p.startswith(_RTL), f"part {i} missing U+200F RTL prefix"
        assert _RTL == "‏"

    # (c)
    def test_no_parse_mode_on_any_part(self, spy):
        self._run(spy)
        for i, (_cid, _txt, kw) in enumerate(spy.calls):
            assert "parse_mode" not in kw, f"part {i} carries parse_mode"

    # (d)
    def test_reply_markup_last_part_only(self, spy):
        _s, _w, _m, _p, calls = self._run(spy)
        for i, (_cid, _txt, kw) in enumerate(calls):
            if i == len(calls) - 1:
                assert kw.get("reply_markup") is _SENTINEL_MENU, \
                    "LAST part must carry get_developer_menu()"
            else:
                assert "reply_markup" not in kw or \
                    kw.get("reply_markup") is None, \
                    f"non-last part {i} must NOT carry reply_markup"

    # (a) loss-free: reconstruct the exact original
    def test_loss_free_reconstruction(self, spy):
        s, w, m, parts, _ = self._run(spy)

        # Strip the injected per-part leading RTL prefix from EVERY part
        # and concatenate in send order. The window split removed exactly
        # ONE cosmetic substring — the inter-window "\n\n" glue between the
        # two _RTL-headed segments (period_data_probe.py:328). Re-prefix a
        # single _RTL (each segment's own _RTL was stripped above) and
        # re-insert the "\n\n" + _RTL at the unique, structure-defined
        # weekly→monthly seam (weekly's last/summary line directly abuts
        # monthly's head line once the glue is gone).
        bodies = [p[len(_RTL):] if p.startswith(_RTL) else p for p in parts]
        w_tail = w.split("\n")[-1]   # weekly summary line
        m_head = m.split("\n")[0]    # monthly head line
        seam = w_tail + m_head
        reglued = (_RTL + "".join(bodies)).replace(
            seam, w_tail + "\n\n" + _RTL + m_head, 1)
        assert reglued == s, \
            "concatenated parts must reproduce the original probe exactly"

    # (a) every campaign row present exactly once, in order, never split
    def test_every_campaign_line_present_once_in_order_uncut(self, spy):
        s, w, m, parts, _ = self._run(spy)
        expected = _all_campaign_lines(w, m)

        # Each campaign line must live wholly inside exactly one part.
        seen = []
        for p in parts:
            body = p[len(_RTL):] if p.startswith(_RTL) else p
            for ln in body.split("\n"):
                if " • HOOD_" in ln:
                    seen.append(ln)
        assert seen == expected, \
            "campaign rows must appear once, in order, none split/dropped"
        assert len(seen) == len(set(seen)) == 120  # 60 weekly + 60 monthly

        # No campaign id may straddle a part boundary.
        for p in parts:
            assert not p.endswith("HOOD_"), "campaign id split across parts"

    def test_within_window_split_only_at_newline(self, spy):
        """If a single window itself exceeds the cap it splits at '\\n'
        only — never mid-line / mid-campaign."""
        big_weekly = _window_block("שבועי", 80)
        seg = _RTL + big_weekly
        assert len(seg) > LIMIT
        tb._send_probe_chunks(9, seg)
        parts = [c[1] for c in spy.calls]
        assert len(parts) >= 2
        for p in parts:
            assert len(p) <= LIMIT
            assert p.startswith(_RTL)
        bodies = [p[len(_RTL):] for p in parts]
        assert "".join(bodies) == big_weekly, \
            "within-window split must be loss-free at '\\n' boundaries"
        # last part only carries the menu
        for i, (_c, _t, kw) in enumerate(spy.calls):
            if i == len(spy.calls) - 1:
                assert kw.get("reply_markup") is _SENTINEL_MENU
            else:
                assert "reply_markup" not in kw or \
                    kw["reply_markup"] is None
            assert "parse_mode" not in kw

    def test_oversized_single_line_emitted_whole_never_dropped(self, spy):
        """Loss-free dominates the size target: a single source line
        longer than the cap is emitted WHOLE in its own part, never
        truncated/dropped (Mark Ruling 1 / Ruling 4 edge)."""
        giant = "שבועי • HOOD_X • " + "Z" * (LIMIT + 500)
        seg = _RTL + "head\n" + giant + "\ntail"
        tb._send_probe_chunks(5, seg)
        parts = [c[1] for c in spy.calls]
        bodies = [p[len(_RTL):] if p.startswith(_RTL) else p for p in parts]
        joined = "".join(bodies)
        assert giant in joined, "oversized line must never be dropped"
        assert joined.count(giant) == 1, "oversized line not duplicated"
        # every other line preserved too
        assert "head" in joined and "tail" in joined


# ── (g) probe byte-identical (git diff empty) ───────────────────────────────

class TestProbeByteIdentical:
    def test_period_data_probe_git_diff_empty(self):
        # Sprint-25 A1 (Ops F1 / Testing P0-1): commit-state-AGNOSTIC
        # SHA256 of the current ON-DISK period_data_probe.py vs its
        # committed authorized baseline (tests/_byte_lock_baselines/
        # period_data_probe.py.baseline). The OLD `git diff --quiet`
        # (working-tree vs index) was EMPTY on every clean CI checkout →
        # this guard passed VACUOUSLY exactly where merges gate. The
        # verdict is now identical dirty / committed-clean / fresh CI and
        # FAILS on an unauthorized change to the *committed* file.
        assert_byte_identical("period_data_probe.py")

    def test_probe_still_send_free_no_bot_attr(self):
        """The probe gained NO send/bot surface — its binding contract
        (period_data_probe.py:33-38) and the §A1 AST proof hold."""
        src = open(os.path.join(_REPO_ROOT, "period_data_probe.py"),
                   encoding="utf-8").read()
        assert "bot.send_message" not in src
        assert "_send_probe_chunks" not in src


# ── (h) the Sprint-21 §A1/§A3 AST contract still green ───────────────────────

class TestSprint21ASTContractStillGreen:
    def test_sprint21_wave2_ast_contract_passes(self):
        """The READ-ONLY (§A1) + no-secrets (§A3) AST proof on
        period_data_probe.py is unaffected by this caller-side fix."""
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "tests/test_sprint21_wave2.py::TestWSAReadOnlyAST",
             "tests/test_sprint21_wave2.py::TestWSANoSecret"],
            cwd=_REPO_ROOT, capture_output=True, text=True)
        assert r.returncode == 0, (
            "Sprint-21 §A1/§A3 AST contract must stay green:\n"
            + r.stdout[-3000:] + r.stderr[-1500:])


# ── single production caller invariant (design §5) ──────────────────────────

class TestSingleProductionCaller:
    def test_exactly_one_production_caller_via_send_probe_chunks(self):
        tb_src = open(os.path.join(_REPO_ROOT, "telegram_bot.py"),
                      encoding="utf-8").read()
        # the success path now routes through the additive helper
        assert "return _send_probe_chunks(chat_id, txt)" in tb_src
        # and the old single-send success line is gone
        assert "return bot.send_message(chat_id, txt,\n" not in tb_src
        # the except error path keeps its short-token Markdown (unchanged)
        assert 'f"{RTL}❌ שגיאת Probe:' in tb_src
        assert tb_src.count("def _send_probe_chunks(") == 1
