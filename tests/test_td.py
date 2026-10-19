import pytest

from autobh import backends

pytest.importorskip("auto_td")


def setup_td():
    store = backends.td_store()
    store.initialize()
    store.save_users({str(i): {"student_id": str(i), "entrance_machine_id": 1,
                              "exit_machine_id": 2, "entrance_image": "a.jpg", "exit_image": "b.jpg"}
                      for i in (1, 2)})
    return store


def test_td_pause_filters_users_without_deleting_progress():
    store = setup_td()
    state = store.load_state()
    state["daily_runs"] = {"2026-10-14": {"users": {"2": {"next_action": "exit", "completed_rounds": 1}}}}
    store.save_state(state)
    backends.set_enabled("td", "2", False)
    runner = backends.runner("td")
    assert [user.student_id for user in runner.store.list_users()] == ["1"]
    runner.store.save_state({"daily_runs": {"2026-10-14": {"users": {"1": {"next_action": "entrance"}}}}})
    assert store.load_state()["daily_runs"]["2026-10-14"]["users"]["2"]["next_action"] == "exit"
    backends.set_enabled("td", "2", True)
    assert [user.student_id for user in runner.store.list_users()] == ["1", "2"]


def test_td_one_user_scope_preserves_other_users_state():
    store = setup_td()
    state = store.load_state()
    state["daily_runs"] = {"2026-10-14": {"users": {"2": {"completed_rounds": 2}}}}
    store.save_state(state)
    runner = backends.runner("td", "1")
    assert [user.student_id for user in runner.store.list_users()] == ["1"]
    runner.store.save_state({"daily_runs": {}})
    assert store.load_state()["daily_runs"]["2026-10-14"]["users"]["2"]["completed_rounds"] == 2


def test_pause_during_a_round_preserves_the_just_completed_action():
    store = setup_td()
    state = {"daily_runs": {"2026-10-14": {"users": {"2": {"next_action": "entrance"}}}}}
    store.save_state(state)
    runner = backends.runner("td")
    # Pausing mid-request must not overwrite its completed result with old state.
    backends.set_enabled("td", "2", False)
    state["daily_runs"]["2026-10-14"]["users"]["2"]["next_action"] = "exit"
    runner.store.save_state(state)
    assert store.load_state()["daily_runs"]["2026-10-14"]["users"]["2"]["next_action"] == "exit"


def retry_fixture():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    store = setup_td()
    store.save_users({'1': store.load_users()['1']})
    settings = store.load_settings()
    settings['schedule']['windows'] = ['00:00-23:59']
    store.save_settings(settings)
    store.image_path('a.jpg').write_bytes(b'photo')
    store.image_path('b.jpg').write_bytes(b'photo')
    now = datetime(2026, 10, 15, 10, tzinfo=ZoneInfo('Asia/Shanghai'))
    runner = backends.runner('td')
    return store, runner, now


def test_connection_failure_retries_exit_preserving_rounds():
    from datetime import timedelta
    from auto_td.models import CheckResponse
    store, runner, now = retry_fixture()
    store.save_state({'daily_runs': {str(now.date()): {'users': {'1': {
        'status': 'waiting', 'next_action': 'exit', 'completed_rounds': 1}}}}})
    class Client:
        calls = 0
        def check(self, user, machine_id, **kwargs):
            self.calls += 1
            assert machine_id == user.exit_machine_id
            if self.calls == 1:
                raise ConnectionError('connect failed') from ConnectionRefusedError('refused')
            return CheckResponse(True, '成功', 20)
        def upload_photo(self, *args, **kwargs):
            pass
    client = Client()
    runner.run_once(now, client, lambda user: 60)
    progress = store.load_state()['daily_runs'][str(now.date())]['users']['1']
    assert progress['next_action'] == 'exit'
    assert progress['completed_rounds'] == 1
    assert progress['next_retry_at']
    runner.run_once(now + timedelta(seconds=30), client)
    assert client.calls == 1
    runner.run_once(now + timedelta(seconds=60), client, lambda user: 60)
    progress = store.load_state()['daily_runs'][str(now.date())]['users']['1']
    assert progress['completed_rounds'] == 2
    assert progress['next_action'] == 'entrance'
    assert client.calls == 2


def test_photo_retry_does_not_repeat_successful_check_even_after_restart():
    from datetime import timedelta
    from auto_td.models import CheckResponse
    store, runner, now = retry_fixture()
    class Client:
        checks = 0
        uploads = 0
        def check(self, *args, **kwargs):
            self.checks += 1
            return CheckResponse(True, '成功', 20)
        def upload_photo(self, *args, **kwargs):
            self.uploads += 1
            if self.uploads == 1:
                raise TimeoutError('photo timeout')
    client = Client()
    runner.run_once(now, client, lambda user: 60)
    runner = backends.runner('td')
    runner.run_once(now + timedelta(seconds=60), client, lambda user: 60)
    assert client.checks == 1
    assert client.uploads == 2
    progress = store.load_state()['daily_runs'][str(now.date())]['users']['1']
    assert progress['next_action'] == 'exit'


def test_uncertain_check_timeout_never_blindly_retries():
    from datetime import timedelta
    store, runner, now = retry_fixture()
    class Client:
        calls = 0
        def check(self, *args, **kwargs):
            self.calls += 1
            raise TimeoutError('response timeout after send')
    client = Client()
    runner.run_once(now, client)
    runner.run_once(now + timedelta(hours=1), client)
    assert client.calls == 1
    progress = store.load_state()['daily_runs'][str(now.date())]['users']['1']
    assert progress['next_retry_at'] is None
    assert not progress['retry_safe']


def test_retry_budget_is_limited_and_survives_restart():
    from datetime import timedelta
    store, runner, now = retry_fixture()
    class Client:
        calls = 0
        def check(self, *args, **kwargs):
            self.calls += 1
            raise ConnectionError('connect') from ConnectionRefusedError('refused')
    client = Client()
    for seconds in (0, 60, 240, 840, 2000):
        runner = backends.runner('td')
        runner.run_once(now + timedelta(seconds=seconds), client)
    assert client.calls == 4
    progress = store.load_state()['daily_runs'][str(now.date())]['users']['1']
    assert progress['retry_count'] == 3
    assert progress['next_retry_at'] is None


def test_reaching_limit_still_finishes_pending_photo_before_stopping():
    from datetime import timedelta
    from auto_td.models import CheckResponse
    store, runner, now = retry_fixture()
    class Client:
        checks = 0
        uploads = 0
        def check(self, *args, **kwargs):
            self.checks += 1
            return CheckResponse(True, '成功', 32)
        def upload_photo(self, *args, **kwargs):
            self.uploads += 1
            if self.uploads == 1:
                raise TimeoutError('photo timeout')
    client = Client()
    runner.run_once(now, client)
    runner = backends.runner('td')
    runner.run_once(now + timedelta(seconds=60), client)
    assert client.checks == 1
    assert client.uploads == 2
    assert store.load_state()['daily_runs'][str(now.date())]['users']['1']['status'] == 'completed'


def test_outside_window_preserves_phase_and_reports_next_allowed_retry():
    from datetime import timedelta
    store, runner, now = retry_fixture()
    settings = store.load_settings()
    settings['schedule']['windows'] = ['11:00-12:00']
    store.save_settings(settings)
    store.save_state({'daily_runs': {str(now.date()): {'users': {'1': {
        'status': 'error', 'next_action': 'exit', 'completed_rounds': 1,
        'last_error': 'Connection refused', 'updated_at': now.isoformat()}}}}})
    runner.run_once(now, client=object())
    progress = store.load_state()['daily_runs'][str(now.date())]['users']['1']
    assert progress['next_action'] == 'exit'
    assert progress['completed_rounds'] == 1
    assert progress['next_retry_at'].startswith('2026-10-15T11:00:00')
    assert '重启' not in progress['last_message']


def test_crash_checkpoint_survives_closed_window_without_repeating_check():
    from datetime import timedelta
    from auto_td.models import CheckResponse
    from autobh.td import CheckpointClient
    store, runner, now = retry_fixture()
    class Client:
        checks = 0
        uploads = 0
        def check(self, *args, **kwargs):
            self.checks += 1
            return CheckResponse(True, '成功', 20)
        def upload_photo(self, *args, **kwargs):
            self.uploads += 1
    client = Client()
    wrapped = CheckpointClient(store, client, now)
    user = runner.store.list_users()[0]
    wrapped.check(user, user.entrance_machine_id, timestamp=now.timestamp())
    # Simulate process death before native state is marked error or committed.
    store.save_state({'daily_runs': {str(now.date()): {'users': {'1': {
        'status': 'pending', 'next_action': 'entrance', 'completed_rounds': 0}}}}})
    settings = store.load_settings()
    settings['schedule']['windows'] = ['11:00-12:00']
    store.save_settings(settings)
    runner.run_once(now, client)
    runner = backends.runner('td')
    runner.run_once(now + timedelta(hours=1), client, lambda user: 60)
    assert client.checks == 1
    assert client.uploads == 1


def test_active_operation_is_visible_only_during_the_request_and_cleared_on_failure():
    from auto_td.models import CheckResponse
    from autobh.storage import read_json
    store, runner, now = retry_fixture()
    path = store.home / 'run/autobh/activity.json'
    class Client:
        def check(self, user, machine_id, **kwargs):
            current = read_json(path)
            assert current['username'] == '1' and current['phase'] == 'check'
            assert current['action'] == 'entrance'
            return CheckResponse(True, '成功', 20)
        def upload_photo(self, *args, **kwargs):
            assert read_json(path)['phase'] == 'photo'
            raise TimeoutError('photo timeout')
    runner.run_once(now, Client())
    assert not path.exists()
    assert store.load_state()['daily_runs'][str(now.date())]['users']['1']['status'] == 'error'
