import http.client
import json
import re
import socket
import threading
from zoneinfo import ZoneInfo

import pytest

from autobh import backends
from autobh.gui import Application, make_server

ORIGINAL_CONNECT = socket.socket.connect


@pytest.fixture
def gui_server(tmp_path, monkeypatch):
    def only_loopback(stream, address):
        if address[0] not in {"127.0.0.1", "::1"}:
            raise AssertionError("School network must not be used by GUI tests")
        return ORIGINAL_CONNECT(stream, address)
    monkeypatch.setattr(socket.socket, "connect", only_loopback)
    assets = tmp_path / "web"
    assets.mkdir()
    (assets / "index.html").write_text('<meta name="autobh-token" content="__AUTOBH_TOKEN__"><html data-appearance="__AUTOBH_APPEARANCE__">', encoding="utf-8")
    server = make_server(tmp_path / "registry", 0, web_root=assets)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]

    def request(path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        defaults = {} if body is None else {"Content-Type": "application/json"}
        connection.request("GET" if body is None else "POST", path,
                           None if body is None else json.dumps(body), {**defaults, **(headers or {})})
        response = connection.getresponse()
        result = response.status, response.read().decode()
        connection.close()
        return result
    status, html = request("/")
    assert status == 200
    token = re.search(r'content="([^"]+)"', html).group(1)
    yield request, {"X-AutoBH-Token": token}, port
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def test_http_api_requires_page_token_and_rejects_foreign_origins(gui_server):
    request, headers, _ = gui_server
    assert request("/api/state")[0] == 403
    assert request("/api/state", headers={**headers, "Origin": "https://untrusted.example"})[0] == 403
    assert request("/api/state", headers={**headers, "Host": "attacker.example"})[0] == 403
    assert request("/api/state", headers=headers)[0] == 200


def test_state_omits_passwords_paths_and_tokens(gui_server):
    request, headers, _ = gui_server
    backends.class_manager().add_user("1", "very-private-password")
    status, body = request("/api/state", headers=headers)
    assert status == 200
    data = json.loads(body)
    assert data["people"][0]["username"] == "1"
    assert "very-private-password" not in body
    assert '"home"' not in body
    assert '"token"' not in body


def test_gui_reuses_real_people_and_feature_management(gui_server):
    request, headers, _ = gui_server
    backends.class_manager().add_user("1", "secret")
    assert request("/api/people/save", {"username": "1", "name": "张三", "group": "学院路"}, headers)[0] == 200
    assert request("/api/feature", {"username": "1", "feature": "class", "enabled": False}, headers)[0] == 200
    data = json.loads(request("/api/state", headers=headers)[1])
    assert data["people"][0]["name"] == "张三"
    assert data["people"][0]["features"]["class"]["enabled"] is False
    assert request("/api/people/remove", {"username": "1"}, headers)[0] == 200
    assert backends.accounts("class") == []
    assert json.loads(request("/api/state", headers=headers)[1])["people"] == []


def test_invalid_switch_payload_cannot_enable_a_feature(gui_server):
    request, headers, _ = gui_server
    backends.class_manager().add_user("1", "secret")
    backends.set_enabled("class", "1", False)
    assert request("/api/feature", {"username": "1", "feature": "class", "enabled": "false"}, headers)[0] == 400
    assert backends.accounts("class")[0]["enabled"] is False
    assert request("/api/people/save", {"username": []}, headers)[0] == 400


def test_demo_mutations_do_not_write_native_accounts(tmp_path):
    app = Application(tmp_path, demo=True)
    app.mutate("/api/feature", {"username": "23370001", "feature": "class", "enabled": False})
    app.mutate("/api/service", {"feature": "boya", "action": "start"})
    app.mutate("/api/people/remove", {"username": "23370002"})
    app.mutate("/api/people/save", {"username": "9", "name": "测试"})
    state = app.snapshot()
    assert state["people"][0]["features"]["class"]["enabled"] is False
    assert state["services"]["boya"]["status"] == "running"
    assert not any(person["username"] == "23370002" for person in state["people"])
    assert not (backends.native_home("class") / "config.yaml").exists()
    assert not (backends.native_home("boya") / "users.json").exists()
    assert not (backends.native_home("td") / "users.json").exists()


def test_td_detail_reads_only_local_progress(tmp_path):
    pytest.importorskip("auto_td")
    from autobh.storage import atomic_json
    store = backends.td_store()
    store.save_users({"1": {"student_id": "1", "rounds": 3}})
    atomic_json(store.state_path, {})
    result = Application(tmp_path).detail("td", "1")
    assert "0 / 3" in result["text"]


def test_gui_binding_uses_native_account_storage(gui_server):
    request, headers, _ = gui_server
    status, response = request("/api/account", {"username": "7", "feature": "class", "password": "fake-private-password"}, headers)
    assert status == 200
    assert "fake-private-password" not in response
    assert backends.class_manager().list_users() == [{"username": "7", "password": "fake-private-password"}]


def test_gui_service_control_uses_existing_manager(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from autobh import service
    start = Mock(return_value={"status": "running"})
    monkeypatch.setattr(service, "start", start)
    root = tmp_path / "registry"
    assert Application(root).mutate("/api/service", {"feature": "class", "action": "start"})["message"] == "后台已启动"
    start.assert_called_once_with("class", root)


def test_week_schedule_reuses_native_read_client_and_returns_structured_data(tmp_path, monkeypatch):
    from datetime import datetime
    from unittest.mock import Mock
    from autosign_cli.core.models import ClassSession
    from autosign_cli.core import iclass_client
    backends.class_manager().add_user("1", "private-password")
    client = Mock()
    client.get_week_schedule.return_value = [ClassSession("schedule-1", "course-1", "智能交通控制", "老师",
        datetime.fromisoformat("2026-10-15T14:00:00+08:00"), datetime.fromisoformat("2026-10-15T15:35:00+08:00"))]
    monkeypatch.setattr(iclass_client, "IClassClient", lambda **kwargs: client)
    result = Application(tmp_path).detail("class", "1")
    assert result["type"] == "timetable"
    assert result["timezone"] == "Asia/Shanghai"
    assert result["sessions"][0]["courseName"] == "智能交通控制"
    assert result["sessions"][0]["startTime"].endswith("+08:00")
    assert "private-password" not in json.dumps(result)
    client.login.assert_called_once_with("1", "private-password")
    client.sign_now.assert_not_called()
    client.session.close.assert_called_once()


def test_week_schedule_closes_client_when_query_fails(tmp_path, monkeypatch):
    from unittest.mock import Mock
    from autosign_cli.core import iclass_client
    backends.class_manager().add_user("1", "password")
    client = Mock()
    client.get_week_schedule.side_effect = RuntimeError("query failed")
    monkeypatch.setattr(iclass_client, "IClassClient", lambda **kwargs: client)
    with pytest.raises(RuntimeError, match="query failed"):
        Application(tmp_path).detail("class", "1")
    client.session.close.assert_called_once()


def test_timetable_week_uses_shanghai_date_at_utc_day_boundary():
    from datetime import datetime
    from autobh.gui import timetable_payload
    result = timetable_payload([], datetime.fromisoformat("2026-10-18T17:00:00+00:00"), "vpn")
    assert result["weekStart"] == "2026-10-19"
    assert result["weekEnd"] == "2026-10-25"
    assert result["sessions"] == []


def test_native_progress_keeps_semester_total_separate_from_today(tmp_path, monkeypatch):
    from datetime import datetime
    from autobh import service
    from autobh.storage import atomic_json
    pytest.importorskip("auto_td")
    store = backends.td_store()
    store.save_users({"1": {"student_id": "1", "rounds": 3}, "2": {"student_id": "2", "rounds": 2}})
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    atomic_json(store.state_path, {"counts": {"1": {"count": 18, "updated_at": "2026-10-15T09:00:00"}},
                                  "daily_runs": {today: {"users": {"1": {"completed_rounds": 1}}}}})
    backends.set_enabled("td", "1", False)
    monkeypatch.setattr(service, "status", lambda feature: {"status": "stopped", "stop_requested": False})
    app = Application(tmp_path)
    people = {row["username"]: row for row in app.snapshot()["people"]}
    assert people["1"]["features"]["td"]["progress"] == "本学期已完成 18 次 · 今日 1 / 3 次"
    assert people["1"]["features"]["td"]["enabled"] is False
    assert people["2"]["features"]["td"]["progress"] == "暂无次数缓存 · 今日 0 / 2 次"
    assert "本学期已完成 18 次" in app.detail("td", "1")["text"]
    assert "2026-10-15 09:00:00" in app.detail("td", "1")["text"]


def test_boya_progress_trusts_official_statistics_without_attendance_records():
    from autobh.progress import boya_progress, progress_text
    stats = {"statistical": {"60|博雅课程": {
        "55|德育": {"completeAssessmentCount": 2, "assessmentCount": 2},
        "56|美育": {"completeAssessmentCount": 1, "assessmentCount": 1}}}, "validCount": -2}
    result = boya_progress(stats)
    assert result["totalCount"] == -2
    assert result["metCategories"] == 2
    assert "2 类待同步" in progress_text("boya", result)
    assert boya_progress({})["totalCount"] is None
    assert boya_progress({}, [])["totalCount"] is None


def test_boya_counts_snapshot_and_detail_reuse_statistical_enrollment_records(tmp_path, monkeypatch):
    from autoboya.cache import CourseCache
    from autoboya.models import UserRecord
    from autobh import service
    store = backends.boya_store()
    store.init()
    store.upsert_user(UserRecord("1", enabled=False))
    CourseCache(store).save_statistics("1", {"statistical": {"60|博雅课程": {
        "55|德育": {"assessmentCount": 2, "completeAssessmentCount": 1, "failAssessmentCount": 1, "courseUserList": [
            {"courseInfo": {"id": 1, "courseName": "德育课", "courseEndDate": "2026-09-10 10:00:00"}, "signInfo": {"signIn": {"inSignArea": True}, "signOut": {"inSignArea": True}}},
            {"courseInfo": {"id": 2, "courseName": "未完成课", "courseEndDate": "2026-09-10 10:00:00"}, "signInfo": None},
        ]}}}, "validCount": 0})
    monkeypatch.setattr(service, "status", lambda feature: {"status": "stopped", "stop_requested": False})
    app = Application(tmp_path)
    row = app.snapshot()["people"][0]
    assert row["features"]["boya"]["progress"] == "净有效 0 次 · 已达标 0 / 4 类 · 3 类待同步"
    detail = app.detail("boya", "1")
    assert "德育：考核通过 1 / 2（还需 1 次）" in detail["text"]
    assert len(detail["courses"]) == 2
    assert detail["courses"][0]["category"] == "德育"
    assert detail["courses"][1]["settlement"]["state"] == "unknown"


def test_boya_detail_returns_per_course_attendance_from_native_cache(tmp_path):
    from autoboya.cache import CourseCache
    from autoboya.models import UserRecord
    store = backends.boya_store()
    store.init()
    store.upsert_user(UserRecord('1'))
    CourseCache(store).save_selected('1', [
        {'id': 1, 'courseName': '仿生机器人', 'signInfo': '{"signIn":{"inSignArea":true}}'},
        {'id': 2, 'courseName': '理论课堂', 'signInfo': None},
    ])
    result = Application(tmp_path).detail('boya', '1')
    assert result['courses'][0]['signIn']['label'] == '已签到'
    assert result['courses'][0]['signOut']['label'] == '暂无签退记录'
    assert result['courses'][1]['signIn']['label'] == '暂无签到记录'
    assert '暂无签退记录' in result['text']
    assert 'signInfo' not in json.dumps(result)


def test_refresh_and_drop_endpoints_validate_account_and_course(gui_server):
    request, headers, _ = gui_server
    assert request('/api/refresh', {'feature': 'boya', 'username': '123'}, headers)[0] == 400
    assert request('/api/boya/drop', {'username': '123', 'courseId': True}, headers)[0] == 400
    assert request('/api/boya/drop', {'username': [], 'courseId': 1}, headers)[0] == 400
    assert request('/api/refresh', {'feature': 'td', 'username': '123'})[0] == 403


def test_demo_refresh_and_withdraw_are_isolated_and_per_person(tmp_path):
    app = Application(tmp_path, demo=True)
    before = app.detail('boya', '23370001')
    future = next(course for course in before['courses'] if course['canDrop'])
    result = app.mutate('/api/refresh', {'feature': 'boya', 'username': '23370001'})
    assert result['detail']['updatedAt']
    app.mutate('/api/boya/drop', {'username': '23370001', 'courseId': future['id']})
    assert future['id'] not in [course['id'] for course in app.detail('boya', '23370001')['courses']]
    assert future['id'] in [course['id'] for course in app.detail('boya', '23370002')['courses']]
    assert not backends.boya_store().path('run/autobh/exclusions.json').exists()


def test_refresh_does_not_block_state_or_turn_account_query_into_automation(tmp_path, monkeypatch):
    app = Application(tmp_path)
    from autoboya.models import UserRecord
    backends.boya_store().upsert_user(UserRecord('123'))
    started, finish = threading.Event(), threading.Event()
    def slow_refresh(username):
        started.set()
        assert finish.wait(3)
    monkeypatch.setattr('autobh.boya_operations.refresh_user', slow_refresh)
    thread = threading.Thread(target=app.refresh_detail, args=('boya', '123'))
    thread.start()
    try:
        assert started.wait(2)
        with app.lock:
            assert app.snapshot()['people'][0]['features']['boya']['refreshing']
        with pytest.raises(ValueError, match='正在刷新'):
            app.refresh_detail('boya', '123')
    finally:
        finish.set()
        thread.join(3)


def test_appearance_api_is_authenticated_validated_and_injected_in_html(gui_server):
    request, headers, _ = gui_server
    assert request('/api/appearance')[0] == 403
    assert request('/api/appearance', {'appearance': 'dark'})[0] == 403
    assert request('/api/appearance', headers=headers) == (200, '{"appearance": "system"}')
    assert request('/api/appearance', {'appearance': 'dark'}, headers)[0] == 200
    assert json.loads(request('/api/appearance', headers=headers)[1])['appearance'] == 'dark'
    assert 'data-appearance="dark"' in request('/')[1]
    assert request('/api/appearance', {'appearance': 'auto'}, headers)[0] == 400
