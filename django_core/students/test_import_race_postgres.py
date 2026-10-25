"""S4(b): a REAL concurrent import race on PostgreSQL, made deterministic by interleaving instead of timing.

The main thread holds an UNCOMMITTED insert of a national id; a worker thread then runs the import write (``import_store.write_row``)
for the same id on its own connection. PostgreSQL makes the worker's INSERT wait on the unique index; the test waits until it is
really blocked (``pg_stat_activity``), commits the main insert, and the worker's INSERT must fail with ``ImportConflict`` and
overwrite nothing. A plain ``update_or_create`` would instead fall back to updating the row that just appeared (the original bug).

It needs real row/index locking, so it runs on PostgreSQL only: in ``scripts/run_tests.sh pg`` and the CI ``postgres`` job, both of
which set ``EIP_REQUIRE_PG=1``. With that variable set, running it on another database FAILS instead of skipping, so CI can never
report green while this test silently did not run. Synthetic data only.
"""
import os
import threading
import time

from django.db import connection, transaction
from django.test import TransactionTestCase

from schools.models import School
from students import import_store
from students.models import Student

WAIT_SECONDS = 15


class PostgresImportRaceTests(TransactionTestCase):
    def setUp(self):
        if connection.vendor != 'postgresql':
            if os.environ.get('EIP_REQUIRE_PG') == '1':
                self.fail('EIP_REQUIRE_PG=1 but the database is not PostgreSQL: the import-race test must run in this job.')
            self.skipTest('needs PostgreSQL row/index locking (runs in run_tests.sh pg and the CI postgres job)')
        self.a = School.objects.create(name='RaceA', code='race-a')
        self.b = School.objects.create(name='RaceB', code='race-b')

    def _race(self, holder_school, importer_school, national_id):
        """Main thread: uncommitted student of ``holder_school``. Worker: import write of the same id for ``importer_school``."""
        outcome = {}

        def worker():
            try:
                with transaction.atomic():                     # as in views._write_import_row: one transaction per row
                    outcome['result'] = import_store.write_row(importer_school.pk, national_id, {
                        'first_name': 'Imported', 'last_name': 'Late', 'grade': 9, 'phone_number': '2', 'school_id': importer_school.pk})
            except Exception as exc:                       # the type is what the test asserts
                outcome['error'] = type(exc).__name__
            finally:
                connection.close()

        thread = threading.Thread(target=worker)
        with transaction.atomic():
            Student.objects.create(first_name='Holder', last_name='First', national_id=national_id, grade=7, phone_number='1',
                                   school=holder_school)
            thread.start()
            deadline = time.monotonic() + WAIT_SECONDS
            while True:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_stat_clear_snapshot()')      # inside a transaction the activity view is cached
                    cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                                   "AND wait_event_type = 'Lock' AND state = 'active'")
                    if cursor.fetchone()[0]:
                        break
                if time.monotonic() > deadline or not thread.is_alive():
                    break
                time.sleep(0.05)
            blocked = thread.is_alive()
        thread.join(WAIT_SECONDS)                          # the main insert is committed here: the worker is released
        self.assertTrue(blocked, f'the worker never blocked on the uncommitted row: the interleaving did not happen ({outcome})')
        self.assertFalse(thread.is_alive(), 'the worker is still waiting after the commit')
        return outcome

    def test_a_concurrent_import_of_an_id_that_appears_meanwhile_is_a_conflict_and_overwrites_nothing(self):
        outcome = self._race(self.b, self.a, '9600000001')                 # another school wins the id
        self.assertEqual(outcome, {'error': 'ImportConflict'})
        rows = list(Student.objects.filter(national_id='9600000001').values_list('first_name', 'grade', 'school_id'))
        self.assertEqual(rows, [('Holder', 7, self.b.pk)])                 # untouched, not moved to school A

    def test_two_imports_of_the_same_new_id_in_one_school_leave_exactly_one_row(self):
        outcome = self._race(self.a, self.a, '9600000002')                 # the same school: still a lost race, not an overwrite
        self.assertEqual(outcome, {'error': 'ImportConflict'})
        rows = list(Student.objects.filter(national_id='9600000002').values_list('first_name', 'grade', 'school_id'))
        self.assertEqual(rows, [('Holder', 7, self.a.pk)])
