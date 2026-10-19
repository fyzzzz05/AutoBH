import test from 'node:test';
import assert from 'node:assert/strict';
import { featureState, personFeatureState, dashboardTotals } from '../src/dashboard-state.js';

test('person lights show enabled configuration even when shared worker is stopped', () => {
  const binding = { enabled: true };
  assert.equal(featureState(binding, { available: true, status: 'stopped' }).tone, 'stopped');
  assert.equal(personFeatureState(binding).tone, 'enabled');
  assert.equal(personFeatureState({ enabled: false }).tone, 'paused');
  assert.equal(personFeatureState(undefined).tone, 'unbound');
});

test('enabled binding needs an active worker to show running', () => {
  assert.equal(featureState({enabled:true},{available:true,status:'stopped'}).tone,'stopped');
  assert.equal(featureState({enabled:true},{available:true,status:'running'}).tone,'running');
  assert.equal(featureState({enabled:true},{available:true,status:'running',stop_requested:true}).tone,'stopping');
  assert.equal(featureState({enabled:false},{available:true,status:'running'}).tone,'paused');
});
test('global counts include all four bindings and distinguish unbound from paused', () => {
  const people=[{features:{class:{enabled:true},td:{enabled:false}}},{features:{ygdk:{enabled:true}}}];
  assert.deepEqual(dashboardTotals(people,{class:{available:true,status:'running'},ygdk:{available:true,status:'stopped'}}),{running:1,paused:1,unbound:5});
  assert.deepEqual(dashboardTotals(),{running:0,paused:0,unbound:0});
});
