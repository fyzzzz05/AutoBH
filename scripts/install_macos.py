"""Install a verified local build without retaining old app bundles or archives.

Quit the GUI first. Prepare release assets before installing; relaunch the App
following installation so its normal handoff restores the previous workers.
"""
from pathlib import Path
import subprocess
import tempfile

if __package__:
    from .cleanup_macos import ROOT, info, running_binaries
else:
    from cleanup_macos import ROOT, info, running_binaries
from autobh.update_workers import prepare, restore_pending


def verify(app):
    if info(app).get('CFBundleIdentifier') != 'app.autobh.desktop':
        raise ValueError('不是 AutoBH App')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True, capture_output=True)


def install(source, target):
    source, target = source.resolve(), target.resolve()
    if source == target:
        raise ValueError('构建目录不能是已安装目录')
    if target / 'Contents/MacOS/AutoBH' in running_binaries():
        raise RuntimeError('请先退出 AutoBH 窗口；后台可继续运行')
    verify(source)
    verify(target)
    with tempfile.TemporaryDirectory(prefix='.autobh-install-', dir=target.parent) as directory:
        temporary = Path(directory)
        incoming, previous = temporary / 'incoming.app', temporary / 'previous.app'
        subprocess.run(['ditto', str(source), str(incoming)], check=True)
        verify(incoming)
        attempted = False
        try:
            # Existing helper serializes updates and stops only this bundle's workers.
            attempted = True
            prepare(executable=str(target / 'Contents/Resources/engine/autobh-engine'))
            target.rename(previous)
            incoming.rename(target)
            verify(target)
        except Exception:
            if previous.exists():
                if target.exists():
                    target.rename(temporary / 'failed.app')
                previous.rename(target)
            if attempted:
                restore_pending(force=True)
            raise
    print(f'已安装 {info(target)["CFBundleShortVersionString"]}；安装成功后不保留旧版本。重新打开 App 恢复原有后台。')


if __name__ == '__main__':
    install(ROOT / 'dist/AutoBH.app', Path('/Applications/AutoBH.app'))
