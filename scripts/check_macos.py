"""Verify a packaged app/DMG with isolated accounts and no school requests."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import http.client
import json
import os
import plistlib
from pathlib import Path
import selectors
import subprocess
import tempfile
import time


@contextmanager
def application(path):
    if path.suffix != '.dmg':
        yield path
        return
    with tempfile.TemporaryDirectory(prefix='autobh-volume-') as temporary:
        mount = Path(temporary) / 'volume'
        mount.mkdir()
        subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', str(mount), str(path)], check=True, capture_output=True)
        try:
            assert (mount / 'Applications').is_symlink()
            yield mount / 'AutoBH.app'
        finally:
            subprocess.run(['hdiutil', 'detach', str(mount)], check=True, capture_output=True)


def verify(app):
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True, capture_output=True)
    private_names = {'people.json', 'users.json', 'secrets.json', 'state.json', 'autotd.pid', 'autoboya.pid', 'autosign.pid', 'accounts.json', 'password.json', 'cache.json', 'submissions.json'}
    assert not [p for p in app.rglob('*') if p.name in private_names], 'Unexpected personal data file in app'
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    if 'SUFeedURL' in info:
        assert info['SUFeedURL'].startswith('https://github.com/')
        assert info.get('SUPublicEDKey') and info.get('SUVerifyUpdateBeforeExtraction') and info.get('SURequireSignedFeed')
        assert (app / 'Contents/Frameworks/Sparkle.framework/Sparkle').is_file()
        links = subprocess.run(['otool', '-L', str(app / 'Contents/MacOS/AutoBH')], capture_output=True, text=True, check=True).stdout
        assert '@rpath/Sparkle.framework/' in links
    assert list((app / 'Contents/Resources').rglob('UBAA-LICENSE.txt')), 'Missing UBAA attribution'
    engine = app / 'Contents/Resources/engine/autobh-engine'
    with tempfile.TemporaryDirectory(prefix='autobh-runtime-') as temporary:
        root = Path(temporary)
        env = {key: value for key, value in os.environ.items() if key not in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV')}
        env['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
        for key in ('AUTOBH_HOME', 'AUTOSIGN_HOME', 'AUTOBOYA_HOME', 'AUTOTD_HOME', 'AUTOBH_YGDK_HOME'):
            env[key] = str(root / key)
        def check(*args):
            return subprocess.run([str(engine), *args], cwd=root, env=env, capture_output=True, text=True, timeout=20, check=True).stdout
        assert 'AutoBH' in check('--version')
        if 'SUFeedURL' in info:
            check('--update-workers', 'resume')
        assert all(row['module_available'] for row in json.loads(check('doctor', '--json'))['checks'])
        for feature in ('class', 'boya', 'td', 'ygdk'):
            check(feature, '--help')
        desktop = subprocess.Popen([str(engine), '--desktop-server', '--demo', '--watch-parent'], cwd=root, env=env,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        worker = None
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(desktop.stdout, selectors.EVENT_READ)
                assert selector.select(10), 'Private GUI did not start'
            url = json.loads(desktop.stdout.readline())['url']
            assert url.startswith('http://127.0.0.1:')
            connection = http.client.HTTPConnection('127.0.0.1', int(url.rsplit(':', 1)[1]), timeout=5)
            connection.request('GET', '/')
            response = connection.getresponse()
            assert response.status == 200 and 'AutoBH' in response.read().decode()
            connection.close()
            # No accounts exist. This exercises the packaged worker entry point
            # and cooperative stop without invoking authentication or school APIs.
            worker = subprocess.Popen([str(engine), '--home', env['AUTOBH_HOME'], '_worker', 'class', 'package-test-token'],
                                      cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            marker = Path(env['AUTOSIGN_HOME']) / 'run/autobh/worker.json'
            for _ in range(50):
                if marker.exists() and json.loads(marker.read_text()).get('state') == 'running':
                    break
                if worker.poll() is not None:
                    raise RuntimeError(worker.stderr.read()[-1000:])
                time.sleep(.1)
            assert marker.exists() and json.loads(marker.read_text())['state'] == 'running'
            desktop.stdin.close()
            assert desktop.wait(timeout=5) == 0
            assert worker.poll() is None, 'Background worker stopped with the GUI'
            check('user', 'list')
            check('service', 'stop', '--feature', 'class')
            assert worker.wait(timeout=10) == 0
        finally:
            for process in (desktop, worker):
                if process is not None and process.poll() is None:
                    process.terminate()
                    process.wait(timeout=5)
    print('PASS: signature, no personal data, self-contained CLI/native tools, GUI lifecycle, independent background worker.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    with application(args.artifact.resolve()) as app:
        verify(app)
