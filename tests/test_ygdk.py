import base64
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import Mock

import httpx
import pytest

from autobh import backends, ygdk
from autobh.storage import atomic_json, read_json

PHOTO = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'demo').decode()


def payload(**overrides):
    return {'itemId': 2, 'startTime': '2026-01-01T10:00', 'endTime': '2026-01-01T11:00',
            'place': '操场', 'photo': {'name': 'sports.png', 'data': PHOTO},
            'requestId': '12345678-1234-1234-1234-123456789012', 'confirmed': True, **overrides}


def bind_fixture(username='123'):
    atomic_json(ygdk.home() / 'accounts.json', {username: {'source': 'file', 'enabled': True}})
    atomic_json(ygdk.user_path(username, 'password.json'), {'password': 'test-password'})


def test_credentials_reuse_does_not_duplicate_password_or_enable_native_feature():
    backends.add_account('class', '123', 'test-password', '北京', False)
    backends.set_enabled('class', '123', False)
    ygdk.bind('123', '')
    assert ygdk.accounts()['123']['source'] == 'class'
    assert ygdk.password_for('123') == 'test-password'
    assert not ygdk.user_path('123', 'password.json').exists()
    assert backends.accounts('class')[0]['enabled'] is False
    assert ygdk.remove('123')
    assert backends.accounts('class')[0]['username'] == '123'


def test_summary_prefers_valid_school_count_and_keeps_unknown_distinct_from_zero():
    assert ygdk.summary({'term_good_count_show': 0, 'term_count': 12}, {'term_num': 16}, {})['termCount'] == 0
    assert ygdk.summary({}, {}, {})['termCount'] is None
    assert ygdk.summary({'week_count': 2}, {'week_num': 3}, {})['weekTarget'] == 4
    assert ygdk.summary({'week_count': 2}, {'week_num': 3}, {})['schoolWeekTarget'] == 3


def test_protocol_login_and_read_never_upload_or_submit():
    paths = []
    def handle(request):
        paths.append(request.url.path)
        if request.url.host == 'sso.buaa.edu.cn':
            return httpx.Response(200, text='<form><input name="execution" value="e1" /></form>')
        if request.url.host == 'uc.buaa.edu.cn':
            return httpx.Response(200, text='signed in')
        if request.url.host == 'app.buaa.edu.cn':
            return httpx.Response(302, headers={'location': 'https://ygdk.buaa.edu.cn/?code=test-code'})
        if request.url.path.endswith('campusAppLogin'):
            return httpx.Response(200, json={'code': 1, 'result': {'data': {'uid': 7, 'token': 'private-token'}}})
        assert b'token=private-token' in request.content
        suffix = request.url.path.split('/Clockin/')[-1]
        result = {'Classify/getList': {'list': [{'classify_id': 3, 'name': '阳光体育', 'term_num': 16}]},
                  'Item/getList': {'list': [{'item_id': 2, 'name': '跑步'}]},
                  'Clockin/getCount': {'term_good_count_show': 8, 'week_count': 2, 'week_num': 3, 'day_count': 1},
                  'Term/get': {'name': '秋季学期'},
                  'Clockin/getList': {'list': [{'record_id': 9, 'item_id': 2, 'start_time': 1767271200}], 'total': 21}}[suffix]
        return httpx.Response(200, json={'code': 1, 'result': result})
    client = ygdk.Client(httpx.Client(transport=httpx.MockTransport(handle)))
    client.login('123', 'test-password')
    value = client.read()
    client.close()
    assert value['summary']['termCount'] == 8
    assert value['records'][0]['itemName'] == '跑步'
    assert value['hasMore'] is True
    assert all(not path.endswith('/clockin') and '/Upload/' not in path for path in paths)
    assert 'private-token' not in str(value)


@pytest.mark.parametrize('change', [
    {'endTime': '2026-01-01T09:00'}, {'endTime': '2026-01-02T11:00'},
    {'photo': None}, {'photo': {'name': 'x.png', 'data': base64.b64encode(b'not an image').decode()}},
    {'itemId': True}, {'confirmed': False}, {'place': ''}, {'requestId': '../invalid'},
])
def test_submission_validation_precedes_any_network(change):
    with pytest.raises(ValueError):
        ygdk.submit('123', payload(**change))


def test_future_activity_rejected():
    with pytest.raises(ValueError, match='尚未结束'):
        ygdk.validate_submission(payload(), now=datetime(2026, 1, 1, 10, 30, tzinfo=ygdk.TZ))


def test_refresh_failure_preserves_previous_cache_and_reports_error(monkeypatch):
    previous = {'summary': {'termCount': 8}, 'updatedAt': '2026-01-01T10:00:00+08:00'}
    atomic_json(ygdk.user_path('123', 'cache.json'), previous)
    @contextmanager
    def disconnected(username):
        raise ygdk.SunshineError('网络异常')
        yield
    monkeypatch.setattr(ygdk, 'connected', disconnected)
    with pytest.raises(ValueError):
        ygdk.refresh('123')
    assert ygdk.detail('123')['summary']['termCount'] == 8
    assert ygdk.detail('123')['updatedAt'] == previous['updatedAt']
    assert ygdk.detail('123')['refreshError'] == '网络异常'


def submit_client(monkeypatch, post=None):
    bind_fixture()
    client = Mock()
    client.catalog.return_value = ({'classify_id': 3}, [{'item_id': 2, 'name': '跑步'}])
    client.upload.return_value = 'uploaded.png'
    client.post.return_value = {'record_id': 9}
    if post:
        client.post.side_effect = post
    @contextmanager
    def connected(username):
        yield client
    monkeypatch.setattr(ygdk, 'connected', connected)
    monkeypatch.setattr(ygdk, 'refresh', lambda username: {'summary': {'termCount': 9}})
    return client


def test_confirmed_submit_exact_fields_and_duplicate_guard(monkeypatch):
    client = submit_client(monkeypatch)
    result = ygdk.submit('123', payload())
    assert result['message'] == '阳光打卡已提交'
    path, fields = client.post.call_args.args
    assert path.endswith('/Clockin/clockin')
    assert fields['isopen'] == '0'
    assert fields['form_time_fmt'] == '2026-01-01 10:00-11:00'
    assert fields['item_name'] == '跑步'
    ygdk.submit('123', payload())
    ygdk.submit('123', payload(requestId='different-12345678901234567890'))
    assert client.post.call_count == 1


def test_timeout_never_retries_even_with_new_request_id(monkeypatch):
    client = submit_client(monkeypatch, post=httpx.ReadTimeout('timeout'))
    with pytest.raises(ValueError, match='结果未确认'):
        ygdk.submit('123', payload())
    with pytest.raises(ValueError, match='上次提交结果'):
        ygdk.submit('123', payload(requestId='different-12345678901234567890'))
    assert client.post.call_count == 1
    assert read_json(ygdk.user_path('123', 'submissions.json'))[payload()['requestId']]['status'] == 'pending'


def test_server_error_keeps_unknown_submission_pending(monkeypatch):
    client = submit_client(monkeypatch, post=ygdk.SunshineError('HTTP 502'))
    with pytest.raises(ValueError, match='结果未确认'):
        ygdk.submit('123', payload())
    assert read_json(ygdk.user_path('123', 'submissions.json'))[payload()['requestId']]['status'] == 'pending'


def test_worker_only_syncs_enabled_users_and_never_submits(monkeypatch):
    atomic_json(ygdk.home() / 'accounts.json', {'1': {'enabled': True}, '2': {'enabled': False}, '3': {'enabled': True}})
    refresh = Mock()
    monkeypatch.setattr(ygdk, 'refresh', refresh)
    results = ygdk.SunshineRunner('1').run_once()
    refresh.assert_called_once_with('1')
    assert results[0].status == 'synced'


def test_account_paths_are_safe_for_arbitrary_username():
    assert ygdk.home() in ygdk.user_path('../../other', 'cache.json').parents


def test_stale_daily_and_weekly_cache_does_not_claim_current_progress():
    atomic_json(ygdk.user_path('123', 'cache.json'), {'summary': {'termCount': 8, 'dayCount': 1, 'weekCount': 3}, 'updatedAt': '2020-01-01T10:00:00+08:00'})
    value = ygdk.detail('123')
    assert value['summary'] == {'termCount': 8, 'dayCount': None, 'weekCount': None}


def test_gui_integrates_local_snapshot_refresh_submit_and_account_scope(tmp_path, monkeypatch):
    from autobh.gui import Application
    bind_fixture()
    app = Application(tmp_path / 'registry')
    assert 'ygdk' in app.snapshot()['people'][0]['features']
    assert app.snapshot()['services']['ygdk']['status'] == 'stopped'
    refreshed = {'title': '阳光打卡', 'summary': {'termCount': 8}, 'records': []}
    refresh = Mock(return_value=refreshed)
    monkeypatch.setattr(ygdk, 'refresh', refresh)
    assert app.mutate('/api/refresh', {'username': '123', 'feature': 'ygdk'})['detail'] == refreshed
    refresh.assert_called_once_with('123')
    submit = Mock(return_value={'message': 'submitted', 'detail': refreshed})
    monkeypatch.setattr(ygdk, 'submit', submit)
    assert app.mutate('/api/ygdk/submit', {'username': '123', **payload()})['message'] == 'submitted'
    with pytest.raises(ValueError, match='先绑定'):
        app.mutate('/api/ygdk/submit', {'username': 'other', **payload()})
    assert submit.call_count == 1


def test_demo_submission_never_calls_real_adapter(tmp_path, monkeypatch):
    from autobh.gui import Application
    monkeypatch.setattr(ygdk, 'submit', Mock(side_effect=AssertionError('real submit')))
    app = Application(tmp_path, demo=True)
    result = app.mutate('/api/ygdk/submit', {'username': '23370001', **payload()})
    assert '示例提交' in result['message']
    with pytest.raises(ValueError, match='先绑定'):
        app.mutate('/api/ygdk/submit', {'username': 'nonexistent', **payload()})


def batch_payload(**overrides):
    return {**payload(), 'records': [{'startTime': f'2026-10-{12 + i:02}T17:00', 'endTime': f'2026-10-{12 + i:02}T18:00'} for i in range(4)], **overrides}


@pytest.fixture
def saturday(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 17, 12, tzinfo=ygdk.TZ).astimezone(tz)
    monkeypatch.setattr(ygdk, 'datetime', FixedDateTime)


def test_batch_plan_has_distinct_times_and_validates_every_record_before_network(saturday):
    plan = ygdk.batch_plan(batch_payload())
    assert len(set(row['requestId'] for row in plan)) == 4
    assert len(set(row['startTime'] for row in plan)) == 4
    broken = batch_payload()
    broken['records'][-1]['endTime'] = '2026-10-20T18:00'
    with pytest.raises(ValueError):
        ygdk.submit_batch('123', broken)


def test_batch_rejects_close_or_other_week_slots(saturday):
    value = batch_payload()
    value['records'][1] = {'startTime': '2026-10-12T18:09', 'endTime': '2026-10-12T18:39'}
    with pytest.raises(ValueError, match='时间过近'):
        ygdk.batch_plan(value)
    value['records'][0] = {'startTime': '2026-10-11T17:00', 'endTime': '2026-10-11T18:00'}
    with pytest.raises(ValueError, match='本周'):
        ygdk.batch_plan(value)


def test_batch_submits_four_times_using_single_record_duplicate_guard(saturday, monkeypatch):
    client = submit_client(monkeypatch)
    monkeypatch.setattr(ygdk, 'refresh', lambda username: {'summary': {'weekCount': 0}})
    result = ygdk.submit_batch('123', batch_payload())
    assert result['batch']['status'] == 'completed'
    assert client.post.call_count == 4
    assert len({call.args[1]['start_time'] for call in client.post.call_args_list}) == 4
    ygdk.submit_batch('123', batch_payload())
    assert client.post.call_count == 4


@pytest.mark.parametrize('existing,expected', [(2, 2), (4, 0), (6, 0)])
def test_batch_only_fills_remaining_weekly_four(saturday, monkeypatch, existing, expected):
    client = submit_client(monkeypatch)
    monkeypatch.setattr(ygdk, 'refresh', lambda username: {'summary': {'weekCount': existing}})
    result = ygdk.submit_batch('123', batch_payload())
    assert client.post.call_count == expected
    assert result['batch']['status'] == 'completed'


def test_batch_timeout_stops_remaining_records_and_retry_never_replays_success(saturday, monkeypatch):
    client = submit_client(monkeypatch, post=[{'record_id': 9}, httpx.ReadTimeout('timeout')])
    monkeypatch.setattr(ygdk, 'refresh', lambda username: {'summary': {'weekCount': 0}})
    result = ygdk.submit_batch('123', batch_payload())
    assert result['batch']['status'] == 'paused'
    assert [row['status'] for row in result['batch']['outcomes']] == ['success', 'error', 'waiting', 'waiting']
    assert client.post.call_count == 2
    ygdk.submit_batch('123', batch_payload())
    assert client.post.call_count == 2


def test_batch_requires_live_weekly_count(saturday, monkeypatch):
    client = submit_client(monkeypatch)
    monkeypatch.setattr(ygdk, 'refresh', lambda username: {'summary': {'weekCount': None}})
    with pytest.raises(ValueError, match='本周次数'):
        ygdk.submit_batch('123', batch_payload())
    client.post.assert_not_called()


def test_mobile_campus_cas_service_is_initialized_before_oauth():
    from urllib.parse import parse_qs
    requests = []
    def handle(request):
        requests.append(request)
        if request.url.host == 'sso.buaa.edu.cn':
            return httpx.Response(200, text='<form><input name="execution" value="test" /></form>')
        if request.url.host == 'uc.buaa.edu.cn':
            return httpx.Response(200, text='ready')
        if request.url.host == 'app.buaa.edu.cn':
            # Mimic the real separate mobile-campus login page.
            if request.url.path == '/uc/api/oauth/index':
                if any(r.method == 'POST' and r.url.path == '/uc/wap/login' for r in requests):
                    return httpx.Response(302, headers={'location': 'https://ygdk.buaa.edu.cn/#/home?code=test-oauth'})
                return httpx.Response(302, headers={'location': '/uc/wap/login'})
            if request.method == 'POST':
                assert parse_qs(request.content.decode())['username'] == ['123']
                assert parse_qs(request.content.decode())['password'] == ['private-password']
                return httpx.Response(302, headers={'location': '/uc/api/oauth/index'})
            return httpx.Response(200, text='<form id="loginForm" action="login"><input name="username"><input name="password" type="password"><input name="execution" value="test"></form>')
        return httpx.Response(200, json={'code': 1, 'result': {'uid': 7, 'token': 'test-private-token'}})
    client = ygdk.Client(httpx.Client(transport=httpx.MockTransport(handle)))
    client.login('123', 'private-password')
    client.close()
    bridge = next(r for r in requests if r.url.host == 'sso.buaa.edu.cn' and 'service' in r.url.params)
    assert parse_qs(bridge.url.params['service'].split('?', 1)[1])['redirect'] == [ygdk.OAUTH]
    assert client.uid == 7


def test_auth_failure_cache_contains_recovery_metadata_not_tokens(monkeypatch):
    @contextmanager
    def auth_failure(username):
        raise ygdk.AuthenticationError('移动校园登录未完成', stage='mobile_campus')
        yield
    monkeypatch.setattr(ygdk, 'connected', auth_failure)
    with pytest.raises(ValueError, match='移动校园'):
        ygdk.refresh('123')
    value = ygdk.detail('123')
    assert value['authorization']['required'] is True
    assert value['authorization']['stage'] == 'mobile_campus'
    assert value['authorization']['errorKind'] == 'authentication'
    assert value['authorization']['loginUrl'].startswith('https://sso.buaa.edu.cn/login?')
    assert 'token' not in value['authorization']


def test_network_failure_is_not_mislabeled_as_missing_authorization(monkeypatch):
    @contextmanager
    def network_failure(username):
        try:
            raise httpx.ConnectTimeout('sensitive URL must never be exposed')
        except httpx.HTTPError as exc:
            raise ygdk.SunshineError('无法连接阳光服务') from exc
        yield
    monkeypatch.setattr(ygdk, 'connected', network_failure)
    with pytest.raises(ValueError):
        ygdk.refresh('123')
    value = ygdk.detail('123')
    assert value['authorization']['required'] is False
    assert value['authorization']['errorKind'] == 'network'
    assert 'sensitive' not in str(value)


def test_legacy_auth_error_still_exposes_recovery_entry():
    atomic_json(ygdk.user_path('123', 'observation.json'), {'error': '未取得阳光登录授权，请检查学校认证状态'})
    assert ygdk.detail('123')['authorization']['required'] is True


@pytest.mark.parametrize('url,expected', [
    ('https://ygdk.buaa.edu.cn/#/home?code=hash-test&state=STATE', 'hash-test'),
    ('https://ygdk.buaa.edu.cn/?code=query-test#/home', 'query-test'),
    ('https://ygdk.buaa.edu.cn/#/home?code=encoded%2Btest', 'encoded+test'),
    ('https://ygdk.buaa.edu.cn/#/home', None),
    ('https://other.example/#/home?code=not-trusted', None),
    ('https://ygdk.buaa.edu.cn.other.example/#/home?code=not-trusted', None),
    ('http://ygdk.buaa.edu.cn/#/home?code=not-secure', None),
])
def test_oauth_callback_supports_hash_routes_without_accepting_other_hosts(url, expected):
    assert ygdk.oauth_code(url) == expected


def test_same_day_batch_accepts_ten_minute_gaps_and_rejects_overlap(saturday):
    value = batch_payload(records=[
        {'startTime': '2026-10-12T14:00', 'endTime': '2026-10-12T14:30'},
        {'startTime': '2026-10-12T14:40', 'endTime': '2026-10-12T15:10'},
        {'startTime': '2026-10-12T15:20', 'endTime': '2026-10-12T15:50'},
        {'startTime': '2026-10-12T16:00', 'endTime': '2026-10-12T16:30'},
    ])
    assert len(ygdk.batch_plan(value)) == 4
    value['records'][1] = {'startTime': '2026-10-12T14:20', 'endTime': '2026-10-12T14:50'}
    with pytest.raises(ValueError, match='10 分钟'):
        ygdk.batch_plan(value)
