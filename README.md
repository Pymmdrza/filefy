# filefy

[![PyPI version](https://badge.fury.io/py/filefy.svg)](https://badge.fury.io/py/filefy)
[![Python](https://img.shields.io/pypi/pyversions/filefy.svg)](https://pypi.org/project/filefy/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A **professional web-based file manager** written in Python with Flask. Features a beautiful dark theme UI, file upload/download, remote URL downloads with progress tracking, and comprehensive file operations.

## Features

- **Professional Dark Theme UI** - Modern, responsive design
- **File Upload** - Drag & drop or click to upload files
- **File Download** - Download files directly from the browser
- **Remote Download** - Download files from URLs with progress tracking
- **File Operations** - Copy, move, rename, delete files and folders
- **Search** - Quick file search functionality
- **Context Menu** - Right-click menu with common actions
- **Keyboard Shortcuts** - Ctrl+C, Ctrl+V, F2, Del, F5
- **File Preview** - Preview text files and images
- **Disk Usage** - View disk space information

## Quick Start

### Install from PyPI (One Command!)

```bash
pip install filefy
```

### Run the File Manager

```bash
# Start with default settings (port 5000, home directory)
filefy

# Custom port
filefy --port 8080

# Custom directory
filefy --dir /path/to/directory

# Bind to specific host
filefy --host 127.0.0.1 --port 3000

# Enable debug mode
filefy --debug
```

Then open your browser and go to: **http://localhost:5000**

## Installation Methods

### Method 1: pip (Recommended)

```bash
pip install filefy
```

### Method 2: From Source

```bash
git clone https://github.com/Pymmdrza/filefy.git
cd filefy
pip install -e .
```

### Method 3: Using pipx (Isolated Environment)

```bash
pipx install filefy
```

## CLI Usage

```
usage: filefy [-h] [-H HOST] [-p PORT] [-d DIR] [--debug] [-v]

filefy - Professional Web-Based File Manager

options:
  -h, --help            show this help message and exit
  -H, --host HOST       Host to bind the server to (default: 0.0.0.0)
  -p, --port PORT       Port to run the server on (default: 5000)
  -d, --dir DIR         Base directory for file management (default: home)
  --debug               Enable Flask debug mode
  -v, --version         show program's version number and exit

Examples:
  filefy                         Start with default settings
  filefy -p 8080                 Use port 8080
  filefy --host 127.0.0.1        Only allow local connections
  filefy -d /home/user/files     Set base directory
  filefy --debug                 Enable Flask debug mode
```

## Python API

You can also use filefy programmatically:

```python
from filefy import app, create_app
from filefy.server import run

# Option 1: Run with default settings
run()

# Option 2: Run with custom settings
run(host='127.0.0.1', port=8080, base_dir='/home/user/files')

# Option 3: Get Flask app for custom deployment
app = create_app(base_dir='/var/www/files')
# Use with gunicorn, waitress, etc.
```

### Using with Gunicorn

```bash
pip install gunicorn
gunicorn "filefy:create_app()" -b 0.0.0.0:8000 -w 4
```

### Using with Waitress (Windows)

```bash
pip install waitress
waitress-serve --listen=0.0.0.0:8000 filefy:app
```

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+C` | Copy selected item |
| `Ctrl+X` | Cut selected item |
| `Ctrl+V` | Paste item |
| `F2` | Rename selected item |
| `Delete` | Delete selected item |
| `F5` | Refresh current directory |
| `Escape` | Close modals / Deselect |

## API Endpoints

The following REST API endpoints are available:

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/browse` | List directory contents |
| `POST` | `/api/upload` | Upload files |
| `GET` | `/api/download` | Download a file |
| `POST` | `/api/remote-download` | Start remote URL download |
| `GET` | `/api/download-tasks` | Get download progress |
| `POST` | `/api/copy` | Copy file/folder |
| `POST` | `/api/move` | Move file/folder |
| `POST` | `/api/delete` | Delete file/folder |
| `POST` | `/api/rename` | Rename file/folder |
| `POST` | `/api/create-folder` | Create new folder |
| `GET` | `/api/search` | Search files |
| `GET` | `/api/preview` | Preview file content |
| `GET` | `/api/file-info` | Get file information |
| `GET` | `/api/disk-usage` | Get disk usage stats |

## Development

### Setup Development Environment

```bash
git clone https://github.com/Pymmdrza/filefy.git
cd filefy
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

Made by [MMdrza](https://github.com/Pymmdrza)
