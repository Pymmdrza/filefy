# Filefy — A Self-Hosted, Web-Based File Manager Built with Python & Flask

> **TL;DR** — `pip install filefy && filefy`. Open your browser, manage files from anywhere, download from remote URLs, compress/extract archives, transfer files to peer servers, and share a public URL via Cloudflare Tunnel — all without leaving the browser and without installing anything extra on the client side.

---

## The Problem

Every developer who manages a remote server, a NAS box, or a cloud VM eventually reaches for the same tired toolkit: `scp`, `rsync`, `wget`, raw `tar` commands, and occasionally a heavy FTP client. The workflow is friction-heavy, requires CLI knowledge on both ends, and leaves non-technical collaborators completely stranded.

Filefy solves this by shipping a **complete, production-ready file manager as a single Python package** that runs in any browser.

---

## What Is Filefy?

**Filefy** (v1.1.1, MIT License) is a professional, self-hosted web file manager written in Python. It runs a Flask server and serves a polished dark-theme single-page application. Every operation — uploading, downloading, compressing, extracting, remote-fetching — happens server-side, while the browser acts purely as a control interface.

Key design principles:

- **Zero client-side dependencies** — users need only a modern browser.
- **Zero mandatory cloud accounts** — everything runs on your own machine.
- **Background-task architecture** — every long-running job runs in a daemon thread; the browser polls a progress endpoint and shows a real progress bar.
- **Minimal Python footprint** — the only runtime dependencies are Flask, Werkzeug, and Requests.

---

## Highlighted Features

### 1 · Resumable Chunked Upload

Uploads use a three-step protocol (`upload-init` → `upload-chunk` → `upload-complete`) that streams files in configurable chunks. If the connection drops mid-way, the client resumes from the last acknowledged byte — no duplicate work.

```
POST /api/upload-init      → create session, receive upload_id
PUT  /api/upload-chunk/<id> (Content-Range: bytes start-end/total)
POST /api/upload-complete/<id>
GET  /api/upload-status/<id>   → bytes received so far (resume point)
DELETE /api/upload-cancel/<id>
```

Controls in the Transfer Center: **Pause · Resume · Cancel**.

---

### 2 · Remote URL Download with Progress

Paste a URL, click **New Download**. Filefy fetches the file on the server side (using `requests` with streaming), stores it in the current directory, and streams back byte-count progress. Multiple downloads run concurrently.

```
POST /api/remote-download    → { "urls": ["https://…"] }  → task_ids[]
GET  /api/download-progress/<task_id>
POST /api/pause-download/<task_id>
POST /api/resume-download/<task_id>
POST /api/cancel-download/<task_id>
POST /api/dismiss-download/<task_id>
```

All status updates are displayed in the Transfer Center, which can be minimised to the sidebar.

---

### 3 · Compress Archives (zip / tar / tar.gz)

Right-click any file or folder → **Compress as…** → choose format and name. A daemon thread builds the archive while the browser polls for progress.

```
POST /api/compress          → { "sources": […], "format": "zip|tar|tar.gz" }
GET  /api/compress-progress/<task_id>
POST /api/cancel-compress/<task_id>
```

Supported formats: `.zip`, `.tar`, `.tar.gz` (with optional `pigz` for faster gzip). Large multi-GB trees are handled without blocking the server.

---

### 4 · Extract Archives — "Extract Here" (NEW)

The mirror image of compression. Right-click a recognised archive file → **Extract Here**. The same background-task + progress-polling pattern applies, so the Transfer Center shows a live progress bar with extracted-bytes / total-bytes and current filename.

Supported input formats: `.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz`, `.gz`, `.bz2`

```
POST /api/extract           → { "path": "/abs/path/archive.zip" }
GET  /api/extract-progress/<task_id>
POST /api/cancel-extract/<task_id>
```

The **Extract Here** context-menu item appears **only** when the selected file has a recognised archive extension — it stays hidden for all other file types.

---

### 5 · Cloudflare Tunnel — Public URL on Startup

Filefy automatically starts a [Cloudflare Quick Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) when it launches. Within seconds, both the local URL and a free `*.trycloudflare.com` public URL are printed to the terminal:

```
═══════════════════════════════════════════════════════
   FileFy v1.1.1 - Web-Based File Manager
═══════════════════════════════════════════════════════
   Base Directory: /home/user
   Local URL:      http://0.0.0.0:5000
   Public URL:     https://random-name.trycloudflare.com
═══════════════════════════════════════════════════════
```

The public URL is also surfaced in the UI so you can share it instantly. If you do not need public access, pass `--no-tunnel` to skip it.

```bash
filefy              # local + public URL (default)
filefy --no-tunnel  # local only
```

`cloudflared` is installed automatically on first use if it is not already on `PATH`. No Cloudflare account required.

---

### 6 · Server Bridge — Peer-to-Peer File Transfer Between Servers

This is arguably Filefy's most unique capability. The **Server Bridge** lets two independent Filefy instances connect to each other and exchange files — entirely through the browser, with no `scp`, no VPN, and no shared storage.

#### The Problem It Solves

Copying files from **Server A → Server B** traditionally means:
1. SSH into Server A, `scp`/`rsync` to Server B, or
2. Download to your laptop, then re-upload to Server B.

With the Server Bridge, you open Filefy in a single browser tab and orchestrate the transfer directly between the two servers — your laptop never touches the data.

#### Step-by-Step: Connecting Two Servers

**On Server A** (the server being connected *to*):

```
GET /api/bridge/generate-code?url=https://server-a.example.com
```

This returns a compact, URL-safe Base64 pairing code that encodes `{ "url": "...", "token": "<uuid>" }`. The token is **one-time use** and expires after a configurable TTL (default: a few minutes).

```json
{ "code": "eyJ1cmwiOiAiaHR0cHM6Ly9zZXJ2ZXItYS5leGFtcGxlLmNvbSIsICJ0b2tlbiI6ICIuLi4ifQ==" }
```

**On Server B** (the initiating side), paste the code:

```
POST /api/bridge/connect
{ "code": "<paste code here>", "name": "My Server B" }
```

Server B decodes the pairing code, calls Server A's **handshake endpoint**:

```
POST https://server-a.example.com/api/bridge/handshake
{ "token": "<uuid>", "peer_name": "My Server B" }
```

Server A:
1. Validates and **consumes** the token (one-time use — replays are rejected with HTTP 403).
2. Issues a **session token** (UUID) scoped to Server B.
3. Returns the session token plus Server A's hostname.

From this point on, Server B authenticates every peer-facing request with:

```
Authorization: Bearer <session_token>
```

Both sides now show each other in their **Connected Peers** panel.

#### Full Bridge API Surface

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/bridge/generate-code?url=<url>` | Generate one-time pairing code |
| `POST` | `/api/bridge/handshake` | Validate token → issue session (called by remote) |
| `POST` | `/api/bridge/connect` | Connect to a remote peer using a pairing code |
| `GET` | `/api/bridge/peers` | List all connected peers |
| `DELETE` | `/api/bridge/disconnect/<peer_id>` | Remove a peer |
| `GET` | `/api/bridge/peer-browse?peer_id=<id>&path=<path>` | Browse the remote peer's filesystem |
| `GET` | `/api/bridge/files` | Expose local files to authenticated peers |
| `GET` | `/api/bridge/file?path=<path>` | Stream a local file to an authenticated peer |
| `POST` | `/api/bridge/push` | Push local files **to** a peer (background task) |
| `POST` | `/api/bridge/pull` | Pull remote files **from** a peer (background task) |
| `POST` | `/api/bridge/receive-init` | Open chunked-upload session (called by pushing peer) |
| `PUT` | `/api/bridge/receive-chunk/<id>` | Receive a chunk (called by pushing peer) |
| `POST` | `/api/bridge/receive-complete/<id>` | Finalise a peer-pushed upload |
| `GET` | `/api/bridge/transfers` | List all active/finished bridge transfers |
| `GET` | `/api/bridge/transfer-progress/<task_id>` | Progress for one transfer |
| `POST` | `/api/bridge/cancel-transfer/<task_id>` | Cancel an in-flight transfer |
| `POST` | `/api/bridge/dismiss-transfer/<task_id>` | Remove a finished task from the list |
| `POST` | `/api/bridge/remote-op` | Proxy a file-op (delete/rename/copy/move) to a peer |

#### Push: Sending Files to a Peer

```
POST /api/bridge/push
{
  "peer_id":     "<uuid>",
  "files":       ["/abs/local/path/file1.tar.gz"],
  "destination": "/remote/dest/dir"
}
→ { "task_id": "<uuid>", "message": "Push started for 1 file(s)" }
```

The push runner:
1. **Initiates** a chunked-upload session on the peer (`receive-init`).
2. **Streams** the file in fixed-size chunks using `Content-Range` headers — the same protocol as a normal browser upload.
3. **Finalises** the session (`receive-complete`).
4. Repeats for every file in the list.
5. Reports bytes transferred, current filename, and speed in real time.

The transfer can be **cancelled** at any point; the partial file on the remote is cleaned up automatically.

#### Pull: Fetching Files from a Peer

```
POST /api/bridge/pull
{
  "peer_id":     "<uuid>",
  "files":       ["/remote/path/report.zip"],
  "destination": "/local/dest/dir"
}
→ { "task_id": "<uuid>", "message": "Pull started for 1 file(s)" }
```

The pull runner streams the remote file using `requests` with `stream=True`, writing it to the local filesystem in chunks. Progress (bytes, speed, current filename) is updated every 500 ms.

#### Remote File-System Operations

Beyond transferring files, the bridge can proxy **file-system operations** to a peer so you can manage the remote server as if it were local:

```
POST /api/bridge/remote-op
{
  "peer_id": "<uuid>",
  "op":      "delete" | "rename" | "create-folder" | "copy" | "move",
  "payload": { ... }
}
```

The payload is forwarded verbatim to the peer's regular API endpoint (`/api/delete`, `/api/rename`, etc.) and the response is returned as-is.

#### Security Model

- The pairing code is a **short-lived, one-time token** — intercepting an already-used code grants no access.
- All peer-facing endpoints require `Authorization: Bearer <session_token>`. Missing or invalid tokens return **HTTP 401**.
- File paths sent by peers are validated through the same `get_safe_path()` guard that protects the normal file manager — path-traversal attacks are blocked at **HTTP 403**.
- Sessions persist only in memory; restarting the server invalidates all active sessions.

#### Typical Use Cases

| Scenario | How Bridge Helps |
|---|---|
| Migrate data between two cloud VMs | Push/pull directly; laptop never touched |
| Sync a build artifact to a staging server | `push` a `.tar.gz` without SSH credentials |
| Remote cleanup on a peer | `remote-op: delete` from your local browser |
| Preview a remote file before pulling | `peer-browse` then open preview |

---

### 7 · Settings Modal

Click the ⚙ icon in the header to open the Settings modal. Current values are loaded from the server (`GET /api/settings`) and saved back (`POST /api/settings`) with instant feedback. Configurable fields:

| Setting | Description |
|---|---|
| Server Host | Network interface the server binds to |
| Server Port | TCP port (restart required) |
| Root Directory | Base directory exposed by the manager |
| Max Upload Size | Maximum bytes per upload |
| Read / Write / Delete | Per-operation permission flags |

---

### 8 · Rich File Operations

| Operation | UI Trigger | Notes |
|---|---|---|
| Copy / Cut / Paste | Context menu or Ctrl+C / Ctrl+X / Ctrl+V | Cross-directory |
| Duplicate | Context menu | Appends `_copy` suffix |
| Rename | F2 or context menu | |
| Move to… | Context menu → folder picker | |
| Copy to… | Context menu → folder picker | |
| Delete | Del key or context menu | |
| New Folder | Context menu | |
| Preview | Context menu | Text files & images |
| Properties | Context menu | Size, modified, MIME |
| Search | Header search box | |
| Keyboard navigation | Arrow keys, Enter | |

---

## Installation

### PyPI (Recommended)

```bash
pip install filefy
filefy
```

### pipx (Isolated Environment)

```bash
pipx install filefy
filefy
```

### From Source

```bash
git clone https://github.com/Pymmdrza/filefy.git
cd filefy
pip install -e .
filefy
```

### Docker (One-Liner)

```bash
docker run -d \
  --name filefy \
  -p 5000:5000 \
  -v "$PWD/data:/data" \
  ghcr.io/pymmdrza/filefy:latest
```

Pre-built multi-arch (`linux/amd64`, `linux/arm64`) images are published on every release to [ghcr.io/pymmdrza/filefy](https://github.com/Pymmdrza/filefy/pkgs/container/filefy). The Docker image includes `cloudflared` pre-installed so the tunnel works out-of-the-box.

### Docker Compose

```yaml
services:
  filefy:
    image: ghcr.io/pymmdrza/filefy:latest
    restart: unless-stopped
    ports:
      - "5000:5000"
    environment:
      FILEFY_HOST: "0.0.0.0"
      FILEFY_PORT: "5000"
      FILEFY_DIR: "/data"
    volumes:
      - ./data:/data
```

```bash
docker compose up -d
```

---

## CLI Reference

```
usage: filefy [-h] [-H HOST] [-p PORT] [-d DIR] [--debug] [--no-tunnel]
              [--install-cloudflared] [-v]

options:
  -H, --host HOST         Network interface to bind  (default: 0.0.0.0)
  -p, --port PORT         TCP port                   (default: 5000)
  -d, --dir DIR           Root directory             (default: home directory)
  --debug                 Enable Flask debug mode
  --no-tunnel             Skip the automatic Cloudflare public URL
  --install-cloudflared   Download & install cloudflared binary, then exit
  -v, --version           Print version and exit
```

Common patterns:

```bash
filefy                            # LAN + public Cloudflare URL
filefy --no-tunnel                # LAN only
filefy -p 8080 -d /srv/data       # custom port and directory
filefy --host 127.0.0.1           # localhost-only (most secure)
filefy --install-cloudflared      # one-shot cloudflared setup
```

---

## Python API

Filefy exposes a programmatic interface for embedding in larger applications:

```python
from filefy.server import run

# Minimal — binds to 0.0.0.0:5000, serves home directory
run()

# Custom configuration
run(
    host="127.0.0.1",
    port=8080,
    base_dir="/var/shared",
    tunnel=False,          # disable Cloudflare tunnel
    debug=False,
)
```

### WSGI Integration

```python
from filefy import create_app

# With Gunicorn
# gunicorn "filefy:create_app(base_dir='/data')" -b 0.0.0.0:8000 -w 4
app = create_app(base_dir="/data")
```

```bash
# Gunicorn
pip install gunicorn
gunicorn "filefy:create_app()" -b 0.0.0.0:8000 -w 4

# Waitress (cross-platform, great on Windows)
pip install waitress
waitress-serve --listen=0.0.0.0:8000 filefy:app
```

---

## Architecture at a Glance

```
Browser (SPA)
    │  REST + JSON
    ▼
Flask Server (filefy/server.py)
    ├─ /api/browse            Directory listing
    ├─ /api/upload-*          Chunked resumable upload protocol
    ├─ /api/download          Local file download (Range support)
    ├─ /api/remote-download   Background remote fetch + progress
    ├─ /api/compress          Background archiving + progress
    ├─ /api/extract           Background extraction + progress
    ├─ /api/bridge/*          Peer-to-peer file transfer
    ├─ /api/settings          Runtime configuration GET/POST
    └─ /api/server-info       Version + tunnel status
    │
    ├─ Background threads (daemon)
    │   ├─ compression_task_runner
    │   ├─ extraction_task_runner
    │   ├─ remote_download_task
    │   ├─ bridge_push_runner     (one per push task)
    │   └─ bridge_pull_runner     (one per pull task)
    │
    └─ CloudflareTunnel (subprocess: cloudflared)
```

Every long-running operation follows the same pattern:

1. **POST** starts the job → returns `task_id` immediately (HTTP 200).
2. **GET progress endpoint** polls at ~750 ms intervals → returns `{ status, processed, total, … }`.
3. **POST cancel endpoint** cooperatively cancels the running thread.
4. The Transfer Center in the UI renders all tasks in a unified panel.

---

## System Requirements

| | Minimum |
|---|---|
| Python | 3.9 + |
| Dependencies | Flask ≥ 2.3, Werkzeug ≥ 2.3, Requests ≥ 2.28 |
| OS | Linux, macOS, Windows |
| Browser | Any modern browser (Chrome, Firefox, Safari, Edge) |
| Disk | No restriction on managed directory size |

---

## Security Notes

- Filefy is designed for **trusted networks** (LAN, VPN, local machine). It does not ship with authentication by default.
- The `--host 127.0.0.1` flag restricts access to the local machine only — recommended when running on a shared host without a reverse proxy.
- All file-operation endpoints validate that resolved paths stay within the configured `BASE_DIR`; path-traversal attempts are rejected with HTTP 403.
- The Cloudflare Tunnel URL is ephemeral — it changes every time you restart filefy and cannot be predicted.

---

## Contributing

1. Fork [github.com/Pymmdrza/filefy](https://github.com/Pymmdrza/filefy)
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Install dev dependencies: `pip install -e ".[dev]"`
4. Run the test suite: `pytest`
5. Open a Pull Request

---

## Links

| | |
|---|---|
| **PyPI** | https://pypi.org/project/filefy/ |
| **GitHub** | https://github.com/Pymmdrza/filefy |
| **Docker Image** | https://github.com/Pymmdrza/filefy/pkgs/container/filefy |
| **Issues** | https://github.com/Pymmdrza/filefy/issues |
| **Changelog** | https://github.com/Pymmdrza/filefy/releases |
| **License** | MIT |

---

*Built by [Mmdrza](https://github.com/Pymmdrza) · MIT License · Python 3.9+*
