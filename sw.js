/* 立橙数据中心 · 离线兜底缓存
   目标：联网正常时永远拿最新；断网/超时则用最近一次成功打开的页面。
   注意：只处理同源 GET，实时接口与安装包一律放行。 */
const PREFIX = 'lcdc-page-';
const VER    = 'v1';
const CACHE  = PREFIX + VER;
const CORE   = ['/', '/music'];
const NET_TIMEOUT = 4500;

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE).then((c) =>
    Promise.allSettled(CORE.map((u) => c.add(new Request(u, { cache: 'reload' })))
  )));
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k.startsWith(PREFIX) && k !== CACHE).map((k) => caches.delete(k)));
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;          // 音乐/识别等实时接口
  if (url.pathname.startsWith('/apk/')) return;          // 安装包下载
  if (url.pathname === '/sw.js' || url.pathname === '/version.json') return; // 更新探测不缓存

  if (req.mode === 'navigate') { e.respondWith(navFetch(req)); return; }
  e.respondWith(cacheFirst(req));
});

function timeoutFetch(req, ms) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error('timeout')), ms);
    fetch(req).then((r) => { clearTimeout(t); resolve(r); }, (err) => { clearTimeout(t); reject(err); });
  });
}

async function navFetch(req) {
  const cache = await caches.open(CACHE);
  // 有缓存才限时抢网络；首次访问没有兜底，就必须等它下完，避免慢网被误判成离线
  const fallbackHit = (await cache.match(req, { ignoreSearch: true })) || (await cache.match('/'));
  const budget = fallbackHit ? NET_TIMEOUT : 25000;
  try {
    const fresh = await timeoutFetch(req, budget);
    if (fresh && fresh.ok && fresh.status === 200) {
      try { await cache.put(req, fresh.clone()); } catch (e) {}
      try { await cache.put(new Request(new URL('/', self.location.origin)), fresh.clone()); } catch (e) {}
      return fresh;
    }
    throw new Error('bad status ' + (fresh && fresh.status));
  } catch (err) {
    const hit = await cache.match(req, { ignoreSearch: true });
    if (hit) return hit;
    const root = await cache.match('/');
    if (root) return root;
    return new Response('<h1>离线且无缓存</h1><p>请联网打开一次立橙数据中心。</p>',
      { status: 503, headers: { 'content-type': 'text/html; charset=utf-8' } });
  }
}

async function cacheFirst(req) {
  const cache = await caches.open(CACHE);
  const hit = await cache.match(req, { ignoreSearch: true });
  if (hit) {
    fetch(req).then((r) => { if (r && r.ok && r.status === 200) cache.put(req, r.clone()); }).catch(() => {});
    return hit;
  }
  try {
    const r = await fetch(req);
    if (r && r.ok && r.status === 200) { try { await cache.put(req, r.clone()); } catch (e) {} }
    return r;
  } catch (e) {
    return new Response('', { status: 504 });
  }
}
