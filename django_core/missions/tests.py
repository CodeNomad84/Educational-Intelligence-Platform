"""Mission module, Slice 1: gating (allowed / denied / expired / trial / cross-school / trial data survives licensing),
role and scope limits, own-observations-only, the grid save rules, versioned weights and the rubric loader. Synthetic data only."""
import io
import tempfile
import zipfile
from datetime import timedelta
from xml.sax.saxutils import escape

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from dashboard.test_counselor import Base, make_user
from schools.models import AuditEvent, SchoolModule, TeacherAssignment
from schools.module_grants import grant
from vocabulary.models import MISSION_ACTIVITY_TYPE, MISSION_CONDITION
from vocabulary.terms import terms_on

from .access import entry_students, visible_observations
from .defaults import INDICATORS
from .models import Activity, Branch, Indicator, Observation, ObservationSession, Period, Weight, WeightSet
from .rubric import parse_rubric_docx
from .weights import ensure_default_weight_set

TODAY = timezone.localdate


class MissionBase(Base):
    def setUp(self):
        super().setUp()
        SchoolModule.objects.all().delete()
        grant(self.a, 'mission')
        grant(self.b, 'mission')
        call_command('seed_mission', verbosity=0)
        self.t1 = make_user('t1', 'Teacher', self.a)
        self.t1b = make_user('t1b', 'Teacher', self.a)          # second teacher of the same class
        self.t2 = make_user('t2', 'Teacher', self.a)            # grade-8 class
        self.tb = make_user('tb', 'Teacher', self.b)
        TeacherAssignment.objects.create(teacher=self.t1, school_class=self.c7, subject='math')
        TeacherAssignment.objects.create(teacher=self.t1b, school_class=self.c7, subject='art')
        TeacherAssignment.objects.create(teacher=self.t2, school_class=self.c8, subject='math')
        TeacherAssignment.objects.create(teacher=self.tb, school_class=self.cb, subject='math')
        self.period = Period.objects.get(school=self.a)
        self.kind = terms_on(self.a, MISSION_ACTIVITY_TYPE).get(code='build')
        self.act = Activity.objects.create(school=self.a, grade=7, period=self.period, title='Bridge', held_on=TODAY(),
                                           activity_type=self.kind, created_by=self.t1)
        self.ind = list(Indicator.objects.all())

    def grid_url(self, act=None):
        return reverse('missions:grid', args=[(act or self.act).pk])

    def get(self, user, url):
        self.client.force_login(user)
        return self.client.get(url)

    def post_grid(self, user, cells, evidence='saw it', act=None, student=None, **extra):
        """cells: {indicator_code: value}; one student row (default s7)."""
        student = student or self.s7
        data = {f'c_{student.pk}_{code}': v for code, v in cells.items()}
        data[f'e_{student.pk}'] = evidence
        data.update(extra)
        self.client.force_login(user)
        return self.client.post(self.grid_url(act), data)


class GatingTests(MissionBase):
    def urls(self):
        return [reverse('missions:activities'), self.grid_url()]

    def test_allowed_and_denied_by_module_state(self):
        for url in self.urls():
            self.assertEqual(self.get(self.t1, url).status_code, 200)
        SchoolModule.objects.filter(school=self.a).delete()                     # no row for A (B still has one)
        for url in self.urls():
            self.assertEqual(self.get(self.t1, url).status_code, 403)
        grant(self.a, 'mission', starts_on=TODAY() - timedelta(days=9), ends_on=TODAY() - timedelta(days=1))   # expired
        for url in self.urls():
            self.assertEqual(self.get(self.t1, url).status_code, 403)
        SchoolModule.objects.filter(school=self.a).delete()
        grant(self.a, 'mission', starts_on=TODAY() + timedelta(days=2))                                         # not started
        for url in self.urls():
            self.assertEqual(self.get(self.t1, url).status_code, 403)

    def test_a_trial_row_works(self):
        SchoolModule.objects.filter(school=self.a).delete()
        SchoolModule.objects.create(school=self.a, module_key='mission', kind='trial', starts_on=TODAY() - timedelta(days=1),
                                    ends_on=TODAY() + timedelta(days=5))
        for url in self.urls():
            self.assertEqual(self.get(self.t1, url).status_code, 200)

    def test_cross_school(self):
        SchoolModule.objects.filter(school=self.a).delete()                     # only B has the module
        self.assertEqual(self.get(self.t1, self.grid_url()).status_code, 403)   # teacher of A: module off in A
        self.assertEqual(self.get(self.tb, self.grid_url()).status_code, 404)   # teacher of B: A's activity is out of scope
        grant(self.a, 'mission')
        self.assertEqual(self.get(self.tb, self.grid_url()).status_code, 404)   # still, with both schools on

    def test_trial_data_is_readable_again_after_a_licensed_row_is_added(self):
        SchoolModule.objects.filter(school=self.a).delete()
        SchoolModule.objects.create(school=self.a, module_key='mission', kind='trial', starts_on=TODAY() - timedelta(days=3),
                                    ends_on=TODAY() + timedelta(days=3))
        self.assertEqual(self.post_grid(self.t1, {1: '4', 2: 'n'}, evidence='found two causes').status_code, 302)
        SchoolModule.objects.filter(school=self.a).update(ends_on=TODAY() - timedelta(days=1))                 # trial ended
        self.assertEqual(self.get(self.t1, self.grid_url()).status_code, 403)
        self.assertEqual(self.post_grid(self.t1, {1: '1'}).status_code, 403)                                   # no write either
        self.assertEqual(Observation.objects.count(), 2)                                                       # data retained
        grant(self.a, 'mission', starts_on=TODAY())                                                            # licensed
        page = self.get(self.t1, self.grid_url())
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'found two causes')
        self.assertTrue(Observation.objects.filter(student=self.s7, indicator__code=1, score=4).exists())


class RoleAndScopeTests(MissionBase):
    def test_only_teacher_and_grade_lead_enter(self):
        for user in (self.admin, self.counselor, self.stu_user(), self.parent):
            for url in (reverse('missions:activities'), self.grid_url()):
                self.assertEqual(self.get(user, url).status_code, 403, user.username)
        self.assertEqual(self.get(self.lead, self.grid_url()).status_code, 200)
        self.client.logout()
        self.assertEqual(self.client.get(self.grid_url()).status_code, 302)

    def stu_user(self):
        user = make_user('stu', 'Student', self.a)
        self.s7.student_user = user
        self.s7.save(update_fields=['student_user'])
        return user

    def test_teacher_of_another_grade_and_unlisted_students(self):
        self.assertEqual(self.get(self.t2, self.grid_url()).status_code, 404)
        page = self.get(self.t1, self.grid_url())
        self.assertContains(page, 'Seven')
        self.assertNotContains(page, 'Eight')
        self.assertNotContains(page, 'Bee')
        self.assertEqual(self.post_grid(self.t1, {1: '3'}, student=self.s8).status_code, 302)   # a student outside the scope
        self.assertEqual(self.post_grid(self.t1, {1: '3'}, student=self.sb).status_code, 302)
        self.assertFalse(Observation.objects.exists())

    def test_entry_students(self):
        self.assertEqual(set(entry_students(self.t1)), {self.s7})
        self.assertEqual(set(entry_students(self.lead)), {self.s7})
        for user in (self.admin, self.counselor, self.parent):
            self.assertFalse(entry_students(user).exists())

    def test_create_activity_scope_period_and_type_are_validated(self):
        url = reverse('missions:activities')
        good = {'title': 'Poster', 'held_on': TODAY().isoformat(), 'scope': f'{self.a.pk}:7', 'period': self.period.pk,
                'activity_type': self.kind.pk}
        self.client.force_login(self.t1)
        self.assertEqual(self.client.post(url, good).status_code, 302)
        for bad in ({'scope': f'{self.a.pk}:8'}, {'scope': f'{self.b.pk}:7'}):
            self.assertEqual(self.client.post(url, {**good, **bad}).status_code, 200)
        other_period = Period.objects.get(school=self.b)
        other_type = terms_on(self.b, MISSION_ACTIVITY_TYPE).first()
        self.assertEqual(self.client.post(url, {**good, 'period': other_period.pk}).status_code, 200)
        self.assertEqual(self.client.post(url, {**good, 'activity_type': other_type.pk}).status_code, 200)
        self.assertEqual(Activity.objects.filter(title='Poster').count(), 1)
        self.assertTrue(AuditEvent.objects.filter(action='mission_activity_create', school=self.a).exists())


class GridTests(MissionBase):
    def test_save_rules(self):
        self.assertEqual(self.post_grid(self.t1, {1: '4', 2: '', 3: 'n'}, evidence='').status_code, 200)       # score without evidence
        self.assertFalse(Observation.objects.exists())
        self.assertEqual(self.post_grid(self.t1, {1: '9'}).status_code, 200)                                    # invalid value
        self.assertFalse(Observation.objects.exists())
        self.assertEqual(self.post_grid(self.t1, {3: 'n'}, evidence='').status_code, 302)                      # only "not observed"
        ob = Observation.objects.get()
        self.assertEqual((ob.score, ob.not_observed), (None, True))
        self.assertEqual(self.post_grid(self.t1, {1: '4', 3: '2'}, evidence='x' * 301).status_code, 200)       # too long
        cond = terms_on(self.a, MISSION_CONDITION).first()
        self.assertEqual(self.post_grid(self.t1, {1: '4', 3: '2'}, evidence='two options', **{f'k_{self.s7.pk}': cond.pk}).status_code, 302)
        self.assertEqual(Observation.objects.count(), 2)
        self.assertEqual(Observation.objects.get(indicator__code=3).score, 2)            # "not observed" edited into a score
        self.assertEqual(Observation.objects.get(indicator__code=1).condition_id, cond.pk)
        self.assertEqual(self.post_grid(self.t1, {1: '', 3: '2'}).status_code, 302)                           # blank clears own entry
        self.assertEqual(list(Observation.objects.values_list('indicator__code', flat=True)), [3])
        other_school_cond = terms_on(self.b, MISSION_CONDITION).first()
        self.assertEqual(self.post_grid(self.t1, {1: '2'}, **{f'k_{self.s7.pk}': other_school_cond.pk}).status_code, 200)
        self.assertEqual(Observation.objects.count(), 1)

    def test_db_constraints(self):
        sess = ObservationSession.objects.create(activity=self.act, observer=self.t1)
        for kwargs in ({'score': 3, 'not_observed': True, 'evidence': 'x'}, {'score': None, 'not_observed': False},
                       {'score': 6, 'evidence': 'x'}, {'score': 3, 'evidence': ''}):
            with self.subTest(kwargs), self.assertRaises(IntegrityError), transaction.atomic():
                Observation.objects.create(session=sess, student=self.s7, indicator=self.ind[0], **kwargs)
        with self.assertRaises(ValidationError):                                                    # student of another school
            Observation.objects.create(session=sess, student=self.sb, indicator=self.ind[0], score=3, evidence='x')

    def test_closed_period_is_read_only(self):
        self.post_grid(self.t1, {1: '3'})
        Period.objects.filter(pk=self.period.pk).update(closed=True)
        self.assertEqual(self.get(self.t1, self.grid_url()).status_code, 200)
        self.assertEqual(self.post_grid(self.t1, {1: '5'}).status_code, 403)
        self.assertEqual(Observation.objects.get().score, 3)

    def test_audit_has_counts_and_no_content(self):
        self.get(self.t1, self.grid_url())
        self.post_grid(self.t1, {1: '4', 2: '5'}, evidence='secret sentence')
        events = AuditEvent.objects.filter(action__startswith='mission_grid')
        self.assertEqual(sorted(events.values_list('action', flat=True)), ['mission_grid_save', 'mission_grid_view'])
        self.assertEqual(events.get(action='mission_grid_save').detail, 's1o2d0')
        self.assertFalse(any('secret' in str(v) for e in events for v in (e.detail, e.object_type, e.object_id)))


class OwnObservationsTests(MissionBase):
    def setUp(self):
        super().setUp()
        self.post_grid(self.t1, {1: '4'}, evidence='from t1')
        self.post_grid(self.t1b, {1: '2'}, evidence='from t1b')

    def test_a_teacher_sees_and_edits_only_their_own(self):
        page = self.get(self.t1, self.grid_url())
        self.assertContains(page, 'from t1')
        self.assertNotContains(page, 'from t1b')
        self.post_grid(self.t1, {1: '5'}, evidence='changed')
        self.assertEqual(set(Observation.objects.values_list('score', 'session__observer__username')), {(5, 't1'), (2, 't1b')})
        self.assertEqual(set(visible_observations(self.t1).values_list('session__observer__username', flat=True)), {'t1'})

    def test_visibility_by_role(self):
        self.assertEqual(visible_observations(self.lead).count(), 2)                  # grade lead: every observer, own grade
        self.assertFalse(visible_observations(self.admin).exists())                   # admin: aggregates only (Slice 3)
        self.assertFalse(visible_observations(self.counselor).exists())               # counselor: needs an open referral
        ref = self.refer(self.s7, self.counselor)
        self.assertEqual(visible_observations(self.counselor).count(), 2)
        ref.status = 'closed'
        ref.save()
        self.assertFalse(visible_observations(self.counselor).exists())
        self.assertFalse(visible_observations(self.t2).exists())
        SchoolModule.objects.filter(school=self.a).delete()
        self.assertFalse(visible_observations(self.lead).exists())                    # module off: nothing, data retained
        self.assertEqual(Observation.objects.count(), 2)


class WeightTests(MissionBase):
    def test_default_set_is_active_complete_and_idempotent(self):
        ws = WeightSet.objects.get(school=self.a)
        self.assertEqual((ws.version, ws.status, str(ws.diff_threshold), ws.min_observations, ws.min_activities), (1, 'active', '1.5', 3, 2))
        self.assertEqual(ws.weights.count(), 96)
        self.assertEqual(set(ws.column_sums().values()), {100})
        self.assertEqual(len(ws.column_sums()), Branch.objects.count())
        self.assertEqual(ensure_default_weight_set(self.a), (ws, False))
        call_command('seed_mission', verbosity=0)
        self.assertEqual(WeightSet.objects.filter(school=self.a).count(), 1)
        self.assertEqual(Period.objects.filter(school=self.a).count(), 1)

    def test_active_set_is_immutable_and_a_draft_needs_sums_of_100(self):
        ws = WeightSet.objects.get(school=self.a)
        w = ws.weights.first()
        w.percent = 0
        with self.assertRaises(ValidationError):
            w.save()
        ws.min_observations = 1
        with self.assertRaises(ValidationError):
            ws.save()
        with self.assertRaises(ValidationError):
            ws.delete()
        draft = WeightSet.objects.create(school=self.a, version=2)
        draft.status = 'simulated'
        with self.assertRaises(ValidationError):
            draft.save()                                                                    # no weights yet: sums are not 100
        with self.assertRaises(ValidationError):
            WeightSet.objects.create(school=self.a, version=3, status='active')
        with self.assertRaises(IntegrityError), transaction.atomic():
            WeightSet.objects.filter(pk=draft.pk).update(status='active')                  # a second active set in one school
        ws = WeightSet.objects.get(pk=ws.pk)
        ws.status = 'retired'
        ws.save()
        self.assertEqual(WeightSet.objects.get(school=self.b).status, 'active')            # per school

    def test_indicators_and_branches_are_seeded(self):
        self.assertEqual(list(Indicator.objects.values_list('code', 'name_fa')), INDICATORS)
        self.assertEqual(Branch.objects.count(), 8)
        self.assertEqual(Weight.objects.filter(weight_set__school=self.a, percent=0).count(), 12)


def _docx(path, indicators):
    paras = ''.join(
        f'<w:p><w:r><w:t>{i}. {escape(f"synthetic indicator {i}")}</w:t></w:r></w:p><w:tbl>'
        + '<w:tr><w:tc><w:p><w:r><w:t>نمره</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>ملاک</w:t></w:r></w:p></w:tc></w:tr>'
        + ''.join(f'<w:tr><w:tc><w:p><w:r><w:t>{s}</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>level {i}-{s}</w:t></w:r></w:p></w:tc></w:tr>'
                  for s in range(1, 6)) + '</w:tbl>' for i in indicators)
    xml = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + paras + '</w:body></w:document>')
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('word/document.xml', xml)


class RubricTests(MissionBase):
    def test_parse_and_load_synthetic_guide(self):
        with tempfile.TemporaryDirectory() as d:
            ok = f'{d}/guide.docx'
            _docx(ok, range(1, 13))
            self.assertEqual(parse_rubric_docx(ok)[7][3], 'level 7-3')
            call_command('load_mission_rubric', ok, stdout=io.StringIO())
            call_command('load_mission_rubric', ok, stdout=io.StringIO())              # idempotent
            self.assertEqual(Indicator.objects.get(code=12).levels.count(), 5)
            page = self.get(self.t1, self.grid_url())
            self.assertContains(page, 'level 1-5')                                    # rubric shown as a header hint
            short = f'{d}/short.docx'
            _docx(short, range(1, 12))
            with self.assertRaises(ValueError):
                parse_rubric_docx(short)
