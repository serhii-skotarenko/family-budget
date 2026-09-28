"""Process-level shutdown behaviour of the bot with the Claude connector running."""

import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

APP = Path(__file__).with_name("connector_lifecycle_app.py")


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class BotProcess:
    """connector_lifecycle_app.py in a subprocess, its output collected line by line."""

    def __init__(self) -> None:
        self.port = free_port()
        self.popen = subprocess.Popen(
            [sys.executable, "-u", str(APP), str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.lines: list[str] = []
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        for line in self.popen.stdout:
            self.lines.append(line.rstrip("\n"))

    def wait_for(self, fragment: str, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if any(fragment in line for line in self.lines):
                return
            if self.popen.poll() is not None:
                break
            time.sleep(0.05)
        raise AssertionError(f"{fragment!r} never appeared in:\n" + "\n".join(self.lines))

    def wait_until_serving(self, timeout: float = 15.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        raise AssertionError("the connector never started listening")

    def line_index(self, fragment: str) -> int:
        return next(i for i, line in enumerate(self.lines) if fragment in line)

    def finish(self, timeout: float = 20.0) -> int:
        try:
            return self.popen.wait(timeout=timeout)
        finally:
            if self.popen.poll() is None:
                self.popen.kill()
            self._reader.join(timeout=2)


def start_bot() -> BotProcess:
    process = BotProcess()
    process.wait_for("Run polling for bot")
    process.wait_until_serving()
    return process


def test_sigterm_stops_polling_then_the_connector_then_cleans_up():
    process = start_bot()

    process.popen.send_signal(signal.SIGTERM)

    assert process.finish() == 0, "\n".join(process.lines)
    polling_stopped = process.line_index("Polling stopped")
    connector_stopped = process.line_index("Claude connector stopped")
    cleanup_finished = process.line_index("CLEANUP finished")
    assert polling_stopped < connector_stopped < cleanup_finished


def test_repeated_sigterm_during_cleanup_does_not_kill_the_process():
    process = start_bot()

    process.popen.send_signal(signal.SIGTERM)
    process.wait_for("CLEANUP started")
    process.popen.send_signal(signal.SIGTERM)

    assert process.finish() == 0, "\n".join(process.lines)
    assert any("CLEANUP finished" in line for line in process.lines)
