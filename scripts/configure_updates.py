"""Configure the public GitHub feed and a dedicated macOS Keychain signing key."""
import argparse
import json
import subprocess
from pathlib import Path
from sparkle import ROOT, configuration, ensure_distribution


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repository', required=True, help='owner/repository')
    parser.add_argument('--account', default='app.autobh.desktop')
    args = parser.parse_args()
    sparkle = ensure_distribution()
    subprocess.run([str(sparkle / 'bin/generate_keys'), '--account', args.account], check=True)
    public_key = subprocess.run([str(sparkle / 'bin/generate_keys'), '--account', args.account, '-p'],
                                check=True, capture_output=True, text=True).stdout.strip()
    data = {'repository': args.repository, 'public_key': public_key, 'keychain_account': args.account}
    path = ROOT / 'packaging/macos/updates.json'
    temporary = path.with_suffix('.tmp')
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        configuration(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'更新源已配置：{args.repository}；私钥保存在本机钥匙串。')


if __name__ == '__main__':
    main()
