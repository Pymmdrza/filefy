"""
Filer - A Professional Web-Based File Manager
Features:
- File upload and download
- Remote URL download with progress tracking
- File/folder operations (copy, move, delete, rename)
- Professional dark theme UI
"""

import os
import sys
import shutil
import string
import threading
import time
import uuid
import mimetypes
from pathlib import Path
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

# Get the package directory for templates and static files
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR_PATH = Path(PACKAGE_DIR).resolve().parent

# Add parent directory to path for config imports
sys.path.insert(0, str(BASE_DIR_PATH))

# Import configuration manager
try:
    from config import config_manager, get_settings, get_details

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
    """Background task for downloading files from remote URLs"""
    response = None
    file_path = None
    partial_path = None
    try:
        update_download_task(
            task_id,
            status="downloading",
            started_at=time.time(),
        )

        # Start the download with headers to mimic browser
        headers = {
            "User-Agent": DOWNLOAD_USER_AGENT,
        }
        response = requests.get(
            url,
            stream=True,
            timeout=DOWNLOAD_TIMEOUT,
            headers=headers,
            verify=True,
        )
        response.raise_for_status()

        if is_download_cancelled(task_id):
            mark_download_cancelled(task_id)
            return

        # Get file size if available
        total_size = int(response.headers.get("content-length", 0))
        filename = get_download_filename(url, response)
        file_path = reserve_download_path(destination_path, filename)
        partial_path = f"{file_path}.part"

        update_download_task(
            task_id,
            total_size=total_size,
            filename=os.path.basename(file_path),
            file_path=file_path,
            partial_path=partial_path,
        )

        # Download with progress tracking
        downloaded = 0
        start_time = time.time()

        with open(partial_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if is_download_cancelled(task_id):
                    mark_download_cancelled(task_id, file_path, partial_path)
                    return

                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    # Calculate progress and speed
                    elapsed = time.time() - start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0

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
    """Download a file"""
    safe_path = get_safe_path(file_path)

    if not os.path.exists(safe_path):
        return jsonify({"error": "File not found"}), 404

    if os.path.isdir(safe_path):
        # Create a zip file for directory download
        import tempfile
        import zipfile

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        with zipfile.ZipFile(temp_file.name, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(safe_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, safe_path)
                    zf.write(file_path, arcname)

        return send_file(
            temp_file.name,
            as_attachment=True,
            download_name=f"{os.path.basename(safe_path)}.zip",
        )

    return send_file(safe_path, as_attachment=True)


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
        }
    )


@app.route("/api/cancel-download/<task_id>", methods=["POST"])
def cancel_download(task_id):
    """Cancel a running download task"""
    task = get_download_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    if task["status"] in {"completed", "error", "cancelled"}:
        return jsonify({"message": "Task is already finished"}), 409

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
            }
        )
    tasks.sort(key=lambda task: task.get("created_at") or 0, reverse=True)
    return jsonify(tasks)


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


def run(host=None, port=None, debug=False, base_dir=None):
    """Run the Filer server

    Args:
        host: Host to bind to (default: from config or 0.0.0.0)
        port: Port to listen on (default: from config or 5000)
        debug: Enable debug mode (default: False)
        base_dir: Base directory for file management (default: user home)
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
        version = details.version
    else:
        host = host or "0.0.0.0"
        port = port or 5000
        app_name = "Filefy"
        version = "1.0.0"

    if base_dir:
        BASE_DIR = os.path.abspath(os.path.expanduser(base_dir))

    print()
    print("\033[1;36m" + "=" * 55 + "\033[0m")
    print(f"\033[1;36m   {app_name} v{version} - Web-Based File Manager\033[0m")
    print("\033[1;36m" + "=" * 55 + "\033[0m")
    print(f"\033[1;33m   Base Directory:\033[0m {BASE_DIR}")
    print(f"\033[1;33m   Server URL:\033[0m http://{host}:{port}")
    print("\033[1;36m" + "=" * 55 + "\033[0m")
    print()

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run(debug=True)
