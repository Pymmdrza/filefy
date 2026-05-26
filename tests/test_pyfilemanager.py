"""
Tests for filefy
"""

import pytest
import os
import sys
import tempfile
from pathlib import Path


class TestPackageImports:
    """Test that package imports work correctly"""

    def test_import_main_module(self):
        """Test importing the main module"""
        from filefy import __version__, app, create_app
        from filefy._version import __version__ as expected_version

        assert __version__ == expected_version
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


class TestCLI:
    """Test command-line startup behavior."""

    def test_cli_defaults_to_current_directory_marker(self, monkeypatch):
        """The CLI should let the server resolve the launch cwd."""
        import filefy.server as server

        captured = {}

        def fake_run(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(sys, "argv", ["filefy", "--no-tunnel"])
        monkeypatch.setattr(server, "run", fake_run)

        from filefy.cli import main

        main()

        assert captured["base_dir"] is None
        assert captured["tunnel"] is False

    def test_cli_accepts_custom_directory_and_tunnel_flags(self, monkeypatch):
        """README CLI examples should be accepted by the parser."""
        import filefy.server as server

        captured = {}

        def fake_run(**kwargs):
            captured.update(kwargs)

        monkeypatch.setattr(
            sys, "argv", ["filefy", "--dir", "/tmp", "--tunnel"]
        )
        monkeypatch.setattr(server, "run", fake_run)

        from filefy.cli import main

        main()

        assert captured["base_dir"] == "/tmp"
        assert captured["tunnel"] is True


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
            assert app.config["BASE_DIR"] == os.path.abspath(tmpdir)

    def test_app_defaults_to_current_directory(self, monkeypatch):
        """Test app creation defaults to the current working directory."""
        from filefy import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            app = create_app()
            assert app.config["BASE_DIR"] == os.path.abspath(tmpdir)

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

    def test_browse_does_not_calculate_recursive_directory_sizes(
        self, client, monkeypatch
    ):
        """Directory listings should not recurse into every child directory."""
        import filefy.server as server

        def fail_if_called(path):
            raise AssertionError(f"Unexpected recursive size scan for {path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "child").mkdir()
            monkeypatch.setattr(server, "get_dir_size", fail_if_called)

            response = client.get(f"/api/browse?path={tmpdir}")

        assert response.status_code == 200
        data = response.get_json()
        child = next(item for item in data["items"] if item["name"] == "child")
        assert child["is_dir"] is True
        assert child["size"] == 0
        assert child["size_formatted"] == "-"

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

    def test_filefy_download_user_agent_format(self):
        """Test Filefy download user-agent format includes version and platform."""
        from filefy.user_agent import build_filefy_user_agent

        user_agent = build_filefy_user_agent(
            version="2.0.16",
            system_name="Windows",
            machine="AMD64",
            architecture="64bit",
        )

        assert user_agent == "FileFy v2.0.16 (Windows NT; Win64; x64)"

    def test_remote_download_uses_filefy_user_agent(self, monkeypatch):
        """Test outbound remote downloads use the Filefy user-agent."""
        import filefy.server as server

        captured_headers = {}

        def fail_after_capturing_headers(*args, **kwargs):
            captured_headers.update(kwargs.get("headers") or {})
            raise server.requests.exceptions.Timeout("stop after headers")

        with tempfile.TemporaryDirectory() as tmpdir:
            task_id = "ua-test"
            server.download_tasks[task_id] = {"status": "pending"}
            monkeypatch.setattr(server.requests, "get", fail_after_capturing_headers)

            server.remote_download_task(
                task_id,
                "https://example.com/file.txt",
                tmpdir,
            )

            assert captured_headers["User-Agent"] == server.DOWNLOAD_USER_AGENT
            assert captured_headers["User-Agent"].startswith("FileFy v")
            server.download_tasks.clear()

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


class TestServerInfoAndTunnelParser:
    """Tests for the /api/server-info endpoint and the tunnel URL parser."""

    @pytest.fixture
    def client(self):
        from filefy import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_server_info_endpoint(self, client):
        response = client.get("/api/server-info")
        assert response.status_code == 200
        data = response.get_json()
        assert "version" in data
        assert "tunnel_status" in data
        assert "tunnel_url" in data
        assert "base_dir" in data

    def test_extract_tunnel_url_finds_quick_tunnel(self):
        from filefy.tunnel import extract_tunnel_url

        log = (
            "INF Your quick Tunnel has been created! Visit it at:\n"
            "INF https://random-words-1234.trycloudflare.com\n"
        )
        assert extract_tunnel_url(log) == (
            "https://random-words-1234.trycloudflare.com"
        )

    def test_extract_tunnel_url_returns_none_for_no_match(self):
        from filefy.tunnel import extract_tunnel_url

        assert extract_tunnel_url("nothing here") is None
        assert extract_tunnel_url("") is None
        assert extract_tunnel_url(None) is None

    def test_run_defaults_to_current_directory(self, monkeypatch):
        import filefy.server as server

        original_base_dir = server.BASE_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.chdir(tmpdir)
            monkeypatch.setattr(server.app, "run", lambda **kwargs: None)

            try:
                server.run(
                    host="127.0.0.1",
                    port=54321,
                    debug=False,
                    base_dir=None,
                    tunnel=False,
                )
                assert server.BASE_DIR == os.path.abspath(tmpdir)
                assert server.app.config["BASE_DIR"] == os.path.abspath(tmpdir)
            finally:
                server.BASE_DIR = original_base_dir
                server.app.config["BASE_DIR"] = original_base_dir

    def test_run_uses_explicit_base_directory(self, monkeypatch):
        import filefy.server as server

        original_base_dir = server.BASE_DIR
        with tempfile.TemporaryDirectory() as cwd:
            with tempfile.TemporaryDirectory() as target:
                monkeypatch.chdir(cwd)
                monkeypatch.setattr(server.app, "run", lambda **kwargs: None)

                try:
                    server.run(
                        host="127.0.0.1",
                        port=54321,
                        debug=False,
                        base_dir=target,
                        tunnel=False,
                    )
                    assert server.BASE_DIR == os.path.abspath(target)
                    assert server.app.config["BASE_DIR"] == os.path.abspath(target)
                finally:
                    server.BASE_DIR = original_base_dir
                    server.app.config["BASE_DIR"] = original_base_dir


class TestCompressEndpoint:
    """Tests for /api/compress."""

    @pytest.fixture
    def client(self):
        from filefy import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def _make_tree(self, root):
        """Create a small directory tree under ``root`` and return a list
        of (file_path, content) tuples for assertions."""
        Path(root, "a.txt").write_text("hello A")
        Path(root, "b.txt").write_text("hello B")
        sub = Path(root, "sub")
        sub.mkdir()
        Path(sub, "c.txt").write_text("nested")

    def _wait_for_compress(self, client, task_id, timeout=10):
        """Poll the progress endpoint until the compression task ends."""
        import time as _time

        deadline = _time.time() + timeout
        while _time.time() < deadline:
            resp = client.get(f"/api/compress-progress/{task_id}")
            assert resp.status_code == 200, resp.get_json()
            info = resp.get_json()
            if info["status"] in {"completed", "error", "cancelled"}:
                return info
            _time.sleep(0.05)
        raise AssertionError(f"Compression task {task_id} did not finish in time")

    def test_compress_zip_directory(self, client):
        import zipfile

        with tempfile.TemporaryDirectory() as tmp:
            self._make_tree(tmp)
            with tempfile.TemporaryDirectory() as dest:
                response = client.post(
                    "/api/compress",
                    json={
                        "sources": [tmp],
                        "destination": dest,
                        "name": "bundle",
                        "format": "zip",
                    },
                )
                assert response.status_code == 200, response.get_json()
                data = response.get_json()
                assert data["name"].endswith(".zip")
                assert "task_id" in data
                final = self._wait_for_compress(client, data["task_id"])
                assert final["status"] == "completed", final
                assert final["archive"]
                with zipfile.ZipFile(final["archive"]) as zf:
                    names = sorted(zf.namelist())
                # Use forward slashes for cross-platform comparison
                names_norm = sorted(n.replace("\\", "/") for n in names)
                assert any(n.endswith("a.txt") for n in names_norm)
                assert any(n.endswith("c.txt") for n in names_norm)

    def test_compress_tar_gz_multiple_files(self, client):
        import tarfile

        with tempfile.TemporaryDirectory() as tmp:
            file_a = Path(tmp, "one.txt")
            file_a.write_text("one")
            file_b = Path(tmp, "two.txt")
            file_b.write_text("two")
            with tempfile.TemporaryDirectory() as dest:
                response = client.post(
                    "/api/compress",
                    json={
                        "sources": [str(file_a), str(file_b)],
                        "destination": dest,
                        "name": "pair",
                        "format": "tar.gz",
                    },
                )
                assert response.status_code == 200
                data = response.get_json()
                assert data["name"].endswith(".tar.gz")
                final = self._wait_for_compress(client, data["task_id"])
                assert final["status"] == "completed", final
                with tarfile.open(final["archive"], "r:gz") as tf:
                    members = sorted(m.name for m in tf.getmembers())
                assert members == ["one.txt", "two.txt"]

    def test_compress_rejects_unsupported_format(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "x.txt").write_text("x")
            response = client.post(
                "/api/compress",
                json={
                    "sources": [tmp],
                    "destination": tmp,
                    "format": "rar",
                },
            )
            assert response.status_code == 400
            assert "Unsupported format" in response.get_json()["error"]

    def test_compress_requires_sources(self, client):
        response = client.post("/api/compress", json={"format": "zip"})
        assert response.status_code == 400
        assert "source" in response.get_json()["error"].lower()

    def test_compress_progress_reports_completion(self, client):
        """Progress endpoint should expose status, totals, and processed bytes."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "x.txt").write_text("hello world")
            with tempfile.TemporaryDirectory() as dest:
                response = client.post(
                    "/api/compress",
                    json={
                        "sources": [tmp],
                        "destination": dest,
                        "name": "p",
                        "format": "zip",
                    },
                )
                assert response.status_code == 200
                task_id = response.get_json()["task_id"]
                final = self._wait_for_compress(client, task_id)
                assert final["status"] == "completed"
                # The progress denominator must reflect the pre-scan and
                # the processed counter must reach the same value when
                # the task finishes.
                assert final["total_size"] >= len("hello world")
                assert final["processed_size"] >= final["total_size"]
                assert final["progress"] == 100.0

    def test_compress_progress_unknown_task(self, client):
        response = client.get("/api/compress-progress/no-such-task")
        assert response.status_code == 404


class TestDownloadEndpoint:
    """Tests for /api/download with absolute paths."""

    @pytest.fixture
    def client(self):
        from filefy import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_download_via_query_string_handles_absolute_path(self, client):
        """Absolute paths must round-trip via the ``?path=`` query form.

        The positional ``/api/download/<path>`` form is unsafe for
        absolute paths because Werkzeug's merge-slashes redirect drops
        the leading ``/`` and re-resolves the path against ``BASE_DIR``.
        """
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp, "file.txt")
            target.write_bytes(b"download-payload")
            response = client.get(f"/api/download?path={target}")
            assert response.status_code == 200
            assert response.data == b"download-payload"


class TestChunkedUpload:
    """Tests for the resumable chunked upload protocol."""

    @pytest.fixture
    def client(self):
        from filefy import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def _send_chunk(self, client, upload_id, payload, start, total):
        end = start + len(payload) - 1
        return client.put(
            f"/api/upload-chunk/{upload_id}",
            data=payload,
            headers={
                "Content-Range": f"bytes {start}-{end}/{total}",
                "Content-Type": "application/octet-stream",
            },
        )

    def test_full_upload_flow(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            payload = b"abcdefghijklmnopqrstuvwxyz" * 4  # 104 bytes
            init = client.post(
                "/api/upload-init",
                json={
                    "filename": "hello.bin",
                    "path": tmp,
                    "size": len(payload),
                },
            )
            assert init.status_code == 200, init.get_json()
            upload_id = init.get_json()["upload_id"]

            # Upload in three chunks.
            chunk1, chunk2, chunk3 = payload[:40], payload[40:80], payload[80:]
            r1 = self._send_chunk(client, upload_id, chunk1, 0, len(payload))
            assert r1.status_code == 200
            r2 = self._send_chunk(client, upload_id, chunk2, 40, len(payload))
            assert r2.status_code == 200

            # Status should report 80 received before the last chunk.
            status = client.get(f"/api/upload-status/{upload_id}")
            assert status.get_json()["received"] == 80

            r3 = self._send_chunk(client, upload_id, chunk3, 80, len(payload))
            assert r3.status_code == 200

            done = client.post(f"/api/upload-complete/{upload_id}")
            assert done.status_code == 200, done.get_json()
            final_path = done.get_json()["path"]
            assert Path(final_path).read_bytes() == payload

    def test_upload_cancel_removes_partial_file(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            payload = b"x" * 50
            init = client.post(
                "/api/upload-init",
                json={"filename": "drop.bin", "path": tmp, "size": len(payload)},
            )
            upload_id = init.get_json()["upload_id"]
            self._send_chunk(client, upload_id, payload[:20], 0, len(payload))

            cancel = client.delete(f"/api/upload-cancel/{upload_id}")
            assert cancel.status_code == 200
            # No leftover .filefy-upload file.
            leftovers = [
                p for p in os.listdir(tmp) if p.endswith(".filefy-upload")
            ]
            assert leftovers == []

    def test_upload_rejects_out_of_order_chunk(self, client):
        with tempfile.TemporaryDirectory() as tmp:
            payload = b"y" * 30
            init = client.post(
                "/api/upload-init",
                json={"filename": "ooo.bin", "path": tmp, "size": len(payload)},
            )
            upload_id = init.get_json()["upload_id"]
            # Skip directly to the second chunk to simulate a buggy client.
            response = self._send_chunk(
                client, upload_id, payload[10:20], 10, len(payload)
            )
            assert response.status_code == 409
            data = response.get_json()
            assert data["expected_offset"] == 0


class TestPauseResumeDownload:
    """Tests for the pause / resume / dismiss endpoints."""

    @pytest.fixture
    def client(self):
        from filefy import app

        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_pause_only_active_downloads(self, client):
        import filefy.server as server

        server.download_tasks.clear()
        server.download_tasks["abc"] = {
            "id": "abc",
            "status": "completed",
            "url": "https://example.com/x",
        }
        response = client.post("/api/pause-download/abc")
        assert response.status_code == 409
        server.download_tasks.clear()

    def test_pause_then_resume_marks_states(self, client):
        import filefy.server as server

        server.download_tasks.clear()
        server.download_tasks["abc"] = {
            "id": "abc",
            "status": "downloading",
            "url": "https://example.com/x",
            "destination": "/tmp",
        }
        response = client.post("/api/pause-download/abc")
        assert response.status_code == 200
        assert server.download_tasks["abc"]["paused"] is True

        # Move task to paused status (simulating worker exit).
        server.download_tasks["abc"]["status"] = "paused"

        # Patch the worker so we don't make real network calls.
        original = server.remote_download_task
        try:
            server.remote_download_task = lambda *args, **kwargs: None
            response = client.post("/api/resume-download/abc")
            assert response.status_code == 200
            assert server.download_tasks["abc"]["paused"] is False
        finally:
            server.remote_download_task = original
            server.download_tasks.clear()

    def test_dismiss_only_terminal_tasks(self, client):
        import filefy.server as server

        server.download_tasks.clear()
        server.download_tasks["live"] = {
            "id": "live",
            "status": "downloading",
        }
        server.download_tasks["done"] = {
            "id": "done",
            "status": "completed",
        }

        assert client.post("/api/dismiss-download/live").status_code == 409
        assert client.post("/api/dismiss-download/done").status_code == 200
        assert "done" not in server.download_tasks
        server.download_tasks.clear()
