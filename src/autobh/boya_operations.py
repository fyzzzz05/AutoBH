"""Read-only refresh and explicit withdrawal, sharing native auth and storage."""
from datetime import datetime
from zoneinfo import ZoneInfo

from . import backends
from .boya import course_view, parse_time
from .storage import atomic_json, file_lock, read_json


def operation_lock(store):
    return file_lock(store.path('run/autobh/course-operations.lock'))


def exclusions(store):
    return read_json(store.path('run/autobh/exclusions.json'), {})


def observation(store, username):
    return read_json(store.path('run/autobh/observations.json'), {}).get(username, {})


def mark_observation(store, username, **values):
    path = store.path('run/autobh/observations.json')
    data = read_json(path, {})
    data.setdefault(username, {}).update(values)
    atomic_json(path, data)


def mark_refresh_error(store, username):
    mark_observation(store, username, error='刷新失败，请检查网络或账号登录状态',
                     attemptedAt=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat())


def semester(client):
    from autoboya.cli import current_semester_window
    start, end = current_semester_window(client.get_all_config())
    now = datetime.now(ZoneInfo('Asia/Shanghai'))
    if not (parse_time(start) and parse_time(end) and parse_time(start) <= now <= parse_time(end)):
        raise ValueError('学校返回的学期范围无效，请稍后刷新')
    return start, end


def refresh_with_client(store, username, client, window=None):
    from autoboya.cache import CourseCache
    from .progress import read_boya_cache
    # Preserve legacy users' timestamps before shared cache files are rewritten.
    stats, selections, old_time = read_boya_cache(store)
    path = store.path('run/autobh/observations.json')
    observations = read_json(path, {})
    for account in set(stats) | set(selections):
        if account not in observations and old_time:
            observations[account] = {'updatedAt': old_time.isoformat()}
    atomic_json(path, observations)
    start, end = window or semester(client)
    # Fetch both before writing; a failed request must not make stale data look fresh.
    selected = client.query_chosen_courses(start, end)
    statistics = client.query_statistics()
    cache = CourseCache(store)
    cache.save_selected(username, selected)
    cache.save_statistics(username, statistics)
    mark_observation(store, username, updatedAt=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), error=None)
    return selected


def refresh_user(username):
    from autoboya.cli import call_with_reauth
    store = backends.boya_store()
    with operation_lock(store):
        try:
            return call_with_reauth(store, username, lambda client: refresh_with_client(store, username, client))
        except Exception as exc:
            # Never expose native exception text: it may contain authenticated URLs.
            mark_refresh_error(store, username)
            raise ValueError('刷新失败，请检查网络或账号登录状态；原缓存已保留') from exc


def drop_user_course(username, course_id):
    from autoboya.cli import call_with_reauth
    store = backends.boya_store()
    with operation_lock(store):
        def drop(client):
            selected = refresh_with_client(store, username, client)
            course = next((course_view(raw) for raw in selected if course_view(raw)['id'] == course_id), None)
            if course is None:
                raise ValueError('该课程已不在已选列表，请刷新')
            if not course['canDrop']:
                raise ValueError(course['dropReason'])
            # Persist exclusion BEFORE submission: uncertain responses must not
            # let automation immediately select the course again.
            path = store.path('run/autobh/exclusions.json')
            data = exclusions(store)
            data.setdefault(username, {})[str(course_id)] = {
                'name': course['name'], 'createdAt': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()}
            atomic_json(path, data)
            try:
                client.drop_course(course_id)
            except Exception as exc:
                raise ValueError('退选未确认，已暂停自动选回此课；请刷新核实后重试') from exc
            try:
                remaining = refresh_with_client(store, username, client)
            except Exception as exc:
                raise ValueError('退选已提交，但刷新失败；已排除此课，请稍后刷新核实') from exc
            if any(course_view(raw)['id'] == course_id for raw in remaining):
                raise ValueError('学校仍显示已选，已排除自动选回；请稍后刷新核实')
        try:
            return call_with_reauth(store, username, drop)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('退选未完成，请检查网络或账号登录状态后刷新核实') from exc
