"""Trash generated, inactive macOS artifacts without creating rollback archives."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import plistlib
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def info(app):
    return plistlib.loads((app / 'Contents/Info.plist').read_bytes())


def running_binaries():
    output = subprocess.run(['ps', '-ax', '-o', 'comm='], check=True, capture_output=True, text=True).stdout
    return [Path(line.strip()) for line in output.splitlines() if line.strip().startswith('/')]


def unused(path, binaries):
    return not path.is_symlink() and not any(binary.is_relative_to(path.resolve()) for binary in binaries)


def candidates(root, installed, binaries):
    work, dist = root / 'build/macos', root / 'dist'
    version = info(installed)['CFBundleShortVersionString']
    current = tuple(map(int, version.split('.')))
    previous = work / 'installed-backups/previous.zip'
    result = [previous] if previous.is_file() and unused(previous, binaries) else []
    for app in (work / 'installed-backups').glob('AutoBH*.app'):
        if unused(app, binaries) and info(app).get('CFBundleIdentifier') == 'app.autobh.desktop':
            result.append(app)
    for pattern in ('update-test*', 'local-ui-update-*', 'dmg-stage'):
        for directory in work.glob(pattern):
            apps = list(directory.rglob('AutoBH*.app')) if directory.is_dir() else []
            if apps and unused(directory, binaries) and all(str(info(app).get('CFBundleIdentifier', '')).startswith('app.autobh.') for app in apps):
                result.append(directory)
    built = dist / 'AutoBH.app'
    archive = dist / f'releases/v{version}/arm64/AutoBH-{version}-macOS-arm64.zip'
    # Only discard an installed, identical build that also has a release archive.
    manifest = Path('Contents/_CodeSignature/CodeResources')
    if built.exists() and unused(built, binaries) and archive.is_file() and (built / manifest).read_bytes() == (installed / manifest).read_bytes():
        result.append(built)
    for image in dist.glob('AutoBH-*-macOS-*.dmg'):
        match = re.fullmatch(r'AutoBH-(\d+)\.(\d+)\.(\d+)-macOS-(arm64|x86_64)\.dmg', image.name)
        if match and tuple(map(int, match.groups()[:3])) < current:
            result.extend([image, *([image.with_suffix('.dmg.sha256')] if image.with_suffix('.dmg.sha256').exists() else [])])
    for release in (dist / 'releases').glob('v*'):
        match = re.fullmatch(r'v(\d+)\.(\d+)\.(\d+)', release.name)
        if match and tuple(map(int, match.groups())) < current and unused(release, binaries):
            result.append(release)
    return sorted(set(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='移入系统废纸篓；不创建回滚包，不清空废纸篓')
    args = parser.parse_args()
    installed = Path('/Applications/AutoBH.app')
    if info(installed).get('CFBundleIdentifier') != 'app.autobh.desktop':
        raise SystemExit('未找到本机已安装的 AutoBH')
    binaries = running_binaries()
    paths = candidates(ROOT, installed, binaries)
    if args.apply:
        # Recheck immediately before moving; never touch an active app/engine.
        active = running_binaries()
        paths = [path for path in paths if unused(path, active)]
        if paths:
            subprocess.run(['/usr/bin/trash', '--stopOnError', *map(str, paths)], check=True)
    print(json.dumps({'applied': args.apply, 'count': len(paths), 'paths': [str(path.relative_to(ROOT)) for path in paths]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
