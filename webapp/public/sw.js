// Cache only the public app shell. Never persist API responses or credentials.
const CACHE='mapauto-shell-v1';
self.addEventListener('install',event=>{self.skipWaiting();});
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 if(url.origin!==self.location.origin||url.pathname.startsWith('/api')||event.request.method!=='GET')return;
 const shell=url.pathname==='/'||url.pathname==='/index.html'||url.pathname.startsWith('/assets/')||['/manifest.webmanifest','/icon.svg','/icon-192.png','/icon-512.png','/apple-touch-icon.png'].includes(url.pathname);
 if(!shell)return;
 event.respondWith(fetch(event.request).then(response=>{if(response.ok){const copy=response.clone();event.waitUntil(caches.open(CACHE).then(cache=>cache.put(event.request,copy)));}return response;}).catch(async()=>{const hit=await caches.match(event.request);return hit||new Response('Offline. Sambungkan internet untuk mengakses workspace.',{status:503,headers:{'Content-Type':'text/plain;charset=utf-8'}});}));
});
