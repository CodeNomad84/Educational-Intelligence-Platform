"""Exams Slice 2: CSV import (dry run, confirm, re-validation, scope), exam editing, teacher results, Grade Lead and SchoolAdmin
views. Same gating set as Slice 1 (allowed / denied / expired / trial / cross-school / trial data readable after a licensed row).
Synthetic data only."""
import io
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from dashboard.test_counselor import make_user
from schools.models import AuditEvent, SchoolModule
from schools.module_grants import grant

from . import analytics
from .models import Exam, ExamQuestion, ExamSession, Option, Question, QuestionAttempt
from .tests import TODAY, ExamBase

HEADER = 'topic,stem,correct,o1_text,o1_expl,o2_text,o2_expl,o3_text,o3_expl,o4_text,o4_expl,o5_text,o5_expl'


def csv_bytes(*lines, header=HEADER):
    return ('\n'.join([header, *lines]) + '\n').encode('utf-8')


GOOD = 'math.ch3.fractions,What is 3/6?,2,1/3,no: that is 2/6,1/2,yes: halve both,2/3,no: that is 4/6,,,,'


class SliceBase(ExamBase):
    def upload(self, user, data, scope=None):
        self.client.force_login(user)
        return self.client.post(reverse('exams:import_form'), {
            'scope': scope or f'{self.a.pk}:math', 'file': SimpleUploadedFile('q.csv', data, content_type='text/csv')})

    def confirm(self, user):
        self.client.force_login(user)
        return self.client.post(reverse('exams:import_confirm'))

    def play_all(self, user, exam, wrong_first=False):
        """Solve every question; with wrong_first choose option 1 (wrong) before the right one."""
        url = self.play_url(exam)
        for item in exam.items.order_by('order'):
            if wrong_first:
                self.post(user, url, {'option': item.question.options.get(order=1).pk})
            self.post(user, url, {'option': item.question.options.get(is_correct=True).pk})
        self.get(user, url)                                                                                    # shows the end page: finishes the session


class GatingTests(SliceBase):
    def pages(self):
        q = self.question()
        exam = self.exam([q])
        return [(self.t1, reverse('exams:import_form')), (self.t1, reverse('exams:import_template')),
                (self.t1, reverse('exams:exam_edit', args=[exam.pk])), (self.t1, reverse('exams:exam_results', args=[exam.pk])),
                (self.lead, reverse('exams:lead_overview')), (self.admin, reverse('exams:admin_overview'))]

    def test_allowed_denied_expired_not_started_trial(self):
        pages = self.pages()
        for user, url in pages:
            self.assertEqual(self.get(user, url).status_code, 200, url)
        for state in ('none', 'expired', 'future'):
            SchoolModule.objects.filter(school=self.a).delete()
            if state == 'expired':
                grant(self.a, 'exams', starts_on=TODAY() - timedelta(days=9), ends_on=TODAY() - timedelta(days=1))
            if state == 'future':
                grant(self.a, 'exams', starts_on=TODAY() + timedelta(days=2))
            for user, url in pages:
                self.assertEqual(self.get(user, url).status_code, 403, (state, url))
        SchoolModule.objects.filter(school=self.a).delete()
        SchoolModule.objects.create(school=self.a, module_key='exams', kind='trial', starts_on=TODAY() - timedelta(days=1),
                                    ends_on=TODAY() + timedelta(days=5))
        for user, url in pages:
            self.assertEqual(self.get(user, url).status_code, 200, ('trial', url))

    def test_cross_school_and_roles(self):
        exam = self.exam([self.question()])
        self.assertEqual(self.get(self.tb, reverse('exams:exam_results', args=[exam.pk])).status_code, 404)
        self.assertEqual(self.get(self.tb, reverse('exams:exam_edit', args=[exam.pk])).status_code, 404)
        self.assertEqual(self.get(self.tart, reverse('exams:exam_results', args=[exam.pk])).status_code, 404)      # other subject
        self.assertEqual(self.get(self.admin_b, reverse('exams:admin_overview')).context['blocks'][0]['school'], self.b)
        for user in (self.parent, self.stu7, self.counselor):
            for name in ('import_form', 'lead_overview', 'admin_overview'):
                self.assertEqual(self.get(user, reverse(f'exams:{name}')).status_code, 403, (user.username, name))
        self.assertEqual(self.get(self.t1, reverse('exams:lead_overview')).status_code, 403)
        self.assertEqual(self.get(self.lead, reverse('exams:admin_overview')).status_code, 403)
        self.assertEqual(self.get(self.admin, reverse('exams:lead_overview')).status_code, 403)

    def test_trial_data_is_readable_again_after_a_licensed_row_is_added(self):
        SchoolModule.objects.filter(school=self.a).delete()
        SchoolModule.objects.create(school=self.a, module_key='exams', kind='trial', starts_on=TODAY() - timedelta(days=3),
                                    ends_on=TODAY() + timedelta(days=3))
        self.assertEqual(self.upload(self.t1, csv_bytes(GOOD)).status_code, 302)
        self.assertEqual(self.confirm(self.t1).status_code, 302)
        SchoolModule.objects.filter(school=self.a).update(ends_on=TODAY() - timedelta(days=1))
        self.assertEqual(self.upload(self.t1, csv_bytes(GOOD.replace('3/6', '4/8'))).status_code, 403)          # no write when ended
        self.assertEqual(Question.objects.filter(source='csv').count(), 1)                                        # retained
        grant(self.a, 'exams', starts_on=TODAY())
        self.assertContains(self.get(self.t1, reverse('exams:teacher_home')), 'What is 3/6?')


class CsvImportTests(SliceBase):
    def test_dry_run_writes_nothing_then_confirm_creates_drafts(self):
        response = self.upload(self.t1, csv_bytes(GOOD, GOOD.replace('3/6', '2/4')))
        self.assertRedirects(response, reverse('exams:import_preview'), fetch_redirect_response=False)
        self.assertEqual(Question.objects.count(), 0)
        page = self.get(self.t1, reverse('exams:import_preview'))
        self.assertEqual((page.context['good'], page.context['bad']), (2, 0))
        self.assertEqual(Question.objects.count(), 0)                                                          # preview writes nothing
        self.assertEqual(self.confirm(self.t1).status_code, 302)
        questions = list(Question.objects.order_by('pk'))
        self.assertEqual([(q.status, q.source, q.author_id, q.school_id, q.subject) for q in questions],
                         [('draft', 'csv', self.t1.pk, self.a.pk, 'math')] * 2)
        self.assertEqual([(o.order, o.is_correct) for o in questions[0].options.all()], [(1, False), (2, True), (3, False)])
        self.assertTrue(all(o.explanation for q in questions for o in q.options.all()))
        self.assertEqual(self.confirm(self.t1).status_code, 302)                                               # nothing left to confirm
        self.assertEqual(Question.objects.count(), 2)

    def test_bad_rows_are_reported_and_not_imported(self):
        bad = [GOOD.replace('math.ch3.fractions', 'math.ch9.nope'),                                            # unknown topic
               'math.ch3.fractions,,2,a,x,b,y,,,,,,',                                                         # no stem
               'math.ch3.fractions,One option?,1,a,x,,,,,,,,',                                                # one option
               'math.ch3.fractions,No explanation?,1,a,x,b,,,,,,,',                                           # explanation missing
               'math.ch3.fractions,Bad correct?,3,a,x,b,y,,,,,,',                                             # correct points at an empty option
               GOOD, GOOD]                                                                                    # the second GOOD duplicates the first
        self.upload(self.t1, csv_bytes(*bad))
        page = self.get(self.t1, reverse('exams:import_preview'))
        self.assertEqual((page.context['good'], page.context['bad']), (1, 6))
        self.confirm(self.t1)
        self.assertEqual(Question.objects.count(), 1)

    def test_existing_stem_topic_of_another_subject_and_other_scope_are_refused(self):
        self.question(stem='What is 3/6?')
        self.upload(self.t1, csv_bytes(GOOD))
        self.assertEqual(self.get(self.t1, reverse('exams:import_preview')).context['bad'], 1)                # duplicate of the bank
        self.upload(self.t1, csv_bytes(GOOD.replace('math.ch3.fractions', 'art.ch1.color')))
        self.assertEqual(self.get(self.t1, reverse('exams:import_preview')).context['bad'], 1)                # topic of another subject
        self.client.force_login(self.t1)
        refused = self.client.post(reverse('exams:import_form'), {'scope': f'{self.b.pk}:math',
                                                                   'file': SimpleUploadedFile('q.csv', csv_bytes(GOOD))})
        self.assertEqual(refused.status_code, 200)                                                             # not the teacher's scope
        self.upload(self.tart, csv_bytes(GOOD), scope=f'{self.a.pk}:math')
        self.assertEqual(Question.objects.filter(source='csv').count(), 0)

    def test_whole_file_problems(self):
        for data in (b'', b'a,b\n1,2\n', ('\n'.join([HEADER] + [GOOD] * 201)).encode(), b'\xff\xfe\x00bad', b'x' * (200 * 1024 + 1)):
            response = self.upload(self.t1, data)
            self.assertEqual(response.status_code, 200)                                                        # stays on the form, with a message
            self.assertNotIn('exam_csv', self.client.session)
        self.assertEqual(Question.objects.count(), 0)

    def test_session_rows_are_revalidated_at_confirm_and_bound_to_the_user(self):
        self.upload(self.t1, csv_bytes(GOOD))
        self.question(stem='What is 3/6?')                                                                     # appears after the preview
        self.confirm(self.t1)
        self.assertEqual(Question.objects.filter(source='csv').count(), 0)
        self.upload(self.t1, csv_bytes(GOOD.replace('3/6', '5/10')))
        stolen = self.client.session['exam_csv']
        self.client.force_login(self.t1b)
        session = self.client.session
        session['exam_csv'] = stolen
        session.save()
        self.client.post(reverse('exams:import_confirm'))
        self.assertEqual(Question.objects.filter(source='csv').count(), 0)                                     # another user's rows

    def test_template_and_audit(self):
        template = self.get(self.t1, reverse('exams:import_template'))
        self.assertEqual(template['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('o5_expl', template.content.decode('utf-8-sig'))
        self.upload(self.t1, csv_bytes(GOOD, 'math.ch3.fractions,,2,a,x,b,y,,,,,,'))
        self.confirm(self.t1)
        event = AuditEvent.objects.get(action='exam_csv_import')
        self.assertEqual(event.detail, 'c1e1f0')
        self.assertNotIn('3/6', f'{event.detail}{event.object_type}{event.object_id}')


class ExamEditTests(SliceBase):
    def setUp(self):
        super().setUp()
        self.q1, self.q2 = self.question(stem='first'), self.question(stem='second')
        self.exam1 = self.exam([self.q1])
        self.url = reverse('exams:exam_edit', args=[self.exam1.pk])

    def data(self, **over):
        data = {'title': 'Renamed', 'questions': [self.q1.pk, self.q2.pk], 'classes': [self.c7.pk], 'published': 'on',
                'opens_on': '2030-01-01', 'closes_on': '2030-02-01'}
        data.update(over)
        return data

    def test_creator_edits_everything_before_the_first_session(self):
        page = self.get(self.t1, self.url)
        self.assertContains(page, 'value="Fractions"')
        self.assertEqual(self.post(self.t1, self.url, self.data()).status_code, 302)
        self.exam1.refresh_from_db()
        self.assertEqual((self.exam1.title, self.exam1.published, [i.question_id for i in self.exam1.items.order_by('order')]),
                         ('Renamed', True, [self.q1.pk, self.q2.pk]))
        self.assertEqual(self.exam1.opens_on.isoformat(), '2030-01-01')
        self.assertEqual(self.post(self.t1, self.url, self.data(published='')).status_code, 302)
        self.exam1.refresh_from_db()
        self.assertFalse(self.exam1.published)

    def test_after_a_session_the_question_set_is_locked_but_the_rest_edits(self):
        self.post(self.stu7, self.play_url(self.exam1), {'option': self.q1.options.get(order=1).pk})
        self.assertTrue(ExamSession.objects.exists())
        self.assertEqual(self.post(self.t1, self.url, self.data(title='After')).status_code, 302)
        self.exam1.refresh_from_db()
        self.assertEqual((self.exam1.title, [i.question_id for i in self.exam1.items.all()]), ('After', [self.q1.pk]))
        self.assertTrue(QuestionAttempt.objects.filter(attempt_count=1).exists())                              # history untouched

    def test_rules(self):
        self.assertEqual(self.post(self.t1b, self.url, self.data()).status_code, 403)                          # a colleague
        self.assertEqual(self.get(self.t1b, self.url).status_code, 403)
        self.assertEqual(self.get(self.tart, self.url).status_code, 404)
        for bad in ({'title': ''}, {'classes': []}, {'classes': [self.c8.pk]}, {'questions': []}, {'questions': [self.question(status='draft').pk]},
                    {'opens_on': '2030-03-01', 'closes_on': '2030-02-01'}):
            self.assertEqual(self.post(self.t1, self.url, self.data(**bad)).status_code, 200, bad)
        self.exam1.refresh_from_db()
        self.assertEqual(self.exam1.title, 'Fractions')


class ResultsTests(SliceBase):
    def setUp(self):
        super().setUp()
        self.questions = [self.question(stem=f'q{n}') for n in range(5)]
        self.exam1 = self.exam(self.questions)
        self.s7b = self.student('Aaa', self.c7, 7)
        self.u7b = make_user('u7b', 'Student')
        self.s7b.student_user = self.u7b
        self.s7b.save(update_fields=['student_user'])
        self.play_all(self.stu7, self.exam1, wrong_first=True)                                                 # 0 first-try of 5
        self.play_all(self.u7b, self.exam1)                                                                    # 5 first-try of 5
        self.url = reverse('exams:exam_results', args=[self.exam1.pk])

    def test_teacher_sees_own_class_students_in_name_order_with_floors(self):
        page = self.get(self.t1, self.url)
        rows = page.context['rows']
        self.assertEqual([r['student'].first_name for r in rows], ['Aaa', 'Seven'])                            # name order, not score order
        by = {r['student'].first_name: r for r in rows}
        self.assertEqual((by['Aaa']['solved'], by['Aaa']['first_try'], by['Aaa']['rate']), (5, 5, 1.0))
        self.assertEqual((by['Seven']['first_try'], by['Seven']['rate']), (0, 0.0))
        self.assertContains(page, 'تمرین است، نه امتحان')
        self.assertEqual(AuditEvent.objects.get(action='exam_results_view').detail, 's2')

    def test_a_student_below_the_question_floor_gets_no_percentage(self):
        small = self.exam(self.questions[:2])
        small.title = 'small'
        small.save()
        self.play_all(self.stu7, small)
        summary = analytics.student_summary(list(QuestionAttempt.objects.filter(session__exam=small)))
        self.assertEqual((summary['solved'], summary['rate']), (2, None))

    def test_students_outside_the_teachers_classes_are_not_listed(self):
        s8 = self.student('Other', self.c8, 8)
        TeacherAssign = __import__('schools.models', fromlist=['TeacherAssignment']).TeacherAssignment
        t8 = make_user('t8', 'Teacher', self.a)
        TeacherAssign.objects.create(teacher=t8, school_class=self.c8, subject='math')
        Exam.objects.get(pk=self.exam1.pk).classes.add(self.c8)
        names = [r['student'].first_name for r in self.get(self.t1, self.url).context['rows']]
        self.assertNotIn('Other', names)
        self.assertEqual([r['student'].first_name for r in self.get(t8, self.url).context['rows']], ['Eight', 'Other'])   # t8 only sees class 8-A
        self.assertEqual(s8.school_id, self.a.pk)

    def test_question_stats_withhold_small_groups_and_never_rank(self):
        stats = self.get(self.t1, self.url).context['questions']
        self.assertEqual([s['question'].stem for s in stats], [f'q{n}' for n in range(5)])                      # exam order
        self.assertTrue(all(s['attempts'] == 2 and s['first_try_rate'] is None and s['median_seconds'] is None for s in stats))
        self.assertTrue(all(s['top_wrong'].order == 1 for s in stats))                                          # the option chosen wrong

    def test_group_floor_reveals_aggregates_at_five(self):
        for n in range(3):
            student = self.student(f'Extra{n}', self.c7, 7)
            user = make_user(f'ex{n}', 'Student')
            student.student_user = user
            student.save(update_fields=['student_user'])
            self.play_all(user, self.exam1)
        stats = self.get(self.t1, self.url).context['questions']
        self.assertTrue(all(s['attempts'] == 5 and s['first_try_rate'] == 0.8 for s in stats))                  # 4 of 5 first try


class LeadAndAdminTests(SliceBase):
    def setUp(self):
        super().setUp()
        self.questions = [self.question(stem=f'q{n}') for n in range(5)]
        self.exam1 = self.exam(self.questions)
        self.play_all(self.stu7, self.exam1, wrong_first=True)

    def test_grade_lead_sees_own_grade_by_name_with_floors_and_no_ranking(self):
        extra = self.student('Aaa', self.c7, 7)
        page = self.get(self.lead, reverse('exams:lead_overview'))
        self.assertEqual([r['student'].first_name for r in page.context['rows']], ['Aaa', 'Seven'])
        self.assertEqual(page.context['subjects'], ['math'])
        cell = {r['student'].first_name: r['cells'][0] for r in page.context['rows']}
        self.assertEqual((cell['Seven']['solved'], cell['Seven']['rate']), (5, 0.0))
        self.assertEqual(cell['Aaa']['solved'], 0)
        self.assertNotContains(page, 'Eight')                                                                   # grade 8 is not theirs
        self.assertEqual(extra.school_id, self.a.pk)
        self.assertTrue(AuditEvent.objects.filter(action='exam_gradelead_view').exists())

    def test_school_admin_sees_aggregates_only_and_small_groups_are_withheld(self):
        page = self.get(self.admin, reverse('exams:admin_overview'))
        block = page.context['blocks'][0]
        self.assertEqual(block['school'], self.a)
        entry = block['exams'][0]
        self.assertEqual((entry['shown'], entry['started'], entry['topics']), (False, None, []))               # 1 student < 5
        for text in ('Seven', 'q0'):
            self.assertNotContains(page, text)
        for n in range(4):
            student = self.student(f'Extra{n}', self.c7, 7)
            user = make_user(f'ad{n}', 'Student')
            student.student_user = user
            student.save(update_fields=['student_user'])
            self.play_all(user, self.exam1)
        entry = self.get(self.admin, reverse('exams:admin_overview')).context['blocks'][0]['exams'][0]
        self.assertEqual((entry['shown'], entry['started'], entry['finished']), (True, 5, 5))
        topic, n, rate = entry['topics'][0]
        self.assertEqual((topic.code, n, rate), ('math.ch3.fractions', 5, 0.8))
        self.assertTrue(AuditEvent.objects.filter(action='exam_admin_view', school=self.a).exists())

    def test_menu_entries(self):
        self.assertIn(reverse('exams:lead_overview'), self.get(self.lead, reverse('dashboard:profile')).content.decode())
        self.assertIn(reverse('exams:admin_overview'), self.get(self.admin, reverse('dashboard:profile')).content.decode())
        SchoolModule.objects.filter(school=self.a).delete()
        self.assertNotIn(reverse('exams:lead_overview'), self.get(self.lead, reverse('dashboard:profile')).content.decode())
