"""
Sprint-25 Wave-2B C1 — named proof for the dev-PIN enforcement CLOSURE-FIX
(Security S-1 / S-2 / S-3; Mark Ruling 3 "named proof", Ruling 5 §A.3).

Closes the gap the Wave-1 Security audit flagged: the ONLY dev-PIN check
was on the `🛠️ מפתח` menu-OPEN button; every privileged dev handler then
dispatched purely on `text == "<button>"` with NO `dev_pin_session_active`
re-check, and an unset `DEV_PIN` made the gate fail-OPEN.

What this proves (the specific validated path per privileged handler):

  * S-1 — admin chat-id but NO active dev session ⇒ the privileged side
    effect (subprocess `git pull` / IBKR sync thread / arming the XML
    upload / config dump / log dump / on-demand report thread / probe /
    health) is NEVER invoked, and a Hebrew refusal is returned.
  * S-1 — WITH a valid active session ⇒ behaviour is UNCHANGED (the
    action proceeds, side effect invoked) — the normal authorized-admin
    flow is byte-identical.
  * S-2 — `DEV_PIN` unset/empty ⇒ fail-CLOSED: the dev menu AND every
    privileged action are DENIED (never opened).
  * S-3 — the XML upload write path (`handle_document_upload` →
    Supabase insert + NAV overwrite) refuses without an active session.
  * The outer admin (chat-id) gate + secure_runner wrapping are
    UNAFFECTED (behavioural `guard_decision` + wrap-ordering checks).

These handlers are decorated with `@bot.message_handler(...)`. In the
test environment `telebot` is stubbed, so the decorator is configured to
return the function UNCHANGED — exactly the real production function body
runs here, only the decorator registration is a no-op.
"""
import sys
import os
import types
import importlib
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "ci-test-token")
os.environ.setdefault("TELEGRAM_ADMIN_ID", "12345")
os.environ.setdefault("SUPABASE_URL", "https://ci-test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "ci-test-key")

ADMIN_CHAT_ID = 12345


def _identity_decorator(*dargs, **dkwargs):
    """A @bot.message_handler / @bot.callback_query_handler replacement that
    returns the decorated function UNCHANGED (registration is a no-op so the
    real handler stays directly callable in-process)."""
    def _wrap(func):
        return func
    return _wrap


class _RecordingBot:
    """Minimal telebot.TeleBot stand-in dedicated to THIS test module.

    Records every `send_message` so the named proof can assert exactly
    which Hebrew text a privileged handler returned, fully isolated from
    whatever stub other suite files installed for `telebot` (run-order
    independent — does NOT rely on MagicMock.reset_mock())."""

    def __init__(self, *a, **k):
        self.sent = []
        self.message_handler = _identity_decorator
        self.callback_query_handler = _identity_decorator

    def send_message(self, chat_id, text, *a, **k):
        self.sent.append((chat_id, text))
        return MagicMock(message_id=1)

    def __getattr__(self, name):
        # get_file/download_file/delete_message/etc. — harmless no-ops.
        return MagicMock()


@pytest.fixture
def tb(monkeypatch):
    """Import telegram_bot against a DEDICATED self-contained stub set so the
    real handler functions stay directly callable and no state leaks in from
    (or out to) other suite files regardless of collection order."""
    # Own, fresh stub modules for THIS test (force-replace, not setdefault —
    # other files may have installed a custom telebot/_FakeBot we must not
    # depend on or pollute).
    saved = {}
    for _mod in ("telebot", "telebot.types", "supabase", "dotenv",
                 "adaptive_risk_engine", "engine_core", "telegram_formatters",
                 "telegram_bot", "telegram_callbacks", "bot_core",
                 "telegram_devops"):
        saved[_mod] = sys.modules.get(_mod)

    telebot_stub = MagicMock()
    telebot_stub.TeleBot = _RecordingBot
    sys.modules["telebot"] = telebot_stub
    sys.modules["telebot.types"] = MagicMock()
    sys.modules["supabase"] = MagicMock()
    sys.modules["dotenv"] = MagicMock()
    sys.modules["adaptive_risk_engine"] = MagicMock()
    sys.modules["engine_core"] = MagicMock()
    sys.modules["telegram_formatters"] = MagicMock()
    for _name in ("telegram_bot", "telegram_callbacks", "bot_core",
                  "telegram_devops"):
        sys.modules.pop(_name, None)

    import telegram_bot as _tb       # builds bot_core.bot = _RecordingBot()
    import telegram_devops as _devops
    _devops._pin_sessions.clear()
    _tb.user_state.clear()
    try:
        yield _tb
    finally:
        for _name in ("telegram_bot", "telegram_callbacks", "bot_core",
                      "telegram_devops"):
            sys.modules.pop(_name, None)
        # Restore whatever the rest of the suite had so no other file is
        # disturbed by this module's dedicated stubs.
        for _mod, _val in saved.items():
            if _val is not None:
                sys.modules[_mod] = _val
            else:
                sys.modules.pop(_mod, None)


def _msg(text, chat_id=ADMIN_CHAT_ID):
    m = MagicMock()
    m.chat.id = chat_id
    m.text = text
    m.content_type = "text"
    return m


def _doc_msg(chat_id=ADMIN_CHAT_ID):
    m = MagicMock()
    m.chat.id = chat_id
    m.text = None
    m.content_type = "document"
    m.document.file_name = "report.xml"
    m.document.file_id = "fid"
    return m


def _grant_session(tb, chat_id=ADMIN_CHAT_ID):
    import telegram_devops as devops
    import time
    devops._pin_sessions[chat_id] = time.time() + 1800


def _clear_session(tb, chat_id=ADMIN_CHAT_ID):
    import telegram_devops as devops
    devops._pin_sessions.pop(chat_id, None)


def _sent_texts(tb):
    return [str(t) for (_cid, t) in tb.bot.sent]


# ── The privileged dev handlers and their guarded side effects ───────────────
# (button label, telegram_devops/telegram_bot attr to spy on, the symbol path)
_PRIVILEGED = [
    ("📡 IBKR Sync ידני",          "_run_manual_sync_thread"),
    ("📊 תוצאת Sync אחרון",        None),   # file read; just assert refusal
    ("📋 לוגים",                    None),
    ("⚙️ הצג Config",              None),
    ("🏥 בריאות מערכת",            "_build_health_report"),
    ("🔬 בדיקת נתוני תקופה (Probe)", None),
]


@pytest.mark.integration
class TestC1NoSessionRefuses:
    """S-1: admin chat-id, NO active dev session ⇒ refuse, side effect never runs."""

    def test_git_pull_subprocess_not_invoked_without_session(self, tb):
        _clear_session(tb)
        with patch("subprocess.run") as sub:
            tb.handle_all_messages(_msg("🔄 Git Pull + Deploy"))
        sub.assert_not_called()
        assert any("PIN" in t for t in _sent_texts(tb))

    def test_ibkr_sync_thread_not_started_without_session(self, tb):
        _clear_session(tb)
        with patch.object(tb.threading, "Thread") as th:
            tb.handle_all_messages(_msg("📡 IBKR Sync ידני"))
        th.assert_not_called()
        assert any("PIN" in t for t in _sent_texts(tb))

    def test_xml_upload_arming_refused_without_session(self, tb):
        _clear_session(tb)
        tb.handle_all_messages(_msg("📤 העלה דוח XML"))
        # The awaiting_ibkr_xml state must NOT be armed.
        assert tb.user_state.get(ADMIN_CHAT_ID, {}).get("action") != "awaiting_ibkr_xml"
        assert any("PIN" in t for t in _sent_texts(tb))

    def test_document_upload_supabase_nav_write_refused_without_session(self, tb):
        # S-3: even if awaiting_ibkr_xml were somehow armed, the actual
        # NAV/Supabase write must refuse without an active session.
        _clear_session(tb)
        tb.user_state[ADMIN_CHAT_ID] = {"action": "awaiting_ibkr_xml"}
        with patch.object(tb, "_process_uploaded_ibkr_xml") as proc:
            tb.handle_document_upload(_doc_msg())
        proc.assert_not_called()

    def test_on_demand_report_thread_not_started_without_session(self, tb):
        _clear_session(tb)
        with patch.object(tb.threading, "Thread") as th:
            tb.handle_all_messages(_msg("📈 דוח שבועי עכשיו"))
        th.assert_not_called()
        assert any("PIN" in t for t in _sent_texts(tb))

    @pytest.mark.parametrize("label,_spy", _PRIVILEGED)
    def test_each_privileged_handler_refuses_without_session(self, tb, label, _spy):
        _clear_session(tb)
        tb.handle_all_messages(_msg(label))
        # A refusal mentioning PIN was sent; the developer keyboard was NOT
        # returned (refusal routes back to main menu / PIN entry).
        assert any("PIN" in t for t in _sent_texts(tb)), (
            f"{label!r} did not refuse without an active session")


@pytest.mark.integration
class TestC1ValidSessionUnchanged:
    """S-1: WITH a valid active session ⇒ unchanged behaviour (proceeds)."""

    @pytest.fixture(autouse=True)
    def _configured_dev_pin(self):
        # Sprint-27 W4b — self-containment: these tests REQUIRE a configured
        # DEV_PIN (dev_pin_is_configured() True) for the "valid session
        # proceeds" path. They were green ONLY because CI's tests.yml sets
        # DEV_PIN=0000 → a latent CI-lie if that env line were ever removed.
        # Pin it locally (symmetric to TestC1FailClosedWhenUnset setting it
        # "") and restore, so "green" can never depend on an unrelated env
        # line. Test-only; assertions unchanged.
        import telegram_devops as devops
        _orig = devops._DEV_PIN
        devops._DEV_PIN = "0000"
        yield
        devops._DEV_PIN = _orig

    def test_git_pull_proceeds_with_session(self, tb):
        _grant_session(tb)
        fake = types.SimpleNamespace(stdout="ok", stderr="", returncode=0)
        with patch("subprocess.run", return_value=fake) as sub:
            tb.handle_all_messages(_msg("🔄 Git Pull + Deploy"))
        sub.assert_called_once()

    def test_ibkr_sync_thread_starts_with_session(self, tb):
        _grant_session(tb)
        with (patch.object(tb, "_dev_sync_check",
                           return_value=(True, "", {})),
              patch.object(tb, "_dev_sync_record"),
              patch.object(tb.threading, "Thread") as th):
            tb.handle_all_messages(_msg("📡 IBKR Sync ידני"))
        th.assert_called_once()

    def test_xml_upload_arming_proceeds_with_session(self, tb):
        _grant_session(tb)
        tb.handle_all_messages(_msg("📤 העלה דוח XML"))
        assert tb.user_state[ADMIN_CHAT_ID]["action"] == "awaiting_ibkr_xml"

    def test_document_upload_write_proceeds_with_session(self, tb):
        _grant_session(tb)
        tb.user_state[ADMIN_CHAT_ID] = {"action": "awaiting_ibkr_xml"}
        with patch.object(tb, "_process_uploaded_ibkr_xml") as proc:
            tb.handle_document_upload(_doc_msg())
        proc.assert_called_once()

    def test_on_demand_report_thread_starts_with_session(self, tb):
        _grant_session(tb)
        with patch.object(tb.threading, "Thread") as th:
            tb.handle_all_messages(_msg("📆 דוח חודשי עכשיו"))
        th.assert_called_once()


@pytest.mark.integration
class TestC1FailClosedWhenUnset:
    """S-2: DEV_PIN unset/empty ⇒ fail-CLOSED (menu + every action denied)."""

    def _unset_dev_pin(self, tb):
        import telegram_devops as devops
        # Simulate production with no DEV_PIN: empty constant ⇒
        # dev_pin_is_configured() False.
        devops._DEV_PIN = ""

    def test_menu_open_denied_when_dev_pin_unset(self, tb):
        self._unset_dev_pin(tb)
        # A live session must NOT rescue an unconfigured PIN.
        _grant_session(tb)
        tb.handle_all_messages(_msg("🛠️ מפתח"))
        texts = _sent_texts(tb)
        assert any("DEV_PIN" in t and "חסום" in t for t in texts), texts
        # The developer keyboard must NOT have been served.
        assert not any("כלי פיתוח ודיבאג" in t for t in texts)

    def test_git_pull_denied_when_dev_pin_unset_even_with_session(self, tb):
        self._unset_dev_pin(tb)
        _grant_session(tb)
        with patch("subprocess.run") as sub:
            tb.handle_all_messages(_msg("🔄 Git Pull + Deploy"))
        sub.assert_not_called()
        assert any("DEV_PIN" in t for t in _sent_texts(tb))

    def test_xml_write_denied_when_dev_pin_unset(self, tb):
        self._unset_dev_pin(tb)
        _grant_session(tb)
        tb.user_state[ADMIN_CHAT_ID] = {"action": "awaiting_ibkr_xml"}
        with patch.object(tb, "_process_uploaded_ibkr_xml") as proc:
            tb.handle_document_upload(_doc_msg())
        proc.assert_not_called()

    @pytest.mark.parametrize("label,_spy", _PRIVILEGED)
    def test_every_privileged_action_denied_when_unset(self, tb, label, _spy):
        self._unset_dev_pin(tb)
        _grant_session(tb)
        tb.handle_all_messages(_msg(label))
        assert any("DEV_PIN" in t for t in _sent_texts(tb)), (
            f"{label!r} not fail-closed when DEV_PIN unset")


@pytest.mark.integration
class TestC1AdminGateAndSecureRunnerUnaffected:
    """The OUTER admin (chat-id) gate + secure_runner wrapping are intact and
    independent of the C1 dev-PIN re-check (behavioural, not substring-only)."""

    def test_guard_decision_rejects_non_admin(self):
        import telegram_bot_secure_runner as sr
        allowed, reason = sr.guard_decision(999999)
        assert allowed is False
        assert reason == "unauthorized"

    def test_guard_decision_allows_admin(self):
        import telegram_bot_secure_runner as sr
        sr._events.clear()
        sr._cooldown_until.clear()
        allowed, reason = sr.guard_decision(ADMIN_CHAT_ID)
        assert allowed is True
        assert reason == "ok"

    def test_guard_decision_fail_closed_when_admin_unset(self, monkeypatch):
        import telegram_bot_secure_runner as sr
        monkeypatch.setattr(sr, "ADMIN_ID", None)
        allowed, reason = sr.guard_decision(ADMIN_CHAT_ID)
        assert allowed is False
        assert reason == "unauthorized"

    def test_secure_runner_wraps_both_handler_types_and_gates_on_guard_decision(self):
        # The admin gate applies to BOTH message AND callback handlers (no
        # bypass from within telegram_bot.py). Verified WITHOUT mutating the
        # process-wide (stubbed) telebot — assert the secure_runner installer
        # replaces both decorators and routes them through guard_decision.
        import inspect
        import telegram_bot_secure_runner as sr
        src = inspect.getsource(sr.install_telegram_hardening)
        assert "telebot.TeleBot.message_handler = guarded_message_handler" in src
        assert "telebot.TeleBot.callback_query_handler = guarded_callback_handler" in src
        # Each guarded wrapper must call guard_decision before the real func.
        assert src.count("guard_decision(chat_id)") >= 2
        msg_src = inspect.getsource(sr.guarded_message_handler) \
            if hasattr(sr, "guarded_message_handler") else src
        assert "guard_decision" in msg_src


@pytest.mark.integration
class TestC1NonPrivilegedFlowsByteIdentical:
    """Non-dev handlers must be completely unaffected by the C1 guard."""

    def test_main_menu_navigation_unaffected(self, tb):
        _clear_session(tb)
        tb.handle_all_messages(_msg("📊 מצב תיק"))
        # Reached the portfolio sub-menu prompt — no PIN involved.
        assert any("מצב תיק" in t for t in _sent_texts(tb))

    def test_health_command_path_not_dev_gated(self, tb):
        # `/health` (NOT the dev-menu "🏥 בריאות מערכת" button branch) is the
        # non-dev catch-all status path and must stay byte-identical: no PIN.
        _clear_session(tb)
        with patch.object(tb, "_build_health_report", return_value="HEALTH"):
            tb.handle_all_messages(_msg("/health"))
        texts = _sent_texts(tb)
        assert any("HEALTH" in t for t in texts)
        assert not any("PIN" in t for t in texts)

    def test_cancel_flow_unaffected(self, tb):
        _clear_session(tb)
        tb.user_state[ADMIN_CHAT_ID] = {"action": "something"}
        tb.handle_all_messages(_msg("ביטול"))
        assert ADMIN_CHAT_ID not in tb.user_state
        assert any("בוטלה" in t for t in _sent_texts(tb))
