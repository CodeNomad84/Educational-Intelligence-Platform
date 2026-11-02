"""P7-5 document assistant. Mutation checks (by hand, see the commit): removing the school filter in retrieval, the screening of
questions or uploads, the attestation, the local-class check, the cap, or putting the question into the audit row each fails a test."""
import io
import zipfile
from datetime import date, timedelta
from unittest import mock

import jwt
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from docqa import demo_docs, services
from docqa.extract import ExtractError, extract_text
from docqa.models import AssistantSettings, DocumentChunk, SchoolDocument
from docqa.screen import screen_text
from risk.loop_testing import LoopBase
from schools import entitlements
from schools.models import AuditEvent

SECRET = 'x' * 8 + 'abcdefghijklmnopqrstuvwxyz0123456789'


def docx(paragraphs, extra=b''):
    body = ''.join(f'<w:p><w:r><w:t>{p}</w:t></w:r></w:p>' for p in paragraphs)
    xml = ('<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           f'{body}</w:body></w:document>').encode() + extra
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr('word/document.xml', xml)
    return out.getvalue()


class Base(LoopBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        today = date.today()
        for school in (self.a, self.b):
            entitlements.set_module(school, 'advisor_ai', today, today + timedelta(days=30), kind=entitlements.TRIAL)
        self.doc = self.add(self.a, 'Handbook', 'ساعت شروع کلاس‌ها هشت صبح است.\n\nغیبت موجه نیازمند گواهی پزشک است.')
        self.doc_b = self.add(self.b, 'BHandbook', 'ساعت شروع کلاس‌ها در مدرسهٔ دیگر نه صبح است. رمزعبور بیرونی.')

    def add(self, school, title, text):
        doc = SchoolDocument.objects.create(school=school, title=title, char_count=len(text))
        DocumentChunk.objects.bulk_create([DocumentChunk(document=doc, school=school, ordinal=i, text=c)
                                           for i, c in enumerate(services.chunk_text(text))])
        return doc

    def enable_ai(self):
        AssistantSettings.objects.update_or_create(school=self.a, defaults={'ai_enabled': True})


class ExtractAndScreenTests(Base):
    def test_extraction_types_and_limits(self):
        self.assertIn('سلام', extract_text('a.txt', 'سلام دنیا'.encode()))
        self.assertIn('سلام', extract_text('a.md', 'سلام'.encode()))
        self.assertIn('بند اول', extract_text('a.docx', docx(['بند اول', 'بند دوم'])))
        for name, data, code in (('a.pdf', b'x', 'unsupported_type'), ('a.txt', b'\xff\xfe\x00', 'not_utf8'), ('a.txt', b'  ', 'empty'),
                                 ('a.txt', b'x' * 1_000_001, 'file_too_large'), ('a.docx', b'not a zip', 'not_docx'),
                                 ('a.docx', docx(['x'], b'<!DOCTYPE a [<!ENTITY e "boom">]>'), 'not_docx')):
            with self.assertRaises(ExtractError, msg=name) as ctx:
                extract_text(name, data)
            self.assertEqual(ctx.exception.code, code)
        bomb = io.BytesIO()
        with zipfile.ZipFile(bomb, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('word/document.xml', b'<w:document/>')
            z.writestr('pad.bin', b'\0' * 10_000_001)
        with self.assertRaises(ExtractError):
            extract_text('a.docx', bomb.getvalue())

    def test_screening_refuses_ids_phones_emails_and_this_schools_student_names(self):
        first, last = self.s7.first_name, self.s7.last_name
        for text in ('کد ملی ۰۰۱۲۳۴۵۶۷۸', '0‌0‌1234 5678', 'تماس 09123456789', 'a.b@example.org', f'{first} {last} غایب بود',
                     f'خانم {last} را ببینید' if len(last) >= 3 else f'{first} {last}'):
            self.assertTrue(screen_text(text, self.a.pk), text)
        self.assertEqual(screen_text('ساعت شروع کلاس هشت صبح، صفحهٔ ۱۲ از ۲۰۲۶ و ۲۴ نفر', self.a.pk), [])


class UploadViewTests(Base):
    def post(self, user, title='Doc1', data=b'hello world policy text', name='d.txt', attest=True, **extra):
        self.client.force_login(user)
        body = {'title': title, 'file': SimpleUploadedFile(name, data), **extra}
        if attest:
            body['attest'] = 'on'
        return self.client.post(reverse('docqa:documents'), body)

    def test_only_the_school_admin_manages_documents(self):
        for user in (self.lead, self.teacher, self.counselor, self.parent, self.student_user):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('docqa:documents')).status_code, 403, user.username)
            self.assertEqual(self.client.post(reverse('docqa:ai_setting'), {'ai_enabled': 'on'}).status_code, 403)
        self.assertEqual(self.post(self.teacher).status_code, 403)
        self.assertFalse(SchoolDocument.objects.filter(title='Doc1').exists())

    def test_upload_needs_the_attestation_and_refuses_personal_data(self):
        self.post(self.admin, attest=False)
        self.assertFalse(SchoolDocument.objects.filter(title='Doc1').exists())
        self.post(self.admin, data=f'{self.s7.first_name} {self.s7.last_name} was absent'.encode())
        self.post(self.admin, title='Doc2', data='national id 0012345678'.encode())
        self.assertFalse(SchoolDocument.objects.filter(title__in=['Doc1', 'Doc2']).exists())
        self.post(self.admin, title='Doc3', data='ساعت شروع کلاس هشت است'.encode())
        doc = SchoolDocument.objects.get(title='Doc3')
        self.assertEqual((doc.school_id, doc.chunks.count() > 0), (self.a.pk, True))
        event = AuditEvent.objects.get(action='doc_upload')
        self.assertNotIn('ساعت', event.detail)                                       # counts only, never text

    def test_actions_are_scoped_to_the_admins_school_and_audited(self):
        url_b = reverse('docqa:document_action', args=[self.doc_b.pk])
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(url_b, {'action': 'delete'}).status_code, 404)          # another school's document
        self.assertTrue(SchoolDocument.objects.filter(pk=self.doc_b.pk).exists())
        url = reverse('docqa:document_action', args=[self.doc.pk])
        self.client.post(url, {'action': 'toggle'})
        self.doc.refresh_from_db()
        self.assertFalse(self.doc.is_active)
        self.client.post(url, {'action': 'delete'})
        self.assertFalse(SchoolDocument.objects.filter(pk=self.doc.pk).exists())
        self.assertEqual(set(AuditEvent.objects.filter(action__in=['doc_toggle', 'doc_delete']).values_list('action', flat=True)),
                         {'doc_toggle', 'doc_delete'})

    def test_the_ai_setting_is_off_by_default_and_audited(self):
        self.assertFalse(AssistantSettings.objects.filter(school=self.a, ai_enabled=True).exists())
        self.client.force_login(self.admin)
        self.client.post(reverse('docqa:ai_setting'), {'ai_enabled': 'on'})
        self.assertTrue(AssistantSettings.objects.get(school=self.a).ai_enabled)
        self.assertTrue(AuditEvent.objects.filter(action='doc_ai_setting', detail='on').exists())

    def test_uploads_are_throttled(self):
        for i in range(10):
            self.post(self.admin, title=f'T{i}', data=b'policy text number %d here' % i)
        self.post(self.admin, title='T-extra', data=b'one more policy')
        self.assertFalse(SchoolDocument.objects.filter(title='T-extra').exists())


class RetrievalTests(Base):
    def test_retrieval_reads_only_the_callers_school_and_active_documents(self):
        rows = services.retrieve(self.a.pk, 'ساعت شروع کلاس‌ها')
        self.assertTrue(rows)
        self.assertTrue(all(r.school_id == self.a.pk for r in rows))
        self.assertNotIn('رمزعبور', ' '.join(r.text for r in rows))
        self.assertTrue(all(r.school_id == self.b.pk for r in services.retrieve(self.b.pk, 'ساعت شروع')))
        SchoolDocument.objects.filter(pk=self.doc.pk).update(is_active=False)
        self.assertEqual(services.retrieve(self.a.pk, 'ساعت شروع کلاس‌ها'), [])

    def test_relevant_chunk_ranks_first(self):
        self.add(self.a, 'Exams', 'آزمون میان‌ترم در هفتهٔ هشتم برگزار می‌شود.\n\nاعتراض به نمره کتبی است.')
        top = services.retrieve(self.a.pk, 'اعتراض به نمره')[0]
        self.assertIn('اعتراض', top.text)
        self.assertEqual(services.retrieve(self.a.pk, 'کوانتوم هیچ'), [])


class AskTests(Base):
    def answer(self, text='ساعت شروع هشت است [1].', status=200):
        class R:
            def __init__(self, code, body): self.status_code, self._b = code, body
            def json(self): return self._b
        def fake_get(url, **kw):
            return R(200, {'enabled': True, 'class': 'local'})
        def fake_post(url, json=None, **kw):
            self.posted = json
            return R(status, {'text': text, 'label': 'LABEL'})
        return mock.patch('docqa.services.requests.get', fake_get), mock.patch('docqa.services.requests.post', fake_post)

    def ask(self, user=None, q='ساعت شروع کلاس‌ها چه زمانی است؟'):
        return services.ask(user or self.teacher, self.a, q)

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_off_by_default_means_search_only_and_no_network_call(self):
        with mock.patch('docqa.services.requests') as req:
            result = self.ask()
        self.assertEqual(result['mode'], 'search')
        self.assertTrue(result['excerpts'])
        req.get.assert_not_called()
        req.post.assert_not_called()

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_the_question_is_screened_before_anything_else(self):
        for q in (f'{self.s7.first_name} {self.s7.last_name} چرا غایب است؟', 'کد ملی 0012345678 چیست', ''):
            with mock.patch('docqa.services.retrieve') as retrieve, self.assertRaises(services.AskRefused):
                self.ask(q=q)
            retrieve.assert_not_called()
        self.assertTrue(AuditEvent.objects.filter(action='doc_ask', detail='refused:screen').exists())

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_no_match_makes_no_call_and_uses_no_cap(self):
        self.enable_ai()
        with mock.patch('docqa.services.requests') as req:
            self.assertEqual(self.ask(q='کوانتوم هیچ')['mode'], 'none')
        req.post.assert_not_called()

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_ai_answer_cites_the_documents_and_the_prompt_holds_only_documents_and_question(self):
        self.enable_ai()
        g, p = self.answer()
        with g, p:
            result = self.ask()
        self.assertEqual((result['mode'], result['cited'], result['label']), ('ai', [1], 'LABEL'))
        self.assertEqual(self.posted['purpose'], 'document_qa')
        sent = ' '.join(m['content'] for m in self.posted['messages'])
        for private in (self.s7.first_name + ' ' + self.s7.last_name, self.s7.national_id, 'رمزعبور'):
            self.assertNotIn(private, sent)                                                        # no student data, nothing of school B
        self.assertIn('Handbook', sent)
        event = AuditEvent.objects.filter(action='doc_ask').latest('pk')
        self.assertEqual(event.detail, 'ai:k1c1')
        self.assertNotIn('ساعت', event.detail)

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_an_answer_without_citations_is_flagged_and_failures_fall_back_to_search(self):
        self.enable_ai()
        g, p = self.answer(text='جواب بدون ارجاع')
        with g, p:
            result = self.ask()
        self.assertEqual((result['mode'], result['cited']), ('ai', []))
        self.assertIn('قابل اعتماد نیست', result['notice'])
        g, p = self.answer(status=502)
        with g, p:
            fallback = self.ask()
        self.assertEqual(fallback['mode'], 'search')
        self.assertTrue(fallback['excerpts'])

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_only_a_local_provider_is_used_and_the_cap_is_enforced(self):
        self.enable_ai()
        class R:
            status_code = 200
            def __init__(self, body): self._b = body
            def json(self): return self._b
        with mock.patch('docqa.services.requests.get', lambda *a, **k: R({'enabled': True, 'class': 'external'})), \
                mock.patch('docqa.services.requests.post') as post:
            self.assertEqual(self.ask()['mode'], 'search')                                          # external class: never used here
            post.assert_not_called()
        with mock.patch('docqa.services.requests.get', lambda *a, **k: R({'enabled': False, 'class': None})), \
                mock.patch('docqa.services.requests.post') as post:
            self.assertEqual(self.ask()['mode'], 'search')
            post.assert_not_called()
        self.a.ai_daily_cap = 0
        self.a.save(update_fields=['ai_daily_cap'])
        g, p = self.answer()
        with g, mock.patch('docqa.services.requests.post') as post:
            result = self.ask()
        self.assertEqual(result['mode'], 'search')
        self.assertIn('سقف', result['notice'])
        post.assert_not_called()

    @override_settings(SERVICE_JWT_SECRET=SECRET)
    def test_the_token_carries_exactly_one_school_and_never_one_the_user_is_not_in(self):
        from config.service_auth import service_headers
        token = service_headers(self.teacher, with_school=self.a.pk)['Authorization'].split()[1]
        claims = jwt.decode(token, SECRET, algorithms=['HS256'], audience='school-fastapi')
        self.assertEqual((claims['roles'], claims['schools']), (['Teacher'], [self.a.pk]))
        with self.assertRaises(Exception):
            service_headers(self.teacher, with_school=self.b.pk)
        plain = jwt.decode(service_headers(self.teacher)['Authorization'].split()[1], SECRET, algorithms=['HS256'], audience='school-fastapi')
        self.assertEqual(plain['schools'], [])


class PageAccessTests(Base):
    def test_staff_can_ask_parents_and_students_cannot_and_the_module_must_be_on(self):
        url = reverse('docqa:home')
        for user in (self.admin, self.lead, self.teacher, self.counselor):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 200, user.username)
        for user in (self.parent, self.student_user):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 403, user.username)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        from schools.models import SchoolModule
        SchoolModule.objects.filter(school=self.a, module_key='advisor_ai').delete()
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_a_question_is_answered_from_the_page_and_the_text_is_never_audited(self):
        self.client.force_login(self.teacher)
        page = self.client.post(reverse('docqa:home'), {'question': 'ساعت شروع کلاس‌ها'})
        self.assertContains(page, 'Handbook')
        self.assertNotContains(page, 'رمزعبور')
        for event in AuditEvent.objects.filter(action='doc_ask'):
            self.assertNotIn('ساعت', event.detail)

    def test_demo_documents_are_synthetic_and_pass_the_screen(self):
        for title, text in demo_docs.DOCS.items():
            self.assertEqual(screen_text(text, self.a.pk), [], title)
