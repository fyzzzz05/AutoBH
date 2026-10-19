"""Read-only presentation of the native TD schedule and worker progress."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def parse_time(value):
    try:
        result = datetime.fromisoformat(value)
        return result.replace(tzinfo=ZoneInfo('Asia/Shanghai')) if result.tzinfo is None else result
    except (TypeError, ValueError):
        return None


def status_view(progress, counts, settings, worker, enabled, *, now, activity=None):
    from auto_td.scheduler import in_any_window, parse_window
    from auto_td.constants import DEFAULT_WINDOWS
    now = now.astimezone(ZoneInfo('Asia/Shanghai'))
    # An empty configured list means no permitted window, not all day.
    windows = settings.get('schedule', {}).get('windows', DEFAULT_WINDOWS)
    current_window = in_any_window(now, windows)
    next_window = None
    if not current_window:
        starts = []
        for offset in (0, 1):
            for window in windows:
                start, _ = parse_window(window)
                candidate = (now + timedelta(days=offset)).replace(hour=start // 60, minute=start % 60, second=0, microsecond=0)
                if candidate > now:
                    starts.append(candidate)
        next_window = min(starts).isoformat() if starts else None
    running = worker.get('status') in ('running', 'native-running') and not worker.get('stop_requested')
    due = parse_time(progress.get('due_at'))
    action = progress.get('next_action') or 'entrance'
    state = 'waiting'
    label = '等待入场' if action == 'entrance' else '等待离场'
    if activity:
        state = 'checking'
        label = '正在上传照片' if activity['phase'] == 'photo' else ('正在离场打卡' if activity['action'] == 'exit' else '正在入场打卡')
        action = activity['action']
    elif counts['completedToday'] >= counts['targetToday'] or progress.get('status') == 'completed':
        state, label = 'completed', '今日已完成'
    elif not enabled:
        state, label = 'paused', '自动执行已暂停'
    elif not running:
        state, label = 'stopped', '后台已停止'
    elif progress.get('status') == 'error':
        state, label = ('retrying', '等待重试') if progress.get('next_retry_at') else ('error', '需要处理')
    elif not current_window:
        state, label = 'outside', '等待打卡时段'
    elif due and due > now:
        state, label = ('exercising', '锻炼中') if action == 'exit' else ('waiting', '等待下一轮')
    return {
        'serverTime': now.isoformat(), 'windowOpen': current_window, 'windows': windows,
        'nextWindowAt': next_window, 'workerRunning': running, 'enabled': enabled,
        'activityState': state, 'activityLabel': label, 'nextAction': action,
        'dueAt': due.isoformat() if due else None,
        'realtimeRead': {'available': False, 'reason': 'no_read_only_endpoint' if current_window else 'outside_window',
            'message': ('TD 没有独立的次数查询接口，不会为刷新额外打卡。' if current_window else
                        '当前不在打卡时段，只能读取缓存；进入时段后随后台打卡更新。')},
    }
