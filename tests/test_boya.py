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


def official_statistics(*, moral=2, art=1, labor=1, health=1, valid=4):
    return {'validCount': valid, 'statistical': {'60|博雅课程': {
        f'{i}|{name}': {'assessmentCount': required, 'completeAssessmentCount': passed,
                       'failAssessmentCount': int(name == '劳动教育'), 'undoneAssessmentCount': 0}
        for i, (name, required, passed) in enumerate([
            ('德育', 2, moral), ('美育', 1, art), ('劳动教育', 2, labor), ('安全健康', 1, health)], 55)}}}


def test_official_statistics_match_school_even_when_attendance_differs():
    stats = official_statistics()
    courses = [enrollment(1, signed_out=False), enrollment(2),
               enrollment(3, '劳动教育'), enrollment(4, '劳动教育', signed=False)]
    result = boya_progress(stats, courses, now=NOW)
    assert result['totalCount'] == 4
    assert [(r['completed'], r['required'], r['met']) for r in result['categories']] == [
        (2, 2, True), (1, 1, True), (1, 2, False), (1, 1, True)]
    assert result['metCategories'] == 3
    assert category(result, '劳育')['failed'] == 1
    assert category(result, '劳育')['remaining'] == 1
    assert not result['met']


def test_official_requirements_and_signed_net_total_are_not_recomputed():
    stats = official_statistics(labor=2, valid=-2)
    stats['statistical']['60|博雅课程']['55|德育']['assessmentCount'] = 3
    result = boya_progress(stats, [], now=NOW)
    assert result['totalCount'] == -2
    assert category(result, '德育')['required'] == 3
    assert category(result, '德育')['remaining'] == 1
    assert not category(result, '德育')['met']


def test_all_four_official_targets_required_and_extra_cannot_offset_other_categories():
    result = boya_progress(official_statistics(art=8, labor=0))
    assert result['metCategories'] == 3
    assert not result['met']
    assert boya_progress(official_statistics(labor=2))['met']


@pytest.mark.parametrize('value', [None, '', 'bad', True, 1.5, {}, [], -1])
def test_invalid_official_category_counts_are_unknown_not_local_fallback(value):
    stats = official_statistics()
    stats['statistical']['60|博雅课程']['55|德育']['completeAssessmentCount'] = value
    result = boya_progress(stats, [enrollment(1), enrollment(2)], now=NOW)
    assert not category(result, '德育')['known']
    assert not category(result, '德育')['met']
    assert category(result, '德育')['remaining'] is None
    assert result['unknown'] == 1


@pytest.mark.parametrize('selected', [None, [], [enrollment(1)]])
def test_missing_official_statistics_never_become_zero_or_local_progress(selected):
    result = boya_progress({}, selected, now=NOW)
    assert result['totalCount'] is None
    assert result['metCategories'] == 0
    assert result['unknown'] == 4


def test_zero_and_string_counts_are_valid_official_data():
    stats = official_statistics(moral=0, art=0, labor=0, health=0, valid='0')
    stats['statistical']['60|博雅课程']['55|德育']['completeAssessmentCount'] = '0'
    result = boya_progress(stats)
    assert result['totalCount'] == 0
    assert result['unknown'] == 0
    assert category(result, '德育')['remaining'] == 2


@pytest.mark.parametrize('value', [True, 'bad', '', 2.5])
def test_malformed_official_total_is_not_replaced_by_sum(value):
    assert boya_progress(official_statistics(valid=value))['totalCount'] is None


def test_school_pass_is_independent_of_signout_and_cannot_invent_attendance():
    course = enrollment(1, signed_out=False)
    course.update({'pass': 1, 'checkin': 1})
    result = course_view(course, now=NOW)
    assert result['settlement'] == {'state': 'completed', 'label': '考核通过'}
    assert result['signOut']['state'] == 'missing'
    course['pass'] = 0
    assert course_view(course, now=NOW)['settlement']['state'] == 'failed'
    del course['pass']
    assert course_view(course, now=NOW)['settlement']['state'] == 'unknown'
    course['courseEndDate'] = '2026-10-16 16:00:00'
    assert course_view(course, now=NOW)['settlement']['state'] == 'pending'


def test_statistical_assessment_survives_chosen_course_without_pass_and_is_deduped():
    course = enrollment(1, signed_out=False)
    course['pass'] = 1
    stats = official_statistics()
    stats['statistical']['60|博雅课程']['55|德育']['courseUserList'] = [course]
    result = boya_progress(stats, [enrollment(1, signed_out=False)], now=NOW)
    assert len(result['courses']) == 1
    assert result['courses'][0]['settlement']['state'] == 'completed'
    assert result['courses'][0]['signOut']['state'] == 'missing'


def test_course_order_is_newest_first_with_invalid_dates_last():
    courses = [dict(enrollment(i), courseStartDate=t) for i, t in enumerate([
        '2026-09-10 10:00:00', None, '2026-10-10 10:00:00'], 1)]
    assert [r['id'] for r in boya_progress(official_statistics(), courses)['courses']] == [3, 1, 2]


def test_other_curriculum_statistics_cannot_override_boya_category():
    stats = official_statistics()
    stats['statistical']['99|其他课程'] = {'德育': {'assessmentCount': 1, 'completeAssessmentCount': 0}}
    result = boya_progress(stats)
    assert category(result, '德育')['met']
    assert category(result, '德育')['completed'] == 2


def test_missing_school_requirement_blocks_target_without_hardcoded_fallback():
    stats = official_statistics()
    del stats['statistical']['60|博雅课程']['55|德育']['assessmentCount']
    result = boya_progress(stats)
    assert category(result, '德育')['required'] is None
    assert not category(result, '德育')['known']
    assert not category(result, '德育')['met']
