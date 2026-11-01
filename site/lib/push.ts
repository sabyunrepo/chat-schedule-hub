import {z} from 'zod';
export function allowedPushEndpoint(endpoint:string){
 try{const u=new URL(endpoint);return u.protocol==='https:'&&!u.username&&!u.password&&!u.port&&!u.hash&&(
 u.hostname==='fcm.googleapis.com'||u.hostname==='web.push.apple.com'||u.hostname.endsWith('.push.apple.com')||u.hostname==='updates.push.services.mozilla.com'||u.hostname.endsWith('.push.services.mozilla.com')||u.hostname.endsWith('.notify.windows.com'));}catch{return false;}
}
export const subscription=z.object({endpoint:z.string().max(3000).refine(allowedPushEndpoint),expirationTime:z.number().nullable().optional(),keys:z.object({p256dh:z.string().regex(/^[A-Za-z0-9_-]{87}={0,2}$/),auth:z.string().regex(/^[A-Za-z0-9_-]{22}={0,2}$/)})});
