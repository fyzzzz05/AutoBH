"""Make signed GitHub Release assets; never publishes or reads account data."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import plistlib
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET

if __package__:
    from .sparkle import ROOT, configuration, ensure_distribution, feed_url
else:
    from sparkle import ROOT, configuration, ensure_distribution, feed_url


def validate_app(app, config):
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    version = info.get('CFBundleVersion', '')
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('发布版本必须为递增的 major.minor.patch')
    if info.get('CFBundleIdentifier') != 'app.autobh.desktop':
        raise ValueError('不是 AutoBH App')
    if info.get('SUPublicEDKey') != config['public_key']:
        raise ValueError('App 公钥与发布配置不符，请重新构建')
    architectures = [arch for arch in ('arm64', 'x86_64') if info.get('SUFeedURL') == feed_url(config, arch)]
    if len(architectures) != 1:
        raise ValueError('App 更新地址与发布配置不符')
    if not info.get('SURequireSignedFeed') or not info.get('SUVerifyUpdateBeforeExtraction'):
        raise ValueError('App 必须校验更新源和更新包签名')
    return version, architectures[0]


def validate_feed(path, archive, config, version, arch):
    root = ET.parse(path).getroot()
    items = root.findall('./channel/item')
    if len(items) != 1:
        raise ValueError('每个架构的更新源应只有当前发布版本')
    item = items[0]
    namespace = '{http://www.andymatuschak.org/xml-namespaces/sparkle}'
    enclosure = item.find('enclosure')
    expected = f'https://github.com/{config["repository"]}/releases/download/v{version}/{archive.name}'
    if enclosure is None or enclosure.get('url') != expected:
        raise ValueError('更新包下载链接不是当前 GitHub Release')
    declared_version = item.findtext(namespace + 'version') or enclosure.get(namespace + 'version')
    if declared_version != version or int(enclosure.get('length', 0)) != archive.stat().st_size:
        raise ValueError('更新源版本或包体大小不符')
    signature = enclosure.get(namespace + 'edSignature', '')
    if not signature:
        raise ValueError('更新包缺少 EdDSA 签名')
    if path.name != f'appcast-{arch}.xml':
        raise ValueError('更新源架构不符')
    return signature


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', type=Path, default=ROOT / 'dist/AutoBH.app')
    parser.add_argument('--notes', type=Path, required=True, help='UTF-8 Markdown 更新说明')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    config = configuration(args.config)
    version, arch = validate_app(args.app, config)
    sparkle = ensure_distribution()
    key = subprocess.run([str(sparkle / 'bin/generate_keys'), '--account', config['keychain_account'], '-p'],
                         check=True, capture_output=True, text=True).stdout.strip()
    if key != config['public_key']:
        raise ValueError('钥匙串签名密钥与 App 公钥不匹配，拒绝发布')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(args.app)], check=True)
    notes = args.notes.read_text(encoding='utf-8').strip()
    if not notes:
        raise ValueError('请提供更新说明')
    destination = args.output or ROOT / f'dist/releases/v{version}/{arch}'
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='autobh-release-', dir=destination.parent) as temporary:
        directory = Path(temporary)
        archive = directory / f'AutoBH-{version}-macOS-{arch}.zip'
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(args.app), str(archive)], check=True)
        archive.with_suffix('.md').write_text(notes, encoding='utf-8')
        feed = directory / f'appcast-{arch}.xml'
        subprocess.run([str(sparkle / 'bin/generate_appcast'), '--account', config['keychain_account'],
                        '--download-url-prefix', f'https://github.com/{config["repository"]}/releases/download/v{version}/',
                        '--maximum-versions', '1', '--maximum-deltas', '0', '--embed-release-notes', '-o', str(feed), str(directory)], check=True)
        signature = validate_feed(feed, archive, config, version, arch)
        # Official verifier checks both signed feed metadata and the executable archive.
        for path, extra in ((feed, []), (archive, [signature])):
            subprocess.run([str(sparkle / 'bin/sign_update'), '--account', config['keychain_account'], '--verify', str(path), *extra], check=True)
        assets = {}
        for path in (archive, feed):
            assets[path.name] = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
            path.replace(destination / path.name)
        (destination / 'release-notes.md').write_text(notes + '\n')
        (destination / 'release.json').write_text(json.dumps({'repository': config['repository'], 'tag': f'v{version}',
            'version': version, 'architecture': arch, 'assets': assets}, indent=2) + '\n')
    print(f'已生成并验证签名更新文件：{destination}')


if __name__ == '__main__':
    main()
