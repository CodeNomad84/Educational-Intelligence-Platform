"""S2b commit 1: the single school-resolution rule (students/student_school.py). Pure decision, no wiring yet."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from schools.models import School, SchoolClass, SchoolMembership

from .student_school import (
    CLASS_TARGET_MISMATCH, NO_SCHOOL_ACCESS, SCHOOL_CHANGE, SCHOOL_NOT_ALLOWED, STUDENT_WITHOUT_SCHOOL, TARGET_REQUIRED,
    StudentSchoolError, allowed_school_ids, resolve_student_school)

User = get_user_model()


class ResolveStudentSchoolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = School.objects.create(name='A', code='a')
        cls.b = School.objects.create(name='B', code='b')
        cls.class_a = SchoolClass.objects.create(school=cls.a, title='7-A', academic_year='1404', grade=7)
        cls.class_b = SchoolClass.objects.create(school=cls.b, title='7-B', academic_year='1404', grade=7)
        cls.admin_group = Group.objects.get_or_create(name='SchoolAdmin')[0]
        cls.platform_group = Group.objects.get_or_create(name='PlatformAdmin')[0]

    def admin(self, username, *schools, active_membership=True):
        user = User.objects.create_user(username, password='x')
        user.groups.add(self.admin_group)
        for school in schools:
            SchoolMembership.objects.create(user=user, school=school, is_active=active_membership)
        return user

    def assertCode(self, code, *args, **kwargs):
        with self.assertRaises(StudentSchoolError) as ctx:
            resolve_student_school(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code)

    # --- one membership: implied -------------------------------------------------------------------------
    def test_one_membership_is_implied_without_class_or_target(self):
        self.assertEqual(resolve_student_school(self.admin('one', self.a)), self.a.pk)

    def test_one_membership_with_its_own_class(self):
        self.assertEqual(resolve_student_school(self.admin('one', self.a), school_class=self.class_a), self.a.pk)

    def test_one_membership_and_a_foreign_class_is_rejected(self):
        self.assertCode(SCHOOL_NOT_ALLOWED, self.admin('one', self.a), school_class=self.class_b)

    def test_one_membership_and_a_foreign_target_is_rejected(self):
        self.assertCode(SCHOOL_NOT_ALLOWED, self.admin('one', self.a), target_school_id=self.b.pk)

    # --- several memberships: required ---------------------------------------------------------------------
    def test_several_memberships_need_a_target(self):
        self.assertCode(TARGET_REQUIRED, self.admin('two', self.a, self.b))

    def test_several_memberships_with_a_target(self):
        self.assertEqual(resolve_student_school(self.admin('two', self.a, self.b), target_school_id=self.b.pk),
                         self.b.pk)

    def test_target_may_be_a_numeric_string(self):
        self.assertEqual(resolve_student_school(self.admin('two', self.a, self.b), target_school_id=str(self.b.pk)),
                         self.b.pk)

    def test_class_alone_is_enough_with_several_memberships(self):
        self.assertEqual(resolve_student_school(self.admin('two', self.a, self.b), school_class=self.class_b),
                         self.b.pk)

    # --- zero memberships: rejected, also with a class or target -----------------------------------------------
    def test_no_membership_is_rejected_in_every_combination(self):
        user = self.admin('none')
        self.assertCode(NO_SCHOOL_ACCESS, user)
        self.assertCode(NO_SCHOOL_ACCESS, user, school_class=self.class_a)
        self.assertCode(NO_SCHOOL_ACCESS, user, target_school_id=self.a.pk)

    def test_inactive_membership_counts_as_none(self):
        self.assertCode(NO_SCHOOL_ACCESS, self.admin('off', self.a, active_membership=False))

    def test_platform_admin_with_a_membership_is_rejected(self):
        user = self.admin('dual', self.a)
        user.groups.add(self.platform_group)
        self.assertCode(NO_SCHOOL_ACCESS, user, school_class=self.class_a)

    def test_user_outside_the_school_admin_group_is_rejected(self):
        user = User.objects.create_user('teacher', password='x', is_staff=True)
        SchoolMembership.objects.create(user=user, school=self.a)
        self.assertCode(NO_SCHOOL_ACCESS, user, school_class=self.class_a)

    def test_inactive_and_anonymous_users_are_rejected(self):
        user = self.admin('gone', self.a)
        user.is_active = False
        user.save()
        self.assertCode(NO_SCHOOL_ACCESS, user)
        self.assertCode(NO_SCHOOL_ACCESS, None)
        from django.contrib.auth.models import AnonymousUser
        self.assertCode(NO_SCHOOL_ACCESS, AnonymousUser())

    # --- superuser: explicit, never defaulted ---------------------------------------------------------------
    def test_superuser_needs_a_target_even_with_one_school_only(self):
        root = User.objects.create_superuser('root', password='x')
        self.assertCode(TARGET_REQUIRED, root)

    def test_superuser_may_name_any_school_or_use_a_class(self):
        root = User.objects.create_superuser('root', password='x')
        self.assertEqual(resolve_student_school(root, target_school_id=self.b.pk), self.b.pk)
        self.assertEqual(resolve_student_school(root, school_class=self.class_a), self.a.pk)

    def test_superuser_naming_a_missing_school_is_rejected_generically(self):
        root = User.objects.create_superuser('root', password='x')
        self.assertCode(SCHOOL_NOT_ALLOWED, root, target_school_id=999999)

    def test_superuser_with_a_single_school_is_still_not_defaulted(self):
        SchoolClass.objects.all().delete()
        School.objects.exclude(pk=self.a.pk).delete()
        root = User.objects.create_superuser('root', password='x')
        self.assertEqual(list(School.objects.values_list('pk', flat=True)), [self.a.pk])
        self.assertCode(TARGET_REQUIRED, root)

    # --- class and target -------------------------------------------------------------------------------------
    def test_class_and_target_that_disagree_are_rejected(self):
        self.assertCode(CLASS_TARGET_MISMATCH, self.admin('two', self.a, self.b),
                        school_class=self.class_a, target_school_id=self.b.pk)

    def test_class_and_target_that_agree_are_accepted(self):
        self.assertEqual(resolve_student_school(self.admin('two', self.a, self.b), school_class=self.class_a,
                                                target_school_id=self.a.pk), self.a.pk)

    def test_garbage_targets_are_rejected(self):
        user = self.admin('two', self.a, self.b)
        for bad in ("abc", True, [1], {}, object()):
            with self.subTest(bad=bad):
                self.assertCode(SCHOOL_NOT_ALLOWED, user, target_school_id=bad)

    def test_empty_target_counts_as_not_given(self):
        self.assertEqual(resolve_student_school(self.admin('one', self.a), target_school_id=''), self.a.pk)

    # --- existing students -------------------------------------------------------------------------------------
    def test_existing_school_is_kept_without_class_or_target(self):
        self.assertEqual(resolve_student_school(self.admin('two', self.a, self.b), existing_school_id=self.b.pk),
                         self.b.pk)

    def test_existing_school_cannot_change_by_target_or_class(self):
        user = self.admin('two', self.a, self.b)
        self.assertCode(SCHOOL_CHANGE, user, target_school_id=self.a.pk, existing_school_id=self.b.pk)
        self.assertCode(SCHOOL_CHANGE, user, school_class=self.class_a, existing_school_id=self.b.pk)

    def test_existing_student_of_a_school_outside_the_users_schools_is_rejected(self):
        self.assertCode(SCHOOL_NOT_ALLOWED, self.admin('one', self.a), existing_school_id=self.b.pk)

    def test_existing_student_without_school_needs_the_normal_rule(self):
        self.assertCode(TARGET_REQUIRED, self.admin('two', self.a, self.b), existing_school_id=None)
        self.assertEqual(resolve_student_school(self.admin('one', self.a), existing_school_id=None), self.a.pk)

    # --- S6: an existing student without a school is never adopted ----------------------------------------------
    def test_existing_student_without_school_is_rejected_for_every_kind_of_user(self):
        root = User.objects.create_superuser('root', password='x')
        for user in (self.admin('one', self.a), self.admin('two', self.a, self.b), root):
            for kwargs in ({}, {'school_class': self.class_a}, {'target_school_id': self.a.pk}):
                with self.subTest(user=user.username, kwargs=list(kwargs)):
                    self.assertCode(STUDENT_WITHOUT_SCHOOL, user, is_existing=True, **kwargs)

    def test_a_user_without_access_still_gets_the_access_error_first(self):
        self.assertCode(NO_SCHOOL_ACCESS, self.admin('none'), is_existing=True)

    def test_existing_student_with_a_school_is_unaffected_by_the_flag(self):
        self.assertEqual(resolve_student_school(self.admin('two', self.a, self.b), existing_school_id=self.b.pk,
                                                is_existing=True), self.b.pk)

    # --- messages never reveal the other school ------------------------------------------------------------------
    def test_not_allowed_message_is_identical_for_existing_and_missing_schools(self):
        user = self.admin('one', self.a)
        messages = set()
        for target in (self.b.pk, 999999):
            with self.assertRaises(StudentSchoolError) as ctx:
                resolve_student_school(user, target_school_id=target)
            messages.add((ctx.exception.code, ctx.exception.message))
        self.assertEqual(len(messages), 1)

    def test_allowed_school_ids(self):
        self.assertEqual(allowed_school_ids(self.admin('two', self.a, self.b)), {self.a.pk, self.b.pk})
        self.assertEqual(allowed_school_ids(User.objects.create_superuser('root', password='x')),
                         set(School.objects.values_list('pk', flat=True)))
