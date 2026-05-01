#!/usr/bin/env python3
"""
Backwards-compatible shim.

All packaging metadata lives in ``pyproject.toml``. This file exists only
so that legacy tooling that explicitly invokes ``python setup.py`` keeps
working. The version itself is the value defined in ``filefy/_version.py``
and is read by setuptools via the ``[tool.setuptools.dynamic]`` table in
``pyproject.toml``.
"""

from setuptools import setup

setup()
