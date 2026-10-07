/* アニメモ！ Service Worker — オフライン起動（ネットワーク優先）とポスター画像キャッシュ */
const CORE_CACHE = "animemo-core-v4";
const IMG_CACHE = "animemo-img-v1";
// 中核アセット（オフラインでも起動できるよう install 時にプリキャッシュ）
const CORE = [
  "./",
  "./index.html",
  "./anime-data.js",
  "./manifest.webmanifest",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/icon-maskable-512.png",
  "./icons/apple-touch-icon.png",
];

self.addEventListener("install", (e) => {
  e.waitUntil(
    caches.open(CORE_CACHE).then((c) => c.addAll(CORE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CORE_CACHE && k !== IMG_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // 同一オリジンの中核アセット: ネットワーク優先（更新を1回目の読み込みから反映する）。
  // cache:"no-cache" でブラウザのHTTPキャッシュ(GitHub Pagesは10分)も再検証させ、
  // 変更が無ければ 304 で軽く済む。キャッシュはオフライン時のフォールバックにだけ使う。
  if (url.origin === self.location.origin) {
    e.respondWith(
      fetch(req, { cache: "no-cache" })
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CORE_CACHE).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match("./index.html")))
    );
    return;
  }

  // 外部画像（AniList CDN のポスター等）: stale-while-revalidate
  if (req.destination === "image") {
    e.respondWith(
      caches.open(IMG_CACHE).then(async (c) => {
        const hit = await c.match(req);
        const net = fetch(req)
          .then((res) => { if (res && res.ok) c.put(req, res.clone()); return res; })
          .catch(() => hit);
        return hit || net;
      })
    );
  }
});
