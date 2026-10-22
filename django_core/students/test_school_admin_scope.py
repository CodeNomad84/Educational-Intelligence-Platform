"""S3 (changes/0010): the SchoolAdmin branch of ``visible_students/grades/attendances`` is the set of schools of the
user's active memberships. Two schools A and B with students, grades and attendances; synthetic data only.

Required by the owner decision of 2026-10-23: an EMPTY school set gives nothing (never "no filter") with a mutation
check; the temporary ``is_superuser`` branch (until S8) has a test that fails if it is removed; the per-request user
object is the unit of trust (H4).
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from schools.models import School, SchoolMembership

from .access import (
    ADMIN, PLATFORM_ADMIN, school_ids_for_admin, visible_attendances, visible_grades, visible_students)
from .models import Attendance, Grade, Student

User = get_user_model()


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = School.objects.create(name='A', code='a')
        cls.b = School.objects.create(name='B', code='b')
        cls.group = Group.objects.get_or_create(name=ADMIN)[0]
        cls.platform = Group.objects.get_or_create(name=PLATFORM_ADMIN)[0]
        cls.students = {}
        for key, school in (('a1', cls.a), ('a2', cls.a), ('b1', cls.b)):
            cls.students[key] = Student.objects.create(
                first_name=key, last_name='T', national_id=f'94{len(cls.students):08d}', grade=7, phone_number='0',
                school=school)
            Grade.objects.create(student=cls.students[key], subject='math', exam_type='quiz', score=15, date='2026-01-01')
            Attendance.objects.create(student=cls.students[key], date='2026-01-02', status='present')

    def admin(self, username, *schools, active=True, superuser=False):
        user = User.objects.create_user(username, password='x', is_staff=superuser, is_superuser=superuser)
        user.groups.add(self.group)
        for school in schools:
            SchoolMembership.objects.create(user=user, school=school, is_active=active)
        return user

    def sees(self, user):
        return ({s.first_name for s in visible_students(user)},
                {g.student.first_name for g in visible_grades(user)},
                {a.student.first_name for a in visible_attendances(user)})


class ScopeTests(Base):
    def test_admin_of_one_school_sees_only_that_school(self):
        self.assertEqual(self.sees(self.admin('one', self.a)), ({'a1', 'a2'},) * 3)
        self.assertEqual(self.sees(self.admin('other', self.b)), ({'b1'},) * 3)

    def test_admin_of_both_schools_sees_both(self):
        self.assertEqual(self.sees(self.admin('both', self.a, self.b)), ({'a1', 'a2', 'b1'},) * 3)

    def test_every_row_of_an_admin_is_full_tier(self):
        self.assertEqual({s.full_tier for s in visible_students(self.admin('one', self.a))}, {True})


class EmptySchoolSetTests(Base):
    """An empty ``school_ids_for_admin`` set means NO rows, not "no filter" (S1 review finding F3)."""

    def users(self):
        inactive_membership = self.admin('inactive_membership', self.a, active=False)
        no_membership = self.admin('no_membership')
        dual = self.admin('dual', self.a)
        dual.groups.add(self.platform)                       # PlatformAdmin + SchoolAdmin: separation of duties
        outside_group = User.objects.create_user('outside', password='x')
        SchoolMembership.objects.create(user=outside_group, school=self.a)       # bypasses clean(): not a SchoolAdmin
        inactive_user = self.admin('inactive_user', self.a)
        User.objects.filter(pk=inactive_user.pk).update(is_active=False)
        inactive_user.refresh_from_db()
        return [inactive_membership, no_membership, dual, outside_group, inactive_user]

    def test_every_empty_set_case_sees_nothing_in_students_grades_and_attendances(self):
        for user in self.users():
            with self.subTest(user=user.username):
                self.assertEqual(school_ids_for_admin(user), set())
                self.assertEqual(self.sees(user), (set(), set(), set()))
                self.assertEqual(visible_students(user).count(), 0)

    def test_the_helper_is_not_called_with_a_cached_set(self):
        user = self.admin('one', self.a)
        self.assertEqual(self.sees(user)[0], {'a1', 'a2'})
        SchoolMembership.objects.filter(user=user).update(is_active=False)   # revoked after a first read
        self.assertEqual(self.sees(user), (set(), set(), set()))


class SuperuserBranchTests(Base):
    """D2: until S8 a superuser keeps the global read through an EXPLICIT branch (``_sees_every_school``). The
    tests below FAIL if that branch is removed (the helper itself returns the empty set for a superuser)."""

    def test_superuser_without_membership_reads_every_school(self):
        root = self.admin('root', superuser=True)
        self.assertEqual(school_ids_for_admin(root), set())          # why the explicit branch is needed
        self.assertEqual(self.sees(root), ({'a1', 'a2', 'b1'},) * 3)
        self.assertEqual({s.full_tier for s in visible_students(root)}, {True})

    def test_an_inactive_superuser_sees_nothing(self):
        root = self.admin('root', superuser=True)
        User.objects.filter(pk=root.pk).update(is_active=False)
        root.refresh_from_db()
        self.assertEqual(self.sees(root), (set(), set(), set()))

    def test_the_branch_is_documented_as_temporary(self):
        import inspect
        from . import access
        self.assertIn('S8', inspect.getsource(access._sees_every_school))


class StaleUserTests(Base):
    """H4: the unit of trust is the per-request user object. Callers pass the freshly loaded ``request.user``; an object
    held across a change in the database keeps the flags it was loaded with unless it is refreshed."""

    def test_a_stale_object_keeps_its_old_flags_until_refreshed(self):
        root = self.admin('root', superuser=True)
        stale = User.objects.get(pk=root.pk)
        User.objects.filter(pk=root.pk).update(is_superuser=False)
        self.assertEqual(self.sees(stale)[0], {'a1', 'a2', 'b1'})                 # documented: stale object
        stale.refresh_from_db(fields=['is_active', 'is_superuser'])
        self.assertEqual(self.sees(stale), (set(), set(), set()))                 # refreshed: no membership, no read

    def test_a_stale_object_of_a_deactivated_admin_is_refused_once_refreshed(self):
        user = self.admin('one', self.a)
        stale = User.objects.get(pk=user.pk)
        User.objects.filter(pk=user.pk).update(is_active=False)
        stale.refresh_from_db(fields=['is_active', 'is_superuser'])
        self.assertEqual(school_ids_for_admin(stale), set())
        self.assertEqual(self.sees(stale), (set(), set(), set()))

    def test_a_logged_in_session_uses_the_flags_of_the_database_on_the_next_request(self):
        user = self.admin('one', self.a)
        self.client.force_login(user)
        self.assertEqual(self.client.get('/api/students/').status_code, 200)
        User.objects.filter(pk=user.pk).update(is_active=False)
        self.assertIn(self.client.get('/api/students/').status_code, (401, 403))   # deactivated: refused at once
        User.objects.filter(pk=user.pk).update(is_active=True)
        root = self.admin('root', superuser=True)
        self.client.force_login(root)
        names = {r['first_name'] for r in self.client.get('/api/students/').json()['results']}
        self.assertEqual(names, {'a1', 'a2', 'b1'})
        User.objects.filter(pk=root.pk).update(is_superuser=False)                 # demoted in the database
        body = self.client.get('/api/students/').json()
        self.assertEqual(body['results'] if isinstance(body, dict) else body, [])  # next request: nothing


class ApiAndDashboardScopeTests(Base):
    def test_api_list_detail_and_actions_are_scoped(self):
        user = self.admin('one', self.a)
        self.client.force_login(user)
        listing = self.client.get('/api/students/').json()
        rows = listing['results'] if isinstance(listing, dict) else listing
        self.assertEqual({r['first_name'] for r in rows}, {'a1', 'a2'})
        mine, foreign = self.students['a1'], self.students['b1']
        self.assertEqual(self.client.get(f'/api/students/{mine.pk}/').status_code, 200)
        for suffix in ('', 'features/', 'predict/'):
            self.assertEqual(self.client.get(f'/api/students/{foreign.pk}/{suffix}').status_code, 404, suffix)

    def test_api_list_of_an_admin_without_a_membership_is_empty(self):
        self.client.force_login(self.admin('none'))
        body = self.client.get('/api/students/').json()
        self.assertEqual(body['results'] if isinstance(body, dict) else body, [])


class DashboardAggregateScopeTests(Base):
    def counts(self, user):
        self.client.force_login(user)
        context = self.client.get('/dashboard/').context
        return context['total_students'], context['total_grades'], context['total_attendances'], context['avg_grade_all']

    def test_aggregates_cover_the_memberships_schools_only(self):
        self.assertEqual(self.counts(self.admin('one', self.a)), (2, 2, 2, 15))
        self.assertEqual(self.counts(self.admin('other', self.b)), (1, 1, 1, 15))
        self.assertEqual(self.counts(self.admin('both', self.a, self.b)), (3, 3, 3, 15))

    def test_an_empty_school_set_gives_zero_aggregates(self):
        self.assertEqual(self.counts(self.admin('none')), (0, 0, 0, 0))
        self.assertEqual(self.counts(self.admin('off', self.a, active=False)), (0, 0, 0, 0))

    def test_the_superuser_branch_still_sees_every_school(self):
        self.assertEqual(self.counts(self.admin('root', superuser=True)), (3, 3, 3, 15))
