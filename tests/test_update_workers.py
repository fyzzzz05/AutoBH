from pathlib import Path
from unittest.mock import Mock

import pytest
from autobh import update_workers as updates
from autobh.storage import atomic_json, read_json


@pytest.fixture
def workers(monkeypatch, tmp_path):
    state = {
        'class': {'status':'running','pid':101,'stop_requested':False},
        'td': {'status':'running','pid':102,'stop_requested':False},
        'boya': {'status':'stopped','pid':None,'stop_requested':False},
        'ygdk': {'status':'stopped','pid':None,'stop_requested':False},
    }
    monkeypatch.setattr(updates.backends, 'available', lambda feature: True)
    monkeypatch.setattr(updates.service, 'status', lambda feature: state[feature].copy())
    monkeypatch.setattr(updates.service, 'busy', lambda feature: state[feature]['status']=='running')
    monkeypatch.setattr(updates, 'process_binary', lambda pid: Path('/app/engine') if pid==101 else Path('/other/python') if pid else None)
    for feature in ('class','td'):
        atomic_json(updates.service.run_dir(feature)/'worker.json', {'pid':state[feature]['pid'],'token':feature+'-token'})
    return state


def test_prepare_stops_only_this_app_and_preserves_native_progress(workers, monkeypatch):
    native = updates.backends.native_home('td')/'state.json'
    progress = {'daily_runs': {'today': {'users': {'1': {'completed_rounds':2,'next_action':'exit'}}}}}
    atomic_json(native, progress)
    def stop(feature, identity):
        assert feature == 'class'
        workers[feature].update(status='stopped',pid=None)
    monkeypatch.setattr(updates, 'request_stop', stop)
    updates.prepare(executable='/app/engine')
    assert read_json(updates.marker())['features']==['class']
    assert read_json(updates.marker())['state']=='ready'
    assert workers['td']['status']=='running'
    assert read_json(native)==progress


def test_prepare_refuses_unmanaged_native_worker_from_same_bundle(workers, monkeypatch):
    workers['class']['status']='native-running'
    stop=Mock()
    monkeypatch.setattr(updates,'request_stop',stop)
    with pytest.raises(RuntimeError,match='原工具后台'):
        updates.prepare(executable='/app/engine')
    stop.assert_not_called()
    assert not updates.marker().exists()


def test_failed_handoff_retains_pending_restore_until_worker_exits(workers, monkeypatch):
    monkeypatch.setattr(updates,'request_stop',lambda feature, identity: workers[feature].update(stop_requested=True))
    with pytest.raises(RuntimeError,match='本次更新已取消'):
        updates.prepare(timeout=0,executable='/app/engine')
    assert read_json(updates.marker())['state']=='rollback'
    start=Mock()
    monkeypatch.setattr(updates.service,'start',start)
    updates.restore_pending(force=True)
    start.assert_not_called()
    assert read_json(updates.marker())['features']==['class']
    workers['class'].update(status='stopped',pid=None,stop_requested=False)
    updates.restore_pending()
    start.assert_called_once_with('class',updates.root())
    assert not updates.marker().exists()


def test_old_gui_does_not_resume_a_ready_update(workers,monkeypatch):
    atomic_json(updates.marker(),{'version':updates.__version__,'state':'ready','features':['class']})
    start=Mock()
    monkeypatch.setattr(updates.service,'start',start)
    updates.restore_pending()
    start.assert_not_called()
    assert updates.marker().exists()


def test_new_version_resumes_only_previously_owned_workers(workers,monkeypatch):
    atomic_json(updates.marker(),{'version':'0.0.0','state':'ready','features':['class']})
    workers['class'].update(status='stopped',pid=None)
    start=Mock(return_value={'status':'running'})
    monkeypatch.setattr(updates.service,'start',start)
    updates.restore_pending()
    start.assert_called_once_with('class',updates.root())
    assert not updates.marker().exists()


def test_restore_is_idempotent_and_retries_only_failed_starts(workers,monkeypatch):
    atomic_json(updates.marker(),{'version':'0.0.0','state':'ready','features':['class','boya']})
    workers['class'].update(status='stopped',pid=None)
    start=Mock(side_effect=[{'status':'running'},RuntimeError('start failed')])
    monkeypatch.setattr(updates.service,'start',start)
    updates.restore_pending()
    assert read_json(updates.marker())['features']==['boya']
    monkeypatch.setattr(updates.service,'start',Mock(return_value={'status':'skipped'}))
    updates.restore_pending()
    assert not updates.marker().exists()


def test_stop_request_does_not_target_replaced_worker(workers):
    with pytest.raises(RuntimeError,match='实例发生变化'):
        updates.request_stop('class',{'pid':999,'token':'old-token'})
    assert not (updates.service.run_dir('class')/'stop.request').exists()
