"""Cooperative worker handoff for replacing a bundled macOS app.

Only workers executing this app's binary are touched. CLI workers and native
backgrounds from separate installations are left to their existing owners.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

from . import __version__, backends, service
from .storage import atomic_json, file_lock, read_json


def root():
    return Path(os.environ.get('AUTOBH_HOME', str(Path.home() / '.autobh'))).expanduser().resolve()


def marker():
    return root() / 'run/update-workers.json'


def process_binary(pid):
    if not isinstance(pid, int) or pid <= 0:
        return None
    result = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'comm='], capture_output=True, text=True, timeout=5)
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 and result.stdout.strip() else None


def request_stop(feature, identity):
    with file_lock(service.run_dir(feature) / 'control.lock'):
        current = read_json(service.run_dir(feature) / 'worker.json', {})
        if (current.get('pid'), current.get('token')) != (identity.get('pid'), identity.get('token')):
            raise RuntimeError('后台实例发生变化，请稍后重试更新')
        atomic_json(service.run_dir(feature) / 'stop.request', {'token': current['token']})


def restore_pending(force=False):
    with file_lock(root() / 'run/update.lock'):
        data = read_json(marker(), {})
        if not data:
            return
        if force:
            data['state'] = 'rollback'
        # The old GUI must not restart workers while Sparkle is replacing it.
        if data.get('version') == __version__ and data.get('state') == 'ready':
            return
        remaining = []
        for feature in data.get('features', []):
            current = service.status(feature)
            if current['stop_requested']:
                remaining.append(feature)
                continue
            try:
                if current['status'] == 'stopped':
                    service.start(feature, root())
            except (OSError, RuntimeError, ValueError):
                remaining.append(feature)
        if remaining:
            data['features'] = remaining
            atomic_json(marker(), data)
        else:
            marker().unlink(missing_ok=True)


def prepare(timeout=90, executable=None):
    if executable is None and not getattr(sys, 'frozen', False):
        raise ValueError('更新准备仅供打包的 macOS App 调用')
    executable = Path(executable or sys.executable).resolve()
    with file_lock(root() / 'run/update.lock'):
        previous = read_json(marker(), {})
        if previous:
            raise RuntimeError('上一次更新的后台恢复尚未完成，请稍后重试')
        identities = {}
        for feature in backends.FEATURES:
            if not backends.available(feature):
                continue
            current = service.status(feature)
            if process_binary(current['pid']) != executable:
                continue
            if current['status'] == 'native-running':
                raise RuntimeError('请先在管理后台停止由这份 App 启动的原工具后台，再安装更新')
            if current['status'] == 'running' and not current['stop_requested']:
                identities[feature] = read_json(service.run_dir(feature) / 'worker.json', {})
        data = {'version': __version__, 'state': 'preparing', 'features': []}
        atomic_json(marker(), data)
        try:
            for feature, identity in identities.items():
                # Persist intent before signaling so an interrupted handoff can
                # be recovered on the next launch without losing enabled jobs.
                data['features'].append(feature)
                atomic_json(marker(), data)
                request_stop(feature, identity)
            deadline = time.monotonic() + timeout
            while any(service.busy(feature) for feature in identities):
                if time.monotonic() >= deadline:
                    raise RuntimeError('后台当前操作尚未结束，本次更新已取消；请稍后重试')
                time.sleep(.2)
            # Catch a second window starting another worker during preparation.
            if any(process_binary(service.status(feature)['pid']) == executable for feature in backends.FEATURES
                   if backends.available(feature)):
                raise RuntimeError('后台仍在使用旧版本，请稍后重试更新')
            data['state'] = 'ready'
            atomic_json(marker(), data)
        except Exception:
            data['state'] = 'rollback'
            atomic_json(marker(), data)
            raise


def main(arguments=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'resume', 'rollback'))
    args = parser.parse_args(arguments)
    try:
        if args.action == 'prepare':
            try:
                prepare()
            except Exception:
                restore_pending(force=True)
                raise
        else:
            restore_pending(force=args.action == 'rollback')
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
