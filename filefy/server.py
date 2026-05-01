"""
Filer - A Professional Web-Based File Manager
Features:
- File upload and download
- Remote URL download with progress tracking
- File/folder operations (copy, move, delete, rename)
- Professional dark theme UI
"""

import logging
import os
import re
import shutil
import string
import tarfile
import tempfile
import threading
import time
import uuid
import zipfile
import mimetypes
from urllib.parse import unquote, urlparse
from datetime import datetime

import requests
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
)
from werkzeug.http import parse_options_header
from werkzeug.utils import secure_filename

from ._version import __version__ as _PACKAGE_VERSION

logger = logging.getLogger(__name__)

# Get the package directory for templates and static files
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

# Import configuration manager from the bundled config subpackage
try:
    from .config import config_manager, get_settings, get_details

    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False


def create_app(base_dir=None, secret_key=None):
    """Create and configure the Flask application"""
    application = Flask(
        __name__,
        template_folder=os.path.join(PACKAGE_DIR, "templates"),
        static_folder=os.path.join(PACKAGE_DIR, "static"),
    )

    # Load configuration from config manager if available
    if CONFIG_AVAILABLE:
        flask_config = config_manager.get_flask_config()
        application.config.update(flask_config)

        # Override with provided values
        if secret_key:
            application.config["SECRET_KEY"] = secret_key
        if base_dir:
            application.config["BASE_DIR"] = base_dir
        else:
            settings = get_settings()
            application.config["BASE_DIR"] = os.path.expanduser(
                settings.root_directory or "~"
            )
    else:
        application.config["SECRET_KEY"] = secret_key or os.urandom(24).hex()
        application.config["MAX_CONTENT_LENGTH"] = (
            10 * 1024 * 1024 * 1024
        )  # 10GB max upload
        application.config["BASE_DIR"] = base_dir or os.path.expanduser("~")

    return application


# Create default app instance
app = create_app()

# Base directory for file management (can be changed to any directory)
BASE_DIR = os.path.expanduser("~")
ALLOWED_EXTENSIONS = {"*"}  # Allow all file types

# Store download progress for remote downloads
download_tasks = {}
download_tasks_lock = threading.RLock()
DOWNLOAD_CHUNK_SIZE = 1024 * 256
DOWNLOAD_TIMEOUT = (10, 15)
DOWNLOAD_MAX_BATCH = 20
PROGRESS_CAP_BEFORE_COMPLETE = 99.9
DOWNLOAD_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# In-memory state for resumable chunked uploads. Each entry maps an
# upload-id (UUID) to a small dict describing the destination and the
# current ``.part`` file that bytes are being appended to. Entries are
# created by ``/api/upload-init`` and removed on completion or cancel.
upload_sessions = {}
upload_sessions_lock = threading.RLock()
UPLOAD_SESSION_TTL_SECONDS = 24 * 60 * 60  # purge idle sessions after 24h
UPLOAD_PART_SUFFIX = ".filefy-upload"

# Public information about the currently published Cloudflare tunnel,
# updated by ``run()`` once the tunnel is active. Exposed via the
# ``/api/server-info`` endpoint so the frontend can render the URL.
_server_info = {
    "version": _PACKAGE_VERSION,
    "tunnel_url": None,
    "tunnel_status": "disabled",  # one of: disabled, starting, active, error
    "tunnel_error": None,
}
_server_info_lock = threading.RLock()


def set_tunnel_info(url=None, status="disabled", error=None):
    """Update the global tunnel-status structure (thread-safe)."""
    with _server_info_lock:
        _server_info["tunnel_url"] = url
        _server_info["tunnel_status"] = status
        _server_info["tunnel_error"] = error


def get_server_info():
    """Return a snapshot of the public server info structure."""
    with _server_info_lock:
        return dict(_server_info)


def get_safe_path(path):
    """Ensure the path is within the allowed directory"""
    if not path:
        return BASE_DIR

    # Decode URL-encoded path
    path = unquote(path)

    # Expand ~ to home directory
    if path.startswith("~"):
        path = os.path.expanduser(path)

    # Handle absolute and relative paths
    if path.startswith("/"):
        full_path = os.path.abspath(path)
    else:
        full_path = os.path.abspath(os.path.join(BASE_DIR, path))

    return full_path


def get_file_info(file_path):
    """Get detailed information about a file or directory"""
    try:
        stat = os.stat(file_path)
        is_dir = os.path.isdir(file_path)

        return {
            "name": os.path.basename(file_path),
            "path": file_path,
            "is_dir": is_dir,
            "size": stat.st_size if not is_dir else get_dir_size(file_path),
            "size_formatted": format_size(stat.st_size) if not is_dir else "-",
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "created": datetime.fromtimestamp(stat.st_ctime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "extension": os.path.splitext(file_path)[1].lower() if not is_dir else "",
            "permissions": oct(stat.st_mode)[-3:],
            "icon": get_file_icon(file_path, is_dir),
        }
    except (OSError, PermissionError):
        return None


def get_dir_size(path):
    """Calculate total size of a directory"""
    total = 0
    try:
        for entry in os.scandir(path):
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_dir_size(entry.path)
    except PermissionError:
        pass
    return total


def format_size(size):
    """Format file size in human-readable format"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def get_file_icon(file_path, is_dir):
    """Get appropriate icon class for file type"""
    if is_dir:
        return "fa-folder"

    ext = os.path.splitext(file_path)[1].lower()
    icons = {
        ".py": "fa-file-code",
        ".js": "fa-file-code",
        ".html": "fa-file-code",
        ".css": "fa-file-code",
        ".json": "fa-file-code",
        ".xml": "fa-file-code",
        ".md": "fa-file-alt",
        ".txt": "fa-file-alt",
        ".pdf": "fa-file-pdf",
        ".doc": "fa-file-word",
        ".docx": "fa-file-word",
        ".xls": "fa-file-excel",
        ".xlsx": "fa-file-excel",
        ".ppt": "fa-file-powerpoint",
        ".pptx": "fa-file-powerpoint",
        ".jpg": "fa-file-image",
        ".jpeg": "fa-file-image",
        ".png": "fa-file-image",
        ".gif": "fa-file-image",
        ".svg": "fa-file-image",
        ".webp": "fa-file-image",
        ".mp3": "fa-file-audio",
        ".wav": "fa-file-audio",
        ".flac": "fa-file-audio",
        ".mp4": "fa-file-video",
        ".avi": "fa-file-video",
        ".mkv": "fa-file-video",
        ".mov": "fa-file-video",
        ".zip": "fa-file-archive",
        ".rar": "fa-file-archive",
        ".7z": "fa-file-archive",
        ".tar": "fa-file-archive",
        ".gz": "fa-file-archive",
    }
    return icons.get(ext, "fa-file")


def build_quick_access():
    """Build the list of Quick Access shortcuts based on what actually exists
    on the host this server is running on (Linux, macOS, Windows or Docker).

    The first entry is always the configured base directory (the user's data
    root, e.g. ``/data`` in Docker, or ``$HOME`` on a normal install). Then
    we add the standard XDG-style user folders that exist, the filesystem
    root, ``/tmp``, any mountpoints under ``/mnt`` and ``/media`` (Linux),
    and Windows drive letters when running on Windows.
    """
    items = []
    seen = set()

    def _add(label, path, icon):
        try:
            if not path:
                return
            normalized = os.path.abspath(os.path.expanduser(path))
            if normalized in seen:
                return
            if not os.path.isdir(normalized):
                return
            seen.add(normalized)
            items.append({"label": label, "path": normalized, "icon": icon})
        except (OSError, ValueError):
            return

    # 1. The configured base/data directory (what Docker users mount as /data).
    _add("Home", BASE_DIR, "fa-home")

    # 2. Standard user folders relative to the real user home (if different).
    user_home = os.path.expanduser("~")
    standard_dirs = [
        ("User Home", user_home, "fa-user"),
        ("Desktop", os.path.join(user_home, "Desktop"), "fa-desktop"),
        ("Documents", os.path.join(user_home, "Documents"), "fa-file-alt"),
        ("Downloads", os.path.join(user_home, "Downloads"), "fa-download"),
        ("Pictures", os.path.join(user_home, "Pictures"), "fa-image"),
        ("Music", os.path.join(user_home, "Music"), "fa-music"),
        ("Videos", os.path.join(user_home, "Videos"), "fa-video"),
    ]
    for label, path, icon in standard_dirs:
        _add(label, path, icon)

    # 3. Filesystem root and temp.
    if os.name == "nt":
        # On Windows expose every available drive letter.
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            _add(f"Drive {letter}:", drive, "fa-hdd")
    else:
        _add("Root", "/", "fa-hdd")
        _add("Temp", "/tmp", "fa-clock")

        # 4. Mountpoints commonly used for external drives / volumes.
        for parent in ("/mnt", "/media", "/Volumes"):
            try:
                if os.path.isdir(parent):
                    for entry in sorted(os.listdir(parent)):
                        full = os.path.join(parent, entry)
                        if os.path.isdir(full):
                            _add(entry, full, "fa-hdd")
            except (OSError, PermissionError):
                continue

    return items


def update_download_task(task_id, **updates):
    """Safely update a download task."""
    with download_tasks_lock:
        if task_id in download_tasks:
            download_tasks[task_id].update(updates)


def get_download_task(task_id):
    """Return a copy of a download task."""
    with download_tasks_lock:
        task = download_tasks.get(task_id)
        return dict(task) if task else None


def is_download_cancelled(task_id):
    """Check whether a download has been cancelled."""
    task = get_download_task(task_id)
    return bool(task and task.get("cancelled"))


def split_download_urls(value):
    """Normalize a single URL, newline text, or URL list."""
    if isinstance(value, list):
        raw_urls = value
    else:
        raw_urls = str(value or "").replace(",", "\n").splitlines()

    urls = [url for url in (str(url).strip() for url in raw_urls) if url]
    return urls[:DOWNLOAD_MAX_BATCH], len(urls) > DOWNLOAD_MAX_BATCH


def validate_remote_url(url):
    """Validate remote download URL input."""
    parsed_url = urlparse(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return "Only valid HTTP and HTTPS URLs are supported"
    return None


def get_download_filename(url, response):
    """Get a safe filename from the response or URL."""
    filename = None
    content_disposition = response.headers.get("content-disposition")
    if content_disposition:
        _, options = parse_options_header(content_disposition)
        filename = options.get("filename*") or options.get("filename")

    if not filename:
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path) or "downloaded_file"

    filename = secure_filename(unquote(filename))
    return filename or "downloaded_file"


def reserve_download_path(destination_path, filename):
    """Reserve a unique destination path for a download."""
    filename = secure_filename(filename) or "downloaded_file"
    file_path = os.path.join(destination_path, filename)
    base, ext = os.path.splitext(file_path)
    counter = 1

    while True:
        try:
            fd = os.open(file_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return file_path
        except FileExistsError:
            file_path = f"{base}_{counter}{ext}"
            counter += 1


def cleanup_download_files(*paths):
    """Remove partial or reserved files left by failed downloads."""
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass


def is_download_paused(task_id):
    """Check whether a download is currently paused by the user."""
    task = get_download_task(task_id)
    return bool(task and task.get("paused"))


def mark_download_cancelled(task_id, file_path=None, partial_path=None):
    """Mark a task cancelled and remove incomplete files."""
    cleanup_download_files(partial_path, file_path)
    update_download_task(
        task_id,
        status="cancelled",
        speed=0,
        cancelled=True,
        cancelled_at=time.time(),
    )


def remote_download_task(task_id, url, destination_path):
    """Background task for downloading files from remote URLs.

    Supports resume after a pause: when the worker is restarted via the
    pause/resume endpoints it reads the current ``downloaded`` byte count
    from the task and re-issues the request with a ``Range`` header so
    the partial file is appended to instead of being rewritten. If the
    server does not honour the ``Range`` header (replies ``200`` instead
    of ``206``) the partial file is truncated and the download restarts
    from the beginning so the result is still byte-accurate.
    """
    response = None
    # Snapshot the previous state (if any). When resuming, file_path /
    # partial_path / downloaded already point at the existing ``.part``
    # file; on a fresh start they are ``None`` / 0 and we will allocate
    # them after issuing the initial request.
    snapshot = get_download_task(task_id) or {}
    file_path = snapshot.get("file_path")
    partial_path = snapshot.get("partial_path")
    downloaded = int(snapshot.get("downloaded") or 0)
    resuming = bool(file_path and partial_path and downloaded > 0)

    try:
        update_download_task(
            task_id,
            status="downloading",
            paused=False,
            started_at=time.time(),
            speed=0,
        )

        headers = {"User-Agent": DOWNLOAD_USER_AGENT}
        if resuming and os.path.exists(partial_path):
            headers["Range"] = f"bytes={downloaded}-"
        else:
            # Either a fresh start or the partial file vanished while
            # paused: reset everything so we begin at byte 0.
            downloaded = 0
            resuming = False

        response = requests.get(
            url,
            stream=True,
            timeout=DOWNLOAD_TIMEOUT,
            headers=headers,
            verify=True,
        )
        response.raise_for_status()

        if is_download_cancelled(task_id):
            mark_download_cancelled(task_id, file_path, partial_path)
            return

        # If the server didn't honour our Range request (returned 200
        # instead of 206) we have to restart from scratch.
        range_honoured = (
            resuming and response.status_code == 206
        )
        if resuming and not range_honoured:
            downloaded = 0
            cleanup_download_files(partial_path)
            resuming = False

        if not resuming:
            content_length = int(response.headers.get("content-length", 0))
            filename = get_download_filename(url, response)
            file_path = reserve_download_path(destination_path, filename)
            partial_path = f"{file_path}.part"
            total_size = content_length
            update_download_task(
                task_id,
                total_size=total_size,
                filename=os.path.basename(file_path),
                file_path=file_path,
                partial_path=partial_path,
                downloaded=0,
            )
        else:
            # When resuming with a 206, content-length is the *remaining*
            # number of bytes; total_size is what we already had recorded.
            total_size = int(snapshot.get("total_size") or 0)

        # Download with progress tracking.
        mode = "ab" if resuming else "wb"
        start_time = time.time()
        bytes_in_session = 0

        with open(partial_path, mode) as f:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if is_download_cancelled(task_id):
                    mark_download_cancelled(task_id, file_path, partial_path)
                    return

                if is_download_paused(task_id):
                    # Persist state, leave the .part on disk and exit
                    # the worker. A fresh worker is spawned by the
                    # /api/resume-download/<id> endpoint when the user
                    # asks to continue.
                    update_download_task(
                        task_id,
                        status="paused",
                        speed=0,
                        paused_at=time.time(),
                    )
                    return

                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    bytes_in_session += len(chunk)

                    elapsed = time.time() - start_time
                    speed = bytes_in_session / elapsed if elapsed > 0 else 0

                    progress = 0
                    if total_size > 0:
                        # Keep 100% reserved for the final atomic rename step.
                        progress = min(
                            (downloaded / total_size) * 100,
                            PROGRESS_CAP_BEFORE_COMPLETE,
                        )

                    update_download_task(
                        task_id,
                        downloaded=downloaded,
                        speed=speed,
                        progress=progress,
                    )

        if is_download_cancelled(task_id):
            mark_download_cancelled(task_id, file_path, partial_path)
            return

        os.replace(partial_path, file_path)
        update_download_task(
            task_id,
            status="completed",
            progress=100,
            speed=0,
            completed_at=time.time(),
        )

    except requests.exceptions.RequestException as e:
        if is_download_cancelled(task_id):
            mark_download_cancelled(task_id, file_path, partial_path)
            return
        cleanup_download_files(partial_path, file_path)
        update_download_task(
            task_id,
            status="error",
            speed=0,
            error=f"Request failed: {str(e)}",
            failed_at=time.time(),
        )
    except IOError as e:
        if is_download_cancelled(task_id):
            mark_download_cancelled(task_id, file_path, partial_path)
            return
        cleanup_download_files(partial_path, file_path)
        update_download_task(
            task_id,
            status="error",
            speed=0,
            error=f"File error: {str(e)}",
            failed_at=time.time(),
        )
    except Exception as e:
        if is_download_cancelled(task_id):
            mark_download_cancelled(task_id, file_path, partial_path)
            return
        cleanup_download_files(partial_path, file_path)
        update_download_task(
            task_id,
            status="error",
            speed=0,
            error=f"Unexpected error: {str(e)}",
            failed_at=time.time(),
        )
    finally:
        if response is not None:
            response.close()


@app.route("/")
def index():
    """Render the main file manager interface"""
    return render_template("index.html")


@app.route("/api/browse")
def browse():
    """List files and directories in the specified path"""
    path = request.args.get("path", BASE_DIR)
    safe_path = get_safe_path(path)

    if not os.path.exists(safe_path):
        return jsonify({"error": "Path does not exist"}), 404

    if not os.path.isdir(safe_path):
        return jsonify({"error": "Path is not a directory"}), 400

    try:
        items = []
        for entry in os.scandir(safe_path):
            info = get_file_info(entry.path)
            if info:
                items.append(info)

        # Sort: directories first, then by name
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))

        # Get parent directory
        parent = os.path.dirname(safe_path)

        return jsonify(
            {
                "current_path": safe_path,
                "parent_path": parent if parent != safe_path else None,
                "items": items,
                "total_items": len(items),
            }
        )
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403


@app.route("/api/upload", methods=["POST"])
def upload():
    """Handle file uploads"""
    path = request.form.get("path", BASE_DIR)
    safe_path = get_safe_path(path)

    if not os.path.exists(safe_path) or not os.path.isdir(safe_path):
        return jsonify({"error": "Invalid destination path"}), 400

    if "files" not in request.files:
        return jsonify({"error": "No files provided"}), 400

    files = request.files.getlist("files")
    uploaded = []
    errors = []

    for file in files:
        if file.filename:
            filename = secure_filename(file.filename)
            file_path = os.path.join(safe_path, filename)

            # Handle duplicate filenames
            base, ext = os.path.splitext(file_path)
            counter = 1
            while os.path.exists(file_path):
                file_path = f"{base}_{counter}{ext}"
                counter += 1

            try:
                file.save(file_path)
                uploaded.append(os.path.basename(file_path))
            except Exception as e:
                errors.append({"file": filename, "error": str(e)})

    return jsonify(
        {
            "uploaded": uploaded,
            "errors": errors,
            "message": f"Uploaded {len(uploaded)} file(s)",
        }
    )


@app.route("/api/download/<path:file_path>")
def download(file_path):
    """Download a file, with HTTP Range support so large transfers can be
    paused / resumed by the browser-side transfer manager.

    Folders are streamed as a freshly-built ``.zip`` archive. Range
    requests on archives fall back to a non-resumable download because
    the archive is rebuilt on each request.
    """
    safe_path = get_safe_path(file_path)

    if not os.path.exists(safe_path):
        return jsonify({"error": "File not found"}), 404

    if os.path.isdir(safe_path):
        # Directory download = zip archive built on the fly.
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        try:
            with zipfile.ZipFile(temp_file.name, "w", zipfile.ZIP_DEFLATED) as zf:
                _add_path_to_zip(zf, safe_path, os.path.basename(safe_path))
        finally:
            temp_file.close()

        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name=f"{os.path.basename(safe_path)}.zip",
        )

    # Regular file: enable conditional / range responses so the
    # frontend can implement pause + resume against this endpoint.
    return send_file(safe_path, as_attachment=True, conditional=True)


@app.route("/api/remote-download", methods=["POST"])
def remote_download():
    """Start a remote file download"""
    data = request.get_json(silent=True) or {}
    requested_urls = data.get("urls", data.get("url"))
    destination = data.get("destination", BASE_DIR)
    urls, truncated = split_download_urls(requested_urls)

    if not urls:
        return jsonify({"error": "At least one URL is required"}), 400

    invalid_urls = [
        {"url": url, "error": validate_remote_url(url)}
        for url in urls
        if validate_remote_url(url)
    ]
    if invalid_urls:
        return jsonify({"error": "Invalid URL", "invalid_urls": invalid_urls}), 400

    safe_path = get_safe_path(destination)

    if not os.path.exists(safe_path) or not os.path.isdir(safe_path):
        return jsonify({"error": "Invalid destination path"}), 400

    task_ids = []
    for url in urls:
        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "url": url,
            "destination": safe_path,
            "status": "pending",
            "progress": 0,
            "downloaded": 0,
            "total_size": 0,
            "speed": 0,
            "filename": None,
            "file_path": None,
            "partial_path": None,
            "cancelled": False,
            "paused": False,
            "created_at": time.time(),
        }
        with download_tasks_lock:
            download_tasks[task_id] = task
        task_ids.append(task_id)

        # Start download in background thread
        thread = threading.Thread(
            target=remote_download_task, args=(task_id, url, safe_path)
        )
        thread.daemon = True
        thread.start()

    return jsonify(
        {
            "task_id": task_ids[0],
            "task_ids": task_ids,
            "count": len(task_ids),
            "truncated": truncated,
            "message": f"Started {len(task_ids)} download(s)",
        }
    )


@app.route("/api/download-progress/<task_id>")
def download_progress(task_id):
    """Get the progress of a remote download task"""
    task = get_download_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    return jsonify(
        {
            "id": task["id"],
            "url": task["url"],
            "status": task["status"],
            "progress": task["progress"],
            "downloaded": task["downloaded"],
            "downloaded_formatted": format_size(task["downloaded"]),
            "total_size": task["total_size"],
            "total_size_formatted": (
                format_size(task["total_size"]) if task["total_size"] else "Unknown"
            ),
            "speed": task["speed"],
            "speed_formatted": (
                format_size(task["speed"]) + "/s" if task["speed"] else "0 B/s"
            ),
            "filename": task["filename"],
            "error": task.get("error"),
            "paused": bool(task.get("paused")),
        }
    )


@app.route("/api/cancel-download/<task_id>", methods=["POST"])
def cancel_download(task_id):
    """Cancel a running, pending or paused download task."""
    task = get_download_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    if task["status"] in {"completed", "error", "cancelled"}:
        return jsonify({"message": "Task is already finished"}), 409

    # Paused tasks have no live worker to observe the ``cancelled`` flag,
    # so we synchronously clean up the partial file here.
    if task["status"] == "paused":
        mark_download_cancelled(
            task_id, task.get("file_path"), task.get("partial_path")
        )
        return jsonify({"message": "Download cancelled"})

    update_download_task(
        task_id,
        cancelled=True,
        status="cancelling",
        speed=0,
        cancelled_at=time.time(),
    )
    return jsonify({"message": "Download cancellation requested"})


@app.route("/api/download-tasks")
def get_download_tasks():
    """Get all download tasks"""
    tasks = []
    with download_tasks_lock:
        task_items = list(download_tasks.items())

    for task_id, task in task_items:
        tasks.append(
            {
                "id": task["id"],
                "url": task["url"],
                "status": task["status"],
                "progress": task["progress"],
                "filename": task["filename"],
                "downloaded": task["downloaded"],
                "total_size": task["total_size"],
                "speed": task["speed"],
                "downloaded_formatted": format_size(task["downloaded"]),
                "total_size_formatted": (
                    format_size(task["total_size"]) if task["total_size"] else "Unknown"
                ),
                "speed_formatted": (
                    format_size(task["speed"]) + "/s" if task["speed"] else "0 B/s"
                ),
                "error": task.get("error"),
                "destination": task.get("destination"),
                "created_at": task.get("created_at"),
                "paused": bool(task.get("paused")),
                "kind": "remote-download",
            }
        )
    tasks.sort(key=lambda task: task.get("created_at") or 0, reverse=True)
    return jsonify(tasks)


@app.route("/api/pause-download/<task_id>", methods=["POST"])
def pause_download(task_id):
    """Pause a running download. The worker thread observes the
    ``paused`` flag at every chunk boundary and exits cleanly, leaving
    the ``.part`` file on disk for ``/api/resume-download/<id>`` to
    pick up."""
    task = get_download_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    if task["status"] != "downloading":
        return jsonify({"message": "Only active downloads can be paused"}), 409

    update_download_task(task_id, paused=True, speed=0)
    return jsonify({"message": "Pause requested"})


@app.route("/api/resume-download/<task_id>", methods=["POST"])
def resume_download(task_id):
    """Resume a paused download by spawning a fresh worker thread that
    re-uses the existing ``.part`` file via an HTTP ``Range`` request."""
    task = get_download_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    if task["status"] not in {"paused", "error"}:
        return jsonify(
            {"message": "Only paused or errored downloads can be resumed"}
        ), 409
    if task.get("cancelled"):
        return jsonify({"error": "Task is cancelled"}), 409

    update_download_task(task_id, paused=False, status="pending", error=None)
    thread = threading.Thread(
        target=remote_download_task,
        args=(task_id, task["url"], task["destination"]),
    )
    thread.daemon = True
    thread.start()
    return jsonify({"message": "Resume requested"})


@app.route("/api/dismiss-download/<task_id>", methods=["POST"])
def dismiss_download(task_id):
    """Remove a finished download task from the listing.

    The frontend calls this when the user explicitly closes a transfer
    row that is in a terminal state (completed, error or cancelled), so
    that the side panel does not stay frozen on a "Cancelled" row.
    """
    with download_tasks_lock:
        task = download_tasks.get(task_id)
        if not task:
            return jsonify({"error": "Task not found"}), 404
        if task["status"] in {"downloading", "pending", "cancelling"}:
            return jsonify({"error": "Task is still active"}), 409
        download_tasks.pop(task_id, None)
    return jsonify({"message": "Task dismissed"})


@app.route("/api/server-info")
def server_info():
    """Return runtime information about the server (version, tunnel)."""
    info = get_server_info()
    info["base_dir"] = BASE_DIR
    return jsonify(info)


# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------

# Map the user-facing format strings to the (extension, callable) pair we
# use to build the archive. ``None`` for the second tuple member means
# the format is handled by ``zipfile`` instead of ``tarfile``.
_ARCHIVE_FORMATS = {
    "zip": (".zip", None),
    "tar": (".tar", "w"),
    "tar.gz": (".tar.gz", "w:gz"),
    "tgz": (".tar.gz", "w:gz"),
}


def _add_path_to_zip(zf, source, arcname_root):
    """Add ``source`` (a file or a directory tree) to an open ``zipfile``.

    ``arcname_root`` is the in-archive name to use for ``source`` itself;
    nested entries are placed under that name with their relative path
    preserved.
    """
    if os.path.isfile(source):
        zf.write(source, arcname_root)
        return
    for root, _dirs, files in os.walk(source):
        rel_root = os.path.relpath(root, source)
        for name in files:
            full = os.path.join(root, name)
            arc = (
                arcname_root
                if rel_root == "."
                else os.path.join(arcname_root, rel_root)
            )
            arc = os.path.join(arc, name)
            zf.write(full, arc)


def _add_path_to_tar(tf, source, arcname_root):
    """Add ``source`` (file or directory) recursively to an open tarfile."""
    tf.add(source, arcname=arcname_root, recursive=True)


@app.route("/api/compress", methods=["POST"])
def compress():
    """Create an archive (zip / tar / tar.gz) from one or more sources.

    Body (JSON)::

        {
          "sources":     [ "/abs/path/one", "/abs/path/two" ],
          "destination": "/abs/path/dest_dir",   # defaults to BASE_DIR
          "name":        "archive",              # without extension
          "format":      "zip" | "tar" | "tar.gz"
        }

    On success returns the path of the produced archive and its size.
    """
    data = request.get_json(silent=True) or {}

    sources = data.get("sources") or []
    if isinstance(sources, str):
        sources = [sources]
    sources = [s for s in sources if isinstance(s, str) and s.strip()]
    if not sources:
        return jsonify({"error": "At least one source path is required"}), 400

    destination = data.get("destination") or BASE_DIR
    fmt = (data.get("format") or "zip").lower()
    name = (data.get("name") or "").strip()

    if fmt not in _ARCHIVE_FORMATS:
        return jsonify({
            "error": (
                "Unsupported format. Use one of: "
                + ", ".join(sorted({k for k in _ARCHIVE_FORMATS if k != "tgz"}))
            )
        }), 400

    safe_destination = get_safe_path(destination)
    if not os.path.isdir(safe_destination):
        return jsonify({"error": "Destination must be an existing directory"}), 400

    safe_sources = []
    for src in sources:
        safe_src = get_safe_path(src)
        if not os.path.exists(safe_src):
            return jsonify({"error": f"Source not found: {src}"}), 404
        safe_sources.append(safe_src)

    if not name:
        # Default to the first source's basename when the user did not
        # provide an explicit archive name.
        name = os.path.basename(os.path.normpath(safe_sources[0])) or "archive"
    name = secure_filename(name) or "archive"

    extension, tar_mode = _ARCHIVE_FORMATS[fmt]
    archive_path = reserve_download_path(safe_destination, name + extension)

    try:
        if tar_mode is None:
            with zipfile.ZipFile(
                archive_path, "w", compression=zipfile.ZIP_DEFLATED
            ) as zf:
                for src in safe_sources:
                    _add_path_to_zip(zf, src, os.path.basename(src))
        else:
            with tarfile.open(archive_path, tar_mode) as tf:
                for src in safe_sources:
                    _add_path_to_tar(tf, src, os.path.basename(src))
    except Exception:
        cleanup_download_files(archive_path)
        logger.exception("Failed to build archive at %s", archive_path)
        return jsonify({"error": "Failed to build archive"}), 500

    size = os.path.getsize(archive_path)
    return jsonify(
        {
            "archive": archive_path,
            "name": os.path.basename(archive_path),
            "size": size,
            "size_formatted": format_size(size),
            "format": fmt,
        }
    )


# ---------------------------------------------------------------------------
# Resumable, chunked upload protocol
# ---------------------------------------------------------------------------
#
# The flow is:
#   1.   POST /api/upload-init    -> creates a session, returns upload_id
#   2.   PUT  /api/upload-chunk/<upload_id>  (with Content-Range header)
#                                 -> appends a slice of bytes to the part
#                                    file. The client may stop calling
#                                    this temporarily (pause), or call it
#                                    repeatedly until the full size has
#                                    been received (resume / continue).
#   3.   POST /api/upload-complete/<upload_id>
#                                 -> renames .part to the final filename
#                                    and frees the session.
#   4.   DELETE /api/upload-cancel/<upload_id>
#                                 -> removes the .part file and frees
#                                    the session.
#   5.   GET  /api/upload-status/<upload_id>
#                                 -> returns received bytes so the client
#                                    can resume from where it left off.

_CONTENT_RANGE_RE = re.compile(
    r"^bytes\s+(?P<start>\d+)-(?P<end>\d+)/(?P<total>\d+|\*)$"
)


def _parse_content_range(value):
    """Parse a ``Content-Range`` header. Returns ``(start, end, total)`` or
    ``None`` when the header is missing / malformed. ``total`` may be
    ``None`` if the client used ``*``."""
    if not value:
        return None
    match = _CONTENT_RANGE_RE.match(value.strip())
    if not match:
        return None
    start = int(match.group("start"))
    end = int(match.group("end"))
    total_raw = match.group("total")
    total = None if total_raw == "*" else int(total_raw)
    if start < 0 or end < start or (total is not None and end >= total):
        return None
    return start, end, total


def _purge_stale_upload_sessions():
    """Drop in-memory upload sessions that have been idle for too long.

    Called from ``upload_init`` so the cleanup runs lazily whenever a
    new upload is started; this avoids a dedicated background timer
    while still keeping the in-memory ``upload_sessions`` table from
    growing unbounded if clients abandon transfers.
    """
    now = time.time()
    with upload_sessions_lock:
        stale = [
            uid
            for uid, sess in upload_sessions.items()
            if now - sess.get("updated_at", 0) > UPLOAD_SESSION_TTL_SECONDS
        ]
        for uid in stale:
            sess = upload_sessions.pop(uid, None)
            if sess:
                cleanup_download_files(sess.get("partial_path"))


@app.route("/api/upload-init", methods=["POST"])
def upload_init():
    """Open a new chunked-upload session."""
    _purge_stale_upload_sessions()

    data = request.get_json(silent=True) or {}
    raw_filename = data.get("filename")
    raw_path = data.get("path") or BASE_DIR
    total_size = data.get("size")

    if not raw_filename or not isinstance(raw_filename, str):
        return jsonify({"error": "filename is required"}), 400
    if total_size is None or not isinstance(total_size, int) or total_size < 0:
        return jsonify({"error": "size must be a non-negative integer"}), 400

    filename = secure_filename(raw_filename) or "upload"
    safe_destination = get_safe_path(raw_path)
    if not os.path.isdir(safe_destination):
        return jsonify({"error": "Destination must be an existing directory"}), 400

    final_path = reserve_download_path(safe_destination, filename)
    partial_path = final_path + UPLOAD_PART_SUFFIX
    # ``reserve_download_path`` created an empty file at ``final_path``
    # to atomically claim the name. Move that placeholder to the part
    # file so the user does not see a zero-byte final file while the
    # upload is in progress.
    try:
        os.replace(final_path, partial_path)
    except OSError:
        cleanup_download_files(final_path)
        return jsonify({"error": "Failed to allocate upload buffer"}), 500

    upload_id = str(uuid.uuid4())
    session = {
        "id": upload_id,
        "filename": os.path.basename(final_path),
        "destination": safe_destination,
        "final_path": final_path,
        "partial_path": partial_path,
        "received": 0,
        "total_size": total_size,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    with upload_sessions_lock:
        upload_sessions[upload_id] = session
    return jsonify(
        {
            "upload_id": upload_id,
            "filename": session["filename"],
            "received": 0,
            "total_size": total_size,
        }
    )


@app.route("/api/upload-chunk/<upload_id>", methods=["PUT"])
def upload_chunk(upload_id):
    """Append a chunk of bytes to an in-progress upload."""
    with upload_sessions_lock:
        session = upload_sessions.get(upload_id)
        if not session:
            return jsonify({"error": "Upload session not found"}), 404
        partial_path = session["partial_path"]
        expected_offset = session["received"]
        total_size = session["total_size"]

    content_range = request.headers.get("Content-Range")
    parsed = _parse_content_range(content_range)
    if not parsed:
        return jsonify({
            "error": "Missing or malformed Content-Range header. "
                     "Use 'bytes start-end/total'.",
        }), 400
    start, end, declared_total = parsed
    chunk_length = end - start + 1
    if declared_total is not None and declared_total != total_size:
        return jsonify(
            {"error": "Content-Range total disagrees with session size"}
        ), 400

    if start != expected_offset:
        # The client is out of sync with the server; tell it where to
        # restart so it can adjust without losing data.
        return jsonify(
            {
                "error": "Chunk out of order",
                "expected_offset": expected_offset,
                "received": expected_offset,
            }
        ), 409

    data = request.get_data(cache=False, as_text=False)
    if len(data) != chunk_length:
        return jsonify({"error": "Body length does not match Content-Range"}), 400

    try:
        with open(partial_path, "ab") as f:
            f.write(data)
    except OSError:
        logger.exception("Failed to write upload chunk for %s", upload_id)
        return jsonify({"error": "Failed to write chunk"}), 500

    new_received = expected_offset + chunk_length
    with upload_sessions_lock:
        session = upload_sessions.get(upload_id)
        if not session:
            return jsonify({"error": "Upload session vanished"}), 404
        session["received"] = new_received
        session["updated_at"] = time.time()

    return jsonify(
        {
            "received": new_received,
            "total_size": total_size,
            "complete": new_received >= total_size,
        }
    )


@app.route("/api/upload-complete/<upload_id>", methods=["POST"])
def upload_complete(upload_id):
    """Finalise a chunked upload by renaming the part file."""
    with upload_sessions_lock:
        session = upload_sessions.pop(upload_id, None)
    if not session:
        return jsonify({"error": "Upload session not found"}), 404

    if session["received"] != session["total_size"]:
        # Put the session back so the client can keep uploading or
        # cancel cleanly.
        with upload_sessions_lock:
            upload_sessions[upload_id] = session
        return jsonify(
            {
                "error": "Upload is incomplete",
                "received": session["received"],
                "total_size": session["total_size"],
            }
        ), 409

    try:
        os.replace(session["partial_path"], session["final_path"])
    except OSError:
        cleanup_download_files(session["partial_path"])
        logger.exception("Failed to finalise upload %s", upload_id)
        return jsonify({"error": "Failed to finalise upload"}), 500

    size = os.path.getsize(session["final_path"])
    return jsonify(
        {
            "filename": os.path.basename(session["final_path"]),
            "path": session["final_path"],
            "size": size,
            "size_formatted": format_size(size),
        }
    )


@app.route("/api/upload-cancel/<upload_id>", methods=["DELETE"])
def upload_cancel(upload_id):
    """Cancel an upload session and remove the partial file."""
    with upload_sessions_lock:
        session = upload_sessions.pop(upload_id, None)
    if not session:
        return jsonify({"error": "Upload session not found"}), 404
    cleanup_download_files(session.get("partial_path"))
    return jsonify({"message": "Upload cancelled"})


@app.route("/api/upload-status/<upload_id>")
def upload_status(upload_id):
    """Report how many bytes have been received so the client can resume."""
    with upload_sessions_lock:
        session = upload_sessions.get(upload_id)
        if not session:
            return jsonify({"error": "Upload session not found"}), 404
        return jsonify(
            {
                "upload_id": upload_id,
                "received": session["received"],
                "total_size": session["total_size"],
                "filename": session["filename"],
            }
        )


@app.route("/api/create-folder", methods=["POST"])
def create_folder():
    """Create a new folder"""
    data = request.get_json()
    path = data.get("path", BASE_DIR)
    folder_name = data.get("name")

    if not folder_name:
        return jsonify({"error": "Folder name is required"}), 400

    safe_path = get_safe_path(path)
    folder_path = os.path.join(safe_path, secure_filename(folder_name))

    try:
        os.makedirs(folder_path, exist_ok=False)
        return jsonify({"message": "Folder created successfully", "path": folder_path})
    except FileExistsError:
        return jsonify({"error": "Folder already exists"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/rename", methods=["POST"])
def rename():
    """Rename a file or folder"""
    data = request.get_json()
    path = data.get("path")
    new_name = data.get("new_name")

    if not path or not new_name:
        return jsonify({"error": "Path and new name are required"}), 400

    safe_path = get_safe_path(path)
    if not os.path.exists(safe_path):
        return jsonify({"error": "File or folder not found"}), 404

    new_path = os.path.join(os.path.dirname(safe_path), secure_filename(new_name))

    try:
        os.rename(safe_path, new_path)
        return jsonify({"message": "Renamed successfully", "new_path": new_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/delete", methods=["POST"])
def delete():
    """Delete a file or folder"""
    data = request.get_json()
    path = data.get("path")

    if not path:
        return jsonify({"error": "Path is required"}), 400

    safe_path = get_safe_path(path)
    if not os.path.exists(safe_path):
        return jsonify({"error": "File or folder not found"}), 404

    try:
        if os.path.isdir(safe_path):
            shutil.rmtree(safe_path)
        else:
            os.remove(safe_path)
        return jsonify({"message": "Deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/copy", methods=["POST"])
def copy():
    """Copy a file or folder"""
    data = request.get_json()
    source = data.get("source")
    destination = data.get("destination")

    if not source or not destination:
        return jsonify({"error": "Source and destination are required"}), 400

    safe_source = get_safe_path(source)
    safe_destination = get_safe_path(destination)

    if not os.path.exists(safe_source):
        return jsonify({"error": "Source not found"}), 404

    if not os.path.isdir(safe_destination):
        return jsonify({"error": "Destination must be a directory"}), 400

    try:
        dest_path = os.path.join(safe_destination, os.path.basename(safe_source))

        # Handle duplicate names
        base, ext = os.path.splitext(dest_path)
        counter = 1
        while os.path.exists(dest_path):
            if os.path.isdir(safe_source):
                dest_path = f"{base}_copy_{counter}"
            else:
                dest_path = f"{base}_copy_{counter}{ext}"
            counter += 1

        if os.path.isdir(safe_source):
            shutil.copytree(safe_source, dest_path)
        else:
            shutil.copy2(safe_source, dest_path)

        return jsonify({"message": "Copied successfully", "new_path": dest_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/move", methods=["POST"])
def move():
    """Move a file or folder"""
    data = request.get_json()
    source = data.get("source")
    destination = data.get("destination")

    if not source or not destination:
        return jsonify({"error": "Source and destination are required"}), 400

    safe_source = get_safe_path(source)
    safe_destination = get_safe_path(destination)

    if not os.path.exists(safe_source):
        return jsonify({"error": "Source not found"}), 404

    if not os.path.isdir(safe_destination):
        return jsonify({"error": "Destination must be a directory"}), 400

    try:
        dest_path = os.path.join(safe_destination, os.path.basename(safe_source))
        shutil.move(safe_source, dest_path)
        return jsonify({"message": "Moved successfully", "new_path": dest_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/file-info")
def file_info():
    """Get detailed information about a file"""
    path = request.args.get("path")
    if not path:
        return jsonify({"error": "Path is required"}), 400

    safe_path = get_safe_path(path)
    if not os.path.exists(safe_path):
        return jsonify({"error": "File not found"}), 404

    info = get_file_info(safe_path)
    if info:
        return jsonify(info)
    return jsonify({"error": "Could not get file info"}), 500


@app.route("/api/preview/<path:file_path>")
def preview(file_path):
    """Preview file content (for text files and images)"""
    safe_path = get_safe_path(file_path)

    if not os.path.exists(safe_path):
        return jsonify({"error": "File not found"}), 404

    if os.path.isdir(safe_path):
        return jsonify({"error": "Cannot preview directories"}), 400

    mime_type, _ = mimetypes.guess_type(safe_path)

    # For images, return the file directly
    if mime_type and mime_type.startswith("image/"):
        return send_file(safe_path, mimetype=mime_type)

    # For text files, return content
    text_extensions = [
        ".txt",
        ".py",
        ".js",
        ".html",
        ".css",
        ".json",
        ".xml",
        ".md",
        ".yml",
        ".yaml",
        ".ini",
        ".cfg",
        ".conf",
        ".sh",
        ".bash",
        ".zsh",
        ".env",
        ".gitignore",
        ".log",
    ]

    ext = os.path.splitext(safe_path)[1].lower()
    if ext in text_extensions or (mime_type and mime_type.startswith("text/")):
        try:
            with open(safe_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(100000)  # Limit to 100KB
            return jsonify(
                {
                    "type": "text",
                    "content": content,
                    "mime_type": mime_type or "text/plain",
                }
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "File type not supported for preview"}), 400


@app.route("/api/search", methods=["GET"])
def search():
    """Search for files and folders"""
    query = request.args.get("query", "")
    path = request.args.get("path", BASE_DIR)

    if not query:
        return jsonify({"error": "Search query is required"}), 400

    safe_path = get_safe_path(path)
    results = []

    try:
        for root, dirs, files in os.walk(safe_path):
            # Limit search depth
            depth = root.replace(safe_path, "").count(os.sep)
            if depth > 5:
                continue

            for name in dirs + files:
                if query.lower() in name.lower():
                    full_path = os.path.join(root, name)
                    info = get_file_info(full_path)
                    if info:
                        results.append(info)

                    if len(results) >= 100:  # Limit results
                        break

            if len(results) >= 100:
                break

        return jsonify({"query": query, "results": results, "total": len(results)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/quick-access")
def quick_access():
    """Return the dynamic Quick Access shortcuts for the host system.

    The frontend uses this to populate the sidebar with locations that
    actually exist on the machine running filefy (instead of relying on
    paths that were hardcoded for the developer's workstation).
    """
    return jsonify(
        {
            "home": BASE_DIR,
            "items": build_quick_access(),
        }
    )


@app.route("/api/disk-usage")
def disk_usage():
    """Get disk usage information"""
    path = request.args.get("path", BASE_DIR)
    safe_path = get_safe_path(path)

    try:
        usage = shutil.disk_usage(safe_path)
        return jsonify(
            {
                "total": usage.total,
                "total_formatted": format_size(usage.total),
                "used": usage.used,
                "used_formatted": format_size(usage.used),
                "free": usage.free,
                "free_formatted": format_size(usage.free),
                "percent_used": round((usage.used / usage.total) * 100, 1),
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run(host=None, port=None, debug=False, base_dir=None, tunnel=False):
    """Run the Filefy server.

    Args:
        host: Host to bind to (default: from config or 0.0.0.0)
        port: Port to listen on (default: from config or 5000)
        debug: Enable debug mode (default: False)
        base_dir: Base directory for file management (default: user home)
        tunnel: When True, also publish a Cloudflare quick tunnel and
                print its public URL alongside the local URL. Requires
                the ``cloudflared`` binary to be installed and on PATH.
    """
    global BASE_DIR

    # Load settings from config if available
    if CONFIG_AVAILABLE:
        settings = get_settings()
        details = get_details()
        host = host or settings.host
        port = port or settings.port
        base_dir = base_dir or settings.root_directory
        app_name = details.app_name
        version = details.version or _PACKAGE_VERSION
    else:
        host = host or "0.0.0.0"
        port = port or 5000
        app_name = "Filefy"
        version = _PACKAGE_VERSION

    if base_dir:
        BASE_DIR = os.path.abspath(os.path.expanduser(base_dir))

    # Determine the URL we should ask Cloudflare to publish. When the
    # server is bound to 0.0.0.0 the loopback address is the right
    # target for the local cloudflared process.
    public_target_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    local_url = f"http://{host}:{port}"
    public_target_url = f"http://{public_target_host}:{port}"

    tunnel_instance = None
    public_url = None
    tunnel_error = None
    if tunnel:
        from .tunnel import CloudflareTunnel, TunnelError

        set_tunnel_info(status="starting")
        try:
            tunnel_instance = CloudflareTunnel(local_url=public_target_url)
            tunnel_instance.start()
            public_url = tunnel_instance.wait_for_url(timeout=30)
            if public_url:
                set_tunnel_info(url=public_url, status="active")
            else:
                tunnel_error = (
                    "cloudflared started but did not report a public URL "
                    "within 30 seconds"
                )
                set_tunnel_info(status="error", error=tunnel_error)
        except TunnelError as exc:
            tunnel_error = str(exc)
            set_tunnel_info(status="error", error=tunnel_error)

    print()
    print("\033[1;36m" + "=" * 55 + "\033[0m")
    print(f"\033[1;36m   {app_name} v{version} - Web-Based File Manager\033[0m")
    print("\033[1;36m" + "=" * 55 + "\033[0m")
    print(f"\033[1;33m   Base Directory:\033[0m {BASE_DIR}")
    print(f"\033[1;33m   Local URL:\033[0m     {local_url}")
    if public_url:
        print(f"\033[1;32m   Public URL:\033[0m    {public_url}")
    elif tunnel:
        print(f"\033[1;31m   Public URL:\033[0m    unavailable ({tunnel_error})")
    print("\033[1;36m" + "=" * 55 + "\033[0m")
    print()

    try:
        app.run(host=host, port=port, debug=debug)
    finally:
        if tunnel_instance is not None:
            tunnel_instance.stop()
            set_tunnel_info(status="disabled")


if __name__ == "__main__":
    run(debug=True)
