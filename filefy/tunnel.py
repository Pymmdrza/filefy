"""
Cloudflare Quick Tunnel integration for Filefy.

This module spawns the official ``cloudflared`` binary (when available on
``PATH``) to expose the locally-running Filefy server on a free
``*.trycloudflare.com`` URL. The implementation has no Python dependency
on Cloudflare libraries: ``cloudflared`` is treated as an *optional*
runtime tool that the user can install separately. If it is not present
we surface a clear, actionable error message instead of crashing.

The public class is :class:`CloudflareTunnel`. Typical use::

    tunnel = CloudflareTunnel(local_url="http://127.0.0.1:5000")
    tunnel.start()
    public_url = tunnel.wait_for_url(timeout=30)
    if public_url:
        print(f"Public URL: {public_url}")
    ...
    tunnel.stop()
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Matches the `https://<subdomain>.trycloudflare.com` URL that the
# `cloudflared` quick-tunnel command prints to its log output once the
# tunnel is established.
_TUNNEL_URL_RE = re.compile(
    r"https://[A-Za-z0-9._-]+\.trycloudflare\.com",
)


class TunnelError(RuntimeError):
    """Raised when the Cloudflare tunnel cannot be started."""


class CloudflareTunnel:
    """Manage a ``cloudflared`` quick-tunnel subprocess.

    Parameters
    ----------
    local_url:
        The fully-qualified local URL to expose (for example
        ``http://127.0.0.1:5000``). Must include the scheme.
    binary:
        Optional override for the ``cloudflared`` binary to invoke.
        When not given, the executable is looked up on ``PATH``.
    """

    def __init__(self, local_url: str, binary: Optional[str] = None) -> None:
        self.local_url = local_url
        self.binary = binary or shutil.which("cloudflared")
        self._process: Optional[subprocess.Popen[str]] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._url_event = threading.Event()
        self._public_url: Optional[str] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def public_url(self) -> Optional[str]:
        """Return the discovered public URL, or ``None`` if not ready."""
        with self._lock:
            return self._public_url

    @property
    def is_running(self) -> bool:
        """Return ``True`` while the underlying process is alive."""
        proc = self._process
        return proc is not None and proc.poll() is None

    def start(self) -> None:
        """Launch the ``cloudflared`` subprocess.

        Raises :class:`TunnelError` if the binary cannot be found or the
        subprocess fails to start.
        """
        if self.is_running:
            return

        if not self.binary:
            raise TunnelError(
                "The 'cloudflared' binary was not found on PATH. Install it "
                "from https://github.com/cloudflare/cloudflared and try again."
            )

        cmd = [
            self.binary,
            "tunnel",
            "--no-autoupdate",
            "--url",
            self.local_url,
        ]
        logger.info("Starting Cloudflare tunnel: %s", " ".join(cmd))
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            raise TunnelError(f"Failed to start cloudflared: {exc}") from exc

        self._url_event.clear()
        self._reader_thread = threading.Thread(
            target=self._consume_output,
            name="cloudflared-reader",
            daemon=True,
        )
        self._reader_thread.start()

    def wait_for_url(self, timeout: float = 30.0) -> Optional[str]:
        """Block until the public URL is detected or ``timeout`` elapses."""
        if self._url_event.wait(timeout=timeout):
            return self.public_url
        return None

    def stop(self, timeout: float = 5.0) -> None:
        """Terminate the tunnel subprocess if it is still running."""
        proc = self._process
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=timeout)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Error terminating cloudflared")
        self._process = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _consume_output(self) -> None:
        """Read cloudflared output and capture the public URL."""
        proc = self._process
        if proc is None or proc.stdout is None:
            return
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                logger.debug("cloudflared: %s", line)
                if not self._url_event.is_set():
                    match = _TUNNEL_URL_RE.search(line)
                    if match:
                        with self._lock:
                            self._public_url = match.group(0)
                        self._url_event.set()
        except Exception:  # pragma: no cover - defensive
            logger.exception("Error reading cloudflared output")
        finally:
            # Make sure waiters wake up even if the process exits before
            # producing a URL (for example on a network failure).
            self._url_event.set()


def extract_tunnel_url(text: str) -> Optional[str]:
    """Return the first ``trycloudflare.com`` URL contained in ``text``.

    Exposed at module level so unit tests can exercise the parser without
    starting an actual tunnel subprocess.
    """
    match = _TUNNEL_URL_RE.search(text or "")
    return match.group(0) if match else None
