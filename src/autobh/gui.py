"""Loopback-only GUI server; operations reuse the existing CLI/application layer."""
from __future__ import annotations

import base64
import copy
import errno
import hashlib
import http.client
import json
import mimetypes
import secrets
import subprocess
import sys
import tempfile
import threading
import webbrowser
from collections import deque
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo

from . import backends, service
from .appearance import MODES, read_appearance, save_appearance
from .storage import Registry, file_lock, read_json
from .runtime import autobh_command, subprocess_environment
from .progress import boya_progress, progress_text, td_progress, read_boya_cache

LABELS = {"class": "上课签到", "td": "TD 锻炼", "boya": "博雅课程", "ygdk": "阳光打卡"}
WEB_ROOT = Path(__file__).parent / "web"


def timetable_payload(sessions, now: datetime, login_mode: str):
    local = now.astimezone(ZoneInfo("Asia/Shanghai"))
    monday = local.date() - timedelta(days=local.weekday())
    return {"type": "timetable", "title": "本周课表", "timezone": "Asia/Shanghai",
            "weekStart": monday.isoformat(), "weekEnd": (monday + timedelta(days=6)).isoformat(),
            "now": local.isoformat(), "loginMode": login_mode,
            "sessions": [session.to_dict() for session in sessions]}


def demo_timetable():
    from autosign_cli.core.models import ClassSession
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    monday = now.date() - timedelta(days=now.weekday())
    courses = [
        (0, "AI赋能英语实务", "08:00", "09:35", "1"),
        (0, "交通安全工程", "09:50", "11:25", "1"),
        (0, "自动控制原理B", "14:00", "15:35", "0"),
        (1, "智能交通控制", "09:50", "11:25", "1"),
        (1, "智能车辆运用基础", "15:50", "18:15", "1"),
        (1, "智能交通系统", "19:00", "20:35", "1"),
        (2, "智能交通控制", "14:00", "15:35", "1"),
        (3, "交通规划", "09:50", "11:25", "1"),
        (3, "智能交通控制", "14:00", "15:35", "0"),
        (3, "职业生涯规划与发展", "15:50", "17:25", "0"),
        (3, "智能交通系统", "19:00", "20:35", "0"),
        (4, "社会主义发展史", "08:00", "09:35", "0"),
        (4, "自动控制原理B", "14:00", "15:35", "0"),
    ]
    sessions = []
    for index, (day, name, start, end, status) in enumerate(courses):
        date = (monday + timedelta(days=day)).isoformat()
        sessions.append(ClassSession(str(index), str(index), name, "",
                                     datetime.fromisoformat(f"{date}T{start}:00+08:00"),
                                     datetime.fromisoformat(f"{date}T{end}:00+08:00"), status))
    return timetable_payload(sessions, now, "direct")


def load_boya_cache():
    return read_boya_cache(backends.boya_store())


def demo_boya_progress():
    tomorrow = datetime.now(ZoneInfo("Asia/Shanghai")) + timedelta(days=2)
    return boya_progress({"validCount": 4, "statistical": {"60|博雅课程": {
        "55|德育": {"assessmentCount": 2, "completeAssessmentCount": 2, "failAssessmentCount": 0, "undoneAssessmentCount": 0},
        "56|美育": {"assessmentCount": 1, "completeAssessmentCount": 1, "failAssessmentCount": 0, "undoneAssessmentCount": 0},
        "57|劳动教育": {"assessmentCount": 2, "completeAssessmentCount": 1, "failAssessmentCount": 1, "undoneAssessmentCount": 0},
        "58|安全健康": {"assessmentCount": 1, "completeAssessmentCount": 1, "failAssessmentCount": 0, "undoneAssessmentCount": 1},
    }}}, [
        {"id": 4, "courseName": "校园安全与健康讲座（示例）", "courseStartDate": tomorrow.isoformat(), "courseEndDate": (tomorrow + timedelta(hours=2)).isoformat(), "courseCancelEndDate": (tomorrow - timedelta(hours=1)).isoformat(), "coursePosition": "沙河", "kindName": "安全健康", "signInfo": None},
        {"id": 1, "courseName": "北航科协大讲堂2026年第六期：仿生水空跨介质机器人关键技术", "courseStartDate": "2026-09-23 14:30:00", "courseEndDate": "2026-09-23 15:50:00", "coursePosition": "新主楼会议中心第二报告厅", "kindName": "德育", "pass": 1, "signInfo": {"signIn": {"inSignArea": True}}},
        {"id": 2, "courseName": "北航红船星河宣讲团·周末理论课堂——“循迹溯源悟思想，守正创新谱新篇”宣讲（沙河校区）", "courseStartDate": "2026-09-19 15:00:00", "courseEndDate": "2026-09-19 16:00:00", "coursePosition": "沙河J3-310", "kindName": "德育", "pass": 1, "signInfo": None},
        {"id": 3, "courseName": "音乐鉴赏", "courseStartDate": "2026-09-18 14:00:00", "courseEndDate": "2026-09-18 16:00:00", "coursePosition": "学院路", "kindName": "美育", "pass": 1, "signInfo": {"signIn": {"inSignArea": True}, "signOut": {"inSignArea": True}}},
    ])


def demo_sunshine():
    from .ygdk import AUTH_ENTRY
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return {"title": "阳光打卡", "updatedAt": now.isoformat(), "authorization": {"loginUrl": AUTH_ENTRY, "required": False},
            "summary": {"termCount": 8, "termTarget": 16, "weekCount": 2, "weekTarget": 4, "dayCount": 1, "monthCount": 5, "monthTarget": 8, "termName": "本学期"},
            "items": [{"id": 1, "name": "跑步"}, {"id": 2, "name": "羽毛球"}],
            "records": [{"id": 1, "itemName": "跑步", "startTime": (now - timedelta(hours=2)).isoformat(), "endTime": (now - timedelta(hours=1)).isoformat(), "place": "沙河操场", "state": 1}],
            "page": 1, "total": 1, "hasMore": False}


def demo_state():
    names = ["张三", "李四", "王同学", "陈同学", "刘同学", "赵同学", "林同学", "吴同学", "孙同学", "周同学", "许同学"]
    people = [{"username": str(23370001 + i), "name": name,
               "group": "学院路" if i % 2 == 0 else "沙河",
               "features": {feature: {"enabled": True} for feature in backends.FEATURES}}
              for i, name in enumerate(names)]
    people[0]["group"] = ""
    for index, person in enumerate(people):
        sunshine = demo_sunshine()
        person["features"]["ygdk"]["counts"] = {**sunshine["summary"], "updatedAt": sunshine["updatedAt"]}
        completed = 3 if index % 6 == 0 else 1
        person["features"]["td"]["progress"] = f"本学期已完成 {19 + index} 次 · 今日 {completed} / 3 次"
        person["features"]["td"]["counts"] = {"totalCount": 19 + index, "completedToday": completed, "targetToday": 3, "updatedAt": "2026-10-15T13:03:36+08:00"}
        if "boya" in person["features"]:
            progress = demo_boya_progress()
            person["features"]["boya"]["progress"] = progress_text("boya", progress)
            person["features"]["boya"]["counts"] = {key: value for key, value in progress.items() if key != "courses"}
    people[0]["features"].pop("class")
    people[0]["features"].pop("boya")
    people[2]["features"].pop("boya")
    people[4]["features"]["td"]["enabled"] = False
    return {"demo": True, "people": people, "services": {
        feature: {"feature": feature, "available": True,
                  "status": "stopped" if feature == "boya" else "running"}
        for feature in backends.FEATURES}, "td_images": ["示例图片.jpg"]}


class Application:
    def __init__(self, root: Path, demo: bool = False):
        self.registry = Registry(root)
        self.demo = demo
        self.sample = demo_state() if demo else None
        self.lock = threading.RLock()
        self.refreshing = set()
        self.refreshed = {}
        self.demo_courses = {}
        self.refresh_errors = {}
        self.sunshine_samples = {}
        self.demo_appearance = "system"
        self.boya_policies = {}

    def appearance(self):
        return self.demo_appearance if self.demo else read_appearance(self.registry.root)

    def snapshot(self):
        if self.demo:
            from .boya_policy import apply_policy, DEFAULT
            sample = copy.deepcopy(self.sample)
            for person in sample['people']:
                binding = person['features'].get('boya')
                if binding:
                    if 'counts' not in binding:
                        binding['counts'] = {key: value for key, value in demo_boya_progress().items() if key != 'courses'}
                    counts = apply_policy(binding['counts'], self.boya_policies.get(person['username'], DEFAULT))
                    binding['progress'] = progress_text('boya', counts)
            return sample
        from .cli import people
        rows = people(self.registry)
        services = {}
        for feature in backends.FEATURES:
            try:
                if not backends.available(feature):
                    services[feature] = {"available": False, "status": "unavailable"}
                else:
                    status = service.status(feature)
                    # GUI does not need native paths or worker tokens.
                    services[feature] = {"available": True, "status": status["status"],
                                         "stop_requested": status["stop_requested"]}
            except (OSError, ValueError, RuntimeError, ImportError) as exc:
                services[feature] = {"available": False, "status": "error", "message": str(exc)}
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        td = read_json(backends.native_home("td") / "state.json", {})
        td_users = read_json(backends.native_home("td") / "users.json", {}).get("users", {})
        boya_stats, boya_selected, boya_observed = {}, {}, None
        if backends.available("boya"):
            boya_stats, boya_selected, boya_observed = load_boya_cache()
        for row in rows:
            if 'class' in row['features']:
                row['features']['class']['refreshing'] = ('class', row['username']) in self.refreshing
                row['features']['class']['counts'] = {'updatedAt': self.refreshed.get(('class', row['username'])),
                                                       'refreshError': self.refresh_errors.get(('class', row['username']))}
            for feature in ("td", "boya"):
                if feature not in row["features"]:
                    continue
                progress = (td_progress(row["username"], td, td_users, today) if feature == "td"
                            else boya_progress(boya_stats.get(row["username"], {}), boya_selected.get(row["username"]), observed_at=boya_observed))
                if feature == "boya":
                    from .boya_operations import observation
                    info = observation(backends.boya_store(), row['username'])
                    from .boya import parse_time
                    personal_observed = parse_time(info.get('updatedAt')) or boya_observed
                    progress = boya_progress(boya_stats.get(row['username'], {}), boya_selected.get(row['username']), observed_at=personal_observed)
                    progress['updatedAt'] = personal_observed.isoformat() if personal_observed else None
                    progress['refreshError'] = info.get('error')
                    from .boya_policy import apply_policy, load_policy
                    apply_policy(progress, load_policy(backends.boya_store(), row['username']))
                row["features"][feature]["refreshing"] = (feature, row['username']) in self.refreshing
                row["features"][feature]["progress"] = progress_text(feature, progress)
                row["features"][feature]["counts"] = {key: value for key, value in progress.items() if key != "courses"}
        from .ygdk import detail as sunshine_detail
        for row in rows:
            if 'ygdk' in row['features']:
                value = sunshine_detail(row['username'])
                row['features']['ygdk']['counts'] = {**value['summary'], 'updatedAt': value.get('updatedAt'), 'refreshError': value.get('refreshError')}
                row['features']['ygdk']['refreshing'] = ('ygdk', row['username']) in self.refreshing
        images = sorted(path.name for path in (backends.native_home("td") / "images").glob("*") if path.is_file())
        return {"demo": False, "people": rows, "services": services, "td_images": images}

    def refresh_detail(self, feature, username):
        from .cli import validate_username
        valid_feature({"feature": feature})
        validate_username(username)
        if self.demo:
            detail = self.detail(feature, username)
            if feature == 'td':
                return {"message": "已重新读取 TD 缓存", "detail": detail}
            detail["updatedAt"] = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
            self.refreshed[(feature, username)] = detail["updatedAt"]
            return {"message": "示例数据已刷新", "detail": detail}
        if not any(row["username"] == username for row in backends.accounts(feature)):
            raise ValueError("请先绑定此项功能")
        key = (feature, username)
        with self.lock:
            if key in self.refreshing:
                raise ValueError("该账号正在刷新，请稍候")
            self.refreshing.add(key)
        try:
            if feature == "boya":
                from .boya_operations import refresh_user
                refresh_user(username)
            if feature == "ygdk":
                from .ygdk import refresh
                detail = refresh(username)
            else:
                detail = self.detail(feature, username)
            if feature == "class":
                self.refreshed[key] = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
                detail['updatedAt'] = self.refreshed[key]
            self.refresh_errors.pop(key, None)
            return {"message": "已重新读取 TD 缓存" if feature == "td" else "数据已刷新", "detail": detail}
        except Exception as exc:
            if feature == 'ygdk':
                from .ygdk import SunshineError
                if isinstance(exc, SunshineError):
                    self.refresh_errors[key] = str(exc)
                    raise ValueError(f'{exc}；原数据已保留') from exc
            self.refresh_errors[key] = "刷新失败，请检查网络或账号登录状态"
            raise ValueError("刷新失败，请检查网络或账号登录状态；原数据已保留") from exc
        finally:
            with self.lock:
                self.refreshing.discard(key)

    def _refresh_binding(self, feature, username):
        if feature == "td":
            return
        try:
            self.refresh_detail(feature, username)
        except Exception:
            pass  # Account remains bound; refresh errors are separately displayed.

    def mutate(self, path: str, payload: dict):
        if path == "/api/appearance":
            mode = payload.get("appearance")
            if not isinstance(mode, str) or mode not in MODES:
                raise ValueError("外观仅支持系统、浅色或深色")
            with self.lock:
                if self.demo:
                    self.demo_appearance = mode
                else:
                    save_appearance(self.registry.root, mode)
            return {"appearance": mode}

        if path in {"/api/refresh", "/api/boya/drop", "/api/boya/personalization", "/api/ygdk/submit", "/api/ygdk/records", "/api/ygdk/batch"}:
            username = payload.get("username", "")
            from .cli import validate_username
            if not isinstance(username, str):
                raise ValueError("学号格式不正确")
            validate_username(username)
            if path == '/api/boya/personalization':
                from .boya_policy import save_policy, validate_policy
                policy = validate_policy(payload)
                if self.demo:
                    with self.lock:
                        if not any(person['username'] == username and 'boya' in person['features'] for person in self.sample['people']):
                            raise ValueError('请先绑定博雅账号')
                        self.boya_policies[username] = policy
                else:
                    save_policy(backends.boya_store(), username, policy)
                return {'message': '个人定制已保存' if policy['mode'] == 'total' else '已恢复默认规则',
                        'detail': self.detail('boya', username)}
            if path == "/api/refresh":
                return self.refresh_detail(valid_feature(payload), username)
            if path.startswith('/api/ygdk/'):
                if not self.demo and not any(row['username'] == username for row in backends.accounts('ygdk')):
                    raise ValueError("请先绑定阳光账号")
                if self.demo and not any(row['username'] == username and 'ygdk' in row['features'] for row in self.sample['people']):
                    raise ValueError('请先绑定阳光账号')
                from .ygdk import refresh, submit, submit_batch, batch_plan, validate_submission
                if path.endswith('/records'):
                    page = payload.get('page', 1)
                    if type(page) is not int or not 1 <= page <= 10000:
                        raise ValueError("页码无效")
                    return {"detail": self.sunshine_samples.get(username, demo_sunshine()) if self.demo else refresh(username, page)}
                if self.demo:
                    batch = path.endswith('/batch')
                    records = batch_plan(payload) if batch else [payload]
                    for record in records:
                        validate_submission(record)
                    value = copy.deepcopy(self.sunshine_samples.get(username, demo_sunshine()))
                    needed = max(0, 4 - value['summary']['weekCount']) if batch else len(records)
                    added = min(len(records), needed)
                    value['summary']['weekCount'] += added
                    value['summary']['termCount'] += added
                    value['total'] += added
                    for index, record in enumerate(records[:added]):
                        value['records'].insert(0, {'id': value['total'] + index + 10, 'itemName': next((item['name'] for item in value['items'] if item['id'] == payload.get('itemId')), '运动'), 'startTime': record['startTime'] + '+08:00', 'endTime': record['endTime'] + '+08:00', 'place': record['place']})
                    self.sunshine_samples[username] = value
                    person = next(row for row in self.sample['people'] if row['username'] == username)
                    person['features']['ygdk']['counts'] = {**value['summary'], 'updatedAt': value['updatedAt']}
                    return {"message": "示例提交成功，未连接学校", "detail": value,
                            **({'batch': {'status': 'completed', 'outcomes': [{'number': i + 1, 'status': 'success' if i < added else 'skipped', 'label': '示例已提交' if i < added else '本周已达标'} for i in range(len(records))]}} if batch else {})}
                return submit_batch(username, payload) if path.endswith('/batch') else submit(username, payload)
            course_id = payload.get("courseId")
            if type(course_id) is not int or course_id <= 0:
                raise ValueError("课程 ID 无效")
            if self.demo:
                courses = self.demo_courses.setdefault(username, demo_boya_progress()["courses"])
                course = next((row for row in courses if row['id'] == course_id), None)
                if not course or not course['canDrop']:
                    raise ValueError("该课程不可退选")
                self.demo_courses[username] = [row for row in courses if row['id'] != course_id]
            else:
                if not any(row["username"] == username for row in backends.accounts("boya")):
                    raise ValueError("请先绑定博雅账号")
                from .boya_operations import drop_user_course
                drop_user_course(username, course_id)
            return {"message": "已退选，并排除自动选回", "detail": self.detail("boya", username)}

        from .cli import validate_username, remove_person
        with self.lock:
            if self.demo:
                return self._demo_mutate(path, payload)
            username = payload.get("username", "")
            if path.startswith("/api/people") or path in {"/api/feature", "/api/account"}:
                if not isinstance(username, str):
                    raise ValueError("学号格式不正确")
                validate_username(username)
            if path == "/api/people/save":
                name, group = payload.get("name", ""), payload.get("group", "")
                if not isinstance(name, str) or not isinstance(group, str) or len(name) > 80 or len(group) > 120:
                    raise ValueError("姓名或分组格式不正确")
                self.registry.upsert(username, name, group)
                message = "人员资料已保存"
            elif path == "/api/people/remove":
                # Keep the CLI's result capture request-local: no global stdout redirection.
                remove_person(self.registry, username, quiet=True)
                message = "人员已删除，后台下一轮读取生效"
            elif path == "/api/feature":
                feature = valid_feature(payload)
                if type(payload.get("enabled")) is not bool:
                    raise ValueError("功能状态必须为启用或暂停")
                with file_lock(service.run_dir(feature) / "accounts.lock"):
                    backends.set_enabled(feature, username, payload["enabled"])
                message = "已启用，下轮读取生效" if payload["enabled"] else "已暂停，下轮读取生效"
            elif path == "/api/account":
                feature = valid_feature(payload)
                password = payload.get("password", "")
                if not isinstance(password, str) or (feature not in ("td", "ygdk") and not password):
                    raise ValueError("请输入学校账号密码")
                campus = payload.get("campus", "北京")
                if campus not in ("北京", "杭州"):
                    raise ValueError("校区必须为北京或杭州")
                quick = payload.get("quick", "学院路")
                if quick not in ("学院路", "沙河"):
                    raise ValueError("TD 校区必须为学院路或沙河")
                if type(payload.get("unsafe", False)) is not bool:
                    raise ValueError("密码保存选项格式不正确")
                with file_lock(service.run_dir(feature) / "accounts.lock"):
                    backends.add_account(feature, username, password, campus, bool(payload.get("unsafe", False)), quick)
                threading.Thread(target=self._refresh_binding, args=(feature, username), daemon=True).start()
                message = "功能账号已绑定" + ("，正在查询最新数据" if feature != "td" else "，次数会在后台执行后更新")
            elif path == "/api/service":
                feature = valid_feature(payload)
                action = payload.get("action")
                if action == "start":
                    result = service.start(feature, self.registry.root)
                    if result["status"] == "skipped":
                        raise ValueError("请先绑定并启用至少一个人员的此项功能")
                    if result["status"] == "native-running":
                        return {"message": "原工具后台已在运行，无需重复启动"}
                    message = "后台已启动"
                elif action == "stop":
                    if service.status(feature)["status"] == "native-running":
                        command = autobh_command(feature, "--stop" if feature == "td" else "stop")
                        subprocess.run(command, capture_output=True, text=True, timeout=15, check=True, env=subprocess_environment())
                        return {"message": "已向原工具请求停止后台"}
                    result = service.stop(feature)
                    message = "已请求停止，等待当前操作结束" if result.get("stop_requested") else "后台已停止"
                else:
                    raise ValueError("不支持的后台操作")
            elif path == "/api/images":
                backends.require("td")
                filename = Path(payload.get("name", "")).name
                if Path(filename).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                    raise ValueError("请上传 JPG、PNG 或 WebP 图片")
                try:
                    content = base64.b64decode(payload.get("data", ""), validate=True)
                except ValueError as exc:
                    raise ValueError("图片内容无效") from exc
                if not content:
                    raise ValueError("图片不能为空")
                store = backends.td_store()
                store.initialize()
                with tempfile.TemporaryDirectory() as temporary:
                    image = Path(temporary) / filename
                    image.write_bytes(content)
                    store.add_image(image)
                message = "图片已导入"
            else:
                raise ValueError("未知操作")
            return {"message": message}

    def _demo_mutate(self, path, payload):
        username = payload.get("username")
        person = next((row for row in self.sample["people"] if row["username"] == username), None)
        if path == "/api/people/save":
            from .cli import validate_username
            validate_username(username or "")
            if person:
                person.update(name=payload.get("name", ""), group=payload.get("group", ""))
            else:
                self.sample["people"].append({"username": username, "name": payload.get("name", ""),
                                               "group": payload.get("group", ""), "features": {}})
        elif path == "/api/people/remove":
            self.sample["people"] = [row for row in self.sample["people"] if row["username"] != username]
            self.boya_policies.pop(username, None)
        elif path in {"/api/feature", "/api/account"}:
            if not person:
                raise ValueError("未找到人员")
            feature = valid_feature(payload)
            person["features"].setdefault(feature, {})["enabled"] = payload.get("enabled", True)
        elif path == "/api/service":
            self.sample["services"][valid_feature(payload)]["status"] = "running" if payload["action"] == "start" else "stopped"
        elif path == "/api/images":
            self.sample["td_images"].append(payload["name"])
        else:
            raise ValueError("未知操作")
        return {"message": "已更新示例数据"}

    def detail(self, feature: str, username: str):
        valid_feature({"feature": feature})
        if feature == "ygdk":
            if self.demo:
                return copy.deepcopy(self.sunshine_samples.get(username, demo_sunshine()))
            if not any(row['username'] == username for row in backends.accounts('ygdk')):
                raise ValueError("请先绑定阳光账号")
            from .ygdk import detail
            return detail(username)
        if self.demo:
            if feature == "class":
                return demo_timetable()
            person = next(row for row in self.sample["people"] if row["username"] == username)
            summary = person["features"].get(feature, {}).get("progress", "暂无次数缓存")
            if feature == "boya":
                counts = demo_boya_progress()
                from .boya_policy import apply_policy, DEFAULT
                apply_policy(counts, self.boya_policies.get(username, DEFAULT))
                if username in self.demo_courses:
                    counts['courses'] = self.demo_courses[username]
                    if not any(course['id'] == 4 for course in counts['courses']):
                        counts['pending'] -= 1
                        counts['categories'][-1]['pending'] -= 1
                        counts['excludedCount'] = 1
                counts['updatedAt'] = self.refreshed.get((feature, username))
                return {"title": "博雅进度", "summary": progress_text("boya", counts), **counts}
            now = datetime.now(ZoneInfo("Asia/Shanghai"))
            from .td_status import status_view
            counts = person['features'].get('td', {}).get('counts', {})
            # Different people exercise each visual state without touching accounts.
            index = self.sample['people'].index(person)
            states = ['completed', 'checking', 'exercising', 'retrying', 'paused', 'outside']
            visual = states[index % len(states)]
            native = {'status': 'error' if visual == 'retrying' else 'waiting', 'next_action': 'exit',
                      'due_at': (now + timedelta(minutes=4)).isoformat()}
            if visual == 'completed':
                native['status'] = 'completed'
            if visual == 'retrying':
                native['next_retry_at'] = (now + timedelta(seconds=30)).isoformat()
            counts = {**counts, 'completedToday': 3 if visual == 'completed' else 1}
            next_hour = (now + timedelta(hours=1)).hour
            settings = {'schedule': {'windows': [f'{next_hour:02}:00-{next_hour:02}:59'] if visual == 'outside' else ['00:00-23:59']}}
            view = status_view(native, counts, settings, self.sample['services']['td'], person['features']['td']['enabled'], now=now,
                               activity={'phase': 'check', 'action': 'exit'} if visual == 'checking' else None)
            return {"title": "TD 进度", "text": summary, **counts, **view,
                    "updatedAt": counts.get('updatedAt'), "status": native['status'],
                    "lastMessage": None, "lastError": "服务器拒绝连接（示例）" if visual == 'retrying' else '',
                    "failedAt": (now - timedelta(seconds=30)).isoformat() if visual == 'retrying' else None,
                    "nextRetryAt": native.get('next_retry_at'), "retryCount": 0}
        if not any(row["username"] == username for row in backends.accounts(feature)):
            raise ValueError("请先绑定此项功能")
        if feature == "class":
            from autosign_cli.core.iclass_client import IClassClient
            from autosign_cli.runtime.scheduler import login_with_fallback
            account = next(row for row in backends.class_manager().list_users() if row["username"] == username)
            clients = []

            def factory(use_vpn):
                client = IClassClient(use_vpn=use_vpn, verify_ssl=True)
                clients.append(client)
                return client

            try:
                client, mode = login_with_fallback(username, account["password"], factory)
                now = datetime.now(ZoneInfo("Asia/Shanghai"))
                result = timetable_payload(client.get_week_schedule(now=now), now, mode)
                result['updatedAt'] = now.isoformat()
                self.refreshed[(feature, username)] = result['updatedAt']
                return result
            finally:
                for client in clients:
                    client.session.close()
        if feature == "td":
            state = read_json(backends.native_home("td") / "state.json", {})
            today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
            progress = state.get("daily_runs", {}).get(today, {}).get("users", {}).get(username, {})
            user = backends.td_store().get_user(username) or {}
            counts = td_progress(username, state, {username: user}, today)
            from .td_status import status_view
            worker = service.status('td')
            activity = read_json(backends.native_home('td') / 'run/autobh/activity.json', {})
            if (activity.get('username') != username or activity.get('pid') != worker.get('pid')
                    or worker['status'] != 'running' or activity.get('phase') not in ('check', 'photo')
                    or activity.get('action') not in ('entrance', 'exit')):
                activity = None
            view = status_view(progress, counts, backends.td_store().load_settings(), worker,
                               backends.td_switches().get(username, True),
                               now=datetime.now(ZoneInfo('Asia/Shanghai')), activity=activity)
            total = counts["totalCount"]
            lines = [f"本学期已完成 {total} 次" if total is not None else "本学期累计次数：暂无缓存",
                     f"今日已完成 {counts['completedToday']} / {counts['targetToday']} 次"]
            if counts["updatedAt"]:
                lines.append(f"累计次数更新时间：{counts['updatedAt'].replace('T', ' ')}")
            lines.append("数据来自本机缓存，不会发起新的打卡。")
            from autoboya.logging import redact
            return {"title": "TD 进度", "text": "\n".join(lines), **counts, **view,
                    "status": progress.get("status", "pending"), "lastMessage": progress.get("last_message"),
                    "lastError": redact(str(progress.get("last_error") or "")),
                    "failedAt": progress.get("failed_at") or (progress.get("updated_at") if progress.get("status") == "error" else None),
                    "nextRetryAt": progress.get("next_retry_at"), "retryCount": progress.get("retry_count", 0),
                    "stateUpdatedAt": progress.get("updated_at")}
        statistics, selected, observed_at = load_boya_cache()
        from .boya_operations import observation, exclusions
        from .boya import parse_time
        observation_info = observation(backends.boya_store(), username)
        observed_at = parse_time(observation_info.get('updatedAt')) or observed_at
        counts = boya_progress(statistics.get(username, {}), selected.get(username), observed_at=observed_at)
        counts['updatedAt'] = observed_at.isoformat() if observed_at else None
        counts['refreshError'] = observation_info.get('error')
        counts['excludedCount'] = len(exclusions(backends.boya_store()).get(username, {}))
        from .boya_policy import apply_policy, load_policy
        apply_policy(counts, load_policy(backends.boya_store(), username))
        summary = progress_text("boya", counts)
        lines = [summary, counts['stopCondition']['label']]
        for row in counts["categories"]:
            if row["known"]:
                state = "已达标" if row["met"] else f"还需 {row['remaining']} 次"
                lines.append(f"{row['name']}：考核通过 {row['completed']} / {row['required']}（{state}）")
            else:
                lines.append(f"{row['name']}：等待官方统计")
        lines.append("以学校统计接口为准；签到、签退记录独立展示，不用于推算考核结果。")
        lines.append("已选课程" if counts["courses"] else "暂无已选课程缓存，后台定期刷新后更新。")
        for course in counts["courses"]:
            lines.append(f"{course['name']}\n{course['start'] or '时间待更新'}　{course['location']}\n{course['signIn']['label']} · {course['signOut']['label']} · {course['settlement']['label']}")
        return {"title": "博雅进度", "text": "\n\n".join(lines), "summary": summary, **counts}

    def logs(self, feature: str):
        valid_feature({"feature": feature})
        if self.demo:
            return {"text": f"{LABELS[feature]}后台状态已读取\n示例记录，不会连接学校系统。"}
        root = backends.native_home(feature)
        if feature == "ygdk":
            from .ygdk import detail
            lines = ["阳光后台每 30 分钟只读同步，不会自动提交运动记录。"]
            for row in backends.accounts('ygdk'):
                value = detail(row['username'])
                lines.append(f"{row['username']} · {value.get('updatedAt') or '尚未同步'} · {value.get('refreshError') or '无刷新错误'}")
            return {"text": "\n".join(lines)}
        if feature == "class":
            paths = sorted((root / "log").glob("*.txt"))[-1:]
        elif feature == "td":
            paths = sorted((root / "logs").glob("*-daytime-log.txt"))[-1:]
        else:
            paths = [root / "logs" / "autoboya.log"]
        if not paths or not paths[0].exists():
            return {"text": "暂无运行记录。"}
        from autoboya.logging import redact
        with paths[0].open(encoding="utf-8", errors="replace") as stream:
            return {"text": redact("".join(deque(stream, maxlen=100)))}


def valid_feature(payload):
    feature = payload.get("feature")
    if feature not in backends.FEATURES:
        raise ValueError("未知功能")
    return feature


def make_server(root: Path, port: int = 8765, demo: bool = False, web_root: Path | None = None):
    application = Application(root, demo)
    assets = web_root or WEB_ROOT
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Avoid logging credentials, request bodies or user identifiers.

        def _headers(self, status, content_type, length):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-AutoBH-Profile", profile_id(root, demo))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()

        def _json(self, value, status=200):
            content = json.dumps(value, ensure_ascii=False).encode()
            self._headers(status, "application/json; charset=utf-8", len(content))
            self.wfile.write(content)

        def _authorized(self, api=False):
            port = self.server.server_address[1]
            hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host") not in hosts:
                self._json({"error": "仅允许本机访问"}, 403)
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {f"http://{host}" for host in hosts}:
                self._json({"error": "请求来源无效"}, 403)
                return False
            if api and not secrets.compare_digest(self.headers.get("X-AutoBH-Token", ""), token):
                self._json({"error": "页面会话已过期，请刷新"}, 403)
                return False
            return True

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if not self._authorized(api=path.startswith("/api/")):
                return
            try:
                if path == "/api/appearance":
                    return self._json({"appearance": application.appearance()})
                if path == "/api/state":
                    with application.lock:
                        return self._json(application.snapshot())
                if path.startswith("/api/detail/"):
                    _, _, _, feature, username = path.split("/", 4)
                    return self._json(application.detail(feature, username))
                if path.startswith("/api/logs/"):
                    return self._json(application.logs(path.rsplit("/", 1)[-1]))
                if path.startswith("/api/"):
                    return self._json({"error": "接口不存在"}, 404)
                file = (assets / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
                if not file.is_relative_to(assets.resolve()) or not file.is_file():
                    return self._json({"error": "页面不存在"}, 404)
                content = file.read_bytes()
                if file.name == "index.html":
                    content = content.replace(b"__AUTOBH_TOKEN__", token.encode())
                    content = content.replace(b"__AUTOBH_APPEARANCE__", application.appearance().encode())
                self._headers(200, mimetypes.guess_type(file.name)[0] or "application/octet-stream", len(content))
                self.wfile.write(content)
            except (ValueError, KeyError, OSError, RuntimeError, ImportError, subprocess.TimeoutExpired) as exc:
                self._json({"error": str(exc)}, 400)

        def do_POST(self):
            if not self._authorized(api=True):
                return
            try:
                if self.headers.get_content_type() != "application/json":
                    return self._json({"error": "请求格式无效"}, 415)
                length = int(self.headers.get("Content-Length", 0))
                if not 0 < length <= 12 * 1024 * 1024:
                    return self._json({"error": "请求过大或为空"}, 413)
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("请求参数格式无效")
                result = application.mutate(urlsplit(self.path).path, payload)
                self._json(result)
            except (ValueError, KeyError, TypeError, OSError, RuntimeError, ImportError, subprocess.SubprocessError) as exc:
                self._json({"error": str(exc)}, 400)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server


def profile_id(root: Path, demo: bool) -> str:
    return hashlib.sha256(f"{root.resolve()}:{demo}".encode()).hexdigest()


def serve(root: Path, port: int = 8765, open_browser: bool = True, demo: bool = False):
    if not (WEB_ROOT / "index.html").exists():
        raise ValueError("GUI 尚未构建，请在仓库执行：python3 scripts/build_gui.py")
    try:
        server = make_server(root, port, demo)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            connection.request("GET", "/")
            response = connection.getresponse()
            existing = response.getheader("X-AutoBH-Profile") == profile_id(root, demo)
            response.read()
            connection.close()
        except (OSError, http.client.HTTPException):
            existing = False
        if not existing:
            raise ValueError(f"端口 {port} 已被其他服务占用，请使用 autobh ui --port 8877") from exc
        url = f"http://127.0.0.1:{port}"
        print(f"AutoBH GUI 已在运行：{url}", flush=True)
        if open_browser:
            webbrowser.open(url)
        return
    with server:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        print(f"AutoBH GUI：{url}" + ("（示例数据）" if demo else ""), flush=True)
        print("按 Ctrl+C 关闭管理界面；自动打卡后台会继续运行。", flush=True)
        if open_browser:
            threading.Timer(0.3, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
