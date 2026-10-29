const CACHE_NAME = 'elektrik-takip-v26';
const SHELL = ['./', './index.html', './manifest.json'];

self.addEventListener('install', (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL)).catch(()=>{}));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
    ))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (e) => {
  // Sadece GET ve kendi origin'imizdeki (http/https) istekleri ele al.
  // Tarayıcı uzantılarının (chrome-extension://) veya farklı origin'lerin
  // (ör. Google giriş akışı, gapi.js) isteklerine karışma — bunlar servis
  // worker'ımızın işi değil ve müdahale edilirse gereksiz konsol hatalarına
  // ve olası girişim çakışmalarına yol açabilir.
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin) return;

  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});
