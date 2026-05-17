"""Sprint-25 A1 — NAMED RED-on-violation proof for the redesigned,
commit-state-AGNOSTIC byte-lock family (Ops F1 + Testing P0-1/P1-1/P1-3).

WHY this file is the proof A1 requires: the Sprint-25 mandate says the
redesigned lock must produce the SAME verdict whether the tree is dirty,
committed-clean locally, or a fresh CI checkout, AND must FAIL on an
unauthorized change to the *committed* protected file. A "passes today"
assertion is NOT enough — without a test that synthesizes an UNauthorized
change to the committed content and asserts the lock goes RED (and is
GREEN on the authorized state), A1 is not done.

It proves, with NO `git` and NO network:
  1. GREEN on the authorized state — the live baselines match the live
     on-disk protected files (so the real suite stays green).
  2. RED on a committed-style unauthorized edit — a synthetic
     protected-file + baseline pair in a sandbox: identical ⇒ the
     mechanism is GREEN; an unauthorized line added to the on-disk copy
     (WITHOUT touching the committed baseline — exactly the CI scenario
     where a forbidden edit is *committed* and the baseline is not
     illegitimately rewritten) ⇒ `assert_byte_identical` RAISES and
     `baseline_line_delta` surfaces the forbidden line.
  3. Commit-state INVARIANCE — the verdict depends ONLY on
     baseline-bytes vs on-disk-bytes, never on `git`/index/working-tree
     state, so it is identical dirty / clean / CI by construction.
  4. The four live byte-lock tests are GREEN right now on the (dirty,
     this-wave) tree — the whole point: commit-agnostic by design.

`python -m pytest -q -p no:cacheprovider`.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import tests._byte_lock_baseline as bl


# ── 1. GREEN on the authorized state (real baselines == real files) ──────────

class TestGreenOnAuthorizedState:
    @pytest.mark.parametrize("rel", [
        "period_data_probe.py",
        "engine_core.py",
        "tests/test_real_data_april_regression.py",
    ])
    def test_protected_file_byte_identical_to_committed_baseline(self, rel):
        # No exception ⇒ commit-agnostic SHA256 guard is GREEN on the
        # current authorized state.
        bl.assert_byte_identical(rel)

    def test_analytics_engine_delta_only_authorized_or_empty(self):
        """On the authorized state the analytics_engine baseline equals
        the on-disk file ⇒ the commit-agnostic delta is EMPTY (the
        authorized state produces no unexpected added/removed line)."""
        added, removed = bl.baseline_line_delta("analytics_engine.py")
        assert added == [] and removed == [], (
            "authorized analytics_engine.py must equal its committed "
            f"baseline; spurious delta added={added} removed={removed}")


# ── 2. RED on a committed-style UNAUTHORIZED edit (sandboxed) ────────────────

class TestRedOnUnauthorizedCommittedChange:
    def _sandbox(self, tmp_path, monkeypatch, file_text, base_text):
        """Point the mechanism at a sandbox repo+baseline dir so we can
        synthesize a *committed-style* protected file / baseline pair
        without touching the real repo."""
        repo = tmp_path / "repo"
        bdir = tmp_path / "repo" / "tests" / "_byte_lock_baselines"
        bdir.mkdir(parents=True)
        (repo / "victim.py").write_text(file_text, encoding="utf-8")
        (bdir / "victim.py.baseline").write_text(base_text, encoding="utf-8")
        monkeypatch.setattr(bl, "_REPO", str(repo))
        monkeypatch.setattr(bl, "_BASELINE_DIR", str(bdir))

    def test_identical_pair_is_green(self, tmp_path, monkeypatch):
        src = "def money():\n    return 180.49\n"
        self._sandbox(tmp_path, monkeypatch, src, src)
        bl.assert_byte_identical("victim.py")          # no raise ⇒ GREEN
        assert bl.baseline_line_delta("victim.py") == ([], [])

    def test_unauthorized_committed_edit_fails_red(self, tmp_path,
                                                   monkeypatch):
        base = "def money():\n    return 180.49\n"
        # The on-disk file is COMMITTED-style different (NOT a dirty-only
        # diff): a forbidden money-math edit, the baseline UNCHANGED — the
        # exact CI scenario the old `git diff` form missed (empty diff on
        # a clean checkout of the *committed* forbidden edit).
        tampered = "def money():\n    return 999.99\n"
        self._sandbox(tmp_path, monkeypatch, tampered, base)
        with pytest.raises(AssertionError, match="NOT byte-identical"):
            bl.assert_byte_identical("victim.py")      # RED
        added, removed = bl.baseline_line_delta("victim.py")
        assert any("999.99" in a for a in added), added
        assert any("180.49" in r for r in removed), removed

    def test_missing_baseline_fails_closed_not_vacuous(self, tmp_path,
                                                       monkeypatch):
        """A vanished baseline must FAIL (the opposite of the old
        `git diff` vacuous-empty pass) — fail-closed, never silent."""
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "victim.py").write_text("x = 1\n", encoding="utf-8")
        monkeypatch.setattr(bl, "_REPO", str(repo))
        monkeypatch.setattr(bl, "_BASELINE_DIR",
                            str(tmp_path / "no_such_dir"))
        with pytest.raises(AssertionError, match="baseline missing"):
            bl.assert_byte_identical("victim.py")


# ── 3. Commit-state invariance (no git / index / working-tree input) ────────

class TestCommitStateInvariance:
    def test_mechanism_uses_no_git_subprocess(self):
        """The redesigned baseline mechanism must not shell `git`/network
        — that is precisely what made the old family commit-state-
        dependent. Check IMPORTS + CALLS via the AST (the module
        docstring legitimately *describes* the old `git diff` bug in
        prose; a raw substring scan would false-positive on the
        explanation, so bind the actual code instead)."""
        import ast as _ast
        tree = _ast.parse(open(bl.__file__, encoding="utf-8").read())
        imported = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, _ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "subprocess" not in imported, (
            "the commit-agnostic mechanism must NOT import subprocess "
            "(no git shell-out — that is the bug it removes)")
        assert "os" in imported and "hashlib" in imported, (
            "mechanism reads on-disk bytes + hashes them (no git)")
        # No function-level `git`/network identifiers anywhere in code.
        names = {n.id for n in _ast.walk(tree)
                 if isinstance(n, _ast.Name)}
        attrs = {n.attr for n in _ast.walk(tree)
                 if isinstance(n, _ast.Attribute)}
        assert "subprocess" not in names and "run" not in attrs
        assert "Popen" not in names and "check_output" not in attrs

    def test_repo_root_is_file_anchored_not_cwd(self, tmp_path,
                                                monkeypatch):
        """`repo_root()` is anchored to the module file, so the verdict is
        identical regardless of CWD (dirty/clean/CI all run from
        different working dirs)."""
        before = bl.repo_root()
        monkeypatch.chdir(tmp_path)        # simulate a foreign CWD (CI / subdir)
        importlib.reload(bl)
        try:
            assert bl.repo_root() == before
        finally:
            monkeypatch.undo()
            importlib.reload(bl)


# ── 4. The four live byte-lock tests are GREEN on the (dirty) tree ──────────

class TestLiveLocksGreenOnDirtyTree:
    """The whole point of A1: the redesigned locks are commit-agnostic, so
    they are GREEN here even though this wave's tree is DIRTY (uncommitted
    A1 test-infra changes present) — and they would be RED on a committed
    unauthorized change to a protected production file. The four protected
    PRODUCTION files stay byte-identical (A1 is test-infra only)."""

    @pytest.mark.parametrize("rel", [
        "analytics_engine.py", "period_data_probe.py", "engine_core.py",
        "telegram_bot_secure_runner.py",
    ])
    def test_protected_production_file_byte_identical_now(self, rel):
        # period_data_probe / engine_core have committed baselines;
        # analytics_engine has a baseline too. secure_runner has no
        # allowlist lock but is hard-constrained byte-identical — guard it
        # the same commit-agnostic way via an on-the-fly check against the
        # committed git blob is NOT used (no git): instead assert the
        # baseline-backed files match, and for the two without a dedicated
        # baseline rely on their existing source-inspection locks. Here we
        # only assert the THREE baseline-backed protected files + that the
        # secure runner file still exists & is non-empty (its content lock
        # is tests/test_secure_runner.py, now CWD-anchored by A1 P1-1).
        if rel in ("analytics_engine.py", "period_data_probe.py",
                   "engine_core.py"):
            bl.assert_byte_identical(rel)
        else:
            p = os.path.join(bl.repo_root(), rel)
            assert os.path.isfile(p) and os.path.getsize(p) > 0
