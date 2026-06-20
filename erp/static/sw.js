/*
 * EasyMB Store — Minimal PWA Service Worker
 * ==========================================
 * هذا الـ Service Worker مخصص فقط لتمكين تثبيت التطبيق على الهاتف
 * بدون أي حفظ للكاش — كل الطلبات تذهب مباشرة للشبكة
 * No caching — Network-only strategy
 */

const APP_VERSION = 'v1.0.0';

// ── Install: تنصيب فوري بدون انتظار ──
self.addEventListener('install', (event) => {
    console.log(`[EasyMB SW ${APP_VERSION}] Installing...`);
    // تخطي مرحلة الانتظار والتفعيل فوراً
    self.skipWaiting();
});

// ── Activate: السيطرة على كل الصفحات فوراً ──
self.addEventListener('activate', (event) => {
    console.log(`[EasyMB SW ${APP_VERSION}] Activated.`);
    event.waitUntil(
        // السيطرة على كل الصفحات المفتوحة فوراً
        clients.claim()
    );
});

// ── Fetch: إعادة توجيه كل الطلبات للشبكة مباشرة (بدون كاش) ──
self.addEventListener('fetch', (event) => {
    // Network-only: لا كاش على الإطلاق
    event.respondWith(
        fetch(event.request).catch(() => {
            // في حالة عدم وجود إنترنت، إرسال صفحة خطأ بسيطة
            if (event.request.destination === 'document') {
                return new Response(
                    `<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EasyMB — لا يوجد اتصال</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', sans-serif;
    background: #0d1117;
    color: #c9d1d9;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    text-align: center;
    padding: 20px;
  }
  .card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 16px;
    padding: 40px 32px;
    max-width: 360px;
    width: 100%;
  }
  .icon { font-size: 64px; margin-bottom: 20px; }
  h1 { color: #f0f6fc; font-size: 1.4rem; margin-bottom: 12px; }
  p { color: #8b949e; font-size: 0.95rem; line-height: 1.6; margin-bottom: 24px; }
  button {
    background: linear-gradient(135deg, #1d4ed8, #1e40af);
    color: white;
    border: none;
    border-radius: 8px;
    padding: 12px 28px;
    font-size: 1rem;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.2s;
  }
  button:hover { background: linear-gradient(135deg, #2563eb, #1d4ed8); }
</style>
</head>
<body>
  <div class="card">
    <div class="icon">📡</div>
    <h1>لا يوجد اتصال بالإنترنت</h1>
    <p>يرجى التحقق من اتصالك بالشبكة ثم المحاولة مجدداً.</p>
    <button onclick="window.location.reload()">🔄 إعادة المحاولة</button>
  </div>
</body>
</html>`,
                    { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
                );
            }
        })
    );
});
