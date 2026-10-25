"""Exams Slice 1: module gating (allowed / denied / expired / not started / trial / cross-school / trial data readable after a
licensed row), authoring scope, the explanation-for-every-option rule, exams and their audience, and the practice player
(red/green feedback, retry until correct, time / attempts / wrong options in order, never a grade). Synthetic data only."""
from datetime import date, timedelta
from unittest import mock

from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from dashboard.test_counselor import Base, make_user
from schools.models import AuditEvent, SchoolModule, TeacherAssignment
from schools.module_grants import grant
from students.models import Grade
from vocabulary.models import EXAM_TOPIC, VocabularyTerm

from .models import Exam, ExamQuestion, ExamSession, Option, Question, QuestionAttempt

TODAY = timezone.localdate
EXPLAIN = {1: 'why-wrong-A', 2: 'why-RIGHT-B', 3: 'why-wrong-C'}


class ExamBase(Base):
    def setUp(self):
        super().setUp()
        SchoolModule.objects.all().delete()
        grant(self.a, 'exams')
        grant(self.b, 'exams')
        self.t1 = make_user('t1', 'Teacher', self.a)              # math, class 7-A
        self.t1b = make_user('t1b', 'Teacher', self.a)            # a colleague, also math 7-A
        self.tart = make_user('tart', 'Teacher', self.a)          # art, class 7-A
        self.tb = make_user('tb', 'Teacher', self.b)
        for teacher, klass, subject in ((self.t1, self.c7, 'math'), (self.t1b, self.c7, 'math'), (self.tart, self.c7, 'art'),
                                        (self.tb, self.cb, 'math')):
            TeacherAssignment.objects.create(teacher=teacher, school_class=klass, subject=subject)
        self.stu7, self.stu8, self.stub = (make_user(n, 'Student') for n in ('stu7', 'stu8', 'stub'))
        for student, user in ((self.s7, self.stu7), (self.s8, self.stu8), (self.sb, self.stub)):
            student.student_user = user
            student.save(update_fields=['student_user'])
        self.topic = self.term(self.a, 'math.ch3.fractions', 'کسرها')
        self.topic_b = self.term(self.b, 'math.ch1.sets', 'مجموعه')
        self.topic_art = self.term(self.a, 'art.ch1.color', 'رنگ')

    def term(self, school, code, label):
        return VocabularyTerm.objects.create(school=school, domain=EXAM_TOPIC, code=code, label_fa=label, effective_from=date(2020, 1, 1))

    def question(self, author=None, school=None, subject='math', topic=None, status='approved', stem='2/4 equals?'):
        question = Question.objects.create(school=school or self.a, subject=subject, topic=topic or self.topic, stem=stem, status=status,
                                           author=author or self.t1)
        for order in (1, 2, 3):
            Option.objects.create(question=question, order=order, text=f'option {order}', is_correct=order == 2, explanation=EXPLAIN[order])
        return question

    def exam(self, questions, classes=None, published=True, creator=None, **kw):
        exam = Exam.objects.create(school=self.a, subject='math', title='Fractions', published=published, created_by=creator or self.t1, **kw)
        exam.classes.set(classes or [self.c7])
        for order, q in enumerate(questions, start=1):
            ExamQuestion.objects.create(exam=exam, question=q, order=order)
        return exam

    def get(self, user, url):
        self.client.force_login(user)
        return self.client.get(url)

    def post(self, user, url, data=None):
        self.client.force_login(user)
        return self.client.post(url, data or {})

    def question_post(self, user, **over):
        data = {'scope': f'{self.a.pk}:math', 'topic': self.topic.pk, 'stem': 'What is 1/2 + 1/2?', 'correct': '2',
                'o1_text': '0', 'o1_expl': 'no: that is subtraction', 'o2_text': '1', 'o2_expl': 'yes: two halves make a whole',
                'o3_text': '2', 'o3_expl': 'no: that would be two wholes'}
        data.update(over)
        return self.post(user, reverse('exams:question_new'), data)

    def play_url(self, exam):
        return reverse('exams:play', args=[exam.pk])

    def option(self, question, order):
        return question.options.get(order=order)


class GatingTests(ExamBase):
    def pages(self):
        q = self.question()
        exam = self.exam([q])
        return [(self.t1, reverse('exams:teacher_home')), (self.t1, reverse('exams:topics')), (self.t1, reverse('exams:question_new')),
                (self.t1, reverse('exams:question_edit', args=[q.pk])), (self.t1, reverse('exams:exam_new')),
                (self.stu7, reverse('exams:student_home')), (self.stu7, self.play_url(exam))]

    def test_allowed_denied_expired_not_started(self):
        for user, url in self.pages():
            self.assertEqual(self.get(user, url).status_code, 200, url)
        SchoolModule.objects.filter(school=self.a).delete()
        for user, url in self.pages_cached():
            self.assertEqual(self.get(user, url).status_code, 403, url)
        grant(self.a, 'exams', starts_on=TODAY() - timedelta(days=9), ends_on=TODAY() - timedelta(days=1))      # expired
        for user, url in self.pages_cached():
            self.assertEqual(self.get(user, url).status_code, 403, url)
        SchoolModule.objects.filter(school=self.a).delete()
        grant(self.a, 'exams', starts_on=TODAY() + timedelta(days=2))                                           # not started
        for user, url in self.pages_cached():
            self.assertEqual(self.get(user, url).status_code, 403, url)

    def pages_cached(self):
        q, exam = Question.objects.first(), Exam.objects.first()
        return [(self.t1, reverse('exams:teacher_home')), (self.t1, reverse('exams:question_edit', args=[q.pk])),
                (self.stu7, reverse('exams:student_home')), (self.stu7, self.play_url(exam))]

    def test_a_trial_row_works(self):
        SchoolModule.objects.filter(school=self.a).delete()
        SchoolModule.objects.create(school=self.a, module_key='exams', kind='trial', starts_on=TODAY() - timedelta(days=1),
                                    ends_on=TODAY() + timedelta(days=5))
        self.assertEqual(self.get(self.t1, reverse('exams:teacher_home')).status_code, 200)
        self.assertEqual(self.get(self.stu7, reverse('exams:student_home')).status_code, 200)

    def test_cross_school(self):
        q, exam = self.question(), None
        exam = self.exam([q])
        self.assertEqual(self.get(self.tb, reverse('exams:question_edit', args=[q.pk])).status_code, 404)
        self.assertEqual(self.post(self.tb, reverse('exams:exam_unpublish', args=[exam.pk])).status_code, 404)
        self.assertEqual(self.get(self.stub, self.play_url(exam)).status_code, 404)                  # student of school B
        SchoolModule.objects.filter(school=self.a).delete()                                          # only B has the module
        self.assertEqual(self.get(self.t1, reverse('exams:teacher_home')).status_code, 403)
        self.assertEqual(self.get(self.tb, reverse('exams:teacher_home')).status_code, 200)

    def test_trial_data_is_readable_again_after_a_licensed_row_is_added(self):
        SchoolModule.objects.filter(school=self.a).delete()
        SchoolModule.objects.create(school=self.a, module_key='exams', kind='trial', starts_on=TODAY() - timedelta(days=3),
                                    ends_on=TODAY() + timedelta(days=3))
        self.assertEqual(self.question_post(self.t1, stem='trial-stem').status_code, 302)
        q = Question.objects.get(stem='trial-stem')
        q.status = 'approved'
        q.save()
        exam = self.exam([q])
        self.post(self.stu7, self.play_url(exam), {'option': self.option(q, 1).pk})                 # a recorded attempt
        SchoolModule.objects.filter(school=self.a).update(ends_on=TODAY() - timedelta(days=1))      # trial ended
        self.assertEqual(self.get(self.t1, reverse('exams:teacher_home')).status_code, 403)
        self.assertEqual(self.get(self.stu7, self.play_url(exam)).status_code, 403)
        self.assertEqual(self.question_post(self.t1, stem='after').status_code, 403)                # no write either
        self.assertEqual((Question.objects.count(), QuestionAttempt.objects.count()), (1, 1))        # data retained
        grant(self.a, 'exams', starts_on=TODAY())                                                   # licensed
        self.assertContains(self.get(self.t1, reverse('exams:teacher_home')), 'trial-stem')
        attempt = QuestionAttempt.objects.get()
        self.assertEqual((attempt.attempt_count, attempt.wrong_option_ids), (1, [self.option(q, 1).pk]))
        self.assertEqual(self.get(self.stu7, self.play_url(exam)).status_code, 200)

    def test_roles_are_separate(self):
        for user in (self.admin, self.lead, self.counselor, self.parent):
            self.assertEqual(self.get(user, reverse('exams:teacher_home')).status_code, 403, user.username)
            self.assertEqual(self.get(user, reverse('exams:student_home')).status_code, 403, user.username)
        self.assertEqual(self.get(self.stu7, reverse('exams:teacher_home')).status_code, 403)
        self.assertEqual(self.get(self.t1, reverse('exams:student_home')).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('exams:student_home')).status_code, 302)


class AuthoringTests(ExamBase):
    def test_a_question_needs_an_explanation_for_every_option(self):
        before = Question.objects.count()
        response = self.question_post(self.t1, o3_expl='')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'توضیح لازم است')
        self.assertEqual(Question.objects.count(), before)
        self.assertEqual(self.question_post(self.t1, correct='').status_code, 200)
        self.assertEqual(self.question_post(self.t1, o2_text='', o2_expl='x', correct='1').status_code, 200)   # option without text
        self.assertEqual(Question.objects.count(), before)

    def test_save_creates_a_draft_with_one_correct_option_and_explanations(self):
        self.assertEqual(self.question_post(self.t1).status_code, 302)
        q = Question.objects.get()
        self.assertEqual((q.status, q.source, q.author_id, q.school_id, q.subject), ('draft', 'teacher', self.t1.pk, self.a.pk, 'math'))
        self.assertEqual([(o.order, o.is_correct, bool(o.explanation)) for o in q.options.all()], [(1, False, True), (2, True, True), (3, False, True)])

    def test_subject_topic_and_school_are_limited_to_the_teachers_scope(self):
        self.assertEqual(self.question_post(self.tart).status_code, 200)                          # art teacher, math scope
        self.assertEqual(self.question_post(self.t1, topic=self.topic_art.pk).status_code, 200)   # a topic of another subject
        self.assertEqual(self.question_post(self.t1, topic=self.topic_b.pk).status_code, 200)     # a topic of another school
        self.assertEqual(self.question_post(self.t1, scope=f'{self.b.pk}:math').status_code, 200)
        self.assertEqual(Question.objects.count(), 0)
        self.assertEqual(self.question_post(self.tart, scope=f'{self.a.pk}:art', topic=self.topic_art.pk).status_code, 302)

    def test_colleagues_read_but_only_the_author_edits_approves_and_retires(self):
        q = self.question(status='draft')
        url = reverse('exams:question_edit', args=[q.pk])
        page = self.get(self.t1b, url)
        self.assertEqual(page.status_code, 200)
        self.assertTrue(page.context['read_only'])
        self.assertEqual(self.post(self.t1b, url, {}).status_code, 403)
        for action in ('approve', 'retire'):
            self.assertEqual(self.post(self.t1b, reverse('exams:question_status', args=[q.pk]), {'action': action}).status_code, 403)
        self.assertEqual(self.get(self.tart, url).status_code, 404)                              # another subject: out of scope
        self.post(self.t1, reverse('exams:question_status', args=[q.pk]), {'action': 'approve'})
        q.refresh_from_db()
        self.assertEqual((q.status, q.approved_by_id), ('approved', self.t1.pk))
        self.post(self.t1, reverse('exams:question_status', args=[q.pk]), {'action': 'retire'})
        q.refresh_from_db()
        self.assertEqual(q.status, 'retired')
        self.post(self.t1, reverse('exams:question_status', args=[q.pk]), {'action': 'approve'})   # not allowed from retired
        q.refresh_from_db()
        self.assertEqual(q.status, 'retired')

    def test_editing_resets_to_draft_and_is_closed_after_the_first_attempt(self):
        q = self.question()
        url = reverse('exams:question_edit', args=[q.pk])
        data = {'scope': f'{self.a.pk}:math', 'topic': self.topic.pk, 'stem': 'edited', 'correct': '1', 'o1_text': 'a', 'o1_expl': 'x', 'o2_text': 'b', 'o2_expl': 'y'}
        self.assertEqual(self.post(self.t1, url, data).status_code, 302)
        q.refresh_from_db()
        self.assertEqual((q.status, q.stem, q.options.count()), ('draft', 'edited', 2))
        q.status = 'approved'
        q.save()
        exam = self.exam([q])
        self.post(self.stu7, self.play_url(exam), {'option': q.options.first().pk})
        self.assertEqual(self.post(self.t1, url, data).status_code, 403)
        self.assertTrue(self.get(self.t1, url).context['read_only'])

    def test_topics_are_flat_hierarchical_codes_added_within_the_own_scope(self):
        url = reverse('exams:topics')
        good = {'scope': f'{self.a.pk}:math', 'chapter': '4', 'concept': 'decimals', 'label_fa': 'اعشار'}
        self.assertEqual(self.post(self.t1, url, good).status_code, 302)
        term = VocabularyTerm.objects.get(code='math.ch4.decimals')
        self.assertEqual((term.domain, term.school_id), (EXAM_TOPIC, self.a.pk))
        for bad in ({**good, 'concept': 'Decimals!'}, {**good, 'chapter': '0'}, {**good, 'label_fa': ''}, good,             # duplicate
                    {**good, 'scope': f'{self.a.pk}:art', 'concept': 'x1'}, {**good, 'scope': f'{self.b.pk}:math', 'concept': 'x2'}):
            self.assertEqual(self.post(self.t1, url, bad).status_code, 200, bad)
        self.assertEqual(VocabularyTerm.objects.filter(domain=EXAM_TOPIC, code__startswith='math.ch4').count(), 1)
        self.assertEqual(self.get(self.t1, url).status_code, 200)
        self.assertContains(self.get(self.t1, url), 'math.ch3.fractions')

    def test_model_rules(self):
        q = self.question()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Option.objects.create(question=q, order=4, text='x', explanation='', is_correct=False)       # explanation required
        with self.assertRaises(IntegrityError), transaction.atomic():
            Option.objects.create(question=q, order=5, text='x', explanation='e', is_correct=True)       # second correct option
        with self.assertRaises(ValidationError):
            Question.objects.create(school=self.a, subject='math', topic=self.topic_art, stem='x')       # topic of another subject
        draft = self.question(status='draft')
        exam = Exam.objects.create(school=self.a, subject='math', title='t')
        with self.assertRaises(ValidationError):
            ExamQuestion.objects.create(exam=exam, question=draft, order=1)                              # unapproved
        art = self.question(subject='art', topic=self.topic_art, author=self.tart)
        with self.assertRaises(ValidationError):
            ExamQuestion.objects.create(exam=exam, question=art, order=1)                                # another subject


class ExamCreationAndAudienceTests(ExamBase):
    def new(self, user, **over):
        q = self.question()
        data = {'scope': f'{self.a.pk}:math', 'title': 'Quiz', 'questions': [q.pk], 'classes': [self.c7.pk], 'published': 'on'}
        data.update(over)
        return self.post(user, reverse('exams:exam_new'), data), q

    def test_create_and_audience(self):
        response, q = self.new(self.t1)
        self.assertEqual(response.status_code, 302)
        exam = Exam.objects.get()
        self.assertEqual((exam.published, [i.question_id for i in exam.items.all()], list(exam.classes.all())), (True, [q.pk], [self.c7]))
        self.assertContains(self.get(self.stu7, reverse('exams:student_home')), 'Quiz')
        self.assertEqual(self.get(self.stu7, self.play_url(exam)).status_code, 200)
        self.assertEqual(self.get(self.stu8, self.play_url(exam)).status_code, 404)                 # class 8-A is not targeted
        self.assertNotContains(self.get(self.stu8, reverse('exams:student_home')), 'Quiz')

    def test_rules(self):
        q = self.question()
        draft = self.question(status='draft')
        art_q = self.question(subject='art', topic=self.topic_art, author=self.tart)
        for bad in ({'questions': [draft.pk]}, {'questions': [art_q.pk]}, {'questions': []}, {'classes': []}, {'classes': [self.c8.pk]},
                    {'title': ''}, {'opens_on': '2026-02-02', 'closes_on': '2026-01-01'}, {'scope': f'{self.a.pk}:art'},
                    {'questions': [q.pk, 99999]}):
            response, _ = self.new(self.t1, **bad)
            self.assertEqual(response.status_code, 200, bad)
        self.assertEqual(Exam.objects.count(), 0)
        self.assertEqual(self.new(self.tart)[0].status_code, 200)                                    # the art teacher cannot build a math exam

    def test_window_and_publication(self):
        q = self.question()
        exam = self.exam([q], opens_on=TODAY() + timedelta(days=1))
        self.assertEqual(self.get(self.stu7, self.play_url(exam)).status_code, 404)                 # not open yet
        Exam.objects.filter(pk=exam.pk).update(opens_on=None, closes_on=TODAY() - timedelta(days=1))
        self.assertEqual(self.get(self.stu7, self.play_url(exam)).status_code, 404)                 # closed
        Exam.objects.filter(pk=exam.pk).update(closes_on=None)
        self.assertEqual(self.get(self.stu7, self.play_url(exam)).status_code, 200)
        self.assertEqual(self.post(self.t1b, reverse('exams:exam_unpublish', args=[exam.pk])).status_code, 403)   # not the creator
        self.assertEqual(self.post(self.t1, reverse('exams:exam_unpublish', args=[exam.pk])).status_code, 302)
        self.assertEqual(self.get(self.stu7, self.play_url(exam)).status_code, 404)


class PlayerTests(ExamBase):
    def setUp(self):
        super().setUp()
        self.q1 = self.question(stem='first question')
        self.q2 = self.question(stem='second question')
        self.exam1 = self.exam([self.q1, self.q2])
        self.url = self.play_url(self.exam1)

    def answer(self, question, order, user=None):
        return self.post(user or self.stu7, self.url, {'option': self.option(question, order).pk})

    def test_the_question_page_leaks_no_explanation_or_correctness(self):
        page = self.get(self.stu7, self.url)
        self.assertContains(page, 'first question')
        for text in EXPLAIN.values():
            self.assertNotContains(page, text)
        self.assertNotContains(page, 'second question')                                             # one question at a time
        self.assertFalse(any(o['state'] for o in page.context['options']))
        self.assertEqual({o['explanation'] for o in page.context['options']}, {''})                 # not even in the template context
        self.assertTrue(all(set(o) == {'pk', 'text', 'state', 'explanation'} for o in page.context['options']))

    def test_wrong_turns_red_with_its_own_explanation_then_retry_until_correct(self):
        page = self.answer(self.q1, 1)
        self.assertContains(page, 'alert-danger')
        self.assertContains(page, 'why-wrong-A')
        self.assertNotContains(page, 'why-wrong-C')
        self.assertNotContains(page, 'why-RIGHT-B')
        self.assertContains(page, 'دوباره تلاش کنید')
        again = self.get(self.stu7, self.url)                                                       # the red state survives a reload
        self.assertContains(again, 'why-wrong-A')
        self.answer(self.q1, 3)
        page = self.answer(self.q1, 2)                                                              # correct
        self.assertContains(page, 'alert-success')
        self.assertContains(page, 'why-RIGHT-B')
        self.assertTrue(page.context['solved_now'])
        attempt = QuestionAttempt.objects.get(question=self.q1)
        self.assertEqual((attempt.attempt_count, attempt.wrong_option_ids, attempt.solved_at is not None),
                         (3, [self.option(self.q1, 1).pk, self.option(self.q1, 3).pk], True))
        self.assertContains(self.get(self.stu7, self.url), 'second question')                       # next question

    def test_repeating_a_red_option_changes_nothing(self):
        self.answer(self.q1, 1)
        self.answer(self.q1, 1)
        attempt = QuestionAttempt.objects.get()
        self.assertEqual((attempt.attempt_count, len(attempt.wrong_option_ids)), (1, 1))

    def test_an_option_of_another_question_is_refused(self):
        self.assertEqual(self.post(self.stu7, self.url, {'option': self.option(self.q2, 1).pk}).status_code, 404)
        self.assertEqual(self.post(self.stu7, self.url, {'option': 'x'}).status_code, 404)
        self.assertEqual(QuestionAttempt.objects.filter(attempt_count__gt=0).count(), 0)

    def test_time_is_recorded_per_step_and_clamped(self):
        t0 = timezone.now()
        with mock.patch('django.utils.timezone.now', return_value=t0):
            self.get(self.stu7, self.url)                                                           # question shown
        with mock.patch('django.utils.timezone.now', return_value=t0 + timedelta(seconds=30)):
            self.answer(self.q1, 1)                                                                 # wrong after 30 s
        with mock.patch('django.utils.timezone.now', return_value=t0 + timedelta(seconds=30 + 10_000)):
            self.answer(self.q1, 2)                                                                 # correct after a forgotten tab
        attempt = QuestionAttempt.objects.get()
        self.assertEqual(attempt.seconds_spent, 30 + 300)                                          # 30 s + the 300 s clamp
        self.assertEqual(attempt.attempt_count, 2)

    def test_finishing_is_practice_only_and_never_writes_a_grade(self):
        grades = Grade.objects.count()
        self.answer(self.q1, 2)
        self.get(self.stu7, self.url)
        page = self.answer(self.q2, 2)
        self.assertTrue(page.context['solved_now'])
        done = self.get(self.stu7, self.url)
        self.assertContains(done, 'نمره‌ای ثبت نمی‌شود')
        session = ExamSession.objects.get()
        self.assertIsNotNone(session.finished_at)
        self.assertEqual(Grade.objects.count(), grades)
        self.assertEqual(self.get(self.stu7, reverse('exams:student_home')).context['rows'][0]['solved'], 2)

    def test_students_have_separate_sessions_and_the_exam_is_class_scoped(self):
        s7b = self.student('SevenB', self.c7, 7)
        stu_b = make_user('stu7b', 'Student')
        s7b.student_user = stu_b
        s7b.save(update_fields=['student_user'])
        self.answer(self.q1, 1)
        self.post(stu_b, self.url, {'option': self.option(self.q1, 2).pk})
        self.assertEqual(ExamSession.objects.count(), 2)
        mine = QuestionAttempt.objects.get(session__student=self.s7)
        theirs = QuestionAttempt.objects.get(session__student=s7b)
        self.assertEqual((mine.attempt_count, theirs.attempt_count, theirs.wrong_option_ids), (1, 1, []))

    def test_parents_and_unlinked_students_cannot_play(self):
        self.assertEqual(self.get(self.parent, self.url).status_code, 403)
        loner = make_user('loner', 'Student')
        self.assertEqual(self.get(loner, self.url).status_code, 403)           # no school: the module is not on for this user


class AuditAndMenuTests(ExamBase):
    def test_audit_has_ids_and_counts_but_no_text(self):
        self.post(self.t1, reverse('exams:topics'), {'scope': f'{self.a.pk}:math', 'chapter': '5', 'concept': 'angles', 'label_fa': 'secret-label'})
        self.question_post(self.t1, stem='secret-stem')
        q = Question.objects.get()
        self.post(self.t1, reverse('exams:question_status', args=[q.pk]), {'action': 'approve'})
        self.post(self.t1, reverse('exams:exam_new'), {'scope': f'{self.a.pk}:math', 'title': 'secret-title', 'questions': [q.pk],
                                                       'classes': [self.c7.pk], 'published': 'on'})
        exam = Exam.objects.get()
        self.post(self.t1, reverse('exams:exam_unpublish', args=[exam.pk]))
        events = AuditEvent.objects.filter(action__startswith='exam_')
        self.assertEqual(set(events.values_list('action', flat=True)),
                         {'exam_topic_add', 'exam_question_save', 'exam_question_status', 'exam_create', 'exam_unpublish'})
        self.assertEqual(events.get(action='exam_create').detail, 'q1c1')
        self.assertFalse(any('secret' in str(v) for e in events for v in (e.detail, e.object_type, e.object_id)))

    def test_menu_entries_follow_the_module(self):
        self.assertIn(reverse('exams:teacher_home'), self.get(self.t1, reverse('dashboard:profile')).content.decode())
        self.assertIn(reverse('exams:student_home'), self.get(self.stu7, reverse('dashboard:profile')).content.decode())
        SchoolModule.objects.filter(school=self.a).delete()
        self.assertNotIn(reverse('exams:teacher_home'), self.get(self.t1, reverse('dashboard:profile')).content.decode())
        self.assertNotIn(reverse('exams:student_home'), self.get(self.stu7, reverse('dashboard:profile')).content.decode())
