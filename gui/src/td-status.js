export function tdStage(detail) {
  if (detail.activityState === 'completed') return 3;
  if (detail.nextAction === 'exit') return detail.activityState === 'exercising' ? 1 : 2;
  return 0;
}

export function shortTime(value, date = false) {
  if (!value) return '暂无记录';
  const time = new Date(value);
  if (Number.isNaN(time.getTime())) return '暂无记录';
  return time.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', ...(date ? { month: '2-digit', day: '2-digit' } : {}), hour: '2-digit', minute: '2-digit', hour12: false });
}

export function remainingTime(value, now) {
  const seconds = Math.max(0, Math.ceil((new Date(value).getTime() - now) / 1000));
  if (!Number.isFinite(seconds)) return '';
  if (!seconds) return '等待下一轮检查';
  const minutes = Math.floor(seconds / 60);
  return minutes >= 60 ? `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分` : `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}
