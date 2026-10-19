from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from autoboya.cache import CourseCache
from autoboya.models import UserRecord

from autobh import backends
from autobh.boya_operations import drop_user_course, exclusions, observation, refresh_user


@pytest.fixture
def native_client(monkeypatch):
    store = backends.boya_store()
    store.init()
    store.upsert_user(UserRecord('1'))
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    class Client:
        selected = [{'id': 7, 'courseName': '安全讲座', 'kindName': '安全健康',
                     'courseStartDate': (now + timedelta(days=2)).isoformat(),
                     'courseCancelEndDate': (now + timedelta(days=1)).isoformat(), 'signInfo': None}]
        dropped = []
        def get_all_config(self):
            return {'data': {'semester': [{'semesterStartDate': (now - timedelta(days=30)).isoformat(),
                                          'semesterEndDate': (now + timedelta(days=30)).isoformat()}]}}
        def query_chosen_courses(self, start, end):
            return self.selected
        def query_statistics(self):
            return {'validCount': 1}
        def drop_course(self, course_id):
            self.dropped.append(course_id)
            self.selected = []
    client = Client()
    monkeypatch.setattr('autoboya.cli.call_with_reauth', lambda store, user, operation: operation(client))
    return store, client


def test_refresh_is_read_only_and_marks_only_requested_user(native_client):
    store, client = native_client
    refresh_user('1')
    assert client.dropped == []
    assert observation(store, '1')['updatedAt']
    assert observation(store, '2') == {}
    assert CourseCache(store).load_selected('1')[0]['id'] == 7


def test_withdraw_uses_course_id_and_persists_per_user_exclusion(native_client):
    store, client = native_client
    drop_user_course('1', 7)
    assert client.dropped == [7]
    assert '7' in exclusions(store)['1']
    runner = backends.runner('boya')
    assert '禁止自动选回' in runner.selection_block_reason('1', 7)
    assert '已手动退选' not in runner.selection_block_reason('2', 7)
    assert CourseCache(store).load_selected('1') == []


def test_expired_course_cannot_be_dropped_even_with_stale_ui(native_client):
    store, client = native_client
    client.selected[0]['courseCancelEndDate'] = '2020-01-01 00:00:00'
    with pytest.raises(ValueError, match='已过'):
        drop_user_course('1', 7)
    assert not client.dropped
    assert not exclusions(store)


def test_uncertain_withdraw_response_retains_exclusion(native_client, monkeypatch):
    store, client = native_client
    def failed(course_id):
        raise TimeoutError('uncertain server response')
    monkeypatch.setattr(client, 'drop_course', failed)
    with pytest.raises(ValueError, match='退选未确认'):
        drop_user_course('1', 7)
    assert '7' in exclusions(store)['1']


def test_failed_refresh_keeps_previous_cache_timestamp(native_client, monkeypatch):
    store, client = native_client
    refresh_user('1')
    old = observation(store, '1')['updatedAt']
    monkeypatch.setattr(client, 'query_statistics', lambda: (_ for _ in ()).throw(TimeoutError('secret-url')))
    with pytest.raises(ValueError, match='原缓存已保留') as error:
        refresh_user('1')
    assert 'secret-url' not in str(error.value)
    assert observation(store, '1')['updatedAt'] == old
