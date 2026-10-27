"""0025 (d): two simultaneous runs the same day must not create duplicate alerts - a REAL concurrent race on PostgreSQL,
deterministic by interleaving (same technique as ``students/test_import_race_postgres.py``).

The main thread holds an UNCOMMITTED hit (+ its alert) for (rule, student, day). A worker thread runs ``run_school`` on its own
connection: it cannot see the uncommitted hit (so the cooldown does not stop it), raises its alert and blocks on the unique index
of ``RuleHit``. After the main commit, the worker's insert must fail and its alert must be rolled back with it: exactly one alert.
PostgreSQL only (``EIP_REQUIRE_PG=1`` turns a skip into a failure in the pg job). Synthetic data only."""
import os
import threading
import time
from datetime import date, timedelta

from django.db import connection, transaction
from django.test import TransactionTestCase

from risk import rules
from risk.models import Alert, RiskEvent, Rule, RuleHit, RuleSettings
from risk.services import raise_alert
from schools.models import AcademicYear, School, SchoolClass
from students.enrollment_sync import ensure_current_enrollment
from students.models import Attendance, Student

WAIT_SECONDS = 15
TODAY = date(2026, 3, 1)


class PostgresRuleRaceTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != 'postgresql':
            if os.environ.get('EIP_REQUIRE_PG') == '1':
                self.fail('EIP_REQUIRE_PG=1 but the database is not PostgreSQL: the rule-race test must run in this job.')
            self.skipTest('needs PostgreSQL row/index locking (runs in run_tests.sh pg and the CI postgres job)')
        self.school = School.objects.create(name='RuleRace', code='rule-race')
        AcademicYear.objects.create(school=self.school, code='1404-1405', start_date=date(2025, 9, 23),
                                    end_date=date(2026, 6, 21), is_current=True)
        klass = SchoolClass.objects.create(school=self.school, title='7-A', academic_year='1404-1405', grade=7)
        self.students = []
        for n in range(8):
            student = Student.objects.create(first_name=f'K{n}', last_name='X', national_id=f'97{n:08d}', grade=7,
                                             phone_number='1', school=self.school, school_class=klass)
            ensure_current_enrollment(student, source='manual')
            self.students.append(student)
        for d in range(1, 8):
            Attendance.objects.create(student=self.students[0], date=TODAY - timedelta(days=d), status='absent')
        RuleSettings.objects.create(school=self.school)
        self.rule = Rule.objects.create(
            school=self.school, code='repeated_absence', version=1, kind='repeated_absence', title='t', risk_type='attendance',
            severity='yellow', status='active', clauses=rules.STARTERS['repeated_absence']['clauses'], connective='any')

    def test_two_simultaneous_runs_leave_exactly_one_alert(self):
        outcome = {}

        def worker():
            try:
                outcome['runs'] = [r.alerts_raised for r in rules.run_school(self.school.pk, as_of=TODAY)]
            except Exception as exc:
                outcome['error'] = repr(exc)
            finally:
                connection.close()

        thread = threading.Thread(target=worker)
        with transaction.atomic():
            alert = raise_alert(self.students[0], risk_type='attendance', severity='yellow', message='m', explanation='e',
                                detected_by='rule_engine')
            RuleHit.objects.create(school=self.school, rule=self.rule, student=self.students[0], alert=alert, evaluated_on=TODAY,
                                   evidence={'items': []})
            thread.start()
            deadline = time.monotonic() + WAIT_SECONDS
            while True:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_stat_clear_snapshot()')
                    cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                                   "AND wait_event_type = 'Lock' AND state = 'active'")
                    if cursor.fetchone()[0]:
                        break
                if time.monotonic() > deadline or not thread.is_alive():
                    break
                time.sleep(0.05)
            blocked = thread.is_alive()
        thread.join(WAIT_SECONDS)
        self.assertTrue(blocked, f'the worker never blocked on the uncommitted hit: no real interleaving ({outcome})')
        self.assertFalse(thread.is_alive())
        self.assertEqual(outcome, {'runs': [0]})
        self.assertEqual((Alert.objects.count(), RiskEvent.objects.count(), RuleHit.objects.count()), (1, 1, 1))
