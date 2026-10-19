import base64
import json
import plistlib
from pathlib import Path

import pytest
from scripts.sparkle import configuration,feed_url
from scripts.prepare_release import validate_app,validate_feed


@pytest.fixture
def config(tmp_path):
    data={'repository':'owner/AutoBH','public_key':base64.b64encode(b'x'*32).decode(),'keychain_account':'app.autobh.desktop'}
    path=tmp_path/'updates.json'
    path.write_text(json.dumps(data))
    return data,path


def test_channel_uses_stable_latest_release_asset_and_separates_architectures(config):
    data,path=config
    assert configuration(path)==data
    assert feed_url(data,'arm64')=='https://github.com/owner/AutoBH/releases/latest/download/appcast-arm64.xml'
    assert feed_url(data,'x86_64').endswith('appcast-x86_64.xml')
    with pytest.raises(ValueError): feed_url(data,'other')


@pytest.mark.parametrize('repository',['https://github.com/owner/repo','owner/repo/extra','owner/repo?token=x','../repo'])
def test_config_rejects_invalid_repository(config,repository):
    data,path=config
    data['repository']=repository
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):configuration(path)


def test_release_checks_public_key_and_feed_before_signing(config,tmp_path):
    data,_=config
    app=tmp_path/'AutoBH.app'
    (app/'Contents').mkdir(parents=True)
    info={'CFBundleIdentifier':'app.autobh.desktop','CFBundleVersion':'0.1.3','SUPublicEDKey':data['public_key'],
          'SUFeedURL':feed_url(data,'arm64'),'SURequireSignedFeed':True,'SUVerifyUpdateBeforeExtraction':True}
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    assert validate_app(app,data)==('0.1.3','arm64')
    info['SUPublicEDKey']=base64.b64encode(b'y'*32).decode()
    (app/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
    with pytest.raises(ValueError,match='公钥'): validate_app(app,data)


def test_release_rejects_archive_url_or_version_mismatch(config,tmp_path):
    data,_=config
    archive=tmp_path/'AutoBH-0.1.3-macOS-arm64.zip'
    archive.write_bytes(b'archive')
    feed=tmp_path/'appcast-arm64.xml'
    template='''<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"><channel><item>
    <sparkle:version>0.1.3</sparkle:version><enclosure url="{url}" length="7" sparkle:edSignature="signature"/>
    </item></channel></rss>'''
    feed.write_text(template.format(url='https://github.com/owner/AutoBH/releases/download/v0.1.3/'+archive.name))
    assert validate_feed(feed,archive,data,'0.1.3','arm64')=='signature'
    feed.write_text(template.format(url='https://unexpected.example/update.zip'))
    with pytest.raises(ValueError,match='下载链接'):validate_feed(feed,archive,data,'0.1.3','arm64')


def test_sparkle_cache_never_rewrites_running_tools_and_rejects_modification(tmp_path,monkeypatch):
    import hashlib
    import io
    import tarfile
    from scripts import sparkle
    archive=tmp_path/f'Sparkle-{sparkle.VERSION}.tar.xz'
    with tarfile.open(archive,'w:xz') as bundle:
        member=tarfile.TarInfo('bin/generate_appcast')
        member.size=4
        member.mode=0o755
        bundle.addfile(member,io.BytesIO(b'tool'))
    monkeypatch.setattr(sparkle,'SHA256',hashlib.sha256(archive.read_bytes()).hexdigest())
    directory=sparkle._ensure_distribution(tmp_path)
    tool=directory/'bin/generate_appcast'
    inode=tool.stat().st_ino
    assert sparkle._ensure_distribution(tmp_path)==directory
    assert tool.stat().st_ino==inode
    tool.write_bytes(b'altered')
    with pytest.raises(ValueError,match='已被修改'):
        sparkle._ensure_distribution(tmp_path)
    assert tool.read_bytes()==b'altered'
