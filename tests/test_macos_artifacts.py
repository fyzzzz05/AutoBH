from pathlib import Path
import plistlib
import shutil
from unittest.mock import Mock

import pytest

from scripts import cleanup_macos as cleanup
from scripts import install_macos as installer


def app(path, version='0.1.8', identifier='app.autobh.desktop', content='old'):
    (path / 'Contents/MacOS').mkdir(parents=True)
    (path / 'Contents/_CodeSignature').mkdir()
    (path / 'Contents/Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': identifier, 'CFBundleShortVersionString': version}))
    (path / 'Contents/MacOS/AutoBH').write_text(content)
    (path / 'Contents/_CodeSignature/CodeResources').write_text(content)
    return path


def test_cleanup_only_selects_generated_inactive_apps_and_old_packages(tmp_path):
    installed = app(tmp_path / 'Applications/AutoBH.app')
    old = app(tmp_path / 'build/macos/installed-backups/AutoBH-old.app')
    active = app(tmp_path / 'build/macos/installed-backups/AutoBH-active.app')
    unrelated = app(tmp_path / 'build/macos/installed-backups/AutoBH-unrelated.app', identifier='org.other')
    dist = tmp_path / 'dist'; dist.mkdir()
    past = dist / 'AutoBH-0.1.7-macOS-arm64.dmg'; past.touch()
    current = dist / 'AutoBH-0.1.8-macOS-arm64.dmg'; current.touch()
    future = dist / 'AutoBH-0.1.9-macOS-arm64.dmg'; future.touch()
    selected = cleanup.candidates(tmp_path, installed, [active / 'Contents/MacOS/AutoBH'])
    assert selected == sorted([old, past])
    assert active.exists() and unrelated.exists() and installed.exists()


def test_build_copy_cleanup_requires_identical_installed_manifest_and_release_archive(tmp_path):
    installed = app(tmp_path / 'Applications/AutoBH.app')
    built = app(tmp_path / 'dist/AutoBH.app', content='not-installed')
    archive = tmp_path / 'dist/releases/v0.1.8/arm64/AutoBH-0.1.8-macOS-arm64.zip'
    archive.parent.mkdir(parents=True); archive.touch()
    assert built not in cleanup.candidates(tmp_path, installed, [])
    (built / 'Contents/_CodeSignature/CodeResources').write_text('old')
    assert built in cleanup.candidates(tmp_path, installed, [])
    assert built not in cleanup.candidates(tmp_path, installed, [built / 'Contents/MacOS/AutoBH'])


def test_cleanup_removes_legacy_rollback_without_creating_new_archive(tmp_path):
    installed = app(tmp_path / 'Applications/AutoBH.app')
    directory = tmp_path / 'build/macos/installed-backups'; directory.mkdir(parents=True)
    previous = directory / 'previous.zip'; previous.write_bytes(b'old rollback')
    unrelated = directory / 'personal.zip'; unrelated.write_bytes(b'keep')
    assert cleanup.candidates(tmp_path, installed, []) == [previous]
    assert unrelated.exists()


@pytest.mark.parametrize('fail', [False, True])
def test_installer_cleans_temporary_bundles_and_restores_old_app_on_failure(tmp_path, monkeypatch, fail):
    source = app(tmp_path / 'build/AutoBH.app', content='new')
    target = app(tmp_path / 'Applications/AutoBH.app', content='old')
    monkeypatch.setattr(installer, 'running_binaries', lambda: [])
    prepare, restore = Mock(), Mock()
    monkeypatch.setattr(installer, 'prepare', prepare)
    monkeypatch.setattr(installer, 'restore_pending', restore)
    def verify(path):
        if fail and path == target and (path / 'Contents/MacOS/AutoBH').read_text() == 'new':
            raise ValueError('new signature invalid')
    monkeypatch.setattr(installer, 'verify', verify)
    monkeypatch.setattr(installer.subprocess, 'run', lambda command, **_: shutil.copytree(command[1], command[2]))
    if fail:
        with pytest.raises(ValueError, match='signature'):
            installer.install(source, target)
        assert (target / 'Contents/MacOS/AutoBH').read_text() == 'old'
        restore.assert_called_once_with(force=True)
    else:
        installer.install(source, target)
        assert (target / 'Contents/MacOS/AutoBH').read_text() == 'new'
        restore.assert_not_called()
    prepare.assert_called_once()
    assert list(target.parent.glob('.autobh-install-*')) == []
    assert list(tmp_path.rglob('*.zip')) == []


def test_installer_refuses_to_replace_running_gui(tmp_path, monkeypatch):
    source = app(tmp_path / 'build/AutoBH.app')
    target = app(tmp_path / 'Applications/AutoBH.app')
    monkeypatch.setattr(installer, 'running_binaries', lambda: [target / 'Contents/MacOS/AutoBH'])
    prepare = Mock(); monkeypatch.setattr(installer, 'prepare', prepare)
    with pytest.raises(RuntimeError, match='先退出'):
        installer.install(source, target)
    prepare.assert_not_called()
