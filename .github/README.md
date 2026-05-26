# FileFy

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](/)
[![License](https://img.shields.io/badge/license-MIT-green)](/LICENSE)
[![FileFy - Modern Cloud File Manager](https://img.shields.io/pypi/v/filefy?color=blue&logo=python)](https://pypi.org/project/filefy/ 'Filefy Modern Flask File Manager')


A **professional web-based File Manager** Written in Python. Features a Beautiful Dark Theme UI, File Upload/Download, Remote URL Downloads With Progress Tracking, and Comprehensive File Operations.

<p align="center">
<a title="pip install filefy" href="https://pypi.org/project/filefy"><img src="https://raw.githubusercontent.com/Pymmdrza/filefy/refs/heads/main/.github/pip.svg" alt="Modern Cloud File Manager - FileFy" width="305"/></a>
<br/>
<a title="FileFy - Home Screenshot" href="https://raw.githubusercontent.com/Pymmdrza/filefy/refs/heads/main/.github/home-screen.png"><img src="https://raw.githubusercontent.com/Pymmdrza/filefy/refs/heads/main/.github/home-screen.png" alt="Modern Cloud File Manager - FileFy" width="605"/></a>
</p>

## Features

- **Professional Dark Theme UI** - Modern, responsive design
- **File Upload** - Drag & drop or click to upload files. Uploads are
  chunked, with per-file progress, **pause / resume / cancel** controls,
  and they survive transient connection drops.
- **File Download** - Download files directly from the browser, with
  HTTP Range support so the in-browser transfer manager can pause and
  resume large local downloads.
- **Remote Download** - Download files from URLs with progress tracking
  and **pause / resume / cancel** support. [Screenshot](https://raw.githubusercontent.com/Pymmdrza/filefy/refs/heads/main/.github/home-screen.png 'FileFy - Download Process Screenshot')
- **Compress** - Right-click any file or folder and create an archive
  (`.zip`, `.tar`, `.tar.gz`) directly on the server.
- **Transfer Center** - Centered, project-themed panel that shows every
  in-flight transfer (upload, download, remote download). It can be
  minimised to the sidebar and never gets stuck on a Cancelled / Error
  state — every row has Pause, Resume, Cancel and Dismiss controls.
- [**Cloudflare Tunnel**](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/ 'Cloudflare Tunnel') - Optional `--tunnel` flag that publishes the
  server through a free `*.trycloudflare.com` URL alongside the local
  one. Requires the `cloudflared` binary to be installed on PATH.
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
# Start in the current directory (port 5000)
filefy

# Custom port
filefy --port 8080

# Custom directory
filefy --dir /path/to/directory

# Bind to specific host
filefy --host 127.0.0.1 --port 3000

# Enable debug mode
filefy --debug

# Explicitly enable the public Cloudflare tunnel (enabled by default)
filefy --tunnel

# Run only on the local/private URL and skip the Cloudflare tunnel
filefy --no-tunnel
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
usage: filefy [-h] [-H HOST] [-p PORT] [-d DIRECTORY] [--debug]
              [--tunnel | --no-tunnel] [--install-cloudflared] [-v]

filefy - Professional Web-Based File Manager

options:
  -h, --help            show this help message and exit
  -H HOST, --host HOST  Host to bind the server to (default: 0.0.0.0)
  -p PORT, --port PORT  Port to run the server on (default: 5000)
  -d DIRECTORY, --dir DIRECTORY, --directory DIRECTORY
                        Base directory for file management (default: current
                        directory)
  --debug               Enable Flask debug mode
  --tunnel              Enable the automatic Cloudflare quick tunnel. This is
                        the default unless --no-tunnel is used.
  --no-tunnel           Disable the automatic Cloudflare quick tunnel.
  --install-cloudflared
                        Install the 'cloudflared' binary for the current
                        operating system and exit.
  -v, --version         show program's version number and exit

Examples:
  filefy                         Start in the current directory
  filefy -p 8080                 Use port 8080
  filefy --host 127.0.0.1        Only allow local connections
  filefy -d /home/user/files     Set base directory
  filefy --debug                 Enable Flask debug mode
  filefy --tunnel                Also expose a public Cloudflare URL
  filefy --no-tunnel             Disable public Cloudflare tunnel startup
```

## Python API

You can also use filefy programmatically:

```python
from filefy import app, create_app
from filefy.server import run

# Option 1: Run in the current directory
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

## Development

### Setup Development Environment

```bash
git clone https://github.com/Pymmdrza/filefy.git
cd filefy
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

>[!NOTE]
> More details about [API](https://github.com/Pymmdrza/filefy/blob/main/.github/API.md)


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
