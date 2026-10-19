import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeAppearance, resolvedAppearance, applyAppearance } from '../src/appearance.js';

test('explicit appearance ignores OS changes, system follows both transitions', () => {
  for (const systemDark of [false, true, false]) {
    assert.equal(resolvedAppearance('system', systemDark), systemDark ? 'dark' : 'light');
    assert.equal(resolvedAppearance('dark', systemDark), 'dark');
    assert.equal(resolvedAppearance('light', systemDark), 'light');
  }
  assert.equal(normalizeAppearance('__AUTOBH_APPEARANCE__'), 'system');
});

test('appearance updates DOM, browser chrome and validated native preference together', () => {
  let color; const messages = [];
  const doc = { documentElement: { dataset: {} }, querySelector: () => ({ setAttribute: (_, value) => { color = value; } }) };
  const native = { messageHandlers: { appearance: { postMessage: (value) => messages.push(value) } } };
  applyAppearance('dark', false, doc, native);
  assert.equal(doc.documentElement.dataset.appearance, 'dark');
  assert.equal(color, '#15161e');
  applyAppearance('system', false, doc, native);
  assert.equal(color, '#f4f4f7');
  applyAppearance('invalid', true, doc, native);
  assert.equal(doc.documentElement.dataset.appearance, 'system');
  assert.deepEqual(messages, ['dark', 'system', 'system']);
});
