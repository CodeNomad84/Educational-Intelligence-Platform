"""CSV import of questions for the Subject Teacher: upload -> dry-run preview (nothing written) -> confirm. The parsed rows live in
the session for 30 minutes and are re-validated against the database at confirm time. Imported questions are drafts."""
import time

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from dashboard.decorators import role_required
from schools import audit
from students.access import TEACHER

from . import csv_import
from .access import MODULE
from .models import Question
from .views import _parse_scope, _scope_choices, _topics

SESSION_KEY = 'exam_csv'
SESSION_SECONDS = 30 * 60


def _topic_map(school_id, subject):
    return {t.code: t.pk for t in _topics(school_id, subject)}


def _stems(school_id, subject):
    return set(Question.objects.filter(school_id=school_id, subject=subject).values_list('stem', flat=True))


def _stored(request, user):
    data = request.session.get(SESSION_KEY)
    if not data or data.get('user') != user.pk or time.time() - data.get('ts', 0) > SESSION_SECONDS:
        request.session.pop(SESSION_KEY, None)
        return None
    pair = _parse_scope(user, f"{data['school']}:{data['subject']}")      # the scope is re-checked, never trusted from the session
    return (pair, data['rows']) if pair else None


@role_required(TEACHER, module=MODULE)
@require_http_methods(['GET', 'POST'])
def import_form(request):
    if request.method == 'POST':
        pair = _parse_scope(request.user, request.POST.get('scope', ''))
        upload = request.FILES.get('file')
        if pair is None or upload is None:
            messages.error(request, 'درس و فایل را انتخاب کنید.')
        elif upload.size > csv_import.MAX_BYTES:
            messages.error(request, 'اندازهٔ فایل بیش از حد مجاز است.')
        else:
            try:
                rows = csv_import.parse(upload.read(), _topic_map(*pair), _stems(*pair))
            except csv_import.BadFile as exc:
                messages.error(request, str(exc))
            else:
                request.session[SESSION_KEY] = {'user': request.user.pk, 'school': pair[0], 'subject': pair[1], 'ts': time.time(),
                                                'rows': [r.as_session() for r in rows]}
                return redirect('exams:import_preview')
    return render(request, 'exams/import_form.html', {'scopes': _scope_choices(request.user), 'header': csv_import.TEMPLATE_HEADER,
                                                      'max_rows': csv_import.MAX_ROWS})


@role_required(TEACHER, module=MODULE)
def import_template(request):
    response = HttpResponse(csv_import.template_csv(), content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="exam-questions-template.csv"'
    return response


def _revalidated(request):
    stored = _stored(request, request.user)
    if stored is None:
        return None, None
    pair, items = stored
    return pair, csv_import.rows_from_session(items, _topic_map(*pair), _stems(*pair))


@role_required(TEACHER, module=MODULE)
def import_preview(request):
    pair, rows = _revalidated(request)
    if rows is None:
        messages.error(request, 'فایلی برای پیش‌نمایش نیست؛ دوباره بارگذاری کنید.')
        return redirect('exams:import_form')
    good = sum(1 for r in rows if r.ok)
    return render(request, 'exams/import_preview.html', {'rows': rows, 'good': good, 'bad': len(rows) - good})


@role_required(TEACHER, module=MODULE)
@require_POST
def import_cancel(request):
    request.session.pop(SESSION_KEY, None)
    return redirect('exams:import_form')


@role_required(TEACHER, module=MODULE)
@require_POST
def import_confirm(request):
    pair, rows = _revalidated(request)
    if rows is None:
        messages.error(request, 'فایلی برای تأیید نیست؛ دوباره بارگذاری کنید.')
        return redirect('exams:import_form')
    created, failed = csv_import.apply(rows, school_id=pair[0], subject=pair[1], author=request.user)
    request.session.pop(SESSION_KEY, None)
    bad = sum(1 for r in rows if not r.ok)
    audit.record(request.user, audit.EXAM_CSV_IMPORT, school=pair[0], detail=f'c{created}e{bad}f{failed}')
    messages.success(request, f'{created} پرسش به‌صورت پیش‌نویس افزوده شد؛ ردیف خطادار: {bad}، ناموفق: {failed}. پیش‌نویس‌ها باید تأیید شوند.')
    return redirect('exams:teacher_home')
