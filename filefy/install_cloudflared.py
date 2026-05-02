"""
filefy.install_cloudflared
==========================

Install ``cloudflared`` automatically for the current operating system.

This module is the canonical implementation of the cloudflared installer
that ships with the ``filefy`` package. It is invoked automatically by
:mod:`filefy.tunnel` when ``--tunnel`` is requested but the binary is not
yet present on the system, and it is also exposed as a stand-alone
console script so users can pre-install or reinstall the binary on
demand.

Usage (console script, available after ``pip install filefy``)::

    filefy-install-cloudflared
    filefy-install-cloudflared --verbose
    filefy-install-cloudflared --reinstall
    filefy-install-cloudflared --no-package-manager

Equivalent module invocation::

    python -m filefy.install_cloudflared

Library usage::

    from filefy.install_cloudflared import ensure_cloudflared

    result = ensure_cloudflared()
    print(result.path)
"""

from __future__ import annotations

import argparse
import logging
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence


LOGGER = logging.getLogger(__name__)

GITHUB_LATEST_DOWNLOAD = (
    "https://github.com/cloudflare/cloudflared/releases/latest/download"
)

EXECUTABLE = "cloudflared.exe" if os.name == "nt" else "cloudflared"


class CloudflaredInstallError(RuntimeError):
    """Raised when cloudflared cannot be installed or verified."""


@dataclass(frozen=True)
class InstallResult:
    path: Path
    installed_now: bool
    version: Optional[str] = None


def detect_platform() -> str:
    """Return one of: linux, darwin, windows."""
    if sys.platform.startswith("linux"):
        return "linux"

    if sys.platform == "darwin":
        return "darwin"

    if sys.platform.startswith("win32"):
        return "windows"

    raise CloudflaredInstallError(f"Unsupported platform: {sys.platform}")


def detect_arch(os_name: Optional[str] = None) -> str:
    """
    Normalize CPU architecture to Cloudflare asset naming.

    Linux assets:
        amd64, 386, arm, arm64

    macOS assets:
        amd64, arm64

    Windows assets:
        amd64, 386
    """
    os_name = os_name or detect_platform()
    machine = platform.machine().lower().strip()

    if machine in {"x86_64", "amd64"}:
        return "amd64"

    if machine in {"i386", "i686", "x86"}:
        return "386"

    if machine in {"aarch64", "arm64"}:
        return "arm64"

    if os_name == "linux" and machine.startswith("arm"):
        return "arm"

    raise CloudflaredInstallError(
        f"Unsupported architecture for {os_name}: {platform.machine()}"
    )


def asset_url(os_name: str, arch: str) -> str:
    """Return the latest cloudflared asset URL for the current OS and arch."""
    if os_name == "linux":
        return f"{GITHUB_LATEST_DOWNLOAD}/cloudflared-linux-{arch}"

    if os_name == "darwin":
        if arch not in {"amd64", "arm64"}:
            raise CloudflaredInstallError(f"Unsupported macOS architecture: {arch}")
        return f"{GITHUB_LATEST_DOWNLOAD}/cloudflared-darwin-{arch}.tgz"

    if os_name == "windows":
        if arch == "arm64":
            raise CloudflaredInstallError(
                "Direct Windows ARM64 cloudflared download is not available. "
                "Use winget if it supports your device."
            )

        if arch not in {"amd64", "386"}:
            raise CloudflaredInstallError(f"Unsupported Windows architecture: {arch}")

        return f"{GITHUB_LATEST_DOWNLOAD}/cloudflared-windows-{arch}.exe"

    raise CloudflaredInstallError(f"Unsupported platform: {os_name}")


def run_command(
    args: Sequence[object],
    *,
    check: bool = True,
    verbose: bool = False,
) -> subprocess.CompletedProcess[str]:
    """
    Run command safely without shell=True.

    Raises CloudflaredInstallError on failure when check=True.
    """
    cmd = [str(arg) for arg in args]

    try:
        if verbose:
            completed = subprocess.run(cmd, text=True)
        else:
            completed = subprocess.run(
                cmd,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
    except FileNotFoundError as exc:
        raise CloudflaredInstallError(f"Command not found: {cmd[0]}") from exc

    if check and completed.returncode != 0:
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""

        raise CloudflaredInstallError(
            "Command failed:\n"
            f"  {' '.join(cmd)}\n"
            f"Exit code: {completed.returncode}\n"
            f"stdout:\n{stdout.strip()}\n"
            f"stderr:\n{stderr.strip()}"
        )

    return completed


def candidate_paths() -> Iterable[Path]:
    """Likely places where cloudflared may exist."""
    from_path = shutil.which("cloudflared")
    if from_path:
        yield Path(from_path)

    os_name = detect_platform()

    if os_name == "windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        program_files = os.environ.get("PROGRAMFILES")
        program_files_x86 = os.environ.get("PROGRAMFILES(X86)")

        if local_app_data:
            yield Path(local_app_data) / "cloudflared" / "cloudflared.exe"

        if program_files:
            yield Path(program_files) / "cloudflared" / "cloudflared.exe"
            yield Path(program_files) / "Cloudflare" / "cloudflared.exe"

        if program_files_x86:
            yield Path(program_files_x86) / "cloudflared" / "cloudflared.exe"
            yield Path(program_files_x86) / "Cloudflare" / "cloudflared.exe"

        return

    yield Path("/usr/local/bin/cloudflared")
    yield Path.home() / ".local" / "bin" / "cloudflared"

    if os_name == "darwin":
        yield Path("/opt/homebrew/bin/cloudflared")
        yield Path("/usr/local/bin/cloudflared")


def find_cloudflared() -> Optional[Path]:
    """Return cloudflared path if it exists."""
    seen: set[str] = set()

    for path in candidate_paths():
        key = str(path).lower() if os.name == "nt" else str(path)

        if key in seen:
            continue

        seen.add(key)

        if path.exists() and path.is_file():
            return path

    return None


def cloudflared_version(path: Optional[Path] = None) -> Optional[str]:
    """Return cloudflared version output, if available."""
    executable = path or find_cloudflared()

    if not executable:
        return None

    completed = run_command(
        [executable, "--version"],
        check=False,
        verbose=False,
    )

    output = f"{completed.stdout or ''}{completed.stderr or ''}".strip()
    return output or None


def is_cloudflared_installed() -> bool:
    """Return True if cloudflared is already available."""
    return find_cloudflared() is not None


def download_file(url: str, destination: Path) -> None:
    """Download a file using only the Python standard library."""
    LOGGER.info("Downloading %s", url)

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "python-cloudflared-installer/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with destination.open("wb") as file:
                shutil.copyfileobj(response, file)
    except Exception as exc:
        raise CloudflaredInstallError(f"Failed to download {url}: {exc}") from exc


def make_executable(path: Path) -> None:
    """Add executable bits to a Unix binary."""
    mode = path.stat().st_mode
    path.chmod(
        mode
        | stat.S_IXUSR
        | stat.S_IXGRP
        | stat.S_IXOTH
    )


def is_writable_directory(path: Path) -> bool:
    """Return True if path can be created and written by current user."""
    try:
        path.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(dir=path, delete=True):
            pass

        return True
    except OSError:
        return False


def warn_if_not_on_path(directory: Path) -> None:
    path_parts = os.environ.get("PATH", "").split(os.pathsep)

    if str(directory) not in path_parts:
        LOGGER.warning(
            "%s is not in PATH. Use the full cloudflared path or add this "
            "directory to PATH.",
            directory,
        )


def install_unix_binary(
    binary_path: Path,
    *,
    install_dir: Optional[Path] = None,
    use_sudo: bool = True,
    allow_user_fallback: bool = True,
    verbose: bool = False,
) -> Path:
    """
    Install a Unix binary to /usr/local/bin by default.

    If /usr/local/bin is not writable:
      - use sudo when available and enabled
      - otherwise install to ~/.local/bin
    """
    target_dir = install_dir.expanduser() if install_dir else Path("/usr/local/bin")
    target_path = target_dir / "cloudflared"

    if is_writable_directory(target_dir):
        shutil.copy2(binary_path, target_path)
        make_executable(target_path)
        return target_path

    if use_sudo and shutil.which("sudo"):
        run_command(["sudo", "mkdir", "-p", target_dir], verbose=verbose)
        run_command(
            ["sudo", "install", "-m", "0755", binary_path, target_path],
            verbose=verbose,
        )
        return target_path

    if allow_user_fallback:
        user_bin = Path.home() / ".local" / "bin"
        user_bin.mkdir(parents=True, exist_ok=True)

        target_path = user_bin / "cloudflared"

        shutil.copy2(binary_path, target_path)
        make_executable(target_path)
        warn_if_not_on_path(user_bin)

        return target_path

    raise CloudflaredInstallError(
        f"Cannot write to {target_dir}. Run as admin/root, enable sudo, "
        "or choose a writable install_dir."
    )


def extract_cloudflared_from_tgz(tgz_path: Path, work_dir: Path) -> Path:
    """Extract cloudflared binary from the macOS .tgz asset safely."""
    output_path = work_dir / "cloudflared"

    with tarfile.open(tgz_path, "r:gz") as archive:
        members = [
            member
            for member in archive.getmembers()
            if member.isfile() and Path(member.name).name == "cloudflared"
        ]

        if not members:
            raise CloudflaredInstallError(
                f"Could not find cloudflared binary inside {tgz_path}"
            )

        member = members[0]
        source = archive.extractfile(member)

        if source is None:
            raise CloudflaredInstallError(
                f"Could not extract cloudflared binary from {tgz_path}"
            )

        with source, output_path.open("wb") as destination:
            shutil.copyfileobj(source, destination)

    make_executable(output_path)
    return output_path


def install_from_github_latest(
    *,
    install_dir: Optional[Path] = None,
    use_sudo: bool = True,
    verbose: bool = False,
) -> Path:
    """Install cloudflared from the latest GitHub release asset."""
    os_name = detect_platform()
    arch = detect_arch(os_name)
    url = asset_url(os_name, arch)

    if os_name == "windows":
        return install_windows_direct(
            arch=arch,
            install_dir=install_dir,
            verbose=verbose,
        )

    with tempfile.TemporaryDirectory(prefix="cloudflared-install-") as temp_dir:
        work_dir = Path(temp_dir)
        download_path = work_dir / Path(url).name

        download_file(url, download_path)

        if os_name == "darwin":
            binary_path = extract_cloudflared_from_tgz(download_path, work_dir)
        else:
            binary_path = download_path
            make_executable(binary_path)

        return install_unix_binary(
            binary_path,
            install_dir=install_dir,
            use_sudo=use_sudo,
            verbose=verbose,
        )


def install_with_homebrew(*, verbose: bool = False) -> Optional[Path]:
    """Install cloudflared using Homebrew on macOS."""
    brew = shutil.which("brew")

    if not brew:
        return None

    LOGGER.info("Installing cloudflared with Homebrew")

    try:
        run_command([brew, "install", "cloudflared"], verbose=verbose)
    except CloudflaredInstallError as exc:
        LOGGER.warning("Homebrew installation failed: %s", exc)
        return None

    return find_cloudflared()


def install_with_winget(*, verbose: bool = False) -> Optional[Path]:
    """Install cloudflared using winget on Windows."""
    winget = shutil.which("winget")

    if not winget:
        return None

    LOGGER.info("Installing cloudflared with winget")

    command = [
        winget,
        "install",
        "--id",
        "Cloudflare.cloudflared",
        "--exact",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]

    try:
        run_command(command, verbose=verbose)
    except CloudflaredInstallError as exc:
        LOGGER.warning("winget installation failed: %s", exc)
        return None

    return find_cloudflared()


def install_windows_direct(
    *,
    arch: str,
    install_dir: Optional[Path] = None,
    verbose: bool = False,
) -> Path:
    """
    Download cloudflared.exe directly on Windows.

    Note:
        This installs to LOCALAPPDATA by default and does not modify PATH.
        For library usage, use the returned absolute path.
    """
    if arch not in {"amd64", "386"}:
        raise CloudflaredInstallError(
            f"Direct Windows installation is not available for architecture: {arch}"
        )

    url = asset_url("windows", arch)

    if install_dir:
        target_dir = install_dir.expanduser()
    else:
        local_app_data = os.environ.get(
            "LOCALAPPDATA",
            str(Path.home() / "AppData" / "Local"),
        )
        target_dir = Path(local_app_data) / "cloudflared"

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "cloudflared.exe"

    with tempfile.TemporaryDirectory(prefix="cloudflared-install-") as temp_dir:
        temp_path = Path(temp_dir) / "cloudflared.exe"
        download_file(url, temp_path)
        shutil.move(str(temp_path), str(target_path))

    LOGGER.info("Installed cloudflared to %s", target_path)

    return target_path


def install_cloudflared(
    *,
    prefer_package_manager: bool = True,
    install_dir: Optional[Path] = None,
    use_sudo: bool = True,
    verbose: bool = False,
) -> InstallResult:
    """
    Install cloudflared for the current platform.

    Platform strategy:
      - Windows: winget first, direct .exe fallback
      - macOS: Homebrew first, direct .tgz fallback
      - Linux: direct latest binary
    """
    os_name = detect_platform()
    path: Optional[Path] = None

    if os_name == "windows":
        if prefer_package_manager:
            path = install_with_winget(verbose=verbose)

        if not path:
            path = install_from_github_latest(
                install_dir=install_dir,
                use_sudo=False,
                verbose=verbose,
            )

    elif os_name == "darwin":
        if prefer_package_manager:
            path = install_with_homebrew(verbose=verbose)

        if not path:
            path = install_from_github_latest(
                install_dir=install_dir,
                use_sudo=use_sudo,
                verbose=verbose,
            )

    elif os_name == "linux":
        path = install_from_github_latest(
            install_dir=install_dir,
            use_sudo=use_sudo,
            verbose=verbose,
        )

    else:
        raise CloudflaredInstallError(f"Unsupported platform: {os_name}")

    version = cloudflared_version(path)

    if not version:
        raise CloudflaredInstallError(
            f"cloudflared was installed at {path}, but version check failed."
        )

    return InstallResult(
        path=path,
        installed_now=True,
        version=version,
    )


def ensure_cloudflared(
    *,
    reinstall: bool = False,
    prefer_package_manager: bool = True,
    install_dir: Optional[Path] = None,
    use_sudo: bool = True,
    verbose: bool = False,
) -> InstallResult:
    """
    Ensure cloudflared exists.

    If already installed and reinstall=False, no installation is performed.
    """
    if not reinstall:
        existing = find_cloudflared()

        if existing:
            return InstallResult(
                path=existing,
                installed_now=False,
                version=cloudflared_version(existing),
            )

    return install_cloudflared(
        prefer_package_manager=prefer_package_manager,
        install_dir=install_dir,
        use_sudo=use_sudo,
        verbose=verbose,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install cloudflared if it is not already installed."
    )

    parser.add_argument(
        "--reinstall",
        action="store_true",
        help="Install again even if cloudflared already exists.",
    )

    parser.add_argument(
        "--no-package-manager",
        action="store_true",
        help="Skip Homebrew/winget and use direct GitHub download.",
    )

    parser.add_argument(
        "--install-dir",
        type=Path,
        default=None,
        help="Custom install directory. Useful for Unix or direct Windows install.",
    )

    parser.add_argument(
        "--no-sudo",
        action="store_true",
        help="Do not use sudo on Linux/macOS. Falls back to ~/.local/bin if needed.",
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show installer command output.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        result = ensure_cloudflared(
            reinstall=args.reinstall,
            prefer_package_manager=not args.no_package_manager,
            install_dir=args.install_dir,
            use_sudo=not args.no_sudo,
            verbose=args.verbose,
        )
    except CloudflaredInstallError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    status = "installed" if result.installed_now else "already installed"

    print(f"cloudflared {status}: {result.path}")

    if result.version:
        print(result.version)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
