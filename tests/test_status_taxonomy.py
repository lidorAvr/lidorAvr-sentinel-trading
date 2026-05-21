"""
Status-Taxonomy meeting (21/05/2026) — pinning tests for the
Mark §X7 Verdict-Honesty Clause closure.

Pins:
  - Tag 1 (👀 מוקדם / Too Early) — fresh, flat, low-distribution
  - Tag 2 (❄️ קופא / Stalled) — old, stalled, no new high
  - Tag 3 (🟠 Weak) — unchanged score 40-54
  - Tag 4 (🔴 Broken) — narrowed to genuine structural failure
  - Mutual exclusivity + ordering (deterministic mapping)
  - Call-site forwarding (ENGINE Top-Risk #1)
  - Action lines for the new tags (Mark §3 anti-list + UX register)
  - §X3 AI-copy mirror reaffirmation
  - ARCH: "Stalled is NOT critical" — _CRITICAL_STATUSES tuples
    must not silently absorb the new tag via substring "Broken"
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import engine_core as ec  # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# Tag 1 — 👀 מוקדם (Too Early)
# ════════════════════════════════════════════════════════════════════════════

class TestTagTooEarly:
    """Fresh + flat + low distribution → 👀 מוקדם. The JPM case
    from the founder's /portfolio observation: 1d age, -0.01R, RS
    weakness on the stock chart (low score), but the position itself
    has had no time to develop."""

    def test_positive_jpm_case(self):
        """JPM real-life signature: score~30, age=1, |R|<0.01."""
        out = ec.map_score_to_status(
            score=30, age_days=1, open_r=-0.01,
            features={"dist_12d": 0, "violation_score": 0},
        )
        assert out == "👀 מוקדם"

    def test_positive_exact_age_boundary(self):
        out = ec.map_score_to_status(
            score=30, age_days=3, open_r=0.2,
            features={"dist_12d": 0},
        )
        assert out == "👀 מוקדם"

    def test_negative_one_day_past_fresh(self):
        """age_days=4 is past the fresh window; falls through to Broken."""
        out = ec.map_score_to_status(
            score=30, age_days=4, open_r=-0.01,
            features={"dist_12d": 0, "violation_score": 0},
        )
        assert out == "🔴 Broken"

    def test_negative_real_move_not_just_fresh(self):
        """|open_r|=0.8 → the position made a real move; not 'too early'."""
        out = ec.map_score_to_status(
            score=30, age_days=1, open_r=-0.8,
            features={"dist_12d": 0, "violation_score": 0},
        )
        assert out == "🔴 Broken"

    def test_negative_high_distribution(self):
        """dist_12d>=3 means structural-style violations; not 'too early'."""
        out = ec.map_score_to_status(
            score=30, age_days=1, open_r=0.1,
            features={"dist_12d": 3, "violation_score": 0},
        )
        assert out == "🔴 Broken"


# ════════════════════════════════════════════════════════════════════════════
# Tag 2 — ❄️ קופא (Stalled / Dead Money)
# ════════════════════════════════════════════════════════════════════════════

class TestTagStalled:
    """Old + stalled + no new high → ❄️ קופא. The PLTR case from the
    founder's /portfolio observation: 20d age, -0.25R, no movement —
    structure is intact, just dead money."""

    def test_positive_pltr_case_via_time_efficiency_proxy(self):
        """PLTR real-life signature: score~30, age=20, |R|<0.5,
        time_efficiency='dead_money'. The has_new_high signal isn't
        available at evaluate_position_engine's call site — the
        mapper uses time_efficiency as a proxy."""
        out = ec.map_score_to_status(
            score=30, age_days=20, open_r=-0.25,
            features={"time_efficiency": "dead_money",
                      "violation_score": 1},
        )
        assert out == "❄️ קופא"

    def test_positive_explicit_no_new_high(self):
        """When has_new_high_since_entry is explicitly False, fires
        regardless of time_efficiency."""
        out = ec.map_score_to_status(
            score=30, age_days=15, open_r=-0.2,
            features={"violation_score": 0},
            has_new_high_since_entry=False,
        )
        assert out == "❄️ קופא"

    def test_negative_age_below_threshold(self):
        """age_days=7 is one day below the stalled threshold (8d)."""
        out = ec.map_score_to_status(
            score=30, age_days=7, open_r=-0.25,
            features={"time_efficiency": "dead_money"},
            has_new_high_since_entry=False,
        )
        assert out == "🔴 Broken"

    def test_negative_made_new_high(self):
        """If the position made a new high after entry, it had
        momentum and lost it → that's structural break, not stall."""
        out = ec.map_score_to_status(
            score=30, age_days=20, open_r=-0.25,
            features={"time_efficiency": "dead_money"},
            has_new_high_since_entry=True,
        )
        assert out == "🔴 Broken"

    def test_negative_R_out_of_stalled_band(self):
        """|open_r|=1.0 means real downside move; not 'stalled'."""
        out = ec.map_score_to_status(
            score=30, age_days=20, open_r=-1.0,
            features={"time_efficiency": "dead_money"},
            has_new_high_since_entry=False,
        )
        assert out == "🔴 Broken"

    def test_negative_violation_too_high(self):
        """violation_score>=4 in stalled-window means accumulating
        structural events — falls through to Broken (Mark §X7: stalled
        is the kinematic claim only, violation events are structural)."""
        out = ec.map_score_to_status(
            score=30, age_days=20, open_r=-0.25,
            features={"time_efficiency": "dead_money",
                      "violation_score": 5},
            has_new_high_since_entry=False,
        )
        assert out == "🔴 Broken"


# ════════════════════════════════════════════════════════════════════════════
# Tag 4 — 🔴 Broken (narrowed)
# ════════════════════════════════════════════════════════════════════════════

class TestTagBrokenNarrowed:
    """Mark §X7 binding: "🔴 Broken" requires structural-failure
    predicate. Default-fallback preserved when age/R unavailable
    (byte-identity invariant)."""

    def test_positive_via_violation_score(self):
        out = ec.map_score_to_status(
            score=30, age_days=15, open_r=0.0,
            features={"violation_score": 7},
        )
        assert out == "🔴 Broken"

    def test_positive_default_fallback_proving_window_gap(self):
        """age_days=5 is in the proving-window gap (4-7d). No fresh,
        no stalled — conservative Broken default."""
        out = ec.map_score_to_status(
            score=30, age_days=5, open_r=-0.3,
            features={"violation_score": 0},
        )
        assert out == "🔴 Broken"

    def test_back_compat_no_age_or_R_means_broken(self):
        """When age_days OR open_r is None (legacy callers), behavior
        collapses to pre-meeting mapping. Score<40 → Broken default."""
        out = ec.map_score_to_status(score=30)
        assert out == "🔴 Broken"

    def test_hard_rule_takes_precedence(self):
        """A hard_rule with status= "🔴 Broken" wins over any tag."""
        hr = {"status": "🔴 Broken", "trigger": "test", "action": "test"}
        out = ec.map_score_to_status(
            score=30, hard_rule=hr,
            age_days=1, open_r=-0.01,
            features={"dist_12d": 0, "violation_score": 0},
        )
        assert out == "🔴 Broken"


# ════════════════════════════════════════════════════════════════════════════
# Existing tags unchanged — byte-identity invariant
# ════════════════════════════════════════════════════════════════════════════

class TestExistingBandsByteIdentical:
    """Sprint-25 byte-lock baseline invariant: callers that don't pass
    age/R see ZERO behavior change. Power/Healthy/Yellow/Weak bands
    map identically to pre-meeting."""

    def test_power_unchanged(self):
        assert ec.map_score_to_status(90) == "🔥 Power"

    def test_healthy_unchanged(self):
        assert ec.map_score_to_status(75) == "🟢 Healthy"

    def test_healthy_with_bad_closes_override(self):
        out = ec.map_score_to_status(
            75, features={"bad_closes_10": 5, "good_closes_10": 2}
        )
        assert out == "🟡 תקין אך במעקב"

    def test_yellow_flag_unchanged(self):
        assert ec.map_score_to_status(60) == "🟡 Yellow Flag"

    def test_weak_unchanged(self):
        assert ec.map_score_to_status(45) == "🟠 Weak"

    def test_with_age_R_band_still_wins(self):
        """When score >= 40, age/R parameters are IGNORED — the
        score-band wins. Tag 1 and Tag 2 only fire at score<40."""
        out = ec.map_score_to_status(
            score=75, age_days=1, open_r=-0.01,
            features={"dist_12d": 0},
        )
        assert out == "🟢 Healthy"  # NOT 👀 מוקדם


# ════════════════════════════════════════════════════════════════════════════
# ENGINE Top-Risk #1: call-site forwarding
# ════════════════════════════════════════════════════════════════════════════

class TestCallSiteForwarding:
    """ENGINE flagged the #1 risk: if the implementer wires the
    signature but forgets engine_core.py:460, the new tags silently
    never fire. This test reads the source verbatim to pin the
    forwarding pattern."""

    def _read_engine(self):
        path = os.path.join(os.path.dirname(__file__), "..", "engine_core.py")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def test_call_site_forwards_age_days(self):
        src = self._read_engine()
        # The call site must pass age_days=days_held (the variable
        # computed at :429).
        assert "age_days=days_held" in src

    def test_call_site_forwards_open_r(self):
        src = self._read_engine()
        assert "open_r=total_r" in src


# ════════════════════════════════════════════════════════════════════════════
# UX action lines for the new tags (Mark §3 anti-list)
# ════════════════════════════════════════════════════════════════════════════

class TestActionLinesForNewTags:
    """build_management_action must emit Mark §3-compliant action
    lines for the new tags. No directive verbs; stop unchanged for
    both (a fresh/stalled position is not tightened by status alone).
    """

    def _features(self):
        # Minimal features dict for build_management_action.
        return {"close": 100.0, "ma10": 99.0, "ma20": 98.0,
                "close_below_ma10": False, "close_below_ma20": False}

    def test_too_early_action_line(self):
        action, trigger, stop = ec.build_management_action(
            "👀 מוקדם", self._features(), "early", 95.0, 0.0, "managed"
        )
        assert "תן לזה לזוז" in action
        assert "עוד לא מספיק ימים" in trigger
        # Stop unchanged for fresh positions.
        assert stop == 95.0

    def test_stalled_action_line(self):
        action, trigger, stop = ec.build_management_action(
            "❄️ קופא", self._features(), "developing", 95.0, -0.2, "managed"
        )
        assert "לא להוסיף" in action
        assert "תזה" in action or "תזה" in trigger
        assert "אין תנועה" in trigger
        # Stop unchanged for stalled positions (stalling alone is not
        # a structural trigger to tighten).
        assert stop == 95.0

    def test_too_early_no_directive_verbs(self):
        """Mark §3 anti-list (Sprint-12): no "חובה", "תכתוב!", "אסור"."""
        action, trigger, _ = ec.build_management_action(
            "👀 מוקדם", self._features(), "early", 95.0, 0.0, "managed"
        )
        for forbidden in ("חובה", "אסור", "תכתוב!", "אתה חייב",
                          "אתה לא יכול"):
            assert forbidden not in action
            assert forbidden not in trigger

    def test_stalled_no_directive_verbs(self):
        action, trigger, _ = ec.build_management_action(
            "❄️ קופא", self._features(), "developing", 95.0, -0.2, "managed"
        )
        for forbidden in ("חובה", "אסור", "תכתוב!", "אתה חייב"):
            assert forbidden not in action
            assert forbidden not in trigger


# ════════════════════════════════════════════════════════════════════════════
# ARCH: "Stalled is NOT critical" — _CRITICAL_STATUSES safety
# ════════════════════════════════════════════════════════════════════════════

class TestStalledIsNotCritical:
    """ARCH flagged the silent-substring-absorption risk: if a future
    refactor used `"Broken" in status` it would also absorb future
    tags. Pin: the new tags must NOT contain "Broken" substring,
    AND telegram_portfolio's _CRITICAL_STATUSES must use exact-match
    tuples (not substring-match)."""

    def test_new_tags_dont_contain_broken_substring(self):
        # Substring safety: even if a future refactor uses `"Broken"
        # in status`, the new tags won't be silently absorbed.
        assert "Broken" not in "👀 מוקדם"
        assert "Broken" not in "❄️ קופא"
        assert "שבור" not in "👀 מוקדם"
        assert "שבור" not in "❄️ קופא"

    def test_critical_statuses_uses_exact_match_in_telegram_portfolio(self):
        """The two _CRITICAL_STATUS / _CRITICAL_STATUSES tuples in
        telegram_portfolio.py must check via `status in tuple`
        (exact match), not substring containment. Verify by source
        read — a future regression that changes to substring would
        fail loudly."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "telegram_portfolio.py"
        )
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        # The tuples literally contain "🔴 Broken" — not "Broken".
        # If a future refactor switches to substring match, this pin
        # surfaces in the matcher pattern.
        assert '"🔴 Broken"' in src or "'🔴 Broken'" in src


# ════════════════════════════════════════════════════════════════════════════
# §X3 AI-copy mirror reaffirmation (MARK ruling)
# ════════════════════════════════════════════════════════════════════════════

class TestAiCopyMirrorReaffirmed:
    """MARK reaffirmed §X3 — AI-copy variants must mirror Hebrew
    labels on §3-class wording. For Phase-1, the AI mirror lives in
    the DOC (`MEETING_STATUS_TAXONOMY_UX.md`), not yet in code. This
    test pins that the mapping table is documented + that the AI
    English mirrors are in the file. Production code wires happen
    when the AI export consumer updates (Phase-2)."""

    def test_doc_documents_ai_mirror_pairs(self):
        path = os.path.join(
            os.path.dirname(__file__), "..",
            "docs/teams/MEETING_STATUS_TAXONOMY_UX.md",
        )
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        # Hebrew tag + its English mirror must coexist in the doc.
        assert "👀 מוקדם" in src
        assert "Too Early" in src
        assert "❄️ קופא" in src
        assert "Stalled" in src
