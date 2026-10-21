import { useState } from 'react';
import { Check, Question, Minus, WarningCircle } from '@phosphor-icons/react';

function AttendanceBadge({ record }) {
  const Icon = record.state === 'done' ? Check : record.state === 'warning' ? WarningCircle : record.state === 'unknown' ? Question : Minus;
  return <span className={`boya-attendance ${record.state}`}><Icon size={15} aria-hidden="true" />{record.label}</span>;
}

export function BoyaProgress({ detail, onWithdraw, onCustomize, busy }) {
  const [confirmId, setConfirmId] = useState(null);
  const [editing, setEditing] = useState(false);
  const [mode, setMode] = useState('categories');
  const [target, setTarget] = useState('6');
  const stop = detail.stopCondition;
  function openCustomization() {
    setMode(stop?.mode === 'total' ? 'total' : 'categories');
    setTarget(String(stop?.target ?? 6));
    setEditing(true);
  }
  return <div className="boya-progress">
    <div className="boya-summary"><div className="boya-summary-heading"><strong>{detail.summary}</strong>{onCustomize && <button className="button secondary small" disabled={busy} aria-expanded={editing} aria-controls="boya-personalization" onClick={openCustomization}>个人定制</button>}</div><p>{stop?.label ?? '默认 · 各类达到学校考核指标'}</p></div>
    {editing && <form id="boya-personalization" className="boya-personalization" aria-label="个人定制" onSubmit={async (event) => {
      event.preventDefault();
      if (await onCustomize(mode === 'total' ? { mode, target: Number(target) } : { mode })) setEditing(false);
    }}>
      <h3>个人定制</h3>
      <div className="boya-personalization-fields"><label>停止条件<select value={mode} disabled={busy} onChange={(event) => setMode(event.target.value)}><option value="categories">默认：各类达到学校指标</option><option value="total">净有效次数达到指定次数</option></select></label>
        {mode === 'total' && <label>净有效次数目标<input type="number" min="1" max="10000" step="1" required value={target} disabled={busy} onChange={(event) => setTarget(event.target.value)} /></label>}</div>
      <p className="form-hint">{mode === 'total' ? '仅按官方净有效次数停选；某类已达标仍可选，直到总目标达标。' : '每类达到官方指标后停止选该类，全部达标后停止新选课。'}仅对当前同学生效，已选课程继续签到、签退。</p>
      <div className="dialog-actions"><button type="button" className="button secondary small" disabled={busy} onClick={() => setEditing(false)}>取消</button><button className="button primary small" disabled={busy}>{busy ? '保存中…' : mode === 'categories' ? '恢复默认' : '保存设置'}</button></div>
    </form>}
    <div className="boya-targets" aria-label="博雅分类完成要求">{detail.categories?.map((row) => <div key={row.name} className={`boya-target ${row.met ? 'met' : ''}`}>
      <div className="boya-target-heading"><strong>{row.name}</strong><span>{!row.known ? '等待官方统计' : row.met ? '已达标' : `还需 ${row.remaining} 次`}</span></div>
      <div className="boya-target-count"><strong>{row.completed ?? '—'}</strong><span> / {row.required ?? '—'}</span></div>
      <p>考核通过 {row.completed ?? '—'}{row.failed != null && ` · 未通过 ${row.failed}`}{row.pending > 0 && ` · 待考核 ${row.pending}`}</p>
    </div>)}</div>
    <p className="boya-school-count">分类通过数不扣减未通过课程；净有效次数由学校单独核算。</p>
    {detail.refreshError && <p className="form-error" role="alert">{detail.refreshError}，当前显示上次缓存。</p>}
    {detail.excludedCount > 0 && <p className="boya-cache-note">已排除 {detail.excludedCount} 门手动退选课程，后台不会自动选回。</p>}
    <section aria-label="已选博雅课程"><h3 className="boya-section-heading">已选课程 <span>{detail.courses.length} 门</span></h3>
      {detail.courses.length ? <ul className="boya-course-list">{detail.courses.map((course, index) => <li key={`${course.id}-${index}`} className="boya-course">
        <h4>{course.name || '未命名课程'}</h4>
        <p className="boya-course-meta"><span>{course.category || '未分类'}</span><time>{course.start?.replace('T', ' ').slice(0, 16) || '时间待更新'}</time>{course.location && <span>{course.location}</span>}</p>
        <div className="boya-attendance-list" aria-label={`${course.name}签到与签退情况`}><AttendanceBadge record={course.signIn} /><AttendanceBadge record={course.signOut} /><span className={`boya-settlement ${course.settlement.state}`}>{course.settlement.label}</span></div>
        {course.dropVisible && <div className="course-withdraw"><span>{course.cancelEnd ? `退选截止：${course.cancelEnd.replace('T', ' ').slice(0, 16)}` : '退选截止时间待更新'}</span>{course.canDrop && onWithdraw ? <button className="text-button delete-person" disabled={busy} onClick={() => setConfirmId(course.id)}>退选</button> : <span>{course.dropReason}</span>}</div>}
        {confirmId === course.id && <div className="withdraw-confirm" role="group" aria-label="确认退选"><p>确认退选「{course.name}」？退选后后台不会自动选回。</p><div className="dialog-actions"><button className="button secondary small" disabled={busy} onClick={() => setConfirmId(null)}>取消</button><button className="button danger small" disabled={busy} onClick={async () => { if (await onWithdraw(course.id)) setConfirmId(null); }}>{busy ? '退选中…' : '确认退选'}</button></div></div>}
      </li>)}</ul> : <p className="boya-empty">当前账号暂无已选课程缓存，后台定期刷新后更新。</p>}
    </section>
    <p className="boya-cache-note">签到、签退仅展示独立记录，不用于推算考核结果；记录不完整时仍以学校考核为准。</p>
  </div>;
}
