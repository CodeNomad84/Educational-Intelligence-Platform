"""Slice 3 pages: the per-student report, the plan, the two forms and the admin aggregate.

Every view: ``role_required(..., module=MODULE)`` (request level) + ``require_module`` on the student's school (object level).
A student outside the user's scope is a 404; a student the user may read but not write is a 403. Writes (plan, choices,
meetings) are for the Grade Lead of that student's grade only. Audit stores counts, never text. No export route exists.
"""
from datetime import date

from django.utils import timezone
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from dashboard.decorators import require_module, role_required
from schools import audit
from students.access import ADMIN, COUNSELOR, GRADE_LEAD, TEACHER, school_ids_for_admin
from students.enrollment_sync import CURRENT_STATUSES
from students.models import Enrollment

from .access import LEAD, MODULE, enabled_school_ids, report_kind, report_students
from .defaults import CHOICE_CATEGORIES
from .engine import NEEDS_DIFF, NEEDS_MORE, STATUS_LABELS, USABLE, active_weight_set, period_profiles
from .models import ActivityChoice, Branch, Indicator, Observation, ParentMeeting, PathSuggestion, Weight, WeightSet
from .report import FOOTER, build_report, pick_period

READ_ROLES = (TEACHER, GRADE_LEAD, COUNSELOR)
MIN_GROUP = 5            # a group smaller than this is never shown in an aggregate


def _student(request, pk, *, write=False):
    student = get_object_or_404(report_students(request.user), pk=pk)
    require_module(student.school_id, MODULE)
    kind = report_kind(request.user, student)
    if kind is None:
        raise Http404
    if write and kind != LEAD:
        raise PermissionDenied
    return student, kind


@role_required(*READ_ROLES, module=MODULE)
def students(request):
    return render(request, 'missions/students.html', {'students': report_students(request.user), 'footer': FOOTER})


@role_required(*READ_ROLES, module=MODULE)
@never_cache
def report(request, pk):
    student, kind = _student(request, pk)
    period, periods = pick_period(student.school_id, request.GET.get('period'))
    ctx = {'student': student, 'kind': kind, 'footer': FOOTER, 'periods': periods, 'period': period}
    if period is None:
        ctx['error'] = 'هنوز دوره‌ای تعریف نشده است.'
    else:
        try:
            ctx.update(build_report(request.user, student, period, kind))
        except ValueError:
            ctx['error'] = 'برای این مدرسه نسخهٔ فعال وزن‌ها وجود ندارد.'
        else:
            ctx['branch_choices'] = list(Branch.objects.all())
            ctx['today'] = timezone.localdate()
            audit.record(request.user, audit.MISSION_REPORT_VIEW, student, school=student.school_id, detail=kind)
    return render(request, 'missions/report_status.html' if ctx.get('teacher_view') else 'missions/report.html', ctx)


def _read_plan(post, branches):
    paths, errors = [], []
    seen = set()
    for i in range(1, PathSuggestion.MAX_PER_PERIOD + 1):
        branch_id = (post.get(f'p{i}_branch') or '').strip()
        if not branch_id:
            continue
        branch = branches.get(branch_id)
        experience, goal = (post.get(f'p{i}_experience') or '').strip(), (post.get(f'p{i}_goal') or '').strip()
        try:
            review = date.fromisoformat((post.get(f'p{i}_review') or '').strip())
        except ValueError:
            review = None
        if branch is None or branch.pk in seen:
            errors.append(f'مسیر {i}: شاخهٔ نامعتبر یا تکراری.')
        elif not experience or not goal or review is None or len(experience) > 300 or len(goal) > 300:
            errors.append(f'مسیر {i}: تجربهٔ عملی، هدف رشد و تاریخ بازبینی لازم است.')
        elif review < timezone.localdate():
            errors.append(f'مسیر {i}: تاریخ بازبینی نباید گذشته باشد.')
        else:
            seen.add(branch.pk)
            paths.append((branch, experience, goal, review))
    if not 2 <= len(paths) <= PathSuggestion.MAX_PER_PERIOD and not errors:
        errors.append('دو یا سه مسیر قابل‌بررسی پیشنهاد کنید.')
    return paths, errors


@role_required(GRADE_LEAD, module=MODULE)
@require_POST
def plan(request, pk):
    student, _kind = _student(request, pk, write=True)
    period, _periods = pick_period(student.school_id, request.POST.get('period'))
    if period is None:
        raise Http404
    ws = active_weight_set(student.school_id)
    paths, errors = _read_plan(request.POST, {str(b.pk): b for b in Branch.objects.all()})
    if errors:
        for e in errors:
            messages.error(request, e)
    else:
        with transaction.atomic():
            PathSuggestion.objects.filter(student=student, period=period).exclude(branch__in=[b for b, *_ in paths]).delete()
            for branch, experience, goal, review in paths:
                PathSuggestion.objects.update_or_create(
                    student=student, period=period, branch=branch,
                    defaults={'experience': experience, 'growth_goal': goal, 'review_date': review,
                              'params_version': ws.pk, 'author': request.user})
        audit.record(request.user, audit.MISSION_PLAN_SAVE, student, school=student.school_id, detail=str(len(paths)))
        messages.success(request, 'مسیرهای پیشنهادی ثبت شد.')
    return redirect(f"{reverse('missions:report', args=[student.pk])}?period={period.pk}")


@role_required(GRADE_LEAD, module=MODULE)
@require_http_methods(['GET', 'POST'])
def choices(request, pk):
    student, _kind = _student(request, pk, write=True)
    period, periods = pick_period(student.school_id, request.GET.get('period') or request.POST.get('period'))
    if period is None:
        raise Http404
    existing = {c.category: c for c in ActivityChoice.objects.filter(student=student, period=period)}
    errors = {}
    if request.method == 'POST':
        rows = {}
        for code, _label in CHOICE_CATEGORIES:
            choice, reason = (request.POST.get(f'ch_{code}') or '').strip(), (request.POST.get(f'rs_{code}') or '').strip()
            if len(choice) > 150 or len(reason) > 300:
                errors[code] = 'طول متن بیش از حد مجاز است.'
            rows[code] = (choice, reason)
        if not errors:
            with transaction.atomic():
                for code, (choice, reason) in rows.items():
                    if choice or reason:
                        ActivityChoice.objects.update_or_create(student=student, period=period, category=code,
                                                                defaults={'choice': choice, 'reason': reason, 'recorded_by': request.user})
                    elif code in existing:
                        existing[code].delete()
            audit.record(request.user, audit.MISSION_CHOICES_SAVE, student, school=student.school_id,
                         detail=str(sum(1 for c, r in rows.values() if c or r)))
            messages.success(request, 'انتخاب‌ها ثبت شد.')
            return redirect(f"{request.path}?period={period.pk}")
    rows = [{'code': code, 'label': label, 'choice': (request.POST.get(f'ch_{code}') if request.method == 'POST' else getattr(existing.get(code), 'choice', '')) or '',
             'reason': (request.POST.get(f'rs_{code}') if request.method == 'POST' else getattr(existing.get(code), 'reason', '')) or '',
             'error': errors.get(code)} for code, label in CHOICE_CATEGORIES]
    return render(request, 'missions/choices.html', {'student': student, 'period': period, 'periods': periods, 'rows': rows, 'footer': FOOTER})


class MeetingForm(forms.ModelForm):
    class Meta:
        model = ParentMeeting
        fields = ['held_on', 'parents_present', 'agreements', 'quality']
        widgets = {'held_on': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
                   'parents_present': forms.Select(attrs={'class': 'form-select'}),
                   'agreements': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
                   'quality': forms.Select(attrs={'class': 'form-select'})}
        labels = {'held_on': 'تاریخ', 'parents_present': 'حضور والدین', 'agreements': 'قرارهای جلسه', 'quality': 'کیفیت انجام'}


@role_required(GRADE_LEAD, module=MODULE)
@require_http_methods(['GET', 'POST'])
def meetings(request, pk):
    student, _kind = _student(request, pk, write=True)
    form = MeetingForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        meeting = form.save(commit=False)
        meeting.student, meeting.recorded_by = student, request.user
        meeting.save()
        audit.record(request.user, audit.MISSION_MEETING_ADD, student, school=student.school_id)
        messages.success(request, 'جلسه ثبت شد.')
        return redirect('missions:meetings', pk=student.pk)
    return render(request, 'missions/meetings.html', {
        'student': student, 'form': form, 'meetings': ParentMeeting.objects.filter(student=student), 'footer': FOOTER})


def _cell(n):
    return n if n >= MIN_GROUP else f'<{MIN_GROUP}'


@role_required(ADMIN, module=MODULE)
@never_cache
def aggregate(request):
    """Admin: counts of students per grade and branch evidence status. No names, no scores, no ranking. A grade with fewer than
    ``MIN_GROUP`` students with observations is suppressed entirely; inside a shown grade a count below it is shown as "<5"."""
    blocks = []
    for school_id in sorted(school_ids_for_admin(request.user) & enabled_school_ids(request.user)):
        period, _periods = pick_period(school_id, request.GET.get('period'))
        if period is None:
            continue
        try:
            profiles = period_profiles(Observation.objects.filter(session__activity__school_id=school_id), period, with_change=False)
        except ValueError:
            continue
        grades = dict(Enrollment.objects.filter(
            student_id__in=list(profiles), academic_year=period.academic_year, ended_on__isnull=True,
            status__in=CURRENT_STATUSES).values_list('student_id', 'grade'))
        branches = list(Branch.objects.all())
        by_grade = {}
        for sid, prof in profiles.items():
            by_grade.setdefault(grades.get(sid), []).append(prof)
        groups = []
        for grade in sorted(g for g in by_grade if g is not None):
            profs = by_grade[grade]
            if len(profs) < MIN_GROUP:
                groups.append({'grade': grade, 'suppressed': True})
                continue
            rows = [{'branch': b.name_fa, 'cells': [_cell(sum(1 for p in profs if p.branches[b.code].status == s))
                                                    for s in (NEEDS_MORE, NEEDS_DIFF, USABLE)]} for b in branches]
            groups.append({'grade': grade, 'suppressed': False, 'n': len(profs), 'rows': rows})
        blocks.append({'school_id': school_id, 'period': period, 'groups': groups})
        audit.record(request.user, audit.MISSION_AGGREGATE_VIEW, school=school_id, detail=str(len(groups)))
    return render(request, 'missions/aggregate.html', {
        'blocks': blocks, 'statuses': [STATUS_LABELS[s] for s in (NEEDS_MORE, NEEDS_DIFF, USABLE)], 'min_group': MIN_GROUP, 'footer': FOOTER})


@role_required(ADMIN, module=MODULE)
@never_cache
def weights(request):
    """Admin, read only: the weight sets of the own schools (the active one as a table with column sums, every version with its
    lifecycle state). Parameters only: no student data. Editing and approval are NOT here (slice 2b)."""
    indicators, branches = list(Indicator.objects.all()), list(Branch.objects.all())
    blocks = []
    for school_id in sorted(school_ids_for_admin(request.user) & enabled_school_ids(request.user)):
        versions = list(WeightSet.objects.filter(school_id=school_id).order_by('-version'))
        active = next((v for v in versions if v.status == WeightSet.ACTIVE), None)
        table = sums = None
        if active:
            cells = {(i, b): p for i, b, p in Weight.objects.filter(weight_set=active).values_list('indicator_id', 'branch_id', 'percent')}
            table = [{'indicator': ind, 'cells': [cells.get((ind.pk, br.pk), 0) for br in branches]} for ind in indicators]
            sums = [sum(row['cells'][n] for row in table) for n in range(len(branches))]
        blocks.append({'school_id': school_id, 'versions': versions, 'active': active, 'table': table, 'sums': sums})
        audit.record(request.user, audit.MISSION_WEIGHTS_VIEW, school=school_id)
    return render(request, 'missions/weights.html', {'blocks': blocks, 'branches': branches, 'footer': FOOTER})
