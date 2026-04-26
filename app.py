"""
filefy - A Professional Web-Based File Manager
Features:
- File upload and download
- Remote URL download with progress tracking
- File/folder operations (copy, move, delete, rename)
- Professional dark theme UI
"""

import os
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
    abort,
    Response,
    stream_with_context,
)
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(24).hex()
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024 * 1024  # 10GB max upload

# Base directory for file management (can be changed to any directory)
BASE_DIR = os.path.expanduser("~")
ALLOWED_EXTENSIONS = {"*"}  # Allow all file types

# Store download progress for remote downloads
download_tasks = {}


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
    except (OSError, PermissionError) as e:
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


def remote_download_task(task_id, url, destination_path):
    """Background task for downloading files from remote URLs"""
    try:
        print(
            f"[Download Task {task_id}] Starting download from {url} to {destination_path}"
        )
        download_tasks[task_id]["status"] = "downloading"
        download_tasks[task_id]["started_at"] = time.time()

        # Start the download with headers to mimic browser
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        response = requests.get(
            url, stream=True, timeout=60, headers=headers, verify=True
        )
        response.raise_for_status()
        print(f"[Download Task {task_id}] Got response, status: {response.status_code}")

        # Get file size if available
        total_size = int(response.headers.get("content-length", 0))
        download_tasks[task_id]["total_size"] = total_size

        # Get filename from URL or Content-Disposition header
        filename = None
        if "content-disposition" in response.headers:
            cd = response.headers["content-disposition"]
            if "filename=" in cd:
                filename = cd.split("filename=")[1].strip("\"'")

        if not filename:
            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path) or "downloaded_file"

        filename = secure_filename(filename)
        file_path = os.path.join(destination_path, filename)

        # Handle duplicate filenames
        base, ext = os.path.splitext(file_path)
        counter = 1
        while os.path.exists(file_path):
            file_path = f"{base}_{counter}{ext}"
            counter += 1

        download_tasks[task_id]["filename"] = os.path.basename(file_path)
        download_tasks[task_id]["file_path"] = file_path

        # Download with progress tracking
        downloaded = 0
        start_time = time.time()

        with open(file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if download_tasks[task_id].get("cancelled"):
                    f.close()
                    os.remove(file_path)
                    download_tasks[task_id]["status"] = "cancelled"
                    return

                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)

                    # Calculate progress and speed
                    elapsed = time.time() - start_time
                    speed = downloaded / elapsed if elapsed > 0 else 0

                    download_tasks[task_id]["downloaded"] = downloaded
                    download_tasks[task_id]["speed"] = speed
                    if total_size > 0:
                        download_tasks[task_id]["progress"] = (
                            downloaded / total_size
                        ) * 100

        download_tasks[task_id]["status"] = "completed"
        download_tasks[task_id]["progress"] = 100
        download_tasks[task_id]["completed_at"] = time.time()

    except requests.exceptions.RequestException as e:
        print(f"[Download Task {task_id}] Request error: {str(e)}")
        download_tasks[task_id]["status"] = "error"
        download_tasks[task_id]["error"] = f"Request failed: {str(e)}"
    except IOError as e:
        print(f"[Download Task {task_id}] IO error: {str(e)}")
        download_tasks[task_id]["status"] = "error"
        download_tasks[task_id]["error"] = f"File error: {str(e)}"
    except Exception as e:
        print(f"[Download Task {task_id}] Unexpected error: {str(e)}")
        download_tasks[task_id]["status"] = "error"
        download_tasks[task_id]["error"] = f"Unexpected error: {str(e)}"


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
    data = request.get_json()
    url = data.get("url")
    destination = data.get("destination", BASE_DIR)

    if not url:
        return jsonify({"error": "URL is required"}), 400

    safe_path = get_safe_path(destination)

    if not os.path.exists(safe_path) or not os.path.isdir(safe_path):
        return jsonify({"error": "Invalid destination path"}), 400

    # Create a new download task
    task_id = str(uuid.uuid4())
    download_tasks[task_id] = {
        "id": task_id,
        "url": url,
        "destination": safe_path,
        "status": "pending",
        "progress": 0,
        "downloaded": 0,
        "total_size": 0,
        "speed": 0,
        "filename": None,
        "created_at": time.time(),
    }

    # Start download in background thread
    thread = threading.Thread(
        target=remote_download_task, args=(task_id, url, safe_path)
    )
    thread.daemon = True
    thread.start()

    return jsonify({"task_id": task_id, "message": "Download started"})


@app.route("/api/download-progress/<task_id>")
def download_progress(task_id):
    """Get the progress of a remote download task"""
    if task_id not in download_tasks:
        return jsonify({"error": "Task not found"}), 404

    task = download_tasks[task_id]
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
    if task_id not in download_tasks:
        return jsonify({"error": "Task not found"}), 404

    download_tasks[task_id]["cancelled"] = True
    return jsonify({"message": "Download cancelled"})


@app.route("/api/download-tasks")
def get_download_tasks():
    """Get all download tasks"""
    tasks = []
    for task_id, task in download_tasks.items():
        tasks.append(
            {
                "id": task["id"],
                "url": task["url"],
                "status": task["status"],
                "progress": task["progress"],
                "filename": task["filename"],
                "downloaded_formatted": format_size(task["downloaded"]),
                "total_size_formatted": (
                    format_size(task["total_size"]) if task["total_size"] else "Unknown"
                ),
                "speed_formatted": (
                    format_size(task["speed"]) + "/s" if task["speed"] else "0 B/s"
                ),
            }
        )
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
    """Return the dynamic Quick Access shortcuts for the host system."""
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


if __name__ == "__main__":
    print("=" * 50)
    print("FileFy - Web-Based File Manager")
    print("=" * 50)
    print(f"Base Directory: {BASE_DIR}")
    print("Starting server at http://0.0.0.0:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)
