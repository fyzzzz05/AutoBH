"""Pinned Sparkle distribution and public update-channel configuration."""
from __future__ import annotations

import base64
import hashlib
import json
import fcntl
import re
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = '2.10.0'
SHA256 = 'c2bf58aa8387266ac179357b1415d6f2635f044da8be41042af32425dae6da0c'
DOWNLOAD = f'https://github.com/sparkle-project/Sparkle/releases/download/{VERSION}/Sparkle-{VERSION}.tar.xz'


def configuration(path=None):
    data = json.loads(Path(path or ROOT / 'packaging/macos/updates.json').read_text())
    repository = data.get('repository', '')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+', repository):
        raise ValueError('更新仓库必须为 owner/repository')
    if len(base64.b64decode(data.get('public_key', ''), validate=True)) != 32:
        raise ValueError('更新签名公钥必须为 32 字节 Ed25519 公钥')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', data.get('keychain_account', '')):
        raise ValueError('更新签名钥匙串账号无效')
    return data


def feed_url(config, architecture):
    if architecture not in ('arm64', 'x86_64'):
        raise ValueError('不支持此架构')
    return f'https://github.com/{config["repository"]}/releases/latest/download/appcast-{architecture}.xml'


def ensure_distribution():
    directory = ROOT / 'build/macos/sparkle'
    directory.mkdir(parents=True, exist_ok=True)
    # Tools may still be running while another build asks for the framework.
    # Never overwrite a loaded executable: macOS invalidates its code signature.
    with (directory / 'distribution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _ensure_distribution(directory)


def _ensure_distribution(directory):
    archive = directory / f'Sparkle-{VERSION}.tar.xz'
    if not archive.exists():
        temporary = archive.with_suffix('.download')
        try:
            with urllib.request.urlopen(DOWNLOAD, timeout=60) as response, temporary.open('wb') as output:
                shutil.copyfileobj(response, output)
            if hashlib.file_digest(temporary.open('rb'), 'sha256').hexdigest() != SHA256:
                raise ValueError('Sparkle 下载校验失败')
            temporary.replace(archive)
        finally:
            temporary.unlink(missing_ok=True)
    if hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest() != SHA256:
        raise ValueError('Sparkle 缓存校验失败，请移除损坏的缓存后重试')
    runtime = directory / f'runtime-{VERSION}-{SHA256[:12]}'
    if not runtime.exists():
        with tempfile.TemporaryDirectory(prefix='extract-', dir=directory) as temporary:
            staging = Path(temporary) / 'runtime'
            staging.mkdir()
            with tarfile.open(archive, 'r:xz') as bundle:
                bundle.extractall(staging, filter='data')
            staging.rename(runtime)
    # Verify cached tools and framework against the pinned archive without
    # rewriting them. Treat a modified cache as an error instead of repairing
    # files which another process may be executing.
    with tarfile.open(archive, 'r:xz') as bundle:
        for member in bundle.getmembers():
            if member.isfile():
                path = runtime / member.name
                with bundle.extractfile(member) as expected, path.open('rb') as actual:
                    if hashlib.file_digest(expected, 'sha256').digest() != hashlib.file_digest(actual, 'sha256').digest():
                        raise ValueError(f'Sparkle 缓存已被修改：{member.name}')
    return runtime
