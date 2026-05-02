#!/usr/bin/env python3
"""
Filer CLI - Command Line Interface

Usage:
    filefy                    # Start with defaults (port 5000, home directory)
    filefy --port 8080        # Start on custom port
    filefy --host 127.0.0.1   # Bind to specific host
    filefy --dir /path/to/dir # Start with custom directory
    filefy --debug            # Enable debug mode
"""

import argparse
import sys

from ._version import __version__ as _PACKAGE_VERSION

# Import the bundled configuration package
try:
    from .config import get_settings, get_details

    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False


def main():
    """Main entry point for the CLI"""
    # Get defaults from config if available
    if CONFIG_AVAILABLE:
        settings = get_settings()
        details = get_details()
        default_host = settings.host
        default_port = settings.port
        default_dir = settings.root_directory
        version = details.version or _PACKAGE_VERSION
    else:
        default_host = "0.0.0.0"
        default_port = 5000
        default_dir = None
        version = _PACKAGE_VERSION

    parser = argparse.ArgumentParser(
        prog="filefy",
        description="Filefy - Professional Web-Based File Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  filefy                         Start with default settings
  filefy -p 8080                 Use port 8080
  filefy --host 127.0.0.1        Only allow local connections
  filefy -d /home/user/files     Set base directory
  filefy --debug                 Enable Flask debug mode

Visit https://github.com/Pymmdrza/filefy for more information.
        """,
    )

    parser.add_argument(
        "-H",
        "--host",
        type=str,
        default=default_host,
        help=f"Host to bind the server to (default: {default_host})",
    )

    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=default_port,
        help=f"Port to run the server on (default: {default_port})",
    )

    parser.add_argument(
        "-d",
        "--dir",
        "--directory",
        type=str,
        default=default_dir,
        dest="directory",
        help="Base directory for file management (default: home directory)",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Flask debug mode",
    )

    parser.add_argument(
        "--tunnel",
        action="store_true",
        help=(
            "Also publish the server through a Cloudflare quick tunnel and "
            "print the public URL. Requires the 'cloudflared' binary to be "
            "installed and on PATH. The local URL stays available too."
        ),
    )

    parser.add_argument(
        "--install-cloudflared",
        action="store_true",
        help=(
            "Install the 'cloudflared' binary for the current operating "
            "system and exit. Useful as a one-shot prerequisite step "
            "before using --tunnel."
        ),
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {version}",
    )

    args = parser.parse_args()

    if args.install_cloudflared:
        from .install_cloudflared import main as install_main

        sys.exit(install_main())

    try:
        from .server import run

        run(
            host=args.host,
            port=args.port,
            debug=args.debug,
            base_dir=args.directory,
            tunnel=args.tunnel,
        )
    except KeyboardInterrupt:
        print("\n\nFilefy stopped. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
