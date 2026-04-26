# filefy

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](/)
[![License](https://img.shields.io/badge/license-MIT-green)](/LICENSE)
[![FileFy - Flask Modern file Manager](https://img.shields.io/pypi/v/filefy?color=blue&logo=python)](https://pypi.org/project/filefy/ 'Filefy Modern Flask File Manager')


A **professional web-based file manager** written in Python with Flask. Features a beautiful dark theme UI, file upload/download, remote URL downloads with progress tracking, and comprehensive file operations.

![FileFy Modern File Manager](.github/home-screen.png 'FileFy Modern flask file Manager')

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

### Method 4: Docker (GitHub Container Registry)

Pre-built multi-arch (`linux/amd64`, `linux/arm64`) images are published on every
push to the default branch and on every `v*` tag at
[`ghcr.io/pymmdrza/filefy`](https://github.com/Pymmdrza/filefy/pkgs/container/filefy).

```bash
# Pull and run the latest image, mounting the host directory you want to manage
docker run -d \
  --name filefy \
  -p 5000:5000 \
  -v "$PWD/data:/data" \
  ghcr.io/pymmdrza/filefy:latest
```

Open <http://localhost:5000> to use the file manager. The container exposes the
following environment variables (all optional):

| Variable      | Default     | Description                              |
|---------------|-------------|------------------------------------------|
| `FILEFY_HOST` | `0.0.0.0`   | Interface to bind the server to          |
| `FILEFY_PORT` | `5000`      | Port to listen on (inside the container) |
| `FILEFY_DIR`  | `/data`     | Base directory exposed by the manager    |

Pin a specific version by tag, e.g. `ghcr.io/pymmdrza/filefy:v1.0.0`.

#### Docker Compose

A ready-to-use `docker-compose.yml` is included:

```bash
docker compose up -d
```

This will mount `./data` into the container and expose the UI on
<http://localhost:5000>. Replace the `image:` line with `build: .` to build the
image locally from the source tree instead of pulling from GHCR.

#### Build the image yourself

```bash
git clone https://github.com/Pymmdrza/filefy.git
cd filefy
docker build -t filefy:local .
docker run --rm -p 5000:5000 -v "$PWD/data:/data" filefy:local
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
