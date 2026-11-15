"""End-to-end QA of the staff user journey (QA audit of 2026-11-14; report: ``E2E_AUDIT_REPORT.md``).

Everything here goes through the real Django stack: real URL routing, real login form, real
templates, real ORM writes and the real ``docqa`` service layer. Only the FastAPI boundary is
replaced (``docqa.services.requests``), because FastAPI is a separate process; its own leg lives in
``fastapi_core/tests/test_e2e_llm_flow.py`` and is exercised over real HTTP there. All data is
synthetic.

Two kinds of test:

* plain tests assert behaviour that is CORRECT today (a regression here is a real bug);
* ``@unittest.expectedFailure`` tests assert the TARGET behaviour of a finding (Fxx) that the
  current code does not meet. Each carries its finding id, and each has a plain companion test
  proving the request really reaches the code path under test -- so an expected failure cannot be
  "passing" because of a broken fixture (if a finding is fixed, unittest reports an unexpected
  success and this file is updated).

Run from django_core/:  python manage.py test dashboard.test_e2e_user_flow -v 2
"""
import io
import re
import time
import unittest
import zipfile
from datetime import date, timedelta
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from docqa import services
from docqa.extract import MAX_BYTES
from docqa.models import AssistantSettings, SchoolDocument
from risk.loop_testing import LoopBase
from schools import audit, entitlements
from schools.models import AICallUsage, AuditEvent

PASSWORD = 'Str0ng-demo-pass-77'
# SERVICE_JWT_SECRET must be >= 32 chars, not a known placeholder and not settings.SECRET_KEY
# (config/service_auth.py); the AI branch of services.ask() signs a token before any network call.
SECRET = 'e2e-audit-' + 'abcdefghijklmnopqrstuvwxyz0123456789'
MODULE = 'advisor_ai'
GOOD_QUESTION = 'ساعت شروع کلاس‌ها چه زمانی است؟'
HANDBOOK = 'ساعت شروع کلاس‌ها هشت صبح است.\n\nغیبت موجه نیازمند گواهی پزشک است.'
HANDBOOK_B = 'ساعت شروع کلاس‌ها در مدرسهٔ دیگر نه صبح است. رمزعبور بیرونی.'
# The page prints Persian digits; float() accepts ASCII only. Display-only normalisation for assertions.
_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')


def docx(paragraphs):
    """A minimal, well-formed .docx (zip + word/document.xml) - the shape docqa/extract.py accepts."""
    body = ''.join(f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in paragraphs)
    xml = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f'<w:body>{body}</w:body></w:document>').encode()
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('word/document.xml', xml)
    return out.getvalue()


class _Response:
    """The attributes services.py / views.py use from a requests response."""

    def __init__(self, status_code, body=None, text=''):
        self.status_code, self._body, self.text = status_code, body, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ValueError(f'HTTP {self.status_code}')

    def json(self):
        if self._body is None:
            raise ValueError('no json')
        return self._body


class E2EUserJourney(LoopBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        today = date.today()
        for school in (self.a, self.b):
            entitlements.set_module(school, MODULE, today, today + timedelta(days=30), kind=entitlements.TRIAL)
        for user in (self.admin, self.admin_b, self.lead, self.teacher, self.counselor, self.parent):
            user.set_password(PASSWORD)
            user.save(update_fields=['password'])

    # ---------- helpers ----------
    def login(self, user):
        self.client.logout()
        return self.client.post(reverse('dashboard:login'),
                                {'username': user.get_username(), 'password': PASSWORD})

    def add_document(self, school, title, text):
        """A document put in place directly (the upload path itself is covered by tests 06/07)."""
        from docqa.models import DocumentChunk
        doc = SchoolDocument.objects.create(school=school, title=title, char_count=len(text))
        DocumentChunk.objects.bulk_create([DocumentChunk(document=doc, school=school, ordinal=i, text=c)
                                           for i, c in enumerate(services.chunk_text(text))])
        return doc

    def provider(self, *, enabled=True, kind='local', answer='ساعت شروع هشت صبح است [1].', status=200):
        """Patch the FastAPI boundary used by docqa.services; returns ``(get_mock, post_mock)``."""
        get = mock.Mock(return_value=_Response(200, {'enabled': True, 'class': kind} if enabled
                                              else {'enabled': False, 'class': None}))
        post = mock.Mock(return_value=_Response(status, {'text': answer, 'label': 'LABEL'}))
        patcher = mock.patch.multiple(services.requests, get=get, post=post)
        patcher.start()
        self.addCleanup(patcher.stop)
        return get, post

    def ask(self, question=GOOD_QUESTION, school=None, follow=True):
        url = reverse('docqa:home') + (f'?school={school.pk}' if school is not None else '')
        return self.client.post(url, {'question': question}, follow=follow)

    def upload(self, title='Handbook', text=HANDBOOK, filename='handbook.txt', attest='on'):
        data = text.encode('utf-8') if isinstance(text, str) else text
        payload = {'title': title, 'file': SimpleUploadedFile(filename, data)}
        if attest:
            payload['attest'] = attest
        return self.client.post(reverse('docqa:documents'), payload, follow=True)

    def enable_ai(self, school=None):
        return self.client.post(reverse('docqa:ai_setting'),
                                {'ai_enabled': 'on', 'school': (school or self.a).pk}, follow=True)

    def usage(self, school=None, module=MODULE):
        return AICallUsage.objects.filter(school=school or self.a, module_key=module,
                                          day=date.today()).values_list('count', flat=True).first() or 0

    def messages_of(self, response):
        return [str(m) for m in response.context['messages']] if response.context else []

    def rendered_risk_percent(self, html):
        """The percentage on the student page, as a number. F01: the page prints it in Persian digits (۰.۷ → ۷۰%), and
        ``\\d`` does match those, but ``float('۷۰')`` raises, so the captured digits are normalised to ASCII first."""
        match = re.search(r'احتمال ریسک[^<]*</strong>\s*([\d.]+)%', html)
        self.assertIsNotNone(match, 'the prediction block is missing from the detail page')
        return float(match.group(1).translate(_DIGITS))

class LoginJourneyTests(E2EUserJourney):
    def test_01_a_bad_password_shows_one_message_and_creates_no_session(self):
        response = self.client.post(reverse('dashboard:login'),
                                    {'username': self.admin.get_username(), 'password': 'not-the-password'})
        self.assertEqual(response.status_code, 200)                     # the form is re-rendered, not a redirect
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertContains(response, 'نام کاربری یا رمز عبور اشتباه است.')

    def test_02_the_admin_lands_on_the_school_dashboard(self):
        response = self.login(self.admin)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('dashboard:school_home'))
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.get(response['Location']).status_code, 200)

    def test_03_each_role_lands_on_its_own_home(self):
        for user, url in ((self.teacher, 'dashboard:teacher_home'),
                          (self.counselor, 'dashboard:counselor_home'),
                          (self.lead, 'dashboard:grade_dashboard'),
                          (self.parent, 'dashboard:student_list')):
            with self.subTest(role=user.groups.first().name):
                response = self.login(user)
                self.assertEqual((response.status_code, response['Location']), (302, reverse(url)))

    def test_04_a_login_redirect_never_leaves_the_site(self):
        """``safe_next``: an off-site ``?next=`` falls back to the role home instead of redirecting away."""
        response = self.client.post('/login/?next=https://evil.example/', {'username': self.admin.get_username(),
                                                                           'password': PASSWORD})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('dashboard:school_home'))


class StaffJourneyTests(E2EUserJourney):
    def test_05_the_staff_journey_home_list_detail_is_served_and_measured(self):
        self.client.force_login(self.admin)
        steps = [('school_home', reverse('dashboard:school_home')),
                 ('student_list', reverse('dashboard:student_list')),
                 ('student_detail', reverse('dashboard:student_detail', args=[self.s7.pk]))]
        for name, url in steps:
            with CaptureQueriesContext(connection) as queries:
                started = time.perf_counter()
                response = self.client.get(url)
                elapsed = time.perf_counter() - started
            print(f'[E2E] {name:14s} status={response.status_code} queries={len(queries):2d} '
                  f'model_calls={len(queries.captured_queries):2d} server_ms={elapsed * 1000:.0f}')
            self.assertEqual(response.status_code, 200)
            # F20: measured, not a target -- the principal dashboard answers with a lot of queries for one screen.
            self.assertLess(len(queries), 120, f'{name} runs {len(queries)} queries for one page')
        detail = self.client.get(reverse('dashboard:student_detail', args=[self.s7.pk]))
        self.assertContains(detail, self.s7.first_name)
        self.assertNotContains(detail, self.sb.first_name)              # another school never leaks into the page

    def test_06_another_schools_student_is_a_404(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('dashboard:student_detail', args=[self.sb.pk])).status_code, 404)

    def test_07_a_teacher_and_a_grade_lead_see_only_their_own_scope(self):
        """A student outside the scope is a 404 (not a 403) on purpose: the URL must not confirm that the id exists."""
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('dashboard:student_detail', args=[self.s7.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('dashboard:student_detail', args=[self.s8.pk])).status_code, 404)
        self.client.force_login(self.lead)
        self.assertEqual(self.client.get(reverse('dashboard:student_detail', args=[self.s7.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('dashboard:student_detail', args=[self.s8.pk])).status_code, 404)

    def test_08_the_students_list_is_not_the_place_for_a_counselor_or_a_student(self):
        for user in (self.counselor, self.student_user):
            with self.subTest(role=user.groups.first().name):
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse('dashboard:student_list')).status_code, 403)

class AssistantAccessTests(E2EUserJourney):
    def test_09_the_assistant_requires_a_login(self):
        response = self.client.get(reverse('docqa:home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('dashboard:login'), response['Location'])

    def test_10_staff_roles_may_open_the_assistant_and_others_may_not(self):
        for user, expected in ((self.admin, 200), (self.lead, 200), (self.teacher, 200), (self.counselor, 200),
                               (self.parent, 403), (self.student_user, 403)):
            with self.subTest(role=user.groups.first().name):
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse('docqa:home')).status_code, expected)

    def test_11_only_the_school_admin_manages_documents(self):
        for user, expected in ((self.admin, 200), (self.teacher, 403), (self.lead, 403), (self.counselor, 403)):
            with self.subTest(role=user.groups.first().name):
                self.client.force_login(user)
                self.assertEqual(self.client.get(reverse('docqa:documents')).status_code, expected)

    def test_12_F11_staff_who_may_use_the_assistant_have_a_link_to_it(self):
        """F11: /assistant/ is open to GradeLead/Teacher/Counselor (test_10) and each of them now has a menu entry on
        their own home. The entry is gated on the same two switches as the view (the advisor_ai module and
        ENABLE_AI_FEATURES), so when the view would answer 403 the link is absent instead of dead."""
        homes = {self.lead: reverse('dashboard:grade_dashboard'),
                 self.teacher: reverse('dashboard:teacher_home'),
                 self.counselor: reverse('dashboard:counselor_home')}
        linked = {}
        for user, home in homes.items():
            role = user.groups.first().name
            self.client.force_login(user)
            page = self.client.get(home)
            self.assertEqual(page.status_code, 200, role)
            linked[role] = reverse('docqa:home') in page.content.decode()
        print(f'[E2E] F11: a nav link to /assistant/ on each role home: {linked}')
        self.assertEqual(linked, {role: True for role in linked})
        with override_settings(ENABLE_AI_FEATURES=False):      # the view 403s, so no link: not a dead end
            for user, home in homes.items():
                self.client.force_login(user)
                self.assertNotIn(reverse('docqa:home'), self.client.get(home).content.decode(), user.username)
        # Companion evidence: the page itself is reachable for these same users (test_10), so the gap was navigation only.


class UploadJourneyTests(E2EUserJourney):
    def test_13_the_txt_upload_through_the_form_creates_searchable_chunks_and_an_audit_row(self):
        self.client.force_login(self.admin)
        response = self.upload(title='Handbook', text=HANDBOOK)
        self.assertEqual(response.status_code, 200)
        doc = SchoolDocument.objects.get(school=self.a, title='Handbook')
        self.assertEqual(doc.chunks.count(), 1)
        self.assertEqual((doc.uploaded_by_id, doc.is_active), (self.admin.pk, True))
        self.assertEqual(doc.char_count, len(HANDBOOK))
        event = AuditEvent.objects.get(action=audit.DOC_UPLOAD, school=self.a)
        self.assertEqual(event.detail, 'c1')
        self.assertNotIn('ساعت', event.detail)

    def test_14_a_docx_upload_is_extracted_by_paragraph(self):
        self.client.force_login(self.admin)
        self.upload(title='Guide', text=docx(['بند اول', 'بند دوم']), filename='guide.docx')
        doc = SchoolDocument.objects.get(school=self.a, title='Guide')
        self.assertEqual(doc.chunks.get().text, 'بند اول\n\nبند دوم')
        self.assertEqual(doc.source_name, 'guide.docx')

    def test_15_upload_rejections_are_specific_messages_and_write_nothing(self):
        self.client.force_login(self.admin)
        self.upload(title='Handbook')                                     # the duplicate-title case below needs it
        before = SchoolDocument.objects.count()
        cases = [
            (dict(title='NoAttest', attest=None), 'باید تأیید کنید که سند دادهٔ شخصی دانش‌آموزان ندارد.'),
            (dict(title='Empty', text='', filename='empty.txt'), 'فایل متنی ندارد.'),
            (dict(title='Pdf', text='x', filename='notes.pdf'), 'فقط txt، md و docx پذیرفته می‌شود.'),
            (dict(title='Broken', text=b'PK\x03\x04broken', filename='broken.docx'), 'فایل docx معتبر نیست.'),
            (dict(title='Utf16', text='سلام'.encode('utf-16'), filename='utf16.txt'), 'فایل متنی باید UTF-8 باشد.'),
            (dict(title='Big', text=b'x' * (MAX_BYTES + 1), filename='big.txt'), 'فایل بزرگ‌تر از حد مجاز است.'),
            (dict(title='Long', text='ا' * 200_001, filename='long.txt'), 'متن بیش از حد طولانی است.'),
            (dict(title='Handbook'), 'سندی با این عنوان وجود دارد.'),
            (dict(title='Notes', text=f'دربارهٔ {self.s7.first_name} {self.s7.last_name} صحبت شد.'),
             'سند دادهٔ شخصی (شناسه، تلفن، ایمیل یا نام دانش‌آموز) دارد و پذیرفته نشد.'),
        ]
        expected_count = before
        for kwargs, message in cases:
            with self.subTest(case=kwargs.get('filename') or kwargs.get('title')):
                response = self.upload(**kwargs)
                self.assertIn(message, self.messages_of(response))
                self.assertEqual(SchoolDocument.objects.count(), expected_count)
        self.assertEqual(expected_count, 1)

    def test_16_a_case_variant_title_creates_a_second_document(self):
        """CHARACTERISATION (F18): the per-school unique constraint is exact, so 'Handbook' and 'handbook' both exist;
        the school pays for the same content twice and the assistant shows it twice."""
        self.client.force_login(self.admin)
        self.upload(title='Handbook')
        self.upload(title='handbook')
        self.assertEqual(SchoolDocument.objects.filter(school=self.a).count(), 2)

class AskJourneyTests(E2EUserJourney):
    def setUp(self):
        super().setUp()
        self.doc = self.add_document(self.a, 'Handbook', HANDBOOK)
        self.add_document(self.b, 'BHandbook', HANDBOOK_B)
        self.client.force_login(self.admin)

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_17_the_full_ask_flow_returns_a_cited_answer_and_audits_codes_only(self):
        self.assertEqual(self.enable_ai().status_code, 200)
        self.assertTrue(AssistantSettings.objects.get(school=self.a).ai_enabled)
        self.assertEqual(AuditEvent.objects.get(action=audit.DOC_AI_SETTING, school=self.a).detail, 'on')
        get, post = self.provider()
        response = self.ask()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ساعت شروع هشت صبح است [1].')
        self.assertContains(response, 'در پاسخ ارجاع شده')                     # the citation is highlighted
        self.assertContains(response, 'LABEL')                                 # the "AI, may be wrong" label
        self.assertEqual((get.call_count, post.call_count), (1, 1))
        self.assertEqual(self.usage(), 1)
        self.assertEqual(AuditEvent.objects.filter(action=audit.DOC_ASK).latest('pk').detail, 'ai:k1c1')
        body = post.call_args.kwargs['json']
        sent = ' '.join(m['content'] for m in body['messages'])
        self.assertEqual(body['purpose'], 'document_qa')
        self.assertIn('Handbook', sent)
        self.assertNotIn('BHandbook', sent)                                    # school A only
        self.assertNotIn(HANDBOOK_B[:20], sent)
        self.assertNotIn(self.s7.national_id, sent)
        self.assertNotIn(f'{self.s7.first_name} {self.s7.last_name}', sent)

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_18_with_the_school_switch_off_the_page_is_a_search_and_makes_no_network_call(self):
        get, post = self.provider()
        response = self.ask()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'بخش‌های مرتبط')
        self.assertContains(response, 'پاسخ هوشمند برای این مدرسه خاموش است')
        self.assertEqual((get.call_count, post.call_count), (0, 0))
        self.assertEqual(self.usage(), 0)
        self.assertEqual(AuditEvent.objects.filter(action=audit.DOC_ASK).latest('pk').detail, 'search:k1')

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_19_without_a_local_provider_the_user_gets_the_excerpts_and_a_notice(self):
        self.enable_ai()
        get, post = self.provider(enabled=False)
        response = self.ask()
        self.assertContains(response, 'مدل زبانی محلی برای این مدرسه فعال نیست')
        self.assertEqual((get.call_count, post.call_count), (1, 0))
        self.assertEqual(self.usage(), 0)                                      # nothing was billed
        self.assertEqual(AuditEvent.objects.filter(action=audit.DOC_ASK).latest('pk').detail, 'search:k1:nolocal')

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_20_a_provider_error_falls_back_to_the_excerpts(self):
        self.enable_ai()
        get, post = self.provider(status=500)
        response = self.ask()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'پاسخ هوشمند در دسترس نبود')
        self.assertEqual(post.call_count, 1)
        print(f'[E2E] provider 500 -> quota_used={self.usage()} (F05: refunded — the cap counts delivered answers)')
        self.assertEqual(AuditEvent.objects.filter(action=audit.DOC_ASK).latest('pk').detail, 'search:k1:error')

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_21_F05_a_failed_llm_call_does_not_burn_the_daily_quota(self):
        """F05 (fixed in change 0044): services.ask() used to call ai_guard.consume() BEFORE _complete(), so a provider
        5xx, a timeout or a 502 still counted against School.ai_daily_cap. It now refunds the slot when the call
        delivered no answer; companion test_20 proves the request reaches the provider and falls back."""
        self.enable_ai()
        self.provider(status=500)
        self.ask()
        print(f'[E2E] F05: quota consumed by a failed provider call = {self.usage()}')
        self.assertEqual(self.usage(), 0)

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_22_the_31st_question_in_the_window_is_refused_before_any_llm_call(self):
        from docqa.views import QUESTIONS_PER_WINDOW, WINDOW
        self.enable_ai()
        get, post = self.provider()
        cache.set(f'docqa-ask:{self.admin.pk}', QUESTIONS_PER_WINDOW, WINDOW)
        response = self.ask()
        self.assertIn('تعداد پرسش‌ها بیش از حد مجاز است؛ چند دقیقه بعد دوباره تلاش کنید.',
                      self.messages_of(response))
        self.assertEqual((get.call_count, post.call_count), (0, 0))
        self.assertEqual(self.usage(), 0)

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_23_question_rules_are_enforced_before_retrieval(self):
        self.enable_ai()
        get, post = self.provider()
        cases = [('', 'سؤال خالی یا بیش از ۵۰۰ نویسه است.'),
                 ('ا' * 501, 'سؤال خالی یا بیش از ۵۰۰ نویسه است.'),
                 ('کد ملی 0012345678 چیست؟',
                  'سؤال نباید نام یا شناسهٔ دانش‌آموز، شمارهٔ تلفن یا نشانی ایمیل داشته باشد.')]
        for question, message in cases:
            with self.subTest(length=len(question)):
                self.assertIn(message, self.messages_of(self.ask(question=question)))
        self.assertEqual((get.call_count, post.call_count), (0, 0))
        self.assertTrue(AuditEvent.objects.filter(action=audit.DOC_ASK, detail='refused:screen').exists())

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_24_a_question_with_no_match_says_so_and_costs_nothing(self):
        self.enable_ai()
        get, post = self.provider()
        response = self.ask(question='کوانتوم هیچ')
        self.assertContains(response, 'در اسناد مدرسه بخش مرتبطی پیدا نشد.')
        self.assertEqual((get.call_count, post.call_count), (0, 0))
        self.assertEqual(self.usage(), 0)
        self.assertEqual(AuditEvent.objects.filter(action=audit.DOC_ASK).latest('pk').detail, 'none')

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_25_a_deactivated_document_is_not_retrieved(self):
        self.enable_ai()
        get, post = self.provider()
        SchoolDocument.objects.filter(school=self.a).update(is_active=False)
        response = self.ask()
        self.assertContains(response, 'در اسناد مدرسه بخش مرتبطی پیدا نشد.')
        self.assertEqual(post.call_count, 0)

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_26_asking_the_same_question_twice_is_two_billed_calls(self):
        """CHARACTERISATION (F14): there is no answer cache, so a double submit or an impatient second click is billed
        twice and the answer is generated again. Measured and printed, not asserted as desirable."""
        self.enable_ai()
        get, post = self.provider()
        self.ask()
        self.ask()
        print(f'[E2E] identical question twice -> complete_calls={post.call_count} quota={self.usage()}')
        self.assertEqual((post.call_count, self.usage()), (2, 2))

@override_settings(SERVICE_JWT_SECRET=SECRET)
class PredictionJourneyTests(E2EUserJourney):
    """The 'predict with AI' button on the student page. FastAPI's /predict/ is mocked at the Django boundary; the
    service side of the same contract is exercised over real HTTP in the FastAPI leg."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.admin)

    def predict(self, status=200, body=None):
        from dashboard import views as dashboard_views
        body = {'risk_probability': 0.7, 'is_high_risk': True,
                'message': 'دانش‌آموز در معرض ریسک افت تحصیلی است.'} if body is None else body
        post = mock.Mock(return_value=_Response(status, body))
        patcher = mock.patch.object(dashboard_views.requests, 'post', post)
        patcher.start()
        self.addCleanup(patcher.stop)
        return post

    def detail_url(self):
        return reverse('dashboard:student_detail', args=[self.s7.pk])

    def run_prediction(self):
        """F04 (change 0044): the page triggers the model with an explicit POST — it used to be `GET ?predict=true`, so
        a refresh, a prefetch, a bookmark or the back button each spent another inference."""
        return self.client.post(self.detail_url(), {'action': 'predict'})

    def test_27_the_admin_gets_the_demo_block_and_the_models_own_message(self):
        """F02 (change 0044): the prediction block is still shown to the admin and still carries the model's message,
        but it is labelled a demo and the internal feature dict is no longer printed."""
        post = self.predict()
        response = self.run_prediction()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'نتیجه‌ی نمایشی')
        self.assertContains(response, 'در معرض ریسک افت تحصیلی')
        self.assertContains(response, 'نمایشی / داده‌های تکمیلی موجود نیست')
        self.assertNotContains(response, 'داده‌های ارسال‌شده به هوش مصنوعی')
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs['timeout'], 5)

    def test_28_F01_the_risk_probability_is_shown_as_a_percentage(self):
        """F01 (fixed in change 0044): the model returns a probability in 0..1 (FastAPI /predict/ rounds to 4
        decimals) and the page used to render ``{{ prediction.risk_probability|floatformat:2 }}%``, so a 70% risk read
        as '0.70%' -- a 100x understatement of the number the admin acts on.
        TARGET: multiply by 100, whole number, Persian digits."""
        self.predict(body={'risk_probability': 0.7, 'is_high_risk': True, 'message': 'm'})
        html = self.run_prediction().content.decode()
        percent = self.rendered_risk_percent(html)
        print(f'[E2E] F01: model probability 0.70 is rendered as {percent}%')
        self.assertAlmostEqual(percent, 70.0)
        self.assertIn('۷۰%', html)                     # Persian digits, no decimals
        self.assertNotIn('0.70%', html)                # the 100x-understated rendering is gone

    def test_29_F02_a_fabricated_prediction_is_labelled_as_a_demo(self):
        """F02 (change 0044, D1): the vector is still built from three placeholder constants because nothing writes the
        homework / communication tables yet, so the block must say so, must not call itself a prediction and must not
        print the internal dict to the principal. The real-data TARGET stays pinned by test_29b."""
        post = self.predict()
        response = self.run_prediction()
        self.assertContains(response, 'نمایشی / داده‌های تکمیلی موجود نیست')
        self.assertContains(response, 'احتمال ریسک (نمایشی)')
        self.assertContains(response, 'این خروجی مبنای تصمیم نیست')
        self.assertNotContains(response, 'نتیجه‌ی پیش‌بینی')
        self.assertNotContains(response, 'داده‌های ارسال‌شده به هوش مصنوعی')
        self.assertNotContains(response, 'avg_completion_rate')
        self.assertEqual(post.call_count, 1, 'the hard-coded logic was kept (D1), so the call must still happen')
        print(f'[E2E] F02: labelled as a demo; features still sent: {post.call_args.kwargs["json"]}')

    @unittest.expectedFailure
    def test_29b_F02_the_prediction_must_eventually_use_the_students_real_numbers(self):
        """F02 TARGET (DEFERRED as F02b in change 0044): dashboard/views.py hard-codes avg_completion_rate=0.8,
        total_communications=3 and completed_homework=12, so two students with different histories get the same vector.
        Until real homework/communication rows exist and are read, this stays expected to fail; the demo label
        (test_29) is what the owner chose in the meantime."""
        post = self.predict()
        self.run_prediction()
        sent = post.call_args.kwargs['json']
        print(f'[E2E] F02b: features sent for a student with no homework records: {sent}')
        self.assertNotEqual(sent['total_communications'], 3, 'F02b: total_communications is a constant in views.py')
        self.assertNotEqual(sent['completed_homework'], 12, 'F02b: completed_homework is a constant in views.py')
        self.assertNotEqual(sent['avg_completion_rate'], 0.8, 'F02b: avg_completion_rate is a constant in views.py')

    def test_30_F04_a_refresh_does_not_repeat_the_prediction_call(self):
        """F04 (fixed in change 0044): the prediction used to be a GET side effect (``<a href="?predict=true">``), so F5,
        a browser prefetch, a shared link or the back button each caused another FastAPI inference. The page now posts
        an explicit form with CSRF (`action=predict`); a plain GET never calls the model."""
        post = self.predict()
        self.run_prediction()
        self.assertEqual(self.client.get(self.detail_url()).status_code, 200)
        self.assertEqual(self.client.get(self.detail_url()).status_code, 200)
        print(f'[E2E] F04: two page views made predict_calls={post.call_count}')
        self.assertEqual(post.call_count, 1)

    def test_31_opening_the_page_without_submitting_the_form_makes_no_call(self):
        post = self.predict()
        self.assertEqual(self.client.get(self.detail_url()).status_code, 200)
        self.assertEqual(post.call_count, 0)

    def test_32_only_the_school_admin_can_spend_a_prediction(self):
        post = self.predict()
        for user in (self.teacher, self.lead, self.parent):
            with self.subTest(role=user.groups.first().name):
                self.client.force_login(user)
                response = self.client.get(self.detail_url())
                self.assertEqual(post.call_count, 0)
                self.assertNotContains(response, 'نمایش آزمایشی وضعیت')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(self.detail_url()), 'نمایش آزمایشی وضعیت')

    def test_33_a_provider_error_is_shown_in_the_page_with_its_http_code(self):
        """CHARACTERISATION (F19): the failure message carries the upstream HTTP status into the school admin's page
        ('کد 500') -- an internal detail the admin cannot act on -- and the same box is used for every failure."""
        self.predict(status=500)
        response = self.run_prediction()
        self.assertEqual(response.status_code, 200)                           # the page still renders
        self.assertContains(response, 'خطا در سرویس هوش مصنوعی (کد 500).')


class AuditAndCostTests(E2EUserJourney):
    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_34_the_audit_page_shows_codes_never_the_question_or_the_answer(self):
        self.add_document(self.a, 'Handbook', HANDBOOK)
        self.client.force_login(self.admin)
        self.enable_ai()
        self.provider(answer='پاسخ محرمانه [1].')
        self.ask()
        page = self.client.get(reverse('dashboard:school_audit'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'doc_ask')
        self.assertNotContains(page, GOOD_QUESTION)
        self.assertNotContains(page, 'پاسخ محرمانه')
        self.assertNotContains(page, HANDBOOK[:15])
        self.client.force_login(self.counselor)
        self.assertEqual(self.client.get(reverse('dashboard:school_audit')).status_code, 403)

    def test_35_retrieval_cost_is_proportional_to_the_whole_school_corpus(self):
        """F07: retrieve() loads every active chunk of the school and re-tokenises each one on every ask (no token or
        chunk cache), then ranks in Python. Measured here so the report can quote real numbers."""
        from docqa.models import DocumentChunk

        def bulk(school, title, count):
            doc = SchoolDocument.objects.create(school=school, title=title)
            DocumentChunk.objects.bulk_create([
                DocumentChunk(document=doc, school=school, ordinal=i,
                              text=f'بند {i} ' + 'مدرسه ساعت شروع کلاس‌ها هشت صبح است ' * 14) for i in range(count)])

        bulk(self.a, 'Fifty', 50)
        bulk(self.b, 'FiveHundred', 500)
        timings = {}
        for label, school, chunks in (('50_chunks', self.a, 50), ('500_chunks', self.b, 500)):
            started = time.perf_counter()
            found = services.retrieve(school.pk, GOOD_QUESTION)
            timings[label] = (time.perf_counter() - started) * 1000
            print(f'[E2E] retrieve corpus={label} chunks={chunks} ms={timings[label]:.1f} results={len(found)}')
            self.assertLessEqual(len(found), services.TOP_K)
        self.assertLess(timings['500_chunks'], 3_000, 'a 500-chunk corpus must not block a page for seconds')

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_36_the_ask_flow_is_two_sequential_calls_with_3s_and_65s_timeouts(self):
        """F06: the page blocks on the status check (3 s) and then on the completion (65 s); no streaming and no
        loading state, so the worst case is 68 s of a held request. The timeouts come from the real call kwargs."""
        self.add_document(self.a, 'Handbook', HANDBOOK)
        self.client.force_login(self.admin)
        self.enable_ai()
        get, post = self.provider()
        started = time.perf_counter()
        self.ask()
        elapsed = (time.perf_counter() - started) * 1000
        print(f'[E2E] ask with a mocked provider: wall_ms={elapsed:.0f} '
              f'status_timeout={get.call_args.kwargs["timeout"]} complete_timeout={post.call_args.kwargs["timeout"]}')
        self.assertEqual((get.call_args.kwargs['timeout'], post.call_args.kwargs['timeout']), (3, 65))
        self.assertIn('/llm/status/', get.call_args.args[0])
        self.assertIn('/llm/complete/', post.call_args.args[0])


class LegacyPagesAndApiTests(E2EUserJourney):
    """The DRF predict action still exists next to the page, and this class pins what it does today. The legacy
    /library/, /upload-document/, /delete-document/ and /chat/ pages are gone (F12, change 0044 tranche 2)."""

    def test_37_F12_the_legacy_library_and_chat_pages_are_gone(self):
        """F12: the pre-P7 pages were removed with their views and templates (dashboard/urls.py, dashboard/views.py).
        Their job is /assistant/ and /assistant/documents/. The old admin page forwarded PDFs to a FastAPI route that is
        disabled_in_phase1 for EVERY role (auth.py), so it always ended in an English error message after a full upload;
        the live assistant accepts txt/md/docx only, so the two pages contradicted each other."""
        self.client.force_login(self.admin)
        for path in ('/library/', '/upload-document/', '/delete-document/', '/chat/'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)
                self.assertEqual(self.client.post(path).status_code, 404)
        self.assertEqual(self.client.get(reverse('docqa:documents')).status_code, 200)     # the one document library
        page = self.client.get(reverse('dashboard:school_home')).content.decode()
        advertised = [path for path in ('/library/', '/chat/') if path in page]
        print(f'[E2E] F12: removed pages still advertised in the admin menu? {advertised}')
        self.assertEqual(advertised, [])
        self.assertNotIn('به‌زودی', page)          # the «coming soon» stubs went with the pages
        self.assertEqual(SchoolDocument.objects.count(), 0)

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_38_F21_the_api_predict_action_is_a_second_unmetered_copy(self):
        """F21 (characterisation): GET /api/students/<pk>/predict/ and .../features/ apply the same Admin role rule as
        the page (students/permissions.py IsAdminUser -> has_any_role(ADMIN), not is_staff), but they are a SECOND copy
        of the placeholder feature dict (students/views.py:461-480 vs dashboard/views.py:142-155), and neither path --
        page or API -- calls ai_guard.consume(), so every prediction is an unmetered inference while the assistant is
        capped. TARGET: one feature builder, one call path, metered like the assistant."""
        from students import views as student_views
        post = mock.Mock(return_value=_Response(200, {'risk_probability': 0.7, 'is_high_risk': True, 'message': 'm'}))
        patcher = mock.patch.object(student_views.requests, 'post', post)
        patcher.start()
        self.addCleanup(patcher.stop)
        codes = {}
        for user in (self.parent, self.lead, self.teacher):
            self.client.force_login(user)
            for action in ('predict', 'features'):
                codes[(user.get_username(), action)] = self.client.get(
                    f'/api/students/{self.s7.pk}/{action}/').status_code
        print(f'[E2E] F21: non-admin API predict/features status codes: {codes}')
        self.assertEqual(set(codes.values()), {403})
        self.client.force_login(self.admin)
        response = self.client.get(f'/api/students/{self.s7.pk}/predict/')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        print(f'[E2E] F21: the API returns the same placeholder vector: {body["input_data"]}')
        self.assertEqual(body['input_data']['completed_homework'], 12)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(AICallUsage.objects.count(), 0)            # nothing metered on this path

    @override_settings(SERVICE_JWT_SECRET='')
    def test_39_F17_a_missing_service_secret_falls_back_to_the_excerpts(self):
        """F17 (fixed in change 0044): SERVICE_JWT_SECRET defaults to '' (base.py) and services.ask() called
        service_headers() outside every try, so with the switch on and a matching document the admin got Django's 500
        page. It now catches ImproperlyConfigured, shows the excerpts with the usual offline notice, records the refusal
        in the audit row and logs the deploy problem -- the same degradation every other AI failure produces."""
        self.add_document(self.a, 'Handbook', HANDBOOK)
        self.client.force_login(self.admin)
        AssistantSettings.objects.update_or_create(school=self.a, defaults={'ai_enabled': True})
        with self.assertLogs('docqa.services', level='WARNING') as logs:
            response = self.ask()
        print(f'[E2E] F17: ask without SERVICE_JWT_SECRET -> status={response.status_code}')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'پاسخ هوشمند در دسترس نبود')
        self.assertIn('SERVICE_JWT_SECRET', logs.output[0])
        self.assertEqual(AuditEvent.objects.filter(action=audit.DOC_ASK).latest('pk').detail, 'search:k1:unconfigured')








