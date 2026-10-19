import pytest
import json
from io import StringIO

from autobh import backends
from autobh.cli import main


def test_merge_native_users_without_copying_passwords(capsys):
    backends.class_manager().add_user("23370001", "secret-class")
    from autoboya.models import UserRecord
    store = backends.boya_store()
    store.upsert_user(UserRecord("23370001", "keyring", campus="杭州"))
    assert main(["user", "add", "23370001", "--name", "张三", "--group", "同学"]) == 0
    capsys.readouterr()
    assert main(["user", "list", "--json"]) == 0
    output = capsys.readouterr().out
    rows = json.loads(output)
    assert len(rows) == 1
    assert rows[0]["name"] == "张三"
    assert rows[0]["features"]["boya"]["campus"] == "杭州"
    assert rows[0]["features"]["class"]["enabled"] is True
    assert "secret-class" not in output


def test_filter_group_and_feature(capsys):
    backends.class_manager().add_user("1", "secret")
    main(["user", "add", "1", "--group", "A"])
    main(["user", "add", "2", "--group", "B"])
    capsys.readouterr()
    assert main(["user", "list", "--feature", "class", "--group", "A", "--json"]) == 0
    assert [row["username"] for row in json.loads(capsys.readouterr().out)] == ["1"]


def test_account_add_stdin_preserves_pause_and_uses_native_storage(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", StringIO("first-password\n"))
    assert main(["account", "add", "class", "1", "--password-stdin"]) == 0
    assert main(["feature", "disable", "class", "--user", "1"]) == 0
    monkeypatch.setattr("sys.stdin", StringIO("updated-password\n"))
    assert main(["account", "add", "class", "1", "--password-stdin"]) == 0
    assert backends.accounts("class") == [{"username": "1", "enabled": False}]
    assert backends.class_manager().list_users()[0]["password"] == "updated-password"
    assert "password" not in capsys.readouterr().out


def test_boya_explicit_password_fallback(monkeypatch, capsys):
    monkeypatch.setattr("autoboya.storage.try_store_keyring_password", lambda *args: False)
    monkeypatch.setattr("sys.stdin", StringIO("secret\n"))
    assert main(["account", "add", "boya", "1", "--password-stdin"]) == 1
    assert backends.boya_store().get_user("1") is None
    monkeypatch.setattr("sys.stdin", StringIO("secret\n"))
    assert main(["account", "add", "boya", "1", "--password-stdin", "--unsafe-store-password"]) == 0
    assert backends.boya_store().load_unsafe_password("1") == "secret"
    assert "secret" not in capsys.readouterr().out


def test_unknown_or_disabled_user_cannot_run(monkeypatch, capsys):
    backends.class_manager().add_user("1", "secret")
    backends.set_enabled("class", "1", False)
    def forbidden(*args):
        raise AssertionError("disabled user must not create a runner")
    monkeypatch.setattr(backends, "runner", forbidden)
    assert main(["run", "--once", "--feature", "class", "--user", "1"]) == 1
    assert main(["run", "--once", "--feature", "class", "--user", "missing"]) == 1


def test_native_help_and_unknown_options_are_passed_unchanged(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(backends, "passthrough", lambda feature, args: calls.append((feature, args)) or 0)
    assert main(["boya", "--help"]) == 0
    assert main(["--home", str(tmp_path), "td", "user", "add", "1", "--quick", "学院路"]) == 0
    assert main([f"--home={tmp_path}", "class", "--help"]) == 0
    assert calls == [("boya", ["--help"]), ("td", ["user", "add", "1", "--quick", "学院路"]),
                     ("class", ["--help"])]


def test_missing_optional_td_does_not_break_all_status(monkeypatch, capsys):
    original = backends.available
    monkeypatch.setattr(backends, "available", lambda feature: feature != "td" and original(feature))
    assert main(["service", "status", "--json"]) == 0
    assert next(row for row in json.loads(capsys.readouterr().out) if row["feature"] == "td")["status"] == "unavailable"
    assert main(["service", "start", "--feature", "td"]) == 1


def test_single_feature_error_does_not_skip_other_services(monkeypatch, capsys):
    from autobh import service
    def start(feature, home):
        if feature == "class":
            raise RuntimeError("mock failure")
        return {"feature": feature, "status": "skipped"}
    monkeypatch.setattr(service, "start", start)
    assert main(["service", "start", "--json"]) == 1
    results = json.loads(capsys.readouterr().out)
    assert results[0]["status"] == "error"
    assert results[1]["feature"] == "boya"


def test_td_log_uses_native_filename(capsys):
    path = backends.native_home("td") / "logs" / "2026-10-14-daytime-log.txt"
    path.parent.mkdir(parents=True)
    path.write_text("first\nsecond\n", encoding="utf-8")
    assert main(["logs", "--feature", "td", "--lines", "1"]) == 0
    assert capsys.readouterr().out == "second\n"


def test_remove_person_deletes_all_bindings_and_only_that_profile(capsys):
    from autoboya.models import UserRecord
    from autobh.storage import Registry
    import os
    from pathlib import Path
    import pytest
    pytest.importorskip("auto_td")
    for username in ("1", "2"):
        backends.class_manager().add_user(username, "secret")
        backends.boya_store().upsert_user(UserRecord(username))
        from autobh import ygdk
        ygdk.bind(username, "")
        assert main(["user", "add", username, "--name", "同学"]) == 0
    td = backends.td_store()
    td.initialize()
    td.save_users({username: {"student_id": username} for username in ("1", "2")})
    backends.set_enabled("td", "1", False)
    assert main(["user", "remove", "1"]) == 0
    for feature in backends.FEATURES:
        assert [row["username"] for row in backends.accounts(feature)] == ["2"]
    assert "1" not in backends.td_switches()
    assert set(Registry(Path(os.environ["AUTOBH_HOME"])).people()) == {"2"}


def test_remove_profile_without_accounts(capsys):
    assert main(["user", "add", "1", "--name", "张三"]) == 0
    assert main(["user", "remove", "1"]) == 0
    capsys.readouterr()
    assert main(["user", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []
    assert main(["user", "remove", "1"]) == 1


def test_remove_person_does_not_modify_anything_when_account_lock_is_busy():
    from autobh.storage import file_lock
    backends.class_manager().add_user("1", "secret")
    with file_lock(backends.native_home("boya") / "run" / "autobh" / "accounts.lock"):
        assert main(["user", "remove", "1"]) == 1
    assert [row["username"] for row in backends.accounts("class")] == ["1"]


def test_remove_person_retains_profile_and_reports_partial_failure(monkeypatch, capsys):
    from autoboya.models import UserRecord
    backends.class_manager().add_user("1", "secret")
    backends.boya_store().upsert_user(UserRecord("1"))
    assert main(["user", "add", "1", "--name", "张三"]) == 0
    original = backends.remove_account
    def fail_boya(feature, username):
        if feature == "boya":
            raise OSError("mock failure")
        return original(feature, username)
    monkeypatch.setattr(backends, "remove_account", fail_boya)
    assert main(["user", "remove", "1"]) == 1
    assert "已删除功能：class" in capsys.readouterr().err
    assert backends.accounts("class") == []
    capsys.readouterr()
    assert main(["user", "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["name"] == "张三"


@pytest.mark.parametrize(('feature', 'arguments'), [('boya', ['run-once']), ('td', ['run', '--once'])])
def test_native_automation_aliases_use_guarded_manager(monkeypatch, feature, arguments):
    from autobh import backends, service
    calls = []
    monkeypatch.setattr(backends, 'require', lambda feature: None)
    monkeypatch.setattr(service, 'busy', lambda feature: False)
    monkeypatch.setattr(service, 'run_once', lambda feature: calls.append(feature) or {})
    assert backends.passthrough(feature, arguments) == 0
    assert calls == [feature]
