"""test_smoke.py — Integration smoke tests.

Starts the real server in a subprocess on a random free port and exercises
the HTTP surface end-to-end. No network calls to Yahoo Finance are made
because the dashboard cache starts empty and /health does not trigger a fetch.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import unittest
import urllib.request


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


class TestServerSmoke(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.port = _free_port()
        env = os.environ.copy()
        env["PORT"] = str(cls.port)
        env["PYTHONPATH"] = os.path.dirname(os.path.abspath(__file__))
        cls.proc = subprocess.Popen(
            [sys.executable, "server.py"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _wait_for_port(cls.port):
            cls.proc.kill()
            raise RuntimeError(f"Server did not start on port {cls.port} within 8s")

    @classmethod
    def tearDownClass(cls):
        cls.proc.send_signal(signal.SIGTERM)
        try:
            cls.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.proc.kill()

    def _get(self, path: str) -> tuple[int, bytes]:
        url = f"http://127.0.0.1:{self.port}{path}"
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def test_health_returns_200(self):
        code, _ = self._get("/health")
        self.assertEqual(code, 200)

    def test_health_payload_has_status_ok(self):
        _, body = self._get("/health")
        data = json.loads(body)
        self.assertEqual(data["status"], "ok")

    def test_health_payload_has_uptime(self):
        _, body = self._get("/health")
        data = json.loads(body)
        self.assertIn("uptime_seconds", data)
        self.assertIsInstance(data["uptime_seconds"], (int, float))
        self.assertGreaterEqual(data["uptime_seconds"], 0)

    def test_root_serves_html(self):
        code, body = self._get("/")
        self.assertEqual(code, 200)
        self.assertIn(b"<html", body.lower())

    def test_unknown_path_returns_404(self):
        code, _ = self._get("/does-not-exist-xyz")
        self.assertEqual(code, 404)

    def test_rate_limit_allows_normal_requests(self):
        """Rapid health pings below rate-limit threshold should all succeed."""
        for _ in range(5):
            code, _ = self._get("/health")
            self.assertEqual(code, 200)


if __name__ == "__main__":
    unittest.main()
