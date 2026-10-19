import json
from datetime import datetime

import pytest

from autobh.boya import course_view
from autobh.progress import boya_progress


@pytest.mark.parametrize('encode', [False, True])
def test_boya_reads_each_school_attendance_record_without_leaking_location(encode):
    info = {'signIn': {'lat': 39.0, 'lng': 116.0, 'inSignArea': True}}
    row = course_view({'id': 1, 'courseName': '课程', 'signInfo': json.dumps(info) if encode else info})
    assert row['signIn'] == {'state': 'done', 'label': '已签到'}
    assert row['signOut'] == {'state': 'missing', 'label': '暂无签退记录'}
    assert 'lat' not in json.dumps(row)
    assert 'lng' not in json.dumps(row)


def test_boya_both_actions_must_have_independent_records():
    row = course_view({'signInfo': {'signIn': {'inSignArea': True}, 'signOut': {'inSignArea': True}}})
    assert row['signIn']['state'] == row['signOut']['state'] == 'done'
    row = course_view({'signInfo': {'signOut': {'inSignArea': True}}})
    assert row['signIn']['state'] == 'missing'
    assert row['signOut']['state'] == 'done'


@pytest.mark.parametrize('info', [None, '', '{}', {}, {'signIn': None, 'signOut': {}}])
def test_boya_explicit_empty_school_records_are_marked_missing(info):
    row = course_view({'signInfo': info, 'pass': 1, 'checkin': 1})
    assert row['signIn']['state'] == row['signOut']['state'] == 'missing'


@pytest.mark.parametrize('data', [{}, {'signInfo': 'bad json'}, {'signInfo': []}, {'signInfo': 7}])
def test_boya_unknown_schema_is_not_invented_as_attendance(data):
    row = course_view({**data, 'pass': 1, 'checkin': 1})
    assert row['signIn']['state'] == row['signOut']['state'] == 'unknown'


def test_boya_reuses_native_nested_course_parser_and_flags_invalid_location():
    row = course_view({'id': 55, 'courseInfo': {'id': 1, 'courseName': '课程', 'coursePosition': '教室'},
                       'signInfo': {'signIn': {'inSignArea': False}}})
    assert row['id'] == 1
    assert row['name'] == '课程'
    assert row['location'] == '教室'
    assert row['signIn'] == {'state': 'warning', 'label': '签到位置异常'}


NOW = datetime.fromisoformat('2026-10-15T12:00:00+08:00')


def enrollment(course_id, category='德育', *, signed=True, signed_out=True, end='2026-10-14 16:00:00'):
    info = {}
    if signed:
        info['signIn'] = {'inSignArea': True}
    if signed_out:
        info['signOut'] = {'inSignArea': True}
    return {'id': course_id, 'courseName': f'课程{course_id}', 'kindName': category,
            'courseEndDate': end, 'signInfo': info}


def category(result, name):
    return next(row for row in result['categories'] if row['name'] == name)


def test_boya_deducts_in_own_category_and_keeps_negative_progress():
    progress = boya_progress({}, [enrollment(1), enrollment(2, signed_out=False),
        enrollment(3, '美育', signed=False, signed_out=False), enrollment(4, '美育', signed_out=False)], now=NOW)
    moral, art = category(progress, '德育'), category(progress, '美育')
    assert (moral['completed'], moral['failed'], moral['net'], moral['remaining']) == (1, 1, 0, 2)
    assert (art['net'], art['remaining']) == (-2, 3)
    assert progress['totalCount'] == -2


def test_boya_all_four_fixed_targets_are_required_and_extra_cannot_offset_other_categories():
    courses = [enrollment(i, '美育') for i in range(1, 8)]
    progress = boya_progress({}, courses, now=NOW)
    assert progress['totalCount'] == 7
    assert progress['metCategories'] == 1
    assert not progress['met']
    courses = [enrollment(i, c) for i, c in enumerate(['德育', '德育', '美育', '劳动教育', '劳育', '安全健康'], 1)]
    progress = boya_progress({}, courses, now=NOW)
    assert [row['required'] for row in progress['categories']] == [2, 1, 2, 1]
    assert progress['totalCount'] == 6
    assert progress['metCategories'] == 4
    assert progress['met']


def test_boya_dedupes_native_statistical_records_and_does_not_subtract_valid_count_twice():
    course = enrollment(1)
    stats = {'validCount': -2, 'statistical': {'60|博雅课程': {'55|德育': {
        'assessmentCount': 50, 'courseUserList': [course]}}}}
    progress = boya_progress(stats, [course, enrollment(2, signed_out=False)], now=NOW)
    assert progress['completed'] == progress['failed'] == 1
    assert progress['totalCount'] == 0
    assert progress['schoolValidCount'] == -2
    assert category(progress, '德育')['required'] == 2
    assert len(progress['courses']) == 2


def test_boya_waits_until_course_and_signout_window_end_before_deduction():
    course = enrollment(1, signed_out=False, end='2026-10-15 11:50:00')
    course['courseSignConfig'] = {'signOutEndDate': '2026-10-15 12:15:00'}
    progress = boya_progress({}, [course], now=NOW)
    assert progress['pending'] == 1
    assert progress['failed'] == 0
    progress = boya_progress({}, [course], now=datetime.fromisoformat('2026-10-15T12:16:00+08:00'))
    assert progress['failed'] == 1
    assert progress['totalCount'] == -1


def test_boya_stale_cache_or_unknown_records_do_not_create_false_penalties():
    course = enrollment(1, signed_out=False)
    progress = boya_progress({}, [course], now=NOW, observed_at=datetime.fromisoformat('2026-10-14T15:00:00+08:00'))
    assert progress['failed'] == 0
    assert progress['unknown'] == 1
    course['signInfo'] = 'invalid json'
    progress = boya_progress({}, [course], now=NOW)
    assert progress['failed'] == 0
    assert progress['unknown'] == 1
    assert not progress['met']


def test_boya_course_pass_cannot_replace_missing_signout_under_user_rules():
    course = enrollment(1, signed_out=False)
    course.update({'pass': 1, 'checkin': 1})
    progress = boya_progress({}, [course], now=NOW)
    assert progress['completed'] == 0
    assert progress['failed'] == 1
    assert progress['totalCount'] == -1


def test_boya_empty_cache_and_missing_cache_are_distinct():
    assert boya_progress({}, None, now=NOW)['totalCount'] is None
    assert boya_progress({}, [], now=NOW)['totalCount'] == 0
