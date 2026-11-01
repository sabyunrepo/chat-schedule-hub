import {strict as assert} from 'node:assert';
// @ts-ignore Node's native type stripping requires the .ts extension.
import {phase} from '../lib/event-time.ts';
const now=Date.parse('2026-11-01T12:00:00+09:00');
const base={id:'test',title:'test',kind:'personal',status:'confirmed',participants:[],evidence:[],start:'2026-11-01T10:00:00+09:00',end:'2026-11-01T11:00:00+09:00'} as const;
const check=(patch:object,expected:string)=>assert.equal(phase({...base,...patch} as any,now),expected);
check({},'past');check({start:'2026-11-01T13:00:00+09:00'},'upcoming');
check({end:'2026-11-01T13:00:00+09:00'},'ongoing');check({end:'2026-11-01T12:00:00+09:00'},'past');
check({start:'2026-10-31',end:'2026-11-01',allDay:true,endExclusive:true},'past');
check({start:'2026-11-01',end:'2026-11-02',allDay:true,endExclusive:true},'ongoing');
check({start:null,end:null},'undated');check({status:'cancelled',start:'2026-11-02'},'inactive');check({status:'completed'},'inactive');
console.log('Time boundaries: 9 cases passed');
