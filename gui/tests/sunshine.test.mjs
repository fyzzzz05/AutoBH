import test from 'node:test';
import assert from 'node:assert/strict';
import { spacedRecords, remainingThisWeek, automaticBatchRecords, unfinishedRecords } from '../src/sunshine.js';

test('subsequent records preserve duration and leave ten minutes between activities', () => {
  const rows = spacedRecords('2026-10-19T05:55', '2026-10-19T06:25', 4);
  assert.deepEqual(rows.map(row => row.startTime), ['2026-10-19T05:55', '2026-10-19T06:35', '2026-10-19T07:15', '2026-10-19T07:55']);
  assert.equal(rows[3].endTime, '2026-10-19T08:25');
  assert.throws(() => spacedRecords('', '', 4));
});
test('batch fills only missing weekly rounds and distinguishes unknown data', () => {
  assert.equal(remainingThisWeek(0), 4);
  assert.equal(remainingThisWeek(2), 2);
  assert.equal(remainingThisWeek(4), 0);
  assert.equal(remainingThisWeek(5), 0);
  assert.equal(remainingThisWeek(null), null);
});


test('auto-fill works backward from now with four completed nonoverlapping activities', () => {
  const now = new Date('2026-10-19T08:26:00+08:00');
  const rows = automaticBatchRecords(4, now);
  assert.deepEqual(rows.map(row => row.startTime), ['2026-10-19T05:55', '2026-10-19T06:35', '2026-10-19T07:15', '2026-10-19T07:55']);
  assert.equal(rows[3].endTime, '2026-10-19T08:25');
  assert.equal(unfinishedRecords(rows, now), 0);
});

test('weekly boundary cannot create last-week records; midnight ranges stay on one day', () => {
  assert.throws(() => automaticBatchRecords(4, new Date('2026-10-19T01:00:00+08:00')), /本周已过时间不足/);
  const now = new Date('2026-10-20T00:20:00+08:00');
  const rows = automaticBatchRecords(4, now);
  assert.equal(unfinishedRecords(rows, now), 0);
  assert.ok(rows.every(row => row.startTime.slice(0, 10) === row.endTime.slice(0, 10)));
  assert.ok(rows.every(row => row.startTime >= '2026-10-19'));
});

test('auto-fill respects Beijing time and the weekly gap count', () => {
  const rows = automaticBatchRecords(2, new Date('2026-10-19T00:26:00Z'));
  assert.equal(rows.length, 2);
  assert.equal(rows[1].endTime, '2026-10-19T08:25');
  for (const count of [0, 5, null, 2.5]) assert.throws(() => automaticBatchRecords(count));
});
