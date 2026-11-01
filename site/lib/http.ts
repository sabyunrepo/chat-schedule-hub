import {getChatGPTUser} from '../app/chatgpt-auth';
export async function user(){ const u=await getChatGPTUser(); if(!u)throw new Error('unauthorized'); return u.userId; }
export function json(data:unknown,status=200){return Response.json(data,{status,headers:{'Cache-Control':'no-store'}})}
export function sameOrigin(r:Request){return r.headers.get('origin')===new URL(r.url).origin;}
export async function body(r:Request){ const t=await r.text(); if(t.length>1000000)throw new Error('payload too large'); return JSON.parse(t); }
export async function hash(t:string){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(t)))].map(x=>x.toString(16).padStart(2,'0')).join('')}
