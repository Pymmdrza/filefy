"""
scripts/install_cloudflared.py
==============================

Thin compatibility shim for the cloudflared installer.

The real implementation lives inside the ``filefy`` package at
:mod:`filefy.install_cloudflared` so that it ships with the wheel
published on PyPI and is therefore available out-of-the-box for every
``pip install filefy`` user. This file is kept so that running the
script directly from a source checkout (without first installing the
package) still works:

    python scripts/install_cloudflared.py
    python scripts/install_cloudflared.py --verbose
    python scripts/install_cloudflared.py --reinstall
    python scripts/install_cloudflared.py --no-package-manager

When the ``filefy`` package is installed, prefer either the dedicated
console script or the module form, both of which use the exact same
implementation::

    filefy-install-cloudflared
    python -m filefy.install_cloudflared
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the in-tree ``filefy`` package importable when this script is run
# directly from a source checkout (i.e. before ``pip install``).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from filefy.install_cloudflared import (  # noqa: E402  (import after sys.path tweak)
    CloudflaredInstallError,
    InstallResult,
    ensure_cloudflared,
    install_cloudflared,
    main,
)

__all__ = [
    "CloudflaredInstallError",
    "InstallResult",
    "ensure_cloudflared",
    "install_cloudflared",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
