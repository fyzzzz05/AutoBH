from pathlib import Path

import pytest
from autoboya.models import UserRecord
from autobh import backends
from autobh.boya_policy import DEFAULT, apply_policy, load_policy, path, save_policy, validate_policy
from autobh.progress import boya_progress, progress_text
from autobh.storage import atomic_json


@pytest.mark.parametrize('value', [None, True, '6', 0, -1, 1.5, 10001, [], {}])
def test_target_requires_a_positive_integer(value):
    with pytest.raises(ValueError):
        validate_policy({'mode': 'total', 'target': value})


def test_settings_survive_restart_are_per_person_and_clear_on_unbind():
    store = backends.boya_store()
    store.init()
    for name in ('1', '2'):
        store.upsert_user(UserRecord(name))
    save_policy(store, '1', {'mode': 'total', 'target': 6})
    save_policy(store, '2', {'mode': 'total', 'target': 8})
    assert load_policy(backends.boya_store(), '1') == {'mode': 'total', 'target': 6}
    save_policy(store, '1', DEFAULT)
    assert load_policy(store, '1') == DEFAULT
    assert load_policy(store, '2')['target'] == 8
    assert store.get_user('1').enabled
    assert path(store).stat().st_mode & 0o077 == 0
    backends.remove_account('boya', '2')
    assert load_policy(store, '2') == DEFAULT


def test_unbound_user_cannot_have_settings_saved():
    with pytest.raises(ValueError, match='绑定'):
        save_policy(backends.boya_store(), '1', {'mode': 'total', 'target': 6})


@pytest.mark.parametrize('raw', ['invalid json', '[]', '{"1":{"mode":"unknown"}}'])
def test_corrupt_policy_is_explicitly_unusable(raw):
    store = backends.boya_store()
    path(store).parent.mkdir(parents=True)
    path(store).write_text(raw)
    assert load_policy(store, '1')['mode'] == 'invalid'


def test_personal_summary_does_not_change_official_category_assessment():
    progress = boya_progress({'validCount': 4})
    before = [dict(row) for row in progress['categories']]
    apply_policy(progress, {'mode': 'total', 'target': 6})
    assert progress_text('boya', progress) == '净有效 4 / 6 次 · 还需 2 次'
    assert progress['categories'] == before
    assert not progress['stopCondition']['met']
    progress['totalCount'] = 6
    apply_policy(progress, {'mode': 'total', 'target': 6})
    assert '个人目标已达标' in progress_text('boya', progress)
    assert progress['stopCondition']['met']
