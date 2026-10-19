import socket

import pytest


@pytest.fixture(autouse=True)
def isolated_homes(tmp_path, monkeypatch):
    for variable, directory in [("AUTOBH_HOME", "bh"), ("AUTOSIGN_HOME", "class"),
                                ("AUTOBOYA_HOME", "boya"), ("AUTOTD_HOME", "td"), ("AUTOBH_YGDK_HOME", "ygdk")]:
        monkeypatch.setenv(variable, str(tmp_path / directory))
    # Unit tests must never reach school systems, even if mocks regress.
    def forbidden(*args, **kwargs):
        raise AssertionError("Live network access is forbidden in AutoBH tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)

