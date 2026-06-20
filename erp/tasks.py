# -*- coding: utf-8 -*-
"""
erp/tasks.py — محرك إرسال إشعارات الواتساب (Anti-Ban Engine)
=================================================================
يُنفَّذ هذا الملف بواسطة Django Q2 Worker في الخلفية.

استراتيجيات Anti-Ban المطبقة:
  1. Randomized Delay     — تأخير عشوائي قبل الإرسال الفعلي
  2. Text Spinning        — رسائل ديناميكية فريدة (اسم العميل، الموديل، الوقت، الـ ID)
  3. Retry Logic          — إعادة المحاولة تلقائياً عند الفشل (عبر Django Q2)
  4. Status Tracking      — تسجيل كل محاولة في NotificationLog

كيفية الربط بالواتساب (مرحلتان):
  ─────────────────────────────────────────────────────────
  المرحلة أ — تجهيز السيرفر (مرة واحدة فقط):
    1. تثبيت ChromeDriver المناسب لنسخة Chrome لديك
    2. تشغيل: python manage.py init_whatsapp
       (أمر مخصص سيفتح نافذة Chrome مع WhatsApp Web)
    3. مسح QR Code من هاتف المحل
    4. إغلاق النافذة — الجلسة محفوظة في مجلد: media/whatsapp_session/

  المرحلة ب — تشغيل Worker (في terminal منفصل دائماً):
    python manage.py qcluster
  ─────────────────────────────────────────────────────────
"""

import time
import random
import logging
from django.utils import timezone
from erp.models import RepairTicket, NotificationLog, NotificationSettings

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
#  الدالة الرئيسية — يستدعيها Django Q2 Worker
# ──────────────────────────────────────────────────────────

def send_whatsapp_notification(log_id: int):
    """
    المهمة الخلفية الرئيسية.
    تستقبل ID سجل إشعار (NotificationLog) وتُرسل الرسالة عبر واتساب.

    يستدعيها views.py هكذا:
        from django_q.tasks import async_task
        log = NotificationLog.objects.create(...)
        async_task('erp.tasks.send_whatsapp_notification', log_id=log.id)
    """
    try:
        log = NotificationLog.objects.select_related('ticket', 'customer').get(id=log_id)
    except NotificationLog.DoesNotExist:
        logger.error(f"[WhatsApp] NotificationLog ID={log_id} غير موجود.")
        return

    settings = NotificationSettings.get_settings()

    # ── التحقق من الإعدادات ──────────────────────────────
    if not settings.whatsapp_enabled:
        log.status = 'skipped'
        log.error_message = "الواتساب غير مفعّل في الإعدادات."
        log.save(update_fields=['status', 'error_message'])
        logger.info(f"[WhatsApp] تم تخطي الإرسال — الواتساب مغلق. (Log #{log_id})")
        return

    if not settings.sender_phone:
        log.status = 'failed'
        log.error_message = "لم يتم تحديد رقم الواتساب المرسل في الإعدادات."
        log.save(update_fields=['status', 'error_message'])
        logger.error(f"[WhatsApp] فشل — لا يوجد sender_phone في الإعدادات.")
        return

    # ── Anti-Ban: تأخير عشوائي ───────────────────────────
    delay = random.randint(settings.delay_min_seconds, settings.delay_max_seconds)
    logger.info(f"[WhatsApp] انتظار {delay} ثانية قبل إرسال الرسالة لـ {log.customer.name}...")
    time.sleep(delay)

    # ── محاولة الإرسال الفعلي ────────────────────────────
    phone = _normalize_phone(log.customer.phone)
    message = log.message_body

    log.retry_count += 1
    log.save(update_fields=['retry_count'])

    try:
        _send_via_whatsapp_web(phone=phone, message=message, settings=settings)
        log.status = 'sent'
        log.error_message = None
        log.save(update_fields=['status', 'error_message'])
        logger.info(f"[WhatsApp] ✅ تم إرسال رسالة للعميل {log.customer.name} ({phone})")

    except Exception as exc:
        log.status = 'failed'
        log.error_message = str(exc)
        log.save(update_fields=['status', 'error_message'])
        logger.error(f"[WhatsApp] ❌ فشل الإرسال للعميل {log.customer.name}: {exc}")
        # Django Q2 سيعيد المحاولة تلقائياً إذا كان retry مضبوطاً في settings.py
        raise  # إعادة رفع الاستثناء لتفعيل Retry في Q2


# ──────────────────────────────────────────────────────────
#  دالة مساعدة: تطبيع رقم الهاتف
# ──────────────────────────────────────────────────────────

def _normalize_phone(phone: str) -> str:
    """
    يحول أي صيغة رقم هاتف مصري إلى الصيغة الدولية.
    مثال: 01012345678 → +201012345678
    """
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("0") and not phone.startswith("00"):
        phone = "+2" + phone
    elif not phone.startswith("+"):
        phone = "+" + phone
    return phone


# ──────────────────────────────────────────────────────────
#  محرك الإرسال عبر WhatsApp Web (Selenium)
# ──────────────────────────────────────────────────────────

def _send_via_whatsapp_web(phone: str, message: str, settings) -> None:
    """
    يُرسل رسالة واتساب عبر Selenium + ChromeDriver.

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    طريقة الربط خطوة بخطوة:
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    1. تأكد أن Google Chrome مثبت على السيرفر.

    2. شغّل أمر تهيئة الجلسة (مرة واحدة فقط):
         python manage.py init_whatsapp
       سيفتح نافذة Chrome مع WhatsApp Web.

    3. امسح QR Code من هاتف المحل (الخط اللي هترسل منه).
       ⚠️ المهم: استخدم خطاً قديماً عليه محادثات طبيعية،
          وليس خطاً جديداً مباشرة.

    4. بعد ظهور واجهة الواتساب، أغلق نافذة Chrome.
       الجلسة ستنحفظ في: media/whatsapp_session/

    5. من الآن، كلما أرسل النظام رسالة، سيفتح Chrome
       في الخلفية (headless) ويُرسل بدون أي تدخل منك.
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """
    import os
    from django.conf import settings as django_settings

    # مسار حفظ جلسة الواتساب (يجب أن يبقى ثابتاً)
    session_dir = os.path.join(django_settings.MEDIA_ROOT, "whatsapp_session")
    os.makedirs(session_dir, exist_ok=True)

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        raise RuntimeError(
            "مكتبة selenium أو webdriver_manager غير مثبتة. "
            "شغّل: pip install selenium webdriver-manager"
        )

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")          # تشغيل في الخلفية بدون نافذة
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument(f"--user-data-dir={session_dir}")  # حفظ الجلسة
    chrome_options.add_argument("--window-size=1280,800")

    driver = None
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # فتح WhatsApp Web مباشرة على رقم العميل
        wa_url = f"https://web.whatsapp.com/send?phone={phone}&text="
        driver.get(wa_url)

        # انتظار تحميل صندوق الرسالة (max 30 ثانية)
        wait = WebDriverWait(driver, 30)
        msg_box = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')
            )
        )

        # Anti-Ban: تأخير إضافي صغير قبل الكتابة لمحاكاة السلوك البشري
        time.sleep(random.uniform(1.5, 3.0))

        # كتابة الرسالة وإرسالها
        msg_box.send_keys(message)
        time.sleep(random.uniform(0.5, 1.5))
        msg_box.send_keys(Keys.ENTER)

        # انتظار لحظة للتأكد من الإرسال
        time.sleep(random.uniform(2.0, 4.0))

    finally:
        if driver:
            driver.quit()
