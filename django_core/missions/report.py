"""Mission module, Slice 3: assembles the per-student report from the engine and the recorded forms. Read-only; stores nothing.

``kind`` (from ``access.report_kind``) decides what is shown: ``lead`` sees everything including which observer gave which
score; ``counselor`` sees the same without observer identity; ``teacher`` gets a status-only view of their OWN observations
(no scores, no other people's data, no plan or forms). Branches and indicators are always listed in their fixed order: the
report never ranks or sorts anything by a score.
"""
from .access import LEAD, TEACHER_KIND, visible_observations
from .engine import STATUS_LABELS, active_weight_set, student_profile
from .models import ActivityChoice, Branch, Indicator, ParentMeeting, PathSuggestion, Period

FOOTER = 'اولیه، اعتبارسنجی‌نشده و تصمیم نیست؛ هرگز برای پذیرش یا جانمایی به کار نمی‌رود.'


def periods_for(school_id):
    return sorted(Period.objects.filter(school_id=school_id).select_related('academic_year'),
                  key=lambda p: (p.academic_year.start_date, p.pk), reverse=True)


def pick_period(school_id, raw):
    periods = periods_for(school_id)
    chosen = next((p for p in periods if str(p.pk) == str(raw)), None) if raw else None
    return chosen or (periods[0] if periods else None), periods


def _label(code):
    return STATUS_LABELS[code]


def build_report(user, student, period, kind):
    ws = active_weight_set(student.school_id)
    observations = visible_observations(user)
    profile = student_profile(student, observations, period, ws)
    indicators = list(Indicator.objects.all())
    names = {i.code: i.name_fa for i in indicators}
    branches = list(Branch.objects.all())
    teacher_view = kind == TEACHER_KIND

    rows = list(observations.filter(student=student, session__activity__period=period).select_related(
        'session__activity', 'session__observer', 'condition', 'indicator').order_by('session__activity__held_on', 'pk'))
    evidence = {}
    for ob in rows:
        if ob.score is not None and ob.evidence:
            evidence.setdefault(ob.indicator.code, []).append({
                'score': ob.score, 'text': ob.evidence, 'activity': ob.session.activity.title, 'condition': ob.condition,
                'observer': (ob.session.observer.get_full_name() or ob.session.observer.username) if kind == LEAD else None})

    ind_rows = []
    for ind in indicators:
        r = profile.indicators[ind.code]
        row = {'code': ind.code, 'name': ind.name_fa, 'status': _label(r.status), 'evidences': r.evidences, 'activities': r.activities,
               'provisional': r.provisional, 'observed': r.score is not None}
        if not teacher_view:
            row.update(score=r.score, change=r.change, differs=r.differs, evidence=evidence.get(ind.code, []))
        ind_rows.append(row)
    branch_rows = []
    for br in branches:
        r = profile.branches[br.code]
        row = {'name': br.name_fa, 'field': br.get_field_display(), 'status': _label(r.status), 'scored': r.score is not None,
               'missing': [names[c] for c in r.missing], 'provisional': [names[c] for c in r.provisional],
               'differing': [names[c] for c in r.differing]}
        if not teacher_view:
            row.update(score=r.score, score_x20=r.score_x20, change=r.change)
        branch_rows.append(row)
    ctx = {'student': student, 'period': period, 'kind': kind, 'indicators': ind_rows, 'branches': branch_rows,
           'params_version': ws.pk, 'footer': FOOTER, 'teacher_view': teacher_view}
    if teacher_view:
        return ctx

    strong_at, growth_at = ws.strong_at, ws.growth_at
    ctx['strong'] = [i for i in ind_rows if i['score'] is not None and i['score'] >= strong_at]
    ctx['growth'] = [i for i in ind_rows if i['score'] is not None and i['score'] <= growth_at]
    situations = []
    for ind in indicators:
        r = profile.indicators[ind.code]
        if r.differs:
            acts = {a.pk: a.title for a in {o.session.activity for o in rows if o.indicator_id == ind.pk}}
            entry = {'name': ind.name_fa, 'activities': [(acts.get(a, a), m) for a, m in r.per_activity.items()]}
            if kind == LEAD:
                users = {o.session.observer_id: (o.session.observer.get_full_name() or o.session.observer.username) for o in rows}
                entry['observers'] = [(users.get(o, o), m) for o, m in r.per_observer.items()]
            situations.append(entry)
    ctx['situations'] = situations
    ctx['choices'] = list(ActivityChoice.objects.filter(student=student, period=period).exclude(choice='', reason=''))
    ctx['meetings'] = list(ParentMeeting.objects.filter(student=student))
    ctx['paths'] = list(PathSuggestion.objects.filter(student=student, period=period).select_related('branch'))
    return ctx
