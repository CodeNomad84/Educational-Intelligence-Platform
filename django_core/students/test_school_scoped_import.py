"""S3: the live import reads only the importer's school (students/import_store.py) and can never move an existing
student to another school. Synthetic data only."""
import ast
import inspect
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from schools.models import School, SchoolClass, SchoolMembership

from . import import_store, views
from .access import ADMIN
from .models import Student

User = get_user_model()
HEADER = 'first_name,last_name,national_id,grade,class_name,phone_number,father_job,mother_job'
GENERIC = 'این کد ملی قابل ثبت نیست.'


def upload(*lines):
    return SimpleUploadedFile('s.csv', ('\n'.join((HEADER,) + lines) + '\n').encode('utf-8-sig'), content_type='text/csv')


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = School.objects.create(name='A', code='a')
        cls.b = School.objects.create(name='B', code='b')
        cls.class_a = SchoolClass.objects.create(school=cls.a, title='7-A', academic_year='1404', grade=7)
        cls.class_b = SchoolClass.objects.create(school=cls.b, title='7-B', academic_year='1404', grade=7)
        cls.group = Group.objects.get_or_create(name=ADMIN)[0]

    def importer(self, name, school):
        user = User.objects.create_user(name, password='x', is_staff=True)
        user.groups.add(self.group)
        SchoolMembership.objects.create(user=user, school=school)
        return user

    def post(self, user, *lines, **extra):
        self.client.force_login(user)
        return self.client.post('/api/students/import/', {'file': upload(*lines), **extra})

    def student(self, nid, school, klass=None, name='Old'):
        return Student.objects.create(first_name=name, last_name='L', national_id=nid, grade=7, phone_number='0',
                                      school=school, school_class=klass)

    def row(self, pk):
        s = Student.objects.get(pk=pk)
        return (s.school_id, s.school_class_id, s.first_name, s.grade)


class ExistingStudentCannotMoveTests(Base):
    def test_a_student_of_another_school_is_refused_with_the_generic_message_and_stays_untouched(self):
        foreign = self.student('9500000001', self.a, self.class_a)
        before = self.row(foreign.pk)
        body = self.post(self.importer('imp_b', self.b), 'New,Name,9500000001,9,7-B,0912,Dr,Nurse').json()
        self.assertEqual((body['created'], body['updated'], body['linked']), (0, 0, 0))
        self.assertEqual(len(body['errors']), 1)
        self.assertIn(GENERIC, body['errors'][0])
        self.assertEqual(self.row(foreign.pk), before)
        self.assertEqual(Student.objects.filter(national_id='9500000001').count(), 1)

    def test_the_planning_reads_do_not_see_other_schools_students(self):
        self.student('9500000002', self.a, self.class_a)
        self.assertEqual(import_store.linked_national_ids(self.b.pk, ['9500000002']), set())
        self.assertEqual(import_store.existing_state(self.b.pk, ['9500000002']), {})
        self.assertEqual(import_store.grades_by_class(self.b.pk, [self.class_a.pk]), {})
        self.assertEqual(import_store.linked_national_ids(self.a.pk, ['9500000002']), {'9500000002'})

    def test_an_update_of_an_own_student_keeps_its_school(self):
        own = self.student('9500000003', self.a)
        body = self.post(self.importer('imp_a', self.a), 'Renamed,L,9500000003,8,7-A,0912,Dr,Nurse').json()
        self.assertEqual((body['updated'], body['errors']), (1, []))
        self.assertEqual(self.row(own.pk)[0], self.a.pk)

    def test_a_planned_link_into_a_class_of_another_school_is_refused_and_nothing_moves(self):
        own = self.student('9500000004', self.a)
        before = self.row(own.pk)
        real_plan = views._plan_class_links

        def plan_into_the_other_school(rows, school_id):
            plan = real_plan(rows, school_id)
            plan.decisions = {r.index: self.class_b.pk for r in rows}    # a buggy planner
            return plan

        with mock.patch.object(views, '_plan_class_links', plan_into_the_other_school):
            body = self.post(self.importer('imp_a', self.a), 'Renamed,L,9500000004,8,7-A,0912,Dr,Nurse').json()
        self.assertEqual(self.row(own.pk), before)                      # not renamed, not moved, not linked
        self.assertEqual((body['updated'], body['linked']), (0, 0))
        self.assertIn(GENERIC, body['errors'][0])

    def test_a_write_that_returns_a_student_of_another_school_is_rolled_back(self):
        own = self.student('9500000005', self.a)
        before = self.row(own.pk)
        real_write = import_store.write_row

        def moving_write(national_id, defaults):
            student, created = real_write(national_id, {**defaults, 'school_id': self.b.pk})
            return student, created

        with mock.patch.object(import_store, 'write_row', moving_write):
            body = self.post(self.importer('imp_a', self.a), 'Renamed,L,9500000005,8,,0912,Dr,Nurse').json()
        self.assertEqual(self.row(own.pk), before)                      # the row's transaction was rolled back
        self.assertEqual(body['updated'], 0)
        self.assertIn(GENERIC, body['errors'][0])

    def test_a_new_student_gets_the_importers_school_never_the_files(self):
        self.post(self.importer('imp_b', self.b), 'New,Name,9500000006,7,,0912,Dr,Nurse')
        self.assertEqual(Student.objects.get(national_id='9500000006').school_id, self.b.pk)


class ImportStoreScopeTests(TestCase):
    def test_every_function_takes_school_id_except_the_two_cross_school_ones(self):
        tree = ast.parse(inspect.getsource(import_store))
        functions = {n.name: [a.arg for a in n.args.args] for n in tree.body
                     if isinstance(n, ast.FunctionDef) and not n.name.startswith('_')}
        for name, args in functions.items():
            if name in import_store.CROSS_SCHOOL_BY_NECESSITY:
                self.assertNotIn('school_id', args, name)
            else:
                self.assertEqual(args[0], 'school_id', name)
        self.assertEqual(set(import_store.CROSS_SCHOOL_BY_NECESSITY) - set(functions), set())
        # review F6: the exemption list is pinned and every scoped function really filters on the school
        self.assertEqual(import_store.CROSS_SCHOOL_BY_NECESSITY, ('locked_state', 'write_row'))
        for name in functions:
            if name not in import_store.CROSS_SCHOOL_BY_NECESSITY:
                self.assertIn('school_id=school_id', inspect.getsource(getattr(import_store, name)), name)

    def test_views_no_longer_reach_the_student_manager(self):
        self.assertNotIn('Student.objects', inspect.getsource(views))
