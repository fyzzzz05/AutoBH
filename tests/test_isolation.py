from unittest.mock import Mock

from autobh import backends


def test_class_paused_users_are_not_processed():
    backends.class_manager().add_user("1", "a")
    backends.class_manager().add_user("2", "b")
    backends.set_enabled("class", "2", False)
    runner = backends.runner("class")
    runner._process_user = Mock()
    runner.process_once()
    assert [call.args[1] for call in runner._process_user.call_args_list] == ["1"]


def test_class_one_user_scope_is_not_written_to_native_config():
    backends.class_manager().add_user("1", "a")
    backends.class_manager().add_user("2", "b")
    runner = backends.runner("class", "2")
    runner._process_user = Mock()
    runner.process_once()
    assert [call.args[1] for call in runner._process_user.call_args_list] == ["2"]
    assert len(backends.accounts("class")) == 2


def test_boya_rejects_cached_decisions_for_paused_users():
    from autoboya.models import UserRecord, AutomationDecision
    from autoboya.scheduler import AutomationRunner
    store = backends.boya_store()
    store.init()
    store.upsert_user(UserRecord("paused", enabled=False))
    store.upsert_user(UserRecord("active"))
    runner = AutomationRunner(store)
    runner._sign_for_user = Mock()
    assert runner.execute_decisions([AutomationDecision("sign", 10, "paused")]) == []
    runner._sign_for_user.assert_not_called()
    assert set(runner._selected_by_user({"paused": [], "active": [], "deleted": []})) == {"active"}


def test_boya_scoped_runner_excludes_other_cached_users():
    from autoboya.models import UserRecord
    store = backends.boya_store()
    store.init()
    store.upsert_user(UserRecord("1"))
    store.upsert_user(UserRecord("2"))
    runner = backends.runner("boya", "1")
    assert set(runner._selected_by_user({"1": [], "2": []})) == {"1"}
    assert len(store.user_records()) == 2


def test_class_stop_event_prevents_another_iteration():
    from threading import Event
    event = Event()
    runner = backends.runner("class")
    runner.process_once = Mock(side_effect=event.set)
    runner.run_forever(stop_event=event)
    runner.process_once.assert_called_once()
