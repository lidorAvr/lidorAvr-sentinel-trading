"""
Sprint 7 #3 — verify pytest-socket actually blocks network from tests.

This is a *meta-test* — it tests the test infrastructure itself.
Without it, a future refactor could silently disable socket blocking
(e.g. by deleting the pytest_runtest_setup hook in conftest.py) and
all production tests would silently start using the network again.

The Sprint 6 CI incident (test_returns_none_when_history_empty falling
through to a real yfinance fetch) is exactly what pytest-socket
prevents — but only if the enforcement is actually active.
"""
import socket
import pytest
import pytest_socket


@pytest.mark.unit
class TestPytestSocketEnforcement:

    def test_socket_calls_raise_blocked_error(self):
        """Opening any socket from inside a test must raise SocketBlockedError.

        If this passes with no exception, pytest-socket is no longer
        active and the Sprint 6 incident class of bugs can recur.
        """
        with pytest.raises(pytest_socket.SocketBlockedError):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect(("8.8.8.8", 53))   # would talk to public DNS
            finally:
                sock.close()

    def test_creating_socket_alone_is_blocked(self):
        """Even calling socket() without connecting must be blocked.

        pytest-socket hooks the constructor, not just connect — that's
        what makes it foolproof against libraries that lazily create
        sockets at import time.
        """
        with pytest.raises(pytest_socket.SocketBlockedError):
            socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    @pytest.mark.enable_socket
    def test_marker_can_opt_in_to_socket_access(self):
        """A test marked @pytest.mark.enable_socket can use sockets.

        This is the escape hatch for genuinely-local integration tests
        (e.g. an in-process HTTP server). It must NOT be used to talk
        to public hosts — that's a code review check.
        """
        # Just creating a socket without connecting is enough to verify
        # the marker takes effect — no need to actually open a connection.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            assert sock is not None
        finally:
            sock.close()
