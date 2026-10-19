"""Thin adapter for the installed AutoTD 0.1.x scheduler and storage."""
from __future__ import annotations

from . import backends
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from contextlib import contextmanager
import os


class TDRunner:
    def __init__(self, username: str | None = None):
        from auto_td.storage import AppStorage
        from auto_td.logging_utils import setup_logging

        class ScopedStorage(AppStorage):
            def list_users(self):
                switches = backends.td_switches()
                return [user for user in super().list_users()
                        if switches.get(user.student_id, True)
                        and (username is None or user.student_id == username)]

            def get_last_count(self, student_id):
                recovery = getattr(self, 'recovery_client', None)
                if recovery and recovery.pending_photo(student_id):
                    # Finish the confirmed action's photo even when its response
                    # already reached the semester limit. Never send a new check.
                    return None
                return super().get_last_count(student_id)

            def save_state(self, state):
                # Native scheduler removes state for users absent from list_users.
                # Preserve paused/unselected users' in-progress entry/exit state.
                active = {user.student_id for user in self.list_users()}
                existing = self.load_state() if self.state_path.exists() else {}
                known = set(self.load_users())
                for day, record in existing.get("daily_runs", {}).items():
                    for student_id, progress in record.get("users", {}).items():
                        if student_id in known and student_id not in active:
                            state.setdefault("daily_runs", {}).setdefault(day, {}).setdefault("users", {}).setdefault(student_id, progress)
                super().save_state(state)

        self.store = ScopedStorage(backends.native_home("td"))
        self.store.initialize()
        self.logger = setup_logging(self.store, stream=False)

    def run_once(self, now=None, client=None, wait_seconds=None):
        from auto_td.scheduler import run_scheduler_once, in_any_window
        from auto_td.client import TDClient
        now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
        state = self.store.load_state()
        day = now.date().isoformat()
        users = state.get("daily_runs", {}).get(day, {}).get("users", {})
        user_models = {user.student_id: user for user in self.store.list_users()}
        active = set(user_models)
        windows = self.store.load_settings().get("schedule", {}).get("windows", [])
        # Preserve entrance/exit state while waiting for the next native window.
        in_window = in_any_window(now, windows)
        for username, record in users.items():
            if username not in active or record.get("status") != "error":
                continue
            attempt = int(record.get("retry_count", 0))
            safe = record.get("retry_safe", False)
            if "retry_safe" not in record:
                safe = "Connection refused" in str(record.get("last_error", ""))
            if not safe or attempt >= 3:
                record['last_message'] = "自动重试已停止，请核实错误后处理"
                continue
            due = record.get("next_retry_at")
            if in_window and due and datetime.fromisoformat(due) <= now:
                record.update(status="pending", retry_count=attempt + 1, next_retry_at=None)
        self.store.save_state(state)
        wrapped = CheckpointClient(self.store, client or TDClient(self.store.load_config()), now)
        self.store.recovery_client = wrapped
        if in_window:
            result = run_scheduler_once(self.store, now=now, client=wrapped, logger=self.logger, wait_seconds=wait_seconds)
        else:
            from auto_td.models import BatchResult
            result = BatchResult([])
        state = self.store.load_state()
        for username, record in state.get("daily_runs", {}).get(day, {}).get("users", {}).items():
            if username not in active:
                continue
            user = user_models[username]
            machine = user.exit_machine_id if record.get("next_action") == "exit" else user.entrance_machine_id
            current_key = f'{day}:{username}:{record.get("completed_rounds", 0)}:{machine}'
            if record.get("status") != "error":
                if current_key not in wrapped.data:
                    record.update(retry_count=0, next_retry_at=None, retry_safe=False)
                for key in list(wrapped.data):
                    if key.startswith(f'{day}:{username}:') and (key != current_key or record.get('status') == 'completed'):
                        del wrapped.data[key]
                continue
            checkpoint = wrapped.data.get(current_key, {})
            safe = checkpoint.get('safe', "Connection refused" in str(record.get('last_error', '')))
            count = int(record.get('retry_count', 0))
            record['retry_safe'] = safe
            record['failed_at'] = record.get('updated_at')
            if safe and count < 3:
                next_time = record.get('next_retry_at')
                candidate = datetime.fromisoformat(next_time) if next_time else now + timedelta(seconds=(60, 180, 600)[count])
                candidate = max(candidate, now)
                while candidate.date() == now.date() and not in_any_window(candidate, windows):
                    candidate = (candidate + timedelta(minutes=1)).replace(second=0, microsecond=0)
                record['next_retry_at'] = candidate.isoformat() if candidate.date() == now.date() else None
                stage = '打卡已成功，照片上传失败' if checkpoint.get('response') else '连接失败'
                record['last_message'] = f'{stage}，等待第 {count + 1}/3 次自动重试' if record['next_retry_at'] else f'{stage}；今日窗口已结束，明日按新计划执行'
            else:
                record['next_retry_at'] = None
                record['last_message'] = '已用完 3 次重试，请检查网络' if safe else '请求结果未知或不可重试，请先核实'
        self.store.save_state(state)
        wrapped.save()
        return result

    def run_forever(self, stop_event):
        while not stop_event.is_set():
            self.run_once()
            seconds = int(self.store.load_settings().get("schedule", {}).get("poll_seconds", 60))
            stop_event.wait(max(1, seconds))


class CheckpointClient:
    """Keep successful check responses until native scheduler commits the phase.

    Only connect failures are automatically retried before a response exists.
    A response timeout after send is deliberately held for verification.
    """
    def __init__(self, store, client, now):
        from .storage import read_json
        self.store, self.client, self.now = store, client, now
        self.path = store.home / 'run/autobh/recovery.json'
        self.data = read_json(self.path, {})
        self.current = None

    def pending_photo(self, username):
        prefix = f'{self.now.date()}:{username}:'
        return any(key.startswith(prefix) and record.get('response') and not record.get('photo_done')
                   for key, record in self.data.items())

    def save(self):
        from .storage import atomic_json
        atomic_json(self.path, self.data)

    @contextmanager
    def activity(self, phase, user_id, action):
        from .storage import atomic_json
        path = self.store.home / 'run/autobh/activity.json'
        try:
            atomic_json(path, {'username': user_id, 'pid': os.getpid(), 'phase': phase, 'action': action,
                              'startedAt': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()})
        except OSError:
            pass  # Presentation telemetry must never prevent a scheduled action.
        try:
            yield
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    def key(self, user, machine_id):
        state = self.store.load_state().get('daily_runs', {}).get(self.now.date().isoformat(), {}).get('users', {}).get(user.student_id, {})
        return f'{self.now.date()}:{user.student_id}:{state.get("completed_rounds", 0)}:{machine_id}'

    def check(self, user, machine_id, **kwargs):
        from auto_td.models import CheckResponse
        key = self.key(user, machine_id)
        self.current = key
        self.current_action = 'exit' if machine_id == user.exit_machine_id else 'entrance'
        record = self.data.setdefault(key, {})
        if record.get('response'):
            return CheckResponse(**record['response'])
        if record.get('inflight'):
            raise RuntimeError('上次请求结果未知，请先核实，暂停自动重试')
        record.update(inflight=True, safe=False, timestamp=kwargs.get('timestamp'))
        self.save()
        try:
            with self.activity('check', user.student_id, self.current_action):
                response = self.client.check(user, machine_id, **kwargs)
        except Exception as exc:
            # Native TDClient wraps connect errors in ConnectionError, with the
            # original OSError as cause; send/receive failures are not wrapped.
            safe = isinstance(exc, ConnectionError) and isinstance(exc.__cause__, OSError)
            record.update(inflight=not safe, safe=safe)
            self.save()
            raise
        record.update(inflight=False, safe=False)
        if response.success:
            record['response'] = {'success': response.success, 'server_message': response.server_message, 'count': response.count}
            record['safe'] = True  # a retry replays response and only uploads photo
        self.save()
        return response

    def upload_photo(self, *args, **kwargs):
        record = self.data[self.current]
        if record.get('photo_done'):
            return None
        if record.get('timestamp') is not None:
            kwargs['timestamp'] = record['timestamp']
        user_id = self.current.split(':')[1]
        with self.activity('photo', user_id, self.current_action):
            result = self.client.upload_photo(*args, **kwargs)
        record['photo_done'] = True
        self.save()
        return result
