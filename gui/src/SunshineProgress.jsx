import { useEffect, useId, useRef, useState } from 'react';
import { Sun, ArrowClockwise, Check, Plus } from '@phosphor-icons/react';
import { spacedRecords, remainingThisWeek, automaticBatchRecords, unfinishedRecords } from './sunshine.js';

const time = (value) => value ? new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '时间未知';
const count = (value, target) => `${value ?? '—'}${target != null ? ` / ${target}` : ''}`;

export function SunshineProgress({ detail, busy, onPage, onSubmit, onReconnect, onRebind }) {
  const formId = useId();
  const contentRef = useRef(null);
  const [editing, setEditing] = useState(false);
  const [review, setReview] = useState(null);
  const [photo, setPhoto] = useState(null);
  const [preview, setPreview] = useState('');
  const [error, setError] = useState('');
  const [batchSize, setBatchSize] = useState(0);
  const [extraTimes, setExtraTimes] = useState([]);
  const [form, setForm] = useState({ itemId: '', startTime: '', endTime: '', place: '' });
  useEffect(() => { contentRef.current?.scrollTo({ top: 0 }); }, [editing, review]);
  useEffect(() => {
    if (!photo) { setPreview(''); return; }
    const url = URL.createObjectURL(photo); setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);
  async function prepare(event) {
    event.preventDefault(); setError('');
    const records = [{ startTime: form.startTime, endTime: form.endTime }, ...extraTimes].slice(0, batchSize || 1);
    if (batchSize && records.some((row) => !row.startTime || !row.endTime || row.endTime <= row.startTime || row.startTime.slice(0, 10) !== row.endTime.slice(0, 10))) { setError('请填写每段运动的完整时间，且每段须在同一天'); return; }
    if (unfinishedRecords(records)) { setError('部分运动时段尚未结束，全部结束并核对实际运动信息后才能一起提交'); return; }
    if (!photo || photo.size > 8 * 1024 * 1024) { setError('请选择不超过 8 MB 的运动图片'); return; }
    if (form.endTime <= form.startTime || form.startTime.slice(0, 10) !== form.endTime.slice(0, 10)) { setError('结束时间须晚于开始时间，且在同一天'); return; }
    if (new Date(`${form.endTime}+08:00`) > new Date()) { setError('运动尚未结束，请结束后再提交'); return; }
    try {
      const encoded = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = () => reject(new Error('图片读取失败')); reader.readAsDataURL(photo); });
      setReview({ ...form, ...(batchSize ? { records } : {}), itemId: Number(form.itemId), requestId: crypto.randomUUID(), photo: { name: photo.name, data: encoded } });
    } catch (failure) { setError(failure.message); }
  }
  const summary = detail.summary || {};
  const authorization = detail.authorization;
  const remaining = remainingThisWeek(summary.weekCount);
  const draftRecords = [{ startTime: form.startTime, endTime: form.endTime }, ...extraTimes];
  const pending = batchSize ? unfinishedRecords(draftRecords) : 0;
  function openBatch() {
    try {
      const rows = automaticBatchRecords(remaining);
      const recent = detail.records?.[0];
      const item = detail.items?.find((value) => value.name === '跑步') ?? detail.items?.find((value) => value.name === recent?.itemName) ?? detail.items?.[0];
      setForm((value) => ({ ...value, ...rows[0], itemId: String(item?.id ?? ''), place: value.place || recent?.place || '' }));
      setBatchSize(remaining); setExtraTimes(rows.slice(1)); setEditing(true); setReview(null); setError('');
    } catch (failure) { setError(failure.message); }
  }
  function fillTimes() {
    try { setExtraTimes(spacedRecords(form.startTime, form.endTime, batchSize).slice(1)); setError(''); }
    catch (failure) { setError(failure.message); }
  }
  function updateTime(index, key, value) {
    if (index === 0) setForm((previous) => ({ ...previous, [key]: value }));
    else setExtraTimes((previous) => previous.map((row, i) => i === index - 1 ? { ...row, [key]: value } : row));
  }
  async function submitReview() {
    if (await onSubmit({ ...review, confirmed: true })) {
      setEditing(false); setReview(null); setPhoto(null); setBatchSize(0); setExtraTimes([]);
      setForm({ itemId: '', startTime: '', endTime: '', place: '' });
    }
  }
  return <div className="sunshine-dashboard">
    <div ref={contentRef} className="sunshine-scroll-body">
    {!editing && <>

    <div className={`sunshine-auth ${authorization?.required ? 'needs-auth' : ''}`}>
      <div><strong>{authorization?.required ? '学校登录需要重新连接' : '学校账号连接'}</strong><p>{authorization?.required ? '统一认证与移动校园需分别登录。可先打开学校页面检查登录或验证码，再返回重新连接。' : '使用当前绑定的学校账号连接阳光服务。'}</p></div>
      <div className="sunshine-auth-actions">{authorization?.loginUrl && <a className="button secondary small" href={authorization.loginUrl} target="_blank" rel="noopener noreferrer">学校登录/授权</a>}<button className="button primary small" disabled={busy} onClick={onReconnect}>{busy ? '连接中…' : '重新连接'}</button><button className="text-button" disabled={busy} onClick={onRebind}>更新账号</button></div>
      <p className="sunshine-auth-note">学校页面在浏览器中打开；浏览器登录不会直接导入 App，重新连接会使用此人的绑定账号。</p>
    </div>
    <div className="sunshine-metrics" aria-label="阳光完成次数">{[['本学期', summary.termCount, summary.termTarget], ['本周', summary.weekCount, summary.weekTarget], ['今日', summary.dayCount]].map(([label, value, target]) => <div key={label}><span>{label}</span><strong>{count(value, target)}<small> 次</small></strong></div>)}</div>
    </>}
    {detail.refreshError && <p className="form-error" role="alert">{detail.refreshError}；当前显示上次缓存。</p>}
    {detail.batch && <div className="sunshine-batch-result" role="status"><strong>{detail.batch.status === 'paused' ? '四连已暂停' : '四连处理结果'}</strong><ol>{detail.batch.outcomes.map((row) => <li key={row.number} className={row.status}><span>{row.number}</span>{row.label}</li>)}</ol></div>}
    <div className="sunshine-section-heading"><h3>{editing ? batchSize ? '一键四连 · 核对时间' : '新增运动记录' : '运动记录'} <span>{editing ? '' : `${detail.total ?? 0} 条`}</span></h3><div className="sunshine-entry-actions">{!editing && <button className="button primary small" disabled={busy || !detail.items?.length || remaining == null || remaining === 0} title={remaining == null ? '请先刷新本周次数' : remaining === 0 ? '本周已达 4 次' : `本周还差 ${remaining} 次`} onClick={openBatch}>一键四连</button>}<button className="button secondary small" disabled={busy || (!editing && !detail.items?.length)} onClick={() => { setEditing(!editing); setBatchSize(0); setReview(null); setError(''); }}>{editing ? '返回记录' : <><Plus size={16} />新增打卡</>}</button></div></div>
    {!editing && error && <p className="form-error" role="alert">{error}</p>}
    {editing ? review ? <div className="sunshine-review"><h4>{review.records ? `确认 ${review.records.length} 段运动记录` : '确认本次运动'}</h4><dl><div><dt>项目</dt><dd>{detail.items.find((item) => item.id === review.itemId)?.name}</dd></div><div><dt>时间</dt><dd>{(review.records || [review]).map((row, index) => <p className="sunshine-review-time" key={index}>{review.records && <b>{index + 1}.</b>} {row.startTime.replace('T', ' ')} 至 {row.endTime.slice(11)}</p>)}</dd></div><div><dt>地点</dt><dd>{review.place}</dd></div><div><dt>图片</dt><dd>{photo?.name}</dd></div></dl>{preview && <img src={preview} alt="待提交的运动图片" />}<p className="form-hint">{review.records ? '依次提交上述记录，本周补足 4 次即停止；异常时保留已成功的记录。' : '将向学校提交此条运动记录，不公开到广场。'}</p></div> : <form id={formId} className="sunshine-form" onSubmit={prepare}>
      <div className="sunshine-meta-fields">
        <label>运动项目<select required value={form.itemId} onChange={(event) => setForm({ ...form, itemId: event.target.value })}><option value="">选择项目</option>{detail.items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label>运动地点<input required maxLength={120} placeholder="填写本次运动地点" value={form.place} onChange={(event) => setForm({ ...form, place: event.target.value })} /></label>
      </div>
      {batchSize > 0 ? <section className="sunshine-batch-times" aria-label="四连运动时间">
        <div className="sunshine-batch-hint"><span>共 {batchSize} 段 · 间隔 10 分钟 · 每段 30 分钟 · 北京时间</span>{batchSize > 1 && <button type="button" className="text-button" onClick={fillTimes}>同步后续时间</button>}</div>
        {pending > 0 && <p className="batch-time-notice" role="status">{pending} 段尚未结束，请按实际运动调整，全部结束后再一起提交。</p>}
        <div className="batch-time-table">
          <div className="batch-time-header" aria-hidden="true"><span>段次</span><span>开始时间</span><span>结束时间</span></div>
          {draftRecords.slice(0, batchSize).map((row, index) => <div className="batch-time-row" key={index}>
            <span className="batch-time-number" aria-hidden="true">{index + 1}</span>
            <label><span>开始时间</span><input type="datetime-local" aria-label={`第 ${index + 1} 段开始时间`} required value={row.startTime} onChange={(event) => updateTime(index, 'startTime', event.target.value)} /></label>
            <label><span>结束时间</span><input type="datetime-local" aria-label={`第 ${index + 1} 段结束时间`} required value={row.endTime} onChange={(event) => updateTime(index, 'endTime', event.target.value)} /></label>
          </div>)}
        </div>
      </section> : <div className="sunshine-time-fields"><label>开始时间（北京时间）<input type="datetime-local" required value={form.startTime} onChange={(event) => setForm({ ...form, startTime: event.target.value })} /></label><label>结束时间（北京时间）<input type="datetime-local" required value={form.endTime} onChange={(event) => setForm({ ...form, endTime: event.target.value })} /></label></div>}
      <label>本次运动图片<input type="file" accept="image/jpeg,image/png,image/webp" required={!photo} onChange={(event) => setPhoto(event.target.files?.[0] ?? null)} />{photo && <span className="form-hint">已选择：{photo.name}</span>}</label>
      {preview && <img className="sunshine-photo-preview" src={preview} alt="本次运动图片预览" />}
      {error && <p className="form-error" role="alert">{error}</p>}
    </form> : <>
      {detail.records?.length ? <ol className="sunshine-records">{detail.records.map((record) => <li key={record.id}><span className="sunshine-record-icon"><Sun size={20} /></span><div><strong>{record.itemName}</strong><p>{time(record.startTime)} — {record.endTime ? new Date(record.endTime).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }) : '时间未知'}<span>{record.place}</span></p></div><span className="sunshine-record-state">学校记录</span></li>)}</ol> : <p className="form-hint">{detail.updatedAt ? '暂无运动记录。' : '尚无缓存，点击“刷新数据”读取次数和运动项目。'}</p>}
      <div className="sunshine-pagination"><span>第 {detail.page || 1} 页</span><button className="button secondary small" disabled={busy || (detail.page || 1) <= 1} onClick={() => onPage(detail.page - 1)}>上一页</button><button className="button secondary small" disabled={busy || !detail.hasMore} onClick={() => onPage((detail.page || 1) + 1)}>下一页</button></div>
      <p className="form-hint sunshine-sync-note"><ArrowClockwise size={14} />后台开启后每 30 分钟同步次数与记录，新增打卡需手动提交。</p>
    </>}
    </div>
    {editing && <div className="sunshine-sticky-actions">
      <span>{review ? '核对后提交' : '时间与地点均可修改'}</span>
      {review ? <><button type="button" className="button secondary" disabled={busy} onClick={() => setReview(null)}>返回修改</button><button type="button" className="button primary" disabled={busy} onClick={submitReview}>{busy ? <><ArrowClockwise className="spin" size={17} />提交中…</> : <><Check size={17} />{review.records ? `确认四连 · ${review.records.length} 条` : '确认提交'}</>}</button></> : <button type="submit" form={formId} className="button primary" disabled={busy}>核对信息</button>}
    </div>}
  </div>;
}
