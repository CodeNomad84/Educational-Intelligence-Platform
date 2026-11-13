"""Slice 1 pages: activities and the fast grid entry (rows = students, columns = the 12 indicators).

Gate on every view: ``role_required(TEACHER, GRADE_LEAD, module='mission')`` (request level) and ``require_module`` on the
activity's school (object level). An activity outside the user's (school, grade) scope is a 404. The grid only ever reads
or writes the logged-in user's OWN session; other observers' rows are never loaded here. Audit stores counts, never text.
"""
from datetime import date

from django.utils import timezone
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from dashboard.decorators import require_module, role_required
from schools import audit
from students.access import GRADE_LEAD, TEACHER
from vocabulary.models import MISSION_ACTIVITY_TYPE, MISSION_CONDITION
from vocabulary.terms import terms_on

from .access import MODULE, entry_scopes, grid_students, usable_activities
from .defaults import MIN_ACTIVITIES, MIN_OBSERVATIONS
from .models import Activity, Indicator, Observation, ObservationSession, Period, WeightSet

NOT_OBSERVED = 'n'
CELL_CHOICES = [('', '—'), (NOT_OBSERVED, 'مشاهده نشد'), *[(str(i), str(i)) for i in range(1, 6)]]
MAX_EVIDENCE = 300


class ActivityForm(forms.Form):
    title = forms.CharField(label='عنوان فعالیت', max_length=120, widget=forms.TextInput(attrs={'class': 'form-control'}))
    held_on = forms.DateField(label='تاریخ', initial=timezone.localdate, widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    scope = forms.ChoiceField(label='مدرسه / پایه', widget=forms.Select(attrs={'class': 'form-select'}))
    period = forms.ChoiceField(label='دوره', widget=forms.Select(attrs={'class': 'form-select'}))
    activity_type = forms.ChoiceField(label='نوع فعالیت', widget=forms.Select(attrs={'class': 'form-select'}))

    def __init__(self, *args, scopes, **kwargs):
        super().__init__(*args, **kwargs)
        self.scopes = scopes
        from schools.models import School
        names = dict(School.objects.filter(pk__in={s for s, _g in scopes}).values_list('pk', 'name'))
        self.fields['scope'].choices = [(f'{s}:{g}', f'{names[s]} — پایه {g}') for s, g in sorted(scopes)]
        school_ids = {s for s, _g in scopes}
        self.periods = {p.pk: p for p in Period.objects.filter(school_id__in=school_ids, closed=False, academic_year__is_current=True)}
        self.fields['period'].choices = [(p.pk, f'{p.label} ({p.school_id})') for p in self.periods.values()]
        self.types = {t.pk: t for sid in school_ids for t in terms_on(sid, MISSION_ACTIVITY_TYPE)}
        self.fields['activity_type'].choices = [(t.pk, t.label_fa) for t in self.types.values()]

    def clean(self):
        data = super().clean()
        if not self.errors:
            school_id, grade = (int(x) for x in data['scope'].split(':'))
            period, kind = self.periods.get(int(data['period'])), self.types.get(int(data['activity_type']))
            if (school_id, grade) not in self.scopes or period is None or kind is None \
                    or period.school_id != school_id or kind.school_id != school_id:
                raise forms.ValidationError('ترکیب مدرسه، پایه، دوره و نوع فعالیت معتبر نیست.')
            data.update(school_id=school_id, grade=grade, period_obj=period, type_obj=kind)
        return data


@role_required(TEACHER, GRADE_LEAD, module=MODULE)
@require_http_methods(['GET', 'POST'])
def activities(request):
    scopes = entry_scopes(request.user)
    form = ActivityForm(request.POST or None, scopes=scopes)
    if request.method == 'POST':
        if form.is_valid():
            d = form.cleaned_data
            act = Activity.objects.create(school_id=d['school_id'], grade=d['grade'], period=d['period_obj'], title=d['title'],
                                          held_on=d['held_on'], activity_type=d['type_obj'], created_by=request.user)
            audit.record(request.user, audit.MISSION_ACTIVITY_CREATE, act, school=act.school_id)
            return redirect('missions:grid', pk=act.pk)
    rows = usable_activities(request.user).select_related('period', 'activity_type')
    return render(request, 'missions/activities.html', {'form': form, 'activities': rows, 'has_scope': bool(scopes)})


def _read_grid(request, students, indicators, conditions):
    """Parse the posted grid. Returns (entries, errors, values): entries = {student_id: (cells, evidence, condition_or_None)}."""
    entries, errors, values = {}, {}, {}
    for st in students:
        cells = {}
        for ind in indicators:
            raw = (request.POST.get(f'c_{st.pk}_{ind.code}') or '').strip()
            if raw not in {c for c, _l in CELL_CHOICES}:
                errors[st.pk] = 'مقدار نامعتبر.'
                continue
            cells[ind.pk] = raw
        evidence = (request.POST.get(f'e_{st.pk}') or '').strip()
        cond_raw = (request.POST.get(f'k_{st.pk}') or '').strip()
        condition = None
        if cond_raw:
            condition = conditions.get(cond_raw)
            if condition is None:
                errors[st.pk] = 'شرایط نامعتبر.'
        if len(evidence) > MAX_EVIDENCE:
            errors[st.pk] = f'شاهد حداکثر {MAX_EVIDENCE} نویسه.'
        elif any(v.isdigit() for v in cells.values()) and not evidence:
            errors[st.pk] = 'برای نمره‌های ثبت‌شده، یک شاهد کوتاه بنویسید.'
        entries[st.pk] = (cells, evidence, condition)
        values[st.pk] = {'cells': {ind.code: cells.get(ind.pk, '') for ind in indicators}, 'evidence': evidence, 'condition': cond_raw}
    return entries, errors, values


@role_required(TEACHER, GRADE_LEAD, module=MODULE)
@require_http_methods(['GET', 'POST'])
def grid(request, pk):
    activity = get_object_or_404(usable_activities(request.user).select_related('period', 'activity_type'), pk=pk)
    require_module(activity.school_id, MODULE)
    students = list(grid_students(request.user, activity))
    indicators = list(Indicator.objects.prefetch_related('levels'))
    conditions = {str(t.pk): t for t in terms_on(activity.school_id, MISSION_CONDITION)}
    session = ObservationSession.objects.filter(activity=activity, observer=request.user).first()
    errors = {}
    if request.method == 'POST':
        if activity.period.closed:
            raise PermissionDenied
        entries, errors, values = _read_grid(request, students, indicators, conditions)
        if not errors:
            saved = deleted = 0
            with transaction.atomic():
                session, _ = ObservationSession.objects.get_or_create(activity=activity, observer=request.user)
                existing = {(o.student_id, o.indicator_id): o for o in session.observations.all()}
                for student_id, (cells, evidence, condition) in entries.items():
                    for indicator_id, raw in cells.items():
                        old = existing.get((student_id, indicator_id))
                        if raw == '':
                            if old:
                                old.delete()
                                deleted += 1
                            continue
                        fields = {'score': None if raw == NOT_OBSERVED else int(raw), 'not_observed': raw == NOT_OBSERVED,
                                  'evidence': evidence, 'condition': condition}
                        if old:
                            for k, v in fields.items():
                                setattr(old, k, v)
                            old.save()
                        else:
                            Observation.objects.create(session=session, student_id=student_id, indicator_id=indicator_id, **fields)
                        saved += 1
            audit.record(request.user, audit.MISSION_GRID_SAVE, activity, school=activity.school_id,
                         detail=f's{len(students)}o{saved}d{deleted}')
            messages.success(request, 'مشاهدات ثبت شد.')
            return redirect('missions:grid', pk=activity.pk)
    else:
        values = {}
        if session:
            for ob in session.observations.select_related('indicator'):
                row = values.setdefault(ob.student_id, {'cells': {}, 'evidence': ob.evidence, 'condition': str(ob.condition_id or '')})
                row['cells'][ob.indicator.code] = NOT_OBSERVED if ob.not_observed else str(ob.score)
        audit.record(request.user, audit.MISSION_GRID_VIEW, activity, school=activity.school_id)
    rows = [{'student': st, 'error': errors.get(st.pk),
             'cells': [{'indicator': ind, 'value': values.get(st.pk, {}).get('cells', {}).get(ind.code, '')} for ind in indicators],
             'evidence': values.get(st.pk, {}).get('evidence', ''), 'condition': values.get(st.pk, {}).get('condition', '')}
            for st in students]
    ws = WeightSet.objects.filter(school_id=activity.school_id, status=WeightSet.ACTIVE).first()
    return render(request, 'missions/grid.html', {
        'min_obs': ws.min_observations if ws else MIN_OBSERVATIONS, 'min_acts': ws.min_activities if ws else MIN_ACTIVITIES,
        'activity': activity, 'rows': rows, 'indicators': indicators, 'cell_choices': CELL_CHOICES,
        'conditions': conditions.items(), 'read_only': activity.period.closed, 'max_evidence': MAX_EVIDENCE})
