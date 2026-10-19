const DAY_MS = 86400000;
export const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const shanghai = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
});
export function localParts(value) {
  return Object.fromEntries(shanghai.formatToParts(new Date(value)).map(({ type, value }) => [type, value]));
}
export function localDay(value) {
  const p = localParts(value);
  return `${p.year}-${p.month}-${p.day}`;
}
export function addDays(day, count) {
  return new Date(Date.parse(`${day}T00:00:00Z`) + count * DAY_MS).toISOString().slice(0, 10);
}
function mondayFor(day) {
  const weekday = new Date(`${day}T00:00:00Z`).getUTCDay();
  return addDays(day, -((weekday + 6) % 7));
}
export function clock(minutes) {
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(Math.round(minutes % 60)).padStart(2, '0')}`;
}
export function attendanceState(attendance, start, end, now) {
  if (attendance === '正常出勤') return { tone: 'attended', label: '正常出勤' };
  if (attendance === '迟到签到') return { tone: 'late', label: '迟到签到' };
  if (attendance !== '未签到') return { tone: 'neutral', label: attendance || '状态未知' };
  if (start > now) return { tone: 'upcoming', label: '待上课' };
  if (end >= now) return { tone: 'upcoming', label: '待签到' };
  return { tone: 'missed', label: '未签到' };
}

// Backward compatibility: a running older GUI server still returns native CLI text.
// Convert it once at the view boundary; never display timestamp columns as a <pre>.
export function normalizeTimetable(detail, fallbackNow = new Date().toISOString()) {
  let sessions = detail.sessions;
  let loginMode = detail.loginMode;
  if (!Array.isArray(sessions)) {
    sessions = [];
    for (const line of (detail.text || '').split('\n')) {
      const match = line.match(/^(.*?)\s+(\d{4}-\d{2}-\d{2}T\S+)\s+(\d{4}-\d{2}-\d{2}T\S+)\s+(\S+)\s*$/);
      if (match) sessions.push({ key: `${sessions.length}`, courseName: match[1].trim(), startTime: match[2], endTime: match[3], attendance: match[4] });
    }
    loginMode = detail.text?.match(/登录方式[：:]\s*(\S+)/)?.[1];
    if (!sessions.length && !/课程名\s+开始\s+结束/.test(detail.text || '')) {
      return { error: detail.text || '暂时无法读取课表，请稍后重试。' };
    }
  }
  const now = Date.parse(detail.now || fallbackNow);
  const weekStart = detail.weekStart || mondayFor(sessions.length ? localDay(sessions[0].startTime) : localDay(now));
  const days = WEEKDAYS.map((label, index) => ({ key: addDays(weekStart, index), label, events: [] }));
  const validSessions = sessions.filter((row) => Number.isFinite(Date.parse(row.startTime)) && Number.isFinite(Date.parse(row.endTime)) && Date.parse(row.endTime) > Date.parse(row.startTime));
  for (const [index, row] of validSessions.entries()) {
    const start = Date.parse(row.startTime);
    const end = Date.parse(row.endTime);
    const state = attendanceState(row.attendance, start, end, now);
    for (const day of days) {
      const dayStart = Date.parse(`${day.key}T00:00:00+08:00`);
      const clippedStart = Math.max(start, dayStart);
      const clippedEnd = Math.min(end, dayStart + DAY_MS);
      if (clippedEnd <= clippedStart) continue;
      day.events.push({ ...row, ...state, id: `${row.key ?? row.scheduleId ?? index}-${day.key}-${index}`, name: row.courseName || '未命名课程',
        startMinute: (clippedStart - dayStart) / 60000, endMinute: (clippedEnd - dayStart) / 60000 });
    }
  }
  for (const day of days) day.events = layoutOverlaps(day.events);
  const events = days.flatMap((day) => day.events);
  const startHour = Math.floor(Math.min(480, ...events.map((e) => e.startMinute)) / 60);
  const endHour = Math.ceil(Math.max(1260, ...events.map((e) => e.endMinute)) / 60);
  return { days, weekStart, weekEnd: addDays(weekStart, 6), today: localDay(now),
    count: validSessions.filter((row) => Date.parse(row.startTime) < Date.parse(`${addDays(weekStart, 7)}T00:00:00+08:00`) && Date.parse(row.endTime) > Date.parse(`${weekStart}T00:00:00+08:00`)).length,
    startHour, endHour, loginMode };
}

export function layoutOverlaps(events) {
  const sorted = events.map((e) => ({ ...e })).sort((a, b) => a.startMinute - b.startMinute || a.endMinute - b.endMinute);
  let cluster = [];
  let clusterEnd = -1;
  function finish() {
    const laneEnds = [];
    for (const event of cluster) {
      let lane = laneEnds.findIndex((end) => end <= event.startMinute);
      if (lane < 0) lane = laneEnds.length;
      laneEnds[lane] = event.endMinute;
      event.lane = lane;
    }
    for (const event of cluster) event.lanes = laneEnds.length;
  }
  for (const event of sorted) {
    if (event.startMinute >= clusterEnd) { finish(); cluster = []; clusterEnd = -1; }
    cluster.push(event);
    clusterEnd = Math.max(clusterEnd, event.endMinute);
  }
  finish();
  return sorted;
}
