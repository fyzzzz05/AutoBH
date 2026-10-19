"""Sunshine sports adapter, ported from BUAASubnet/UBAA (MIT).

Protocol reference: UBAA e8a397f, shared/.../api/local/LocalYgdkApi.kt.
See third_party/UBAA-LICENSE.txt. Background work is read-only synchronization.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlencode
from zoneinfo import ZoneInfo

import httpx

from .storage import atomic_json, file_lock, read_json

TZ = ZoneInfo("Asia/Shanghai")
BASE = "https://ygdk.buaa.edu.cn/api"
OAUTH = "https://app.buaa.edu.cn/uc/api/oauth/index?redirect=https%3A%2F%2Fygdk.buaa.edu.cn%2F%23%2Fhome&appid=200230221144501510&state=STATE&qrcode=1"
# Mobile campus has its own CAS service; a UC session alone is insufficient.
APP_CAS_SERVICE = 'https://app.buaa.edu.cn/a_buaa/api/cas/index?' + urlencode({'redirect': OAUTH, 'from': 'wap', 'login_from': ''})
AUTH_ENTRY = 'https://sso.buaa.edu.cn/login?' + urlencode({'service': APP_CAS_SERVICE, 'noAutoRedirect': '1'})
KEYRING = "AutoBH.yangguang"


class SunshineError(ValueError):
    pass


class RejectedError(SunshineError):
    """The upstream explicitly rejected the operation before accepting it."""


class AuthenticationError(RejectedError):
    def __init__(self, message, stage='sso'):
        super().__init__(message)
        self.stage = stage


def home():
    from .backends import native_home
    return native_home("ygdk")


def account_key(username):
    return hashlib.sha256(username.encode()).hexdigest()


def user_path(username, name):
    return home() / "users" / account_key(username) / name


def accounts():
    return read_json(home() / "accounts.json", {})


def bind(username, password, unsafe=False):
    """An empty password explicitly reuses an existing school's credential store."""
    from . import backends
    current = accounts()
    row = {"enabled": current.get(username, {}).get("enabled", True)}
    if not password:
        source = next((feature for feature in ("boya", "class")
                       if any(a['username'] == username for a in backends.accounts(feature))), None)
        if not source:
            raise SunshineError("请填写学校密码，或先绑定上课/博雅账号")
        row['source'] = source
    else:
        import keyring
        try:
            keyring.set_password(KEYRING, username, password)
            row['source'] = 'keyring'
        except Exception as exc:
            if not unsafe:
                raise SunshineError("钥匙串不可用；可勾选允许本地密码文件后重试") from exc
            atomic_json(user_path(username, 'password.json'), {'password': password})
            row['source'] = 'file'
    if row['source'] != 'file':
        user_path(username, 'password.json').unlink(missing_ok=True)
    current[username] = row
    atomic_json(home() / 'accounts.json', current)


def password_for(username):
    row = accounts().get(username)
    if not row:
        raise SunshineError("请先绑定阳光打卡账号")
    source = row.get('source')
    if source == 'boya':
        from .backends import boya_store
        from autoboya.session import password_for as native_password
        password = native_password(boya_store(), username)
    elif source == 'class':
        from .backends import class_manager
        password = next((a.get('password') for a in class_manager().load()['accounts']
                         if str(a.get('username')) == username), None)
    elif source == 'file':
        password = read_json(user_path(username, 'password.json'), {}).get('password')
    else:
        import keyring
        password = keyring.get_password(KEYRING, username)
    if not password:
        raise AuthenticationError("学校密码不可用，请重新绑定阳光账号")
    return password


def set_enabled(username, enabled):
    current = accounts()
    if username not in current:
        raise SunshineError("请先绑定阳光打卡账号")
    current[username]['enabled'] = enabled
    atomic_json(home() / 'accounts.json', current)


def remove(username):
    current = accounts()
    if username not in current:
        return False
    del current[username]
    atomic_json(home() / 'accounts.json', current)
    user_path(username, 'password.json').unlink(missing_ok=True)
    try:
        import keyring
        keyring.delete_password(KEYRING, username)
    except Exception:
        pass
    return True


def number(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def first(data, *keys):
    return next((number(data.get(key)) for key in keys if number(data.get(key)) is not None), None)


def summary(count, classify, term):
    return {'termCount': first(count, 'term_good_count_show', 'term_good_count', 'term_count_show', 'term_count'),
            'termTarget': first(count, 'term_num') if count.get('term_num') is not None else number(classify.get('term_num')),
            'weekCount': number(count.get('week_count')), 'weekTarget': 4, 'schoolWeekTarget': first(count, 'week_num') if count.get('week_num') is not None else number(classify.get('week_num')),
            'monthCount': number(count.get('month_count')), 'monthTarget': first(count, 'month_num') if count.get('month_num') is not None else number(classify.get('month_num')),
            'dayCount': number(count.get('day_count')), 'termName': term.get('name')}


def local_time(value):
    seconds = number(value)
    try:
        return datetime.fromtimestamp(seconds, TZ).isoformat() if seconds is not None else None
    except (OverflowError, OSError, ValueError):
        return None


def records_payload(result, items, page, size=20):
    names = {number(item.get('item_id')): item.get('name') for item in items}
    records = [{'id': number(row.get('record_id')), 'itemName': row.get('item_name') or names.get(number(row.get('item_id'))) or '运动',
                'startTime': local_time(row.get('start_time')), 'endTime': local_time(row.get('end_time')),
                'place': str(row.get('place') or ''), 'state': number(row.get('state')),
                'createdAt': row.get('create_time_fmt')}
               for row in result.get('list', []) if isinstance(row, dict)]
    records.sort(key=lambda row: row.get('startTime') or '', reverse=True)
    total = number(result.get('total')) or 0
    return {'records': records, 'total': total, 'page': page, 'hasMore': page * size < total}


def oauth_code(url):
    """School uses both normal query and Vue hash-route callback parameters."""
    parsed = urlsplit(str(url))
    if parsed.scheme != 'https' or parsed.hostname != 'ygdk.buaa.edu.cn':
        return None
    for query in (parsed.query, parsed.fragment.partition('?')[2]):
        value = parse_qs(query).get('code', [None])[0]
        if value:
            return value
    return None


class Client:
    def __init__(self, client=None):
        self.http = client or httpx.Client(timeout=20, follow_redirects=False)
        self.uid = None
        self.token = None

    def close(self):
        self.http.close()

    def unwrap(self, response):
        if response.status_code >= 400:
            raise SunshineError(f"阳光服务返回 HTTP {response.status_code}，请稍后刷新")
        try:
            payload = response.json()
        except ValueError as exc:
            raise SunshineError("阳光服务返回格式异常，请检查网络或登录状态") from exc
        if not isinstance(payload, dict):
            raise SunshineError("阳光服务返回格式异常")
        if number(payload.get('code')) == -98:
            raise AuthenticationError("阳光登录已过期，请重新刷新或绑定账号")
        if number(payload.get('code')) != 1:
            # Upstream messages may include credentials; keep them out of the UI/log.
            raise RejectedError("学校未接受阳光请求，请检查活动信息或稍后重试")
        result = payload.get('result')
        if not isinstance(result, dict):
            raise SunshineError("阳光服务缺少结果数据")
        return result

    def login(self, username, password):
        # Reuse AutoBoya's CAS form parsing and password-expiry continuation;
        # do not require a Boya session or call its selection/sign-in endpoints.
        from autoboya.auth import AuthClient, SSO_LOGIN, UC_ACTIVATE, build_login_params, find_login_error
        from autoboya.exceptions import CaptchaRequired
        from .backends import boya_store
        auth = AuthClient(boya_store(), http_client=self.http, use_vpn=False)
        try:
            auth.preflight_login()
        except CaptchaRequired as exc:
            raise AuthenticationError("统一认证需要验证码，请打开学校登录/授权页完成验证，再重新连接", stage="captcha") from exc
        response = self.http.post(SSO_LOGIN, data=build_login_params(auth._last_login_html or '', username, password))
        response = auth.follow_redirects_and_password_expiry(response)
        if response.status_code >= 400 or find_login_error(response.text):
            raise AuthenticationError("学校账号登录失败，请检查密码或验证码")
        activated = auth.follow_redirects_and_password_expiry(self.http.get(UC_ACTIVATE))
        if activated.status_code >= 400:
            raise AuthenticationError('学校统一认证激活失败，请稍后重试')
        mobile = auth.follow_redirects_and_password_expiry(self.http.get(AUTH_ENTRY))
        if mobile.status_code >= 400:
            raise AuthenticationError('移动校园登录失败，请打开学校登录/授权页检查账号', stage='mobile_campus')
        current = str(mobile.url) if oauth_code(mobile.url) else OAUTH
        code = None
        mobile_form_submitted = False
        for _ in range(12):
            parsed = urlsplit(current)
            if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.buaa.edu.cn'):
                raise AuthenticationError("学校认证跳转异常")
            code = oauth_code(current)
            if code:
                break
            response = self.http.get(current)
            location = response.headers.get('location')
            if not location:
                # Some school deployments return a separate app.buaa CAS form
                # instead of redirecting the unified SSO session. Handle only
                # the known HTTPS school login endpoint, never arbitrary forms.
                if parsed.hostname == 'app.buaa.edu.cn' and parsed.path == '/uc/wap/login' and not mobile_form_submitted:
                    from bs4 import BeautifulSoup
                    from autoboya.auth import detect_captcha
                    if detect_captcha(response.text):
                        raise AuthenticationError('移动校园需要验证码，请打开学校登录/授权页完成验证', stage='captcha')
                    form = BeautifulSoup(response.text, 'html.parser').find('form', id='loginForm')
                    names = {field.get('name') for field in form.find_all('input')} if form else set()
                    if {'username', 'password', 'execution'} <= names:
                        mobile_form_submitted = True
                        response = self.http.post('https://app.buaa.edu.cn/uc/wap/login', data=build_login_params(str(form), username, password))
                        if response.status_code >= 400 or find_login_error(response.text):
                            raise AuthenticationError('移动校园账号登录失败，请检查密码或验证码', stage='mobile_campus')
                        location = response.headers.get('location')
                        if location:
                            current = urljoin(str(response.url), location)
                            continue
                break
            current = urljoin(current, location)
        if not code:
            raise AuthenticationError("移动校园尚未返回阳光授权码，请打开学校登录/授权页检查，再重新连接", stage="mobile_campus")
        result = self.unwrap(self.http.get(f'{BASE}/Front/Clockin/User/campusAppLogin', params={'code': code}))
        data = result.get('data', result)
        self.uid = number(data.get('uid'))
        self.token = unquote(str(data.get('token') or ''))
        if self.uid is None or not self.token:
            raise AuthenticationError("阳光登录凭据缺失")

    def post(self, path, data=None, query=False):
        fields = data or {}
        return self.unwrap(self.http.post(BASE + path, data={**fields, 'uid': self.uid, 'token': self.token},
                                          params=fields if query else None,
                                          headers={'X-Requested-With': 'XMLHttpRequest'}))

    def catalog(self):
        rows = self.post('/Front/Clockin/Classify/getList').get('list', [])
        if not rows:
            raise SunshineError("未获取到阳光打卡分类")
        classify = next((row for row in rows if '体育' in str(row.get('name'))), None) or next((row for row in rows if number(row.get('classify_id')) == 1), rows[0])
        items = self.post('/Front/Clockin/Item/getList', {'page': 1, 'limit': 1000, 'classify_id': classify['classify_id']}, query=True).get('list', [])
        if not items:
            raise SunshineError("未获取到运动项目")
        return classify, items

    def read(self, page=1):
        classify, items = self.catalog()
        cid = classify['classify_id']
        count = self.post('/Front/Clockin/Clockin/getCount', {'classify_id': cid, 'user_id': self.uid})
        term = self.post('/Front/Clockin/Term/get')
        records = self.post('/Front/Clockin/Clockin/getList', {'page': page, 'limit': 20, 'classify_id': cid, 'user_id': self.uid}, query=True)
        return {'summary': summary(count, classify, term), 'classifyName': classify.get('name'),
                'items': [{'id': number(row.get('item_id')), 'name': row.get('name')} for row in items],
                **records_payload(records, items, page)}

    def upload(self, photo):
        return self.unwrap(self.http.post(BASE + '/Front/Upload/File/post',
                    data={'uid': str(self.uid), 'token': self.token},
                    files={'file': (photo['name'], photo['bytes'], photo['mime'])},
                    headers={'X-Requested-With': 'XMLHttpRequest'})).get('file_name')


@contextmanager
def connected(username):
    client = Client()
    try:
        client.login(username, password_for(username))
        yield client
    except httpx.HTTPError as exc:
        raise SunshineError("无法连接阳光服务，请检查网络；原缓存已保留") from exc
    finally:
        client.close()


def detail(username):
    value = read_json(user_path(username, 'cache.json'), {})
    # Cached daily/weekly counters describe their observation period only.
    observed = value.get('updatedAt')
    if observed:
        try:
            stamp = datetime.fromisoformat(observed).astimezone(TZ)
            now = datetime.now(TZ)
            stats = value.get('summary', {}).copy()
            if stamp.date() != now.date():
                stats['dayCount'] = None
            if stamp.isocalendar()[:2] != now.isocalendar()[:2]:
                stats['weekCount'] = None
            value['summary'] = stats
        except ValueError:
            pass
    observed = read_json(user_path(username, 'observation.json'), {})
    return {'title': '阳光打卡', 'summary': {}, 'records': [], 'items': [], 'page': 1, 'total': 0, 'hasMore': False,
            **value, 'refreshError': observed.get('error'),
            'authorization': {'loginUrl': AUTH_ENTRY, 'required': observed.get('errorKind') == 'authentication' or '未取得阳光登录授权' in str(observed.get('error') or ''),
                              'stage': observed.get('authStage'), 'errorKind': observed.get('errorKind')}}


def refresh(username, page=1):
    if type(page) is not int or not 1 <= page <= 10000:
        raise SunshineError("页码无效")
    with file_lock(user_path(username, 'operation.lock')):
        try:
            with connected(username) as client:
                value = client.read(page)
            value['updatedAt'] = datetime.now(TZ).isoformat()
            if page == 1:
                atomic_json(user_path(username, 'cache.json'), value)
            atomic_json(user_path(username, 'observation.json'), {'error': None})
            return {'title': '阳光打卡', **value, 'authorization': {'loginUrl': AUTH_ENTRY, 'required': False, 'errorKind': None}}
        except Exception as exc:
            message = str(exc) if isinstance(exc, SunshineError) else "刷新失败，请检查网络或账号登录状态"
            atomic_json(user_path(username, 'observation.json'), {'error': message, 'errorKind': 'authentication' if isinstance(exc, AuthenticationError) else 'network' if isinstance(exc.__cause__, httpx.HTTPError) else 'service', 'authStage': getattr(exc, 'stage', None)})
            raise SunshineError(message) from exc


def validate_submission(payload, now=None):
    now = now or datetime.now(TZ)
    item = payload.get('itemId')
    if type(item) is not int or item <= 0:
        raise SunshineError("请选择运动项目")
    try:
        start, end = [datetime.fromisoformat(str(payload.get(key, '')).replace(' ', 'T')) for key in ('startTime', 'endTime')]
        start, end = [(value.replace(tzinfo=TZ) if value.tzinfo is None else value.astimezone(TZ)) for value in (start, end)]
    except ValueError as exc:
        raise SunshineError("请填写完整的运动开始、结束时间") from exc
    if start.date() != end.date() or end <= start:
        raise SunshineError("运动须在同一天，结束时间须晚于开始时间")
    if end > now:
        raise SunshineError("运动尚未结束，请结束后再提交")
    place = payload.get('place', '')
    if not isinstance(place, str) or not place.strip() or len(place) > 120:
        raise SunshineError("请填写运动地点（最多 120 字）")
    photo = payload.get('photo')
    if not isinstance(photo, dict):
        raise SunshineError("请上传本次运动图片")
    name = Path(str(photo.get('name', ''))).name
    try:
        content = base64.b64decode(photo.get('data', ''), validate=True)
    except (ValueError, TypeError) as exc:
        raise SunshineError("图片内容无效") from exc
    mime = ('image/png' if content.startswith(b'\x89PNG\r\n\x1a\n') else
            'image/jpeg' if content.startswith(b'\xff\xd8\xff') else
            'image/webp' if content.startswith(b'RIFF') and content[8:12] == b'WEBP' else None)
    if not mime or not 0 < len(content) <= 8 * 1024 * 1024:
        raise SunshineError("请上传不超过 8 MB 的 JPG、PNG 或 WebP 图片")
    request_id = payload.get('requestId', '')
    if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', request_id):
        raise SunshineError("提交编号无效，请重新打开表单")
    if payload.get('confirmed') is not True:
        raise SunshineError("请先核对运动信息并确认提交")
    return {'itemId': item, 'start': start, 'end': end, 'place': place.strip(),
            'photo': {'name': name or 'sports.png', 'bytes': content, 'mime': mime}, 'requestId': request_id}


def _submit(username, payload):
    data = validate_submission(payload)
    if username not in accounts():
        raise SunshineError("请先绑定阳光打卡账号")
    fingerprint = hashlib.sha256(json.dumps({key: payload.get(key) for key in ('itemId', 'startTime', 'endTime', 'place', 'photo')}, sort_keys=True).encode()).hexdigest()
    with file_lock(user_path(username, 'operation.lock')):
        journal_path = user_path(username, 'submissions.json')
        journal = read_json(journal_path, {})
        previous = journal.get(data['requestId']) or next((row for row in journal.values() if row.get('fingerprint') == fingerprint and row.get('status') in ('pending', 'success')), None)
        if previous:
            if previous.get('fingerprint') != fingerprint:
                raise SunshineError("提交编号已使用，请重新打开表单")
            if previous['status'] == 'success':
                return {'message': '此条记录已提交，请勿重复提交', 'detail': detail(username), 'submitted': False}
            if previous['status'] == 'pending':
                raise SunshineError("上次提交结果尚未确认，请先刷新历史记录核对，勿重复提交")
        with connected(username) as client:
            classify, items = client.catalog()
            item = next((row for row in items if number(row.get('item_id')) == data['itemId']), None)
            if not item:
                raise SunshineError("所选运动项目已失效，请刷新后重新选择")
            image = client.upload(data['photo'])
            if not image:
                raise SunshineError("运动图片上传失败，尚未提交打卡")
            # Persist before sending. A timeout must never cause an automatic retry.
            journal[data['requestId']] = {'fingerprint': fingerprint, 'status': 'pending', 'at': datetime.now(TZ).isoformat()}
            atomic_json(journal_path, journal)
            try:
                result = client.post('/Front/Clockin/Clockin/clockin', {
                    'start_time': int(data['start'].timestamp()), 'end_time': int(data['end'].timestamp()),
                    'place_type': '1', 'place': data['place'], 'isopen': '0',
                    'form_time_fmt': f"{data['start']:%Y-%m-%d %H:%M}-{data['end']:%H:%M}",
                    'images': json.dumps([image]), 'classify_id': classify['classify_id'],
                    'item_id': data['itemId'], 'item_name': item['name']})
            except RejectedError:
                journal[data['requestId']]['status'] = 'rejected'
                atomic_json(journal_path, journal)
                raise
            except Exception as exc:
                raise SunshineError('提交结果未确认，请先刷新历史记录核对；不会自动重复提交') from exc
            journal[data['requestId']].update(status='success', recordId=result.get('record_id'))
            atomic_json(journal_path, journal)
        message = '阳光打卡已提交'
    try:
        refreshed = refresh(username)
    except SunshineError:
        refreshed = detail(username)
        message += '，次数暂未刷新，可稍后刷新历史记录'
    return {'message': message, 'detail': refreshed, 'submitted': True}


def submit(username, payload):
    with file_lock(user_path(username, 'batch.lock')):
        return _submit(username, payload)


@dataclass
class SyncResult:
    username: str
    status: str


class SunshineRunner:
    def __init__(self, username=None):
        self.username = username

    def run_once(self, stop_event=None):
        results = []
        for username, row in accounts().items():
            if stop_event is not None and stop_event.is_set():
                break
            if not row.get('enabled') or self.username not in (None, username):
                continue
            try:
                refresh(username)
                results.append(SyncResult(username, 'synced'))
            except (ValueError, RuntimeError):
                results.append(SyncResult(username, 'error'))
        return results

    def run_forever(self, stop_event):
        while not stop_event.is_set():
            self.run_once(stop_event)
            stop_event.wait(1800)


WEEK_TARGET = 4
MIN_GAP_MINUTES = 10


def batch_plan(payload, now=None):
    """Validate the entire plan before any school request or image upload."""
    now = now or datetime.now(TZ)
    rows = payload.get('records')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 4 or not all(isinstance(row, dict) for row in rows):
        raise SunshineError('每次请提交 1–4 段运动记录')
    base = {key: value for key, value in payload.items() if key != 'records'}
    result = []
    for index, row in enumerate(rows):
        record = {**base, 'startTime': row.get('startTime'), 'endTime': row.get('endTime'),
                  'requestId': f"{payload.get('requestId', '')}-{index + 1}"}
        parsed = validate_submission(record, now=now)
        if parsed['start'].isocalendar()[:2] != now.isocalendar()[:2]:
            raise SunshineError('四连仅用于本周的运动记录，请检查四段日期')
        result.append((record, parsed))
    result.sort(key=lambda row: row[1]['start'])
    for (_, before), (_, after) in zip(result, result[1:]):
        if (after['start'] - before['end']).total_seconds() < MIN_GAP_MINUTES * 60:
            raise SunshineError(f'运动时间过近：两段之间请至少留出 {MIN_GAP_MINUTES} 分钟')
    return [row[0] for row in result]


def submit_batch(username, payload):
    plan = batch_plan(payload)
    if username not in accounts():
        raise SunshineError('请先绑定阳光打卡账号')
    # Serialize whole batches while each constituent submission keeps the same
    # durable idempotency journal as the single-record action.
    with file_lock(user_path(username, 'batch.lock')):
        fresh = refresh(username)
        observed = fresh.get('summary', {}).get('weekCount')
        if type(observed) is not int:
            raise SunshineError('本周次数暂不可读取，请刷新成功后再提交四连')
        remaining = max(0, WEEK_TARGET - observed)
        outcomes = []
        state = 'completed'
        for index, record in enumerate(plan):
            old = read_json(user_path(username, 'submissions.json'), {}).get(record['requestId'])
            if old and old.get('status') == 'success':
                # submit() only returns the cached success here; it also checks
                # that this request ID still refers to identical activity data.
                _submit(username, record)
                outcomes.append({'number': index + 1, 'status': 'success', 'label': '此前已提交'})
                continue
            if remaining <= 0:
                outcomes.append({'number': index + 1, 'status': 'skipped', 'label': '本周已达 4 次，跳过'})
                continue
            try:
                result = _submit(username, record)
                if result.get('submitted', True):
                    remaining -= 1
                outcomes.append({'number': index + 1, 'status': 'success', 'label': '已提交'})
                latest = result.get('detail', {}).get('summary', {}).get('weekCount')
                if type(latest) is int:
                    remaining = min(remaining, max(0, WEEK_TARGET - latest))
            except (ValueError, RuntimeError) as exc:
                state = 'paused'
                outcomes.append({'number': index + 1, 'status': 'error', 'label': str(exc)})
                outcomes.extend({'number': next_index + 1, 'status': 'waiting', 'label': '尚未提交'} for next_index in range(index + 1, len(plan)))
                break
        succeeded = sum(row['status'] == 'success' for row in outcomes)
        return {'message': f'四连已暂停，已确认 {succeeded} 条' if state == 'paused' else '本周四连处理完成',
                'detail': detail(username), 'batch': {'status': state, 'outcomes': outcomes}}
