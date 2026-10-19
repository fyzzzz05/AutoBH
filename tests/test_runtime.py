import http.client
import json
import os
import re
import selectors
import subprocess
import sys

from autobh import runtime


def test_frozen_worker_and_native_commands_do_not_assume_a_system_python(monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', '/Applications/AutoBH.app/Contents/Resources/engine/autobh-engine')
    assert runtime.autobh_command('_worker', 'td', 'test') == [sys.executable, '_worker', 'td', 'test']
    assert runtime.native_command('boya') == [sys.executable, '--native', 'boya']
    assert runtime.subprocess_environment()['PYINSTALLER_RESET_ENVIRONMENT'] == '1'


def test_normal_python_commands_still_use_native_modules(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    assert runtime.autobh_command('ui') == [sys.executable, '-m', 'autobh', 'ui']
    assert runtime.native_command('td') == [sys.executable, '-m', 'auto_td.cli']
    assert runtime.subprocess_environment() is None


def test_desktop_private_server_uses_demo_and_exits_when_parent_pipe_closes():
    process = subprocess.Popen([sys.executable, '-m', 'autobh.frozen_entry', '--desktop-server', '--demo', '--watch-parent'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            assert selector.select(10), 'Desktop server did not announce its URL'
        url = json.loads(process.stdout.readline())['url']
        assert url.startswith('http://127.0.0.1:')
        port = int(url.rsplit(':', 1)[1])
        # The global test fixture blocks school traffic; allow only this local connection.
        import socket
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        # Child response validation uses a direct socket to the loopback server.
        original = socket.socket.connect
        def local_connect(stream, address):
            if address[0] != '127.0.0.1' or address[1] != port:
                return original(stream, address)
            return stream.connect_ex(address)
        from unittest.mock import patch
        with patch.object(socket.socket, 'connect', local_connect):
            connection.request('GET', '/')
            html = connection.getresponse().read().decode()
            token = re.search(r'name="autobh-token" content="([^"]+)"', html).group(1)
            connection.request('GET', '/api/state', headers={'X-AutoBH-Token': token})
            state = json.loads(connection.getresponse().read())
            assert state['demo'] is True
            connection.close()
        process.stdin.close()
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def test_fresh_native_class_template_with_null_accounts_is_empty():
    from autobh import backends
    manager = backends.class_manager()
    manager.ensure_environment()
    assert backends.accounts('class') == []
