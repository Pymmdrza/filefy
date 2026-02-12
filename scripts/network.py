"""
Network Utility Module
Provides IP detection, port checking, and port opening functionalities.
"""

import socket
import subprocess
import platform
import urllib.request
import json
from typing import Optional, Tuple


# ──────────────────────────────────────────────
#  1. IP Address Detection
# ──────────────────────────────────────────────

def get_local_ip() -> str:
    """
    Get the local (LAN) IP address of the machine.
    Creates a dummy UDP connection to determine the preferred outbound IP.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Doesn't actually send data; used to find the preferred local IP
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
        return local_ip
    except OSError:
        return "127.0.0.1"


def get_public_ip() -> Optional[str]:
    """
    Get the public (WAN) IP address by querying an external API.
    Returns None if the request fails.
    """
    services = [
        "https://api.ipify.org?format=json",
        "https://ipinfo.io/json",
        "https://httpbin.org/ip",
    ]

    for url in services:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Python"})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                # Different services use different key names
                return data.get("ip") or data.get("origin")
        except Exception:
            continue

    return None


def get_all_ips() -> dict:
    """
    Return both local and public IP addresses in a dictionary.
    """
    return {
        "local_ip": get_local_ip(),
        "public_ip": get_public_ip(),
    }


# ──────────────────────────────────────────────
#  2. Port Checking
# ──────────────────────────────────────────────

def is_port_open(port: int, host: str = "127.0.0.1", timeout: float = 2.0) -> bool:
    """
    Check whether a specific port is open (listening) on the given host.

    Args:
        port:    Port number to check.
        host:    Target host/IP (default: localhost).
        timeout: Connection timeout in seconds.

    Returns:
        True if the port is open, False otherwise.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            result = s.connect_ex((host, port))
            return result == 0
    except OSError:
        return False


def scan_ports(
        host: str = "127.0.0.1",
        start: int = 1,
        end: int = 1024,
        timeout: float = 0.5,
) -> list[int]:
    """
    Scan a range of ports and return the list of open ones.

    Args:
        host:    Target host/IP.
        start:   Start of port range (inclusive).
        end:     End of port range (inclusive).
        timeout: Timeout per port attempt.

    Returns:
        A sorted list of open port numbers.
    """
    open_ports = []
    for port in range(start, end + 1):
        if is_port_open(port, host, timeout):
            open_ports.append(port)
    return open_ports


# ──────────────────────────────────────────────
#  3. Port Opening (Firewall Rule)
# ──────────────────────────────────────────────

def open_port_on_firewall(
        port: int,
        protocol: str = "tcp",
        rule_name: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Open a port in the OS firewall.
    Supports Windows (netsh) and Linux (iptables / firewalld / ufw).

    ⚠ Requires administrator / root privileges.

    Args:
        port:      Port number to open.
        protocol:  'tcp' or 'udp'.
        rule_name: Friendly name for the rule (Windows only).

    Returns:
        A tuple of (success: bool, message: str).
    """
    protocol = protocol.lower()
    if protocol not in ("tcp", "udp"):
        return False, "Protocol must be 'tcp' or 'udp'."

    if rule_name is None:
        rule_name = f"Open_Port_{port}_{protocol.upper()}"

    os_name = platform.system().lower()

    try:
        # ── Windows ──────────────────────────
        if os_name == "windows":
            cmd = [
                "netsh", "advfirewall", "firewall", "add", "rule",
                f"name={rule_name}",
                "dir=in",
                "action=allow",
                f"protocol={protocol}",
                f"localport={port}",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0:
                return True, f"Firewall rule '{rule_name}' added on Windows (port {port}/{protocol})."
            return False, f"Failed: {result.stderr.strip()}"

        # ── Linux ────────────────────────────
        elif os_name == "linux":
            # Try ufw first
            if _command_exists("ufw"):
                cmd = ["sudo", "ufw", "allow", f"{port}/{protocol}"]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0:
                    return True, f"UFW rule added (port {port}/{protocol})."
                return False, f"UFW failed: {result.stderr.strip()}"

            # Try firewall-cmd (firewalld)
            if _command_exists("firewall-cmd"):
                cmd = [
                    "sudo", "firewall-cmd", "--permanent",
                    f"--add-port={port}/{protocol}",
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0:
                    # Reload to apply
                    subprocess.run(
                        ["sudo", "firewall-cmd", "--reload"],
                        capture_output=True, text=True, timeout=15,
                    )
                    return True, f"Firewalld rule added (port {port}/{protocol})."
                return False, f"Firewalld failed: {result.stderr.strip()}"

            # Fallback to iptables
            if _command_exists("iptables"):
                cmd = [
                    "sudo", "iptables", "-A", "INPUT",
                    "-p", protocol,
                    "--dport", str(port),
                    "-j", "ACCEPT",
                ]
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0:
                    return True, f"iptables rule added (port {port}/{protocol})."
                return False, f"iptables failed: {result.stderr.strip()}"

            return False, "No supported firewall tool found (ufw / firewalld / iptables)."

        # ── macOS ────────────────────────────
        elif os_name == "darwin":
            return False, (
                "macOS pf firewall requires manual configuration. "
                "Edit /etc/pf.conf to add a rule for port "
                f"{port}/{protocol}, then run 'sudo pfctl -f /etc/pf.conf'."
            )

        else:
            return False, f"Unsupported operating system: {os_name}"

    except subprocess.TimeoutExpired:
        return False, "Command timed out."
    except PermissionError:
        return False, "Permission denied. Run with administrator/root privileges."
    except Exception as e:
        return False, f"Unexpected error: {e}"


def _command_exists(name: str) -> bool:
    """Check if a CLI command is available on the system."""
    try:
        subprocess.run(
            ["which", name], capture_output=True, text=True, timeout=5
        )
        return True
    except Exception:
        return False


# ──────────────────────────────────────────────
#  4. Simple TCP Listener (bonus utility)
# ──────────────────────────────────────────────

def start_tcp_listener(port: int, host: str = "0.0.0.0") -> socket.socket:
    """
    Start a simple TCP listener on the given port so the port appears 'open'.
    Returns the server socket. Call .close() to stop listening.

    Args:
        port: Port to listen on.
        host: Bind address (default: all interfaces).

    Returns:
        A bound and listening socket object.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(1)
    print(f"[*] Listening on {host}:{port}")
    return server

# ──────────────────────────────────────────────
#  Example usage
# ──────────────────────────────────────────────

# # --- IP addresses ---
# ips = get_all_ips()
# print(f"\n[+] Local  IP : {ips['local_ip']}")
# print(f"[+] Public IP : {ips['public_ip'] or 'Could not determine'}")
#
# # --- Port check ---
# test_port = 80
# status = is_port_open(test_port)
# print(f"\n[+] Port {test_port} on localhost is {'OPEN' if status else 'CLOSED'}")
#
# # --- Open port in firewall (example, commented out) ---
# # success, msg = open_port_on_firewall(8080, protocol="tcp")
# # print(f"\n[+] Firewall: {msg}")
#
# # --- Start a listener (example, commented out) ---
# # srv = start_tcp_listener(9999)
# # input("Press Enter to stop listener...")
# # srv.close()
