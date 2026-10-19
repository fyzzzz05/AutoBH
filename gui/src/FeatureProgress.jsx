export function FeatureProgress({ feature, binding }) {
  const counts = binding?.counts;
  if (!binding || (!counts && !binding.progress)) return null;
  if (feature === 'td' && counts) {
    const completed = Number(counts.completedToday ?? 0);
    const target = Number(counts.targetToday ?? 3);
    return <div className="td-progress-card" aria-label={`TD 本学期已完成 ${counts.totalCount ?? '未知'} 次，今日 ${completed} / ${target} 次`}>
      <div className="td-semester-count"><strong>{counts.totalCount ?? '—'}</strong><span>次，本学期已完成</span></div>
      <div className="td-today-count"><span>今日 {completed}/{target}</span><span className="td-rounds" aria-hidden="true">{Array.from({ length: Math.min(10, Math.max(0, target)) }, (_, index) => <progress key={index} max="1" value={index < completed ? 1 : 0} />)}</span></div>
    </div>;
  }
  if (feature === 'ygdk' && counts) {
    return <p className="sunshine-inline-progress">学期 <strong>{counts.termCount ?? '—'}{counts.termTarget != null ? ` / ${counts.termTarget}` : ''}</strong><span>本周 <strong>{counts.weekCount ?? '—'} / {counts.weekTarget ?? 4}</strong></span></p>;
  }
  if (feature === 'boya' && counts?.categories) {
    return <div className="boya-inline-progress"><p>{binding.progress}</p><div className="boya-inline-categories">{counts.categories.map((category) => <span key={category.name} className={category.met ? 'met' : ''}>{category.name}<strong>{counts.totalCount == null ? '—' : category.net} / {category.required}</strong></span>)}</div></div>;
  }
  return binding.progress ? <p className="feature-progress">{binding.progress}</p> : null;
}
