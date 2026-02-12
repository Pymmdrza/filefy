"""
Filefy Scripts Package.

This package contains utility scripts for the Filefy application:
- network.py: Network utilities (IP detection, port checking, firewall)
- permission.py: File permission management
- setup.py: Application setup and initialization
- logger.py: Logging configuration and utilities
- system.py: System information and cross-platform utilities
"""

from .network import (
    get_local_ip,
    get_public_ip,
    get_all_ips,
    is_port_open,
    scan_ports,
    open_port_on_firewall,
    start_tcp_listener,
)

from .permission import (
    PermissionManager,
    check_permissions,
    ensure_directories,
    validate_config,
    get_app_permission_report,
)

from .logger import (
    setup_logging,
    get_logger,
    LoggerAdapter,
    create_request_logger,
    ColoredFormatter,
    JSONFormatter,
)

from .system import (
    SystemInfo,
    DiskUtils,
    ProcessUtils,
    PathUtils,
    get_system_report,
)

__all__ = [
    # Network utilities
    "get_local_ip",
    "get_public_ip",
    "get_all_ips",
    "is_port_open",
    "scan_ports",
    "open_port_on_firewall",
    "start_tcp_listener",
    # Permission utilities
    "PermissionManager",
    "check_permissions",
    "ensure_directories",
    "validate_config",
    "get_app_permission_report",
    # Logging utilities
    "setup_logging",
    "get_logger",
    "LoggerAdapter",
    "create_request_logger",
    "ColoredFormatter",
    "JSONFormatter",
    # System utilities
    "SystemInfo",
    "DiskUtils",
    "ProcessUtils",
    "PathUtils",
    "get_system_report",
]


