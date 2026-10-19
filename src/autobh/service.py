from __future__ import annotations

import os
import csv
import io
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from . import backends
from .storage import BusyError, atomic_json, file_lock, read_json
from .runtime import autobh_command, subprocess_environment


def run_dir(feature: str) -> Path:
    # Lock by native data directory, even if two AutoBH registries differ.
    return backends.native_home(feature) / "run" / "autobh"


def busy(feature: str) -> bool:
    try:
        with file_lock(run_dir(feature) / "worker.lock"):
            return False
    except BusyError:
        return True


def native_pid(feature: str) -> int | None:
    if feature == "ygdk":
        return None
    if feature == "td":
        from auto_td.background import read_pid_file, is_process_running
        pid = read_pid_file(backends.native_home("td") / "autotd.pid")
        return pid if pid and is_process_running(pid) else None
    path = backends.native_home(feature) / "run" / ("autosign.pid" if feature == "class" else "autoboya.pid")
    try:
        pid = int(path.read_text().strip())
        if pid <= 0:
            return None
        if os.name == "nt":
            # os.kill(pid, 0) can terminate a process on Windows.
            result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                    capture_output=True, text=True, errors="replace", check=True)
            return pid if any(len(row) > 1 and row[1] == str(pid)
                              for row in csv.reader(io.StringIO(result.stdout))) else None
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def status(feature: str) -> dict:
    directory = run_dir(feature)
    running = busy(feature)
    data = read_json(directory / "worker.json", {})
    native = native_pid(feature)
    return {"feature": feature, "status": "running" if running else ("native-running" if native else "stopped"),
            "pid": data.get("pid") if running else native,
            "stop_requested": running and (directory / "stop.request").exists(),
            "home": str(backends.native_home(feature)),
            "log": str(directory / "worker.log")}


def start(feature: str, home: Path) -> dict:
    backends.require(feature)
    directory = run_dir(feature)
    with file_lock(directory / "control.lock"):
        current = status(feature)
        if current["status"] != "stopped":
            return current
        if not any(row["enabled"] for row in backends.accounts(feature)):
            return {"feature": feature, "status": "skipped", "reason": "没有启用的账号"}
        token = uuid.uuid4().hex
        (directory / "stop.request").unlink(missing_ok=True)
        atomic_json(directory / "worker.json", {"token": token, "pid": None, "state": "starting"})
        command = autobh_command("--home", str(home), "_worker", feature, token)
        kwargs = {"stdin": subprocess.DEVNULL, "stderr": subprocess.STDOUT, "env": subprocess_environment()}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        with (directory / "worker.log").open("a", encoding="utf-8") as log:
            os.chmod(directory / "worker.log", 0o600)
            process = subprocess.Popen(command, stdout=log, **kwargs)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            data = read_json(directory / "worker.json", {})
            if data.get("token") == token and data.get("state") == "running" and busy(feature):
                return status(feature)
            if process.poll() is not None:
                raise RuntimeError(f"{feature} 后台启动失败，查看 {directory / 'worker.log'}")
            time.sleep(0.05)
        raise RuntimeError(f"{feature} 后台尚未就绪，查看 service status 和 {directory / 'worker.log'}")


def stop(feature: str) -> dict:
    directory = run_dir(feature)
    with file_lock(directory / "control.lock"):
        current = status(feature)
        if current["status"] == "native-running":
            stop_command = "autobh td --stop" if feature == "td" else f"autobh {feature} stop"
            raise ValueError(f"{feature} 由原工具启动，请执行 {stop_command}；AutoBH 不会向不受管理的 PID 发送信号")
        if current["status"] == "stopped":
            return current
        # Tokenized cooperative stop avoids signaling a stale/recycled PID.
        data = read_json(directory / "worker.json", {})
        atomic_json(directory / "stop.request", {"token": data.get("token")})
        deadline = time.monotonic() + 5
        while busy(feature) and time.monotonic() < deadline:
            time.sleep(0.05)
        return status(feature)


def worker(feature: str, token: str) -> None:
    directory = run_dir(feature)
    with file_lock(directory / "worker.lock"):
        if native_pid(feature):
            raise RuntimeError("原工具后台已经运行，请先停止原后台")
        event = threading.Event()
        finished = threading.Event()

        def monitor():
            while not finished.wait(0.2):
                if read_json(directory / "stop.request", {}).get("token") == token:
                    event.set()
                    return

        instance = backends.runner(feature)
        # Ready only after imports, configuration, and runner setup succeed.
        atomic_json(directory / "worker.json", {"token": token, "pid": os.getpid(), "state": "running"})
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        try:
            instance.run_forever(stop_event=event)
        finally:
            finished.set()
            thread.join(timeout=1)
            atomic_json(directory / "worker.json", {"token": token, "pid": None, "state": "stopped"})
            (directory / "stop.request").unlink(missing_ok=True)


def run_once(feature: str, username: str | None = None):
    with file_lock(run_dir(feature) / "worker.lock"):
        if native_pid(feature):
            raise ValueError(f"{feature} 原后台正在运行，请先停止，避免并发执行")
        return backends.run_once(feature, username)
