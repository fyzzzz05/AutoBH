from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from collections import deque
from contextlib import ExitStack
from pathlib import Path

from rich import box
from rich.console import Console
from rich.table import Table
from rich.text import Text

from . import __version__, backends, service
from .storage import Registry, file_lock


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autobh", description="AutoBH · 上课 / TD / 博雅 / 阳光统一管理")
    parser.add_argument("--version", action="version", version=f"AutoBH {__version__}")
    parser.add_argument("--home", type=Path, default=None, help="人员档案目录，默认 ~/.autobh；原工具数据目录保持原样")
    commands = parser.add_subparsers(dest="command", required=True,
                                    metavar="{init,doctor,user,account,feature,service,run,logs,ui,class,boya,td,ygdk}")
    commands.add_parser("init", help="初始化 AutoBH 人员档案")
    ui = commands.add_parser("ui", help="打开本机 GUI 管理界面")
    ui.add_argument("--port", type=int, default=8765)
    ui.add_argument("--no-browser", action="store_true", help="启动服务但不自动打开浏览器")
    ui.add_argument("--demo", action="store_true", help="使用隔离的示例数据，不修改真实账号")
    doctor = commands.add_parser("doctor", help="本地模块和数据目录检查，不访问学校系统")
    doctor.add_argument("--json", action="store_true")
    users = commands.add_parser("user", help="统一人员档案，自动发现原工具账号")
    user_commands = users.add_subparsers(dest="action", required=True)
    add = user_commands.add_parser("add", help="添加/更新人员备注；绑定功能请用 account add")
    add.add_argument("username")
    add.add_argument("--name")
    add.add_argument("--group")
    remove = user_commands.add_parser("remove", help="删除人员档案及全部功能的本地账号绑定；保留原日志和缓存")
    remove.add_argument("username")
    listing = user_commands.add_parser("list", help="按功能或分组查看人员及启用状态")
    listing.add_argument("--feature", choices=backends.FEATURES)
    listing.add_argument("--group")
    listing.add_argument("--json", action="store_true")
    account = commands.add_parser("account", help="复用原工具的账号和密码存储")
    account_commands = account.add_subparsers(dest="action", required=True)
    account_add = account_commands.add_parser("add", help="绑定或更新账号，密码使用隐藏输入")
    account_add.add_argument("feature", choices=backends.FEATURES)
    account_add.add_argument("username")
    account_add.add_argument("--quick", choices=("学院路", "沙河"), help="TD 沿用原工具的快速机位和图片配置")
    account_add.add_argument("--campus", choices=("北京", "杭州"), default="北京")
    account_add.add_argument("--password-stdin", action="store_true")
    account_add.add_argument("--reuse-password", action="store_true", help="阳光功能复用已绑定的上课/博雅密码")
    account_add.add_argument("--unsafe-store-password", action="store_true", help="博雅钥匙串不可用时允许沿用原工具明文文件")
    feature = commands.add_parser("feature", help="按人员启用或暂停功能，不删除账号")
    feature_commands = feature.add_subparsers(dest="action", required=True)
    for action in ("enable", "disable"):
        child = feature_commands.add_parser(action)
        child.add_argument("feature", choices=backends.FEATURES)
        child.add_argument("--user", required=True, help="学号")
    services = commands.add_parser("service", help="分别运行各功能的原有后台循环")
    service_commands = services.add_subparsers(dest="action", required=True)
    for action in ("start", "stop", "status"):
        child = service_commands.add_parser(action)
        child.add_argument("--feature", choices=("all", *backends.FEATURES), default="all")
        child.add_argument("--json", action="store_true")
    run = commands.add_parser("run", help="立即执行单轮真实自动化；详情见各工具日志")
    run.add_argument("--once", action="store_true", required=True)
    run.add_argument("--feature", choices=("all", *backends.FEATURES), default="all")
    run.add_argument("--user", help="只执行该人员已启用的功能")
    logs = commands.add_parser("logs", help="读取原工具业务日志或 AutoBH 后台启动日志")
    logs.add_argument("--feature", choices=backends.FEATURES, required=True)
    logs.add_argument("--worker", action="store_true", help="查看后台启动/异常输出")
    logs.add_argument("--lines", type=int, default=50)
    for name in backends.FEATURES:
        native = commands.add_parser(name, add_help=False, help=f"转发 {name} 原 CLI，例如 autobh {name} --help")
        native.add_argument("args", nargs=argparse.REMAINDER)
    hidden = commands.add_parser("_worker", help=argparse.SUPPRESS)
    hidden.add_argument("feature", choices=backends.FEATURES)
    hidden.add_argument("token")
    commands._choices_actions = [action for action in commands._choices_actions if action.dest != "_worker"]
    return parser


def people(registry: Registry) -> list[dict]:
    merged = {username: {"username": username, **metadata, "features": {}}
              for username, metadata in registry.people().items()}
    for feature in backends.FEATURES:
        if not backends.available(feature):
            continue
        for account in backends.accounts(feature):
            row = merged.setdefault(account["username"], {"username": account["username"],
                                                         "name": "", "group": "", "features": {}})
            row["features"][feature] = {key: value for key, value in account.items() if key != "username"}
    return [merged[key] for key in sorted(merged)]


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def remove_person(registry: Registry, username: str, quiet: bool = False):
    validate_username(username)
    # An uninstalled optional TD package must not hide a surviving TD binding.
    if not backends.available("td"):
        from .storage import read_json
        raw = read_json(backends.native_home("td") / "users.json", {})
        if username in raw.get("users", {}):
            backends.require("td")
    removed = []
    with ExitStack() as locks:
        # Acquire all relevant locks before modifying any feature's account data.
        installed = [feature for feature in backends.FEATURES if backends.available(feature)]
        for feature in installed:
            locks.enter_context(file_lock(backends.native_home(feature) / "run" / "autobh" / "accounts.lock"))
        for feature in installed:
            if not any(row["username"] == username for row in backends.accounts(feature)):
                continue
            try:
                backends.remove_account(feature, username)
                removed.append(feature)
            except (ValueError, OSError, RuntimeError, ImportError) as exc:
                completed = "、".join(removed) or "无"
                raise RuntimeError(f"删除 {feature} 账号失败：{exc}；已删除功能：{completed}。人员档案保留，可修复后重试。") from exc
        profile_removed = registry.remove(username)
    if not removed and not profile_removed:
        raise ValueError(f"未找到人员：{username}")
    details = "、".join(removed) if removed else "无功能绑定"
    if not quiet:
        print(f"已删除人员 {username}（{details}）及姓名/分组。后台下一轮读取生效，已发出的请求会继续完成。")


def dispatch(args, registry: Registry) -> int:
    command = args.command
    if command in backends.FEATURES:
        return backends.passthrough(command, args.args)
    if command == "_worker":
        service.worker(args.feature, args.token)
    elif command == "ui":
        from .gui import serve
        if not 0 <= args.port <= 65535:
            raise ValueError("端口必须在 0–65535 之间")
        serve(registry.root, args.port, not args.no_browser, args.demo)
    elif command == "init":
        registry.root.mkdir(parents=True, exist_ok=True)
        with file_lock(registry.root / "people.lock"):
            if not registry.path.exists():
                from .storage import atomic_json
                atomic_json(registry.path, {})
        print(f"AutoBH 已初始化：{registry.root}\n原有账号通过 user list 自动发现。")
    elif command == "doctor":
        checks = [{"feature": feature, "module_available": backends.available(feature),
                   "integration": "复用原工具接口和调度",
                   "home": str(backends.native_home(feature))}
                  for feature in backends.FEATURES]
        if args.json:
            emit({"name": "AutoBH", "version": __version__, "home": str(registry.root), "checks": checks})
        else:
            print(f"AutoBH {__version__} · 人员档案：{registry.root}")
            for check in checks:
                print(f"{check['feature']}: {'可用' if check['module_available'] else '未安装'} · {check['integration']}")
                if check["home"]:
                    print(f"  数据：{check['home']}")
    elif command == "user":
        if args.action == "add":
            validate_username(args.username)
            registry.upsert(args.username, args.name, args.group)
            print(f"人员档案已保存：{args.username}；绑定功能：autobh account add class|boya|td|ygdk {args.username}")
        elif args.action == "remove":
            remove_person(registry, args.username)
        else:
            rows = [row for row in people(registry)
                    if (not args.feature or args.feature in row["features"])
                    and (args.group is None or row["group"] == args.group)]
            if args.json:
                emit(rows)
            elif not rows:
                print("暂无人员。可先 user add，或 account add 绑定原工具账号。")
            else:
                table = Table(box=box.SIMPLE, header_style="bold", pad_edge=False,
                              show_edge=False)
                table.add_column("学号", no_wrap=True)
                table.add_column("姓名", overflow="fold")
                table.add_column("分组", overflow="fold")
                for heading in ("上课", "博雅", "TD", "阳光"):
                    table.add_column(heading, no_wrap=True)
                for row in rows:
                    states = []
                    for feature in backends.FEATURES:
                        if feature not in row["features"]:
                            states.append(Text("未绑定", style="dim"))
                        elif row["features"][feature]["enabled"]:
                            states.append(Text("启用", style="green"))
                        else:
                            states.append(Text("暂停", style="yellow"))
                    table.add_row(Text(row["username"]), Text(row["name"] or "-"),
                                  Text(row["group"] or "-"), *states)
                Console(highlight=False).print(table)
    elif command == "account":
        validate_username(args.username)
        backends.require(args.feature)
        password = ""
        if args.reuse_password and args.feature != "ygdk":
            raise ValueError("--reuse-password 仅用于阳光功能")
        if args.feature != "td" and not args.reuse_password:
            password = sys.stdin.readline().rstrip("\r\n") if args.password_stdin else getpass.getpass("学校账号密码：")
            if not password:
                raise ValueError("密码不能为空")
        with file_lock(backends.native_home(args.feature) / "run" / "autobh" / "accounts.lock"):
            backends.add_account(args.feature, args.username, password, args.campus, args.unsafe_store_password, args.quick)
        registry.upsert(args.username, None, None)
        print(f"已绑定 {args.feature}：{args.username}。密码存储沿用原工具。")
    elif command == "feature":
        with file_lock(backends.native_home(args.feature) / "run" / "autobh" / "accounts.lock"):
            backends.set_enabled(args.feature, args.user, args.action == "enable")
        print(f"{args.user} · {args.feature} · {'启用' if args.action == 'enable' else '暂停'}；后台下一轮读取生效，已发出的请求会继续完成。")
    elif command == "service":
        errors = False
        results = []
        for feature in selected_features(args.feature):
            try:
                if feature == "td" and args.feature == "all" and not backends.available("td"):
                    results.append({"feature": "td", "status": "unavailable", "reason": "可选依赖未安装，安装 .[td] 后可用"})
                    continue
                backends.require(feature)
                if args.action == "start":
                    result = service.start(feature, registry.root)
                elif args.action == "stop":
                    result = service.stop(feature)
                else:
                    result = service.status(feature)
                result["enabled_users"] = sum(bool(row["enabled"]) for row in backends.accounts(feature))
                results.append(result)
            except (ValueError, OSError, RuntimeError, ImportError) as exc:
                results.append({"feature": feature, "status": "error", "reason": str(exc)})
                errors = True
        if args.json:
            emit(results)
        else:
            for result in results:
                print(f"{result['feature']}: {result['status']} · {result.get('reason', '') or '启用人数 ' + str(result.get('enabled_users', 0))}")
                if result.get("pid"):
                    print(f"  PID {result['pid']} · 后台输出：{result['log']}")
                if result.get("stop_requested"):
                    print("  已请求停止，等待当前网络请求结束。")
        return 1 if errors else 0
    elif command == "run":
        results = []
        errors = False
        matched = False
        for feature in selected_features(args.feature):
            try:
                if feature == "td" and args.feature == "all" and not backends.available("td"):
                    results.append({"feature": "td", "status": "unavailable", "reason": "可选依赖未安装"})
                    continue
                if args.user and args.feature == "all" and not any(
                    row["username"] == args.user and row["enabled"] for row in backends.accounts(feature)
                ):
                    continue
                matched = True
                results.append(service.run_once(feature, args.user))
            except (ValueError, OSError, RuntimeError, ImportError) as exc:
                errors = True
                results.append({"feature": feature, "status": "error", "reason": str(exc)})
        if not matched and not errors:
            raise ValueError(f"{args.user} 没有已启用的功能")
        emit(results)
        return 1 if errors else 0
    elif command == "logs":
        if args.lines < 1:
            raise ValueError("--lines 必须大于 0")
        if args.worker:
            paths = [service.run_dir(args.feature) / "worker.log"]
        elif args.feature == "td":
            paths = sorted((backends.native_home("td") / "logs").glob("*-daytime-log.txt"))[-1:]
        elif args.feature == "ygdk":
            print("阳光后台每 30 分钟同步一次；每人最近的刷新状态可在 App 查看。")
            return 0
        elif args.feature == "boya":
            paths = [backends.native_home("boya") / "logs" / "autoboya.log"]
        else:
            paths = sorted((backends.native_home("class") / "log").glob("*.txt"))[-1:]
        if not paths or not paths[0].exists():
            print("暂无日志。")
        else:
            with paths[0].open(encoding="utf-8", errors="replace") as stream:
                print("".join(deque(stream, maxlen=args.lines)), end="")
    return 0


def validate_username(username: str):
    if not username.strip() or username != username.strip() or any(ord(char) < 32 for char in username):
        raise ValueError("学号不能为空，不能含首尾空格或控制字符")


def selected_features(feature: str):
    return backends.FEATURES if feature == "all" else (feature,)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    # argparse otherwise consumes native --help/unknown options before REMAINDER.
    # Parse only the common prefix, then pass every native token unchanged.
    prefix = 0
    while prefix < len(argv):
        if argv[prefix] == "--home":
            prefix += 2
        elif argv[prefix].startswith("--home="):
            prefix += 1
        else:
            break
    if prefix < len(argv) and argv[prefix] in backends.FEATURES:
        raw = argv[prefix + 1:]
        args = parser.parse_args(argv[:prefix + 1])
        args.args = raw
    else:
        args = parser.parse_args(argv)
    root = (args.home or Path(os.environ.get("AUTOBH_HOME", str(Path.home() / ".autobh")))).expanduser().resolve()
    try:
        return dispatch(args, Registry(root))
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        print(f"AutoBH：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAutoBH：已中断", file=sys.stderr)
        return 130
