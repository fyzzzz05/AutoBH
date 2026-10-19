import test from 'node:test';
import assert from 'node:assert/strict';
import { filterPeople } from '../src/people.js';

const people = [
  {username:'1',name:'张三',group:'沙河',features:{td:{enabled:true}}},
  {username:'2',name:'李四',group:'学院路',features:{class:{enabled:false},td:{enabled:false},boya:{enabled:false},ygdk:{enabled:false}}},
  {username:'3',name:'Alice',group:'',features:{class:{enabled:true},td:{enabled:true},boya:{enabled:true},ygdk:{enabled:true}}},
];
test('running filter requires an enabled account and a running non-stopping worker', () => {
  assert.deepEqual(filterPeople(people,'','running',{td:{status:'running'}}).map(p=>p.username),['1','3']);
  assert.deepEqual(filterPeople(people,'','running',{td:{status:'running',stop_requested:true}}),[]);
  assert.deepEqual(filterPeople(people,'','running',{td:{status:'stopped'}}),[]);
  assert.deepEqual(filterPeople(people,'','running',{class:{status:'native-running'}}).map(p=>p.username),['3']);
});
test('unbound filter includes people missing at least one of the four accounts', () => {
  assert.deepEqual(filterPeople(people,'','unbound',{}).map(p=>p.username),['1']);
});
test('search combines with status and supports names, IDs, groups and case-insensitive text', () => {
  assert.deepEqual(filterPeople(people,' 沙河 ','unbound',{}).map(p=>p.username),['1']);
  assert.deepEqual(filterPeople(people,'ALICE','all',{}).map(p=>p.username),['3']);
  assert.deepEqual(filterPeople(people,'2','all',{}).map(p=>p.username),['2']);
  assert.deepEqual(filterPeople(people,'学院路','running',{td:{status:'running'}}),[]);
});
