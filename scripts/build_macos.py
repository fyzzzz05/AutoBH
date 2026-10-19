"""Build a self-contained macOS app and drag-to-install DMG.

Run using an isolated environment with `pip install -e '.[td]' pyinstaller`.
PyInstaller options: https://pyinstaller.org/en/stable/usage.html
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import tempfile
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*command):
    subprocess.run([str(part) for part in command], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-gui', action='store_true')
    parser.add_argument('--sign-identity', default='-')
    parser.add_argument('--skip-dmg', action='store_true', help='只构建 App，供在线更新打包使用')
    parser.add_argument('--updates-config', type=Path)
    args = parser.parse_args()
    if sys.platform != 'darwin':
        raise SystemExit('Build the macOS installer on a Mac.')
    from autobh import __version__
    from sparkle import configuration, ensure_distribution, feed_url
    updates = configuration(args.updates_config)
    sparkle = ensure_distribution()
    architecture = platform.machine()
    if architecture not in ('arm64', 'x86_64'):
        raise SystemExit(f'Unsupported architecture: {architecture}')
    work = ROOT / 'build/macos'
    output = ROOT / 'dist'
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=True)
    if not args.skip_gui:
        run(sys.executable, ROOT / 'scripts/build_gui.py')
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--console',
               '--name', 'autobh-engine', '--clean', '--distpath', str(work / 'engine-dist'),
               '--workpath', str(work / 'freeze'), '--specpath', str(work),
               '--target-architecture', architecture, '--log-level', 'WARN',
               '--paths', str(ROOT / 'src'), '--paths', str(ROOT / 'AutoSign/CLI/src'),
               '--paths', str(ROOT / 'AutoBoya'),
               '--exclude-module', 'pytest', '--exclude-module', 'tkinter',
               '--add-data', f'{ROOT / "src/autobh/web"}:autobh/web']
    for package in ('autobh', 'autosign_cli', 'autoboya', 'auto_td', 'keyring.backends'):
        command += ['--collect-all', package]
    for package in ('AutoBH', 'autotd-buaa', 'keyring'):
        command += ['--copy-metadata', package]
    command.append(str(ROOT / 'src/autobh/frozen_entry.py'))
    run(*command)
    engine = work / 'engine-dist/autobh-engine/autobh-engine'
    with tempfile.TemporaryDirectory(prefix='autobh-package-check-') as directory:
        environment = {key: value for key, value in os.environ.items() if key not in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV')}
        environment['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
        for key in ('AUTOBH_HOME', 'AUTOSIGN_HOME', 'AUTOBOYA_HOME', 'AUTOTD_HOME', 'AUTOBH_YGDK_HOME'):
            environment[key] = str(Path(directory) / key)
        def check(*arguments):
            return subprocess.run([str(engine), *arguments], cwd=directory, env=environment,
                                  capture_output=True, text=True, timeout=30, check=True).stdout
        check('--version')
        doctor = json.loads(check('doctor', '--json'))
        if not all(item['module_available'] for item in doctor['checks']):
            raise RuntimeError('A native tool is missing from the bundled engine.')
        for feature in ('class', 'boya', 'td', 'ygdk'):
            check(feature, '--help')
        print('Standalone engine verified with system-only PATH and isolated data directories.')
    app = output / 'AutoBH.app'
    if app.exists():
        shutil.rmtree(app)
    contents = app / 'Contents'
    executable = contents / 'MacOS'
    resources = contents / 'Resources'
    executable.mkdir(parents=True)
    resources.mkdir()
    shutil.copytree(work / 'engine-dist/autobh-engine', resources / 'engine', symlinks=True)
    frameworks = contents / 'Frameworks'
    frameworks.mkdir()
    shutil.copytree(sparkle / 'Sparkle.framework', frameworks / 'Sparkle.framework', symlinks=True)
    run('xcrun', 'swiftc', '-O', '-swift-version', '5', '-target', f'{architecture}-apple-macosx13.0',
        '-framework', 'Cocoa', '-framework', 'WebKit', '-F', sparkle, '-framework', 'Sparkle',
        '-Xlinker', '-rpath', '-Xlinker', '@executable_path/../Frameworks', ROOT / 'packaging/macos/AutoBH.swift', '-o', executable / 'AutoBH')
    iconset = work / 'AutoBH.iconset'
    run('xcrun', 'swift', ROOT / 'packaging/macos/Icon.swift', iconset)
    run('iconutil', '-c', 'icns', iconset, '-o', resources / 'AutoBH.icns')
    with (contents / 'Info.plist').open('wb') as stream:
        plistlib.dump({'CFBundleName': 'AutoBH', 'CFBundleDisplayName': 'AutoBH',
                      'CFBundleIdentifier': 'app.autobh.desktop', 'CFBundleExecutable': 'AutoBH',
                      'CFBundlePackageType': 'APPL', 'CFBundleShortVersionString': __version__,
                      'CFBundleVersion': __version__, 'CFBundleIconFile': 'AutoBH.icns',
                      'LSMinimumSystemVersion': '13.0', 'NSHighResolutionCapable': True,
                      'NSAppTransportSecurity': {'NSAllowsLocalNetworking': True},
                      'NSHumanReadableCopyright': 'AutoBH contributors',
                      'SUFeedURL': feed_url(updates, architecture), 'SUPublicEDKey': updates['public_key'],
                      'SUEnableAutomaticChecks': True, 'SUAllowsAutomaticUpdates': False,
                      'SUVerifyUpdateBeforeExtraction': True, 'SURequireSignedFeed': True}, stream)
    versions = {dist.metadata['Name']: dist.version for dist in importlib.metadata.distributions()}
    (resources / 'build-info.json').write_text(json.dumps({'version': __version__, 'architecture': architecture,
        'python': platform.python_version(), 'packages': versions}, indent=2), encoding='utf-8')
    notices = []
    for dist in importlib.metadata.distributions():
        notices.append(f"\n{'=' * 70}\n{dist.metadata['Name']} {dist.version}\n")
        for file in dist.files or []:
            if ('license' in str(file).lower() or 'copying' in file.name.lower()) and file.suffix.lower() in ('', '.txt', '.md', '.rst'):
                path = dist.locate_file(file)
                if path.is_file() and path.stat().st_size < 100000:
                    notices.append(path.read_text(encoding='utf-8', errors='replace'))
    notices.append('\nSparkle\n' + (sparkle / 'LICENSE').read_text())
    (resources / 'THIRD_PARTY_NOTICES.txt').write_text('\n'.join(notices), encoding='utf-8')
    timestamp = '--timestamp=none' if args.sign_identity == '-' else '--timestamp'
    run('codesign', '--force', '--deep', '--sign', args.sign_identity, timestamp, app)
    run('codesign', '--verify', '--deep', '--strict', app)
    run(sys.executable, ROOT / 'scripts/check_macos.py', app)
    if args.skip_dmg:
        print(f'App: {app}')
        return
    stage_context = tempfile.TemporaryDirectory(prefix='dmg-stage-', dir=work)
    stage = Path(stage_context.name)
    run('ditto', app, stage / 'AutoBH.app')
    (stage / 'Applications').symlink_to('/Applications')
    (stage / '安装说明.txt').write_text('AutoBH\n\n将 AutoBH.app 拖入 Applications（应用程序）后打开。\n\n内置 Python 与前端，不需要安装 Python 或 Node.js。\n账号、缓存和设置保存在原有本机数据目录，安装包不包含个人账号。\n关闭 App 不会停止已经启动的自动打卡后台；停止后台请使用“管理后台”。\n', encoding='utf-8')
    image = output / f'AutoBH-{__version__}-macOS-{architecture}.dmg'
    try:
        run('hdiutil', 'create', '-volname', 'AutoBH', '-srcfolder', stage, '-format', 'UDZO', '-ov', image)
    finally:
        stage_context.cleanup()
    digest = hashlib.file_digest(image.open('rb'), 'sha256').hexdigest()
    image.with_suffix('.dmg.sha256').write_text(f'{digest}  {image.name}\n')
    print(f'App: {app}\nDMG: {image}\nSHA256: {digest}')


if __name__ == '__main__':
    main()
