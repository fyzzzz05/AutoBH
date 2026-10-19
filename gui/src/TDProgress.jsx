import { useEffect, useState } from 'react';
import { ArrowClockwise, ArrowRight, Check, Clock, Pause, PersonSimpleRun, WarningCircle, Plugs, SignIn, SignOut, Camera } from '@phosphor-icons/react';
import { remainingTime, shortTime, tdStage } from './td-status.js';

export function TDProgress({ detail, onRefresh, busy, syncError }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const state = detail.activityState || 'waiting';
  const stage = tdStage(detail);
  const completed = detail.completedToday ?? 0;
  const target = detail.targetToday ?? 3;
  const ratio = Math.min(100, Math.max(0, target > 0 ? completed / target * 100 : 0));
  const icons = { completed: Check, exercising: PersonSimpleRun, retrying: Clock, error: WarningCircle, paused: Pause, stopped: Plugs, outside: Clock, waiting: Clock, checking: detail.activityLabel?.includes('照片') ? Camera : detail.nextAction === 'exit' ? SignOut : SignIn };
  const Icon = icons[state] || Clock;
  const countdown = state === 'retrying' ? detail.nextRetryAt : ['waiting', 'exercising'].includes(state) ? detail.dueAt : null;
  const clockOffset = detail.serverTime ? new Date(detail.serverTime).getTime() - new Date(detail.receivedAt ?? detail.serverTime).getTime() : 0;
  const timing = countdown ? remainingTime(countdown, now + clockOffset) : null;
  return <section className="td-dashboard" aria-label="TD 次数与打卡状态">
    <div className="td-sync-toolbar">
      <span className={`td-sync-label ${syncError ? 'is-offline' : ''}`}><i aria-hidden="true" />{syncError ? '同步中断 · 保留原数据' : '每 3 秒自动同步状态'}</span>
      <button className="button secondary small" onClick={onRefresh} disabled={busy}><ArrowClockwise className={busy ? 'spin' : ''} size={16} />{busy ? '读取中…' : '重新读取缓存'}</button>
    </div>
    <div className="td-metrics">
      <div className="td-total"><span>本学期已完成</span><div><strong>{detail.totalCount ?? '—'}</strong><span>次</span></div></div>
      <div className="td-daily"><div><span>今日进度</span><strong>{completed}<small> / {target} 次</small></strong></div><div className="td-daily-track" role="progressbar" aria-label="今日完成次数" aria-valuemin={0} aria-valuemax={Math.max(target, completed, 1)} aria-valuenow={completed}><span style={{ width: `${ratio}%` }} /></div><span className="td-count-time">次数更新 {shortTime(detail.updatedAt, true)}</span></div>
    </div>
    <div className={`td-activity td-state-${state}`}>
      <div className="td-motion" aria-hidden="true"><span className="td-motion-halo" /><Icon size={31} weight="regular" /><span className="td-motion-ground" /></div>
      <div className="td-current"><strong role="status">{detail.activityLabel || '等待后台执行'}</strong><span>{state === 'completed' ? '今日轮次已结束' : timing ? <>{state === 'retrying' ? '重试倒计时' : '下一次操作'} <b>{timing}</b></> : state === 'outside' ? detail.nextWindowAt ? <>下个时段 {shortTime(detail.nextWindowAt, true)}</> : '未设置打卡时段' : state === 'error' ? '展开下方详情查看原因' : state === 'paused' || state === 'stopped' ? '当前进度已保留' : state === 'checking' ? '后台正在处理当前步骤' : '等待后台按计划执行'}</span></div>
      <span className="td-phase-label">{state === 'completed' ? `${completed} 轮完成` : `第 ${Math.min(completed + 1, target)} / ${target} 轮`}</span>
    </div>
    <ol className="td-flow" aria-label="当前轮次阶段">{['入场', '锻炼', '离场'].map((label, index) => <li key={label} className={stage > index ? 'done' : stage === index ? `current ${state}` : ''}><span>{stage > index ? <Check size={13} weight="bold" /> : index + 1}</span><b>{label}</b>{index < 2 && <ArrowRight size={15} aria-hidden="true" />}</li>)}</ol>
    <div className="td-source-note"><InfoMark /><p><strong>{detail.windowOpen ? '实时次数随后台打卡更新' : '当前只能读取缓存'}</strong><span>{detail.realtimeRead?.message || 'TD 暂无独立查询接口，不会额外发起打卡。'}</span></p></div>
    {detail.lastError && <details className="td-error-detail"><summary><WarningCircle size={17} />{state === 'retrying' ? '连接异常' : '最近异常'}{detail.nextRetryAt && <span>已重试 {detail.retryCount ?? 0} / 3</span>}</summary><p>{detail.lastError}</p><div>{detail.failedAt && <span>失败时间 {shortTime(detail.failedAt, true)}</span>}{detail.nextRetryAt && <span>下次重试 {shortTime(detail.nextRetryAt, true)}</span>}</div></details>}
  </section>;
}

function InfoMark() { return <span className="td-info-mark" aria-hidden="true">i</span>; }
