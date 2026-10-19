import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeTimetable, layoutOverlaps, attendanceState, clock } from '../src/timetable.js';

const now = '2026-10-15T12:00:00+08:00';
const session = (overrides = {}) => ({ key: 'a', courseName: '智能交通控制',
  startTime: '2026-10-15T14:00:00+08:00', endTime: '2026-10-15T15:35:00+08:00', attendance: '未签到', ...overrides });

test('native CLI text becomes a Monday–Sunday calendar without losing course names', () => {
  const table = normalizeTimetable({ text: '登录方式: direct\n课程名\t开始\t结束\t签到状态\nAI 赋能英语实务\t2026-10-12T08:00:00+08:00\t2026-10-12T09:35:00+08:00\t正常出勤' }, now);
  assert.equal(table.weekStart, '2026-10-12');
  assert.equal(table.weekEnd, '2026-10-18');
  assert.equal(table.days.length, 7);
  assert.equal(table.days[0].events[0].name, 'AI 赋能英语实务');
  assert.equal(table.days[0].events[0].startMinute, 480);
  assert.equal(table.loginMode, 'direct');
});

test('future unsigned classes are pending, past unsigned classes retain their actual status', () => {
  const time = Date.parse(now);
  assert.equal(attendanceState('未签到', time + 1000, time + 2000, time).label, '待上课');
  assert.equal(attendanceState('未签到', time - 1000, time + 2000, time).label, '待签到');
  assert.equal(attendanceState('未签到', time - 2000, time - 1000, time).label, '未签到');
  assert.equal(attendanceState('正常出勤', time - 2000, time - 1000, time).tone, 'attended');
  assert.equal(attendanceState('迟到签到', time - 2000, time - 1000, time).tone, 'late');
});

test('overlapping classes have separate lanes while adjacent classes do not collide', () => {
  const result = layoutOverlaps([{ startMinute: 480, endMinute: 600 }, { startMinute: 500, endMinute: 550 },
    { startMinute: 550, endMinute: 620 }, { startMinute: 620, endMinute: 700 }]);
  assert.deepEqual(result.map((event) => [event.lane, event.lanes]), [[0, 2], [1, 2], [1, 2], [0, 1]]);
});

test('midnight-spanning classes split across local calendar dates', () => {
  const table = normalizeTimetable({ now, weekStart: '2026-10-12', sessions: [session({
    startTime: '2026-10-15T15:30:00Z', endTime: '2026-10-15T16:30:00Z',
  })] });
  assert.equal(table.days[3].events[0].startMinute, 1410);
  assert.equal(table.days[3].events[0].endMinute, 1440);
  assert.equal(table.days[4].events[0].startMinute, 0);
  assert.equal(table.days[4].events[0].endMinute, 30);
  assert.equal(clock(1440), '24:00');
  assert.equal(table.count, 1);
});

test('Shanghai timezone determines day placement and excludes courses outside the week', () => {
  const table = normalizeTimetable({ now, weekStart: '2026-10-12', sessions: [session(), session({
    key: 'next-week', startTime: '2026-10-18T23:30:00Z', endTime: '2026-10-19T01:00:00Z',
  })] });
  assert.equal(table.today, '2026-10-15');
  assert.equal(table.count, 1);
  assert.equal(table.days[3].events.length, 1);
  assert.equal(table.days[6].events.length, 0);
});

test('empty calendars remain distinct from failed login output', () => {
  assert.equal(normalizeTimetable({ sessions: [], now }).count, 0);
  assert.equal(normalizeTimetable({ text: '登录方式: direct\n课程名\t开始\t结束\t签到状态' }, now).count, 0);
  assert.match(normalizeTimetable({ text: '登录失败：请检查账号密码' }, now).error, /登录失败/);
});
