from unittest.mock import Mock

import pytest

from autoboya.cache import CourseCache
from autoboya.models import ActionResult, AutomationDecision, UserRecord
from autoboya.scheduler import select_failure_attempts
from autobh import backends


@pytest.fixture
def runner():
    store = backends.boya_store()
    store.init()
    store.upsert_user(UserRecord('done'))
    store.upsert_user(UserRecord('needed'))
    instance = backends.runner('boya')
    instance._with_reauth = Mock(return_value={})
    instance._refresh_user_cache = Mock()
    return instance


def completed(course_id, name='安全健康', *, signout=True):
    info = {'signIn': {'inSignArea': True}}
    if signout:
        info['signOut'] = {'inSignArea': True}
    return {'id': course_id, 'courseName': '历史课程', 'kindName': name,
            'courseEndDate': '2026-09-10 16:00:00', 'signInfo': info}


def cache_candidate(runner, name='安全健康'):
    runner.cache.save_courses([{'id': 99, 'courseName': '新课程', 'kindName': name}])


def save_official(runner, username, name='安全健康', passed=0, required=None, failed=0):
    from autobh.boya import TARGETS, category_name
    runner.cache.save_statistics(username, {'validCount': (passed or 0) - failed, 'statistical': {'60|博雅课程': {
        name: {'assessmentCount': TARGETS[category_name(name)] if required is None else required,
               'completeAssessmentCount': passed, 'failAssessmentCount': failed}}}})


def test_category_goal_blocks_only_completed_user_before_native_submission(runner):
    cache_candidate(runner)
    save_official(runner, 'done', passed=1)
    save_official(runner, 'needed')
    results = runner.execute_decisions([AutomationDecision('select', 99)])
    assert [(row.username, row.ok) for row in results] == [('done', False), ('needed', True)]
    assert '安全健康已达标' in results[0].message
    assert [call.args[0] for call in runner._with_reauth.call_args_list] == ['needed']
    journal = runner.store.load_json('cache/action_journal.json', {})
    assert not any(':done:select:99' in key for key in journal)
    assert select_failure_attempts(journal, 'done', 99) == 0


def test_completed_category_does_not_block_other_official_category(runner):
    cache_candidate(runner, '德育')
    save_official(runner, 'done', '德育', 1)
    assert runner._select_for_user(UserRecord('done'), 99).ok
    runner._with_reauth.assert_called_once()


def test_labor_alias_uses_school_goal(runner):
    cache_candidate(runner, '劳动教育')
    save_official(runner, 'done', '劳育', 2)
    assert '劳育已达标' in runner.selection_block_reason('done', 99)
    runner._select_for_user(UserRecord('done'), 99)
    runner._with_reauth.assert_not_called()


def test_failure_and_missing_signout_do_not_reopen_officially_met_category(runner):
    cache_candidate(runner)
    save_official(runner, 'done', passed=1, failed=1)
    runner.cache.save_selected('done', [completed(1, signout=False)])
    assert '已达标' in runner.selection_block_reason('done', 99)
    assert not runner._select_for_user(UserRecord('done'), 99).ok
    runner._with_reauth.assert_not_called()


def test_cached_decision_is_checked_again_when_official_progress_becomes_complete(runner):
    cache_candidate(runner)
    decision = AutomationDecision('select', 99)
    save_official(runner, 'done')
    assert runner.selection_block_reason('done', 99) is None
    save_official(runner, 'done', passed=1)
    runner.store.upsert_user(UserRecord('needed', enabled=False))
    assert not runner.execute_decisions([decision])[0].ok
    runner._with_reauth.assert_not_called()


def test_existing_course_signin_and_signout_continue_after_category_goal(runner):
    pending = {'id': 10, 'courseName': '已选课', 'kindName': '安全健康',
               'courseSignConfig': {'signPointList': [{'lat': 1, 'lng': 1}]}, 'signInfo': None}
    save_official(runner, 'done', passed=1)
    runner.cache.save_selected('done', [completed(1), pending])
    runner._sign_for_user = Mock(side_effect=lambda username, course, action: ActionResult(username, action, course.id, True, 'signed'))
    results = runner.execute_decisions([AutomationDecision('sign', 10, 'done'), AutomationDecision('signout', 10, 'done')])
    assert [row.action for row in results] == ['sign', 'signout']
    assert [call.args[2] for call in runner._sign_for_user.call_args_list] == ['sign', 'signout']


def test_missing_or_unknown_official_progress_blocks_selection_even_with_complete_attendance(runner):
    cache_candidate(runner)
    runner.cache.save_selected('done', [completed(1)])
    assert '待核实' in runner.selection_block_reason('done', 99)
    save_official(runner, 'done', passed=None)
    assert '待核实' in runner.selection_block_reason('done', 99)
    runner._select_for_user(UserRecord('done'), 99)
    runner._with_reauth.assert_not_called()


def test_refresh_failure_blocks_selection_and_preserves_official_cache(runner):
    from autobh.boya_operations import mark_refresh_error
    cache_candidate(runner)
    save_official(runner, 'done')
    mark_refresh_error(runner.store, 'done')
    assert '刷新失败' in runner.selection_block_reason('done', 99)
    runner._select_for_user(UserRecord('done'), 99)
    runner._with_reauth.assert_not_called()
    assert runner.cache.load_statistics('done')['validCount'] == 0


@pytest.mark.parametrize(('name', 'required'), [('德育', 3), ('美育', 2), ('劳育', 4), ('安全健康', 2)])
def test_each_category_stops_at_school_requirement_instead_of_hardcoded_goal(runner, name, required):
    cache_candidate(runner, name)
    save_official(runner, 'done', name, required - 1, required)
    assert runner.selection_block_reason('done', 99) is None
    save_official(runner, 'done', name, required, required)
    assert '已达标' in runner.selection_block_reason('done', 99)
    assert not runner._select_for_user(UserRecord('done'), 99).ok
    runner._with_reauth.assert_not_called()


def test_personal_total_replaces_category_stop_without_affecting_other_user(runner):
    from autobh.boya_policy import save_policy
    cache_candidate(runner)
    save_official(runner, 'done', passed=1)
    save_official(runner, 'needed', passed=1)
    save_policy(runner.store, 'done', {'mode': 'total', 'target': 6})
    assert runner.selection_block_reason('done', 99) is None
    assert '已达标' in runner.selection_block_reason('needed', 99)
    assert runner._select_for_user(UserRecord('done'), 99).ok


def test_personal_total_uses_official_net_including_deductions_and_rechecks_changes(runner):
    from autobh.boya_policy import save_policy
    cache_candidate(runner)
    save_policy(runner.store, 'done', {'mode': 'total', 'target': 6})
    save_official(runner, 'done', passed=6, failed=1)
    assert runner.selection_block_reason('done', 99) is None
    save_official(runner, 'done', passed=6)
    assert '个人目标已达标' in runner.selection_block_reason('done', 99)
    assert not runner._select_for_user(UserRecord('done'), 99).ok
    runner._with_reauth.assert_not_called()
    save_official(runner, 'done', passed=0, failed=2)
    assert runner.selection_block_reason('done', 99) is None


def test_restore_default_reinstates_official_category_guard(runner):
    from autobh.boya_policy import save_policy
    cache_candidate(runner)
    save_official(runner, 'done', passed=1)
    save_policy(runner.store, 'done', {'mode': 'total', 'target': 6})
    assert runner.selection_block_reason('done', 99) is None
    save_policy(runner.store, 'done', {'mode': 'categories'})
    assert '安全健康已达标' in runner.selection_block_reason('done', 99)


def test_total_mode_blocks_unknown_totals_refresh_failures_and_manual_exclusions(runner):
    from autobh.boya_policy import save_policy
    from autobh.boya_operations import mark_refresh_error
    from autobh.storage import atomic_json
    cache_candidate(runner)
    save_policy(runner.store, 'done', {'mode': 'total', 'target': 6})
    runner.cache.save_statistics('done', {})
    assert '待核实' in runner.selection_block_reason('done', 99)
    save_official(runner, 'done', passed=1)
    mark_refresh_error(runner.store, 'done')
    assert '刷新失败' in runner.selection_block_reason('done', 99)
    atomic_json(runner.store.path('run/autobh/exclusions.json'), {'done': {'99': {}}})
    assert '禁止自动选回' in runner.selection_block_reason('done', 99)


def test_existing_attendance_continues_after_personal_total_is_met(runner):
    from autobh.boya_policy import save_policy
    save_policy(runner.store, 'done', {'mode': 'total', 'target': 1})
    save_official(runner, 'done', passed=1)
    runner.cache.save_selected('done', [completed(10)])
    runner._sign_for_user = Mock(side_effect=lambda username, course, action: ActionResult(username, action, course.id, True, 'signed'))
    results = runner.execute_decisions([AutomationDecision('sign', 10, 'done'), AutomationDecision('signout', 10, 'done')])
    assert [row.action for row in results] == ['sign', 'signout']


def test_malformed_personal_configuration_blocks_instead_of_using_default(runner):
    from autobh.boya_policy import path
    from autobh.storage import atomic_json
    cache_candidate(runner)
    save_official(runner, 'done')
    atomic_json(path(runner.store), {'done': {'mode': 'total', 'target': 0}})
    assert '配置异常' in runner.selection_block_reason('done', 99)
    runner._select_for_user(UserRecord('done'), 99)
    runner._with_reauth.assert_not_called()
