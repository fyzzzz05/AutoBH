"""Local Sparkle integration fixture, operated through native UI automation.

Builds a disposable older/newer app pair, starts an inert class worker
and serves a signed feed only on loopback. No real user homes or school calls.
Launch the printed app through CUA; use its Check for Updates menu. Ctrl-C cleans
up fixture workers after the test app has been closed.
"""
from __future__ import annotations
import argparse
import base64
import functools
import http.server
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import time
import uuid

from sparkle import ROOT, ensure_distribution
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--tamper', action='store_true')
    parser.add_argument('--directory', type=Path, default=ROOT/'build/macos/update-test')
    args=parser.parse_args()
    directory=args.directory.resolve()
    if directory.exists():
        raise SystemExit('Move/remove the previous disposable update-test directory after closing its app first.')
    directory.mkdir()
    key = Ed25519PrivateKey.generate()
    key_file = directory / 'disposable-signing-key'
    descriptor = os.open(key_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(base64.b64encode(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())))
    public_key = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    feed_dir=directory/'feed'
    feed_dir.mkdir()
    handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(feed_dir))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    feed_url=f'http://127.0.0.1:{server.server_address[1]}/appcast-arm64.xml'
    env={key:value for key,value in os.environ.items() if key not in ('PYTHONPATH','PYTHONHOME','VIRTUAL_ENV')}
    homes={key:str(directory/key) for key in ('AUTOBH_HOME','AUTOSIGN_HOME','AUTOBOYA_HOME','AUTOTD_HOME')}
    env.update(homes)
    # Enabled so recovery exercises service.start, but an empty password makes
    # the native runner skip it before login or any school network operation.
    class_home = Path(homes['AUTOSIGN_HOME'])
    class_home.mkdir(parents=True)
    (class_home / 'config.yaml').write_text('accounts:\n  - username: update-test-inert\n    password: ""\n    enabled: true\n')
    env['PYINSTALLER_RESET_ENVIRONMENT']='1'
    identifier='app.autobh.updatecheck.'+uuid.uuid4().hex
    apps=[]
    for label,version in [('installed','0.1.2'),('candidate','0.1.4')]:
        app=directory/label/'AutoBH Update Test.app'
        app.parent.mkdir()
        subprocess.run(['ditto',str(ROOT/'dist/AutoBH.app'),str(app)],check=True)
        path=app/'Contents/Info.plist'
        info=plistlib.loads(path.read_bytes())
        info.update(CFBundleName='AutoBH Update Test',CFBundleDisplayName='AutoBH Update Test',
                    CFBundleIdentifier=identifier,CFBundleVersion=version,CFBundleShortVersionString=version,
                    SUFeedURL=feed_url,SUPublicEDKey=public_key,SUEnableAutomaticChecks=False,LSEnvironment=homes)
        path.write_bytes(plistlib.dumps(info))
        subprocess.run(['codesign','--force','--deep','--sign','-','--timestamp=none',str(app)],check=True,capture_output=True)
        apps.append(app)
    sparkle=ensure_distribution()
    archive=feed_dir/'AutoBH-0.1.4-macOS-arm64.zip'
    subprocess.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(apps[1]),str(archive)],check=True)
    subprocess.run([str(sparkle/'bin/generate_appcast'),'--ed-key-file',str(key_file),
                    '--download-url-prefix',f'http://127.0.0.1:{server.server_address[1]}/','--maximum-deltas','0',
                    '-o',str(feed_dir/'appcast-arm64.xml'),str(feed_dir)],check=True)
    key_file.unlink()
    if args.tamper:
        content=bytearray(archive.read_bytes())
        content[len(content)//2]^=1
        archive.write_bytes(content)
    engine=apps[0]/'Contents/Resources/engine/autobh-engine'
    log=(directory/'worker-test.log').open('w')
    worker=subprocess.Popen([str(engine),'_worker','class','isolated-update-worker'],env=env,
                            stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
    marker=Path(homes['AUTOSIGN_HOME'])/'run/autobh/worker.json'
    for _ in range(100):
        if marker.exists() and json.loads(marker.read_text()).get('state')=='running':break
        if worker.poll() is not None:raise RuntimeError('Test worker failed')
        time.sleep(.1)
    (directory/'test.json').write_text(json.dumps({'app':str(apps[0]),'originalWorker':worker.pid,
                                                 'homes':homes,'identifier':identifier,'tampered':args.tamper}))
    print(json.dumps({'app':str(apps[0]),'feed':feed_url,'originalWorker':worker.pid,'tampered':args.tamper}),flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        # Current test worker may be a different PID after update. Request its
        # normal cooperative shutdown through this isolated profile only.
        current=apps[0]/'Contents/Resources/engine/autobh-engine'
        subprocess.run([str(current),'service','stop','--feature','class'],env=env,capture_output=True,timeout=15)
        log.close()


if __name__=='__main__':
    main()
