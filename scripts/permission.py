#!/usr/bin/env python3
"""
Permission Management Module for Filefy Application.

This module provides utilities for checking and setting file permissions
across different operating systems (Windows, Linux, macOS).

Features:
- Check file/directory read, write, execute permissions
- Set permissions (where supported)
- Cross-platform compatibility
- Permission validation for application directories
"""

import os
import stat
import platform
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Get base directory
BASE_DIR = Path(__file__).resolve().parent.parent


class PermissionError(Exception):
    """Custom exception for permission-related errors."""
    pass


class PermissionManager:
    """
    Manages file and directory permissions across different operating systems.
    """

    def __init__(self, base_path: Optional[Path] = None):
        """
        Initialize the PermissionManager.

        Args:
            base_path: Base path for permission operations (default: project root)
        """
        self.base_path = base_path or BASE_DIR
        self.os_type = platform.system().lower()

    # -------------------------------------------------------------------------
    # Permission Checking
    # -------------------------------------------------------------------------

    def check_readable(self, path: Union[str, Path]) -> bool:
        """
        Check if a file or directory is readable.

        Args:
            path: Path to check

        Returns:
            True if readable, False otherwise
        """
        path = Path(path)
        return path.exists() and os.access(path, os.R_OK)

    def check_writable(self, path: Union[str, Path]) -> bool:
        """
        Check if a file or directory is writable.

        Args:
            path: Path to check

        Returns:
            True if writable, False otherwise
        """
        path = Path(path)
        return path.exists() and os.access(path, os.W_OK)

    def check_executable(self, path: Union[str, Path]) -> bool:
        """
        Check if a file is executable.

        Args:
            path: Path to check

        Returns:
            True if executable, False otherwise
        """
        path = Path(path)
        return path.exists() and os.access(path, os.X_OK)

    def get_permissions(self, path: Union[str, Path]) -> Dict[str, bool]:
        """
        Get all permissions for a file or directory.

        Args:
            path: Path to check

        Returns:
            Dictionary with read, write, execute permissions
        """
        path = Path(path)

        if not path.exists():
            return {"exists": False, "read": False, "write": False, "execute": False}

        return {
            "exists": True,
            "read": os.access(path, os.R_OK),
            "write": os.access(path, os.W_OK),
            "execute": os.access(path, os.X_OK),
        }

    def get_permission_string(self, path: Union[str, Path]) -> str:
        """
        Get permission string in Unix format (e.g., 'rwx').

        Args:
            path: Path to check

        Returns:
            Permission string like 'rwx', 'rw-', etc.
        """
        perms = self.get_permissions(path)
        if not perms["exists"]:
            return "---"

        result = ""
        result += "r" if perms["read"] else "-"
        result += "w" if perms["write"] else "-"
        result += "x" if perms["execute"] else "-"
        return result

    def get_numeric_permissions(self, path: Union[str, Path]) -> Optional[str]:
        """
        Get numeric permission mode (Unix-style, e.g., '755').

        Args:
            path: Path to check

        Returns:
            Numeric permission string or None if path doesn't exist
        """
        path = Path(path)

        if not path.exists():
            return None

        try:
            mode = os.stat(path).st_mode
            return oct(mode)[-3:]
        except OSError:
            return None

    # -------------------------------------------------------------------------
    # Permission Setting
    # -------------------------------------------------------------------------

    def set_permissions(
        self,
        path: Union[str, Path],
        mode: int,
        recursive: bool = False
    ) -> Tuple[bool, str]:
        """
        Set permissions on a file or directory.

        Args:
            path: Path to modify
            mode: Permission mode (e.g., 0o755)
            recursive: Apply recursively to directories

        Returns:
            Tuple of (success, message)
        """
        path = Path(path)

        if not path.exists():
            return False, f"Path does not exist: {path}"

        try:
            if recursive and path.is_dir():
                for item in path.rglob("*"):
                    os.chmod(item, mode)
                os.chmod(path, mode)
            else:
                os.chmod(path, mode)

            return True, f"Permissions set to {oct(mode)} for {path}"
        except PermissionError as e:
            return False, f"Permission denied: {e}"
        except OSError as e:
            return False, f"Error setting permissions: {e}"

    def make_readable(self, path: Union[str, Path]) -> Tuple[bool, str]:
        """Make a file readable by the current user."""
        path = Path(path)

        if not path.exists():
            return False, f"Path does not exist: {path}"

        try:
            current_mode = os.stat(path).st_mode
            new_mode = current_mode | stat.S_IRUSR
            os.chmod(path, new_mode)
            return True, f"Made readable: {path}"
        except (PermissionError, OSError) as e:
            return False, f"Error: {e}"

    def make_writable(self, path: Union[str, Path]) -> Tuple[bool, str]:
        """Make a file writable by the current user."""
        path = Path(path)

        if not path.exists():
            return False, f"Path does not exist: {path}"

        try:
            current_mode = os.stat(path).st_mode
            new_mode = current_mode | stat.S_IWUSR
            os.chmod(path, new_mode)
            return True, f"Made writable: {path}"
        except (PermissionError, OSError) as e:
            return False, f"Error: {e}"

    def make_executable(self, path: Union[str, Path]) -> Tuple[bool, str]:
        """Make a file executable by the current user."""
        path = Path(path)

        if not path.exists():
            return False, f"Path does not exist: {path}"

        try:
            current_mode = os.stat(path).st_mode
            new_mode = current_mode | stat.S_IXUSR
            os.chmod(path, new_mode)
            return True, f"Made executable: {path}"
        except (PermissionError, OSError) as e:
            return False, f"Error: {e}"

    # -------------------------------------------------------------------------
    # Application-Specific Checks
    # -------------------------------------------------------------------------

    def check_app_directories(self) -> Dict[str, Dict[str, bool]]:
        """
        Check permissions for all important application directories.

        Returns:
            Dictionary mapping directory names to their permissions
        """
        directories = {
            "root": self.base_path,
            "config": self.base_path / "config",
            "filefy": self.base_path / "filefy",
            "scripts": self.base_path / "scripts",
            "uploads": self.base_path / "uploads",
            "logs": self.base_path / "logs",
            "templates": self.base_path / "filefy" / "templates",
            "static": self.base_path / "filefy" / "static",
        }

        result = {}
        for name, path in directories.items():
            result[name] = self.get_permissions(path)
            result[name]["path"] = str(path)

        return result

    def ensure_app_directories(self) -> List[Tuple[str, bool, str]]:
        """
        Ensure all required application directories exist and are writable.

        Returns:
            List of (directory_name, success, message) tuples
        """
        required_dirs = [
            self.base_path / "uploads",
            self.base_path / "logs",
        ]

        results = []
        for dir_path in required_dirs:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)

                # Check if writable
                if os.access(dir_path, os.W_OK):
                    results.append((str(dir_path), True, "Directory ready"))
                else:
                    results.append((str(dir_path), False, "Directory not writable"))
            except PermissionError as e:
                results.append((str(dir_path), False, f"Permission denied: {e}"))
            except OSError as e:
                results.append((str(dir_path), False, f"Error: {e}"))

        return results

    def validate_config_files(self) -> List[Tuple[str, bool, str]]:
        """
        Validate that all configuration files are readable.

        Returns:
            List of (filename, success, message) tuples
        """
        config_files = [
            "config.json",
            "settings.json",
            "security.json",
            "details.json",
            "build.json",
        ]

        config_dir = self.base_path / "config"
        results = []

        for filename in config_files:
            filepath = config_dir / filename
            if not filepath.exists():
                results.append((filename, False, "File does not exist"))
            elif not os.access(filepath, os.R_OK):
                results.append((filename, False, "File not readable"))
            else:
                results.append((filename, True, "OK"))

        return results

    # -------------------------------------------------------------------------
    # Windows-Specific Methods
    # -------------------------------------------------------------------------

    def get_windows_acl_info(self, path: Union[str, Path]) -> Optional[Dict[str, any]]:
        """
        Get Windows ACL information for a path.
        Requires pywin32 package on Windows.

        Args:
            path: Path to check

        Returns:
            Dictionary with ACL info or None if not on Windows
        """
        if self.os_type != "windows":
            return None

        try:
            import win32security
            import ntsecuritycon

            path = str(Path(path))
            sd = win32security.GetFileSecurity(
                path, win32security.OWNER_SECURITY_INFORMATION
            )
            owner_sid = sd.GetSecurityDescriptorOwner()
            owner_name, domain, type_ = win32security.LookupAccountSid(None, owner_sid)

            return {
                "owner": owner_name,
                "domain": domain,
            }
        except ImportError:
            logger.warning("pywin32 not installed, cannot get ACL info")
            return None
        except Exception as e:
            logger.error(f"Error getting ACL info: {e}")
            return None


# Convenience functions
def check_permissions(path: Union[str, Path]) -> Dict[str, bool]:
    """Check permissions for a path."""
    manager = PermissionManager()
    return manager.get_permissions(path)


def ensure_directories() -> List[Tuple[str, bool, str]]:
    """Ensure all application directories exist."""
    manager = PermissionManager()
    return manager.ensure_app_directories()


def validate_config() -> List[Tuple[str, bool, str]]:
    """Validate configuration file permissions."""
    manager = PermissionManager()
    return manager.validate_config_files()


def get_app_permission_report() -> Dict[str, any]:
    """
    Generate a full permission report for the application.

    Returns:
        Dictionary containing all permission information
    """
    manager = PermissionManager()

    return {
        "os": platform.system(),
        "base_path": str(manager.base_path),
        "directories": manager.check_app_directories(),
        "config_files": manager.validate_config_files(),
        "directory_setup": manager.ensure_app_directories(),
    }


def main():
    """Main function for running permission checks."""
    print("=" * 60)
    print("Filefy Permission Check Report")
    print("=" * 60)
    print()

    manager = PermissionManager()

    # Check app directories
    print("Directory Permissions:")
    print("-" * 40)
    dirs = manager.check_app_directories()
    for name, info in dirs.items():
        status = manager.get_permission_string(info.get("path", ""))
        exists = "✓" if info.get("exists") else "✗"
        print(f"  {name:12} [{exists}] {status} - {info.get('path', 'N/A')}")

    print()

    # Validate config files
    print("Configuration Files:")
    print("-" * 40)
    configs = manager.validate_config_files()
    for filename, success, message in configs:
        status = "✓" if success else "✗"
        print(f"  {filename:20} [{status}] {message}")

    print()

    # Ensure directories
    print("Ensuring Required Directories:")
    print("-" * 40)
    setup = manager.ensure_app_directories()
    for path, success, message in setup:
        status = "✓" if success else "✗"
        print(f"  [{status}] {path}: {message}")

    print()
    print("=" * 60)
    print("Permission check complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
