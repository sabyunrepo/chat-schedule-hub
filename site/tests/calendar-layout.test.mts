import {strict as assert} from 'node:assert';
// @ts-ignore Native Node type stripping requires the extension.
import {monthCells,eventsForDay} from '../lib/calendar-layout.ts';
import type {Event} from '../lib/model';
const base:Event={id:'one',title:'test',kind:'personal',status:'confirmed',start:'2026-11-01',end:'2026-11-02',allDay:true,participants:[],evidence:[]};
assert.equal(monthCells('2026-11-01').length,42);
assert.equal(monthCells('2026-11-01')[0],'2026-10-26');
assert(monthCells('2028-02-01').includes('2028-02-29'));
assert.equal(monthCells('2027-02-01').length,28);
assert.equal(eventsForDay([base],'2026-11-01').length,1);
assert.equal(eventsForDay([base],'2026-11-02').length,0);
assert.equal(eventsForDay([{...base,end:null}],'2026-11-02').length,0);
const overnight={...base,allDay:false,start:'2026-11-01T23:00:00+09:00',end:'2026-11-02T01:00:00+09:00'};
assert.equal(eventsForDay([overnight],'2026-11-02').length,1);
assert.equal(eventsForDay([{...base,start:'2026-11-01T15:00:00Z',end:null,allDay:false}],'2026-11-02').length,1);
assert.equal(eventsForDay([{...base,status:'cancelled'},{...base,excluded:true}],'2026-11-01').length,0);
console.log('Calendar boundaries: 10 cases passed');
