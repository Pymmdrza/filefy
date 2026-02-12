#!/usr/bin/env python3
"""
System Utilities Module for Filefy Application.

This module provides cross-platform system utilities including:
- OS detection and information
- Path utilities
- Process management
- System resource monitoring

Features:
- Cross-platform compatibility (Windows, Linux, macOS)
- Resource usage monitoring (CPU, memory, disk)
- Safe process management
"""

import os
import sys
import platform
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import logging
import shutil

# Configure logging
logger = logging.getLogger(__name__)

# Get base directory
BASE_DIR = Path(__file__).resolve().parent.parent


class SystemInfo:
    """Provides system information utilities."""
    
    @staticmethod
    def get_os_info() -> Dict[str, str]:
        """
        Get operating system information.
        
        Returns:
            Dictionary with OS details
        """
        return {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "architecture": platform.architecture()[0],
        }
    
    @staticmethod
    def get_python_info() -> Dict[str, Any]:
        """
        Get Python environment information.
        
        Returns:
            Dictionary with Python details
        """
        return {
            "version": sys.version,
            "version_info": {
                "major": sys.version_info.major,
                "minor": sys.version_info.minor,
                "micro": sys.version_info.micro,
            },
            "executable": sys.executable,
            "prefix": sys.prefix,
            "base_prefix": sys.base_prefix,
            "is_virtual_env": sys.prefix != sys.base_prefix,
            "platform": sys.platform,
        }
    
    @staticmethod
    def is_windows() -> bool:
        """Check if running on Windows."""
        return platform.system().lower() == "windows"
    
    @staticmethod
    def is_linux() -> bool:
        """Check if running on Linux."""
        return platform.system().lower() == "linux"
    
    @staticmethod
    def is_macos() -> bool:
        """Check if running on macOS."""
        return platform.system().lower() == "darwin"
    
    @staticmethod
    def is_admin() -> bool:
        """
        Check if the current process has administrator/root privileges.
        
        Returns:
            True if running with elevated privileges
        """
        try:
            if platform.system().lower() == "windows":
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            else:
                return os.geteuid() == 0
        except Exception:
            return False


class DiskUtils:
    """Disk and storage utilities."""
    
    @staticmethod
    def get_disk_usage(path: str = "/") -> Dict[str, Any]:
        """
        Get disk usage information for a path.
        
        Args:
            path: Path to check disk usage for
            
        Returns:
            Dictionary with disk usage information
        """
        try:
            usage = shutil.disk_usage(path)
            return {
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent_used": round((usage.used / usage.total) * 100, 2),
                "total_gb": round(usage.total / (1024 ** 3), 2),
                "used_gb": round(usage.used / (1024 ** 3), 2),
                "free_gb": round(usage.free / (1024 ** 3), 2),
            }
        except Exception as e:
            logger.error(f"Error getting disk usage: {e}")
            return {}
    
    @staticmethod
    def get_all_drives() -> List[Dict[str, Any]]:
        """
        Get information about all available drives/mount points.
        
        Returns:
            List of drive information dictionaries
        """
        drives = []
        
        if SystemInfo.is_windows():
            # Windows: Check common drive letters
            import string
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    usage = DiskUtils.get_disk_usage(drive)
                    if usage:
                        usage["path"] = drive
                        drives.append(usage)
        else:
            # Unix-like: Read from /proc/mounts or use df
            try:
                result = subprocess.run(
                    ["df", "-P"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                lines = result.stdout.strip().split("\n")[1:]  # Skip header
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 6:
                        mount_point = parts[5]
                        if mount_point.startswith("/"):
                            usage = DiskUtils.get_disk_usage(mount_point)
                            if usage:
                                usage["path"] = mount_point
                                usage["filesystem"] = parts[0]
                                drives.append(usage)
            except Exception as e:
                logger.error(f"Error getting drives: {e}")
                # Fallback to root
                usage = DiskUtils.get_disk_usage("/")
                if usage:
                    usage["path"] = "/"
                    drives.append(usage)
        
        return drives


class ProcessUtils:
    """Process management utilities."""
    
    @staticmethod
    def run_command(
        command: List[str],
        cwd: Optional[str] = None,
        timeout: int = 30,
        capture_output: bool = True
    ) -> Tuple[int, str, str]:
        """
        Run a shell command safely.
        
        Args:
            command: Command and arguments as a list
            cwd: Working directory
            timeout: Command timeout in seconds
            capture_output: Whether to capture stdout/stderr
            
        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=capture_output,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout or "", result.stderr or ""
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except FileNotFoundError:
            return -1, "", f"Command not found: {command[0]}"
        except Exception as e:
            return -1, "", str(e)
    
    @staticmethod
    def get_process_memory() -> Dict[str, Any]:
        """
        Get memory usage of the current process.
        
        Returns:
            Dictionary with memory information
        """
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            return {
                "max_rss_kb": usage.ru_maxrss,
                "max_rss_mb": round(usage.ru_maxrss / 1024, 2),
            }
        except ImportError:
            # Windows doesn't have resource module
            try:
                import psutil
                process = psutil.Process(os.getpid())
                mem_info = process.memory_info()
                return {
                    "rss_bytes": mem_info.rss,
                    "rss_mb": round(mem_info.rss / (1024 ** 2), 2),
                    "vms_bytes": mem_info.vms,
                    "vms_mb": round(mem_info.vms / (1024 ** 2), 2),
                }
            except ImportError:
                return {"error": "psutil not installed"}
        except Exception as e:
            return {"error": str(e)}


class PathUtils:
    """Path manipulation utilities."""
    
    @staticmethod
    def normalize_path(path: str) -> str:
        """
        Normalize a path for the current OS.
        
        Args:
            path: Path to normalize
            
        Returns:
            Normalized path string
        """
        # Expand user directory
        if path.startswith("~"):
            path = os.path.expanduser(path)
        
        # Convert to absolute path
        path = os.path.abspath(path)
        
        # Normalize separators
        return str(Path(path))
    
    @staticmethod
    def ensure_directory(path: str) -> Tuple[bool, str]:
        """
        Ensure a directory exists, creating it if necessary.
        
        Args:
            path: Directory path
            
        Returns:
            Tuple of (success, message)
        """
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return True, f"Directory ready: {path}"
        except PermissionError:
            return False, f"Permission denied: {path}"
        except Exception as e:
            return False, f"Error: {e}"
    
    @staticmethod
    def get_home_directory() -> str:
        """Get the user's home directory."""
        return str(Path.home())
    
    @staticmethod
    def get_temp_directory() -> str:
        """Get the system temporary directory."""
        import tempfile
        return tempfile.gettempdir()
    
    @staticmethod
    def format_size(size_bytes: int) -> str:
        """
        Format a size in bytes to human-readable format.
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Formatted size string
        """
        for unit in ["B", "KB", "MB", "GB", "TB", "PB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} EB"


def get_system_report() -> Dict[str, Any]:
    """
    Generate a comprehensive system report.
    
    Returns:
        Dictionary containing all system information
    """
    return {
        "os": SystemInfo.get_os_info(),
        "python": SystemInfo.get_python_info(),
        "is_admin": SystemInfo.is_admin(),
        "disk": DiskUtils.get_all_drives(),
        "process_memory": ProcessUtils.get_process_memory(),
        "home_directory": PathUtils.get_home_directory(),
        "temp_directory": PathUtils.get_temp_directory(),
    }


def main():
    """Main function for running system checks."""
    print("=" * 60)
    print("Filefy System Information Report")
    print("=" * 60)
    print()
    
    # OS Info
    print("Operating System:")
    print("-" * 40)
    os_info = SystemInfo.get_os_info()
    for key, value in os_info.items():
        print(f"  {key}: {value}")
    print()
    
    # Python Info
    print("Python Environment:")
    print("-" * 40)
    py_info = SystemInfo.get_python_info()
    print(f"  Version: {py_info['version_info']['major']}.{py_info['version_info']['minor']}.{py_info['version_info']['micro']}")
    print(f"  Executable: {py_info['executable']}")
    print(f"  Virtual Env: {py_info['is_virtual_env']}")
    print()
    
    # Admin Status
    print("Privileges:")
    print("-" * 40)
    print(f"  Administrator/Root: {SystemInfo.is_admin()}")
    print()
    
    # Disk Info
    print("Disk Information:")
    print("-" * 40)
    drives = DiskUtils.get_all_drives()
    for drive in drives[:5]:  # Show first 5 drives
        print(f"  {drive.get('path', 'Unknown')}:")
        print(f"    Total: {drive.get('total_gb', 0)} GB")
        print(f"    Used: {drive.get('used_gb', 0)} GB ({drive.get('percent_used', 0)}%)")
        print(f"    Free: {drive.get('free_gb', 0)} GB")
    print()
    
    print("=" * 60)
    print("System check complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()

