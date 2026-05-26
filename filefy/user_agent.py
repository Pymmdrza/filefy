"""Helpers for building Filefy network user-agent strings."""

import platform

from ._version import __version__


def _normalize_architecture(machine=None, architecture=None):
    """Return a compact architecture token for user-agent strings."""
    machine = (machine or platform.machine() or "").lower()
    architecture = architecture or platform.architecture()[0]

    if machine in {"amd64", "x86_64", "x64"}:
        return "x64"
    if machine in {"i386", "i686", "x86"}:
        return "x86"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    if "64" in str(architecture):
        return "x64"
    if "32" in str(architecture):
        return "x86"
    return machine or "unknown"


def build_filefy_user_agent(
    version=None,
    system_name=None,
    machine=None,
    architecture=None,
):
    """Build the Filefy user-agent used for outbound download requests."""
    version = version or __version__
    system_name = system_name or platform.system() or "Unknown"
    arch = _normalize_architecture(machine, architecture)
    normalized_system = system_name.lower()

    if normalized_system == "windows":
        win_arch = "Win64" if arch in {"x64", "arm64"} else "Win32"
        system_descriptor = f"Windows NT; {win_arch}; {arch}"
    elif normalized_system == "darwin":
        system_descriptor = f"macOS; {arch}"
    else:
        system_descriptor = f"{system_name}; {arch}"

    return f"FileFy v{version} ({system_descriptor})"
