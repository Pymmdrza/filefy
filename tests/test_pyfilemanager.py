"""
Tests for filefy
"""

import pytest
import os
import tempfile
from pathlib import Path


class TestPackageImports:
    """Test that package imports work correctly"""

    def test_import_main_module(self):
        """Test importing the main module"""
        from filefy import __version__, app, create_app

        assert __version__ == "1.0.0"
        assert app is not None
        assert callable(create_app)

    def test_import_server(self):
        """Test importing server module"""
        from filefy.server import app, run, create_app

        assert app is not None
        assert callable(run)
        assert callable(create_app)

    def test_import_cli(self):
        """Test importing CLI module"""
        from filefy.cli import main

        assert callable(main)


class TestFlaskApp:
    """Test Flask application"""

    def test_app_creation(self):
        """Test that app can be created"""
        from filefy import create_app

        app = create_app()
        assert app is not None
        assert app.config["MAX_CONTENT_LENGTH"] == 10 * 1024 * 1024 * 1024

    def test_app_with_custom_base_dir(self):
        """Test app creation with custom base directory"""
        from filefy import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(base_dir=tmpdir)
            assert app.config["BASE_DIR"] == tmpdir

    def test_app_routes_exist(self):
        """Test that main routes exist"""
        from filefy import app

        routes = [rule.rule for rule in app.url_map.iter_rules()]

        # Check main routes exist
        assert "/" in routes
        assert "/api/browse" in routes
        assert "/api/upload" in routes
        assert "/api/download/<path:file_path>" in routes
        assert "/api/remote-download" in routes
        assert "/api/quick-access" in routes


class TestAPIEndpoints:
    """Test API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from filefy import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_index_page(self, client):
        """Test that index page loads"""
        response = client.get("/")
        assert response.status_code == 200

    def test_browse_home(self, client):
        """Test browsing home directory"""
        response = client.get("/api/browse?path=~")
        assert response.status_code == 200
        data = response.get_json()
        assert "current_path" in data
        assert "items" in data

    def test_browse_invalid_path(self, client):
        """Test browsing non-existent path"""
        response = client.get("/api/browse?path=/nonexistent/path/12345")
        assert response.status_code == 404

    def test_disk_usage(self, client):
        """Test disk usage endpoint"""
        response = client.get("/api/disk-usage")
        assert response.status_code == 200
        data = response.get_json()
        assert "total" in data
        assert "used" in data
        assert "free" in data

    def test_download_tasks(self, client):
        """Test download tasks endpoint"""
        response = client.get("/api/download-tasks")
        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)


class TestFileOperations:
    """Test file operation endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from filefy import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_create_folder(self, client, temp_dir):
        """Test creating a new folder"""
        response = client.post(
            "/api/create-folder", json={"path": temp_dir, "name": "test_folder"}
        )
        assert response.status_code == 200
        assert os.path.exists(os.path.join(temp_dir, "test_folder"))

    def test_create_folder_no_name(self, client, temp_dir):
        """Test creating folder without name"""
        response = client.post("/api/create-folder", json={"path": temp_dir})
        assert response.status_code == 400

    def test_file_info(self, client, temp_dir):
        """Test getting file info"""
        # Create a test file
        test_file = os.path.join(temp_dir, "test.txt")
        with open(test_file, "w") as f:
            f.write("Hello, World!")

        response = client.get(f"/api/file-info?path={test_file}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["name"] == "test.txt"
        assert data["is_dir"] is False


class TestRemoteDownload:
    """Test remote download functionality"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from filefy import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_remote_download_no_url(self, client):
        """Test remote download without URL"""
        response = client.post("/api/remote-download", json={"destination": "/tmp"})
        assert response.status_code == 400
        data = response.get_json()
        assert "error" in data

    def test_remote_download_invalid_destination(self, client):
        """Test remote download with invalid destination"""
        response = client.post(
            "/api/remote-download",
            json={
                "url": "https://example.com/file.txt",
                "destination": "/nonexistent/path",
            },
        )
        assert response.status_code == 400

    def test_remote_download_rejects_invalid_scheme(self, client):
        """Test remote download only accepts HTTP(S) URLs"""
        response = client.post(
            "/api/remote-download",
            json={"url": "file:///etc/passwd", "destination": "/tmp"},
        )
        assert response.status_code == 400
        data = response.get_json()
        assert "invalid_urls" in data

    def test_remote_download_accepts_multiple_urls(self, client, monkeypatch):
        """Test starting multiple remote downloads in one request"""
        import filefy.server as server

        def skip_download(*args):
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            server.download_tasks.clear()
            monkeypatch.setattr(server, "remote_download_task", skip_download)

            response = client.post(
                "/api/remote-download",
                json={
                    "urls": [
                        "https://example.com/one.txt",
                        "https://example.com/two.txt",
                    ],
                    "destination": tmpdir,
                },
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["count"] == 2
            assert len(data["task_ids"]) == 2
            assert len(server.download_tasks) == 2
            server.download_tasks.clear()

    def test_remote_download_accepts_comma_separated_urls(self, client, monkeypatch):
        """Test comma-separated URLs match the client-side splitter behavior"""
        import filefy.server as server

        def skip_download(*args):
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            server.download_tasks.clear()
            monkeypatch.setattr(server, "remote_download_task", skip_download)

            response = client.post(
                "/api/remote-download",
                json={
                    "url": (
                        "https://example.com/one.txt," "https://example.com/two.txt"
                    ),
                    "destination": tmpdir,
                },
            )

            assert response.status_code == 200
            data = response.get_json()
            assert data["count"] == 2
            assert len(data["task_ids"]) == 2
            server.download_tasks.clear()

    def test_cancel_download_marks_active_task(self, client):
        """Test cancelling an active download marks it for cleanup"""
        import filefy.server as server

        task_id = "active-task"
        server.download_tasks[task_id] = {
            "id": task_id,
            "url": "https://example.com/file.txt",
            "destination": "/tmp",
            "status": "downloading",
            "progress": 10,
            "downloaded": 10,
            "total_size": 100,
            "speed": 1,
            "filename": "file.txt",
            "created_at": 1,
        }

        response = client.post(f"/api/cancel-download/{task_id}")
        assert response.status_code == 200
        assert server.download_tasks[task_id]["cancelled"] is True
        assert server.download_tasks[task_id]["status"] == "cancelling"
        server.download_tasks.clear()

    def test_cancel_download_removes_partial_files(self):
        """Test cancellation cleanup removes reserved and partial files"""
        import filefy.server as server

        task_id = "cleanup-task"
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "file.txt")
            partial_path = os.path.join(tmpdir, "file.txt.part")
            Path(file_path).touch()
            Path(partial_path).touch()
            server.download_tasks[task_id] = {
                "id": task_id,
                "status": "downloading",
                "speed": 1,
            }

            server.mark_download_cancelled(task_id, file_path, partial_path)

            assert not os.path.exists(file_path)
            assert not os.path.exists(partial_path)
            assert server.download_tasks[task_id]["status"] == "cancelled"
            server.download_tasks.clear()


class TestQuickAccess:
    """Test the dynamic Quick Access endpoint."""

    @pytest.fixture
    def client(self):
        from filefy import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_quick_access_endpoint(self, client):
        """The endpoint must report a home directory and a list of items."""
        response = client.get("/api/quick-access")
        assert response.status_code == 200
        data = response.get_json()
        assert "home" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        # All returned shortcuts must point at directories that actually
        # exist on the host - never at hardcoded paths from the developer's
        # machine.
        for item in data["items"]:
            assert "label" in item
            assert "path" in item
            assert "icon" in item
            assert os.path.isdir(item["path"]), (
                f"Quick Access entry {item['label']!r} -> {item['path']!r} "
                "does not exist on this host"
            )

    def test_quick_access_includes_home(self, client):
        """The configured base/home directory must be among the shortcuts."""
        response = client.get("/api/quick-access")
        data = response.get_json()
        paths = {item["path"] for item in data["items"]}
        assert os.path.abspath(os.path.expanduser(data["home"])) in paths
