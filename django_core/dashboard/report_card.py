"""Printable report card (decision pack 0028 P5-4): one student, one term, from existing grades and attendance only, read
through the viewer's own scopes (``visible_students`` full tier, ``visible_grades``, ``visible_attendances``). No new data, no
PDF dependency: the page has a print stylesheet. Terms: the current academic year of the student's school split at 1 Bahman
(approximated as 21 January); without a current year, the last 365 days are one term."""
from datetime import date, timedelta

from django.db.models import Avg, Count, Max, Min
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from schools import audit
from schools.models import AcademicYear
from schools.vocabulary import SUBJECT_CHOICES
from students.access import ADMIN, GRADE_LEAD, PARENT, visible_attendances, visible_grades, visible_students

from .decorators import role_required


def terms_for(student, today):
    year = AcademicYear.objects.filter(school_id=student.school_id, is_current=True).first()
    if year is None:
        return None, [('year', 'یک سال اخیر', today - timedelta(days=365), today)]
    split = date(year.start_date.year + 1, 1, 21)
    return year, [('1', 'نوبت اول', year.start_date, split - timedelta(days=1)), ('2', 'نوبت دوم', split, year.end_date)]


@role_required(ADMIN, GRADE_LEAD, PARENT)
def report_card(request, pk):
    student = get_object_or_404(visible_students(request.user).filter(full_tier=True), pk=pk)
    today = timezone.localdate()
    year, terms = terms_for(student, today)
    wanted = request.GET.get('term') or next((t[0] for t in terms if t[2] <= today <= t[3]), terms[-1][0])
    term = next((t for t in terms if t[0] == wanted), None)
    if term is None:
        raise Http404
    _code, _label, start, end = term
    grades = visible_grades(request.user).filter(student=student, date__gte=start, date__lte=end)
    labels = dict(SUBJECT_CHOICES)
    subjects = [{**row, 'label': labels.get(row['subject'], row['subject']), 'avg': round(row['avg'], 2)}
                for row in grades.values('subject').annotate(avg=Avg('score'), n=Count('pk'), lo=Min('score'), hi=Max('score'))
                .order_by('subject')]
    overall = grades.aggregate(a=Avg('score'))['a']
    days = dict(visible_attendances(request.user).filter(student=student, date__gte=start, date__lte=end)
                .values_list('status').annotate(n=Count('pk')))
    audit.record(request.user, audit.REPORT_CARD_VIEW, student, detail=f'term:{term[0]}')
    return render(request, 'dashboard/report_card.html', {
        'student': student, 'year': year, 'terms': terms, 'term': term, 'subjects': subjects, 'today': today,
        'overall': round(overall, 2) if overall is not None else None, 'days': days, 'days_total': sum(days.values())})
