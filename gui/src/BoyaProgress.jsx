import { useState } from 'react';
import { Check, Question, Minus, WarningCircle } from '@phosphor-icons/react';

function AttendanceBadge({ record }) {
  const Icon = record.state === 'done' ? Check : record.state === 'warning' ? WarningCircle : record.state === 'unknown' ? Question : Minus;
  return <span className={`boya-attendance ${record.state}`}><Icon size={15} aria-hidden="true" />{record.label}</span>;
}

export function BoyaProgress({ detail, onWithdraw, busy }) {
  const [confirmId, setConfirmId] = useState(null);
  return <div className="boya-progress">
    <div className="boya-summary"><strong>{detail.met ? '博雅要求已达标' : detail.summary}</strong><p>签到与签退均成功 +1，结束后未完成 −1；四类分别核算。</p></div>
    <div className="boya-targets" aria-label="博雅分类完成要求">{detail.categories?.map((row) => <div key={row.name} className={`boya-target ${row.met ? 'met' : ''}`}>
      <div className="boya-target-heading"><strong>{row.name}</strong><span>{detail.totalCount == null ? '等待数据' : row.met ? '已达标' : row.unknown ? '待核实' : `还需 ${row.remaining} 次`}</span></div>
      <div className={`boya-target-count ${row.net < 0 ? 'negative' : ''}`}><strong>{detail.totalCount == null ? '—' : row.net}</strong><span> / {row.required}</span></div>
      <p>完成 {row.completed} · 扣次 {row.failed}{row.pending > 0 && ` · 待完成 ${row.pending}`}{row.unknown > 0 && ` · 待核实 ${row.unknown}`}</p>
    </div>)}</div>
    {detail.schoolValidCount != null && <p className="boya-school-count">学校缓存有效次数：{detail.schoolValidCount}。上方按当前签到、签退记录和你的规则核算。</p>}
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
    <p className="boya-cache-note">未到结束时间暂不扣次；状态字段缺失、无法识别或缓存早于签退结束时间时，标为待核实，不直接判定扣次。</p>
  </div>;
}
