from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import Mock

import pytest

pytest.importorskip('auto_td')
from autobh.td_status import status_view

NOW = datetime(2026, 10, 16, 15, 10, tzinfo=ZoneInfo('Asia/Shanghai'))
COUNTS = {'completedToday': 1, 'targetToday': 3}
SETTINGS = {'schedule': {'windows': ['07:30-10:00', '15:30-20:00']}}
WORKER = {'status': 'running'}


def view(progress=None, **kwargs):
    return status_view(progress or {}, COUNTS, SETTINGS, WORKER, True, now=NOW, **kwargs)


def test_closed_window_explains_cache_only_and_next_window():
    result = view()
    assert result['activityState'] == 'outside'
    assert result['nextWindowAt'] == '2026-10-16T15:30:00+08:00'
    assert not result['realtimeRead']['available']
    assert '只能读取缓存' in result['realtimeRead']['message']


def test_open_window_still_never_claims_a_read_only_count_endpoint():
    result = status_view({}, COUNTS, SETTINGS, WORKER, True, now=NOW.replace(hour=16))
    assert result['windowOpen']
    assert result['realtimeRead']['reason'] == 'no_read_only_endpoint'
    assert not result['realtimeRead']['available']


def test_next_window_rolls_to_tomorrow_and_empty_schedule_stays_closed():
    result = status_view({}, COUNTS, SETTINGS, WORKER, True, now=NOW.replace(hour=21))
    assert result['nextWindowAt'] == '2026-10-17T07:30:00+08:00'
    result = status_view({}, COUNTS, {'schedule': {'windows': []}}, WORKER, True, now=NOW)
    assert result['nextWindowAt'] is None and not result['windowOpen']


def test_waiting_is_not_reported_as_an_active_request():
    progress = {'next_action': 'exit', 'due_at': (NOW + timedelta(hours=2)).isoformat()}
    result = status_view(progress, COUNTS, SETTINGS, WORKER, True, now=NOW.replace(hour=16))
    assert result['activityState'] == 'exercising'
    assert view(activity={'phase': 'photo', 'action': 'exit'})['activityLabel'] == '正在上传照片'


@pytest.mark.parametrize('enabled,status,expected', [(False, 'running', 'paused'), (True, 'stopped', 'stopped')])
def test_paused_or_stopped_jobs_do_not_animate_as_retrying(enabled, status, expected):
    result = status_view({'status': 'error', 'next_retry_at': NOW.isoformat()}, COUNTS, SETTINGS,
                         {'status': status}, enabled, now=NOW)
    assert result['activityState'] == expected


def test_gui_cache_refresh_never_calls_td_query_or_changes_count_timestamp(tmp_path, monkeypatch):
    from autobh import backends
    from autobh.gui import Application
    from auto_td.client import TDClient
    store = backends.td_store()
    store.initialize()
    store.save_users({'1': {'student_id': '1', 'rounds': 3}})
    state = {'counts': {'1': {'count': 18, 'updated_at': '2026-10-16T07:50:10+08:00'}}}
    store.save_state(state)
    check, query = Mock(), Mock()
    monkeypatch.setattr(TDClient, 'check', check)
    monkeypatch.setattr(TDClient, 'query_count', query)
    result = Application(tmp_path).refresh_detail('td', '1')['detail']
    assert result['totalCount'] == 18
    assert result['updatedAt'] == state['counts']['1']['updated_at']
    check.assert_not_called()
    query.assert_not_called()
    assert store.load_state() == state
