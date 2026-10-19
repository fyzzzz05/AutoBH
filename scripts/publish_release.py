"""Explicitly publish prepared assets to an existing GitHub repository/tag."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--publish', action='store_true', help='确认将草稿公开并设为 latest；默认只创建草稿')
    args = parser.parse_args()
    directory = args.directory.resolve()
    manifest = json.loads((directory / 'release.json').read_text())
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+', manifest['repository']):
        raise ValueError('无效仓库')
    if not re.fullmatch(r'v\d+\.\d+\.\d+', manifest['tag']):
        raise ValueError('无效版本标签')
    if len(manifest['assets']) != 2:
        raise ValueError('需要一个已签名 ZIP 和对应 appcast')
    assets = []
    for name, digest in manifest['assets'].items():
        path = (directory / name).resolve()
        if path.parent != directory or not path.is_file():
            raise ValueError('发布文件必须位于发布目录内')
        if hashlib.file_digest(path.open('rb'), 'sha256').hexdigest() != digest:
            raise ValueError(f'{name} 与签名验证时的文件不符，请重新生成')
        assets.append(str(path))
    # Require an existing source tag; never invent a release commit or replace
    # published assets. Draft-first also makes interrupted uploads non-current.
    subprocess.run(['gh', 'release', 'create', manifest['tag'], '--repo', manifest['repository'], '--verify-tag',
                    '--title', f'AutoBH {manifest["version"]}', '--notes-file', str(directory / 'release-notes.md'),
                    '--draft', *assets], check=True)
    if args.publish:
        subprocess.run(['gh', 'release', 'edit', manifest['tag'], '--repo', manifest['repository'], '--draft=false', '--latest'], check=True)


if __name__ == '__main__':
    main()
