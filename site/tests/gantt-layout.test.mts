import {strict as assert} from 'node:assert';
// @ts-ignore Node's native type stripping requires the .ts extension.
import {layoutEvents} from '../lib/gantt-layout.ts';
const make=(id:string,day:number,title='긴 일정 이름이 잘리지 않고 표시됩니다')=>({id,title,kind:'work',status:'confirmed',participants:[],evidence:[],start:`2026-11-0${day}T09:00:00+09:00`,end:`2026-11-0${day}T10:00:00+09:00`});
const r=layoutEvents([make('a',1),make('b',1),make('c',5)] as any,Date.parse('2026-11-01T00:00:00+09:00'),7);
assert.notEqual(r.items[0].top,r.items[1].top);assert.equal(r.items[0].top,r.items[2].top);
for(const i of r.items){assert.ok(i.labelWidth>=200);assert.ok(i.barWidth<i.labelWidth);assert.ok(i.labelLeft+i.labelWidth<=840)}
console.log('Gantt label packing passed');
