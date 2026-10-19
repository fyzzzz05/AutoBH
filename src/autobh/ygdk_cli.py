"""CLI for sunshine sports; submissions always require an explicit confirmation."""
import argparse
import base64
import json
import uuid
from pathlib import Path

from . import ygdk


def main(arguments=None):
    parser = argparse.ArgumentParser(prog='autobh ygdk', description='阳光体育：概览、历史记录和手动提交；后台仅同步数据')
    commands = parser.add_subparsers(dest='action', required=True)
    for name in ('status', 'refresh', 'records'):
        child = commands.add_parser(name)
        child.add_argument('--user', required=True)
        if name == 'records':
            child.add_argument('--page', type=int, default=1)
    for name in ('submit', 'batch'):
        command = commands.add_parser(name)
        command.add_argument('--user', required=True)
        command.add_argument('--item', type=int, required=True)
        if name == 'batch':
            command.add_argument('--plan', type=Path, required=True, help='JSON 数组，每段含 startTime、endTime，最多 4 段')
        else:
            command.add_argument('--start', required=True, help='北京时间 yyyy-MM-ddTHH:mm')
            command.add_argument('--end', required=True)
        command.add_argument('--place', required=True)
        command.add_argument('--photo', type=Path, required=True)
        command.add_argument('--request-id', default=None, help='重试时沿用同一编号，防止重复提交')
        command.add_argument('--yes', action='store_true', required=True, help='已核对运动信息，确认提交到学校')
    args = parser.parse_args(arguments)
    if args.user not in ygdk.accounts():
        parser.error('请先用 autobh account add ygdk 绑定账号')
    if args.action == 'status':
        result = ygdk.detail(args.user)
    elif args.action in ('refresh', 'records'):
        result = ygdk.refresh(args.user, getattr(args, 'page', 1))
    else:
        if args.photo.stat().st_size > 8 * 1024 * 1024:
            parser.error('图片需不超过 8 MB')
        request_id = args.request_id or str(uuid.uuid4())
        print(f'提交编号：{request_id}（重试请沿用）')
        payload = {'itemId': args.item, 'place': args.place, 'requestId': request_id, 'confirmed': True,
                   'photo': {'name': args.photo.name, 'data': base64.b64encode(args.photo.read_bytes()).decode()}}
        if args.action == 'batch':
            payload['records'] = json.loads(args.plan.read_text(encoding='utf-8'))
            result = ygdk.submit_batch(args.user, payload)
        else:
            payload.update(startTime=args.start, endTime=args.end)
            result = ygdk.submit(args.user, payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    import sys
    try:
        main()
    except (ValueError, OSError) as exc:
        print(f'错误：{exc}', file=sys.stderr)
        raise SystemExit(1)
