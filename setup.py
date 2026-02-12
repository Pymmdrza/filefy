#!/usr/bin/env python3
"""
Setup script for backwards compatibility.
Modern installations should use pyproject.toml with pip install.
"""

from setuptools import setup, find_packages
from  pathlib import Path


# Read README for long description
def read_file(filename):
    current_dir = Path(__file__).parent
    with open(current_dir / filename) as f:
        return f.read()


setup(
    name="filefy",
    version="1.0.0",
    author="Mmdrza",
    author_email="pymmdrza@gmail.com",
    description="A professional web-based file manager with dark theme UI",
    long_description=read_file("README.md"),
    long_description_content_type="text/markdown",
    url="https://github.com/Pymmdrza/filefy",
    project_urls={
        "Bug Tracker": "https://github.com/Pymmdrza/filefy/issues",
        "Documentation": "https://github.com/Pymmdrza/filefy#readme",
    },
    packages=find_packages(),
    include_package_data=True,
    package_data={
        "filefy": [
            "templates/*.html",
            "templates/**/*.html",
            "static/css/*.css",
            "static/js/*.js",
            "static/img/*",
            "static/**/*",
        ],
    },
    python_requires=">=3.8",
    install_requires=[
        "Flask>=3.1.2",
        "Werkzeug>=3.1.5",
        "requests>=2.32.5",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "build>=0.10.0",
            "twine>=4.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "filefy=filefy.cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Web Environment",
        "Framework :: Flask",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        "Topic :: System :: Filesystems",
        "Topic :: Utilities",
    ],
    keywords="file-manager web-file-manager flask file-browser remote-download dark-theme remote-download filefy",
)
