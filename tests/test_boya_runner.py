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


def test_category_goal_blocks_only_completed_user_before_native_submission(runner):
    cache_candidate(runner)
    runner.cache.save_selected('done', [completed(1)])
    runner.cache.save_selected('needed', [])
    results = runner.execute_decisions([AutomationDecision('select', 99)])
    assert [(row.username, row.ok) for row in results] == [('done', False), ('needed', True)]
    assert '安全健康已达标' in results[0].message
    assert [call.args[0] for call in runner._with_reauth.call_args_list] == ['needed']
    journal = runner.store.load_json('cache/action_journal.json', {})
    assert not any(':done:select:99' in key for key in journal)
    assert select_failure_attempts(journal, 'done', 99) == 0


def test_completed_category_does_not_block_other_category(runner):
    cache_candidate(runner, '德育')
    runner.cache.save_selected('done', [completed(1)])
    assert runner._select_for_user(UserRecord('done'), 99).ok
    runner._with_reauth.assert_called_once()


def test_labor_alias_uses_two_course_goal(runner):
    cache_candidate(runner, '劳动教育')
    runner.cache.save_selected('done', [completed(1, '劳育'), completed(2, '劳动教育')])
    assert '劳育已达标' in runner.selection_block_reason('done', 99)
    runner._select_for_user(UserRecord('done'), 99)
    runner._with_reauth.assert_not_called()


def test_deduction_reopens_category_for_future_selection(runner):
    cache_candidate(runner)
    runner.cache.save_selected('done', [completed(1), completed(2, signout=False)])
    assert runner.selection_block_reason('done', 99) is None
    assert runner._select_for_user(UserRecord('done'), 99).ok


def test_cached_decision_is_checked_again_when_progress_becomes_complete(runner):
    cache_candidate(runner)
    decision = AutomationDecision('select', 99)
    runner.cache.save_selected('done', [])
    assert runner.selection_block_reason('done', 99) is None
    runner.cache.save_selected('done', [completed(1)])
    runner.store.upsert_user(UserRecord('needed', enabled=False))
    result = runner.execute_decisions([decision])
    assert not result[0].ok
    runner._with_reauth.assert_not_called()


def test_existing_course_signin_and_signout_continue_after_category_goal(runner):
    pending = {'id': 10, 'courseName': '已选课', 'kindName': '安全健康',
               'courseSignConfig': {'signPointList': [{'lat': 1, 'lng': 1}]}, 'signInfo': None}
    runner.cache.save_selected('done', [completed(1), pending])
    runner._sign_for_user = Mock(side_effect=lambda username, course, action: ActionResult(username, action, course.id, True, 'signed'))
    results = runner.execute_decisions([AutomationDecision('sign', 10, 'done'), AutomationDecision('signout', 10, 'done')])
    assert [row.action for row in results] == ['sign', 'signout']
    assert [call.args[2] for call in runner._sign_for_user.call_args_list] == ['sign', 'signout']


def test_missing_or_unknown_progress_does_not_trigger_unchecked_selection(runner):
    cache_candidate(runner)
    assert '待核实' in runner.selection_block_reason('done', 99)
    runner.cache.save_selected('done', [{'id': 1, 'kindName': '安全健康', 'courseEndDate': '2026-09-10 16:00:00'}])
    assert '待核实' in runner.selection_block_reason('done', 99)
    runner._select_for_user(UserRecord('done'), 99)
    runner._with_reauth.assert_not_called()


@pytest.mark.parametrize(('name', 'required'), [('德育', 2), ('美育', 1), ('劳育', 2), ('安全健康', 1)])
def test_each_category_stops_at_its_own_required_net_count(runner, name, required):
    cache_candidate(runner, name)
    rows = [completed(index + 1, name) for index in range(required - 1)]
    runner.cache.save_selected('done', rows)
    assert runner.selection_block_reason('done', 99) is None
    runner.cache.save_selected('done', rows + [completed(required, name)])
    assert '已达标' in runner.selection_block_reason('done', 99)
    assert not runner._select_for_user(UserRecord('done'), 99).ok
    runner._with_reauth.assert_not_called()
