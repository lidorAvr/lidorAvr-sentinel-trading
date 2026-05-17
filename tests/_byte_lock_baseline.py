"""Sprint-25 A1 — commit-state-AGNOSTIC byte-lock baseline mechanism.

WHY THIS EXISTS (the Sprint-25 headline finding, Ops F1 + Testing P0-1):
the entire Sprint-19/22/23/24 byte-lock family asserted on
`git diff -- <file>` — working tree vs the **index**. On a clean/committed
checkout (i.e. EVERY CI run via `actions/checkout@v4`) `index == working
tree`, so `git diff` is EMPTY, so every additive/removed/byte-identical
assertion is **vacuously true**. The money-math protection was INERT
exactly where merges gate. `1a9213a` only fixed one symptom.

THE FIX — a committed in-repo baseline snapshot:
`tests/_byte_lock_baselines/<file>.baseline` is a committed verbatim copy
of each protected file at its authorized state. The lock compares the
**current on-disk content** against that committed baseline. This is:

  * commit-state-AGNOSTIC — the verdict depends ONLY on on-disk bytes vs
    the committed baseline bytes, so it is IDENTICAL whether the tree is
    dirty, committed-clean locally, or a fresh shallow CI checkout. There
    is no `git`, no index, no working-tree state, no `origin/main`, no
    `merge-base`, no network, and no ref a shallow CI checkout lacks.
  * actually ENFORCING — an unauthorized change to the *committed*
    protected file changes its bytes ⇒ SHA mismatch / a non-authorized
    diff line ⇒ the lock FAILS, in CI, exactly where merges gate.
  * allowlist-preserving — `baseline_line_delta()` returns the SAME
    `(added, removed)` line-list shape the old `git diff` parsing produced
    (via `difflib`, only the SOURCE of the diff changed from
    working-tree-vs-index to committed-baseline-vs-on-disk). Every
    existing Sprint-20/21/22/24 authorized-allowlist clause is untouched;
    only the diff source is now commit-agnostic. Nothing widened.

Authorized-change ritual (unchanged in spirit from the Sprint-24 governed
expansion): a *legitimate, Mark-gated* edit to a protected file is landed
together with a regenerated `<file>.baseline` (the existing allowlist
clauses still constrain WHAT may differ); an *unauthorized* edit that does
NOT also (illegitimately) rewrite the committed baseline fails the SHA /
allowlist guard. The RED-on-violation proof
(tests/test_sprint25_byte_lock_redteam.py) demonstrates both directions.
"""
import difflib
import hashlib
import os

# Repo root = parent of tests/.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BASELINE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "_byte_lock_baselines")


def repo_root():
    """Absolute repo root, anchored to THIS file (CWD-independent)."""
    return _REPO


def _baseline_path(rel_path):
    name = os.path.basename(rel_path) + ".baseline"
    return os.path.join(_BASELINE_DIR, name)


def baseline_text(rel_path):
    """The committed authorized-state baseline content for `rel_path`.

    Fail-CLOSED: a missing baseline raises (the lock must never silently
    pass because its baseline artifact vanished) — this is the opposite of
    the old `git diff` vacuous-empty failure mode.
    """
    p = _baseline_path(rel_path)
    if not os.path.isfile(p):
        raise AssertionError(
            f"byte-lock baseline missing for {rel_path!r} ({p}); the "
            "commit-agnostic lock cannot be vacuously satisfied — a "
            "baseline MUST exist and be committed alongside the protected "
            "file")
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def current_text(rel_path):
    """Current on-disk content of the protected file (repo-root anchored)."""
    with open(os.path.join(_REPO, rel_path), "r", encoding="utf-8") as f:
        return f.read()


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def baseline_sha(rel_path):
    return _sha256(baseline_text(rel_path))


def current_sha(rel_path):
    return _sha256(current_text(rel_path))


def assert_byte_identical(rel_path):
    """Hard byte-identity guard (no allowlist): current == committed
    baseline, SHA256. Commit-state-agnostic; FAILS on ANY unauthorized
    edit to the committed file (this is the whole point — the old
    `git diff` form passed vacuously in CI)."""
    b, c = baseline_sha(rel_path), current_sha(rel_path)
    assert b == c, (
        f"{rel_path} is NOT byte-identical to its committed authorized "
        f"baseline (commit-agnostic SHA256 guard). baseline={b} "
        f"current={c}. An authorized change must regenerate "
        f"tests/_byte_lock_baselines/{os.path.basename(rel_path)}.baseline "
        f"via the governed Mark-gated ritual.")


def baseline_line_delta(rel_path):
    """Commit-agnostic replacement for the old
    `git diff -- <file>` `+`/`-` line scan.

    Returns `(added, removed)`: lines present in the CURRENT on-disk file
    but NOT the committed baseline (`added`), and lines in the baseline
    but NOT current (`removed`) — the SAME shape the old `git diff`
    parsing fed into every existing authorized-allowlist clause. Only the
    diff SOURCE changed (committed-baseline-vs-on-disk, not
    working-tree-vs-index), so the verdict is now identical dirty / clean
    / CI and the allowlist semantics are byte-for-byte preserved.
    """
    base = baseline_text(rel_path).splitlines()
    cur = current_text(rel_path).splitlines()
    sm = difflib.SequenceMatcher(a=base, b=cur, autojunk=False)
    added, removed = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(base[i1:i2])
        if tag in ("replace", "insert"):
            added.extend(cur[j1:j2])
    return added, removed
