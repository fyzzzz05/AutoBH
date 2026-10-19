import { useCallback, useEffect, useRef, useState } from 'react';
import { GraduationCap, Barbell, BookOpen, Sun, Plus, MagnifyingGlass, X, Check, WarningCircle, CircleNotch, Play, Stop, Circle } from '@phosphor-icons/react';
import { AppearanceControl } from './AppearanceControl.jsx';
import { WeekTimetable } from './WeekTimetable.jsx';
import { BoyaProgress } from './BoyaProgress.jsx';
import { FeatureProgress } from './FeatureProgress.jsx';
import { TDProgress } from './TDProgress.jsx';
import { SunshineProgress } from './SunshineProgress.jsx';
import { filterPeople } from './people.js';
import { featureState, personFeatureState, dashboardTotals } from './dashboard-state.js';

const features = [
  { id: 'class', title: '上课签到', short: '上课', icon: GraduationCap, glyph: '课', detail: '查看课表' },
  { id: 'td', title: 'TD 锻炼', short: 'TD', icon: Barbell, glyph: 'TD', detail: '查看进度' },
  { id: 'boya', title: '博雅课程', short: '博雅', icon: BookOpen, glyph: '博', detail: '查看进度' },
  { id: 'ygdk', title: '阳光打卡', short: '阳光', icon: Sun, glyph: '阳', detail: '查看记录' },
];
const isRunning = (service) => ['running', 'native-running'].includes(service?.status);
function formatTime(value) {
  if (!value) return '暂无记录';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}
const token = document.querySelector('meta[name="autobh-token"]')?.content ?? '';
async function api(path, body, signal) {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: { 'X-AutoBH-Token': token, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '操作未完成，请重试');
  return result;
}

function Dialog({ title, children, onClose, wide = false, timetable = false, td = false, sunshine = false }) {
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    dialog.querySelector('input:not(:disabled)')?.focus();
    return () => { if (dialog.open) dialog.close(); };
  }, []);
  return <dialog ref={ref} aria-label={title} className={`dialog ${wide ? 'dialog-wide' : ''} ${timetable ? 'dialog-timetable' : ''} ${td ? 'dialog-td' : ''} ${sunshine ? 'dialog-sunshine' : ''}`} onCancel={onClose} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="dialog-heading"><h2>{title}</h2><button className="icon-button" onClick={onClose} aria-label="关闭对话框"><X size={22} /></button></div>
    {children}
  </dialog>;
}

function PersonForm({ person, onSave, onClose, onDelete, busy, error }) {
  const [username, setUsername] = useState(person?.username ?? '');
  const [name, setName] = useState(person?.name ?? '');
  const [group, setGroup] = useState(person?.group ?? '');
  return <Dialog title={person ? '编辑资料' : '添加人员'} onClose={onClose}>
    <form onSubmit={(event) => { event.preventDefault(); onSave({ username: username.trim(), name: name.trim(), group: group.trim() }); }}>
      <label>学号<input name="username" autoFocus={!person} required maxLength={40} value={username} disabled={!!person} onChange={(event) => setUsername(event.target.value)} placeholder="输入学号" autoComplete="off" /></label>
      <label>姓名<input name="name" autoFocus={!!person} maxLength={80} value={name} onChange={(event) => setName(event.target.value)} placeholder="便于识别的姓名或备注" autoComplete="off" /></label>
      <label>分组 <span className="optional">选填</span><input name="group" maxLength={120} value={group} onChange={(event) => setGroup(event.target.value)} placeholder="例如：学院路" autoComplete="off" /></label>
      {!person && <p className="form-hint">添加后，可分别绑定上课、TD、博雅和阳光账号。</p>}
      {error && <p role="alert" className="form-error">{error}</p>}
      <div className="dialog-actions">{person && <button type="button" className="delete-person form-delete" disabled={busy} onClick={onDelete}>删除人员</button>}<button type="button" className="button secondary" onClick={onClose}>取消</button><button className="button primary" disabled={busy}>{busy ? '保存中…' : '保存资料'}</button></div>
    </form>
  </Dialog>;
}

function BindForm({ feature, person, state, onSave, onClose, busy, error }) {
  const [password, setPassword] = useState('');
  const [campus, setCampus] = useState('北京');
  const [quick, setQuick] = useState('学院路');
  const [unsafe, setUnsafe] = useState(false);
  const [file, setFile] = useState(null);
  const isTD = feature.id === 'td';
  const isSunshine = feature.id === 'ygdk';
  const canReuse = isSunshine && (person.features.class || person.features.boya);
  const [reuse, setReuse] = useState(!!canReuse);
  return <Dialog title={`绑定${feature.title}`} onClose={onClose}>
    <p className="form-hint first-hint">{person.name || '未命名人员'} · {person.username}</p>
    <form onSubmit={(event) => { event.preventDefault(); onSave({ username: person.username, feature: feature.id, password: reuse ? '' : password, campus, quick, unsafe }, file); }}>
      {isTD ? <>
        <label>校区<select value={quick} onChange={(event) => setQuick(event.target.value)}><option>学院路</option><option>沙河</option></select></label>
        <label>打卡图片 {!state.td_images.length && <span className="required">必填</span>}<input type="file" accept="image/jpeg,image/png,image/webp" required={!state.td_images.length} onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label>
        <p className="form-hint">{state.td_images.length ? '已有可用图片，也可以上传新图片。' : '先导入一张图片，即可沿用原 TD 的快速配置。'}</p>
      </> : <>
        <>{canReuse && <label className="checkbox-label"><input type="checkbox" checked={reuse} onChange={(event) => setReuse(event.target.checked)} />复用已绑定的上课 / 博雅密码</label>}{!reuse && <label>学校账号密码<input type="password" name="password" autoFocus autoComplete="new-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>}</>
        {isSunshine && !reuse && <label className="checkbox-label"><input type="checkbox" checked={unsafe} onChange={(event) => setUnsafe(event.target.checked)} />钥匙串不可用时，允许保存到本地密码文件</label>}{feature.id === 'boya' && <><label>校区<select value={campus} onChange={(event) => setCampus(event.target.value)}><option>北京</option><option>杭州</option></select></label><label className="checkbox-label"><input type="checkbox" checked={unsafe} onChange={(event) => setUnsafe(event.target.checked)} />钥匙串不可用时，允许保存到本地密码文件</label></>}
        <p className="form-hint">{isSunshine ? '复用学校统一认证。后台只同步数据，运动记录手动核对后提交。' : feature.id === 'class' ? '密码沿用上课工具的本地配置保存方式。' : '优先使用系统钥匙串保存密码。博雅自动化沿用原有选课、签到和签退规则。'}</p>
      </>}
      {error && <p role="alert" className="form-error">{error}</p>}
      <div className="dialog-actions"><button type="button" className="button secondary" onClick={onClose}>取消</button><button className="button primary" disabled={busy}>{busy ? '绑定中…' : '绑定账号'}</button></div>
    </form>
  </Dialog>;
}

export function App() {
  const [state, setState] = useState(null);
  const [selectedId, setSelectedId] = useState('');
  const [query, setQuery] = useState('');
  const [peopleFilter, setPeopleFilter] = useState('all');
  const [searchOpen, setSearchOpen] = useState(false);
  const [modal, setModal] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [connectionError, setConnectionError] = useState('');
  const [toast, setToast] = useState('');
  const [detail, setDetail] = useState(null);
  const [tdSyncError, setTdSyncError] = useState(false);
  const [logFeature, setLogFeature] = useState('class');
  const generation = useRef(0);
  const detailAbort = useRef(null);
  const visiblePeople = state ? filterPeople(state.people, query, peopleFilter, state.services) : [];
  const selected = visiblePeople.find((person) => person.username === selectedId) ?? visiblePeople[0];
  const totals = dashboardTotals(state?.people, state?.services);

  const refresh = useCallback(async (signal) => {
    const revision = ++generation.current;
    try {
      const next = await api('/api/state', undefined, signal);
      if (revision === generation.current) { setState(next); setConnectionError(''); }
    } catch (failure) {
      if (failure.name !== 'AbortError' && revision === generation.current) setConnectionError(failure.message);
    }
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    refresh(abort.signal);
    const interval = setInterval(() => { if (!document.hidden) refresh(abort.signal); }, 5000);
    return () => { abort.abort(); clearInterval(interval); };
  }, [refresh]);
  useEffect(() => { if (!toast) return; const timeout = setTimeout(() => setToast(''), 4200); return () => clearTimeout(timeout); }, [toast]);
  useEffect(() => () => detailAbort.current?.abort(), []);
  // TD detail is strictly local. Keep animation/state current without querying
  // a school endpoint or starting a scheduler from a read action.
  useEffect(() => {
    if (modal?.type !== 'detail' || modal.feature !== 'td' || busy) return;
    const abort = new AbortController();
    let inflight = false;
    const timer = setInterval(async () => {
      if (document.hidden || inflight) return;
      inflight = true;
      try {
        const next = await api(`/api/detail/td/${encodeURIComponent(modal.username)}`, undefined, abort.signal);
        if (!abort.signal.aborted) { setDetail({ ...next, receivedAt: new Date().toISOString() }); setTdSyncError(false); }
      } catch (failure) { if (failure.name !== 'AbortError') setTdSyncError(true); }
      finally { inflight = false; }
    }, 3000);
    return () => { clearInterval(timer); abort.abort(); };
  }, [modal?.type, modal?.feature, modal?.username, busy]);

  function openModal(next) { detailAbort.current?.abort(); setError(''); setTdSyncError(false); setDetail(null); setModal(next); }
  function closeModal() { detailAbort.current?.abort(); setModal(null); setError(''); }
  async function action(key, path, payload, close = false) {
    setBusy(key); setError('');
    try {
      const result = await api(path, payload);
      await refresh();
      setToast(result.message);
      if (close) setModal(null);
      return true;
    } catch (failure) { setError(failure.message); return false; }
    finally { setBusy(''); }
  }
  async function savePerson(payload) {
    if (await action('save', '/api/people/save', payload, true)) { setSelectedId(payload.username); setPeopleFilter('all'); setQuery(''); }
  }
  async function saveBinding(payload, file) {
    setBusy('bind'); setError('');
    try {
      if (file) {
        if (file.size > 8 * 1024 * 1024) throw new Error('图片需小于 8 MB');
        const encoded = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = () => reject(new Error('图片读取失败')); reader.readAsDataURL(file); });
        await api('/api/images', { name: file.name, data: encoded });
      }
      const result = await api('/api/account', payload);
      await refresh(); setToast(result.message); setModal(null);
    } catch (failure) { setError(failure.message); }
    finally { setBusy(''); }
  }
  async function showDetail(feature, person = selected) {
    openModal({ type: 'detail', feature: feature.id, username: person.username, title: feature.id === 'class' ? '本周课表' : feature.id === 'td' ? 'TD 进度' : feature.id === 'ygdk' ? '阳光打卡' : '博雅进度' });
    const abort = new AbortController(); detailAbort.current = abort;
    try { setDetail({ ...await api(`/api/detail/${feature.id}/${encodeURIComponent(person.username)}`, undefined, abort.signal), receivedAt: new Date().toISOString() }); }
    catch (failure) { if (failure.name !== 'AbortError') setError(failure.message); }
  }
  async function refreshDetail() {
    const target = modal;
    setBusy('refresh'); setError('');
    detailAbort.current?.abort();
    const abort = new AbortController(); detailAbort.current = abort;
    try {
      const result = await api('/api/refresh', { feature: target.feature, username: target.username }, abort.signal);
      setDetail({ ...result.detail, receivedAt: new Date().toISOString() }); setTdSyncError(false); setToast(result.message); await refresh();
    } catch (failure) { if (failure.name !== 'AbortError') { setError(failure.message); if (target.feature === 'ygdk') { try { setDetail(await api(`/api/detail/ygdk/${encodeURIComponent(target.username)}`, undefined, abort.signal)); } catch {} } } }
    finally { setBusy(''); }
  }
  async function withdraw(courseId) {
    const target = modal;
    setBusy('withdraw'); setError('');
    detailAbort.current?.abort();
    const abort = new AbortController(); detailAbort.current = abort;
    try {
      const result = await api('/api/boya/drop', { username: target.username, courseId }, abort.signal);
      setDetail(result.detail); setToast(result.message); await refresh();
      return true;
    } catch (failure) { if (failure.name !== 'AbortError') setError(failure.message); return false; }
    finally { setBusy(''); }
  }
  async function sunshineAction(path, payload) {
    setBusy('sunshine'); setError('');
    const target = modal;
    detailAbort.current?.abort(); const abort = new AbortController(); detailAbort.current = abort;
    try {
      const result = await api(path, { username: target.username, ...payload }, abort.signal);
      setDetail({ ...result.detail, batch: result.batch }); if (result.message) setToast(result.message); await refresh(); return result.batch?.status !== 'paused';
    } catch (failure) { if (failure.name !== 'AbortError') setError(failure.message); return false; }
    finally { setBusy(''); }
  }
  async function loadLogs(feature) {
    setLogFeature(feature); setDetail(null); setError('');
    detailAbort.current?.abort(); const abort = new AbortController(); detailAbort.current = abort;
    try { setDetail(await api(`/api/logs/${feature}`, undefined, abort.signal)); }
    catch (failure) { if (failure.name !== 'AbortError') setError(failure.message); }
  }
  function showLogs() { openModal({ type: 'logs' }); loadLogs(logFeature); }

  return <div className="app-shell">
    <header className="app-header">
      <a className="brand" href="/" aria-label="AutoBH 首页">AutoBH</a>
      <div className="dashboard-totals" role="group" aria-label="功能状态统计"><span><strong>{state ? totals.running : '—'}</strong> 运行中</span><i aria-hidden="true">·</i><span><strong>{state ? totals.paused : '—'}</strong> 已暂停</span><i aria-hidden="true">·</i><span><strong>{state ? totals.unbound : '—'}</strong> 未绑定</span></div>
      <div className="header-actions"><AppearanceControl save={(appearance) => api('/api/appearance', { appearance })} />
      <button className="text-button manage-background" onClick={() => openModal({ type: 'services' })}>管理后台</button></div>
    </header>
    {connectionError && <div role="alert" className="connection-error"><WarningCircle size={20} /><span>连接中断：{connectionError}</span><button onClick={() => refresh()}>重新连接</button></div>}
    <div className="workspace">
      <aside className="people-sidebar" aria-label="人员列表">
        <div className="sidebar-controls">
          <div className="people-filters" role="group" aria-label="人员筛选">{[{id: 'all', label: '全部'}, {id: 'running', label: '运行中'}, {id: 'unbound', label: '未绑定'}].map((filter) => <button key={filter.id} aria-pressed={peopleFilter === filter.id} className={peopleFilter === filter.id ? 'active' : ''} onClick={() => setPeopleFilter(filter.id)}>{filter.label}</button>)}</div>
          <div className="sidebar-utilities"><button className="icon-button" aria-label="搜索人员" aria-expanded={searchOpen} title="搜索人员" onClick={() => setSearchOpen(!searchOpen)}><MagnifyingGlass size={16} /></button><button className="icon-button" title="添加人员" aria-label="添加人员" onClick={() => openModal({ type: 'person' })}><Plus size={17} /></button></div>
        </div>
        {(searchOpen || query) && <div className="search-field"><MagnifyingGlass size={17} /><input autoFocus aria-label="搜索姓名或学号" placeholder="搜索姓名或学号" value={query} onChange={(event) => setQuery(event.target.value)} /><button aria-label="关闭搜索" onClick={() => { setQuery(''); setSearchOpen(false); }}><X size={16} /></button></div>}
        <nav className="people-list" aria-label="人员名单" tabIndex={0}>{!state ? <p className="sidebar-empty">正在读取人员…</p> : visiblePeople.length ? visiblePeople.map((person) => <button key={person.username} className={`person-item ${selected?.username === person.username ? 'selected' : ''}`} aria-current={selected?.username === person.username ? 'true' : undefined} onClick={() => { setSelectedId(person.username); setError(''); }}>
          <span className="person-identity"><span className={`person-name ${person.name ? '' : 'unnamed'}`}>{person.name || '未命名人员'}</span><span className="student-id">{person.username}</span></span><span className="person-feature-dots" aria-label="四项功能启用状态">{features.map((feature) => { const status = personFeatureState(person.features[feature.id]); return <Circle key={feature.id} size={8} weight="fill" className={`person-state-dot ${status.tone}`} aria-label={`${feature.short}：${status.label}`} title={`${feature.short}：${status.label}`} />; })}</span>
        </button>) : <p className="sidebar-empty">{state.people.length ? '没有符合条件的人员' : '暂无人员，点击上方添加'}</p>}</nav>
        <div className="sidebar-footer">{state?.demo ? '示例数据 · 不会影响真实账号' : ''}</div>
      </aside>
      <main key={selected?.username ?? 'empty'} className="person-detail" aria-label="人员功能详情" tabIndex={0}>
        {selected ? <>
          <div className="person-heading"><div><h1>{selected.name || '未命名人员'}</h1><div className="person-meta"><span className="detail-student-id">{selected.username}</span>{selected.group?.trim() && selected.group.trim() !== '未分组' && <span className="person-group">{selected.group}</span>}</div></div><div className="person-heading-actions"><button className="text-button" onClick={showLogs}>查看运行记录</button><button className="button edit-person" onClick={() => openModal({ type: 'person', person: selected })}>编辑资料</button></div></div>
          <section className="automation" aria-label="自动执行"><div className="feature-list">{features.map((feature) => {
            const binding = selected.features[feature.id];
            const backend = state.services[feature.id];
            const disabled = !!busy || !backend?.available;
            const status = featureState(binding, backend);
            const updated = binding?.counts;
            return <article className={`feature-card feature-${feature.id} ${binding ? 'bound' : 'unbound'}`} key={feature.id}>
              <div className="feature-card-header"><span className="feature-monogram" aria-hidden="true">{feature.glyph}</span><div className="feature-card-title"><h3>{feature.title}</h3><span className={`feature-card-status ${status.tone}`}><Circle size={7} weight="fill" aria-hidden="true" />{status.label}</span></div>
                {binding && <button type="button" role="switch" aria-label={`${feature.title}${feature.id === 'ygdk' ? '自动同步' : '自动执行'}`} aria-checked={!!binding.enabled} disabled={disabled} title={feature.id === 'ygdk' ? (binding.enabled ? '暂停自动同步' : '启用自动同步') : binding.enabled ? '暂停自动执行' : '启用自动执行'} className="toggle-control" onClick={() => action(`toggle-${feature.id}`, '/api/feature', { username: selected.username, feature: feature.id, enabled: !binding.enabled })}><span className={`toggle-track ${binding.enabled ? 'on' : ''}`} /></button>}
              </div>
              {!binding ? <div className="card-empty"><p>绑定账号后可启用</p><button className="button feature-action" disabled={disabled} onClick={() => openModal({ type: 'bind', feature, person: selected })}>绑定账号</button></div> : <>
                <div className="feature-card-body"><FeatureProgress feature={feature.id} binding={binding} />{feature.id === 'class' && <p className="card-class-description">查看本周课程与签到情况</p>}</div>
                <p className={`card-updated ${updated?.refreshError ? 'refresh-failed' : ''}`}>{binding.refreshing ? '正在查询最新数据…' : updated?.refreshError || (updated?.updatedAt ? `数据更新于 ${formatTime(updated.updatedAt)}` : '暂无数据更新记录')}</p>
                <button className="card-detail-link" disabled={disabled} onClick={() => showDetail(feature)} aria-label={`${feature.title} · ${feature.detail}`} title={feature.detail}><span>{feature.detail}</span></button>
              </>}
            </article>;
          })}</div></section>
          {error && !modal && <div role="alert" className="inline-error"><WarningCircle size={20} />{error}</div>}
        </> : <div className="empty-main"><GraduationCap size={58} weight="light" /><h1>{!state ? '正在连接 AutoBH' : state.people.length ? '没有符合条件的人员' : '从添加一位人员开始'}</h1><p>{state?.people.length ? '试试切换筛选，或搜索其他姓名和学号。' : '在这里管理上课、TD、博雅和阳光的功能。'}</p>{state?.people.length ? <button className="button secondary" onClick={() => { setQuery(''); setPeopleFilter('all'); }}>重置筛选</button> : state && <button className="button primary" onClick={() => openModal({ type: 'person' })}><Plus size={20} />添加人员</button>}</div>}
      </main>
    </div>
    {toast && <div className="toast" role="status"><Check size={19} weight="bold" />{toast}</div>}
    {modal?.type === 'person' && <PersonForm person={modal.person} onDelete={() => openModal({ type: 'delete', person: modal.person })} onSave={savePerson} onClose={closeModal} busy={!!busy} error={error} />}
    {modal?.type === 'bind' && <BindForm feature={modal.feature} person={modal.person} state={state} onSave={saveBinding} onClose={closeModal} busy={!!busy} error={error} />}
    {modal?.type === 'delete' && <Dialog title="删除这位人员？" onClose={closeModal}><p className="delete-description">将移除 <strong>{modal.person.name || modal.person.username}</strong> 的人员资料和全部功能绑定。历史日志与缓存会保留。</p><p className="form-hint">后台在下一轮读取时生效，已发出的请求会继续完成。</p>{error && <p className="form-error" role="alert">{error}</p>}<div className="dialog-actions"><button className="button secondary" onClick={closeModal}>取消</button><button className="button danger" disabled={!!busy} onClick={() => action('delete', '/api/people/remove', { username: modal.person.username }, true)}>{busy ? '删除中…' : '删除人员'}</button></div></Dialog>}
    {modal?.type === 'services' && <Dialog title="管理后台" onClose={closeModal}><p className="form-hint first-hint">后台按功能独立运行，关闭管理窗口后会继续执行。</p><div className="service-list">{features.map((feature) => { const backend = state?.services[feature.id]; const running = isRunning(backend); const Icon = feature.icon; return <div className="service-item" key={feature.id}><Icon size={28} weight="light" /><div><strong>{feature.title}</strong><span><i className={`status-dot ${running ? 'green' : 'gray'}`} />{!backend?.available ? '功能不可用' : backend.stop_requested ? '正在停止' : backend.status === 'native-running' ? '由原工具运行' : running ? '运行中' : '已停止'}</span></div><button className="button secondary small" disabled={!!busy || !backend?.available || backend.stop_requested} onClick={() => action(`service-${feature.id}`, '/api/service', { feature: feature.id, action: running ? 'stop' : 'start' })}>{running ? <Stop size={15} /> : <Play size={15} />}{busy === `service-${feature.id}` ? '处理中…' : running ? '停止' : '启动'}</button></div>; })}</div>{error && <p className="form-error" role="alert">{error}</p>}</Dialog>}
    {(modal?.type === 'detail' || modal?.type === 'logs') && <Dialog title={modal.type === 'logs' ? '运行记录' : modal.title} onClose={closeModal} wide timetable={modal.type === 'detail' && modal.feature === 'class'} td={modal.type === 'detail' && modal.feature === 'td'} sunshine={modal.type === 'detail' && modal.feature === 'ygdk'}>
      {modal.type === 'logs' && <div className="log-tabs">{features.map((feature) => <button key={feature.id} className={logFeature === feature.id ? 'active' : ''} onClick={() => loadLogs(feature.id)}>{feature.title}</button>)}</div>}
      {modal.type === 'detail' && modal.feature !== 'td' && <div className="detail-toolbar"><span>数据更新：{formatTime(detail?.updatedAt)}</span><button className="button secondary small" disabled={!!busy} onClick={refreshDetail}>{busy === 'refresh' ? '刷新中…' : '刷新数据'}</button></div>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {detail ? modal.type === 'detail' && modal.feature === 'class' ? <WeekTimetable detail={detail} /> : modal.type === 'detail' && modal.feature === 'td' ? <TDProgress detail={detail} onRefresh={refreshDetail} busy={!!busy} syncError={tdSyncError} /> : modal.type === 'detail' && modal.feature === 'ygdk' ? <SunshineProgress detail={detail} busy={!!busy} onReconnect={refreshDetail} onRebind={() => openModal({ type: 'bind', feature: features.find((feature) => feature.id === 'ygdk'), person: state.people.find((person) => person.username === modal.username) })} onPage={(page) => sunshineAction('/api/ygdk/records', { page })} onSubmit={(payload) => sunshineAction(payload.records ? '/api/ygdk/batch' : '/api/ygdk/submit', payload)} /> : modal.type === 'detail' && modal.feature === 'boya' && detail.courses ? <BoyaProgress detail={detail} onWithdraw={withdraw} busy={!!busy} /> : <pre className="records-content">{detail.text}</pre> : <div className="loading-detail"><CircleNotch className="spin" size={22} />{modal.type === 'detail' && modal.title === '本周课表' ? '正在查询课表，请稍候…' : '正在读取…'}</div>}
    </Dialog>}
  </div>;
}
