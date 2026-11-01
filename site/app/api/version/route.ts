import {BUILD_ID} from '../../../lib/build-info';
export const dynamic='force-dynamic';
export function GET(){return Response.json({version:BUILD_ID},{headers:{'Cache-Control':'no-store, max-age=0','CDN-Cache-Control':'no-store','Cloudflare-CDN-Cache-Control':'no-store'}});}
