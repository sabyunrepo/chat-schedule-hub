import {json,user} from '../../../lib/http';
import {readData} from '../../../lib/sync-records';
export async function GET(){try{return json(await readData(await user())||{data:null});}catch{return json({error:'일정을 불러오지 못했습니다.'},401);}}
