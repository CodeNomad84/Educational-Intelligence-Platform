"""Static text for the four sellable modules and the locked-module page. No school data on that page, by design."""
from django.http import Http404
from django.shortcuts import render

from django.contrib.auth.decorators import login_required

from schools.entitlements import BUILT, MODULES

MODULE_INFO = {
    'advisor_ai': ('دستیار مشاور هوشمند', 'دستیار هوشمند کارکنان برای پرسش دربارهٔ وضعیت مدرسه (فقط پیشنهادی؛ تصمیم با انسان است).'),
    'tutor_ai': ('دستیار مطالعه', 'راهنمای مطالعهٔ دانش‌آموز بر پایهٔ نمرات خود او.'),
    'exams': ('آزمون‌ها', 'آزمون‌های تمرینی تعاملی با بازخورد برای هر گزینه.'),
    'mission': ('انتخاب مأموریت‌محور', 'ثبت مشاهدهٔ توانمندی‌ها در فعالیت‌ها و پیشنهاد مسیرهای قابل‌بررسی (اولیه، اعتبارسنجی‌نشده و فقط پیشنهادی؛ تصمیم با انسان است).'),
}


def label(key):
    return MODULE_INFO[key][0]


@login_required
def module_info(request, key):
    """Reachable whether the module is on or locked; shows only static text (no school data)."""
    if key not in MODULES:
        raise Http404
    title, text = MODULE_INFO[key]
    return render(request, 'dashboard/module_info.html', {'key': key, 'title': title, 'text': text, 'built': key in BUILT})
