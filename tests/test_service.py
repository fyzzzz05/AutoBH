import os

import pytest

from autobh import backends, service
from autobh.storage import BusyError, file_lock


def test_process_lock_releases_after_exception(tmp_path):
    path = tmp_path / "test.lock"
    with pytest.raises(RuntimeError):
        with file_lock(path):
            with pytest.raises(BusyError):
                with file_lock(path):
                    pass
            raise RuntimeError("test")
    with file_lock(path):
        pass


def test_no_users_does_not_start_background(tmp_path):
    assert service.start("class", tmp_path)["status"] == "skipped"
    assert service.status("class")["status"] == "stopped"


def test_run_once_refuses_a_concurrent_worker():
    with file_lock(service.run_dir("class") / "worker.lock"):
        with pytest.raises(BusyError):
            service.run_once("class")


@pytest.mark.parametrize("feature", ["class", "boya", "td"])
def test_real_background_start_idempotent_stop_and_restart(feature, tmp_path, monkeypatch):
    if feature == "td":
        pytest.importorskip("auto_td")
        store = backends.td_store()
        store.initialize()
        store.save_users({"1": {"student_id": "1", "entrance_machine_id": 1, "exit_machine_id": 2,
                                "entrance_image": "a.jpg", "exit_image": "b.jpg"}})
    elif feature == "class":
        backends.class_manager().add_user("1", "fake-secret")
    else:
        from autoboya.models import UserRecord
        backends.boya_store().upsert_user(UserRecord("1"))

    # Child process runs the real lifecycle and original scheduling loops,
    # with only remote operations stubbed. No live account or network is used.
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text('''
import socket
def forbidden(*args, **kwargs):
    raise AssertionError("Network forbidden in background test")
socket.socket.connect = forbidden
from autosign_cli.runtime.scheduler import AutoSignRunner
AutoSignRunner.process_once = lambda self: None
from autoboya.scheduler import AutomationRunner
AutomationRunner.refresh_once = lambda self: None
AutomationRunner.scan_once = lambda self: []
try:
    import auto_td.scheduler as td
    from auto_td.models import BatchResult
    td.run_scheduler_once = lambda *args, **kwargs: BatchResult([])
    td.flush_telemetry_queue = lambda *args, **kwargs: None
except ImportError:
    pass
''', encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(guard) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    try:
        first = service.start(feature, tmp_path / "registry")
        assert first["status"] == "running"
        assert first["pid"] > 0
        assert service.start(feature, tmp_path / "other-registry")["pid"] == first["pid"]
        assert service.stop(feature)["status"] == "stopped"
        assert service.stop(feature)["status"] == "stopped"
        second = service.start(feature, tmp_path / "registry")
        assert second["status"] == "running"
        assert second["pid"] != first["pid"]
    finally:
        service.stop(feature)


def test_native_running_is_reported_without_starting_another_worker(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "native_pid", lambda feature: os.getpid())
    result = service.start("class", tmp_path)
    assert result["status"] == "native-running"
    with pytest.raises(ValueError, match="原工具启动"):
        service.stop("class")
