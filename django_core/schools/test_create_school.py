"""C-B (docs/changes/0026): ``create_school`` and the Django-admin add path both write a ``school_create`` audit event; the
command seeds the vocabulary, refuses bad or taken codes and leaves nothing behind on failure. Synthetic data only."""
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from vocabulary.models import VocabularyTerm

from .models import AuditEvent, School


class CreateSchoolCommandTests(TestCase):
    def test_creates_audits_and_seeds(self):
        out = StringIO()
        call_command('create_school', 'pilot-1', ' مدرسه آزمایشی ', stdout=out)
        school = School.objects.get(code='pilot-1')
        self.assertEqual(school.name, 'مدرسه آزمایشی')
        event = AuditEvent.objects.get(action='school_create')
        self.assertEqual((event.school_id, event.username, event.user_id, event.detail, event.object_type, event.object_id),
                         (school.pk, 'system', None, 'cmd', 'School', str(school.pk)))
        self.assertTrue(VocabularyTerm.objects.filter(school=school).exists())
        self.assertIn('pilot-1: created', out.getvalue())

    def test_works_when_several_schools_exist(self):
        School.objects.create(name='A', code='a')
        call_command('create_school', 'b', 'B', stdout=StringIO())
        self.assertEqual(set(VocabularyTerm.objects.values_list('school__code', flat=True)), {'b'})

    def test_refusals_change_nothing(self):
        School.objects.create(name='A', code='a')
        before = (School.objects.count(), AuditEvent.objects.count())
        for args, message in ((('a', 'X'), 'already exists'), (('bad code', 'X'), 'only letters'), (('x/y', 'X'), 'only letters'),
                              (('ok', '  '), 'name is empty'), (('x' * 51, 'X'), 'too long')):
            with self.subTest(args=args), self.assertRaisesMessage(CommandError, message):
                call_command('create_school', *args, stdout=StringIO())
        self.assertEqual((School.objects.count(), AuditEvent.objects.count()), before)

    def test_failure_in_seed_rolls_back(self):
        with mock.patch('schools.management.commands.create_school.call_command', side_effect=RuntimeError('boom')):
            with self.assertRaises(RuntimeError):
                call_command('create_school', 'c', 'C', stdout=StringIO())
        self.assertFalse(School.objects.filter(code='c').exists())
        self.assertFalse(AuditEvent.objects.filter(action='school_create').exists())


class AdminAddSchoolTests(TestCase):
    def setUp(self):
        self.root = get_user_model().objects.create_superuser('root', password='pw-123456789')
        self.client.force_login(self.root)

    def test_admin_add_is_audited_change_is_not(self):
        response = self.client.post('/admin/schools/school/add/', {'name': 'D', 'code': 'd'})
        self.assertEqual(response.status_code, 302)
        school = School.objects.get(code='d')
        event = AuditEvent.objects.get(action='school_create')
        self.assertEqual((event.school_id, event.user_id, event.detail), (school.pk, self.root.pk, 'admin'))
        self.client.post(f'/admin/schools/school/{school.pk}/change/', {'name': 'D2', 'code': 'd'})
        self.assertEqual(School.objects.get(pk=school.pk).name, 'D2')
        self.assertEqual(AuditEvent.objects.filter(action='school_create').count(), 1)
