"""P7-5 pages. Ask: Admin, Grade Lead, Teacher, Counselor with the ``advisor_ai`` module on. Manage documents and the AI setting: SchoolAdmin only.
Parent and Student never. The school is the user's own (never taken from the request without checking membership)."""
from django.contrib import messages
from django.core.cache import cache
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from dashboard.decorators import role_required
from schools import audit
from schools.entitlements import module_enabled, user_school_ids
from schools.models import School
from students.access import ADMIN, COUNSELOR, GRADE_LEAD, TEACHER, roles_for

from . import services
from .extract import MAX_BYTES, ExtractError
from .models import AssistantSettings, SchoolDocument

STAFF = (ADMIN, GRADE_LEAD, TEACHER, COUNSELOR)
MODULE = 'advisor_ai'
REASONS = {'bad_question': 'سؤال خالی یا بیش از ۵۰۰ نویسه است.',
           'screen': 'سؤال نباید نام یا شناسهٔ دانش‌آموز، شمارهٔ تلفن یا نشانی ایمیل داشته باشد.'}
UPLOAD_ERRORS = {'file_too_large': 'فایل بزرگ‌تر از حد مجاز است.', 'unsupported_type': 'فقط txt، md و docx پذیرفته می‌شود.',
                 'not_utf8': 'فایل متنی باید UTF-8 باشد.', 'empty': 'فایل متنی ندارد.', 'too_long': 'متن بیش از حد طولانی است.',
                 'not_docx': 'فایل docx معتبر نیست.'}
UPLOADS_PER_WINDOW, WINDOW = 10, 600


def _school(request, admin_only=False):
    """The caller's own school with the module on (``?school=`` only picks among the user's own schools)."""
    mine = sorted(s for s in user_school_ids(request.user) if module_enabled(s, MODULE))
    if admin_only:
        from students.access import school_ids_for_admin
        mine = [s for s in mine if s in school_ids_for_admin(request.user)]
    if not mine:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    wanted = request.GET.get('school') or request.POST.get('school') or ''
    chosen = int(wanted) if wanted.isdigit() and int(wanted) in mine else mine[0]
    return School.objects.get(pk=chosen)


@role_required(*STAFF, module=MODULE)
@require_http_methods(['GET', 'POST'])
def home(request):
    school = _school(request)
    context = {'school': school, 'is_admin': ADMIN in roles_for(request.user)}
    if request.method == 'POST':
        question = request.POST.get('question', '')
        context['question'] = question
        try:
            context['result'] = services.ask(request.user, school, question)
        except services.AskRefused as exc:
            messages.error(request, REASONS.get(exc.code, 'درخواست انجام نشد.'))
    cfg = AssistantSettings.objects.filter(school=school).first()
    context['ai_on'] = bool(cfg and cfg.ai_enabled)
    context['doc_count'] = SchoolDocument.objects.filter(school=school, is_active=True).count()
    return render(request, 'docqa/home.html', context)


@role_required(ADMIN, module=MODULE)
@require_http_methods(['GET', 'POST'])
def documents(request):
    school = _school(request, admin_only=True)
    if request.method == 'POST':
        upload = request.FILES.get('file')
        title = (request.POST.get('title') or '').strip()[:120]
        key = f'docqa-upload:{request.user.pk}'
        cache.add(key, 0, WINDOW)
        if cache.incr(key) > UPLOADS_PER_WINDOW:
            messages.error(request, 'تعداد بارگذاری‌ها بیش از حد مجاز است؛ چند دقیقه بعد دوباره تلاش کنید.')
        elif not request.POST.get('attest'):
            messages.error(request, 'باید تأیید کنید که سند دادهٔ شخصی دانش‌آموزان ندارد.')
        elif upload is None or not title:
            messages.error(request, 'عنوان و فایل لازم است.')
        else:
            try:
                doc = services.add_document(request.user, school.pk, title, upload.name, upload.read(MAX_BYTES + 1))
            except ExtractError as exc:
                messages.error(request, UPLOAD_ERRORS.get(exc.code, 'فایل پذیرفته نشد.'))
            except services.AskRefused as exc:
                messages.error(request, 'سند دادهٔ شخصی (شناسه، تلفن، ایمیل یا نام دانش‌آموز) دارد و پذیرفته نشد.')
            except IntegrityError:
                messages.error(request, 'سندی با این عنوان وجود دارد.')
            else:
                audit.record(request.user, audit.DOC_UPLOAD, doc, school=school.pk, detail=f'c{doc.chunks.count()}')
                messages.success(request, 'سند ثبت شد.')
        return redirect('docqa:documents')
    cfg = AssistantSettings.objects.filter(school=school).first()
    return render(request, 'docqa/documents.html', {'school': school, 'docs': SchoolDocument.objects.filter(school=school),
                                                    'ai_on': bool(cfg and cfg.ai_enabled)})


@role_required(ADMIN, module=MODULE)
@require_POST
def document_action(request, pk):
    school = _school(request, admin_only=True)
    doc = get_object_or_404(SchoolDocument, pk=pk, school=school)          # another school's id is a 404
    action = request.POST.get('action')
    if action == 'delete':
        audit.record(request.user, audit.DOC_DELETE, doc, school=school.pk)
        doc.delete()
    elif action == 'toggle':
        doc.is_active = not doc.is_active
        doc.save(update_fields=['is_active'])
        audit.record(request.user, audit.DOC_TOGGLE, doc, school=school.pk, detail='on' if doc.is_active else 'off')
    return redirect('docqa:documents')


@role_required(ADMIN, module=MODULE)
@require_POST
def ai_setting(request):
    school = _school(request, admin_only=True)
    on = request.POST.get('ai_enabled') == 'on'
    cfg, _ = AssistantSettings.objects.get_or_create(school=school)
    if cfg.ai_enabled != on:
        cfg.ai_enabled, cfg.updated_by = on, request.user
        cfg.save()
        audit.record(request.user, audit.DOC_AI_SETTING, school=school.pk, detail='on' if on else 'off')
    return redirect('docqa:documents')
