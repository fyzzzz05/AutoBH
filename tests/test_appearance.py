import json

import pytest

from autobh.appearance import read_appearance, save_appearance
from autobh.gui import Application


def test_preference_persists_across_application_restarts_and_preserves_other_settings(tmp_path):
    settings = tmp_path / 'preferences.json'
    settings.write_text('{"other": 42}')
    for mode in ('dark', 'light', 'system'):
        Application(tmp_path).mutate('/api/appearance', {'appearance': mode})
        assert Application(tmp_path).appearance() == mode
        assert json.loads(settings.read_text())['other'] == 42
    assert settings.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('value', [None, '', 'auto', '<script>', [], {}, True, 1])
def test_invalid_preferences_do_not_replace_saved_choice(tmp_path, value):
    save_appearance(tmp_path, 'dark')
    with pytest.raises(ValueError):
        Application(tmp_path).mutate('/api/appearance', {'appearance': value})
    assert read_appearance(tmp_path) == 'dark'


@pytest.mark.parametrize('content', ['{', 'null', '[]', '{"appearance":"invalid"}'])
def test_bad_settings_fall_back_to_system_and_can_be_repaired(tmp_path, content):
    (tmp_path / 'preferences.json').write_text(content)
    assert read_appearance(tmp_path) == 'system'
    save_appearance(tmp_path, 'light')
    assert read_appearance(tmp_path) == 'light'


def test_demo_preferences_are_isolated_from_real_profile(tmp_path):
    save_appearance(tmp_path, 'light')
    app = Application(tmp_path, demo=True)
    assert app.appearance() == 'system'
    app.mutate('/api/appearance', {'appearance': 'dark'})
    assert app.appearance() == 'dark'
    assert read_appearance(tmp_path) == 'light'
