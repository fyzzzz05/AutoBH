import test from 'node:test';
import assert from 'node:assert/strict';
import { remainingTime, shortTime, tdStage } from '../src/td-status.js';

test('stage follows the actual entrance, exercise and exit phases', () => {
  assert.equal(tdStage({ activityState: 'checking', nextAction: 'entrance' }), 0);
  assert.equal(tdStage({ activityState: 'exercising', nextAction: 'exit' }), 1);
  assert.equal(tdStage({ activityState: 'checking', nextAction: 'exit' }), 2);
  assert.equal(tdStage({ activityState: 'retrying', nextAction: 'exit' }), 2);
  assert.equal(tdStage({ activityState: 'completed', nextAction: 'entrance' }), 3);
});

test('countdown never shows negative time or claims an action already happened', () => {
  const now = Date.parse('2026-10-16T15:30:00+08:00');
  assert.equal(remainingTime('2026-10-16T15:31:05+08:00', now), '01:05');
  assert.equal(remainingTime('2026-10-16T16:31:05+08:00', now), '1 小时 1 分');
  assert.equal(remainingTime('2026-10-16T15:29:00+08:00', now), '等待下一轮检查');
  assert.equal(remainingTime('invalid', now), '');
});

test('times use Beijing timezone and distinguish unavailable values', () => {
  assert.equal(shortTime('2026-10-16T07:30:00Z'), '15:30');
  assert.equal(shortTime(null), '暂无记录');
  assert.equal(shortTime('invalid'), '暂无记录');
});
