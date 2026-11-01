import type {Event} from './model';
// Date-only Calendar values are Seoul civil dates, with exclusive end dates.
export function instant(value:string){return Date.parse(/^\d{4}-\d{2}-\d{2}$/.test(value)?value+'T00:00:00+09:00':value)}
export function phase(e:Event,now:number):'past'|'upcoming'|'ongoing'|'undated'|'inactive'{
 if(e.status==='cancelled'||e.status==='completed')return 'inactive';
 if(!e.start)return 'undated';
 const start=instant(e.start);
 if(!Number.isFinite(start))return 'undated';
 if(start>now)return 'upcoming';
 const end=e.end?instant(e.end):e.allDay||/^\d{4}-\d{2}-\d{2}$/.test(e.start)?start+86400000:start;
 return end>now?'ongoing':'past';
}
