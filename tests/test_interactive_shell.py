"""Wave 0 test stubs for Phase 9: Interactive Shell (SHLL-01 through SHLL-04).

All tests must fail RED before implementation — they exercise the real call path
and fail because connect() raises NotImplementedError.
"""

import os
import select
import signal
import struct
import sys
from unittest.mock import MagicMock, call, patch

import pytest

from just_akash.transport.lease_shell import LeaseShellTransport

DEPLOYMENT_FIXTURE = {
    "leases": [{
        "provider": {"hostUri": "https://provider.us-east.akash.pub:8443"},
        "status": {"services": {"web": {}}},
    }]
}


def _make_transport():
    """Return a LeaseShellTransport with pre-set _ws_url and _service so connect()
    can proceed past prepare() without a live API call."""
    t = LeaseShellTransport.__new__(LeaseShellTransport)
    # Call base __init__ minimally — set mandatory attributes
    t._ws_url = "wss://provider.us-east.akash.pub:8443/lease/1/1/1/shell"
    t._service = "web"
    t._dseq = 1
    t._provider_uri = "https://provider.us-east.akash.pub:8443"
    t._cert = None
    t._ws = None
    return t


class TestLeaseShellConnect:
    """Tests covering TTY setup, terminal dimensions, SIGINT forwarding,
    SIGWINCH resize, bidirectional I/O dispatch, terminal restoration,
    and platform/TTY guards (SHLL-01 through SHLL-04)."""

    def test_connect_raises_on_windows(self):
        t = _make_transport()
        with patch("sys.platform", "win32"), \
             patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = True
            with pytest.raises(NotImplementedError, match="Windows"):
                t.connect()

    def test_connect_raises_on_non_tty_stdin(self):
        t = _make_transport()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            with pytest.raises((RuntimeError, NotImplementedError)):
                t.connect()

    def test_connect_opens_websocket_with_tty_true_stdin_true(self):
        t = _make_transport()
        with patch("just_akash.transport.lease_shell.connect") as mock_ws, \
             patch("termios.tcgetattr", return_value=[]), \
             patch("termios.tcsetattr"), \
             patch("tty.setraw"), \
             patch("sys.stdin") as mock_stdin, \
             patch("signal.signal"), \
             patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))):
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            ws_instance = MagicMock()
            ws_instance.recv.side_effect = Exception("stop")
            mock_ws.return_value.__enter__.return_value = ws_instance
            mock_ws.return_value.__exit__.return_value = False
            with pytest.raises(Exception):
                t.connect()
            called_url = mock_ws.call_args[0][0]
            assert "tty=true" in called_url
            assert "stdin=true" in called_url

    def test_connect_sends_terminal_size_on_connect(self):
        t = _make_transport()
        with patch("just_akash.transport.lease_shell.connect") as mock_ws, \
             patch("termios.tcgetattr", return_value=[]), \
             patch("termios.tcsetattr"), \
             patch("tty.setraw"), \
             patch("sys.stdin") as mock_stdin, \
             patch("signal.signal"), \
             patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))):
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            ws_instance = MagicMock()
            ws_instance.recv.side_effect = Exception("stop")
            mock_ws.return_value.__enter__.return_value = ws_instance
            mock_ws.return_value.__exit__.return_value = False
            with pytest.raises(Exception):
                t.connect()
            # Expect ws.send called with a frame where frame[0] == 105 (RESIZE)
            sent_frames = [c.args[0] for c in ws_instance.send.call_args_list
                           if isinstance(c.args[0], (bytes, bytearray))]
            resize_frames = [f for f in sent_frames if f[0] == 105]
            assert resize_frames, "Expected at least one resize frame (code 105) sent on connect"
            rows, cols = struct.unpack(">HH", resize_frames[0][1:5])
            assert rows == 24
            assert cols == 80

    def test_connect_forwards_stdin_to_frame_104(self):
        """stdin input is forwarded as bytes([104]) + data."""
        t = _make_transport()
        stdin_data = b"hello"
        call_count = [0]

        with patch("just_akash.transport.lease_shell.connect") as mock_ws, \
             patch("termios.tcgetattr", return_value=[]), \
             patch("termios.tcsetattr"), \
             patch("tty.setraw"), \
             patch("sys.stdin") as mock_stdin, \
             patch("signal.signal"), \
             patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))), \
             patch("select.select") as mock_select, \
             patch("os.read") as mock_os_read:
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            # First select() returns stdin readable, second raises to break loop
            mock_select.side_effect = [([0], [], []), Exception("stop")]
            mock_os_read.return_value = stdin_data
            ws_instance = MagicMock()
            ws_instance.recv.side_effect = Exception("no recv")
            mock_ws.return_value.__enter__.return_value = ws_instance
            mock_ws.return_value.__exit__.return_value = False
            with pytest.raises(Exception):
                t.connect()
            stdin_frames = [c.args[0] for c in ws_instance.send.call_args_list
                            if isinstance(c.args[0], (bytes, bytearray)) and c.args[0][0] == 104]
            # Filter out the initial resize frame; check for stdin frame
            assert any(f[1:] == stdin_data for f in stdin_frames), \
                f"Expected frame 104 + b'hello'; got send calls: {ws_instance.send.call_args_list}"

    def test_connect_dispatches_frame_100_to_stdout(self):
        """Frame 100 payload is written to sys.stdout.buffer."""
        t = _make_transport()
        with patch("just_akash.transport.lease_shell.connect") as mock_ws, \
             patch("termios.tcgetattr", return_value=[]), \
             patch("termios.tcsetattr"), \
             patch("tty.setraw"), \
             patch("sys.stdin") as mock_stdin, \
             patch("signal.signal"), \
             patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))), \
             patch("select.select", return_value=([], [], [])), \
             patch("sys.stdout") as mock_stdout:
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            ws_instance = MagicMock()
            # recv returns one stdout frame then raises to break loop
            ws_instance.recv.side_effect = [bytes([100]) + b"output", Exception("stop")]
            mock_ws.return_value.__enter__.return_value = ws_instance
            mock_ws.return_value.__exit__.return_value = False
            with pytest.raises(Exception):
                t.connect()
            mock_stdout.buffer.write.assert_any_call(b"output")

    def test_connect_dispatches_frame_101_to_stderr(self):
        """Frame 101 payload is written to sys.stderr.buffer."""
        t = _make_transport()
        with patch("just_akash.transport.lease_shell.connect") as mock_ws, \
             patch("termios.tcgetattr", return_value=[]), \
             patch("termios.tcsetattr"), \
             patch("tty.setraw"), \
             patch("sys.stdin") as mock_stdin, \
             patch("signal.signal"), \
             patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))), \
             patch("select.select", return_value=([], [], [])), \
             patch("sys.stderr") as mock_stderr:
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            ws_instance = MagicMock()
            ws_instance.recv.side_effect = [bytes([101]) + b"err", Exception("stop")]
            mock_ws.return_value.__enter__.return_value = ws_instance
            mock_ws.return_value.__exit__.return_value = False
            with pytest.raises(Exception):
                t.connect()
            mock_stderr.buffer.write.assert_any_call(b"err")

    def test_connect_exits_on_frame_102(self):
        """connect() returns cleanly when frame code 102 (exit) is received."""
        t = _make_transport()
        with patch("just_akash.transport.lease_shell.connect") as mock_ws, \
             patch("termios.tcgetattr", return_value=[]), \
             patch("termios.tcsetattr"), \
             patch("tty.setraw"), \
             patch("sys.stdin") as mock_stdin, \
             patch("signal.signal"), \
             patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))), \
             patch("select.select", return_value=([], [], [])):
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            ws_instance = MagicMock()
            ws_instance.recv.return_value = bytes([102])  # exit frame
            mock_ws.return_value.__enter__.return_value = ws_instance
            mock_ws.return_value.__exit__.return_value = False
            # Should return without raising
            t.connect()

    def test_sigint_sends_frame_104_with_0x03(self):
        """SIGINT handler sends bytes([104, 0x03]) via ws.send()."""
        t = _make_transport()
        captured_handler = [None]

        def capture_signal(sig, handler):
            if sig == signal.SIGINT:
                captured_handler[0] = handler
            return signal.SIG_DFL

        with patch("just_akash.transport.lease_shell.connect") as mock_ws, \
             patch("termios.tcgetattr", return_value=[]), \
             patch("termios.tcsetattr"), \
             patch("tty.setraw"), \
             patch("sys.stdin") as mock_stdin, \
             patch("signal.signal", side_effect=capture_signal), \
             patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))), \
             patch("select.select", return_value=([], [], [])):
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            ws_instance = MagicMock()
            # recv returns exit frame so connect() finishes after handler setup
            ws_instance.recv.return_value = bytes([102])
            mock_ws.return_value.__enter__.return_value = ws_instance
            mock_ws.return_value.__exit__.return_value = False
            t.connect()

        assert captured_handler[0] is not None, "SIGINT handler was never registered"
        ws_instance.send.reset_mock()
        captured_handler[0](signal.SIGINT, None)
        ws_instance.send.assert_called_with(bytes([104, 0x03]))

    def test_sigint_does_not_raise_keyboardinterrupt(self):
        """connect() completes without KeyboardInterrupt propagating to caller."""
        t = _make_transport()
        with patch("just_akash.transport.lease_shell.connect") as mock_ws, \
             patch("termios.tcgetattr", return_value=[]), \
             patch("termios.tcsetattr"), \
             patch("tty.setraw"), \
             patch("sys.stdin") as mock_stdin, \
             patch("signal.signal"), \
             patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))), \
             patch("select.select", return_value=([], [], [])):
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            ws_instance = MagicMock()
            ws_instance.recv.return_value = bytes([102])
            mock_ws.return_value.__enter__.return_value = ws_instance
            mock_ws.return_value.__exit__.return_value = False
            # Must not raise KeyboardInterrupt
            t.connect()

    def test_sigwinch_sends_frame_105_with_new_size(self):
        """SIGWINCH handler sends frame where frame[0]==105 and size matches new terminal."""
        t = _make_transport()
        captured_handler = [None]

        def capture_signal(sig, handler):
            if sig == signal.SIGWINCH:
                captured_handler[0] = handler
            return signal.SIG_DFL

        with patch("just_akash.transport.lease_shell.connect") as mock_ws, \
             patch("termios.tcgetattr", return_value=[]), \
             patch("termios.tcsetattr"), \
             patch("tty.setraw"), \
             patch("sys.stdin") as mock_stdin, \
             patch("signal.signal", side_effect=capture_signal), \
             patch("os.get_terminal_size", return_value=os.terminal_size((100, 40))), \
             patch("select.select", return_value=([], [], [])):
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            ws_instance = MagicMock()
            ws_instance.recv.return_value = bytes([102])
            mock_ws.return_value.__enter__.return_value = ws_instance
            mock_ws.return_value.__exit__.return_value = False
            t.connect()

        assert captured_handler[0] is not None, "SIGWINCH handler was never registered"
        ws_instance.send.reset_mock()
        captured_handler[0](signal.SIGWINCH, None)
        sent = [c.args[0] for c in ws_instance.send.call_args_list
                if isinstance(c.args[0], (bytes, bytearray)) and c.args[0][0] == 105]
        assert sent, "SIGWINCH handler did not send a resize frame (code 105)"
        rows, cols = struct.unpack(">HH", sent[0][1:5])
        assert rows == 40
        assert cols == 100

    def test_terminal_restored_on_normal_exit(self):
        """termios.tcsetattr() is called after connect() completes normally."""
        t = _make_transport()
        with patch("just_akash.transport.lease_shell.connect") as mock_ws, \
             patch("termios.tcgetattr", return_value=[]) as mock_tcgetattr, \
             patch("termios.tcsetattr") as mock_tcsetattr, \
             patch("tty.setraw"), \
             patch("sys.stdin") as mock_stdin, \
             patch("signal.signal"), \
             patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))), \
             patch("select.select", return_value=([], [], [])):
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            ws_instance = MagicMock()
            ws_instance.recv.return_value = bytes([102])
            mock_ws.return_value.__enter__.return_value = ws_instance
            mock_ws.return_value.__exit__.return_value = False
            t.connect()
        assert mock_tcsetattr.called, "termios.tcsetattr() was not called — terminal not restored"

    def test_terminal_restored_on_exception(self):
        """termios.tcsetattr() is called even when _run_interactive_session raises RuntimeError."""
        t = _make_transport()
        with patch("just_akash.transport.lease_shell.connect") as mock_ws, \
             patch("termios.tcgetattr", return_value=[]), \
             patch("termios.tcsetattr") as mock_tcsetattr, \
             patch("tty.setraw"), \
             patch("sys.stdin") as mock_stdin, \
             patch("signal.signal"), \
             patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))):
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            ws_instance = MagicMock()
            # Simulate a crash mid-session
            ws_instance.recv.side_effect = RuntimeError("crash")
            mock_ws.return_value.__enter__.return_value = ws_instance
            mock_ws.return_value.__exit__.return_value = False
            with pytest.raises((RuntimeError, NotImplementedError)):
                t.connect()
        assert mock_tcsetattr.called, "termios.tcsetattr() was not called after exception — finally block missing"

    def test_terminal_restored_on_connection_close(self):
        """termios.tcsetattr() is called after ConnectionClosedOK during the session."""
        from websockets.exceptions import ConnectionClosedOK
        t = _make_transport()
        with patch("just_akash.transport.lease_shell.connect") as mock_ws, \
             patch("termios.tcgetattr", return_value=[]), \
             patch("termios.tcsetattr") as mock_tcsetattr, \
             patch("tty.setraw"), \
             patch("sys.stdin") as mock_stdin, \
             patch("signal.signal"), \
             patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))):
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            ws_instance = MagicMock()
            # Simulate ConnectionClosedOK during recv
            rcvd = MagicMock()
            rcvd.code = 1000
            rcvd.reason = ""
            ws_instance.recv.side_effect = ConnectionClosedOK(rcvd, None)
            mock_ws.return_value.__enter__.return_value = ws_instance
            mock_ws.return_value.__exit__.return_value = False
            t.connect()  # Must return cleanly (not raise)
        assert mock_tcsetattr.called, "termios.tcsetattr() was not called after ConnectionClosedOK"
