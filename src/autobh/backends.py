from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

from .runtime import native_command, subprocess_environment

FEATURES = ("class", "boya", "td", "ygdk")


def native_home(feature: str) -> Path:
    key, default = {"class": ("AUTOSIGN_HOME", ".autosign"),
                    "boya": ("AUTOBOYA_HOME", ".autoboya"),
                    "td": ("AUTOTD_HOME", ".autoTD"),
                    "ygdk": ("AUTOBH_YGDK_HOME", ".autobh/ygdk")}[feature]
    return Path(os.environ.get(key, str(Path.home() / default))).expanduser().resolve()


def available(feature: str) -> bool:
    module = {"class": "autosign_cli", "boya": "autoboya", "td": "auto_td", "ygdk": "autobh.ygdk"}[feature]
    return importlib.util.find_spec(module) is not None


def require(feature: str):
    if not available(feature):
        if feature == "td":
            raise ValueError("TD 本地仓库只有 README；请安装 TD 可选依赖：python -m pip install -e '.[td]'")
        raise ValueError(f"{feature} 模块不可用，请安装 AutoBH：python -m pip install -e .")


def class_manager():
    from autosign_cli.config.manager import ConfigManager
    return ConfigManager(native_home("class"))


def boya_store():
    from autoboya.storage import AutoBoyaStore
    return AutoBoyaStore(native_home("boya"))


def td_store():
    from auto_td.storage import AppStorage
    return AppStorage(native_home("td"))


def td_switches() -> dict:
    from .storage import read_json
    return read_json(native_home("td") / "run" / "autobh" / "enabled.json", {})


def accounts(feature: str) -> list[dict]:
    require(feature)
    if feature == "ygdk":
        from .ygdk import accounts as sunshine_accounts
        return [{"username": username, "enabled": row.get("enabled", True)} for username, row in sunshine_accounts().items()]
    if feature == "class":
        # Reading status should not initialize or change native configuration.
        path = native_home(feature) / "config.yaml"
        if not path.exists():
            return []
        import yaml
        rows = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("accounts", [])
        if not isinstance(rows, list):
            rows = []
        return [{"username": str(row["username"]), "enabled": row.get("enabled", True)}
                for row in rows if isinstance(row, dict) and row.get("username")]
    if feature == "boya":
        return [{"username": row.username, "enabled": row.enabled, "campus": row.campus}
                for row in boya_store().user_records()]
    switches = td_switches()
    return [{"username": str(username), "enabled": switches.get(str(username), True)}
            for username in td_store().load_users()]


def add_account(feature: str, username: str, password: str, campus: str, unsafe: bool, quick: str | None = None):
    require(feature)
    if feature == "ygdk":
        from .ygdk import bind
        return bind(username, password, unsafe)
    if feature == "class":
        # Native AutoSign stores passwords in its 0600 config, as before.
        class_manager().add_user(username, password)
    elif feature == "boya":
        from autoboya.models import UserRecord
        from autoboya.storage import try_store_keyring_password
        store = boya_store()
        old = store.get_user(username)
        in_keyring = try_store_keyring_password(username, password)
        if not in_keyring and not unsafe:
            raise ValueError("系统钥匙串不可用；可显式添加 --unsafe-store-password 使用原博雅本地密码文件")
        store.init()
        if not in_keyring:
            store.save_unsafe_password(username, password)
        store.upsert_user(UserRecord(username, "keyring" if in_keyring else "unsafe-file",
                                     not in_keyring, old.enabled if old else True, campus))
    else:
        if quick is None:
            raise ValueError("添加 TD 账号需要 --quick 学院路|沙河；先通过 autobh td image add 导入图片")
        from auto_td.quick import build_quick_user
        store = td_store()
        store.initialize()
        # Native user update supports machine/image/round settings. Avoid replacing
        # an existing user's customized settings with random quick defaults.
        if store.get_user(username):
            raise ValueError("TD 账号已存在；使用 autobh td user update 修改，或 feature enable td 启用")
        store.save_user(build_quick_user(store, username, quick))


def set_enabled(feature: str, username: str, enabled: bool):
    require(feature)
    if feature == "ygdk":
        from .ygdk import set_enabled as sunshine_enabled
        return sunshine_enabled(username, enabled)
    if feature == "class":
        manager = class_manager()
        config = manager.load()
        found = False
        for row in config["accounts"]:
            if isinstance(row, dict) and str(row.get("username")) == username:
                row["enabled"] = enabled
                found = True
        if not found:
            raise ValueError(f"{username} 尚未绑定上课账号，请先 account add class")
        manager.save(config)
    elif feature == "boya":
        store = boya_store()
        user = store.get_user(username)
        if user is None:
            raise ValueError(f"{username} 尚未绑定博雅账号，请先 account add boya")
        user.enabled = enabled
        store.upsert_user(user)
    else:
        from .storage import atomic_json
        if username not in td_store().load_users():
            raise ValueError(f"{username} 尚未绑定 TD 账号，请先 account add td")
        switches = td_switches()
        switches[username] = enabled
        atomic_json(native_home("td") / "run" / "autobh" / "enabled.json", switches)


def remove_account(feature: str, username: str) -> bool:
    """Keep native deletion semantics, including retained logs and caches."""
    require(feature)
    if feature == "ygdk":
        from .ygdk import remove
        return remove(username)
    if feature == "class":
        return class_manager().delete_user(username)
    if feature == "boya":
        from .boya_operations import operation_lock
        from .boya_policy import path as policy_path
        from .storage import atomic_json, read_json
        store = boya_store()
        with operation_lock(store):
            policies = read_json(policy_path(store), {})
            if username in policies:
                del policies[username]
                atomic_json(policy_path(store), policies)
            return store.remove_user(username)
    removed = td_store().delete_user(username)
    switches = td_switches()
    if username in switches:
        from .storage import atomic_json
        del switches[username]
        atomic_json(native_home("td") / "run" / "autobh" / "enabled.json", switches)
    return removed


def passthrough(feature: str, args: list[str]) -> int:
    require(feature)
    if args[:1] == ["--"]:
        args = args[1:]
    if args[:1] and args[0] in {"run", "run-once", "run-worker", "--daemon-worker"}:
        from .service import busy
        if busy(feature):
            raise ValueError(f"{feature} 的 AutoBH 后台/单轮任务正在执行，请先 autobh service stop --feature {feature}")
    if feature in {"boya", "td"} and args in (["run"], ["run-once"], ["run-worker"], ["run", "--once"], ["--daemon-worker"]):
        from . import service
        root = Path(os.environ.get("AUTOBH_HOME", str(Path.home() / ".autobh")))
        if args in (["run-once"], ["run", "--once"]):
            result = service.run_once(feature)
        else:
            result = service.start(feature, root)
        import json
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if feature in {"boya", "td"} and args in (["stop"], ["--stop"]):
        from . import service
        if service.status(feature)["status"] == "running":
            service.stop(feature)
            print("已请求停止 AutoBH 后台")
            return 0
    if feature == "boya" and args[:1] == ["drop"] and "--yes" in args and "--help" not in args:
        import argparse
        from .boya_operations import drop_user_course
        parser = argparse.ArgumentParser(prog="autobh boya drop")
        parser.add_argument("course_id", type=int)
        scope = parser.add_mutually_exclusive_group(required=True)
        scope.add_argument("--user")
        scope.add_argument("--all-users", action="store_true")
        parser.add_argument("--yes", action="store_true", required=True)
        parsed = parser.parse_args(args[1:])
        for username in ([parsed.user] if parsed.user else [row['username'] for row in accounts('boya')]):
            drop_user_course(username, parsed.course_id)
        print("已退选，并排除自动选回")
        return 0
    command = native_command(feature)
    if feature == "class":
        command += ["--home", str(native_home(feature))]
    return subprocess.call(command + (args or ["--help"]), env=subprocess_environment())


def runner(feature: str, username: str | None = None):
    require(feature)
    if feature == "ygdk":
        from .ygdk import SunshineRunner
        return SunshineRunner(username)
    if feature == "class":
        from autosign_cli.config.manager import ConfigManager
        from autosign_cli.runtime.scheduler import AutoSignRunner
        from autosign_cli.cli import _build_logger

        class ScopedManager(ConfigManager):
            def load(self):
                data = super().load()
                data["accounts"] = [row for row in data["accounts"]
                                    if isinstance(row, dict) and row.get("enabled", True) and
                                    (username is None or str(row.get("username")) == username)]
                return data

        manager = ScopedManager(native_home(feature))
        return AutoSignRunner(manager, _build_logger(manager))
    if feature == "boya":
        from autoboya.storage import AutoBoyaStore
        from .boya_runner import BoyaRunner
        from autoboya.logging import configure_logging

        class ScopedStore(AutoBoyaStore):
            def user_records(self):
                return [row for row in super().user_records()
                        if username is None or row.username == username]

        store = ScopedStore(native_home(feature))
        store.init()
        configure_logging(store, console=False)
        return BoyaRunner(store)
    from .td import TDRunner
    return TDRunner(username)


def run_once(feature: str, username: str | None = None):
    rows = accounts(feature)
    if username is not None and not any(row["username"] == username and row["enabled"] for row in rows):
        raise ValueError(f"{username} 未绑定 {feature} 或功能已暂停")
    active = [row for row in rows if row["enabled"] and (username is None or row["username"] == username)]
    if not active:
        return {"feature": feature, "status": "skipped", "reason": "没有启用的账号"}
    instance = runner(feature, username)
    if feature == "class":
        instance.process_once()
        return {"feature": feature, "status": "completed", "note": "执行轮次已结束，签到结果见原工具日志"}
    results = instance.run_once()
    if feature == "td":
        return {"feature": feature, "status": "completed", "results": [row.__dict__ for row in results.results]}
    return {"feature": feature, "status": "completed", "results": [row.__dict__ for row in results]}
