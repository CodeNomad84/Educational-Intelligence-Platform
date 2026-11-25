"""Tests for the JSON dashboard summary endpoint (Phase 3, Step 1).

Every figure is derived from the caller's own access scopes, so the tests assert both the happy
path (a SchoolAdmin with a small dataset) and the fail-closed path (a role with no scope).
"""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from risk.models import Alert, RiskEvent
from schools.models import School, SchoolMembership
from students.models import Attendance, Grade, Student

User = get_user_model()
PASSWORD = 'Str0ng-demo-pass-77'

SUMMARY_KEYS = {'meta', 'kpis', 'attendance_trend', 'average_trend', 'subjects',
                'subjects_by_grade', 'grades_present', 'alerts', 'students'}


class SummaryApiBase(TestCase):
    def setUp(self):
        self.school = School.objects.create(name='A', code='a')
        self.admin = User.objects.create_user('9000000001', password=PASSWORD, first_name='سارا', last_name='احمدی')
        self.admin.groups.add(Group.objects.get_or_create(name='SchoolAdmin')[0])
        SchoolMembership.objects.create(user=self.admin, school=self.school)
        self.url = reverse('api_dashboard_summary')

    def student(self, first='علی', last='رضایی', grade=9, national_id=None):
        n = national_id or f'{Student.objects.count() + 1000000000}'
        return Student.objects.create(first_name=first, last_name=last, national_id=n, grade=grade,
                                      phone_number='09120000000', school=self.school)

    def login(self, user=None):
        self.client.force_login(user or self.admin)


class ScopeTests(SummaryApiBase):
    def test_anonymous_is_json_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response['Content-Type'].split(';')[0], 'application/json')

    def test_no_scope_yields_empty_but_valid_payload(self):
        parent = User.objects.create_user('9000000002', password=PASSWORD)
        parent.groups.add(Group.objects.get_or_create(name='Parent')[0])
        self.login(parent)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), SUMMARY_KEYS)
        self.assertEqual(body['students'], [])
        self.assertEqual(body['alerts'], [])
        self.assertEqual(body['subjects'], [])
        self.assertEqual(body['kpis'][0]['value'], 0)          # students
        self.assertIsNone(body['kpis'][1]['value'])            # average
        self.assertIsNone(body['kpis'][2]['value'])            # attendance


class DataTests(SummaryApiBase):
    def setUp(self):
        super().setUp()
        today = timezone.localdate()
        self.s1 = self.student(first='علی', last='رضایی', grade=9)
        self.students = [self.s1]
        for first, last in [('مریم', 'احمدی'), ('حسین', 'کاظمی'), ('زهرا', 'موسوی'), ('رضا', 'نوری')]:
            self.students.append(self.student(first=first, last=last, grade=9))
        for s in self.students:
            Grade.objects.create(student=s, subject='math', exam_type='quiz', score=18, date=today)
            Grade.objects.create(student=s, subject='math', exam_type='quiz', score=14, date=today - timedelta(days=5))
            for n in range(3):
                Attendance.objects.create(student=s, date=today - timedelta(days=n), status='present')
        self.event = RiskEvent.objects.create(school=self.school, student=self.s1, risk_type='academic',
                                              severity='yellow', detected_by='teacher', explanation='x')
        Alert.objects.create(school=self.school, student=self.s1, risk_event=self.event, message='نیازمند توجه', status='new')

    def test_aggregates_follow_the_scope(self):
        self.login()
        body = self.client.get(self.url).json()
        kpis = {k['key']: k for k in body['kpis']}
        self.assertEqual(kpis['students']['value'], 5)
        self.assertEqual(kpis['average']['value'], 16.0)       # (18 + 14) / 2
        self.assertEqual(kpis['attendance']['value'], 100.0)
        self.assertEqual(kpis['alerts_open']['value'], 1)
        self.assertEqual(len(body['alerts']), 1)
        self.assertEqual(body['alerts'][0]['student_name'], 'علی رضایی')
        self.assertEqual(body['alerts'][0]['message'], 'نیازمند توجه')

    def test_roster_carries_real_gpa_and_status(self):
        self.login()
        body = self.client.get(self.url).json()
        by_name = {s['name']: s for s in body['students']}
        self.assertEqual(by_name['علی رضایی']['gpa'], 16.0)
        self.assertEqual(by_name['علی رضایی']['status'], 'growing')
        self.assertEqual(by_name['علی رضایی']['attendance_rate'], 100.0)

    def test_sensitive_alert_text_is_hidden(self):
        self.event.risk_type = 'emotional'
        self.event.save(update_fields=['risk_type'])
        self.login()
        body = self.client.get(self.url).json()
        alert = body['alerts'][0]
        self.assertTrue(alert['text_hidden'])
        self.assertEqual(alert['message'], '')
