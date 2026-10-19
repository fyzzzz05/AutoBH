// Input and output use explicit Beijing local datetime strings.
export function spacedRecords(startTime, endTime, count) {
  const start = Date.parse(`${startTime}+08:00`);
  const end = Date.parse(`${endTime}+08:00`);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) throw new Error('请先填写第一段运动的开始和结束时间');
  const format = (value) => new Date(value + 8 * 3600000).toISOString().slice(0, 16);
  return Array.from({ length: count }, (_, index) => ({ startTime: format(start + index * (end - start + 10 * 60000)), endTime: format(end + index * (end - start + 10 * 60000)) }));
}
export function remainingThisWeek(count) {
  return count == null ? null : Math.min(4, Math.max(0, 4 - Number(count)));
}

// Draft times only: the user reviews actual activity information before submission.
export function automaticBatchRecords(count, now = new Date()) {
  if (!Number.isInteger(count) || count < 1 || count > 4) throw new Error('本周待完成次数无效，请先刷新');
  const stamp = new Date(now).getTime();
  if (!Number.isFinite(stamp)) throw new Error('当前时间无效');
  const minute = 60000, offset = 8 * 3600000, day = 86400000;
  const local = new Date(stamp + offset);
  const today = Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), local.getUTCDate()) - offset;
  const monday = today - ((local.getUTCDay() + 6) % 7) * day;
  const format = (value) => new Date(value + offset).toISOString().slice(0, 16);
  let end = Math.floor(stamp / minute) * minute - minute;
  const rows = [];
  for (let index = 0; index < count; index++) {
    let start = end - 30 * minute;
    if (format(start).slice(0, 10) !== format(end).slice(0, 10)) {
      const endLocal = new Date(end + offset);
      end = Date.UTC(endLocal.getUTCFullYear(), endLocal.getUTCMonth(), endLocal.getUTCDate()) - offset - minute;
      start = end - 30 * minute;
    }
    if (start < monday) throw new Error('本周已过时间不足，暂时无法生成全部时段，请稍后再试或手动填写');
    rows.push({ startTime: format(start), endTime: format(end) });
    end = start - 10 * minute;
  }
  return rows.reverse();
}

export function unfinishedRecords(records, now = new Date()) {
  return records.filter((row) => Date.parse(`${row.endTime}+08:00`) > new Date(now).getTime()).length;
}
