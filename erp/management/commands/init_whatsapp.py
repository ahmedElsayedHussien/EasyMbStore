# -*- coding: utf-8 -*-
"""
أمر Django مخصص: python manage.py init_whatsapp
================================================
يفتح نافذة Chrome مع WhatsApp Web لمسح QR Code وحفظ الجلسة.

الاستخدام:
    python manage.py init_whatsapp

الخطوات:
    1. شغّل هذا الأمر
    2. ستفتح نافذة Chrome تلقائياً مع WhatsApp Web
    3. امسح الـ QR Code من هاتف المحل
    4. انتظر حتى تظهر الرسالة "تم حفظ الجلسة بنجاح!"
    5. يمكنك إغلاق النافذة
"""

import os
import time
from django.core.management.base import BaseCommand
from django.conf import settings as django_settings


class Command(BaseCommand):
    help = 'تهيئة جلسة واتساب ويب عبر مسح QR Code'

    def handle(self, *args, **options):
        session_dir = os.path.join(django_settings.MEDIA_ROOT, 'whatsapp_session')
        os.makedirs(session_dir, exist_ok=True)

        self.stdout.write(self.style.WARNING(
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "  تهيئة جلسة واتساب ويب\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  مجلد الجلسة: {session_dir}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        ))

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.by import By
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            self.stderr.write(self.style.ERROR(
                "خطأ: selenium أو webdriver-manager غير مثبت.\n"
                "شغّل: pip install selenium webdriver-manager"
            ))
            return

        chrome_options = Options()
        # ⚠️ لا نضع --headless هنا حتى تظهر نافذة QR Code للمستخدم
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument(f"--user-data-dir={session_dir}")
        chrome_options.add_argument("--window-size=1280,800")
        chrome_options.add_argument("--start-maximized")

        self.stdout.write("⏳ جاري فتح Chrome وتحميل واتساب ويب...")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        try:
            driver.get("https://web.whatsapp.com")

            self.stdout.write(self.style.SUCCESS(
                "\n✅ تم فتح Chrome!\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "  الخطوات:\n"
                "  1. افتح واتساب على هاتف المحل\n"
                "  2. اختر: الإعدادات ← الأجهزة المرتبطة ← ربط جهاز\n"
                "  3. امسح الـ QR Code الظاهر في نافذة Chrome\n"
                "  4. انتظر حتى تظهر محادثاتك\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            ))

            self.stdout.write("⏳ في انتظار مسح QR Code... (لديك 5 دقائق)")

            # انتظار حتى يظهر عنصر يدل على تسجيل الدخول الناجح
            wait = WebDriverWait(driver, 300)  # 5 دقائق
            wait.until(
                EC.presence_of_element_located(
                    (By.XPATH, '//div[@data-testid="chat-list-search"]')
                )
            )

            self.stdout.write(self.style.SUCCESS(
                "\n🎉 تم تسجيل الدخول بنجاح!\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"  الجلسة محفوظة في: {session_dir}\n"
                "  يمكنك الآن تفعيل الإشعارات من صفحة الإعدادات.\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            ))

            # انتظار 3 ثواني قبل الإغلاق للتأكد من حفظ الجلسة
            time.sleep(3)

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"\n❌ خطأ: {e}"))
        finally:
            driver.quit()
            self.stdout.write("✅ تم إغلاق Chrome. الجلسة محفوظة.")
