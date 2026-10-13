"""C1 tests: School / SchoolClass / TeacherAssignment structure and admin (proposal 0002).

Traceability: REQ: P2-REQ-04 (assignments via admin), P2-REQ-05 (School key), P2-REQ-17 (teachers are never
staff, ``auth.*`` stays superuser-only). No visibility change is part of C1; a guard test proves it.
"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from students.access import ADMIN, TEACHER, visible_students
from students.models import Student

from .admin import SchoolAdmin, TeacherAssignmentAdmin
from .models import School, SchoolClass, TeacherAssignment

User = get_user_model()


def make_user(username, group=None, **extra):
    user = User.objects.create_user(username=username, **extra)
    user.set_unusable_password()
    user.save()
    if group:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    return user


class StructureTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="School A", code="school-a")
        self.other = School.objects.create(name="School B", code="school-b")

    def test_school_code_is_unique(self):
        """REQ: P2-REQ-05"""
        with self.assertRaises(IntegrityError), transaction.atomic():
            School.objects.create(name="Dup", code="school-a")

    def test_class_unique_per_school_year_title(self):
        """REQ: P2-REQ-05"""
        SchoolClass.objects.create(school=self.school, title="10-A", academic_year="1404")
        with self.assertRaises(IntegrityError), transaction.atomic():
            SchoolClass.objects.create(school=self.school, title="10-A", academic_year="1404")

    def test_same_title_allowed_in_other_year_or_school(self):
        """REQ: P2-REQ-05"""
        SchoolClass.objects.create(school=self.school, title="10-A", academic_year="1404")
        SchoolClass.objects.create(school=self.school, title="10-A", academic_year="1405")
        SchoolClass.objects.create(school=self.other, title="10-A", academic_year="1404")
        self.assertEqual(SchoolClass.objects.filter(title="10-A").count(), 3)

    def test_school_with_classes_cannot_be_deleted(self):
        """REQ: P2-REQ-05 (PROTECT: no silent loss of class structure)"""
        SchoolClass.objects.create(school=self.school, title="10-A")
        with self.assertRaises(ProtectedError):
            self.school.delete()

    def test_class_defaults_to_active(self):
        self.assertTrue(SchoolClass.objects.create(school=self.school, title="9-B").is_active)


class TeacherAssignmentValidationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="School A", code="school-a")
        self.klass = SchoolClass.objects.create(school=self.school, title="10-A", academic_year="1404")
        self.teacher = make_user("teacher_a", TEACHER)

    def assignment(self, **kw):
        data = {"teacher": self.teacher, "school_class": self.klass}
        data.update(kw)
        return TeacherAssignment(**data)

    def test_valid_assignment_passes(self):
        """REQ: P2-REQ-04"""
        self.assignment().full_clean()

    def test_user_without_teacher_group_is_rejected(self):
        """REQ: P2-REQ-04"""
        for user in (make_user("nogroup"), make_user("parent", "Parent"), make_user("admin_g", ADMIN)):
            with self.assertRaises(ValidationError) as ctx:
                self.assignment(teacher=user).full_clean()
            self.assertIn("teacher", ctx.exception.message_dict)

    def test_inactive_user_is_rejected(self):
        """REQ: P2-REQ-04"""
        user = make_user("gone", TEACHER, is_active=False)
        with self.assertRaises(ValidationError) as ctx:
            self.assignment(teacher=user).full_clean()
        self.assertIn("teacher", ctx.exception.message_dict)

    def test_staff_and_superuser_cannot_be_teachers(self):
        """REQ: P2-REQ-17 (admin site bypasses student scoping, so teachers are never staff)"""
        staff = make_user("staff_t", TEACHER, is_staff=True)
        root = make_user("root_t", TEACHER, is_superuser=True)
        for user in (staff, root):
            with self.assertRaises(ValidationError) as ctx:
                self.assignment(teacher=user).full_clean()
            self.assertIn("teacher", ctx.exception.message_dict)

    def test_inactive_class_is_rejected(self):
        """REQ: P2-REQ-04"""
        self.klass.is_active = False
        self.klass.save()
        with self.assertRaises(ValidationError) as ctx:
            self.assignment().full_clean()
        self.assertIn("school_class", ctx.exception.message_dict)

    def test_duplicate_assignment_is_rejected(self):
        """REQ: P2-REQ-04"""
        TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.klass, subject="math")
        with self.assertRaises(ValidationError):
            self.assignment(subject="math").full_clean()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.klass, subject="math")

    def test_same_teacher_class_with_other_subject_is_allowed(self):
        TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.klass, subject="math")
        self.assignment(subject="physics").full_clean()

    def test_deleting_teacher_or_class_removes_assignment(self):
        TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.klass)
        self.teacher.delete()
        self.assertEqual(TeacherAssignment.objects.count(), 0)
        other = make_user("teacher_b", TEACHER)
        TeacherAssignment.objects.create(teacher=other, school_class=self.klass)
        self.klass.delete()
        self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_created_by_survives_creator_deletion_as_null(self):
        creator = make_user("creator")
        row = TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.klass, created_by=creator)
        creator.delete()
        row.refresh_from_db()
        self.assertIsNone(row.created_by_id)


class NoVisibilityChangeTests(TestCase):
    def test_assignment_alone_does_not_grant_student_access(self):
        """REQ: P2-REQ-02 is NOT delivered by C1: Student has no class link and access.py is unchanged."""
        school = School.objects.create(name="School A", code="school-a")
        klass = SchoolClass.objects.create(school=school, title="10-A")
        teacher = make_user("teacher_a", TEACHER)
        TeacherAssignment.objects.create(teacher=teacher, school_class=klass)
        Student.objects.create(first_name="S", last_name="One", national_id="0000000001", grade=10,
                               class_name="10-A", phone_number="0")
        self.assertEqual(visible_students(teacher).count(), 0)


class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="School A", code="school-a")
        cls.klass = SchoolClass.objects.create(school=cls.school, title="10-A", academic_year="1404")
        cls.closed = SchoolClass.objects.create(school=cls.school, title="9-Z", is_active=False)
        cls.teacher = make_user("teacher_a", TEACHER)
        cls.root = make_user("root", is_superuser=True, is_staff=True)

    def setUp(self):
        self.rf = RequestFactory()

    def request_for(self, user):
        request = self.rf.get("/")
        request.user = user
        return request

    def test_models_are_registered(self):
        for model in (School, SchoolClass, TeacherAssignment):
            self.assertIn(model, admin.site._registry)

    def test_teacher_choices_only_active_non_staff_teachers(self):
        """REQ: P2-REQ-04, P2-REQ-17"""
        make_user("inactive_t", TEACHER, is_active=False)
        make_user("staff_t", TEACHER, is_staff=True)
        make_user("plain")
        make_user("parent_p", "Parent")
        model_admin = TeacherAssignmentAdmin(TeacherAssignment, admin.site)
        field = TeacherAssignment._meta.get_field("teacher")
        qs = model_admin.formfield_for_foreignkey(field, self.request_for(self.root)).queryset
        self.assertEqual(list(qs.values_list("username", flat=True)), ["teacher_a"])

    def test_class_choices_only_active_classes(self):
        model_admin = TeacherAssignmentAdmin(TeacherAssignment, admin.site)
        field = TeacherAssignment._meta.get_field("school_class")
        qs = model_admin.formfield_for_foreignkey(field, self.request_for(self.root)).queryset
        self.assertEqual(list(qs), [self.klass])

    def test_superuser_can_add_assignment_and_creator_is_recorded(self):
        """REQ: P2-REQ-04"""
        self.client.force_login(self.root)
        url = reverse("admin:schools_teacherassignment_add")
        self.assertEqual(self.client.get(url).status_code, 200)
        resp = self.client.post(url, {"teacher": self.teacher.pk, "school_class": self.klass.pk, "subject": "math"})
        self.assertEqual(resp.status_code, 302)
        row = TeacherAssignment.objects.get()
        self.assertEqual((row.teacher, row.school_class, row.created_by), (self.teacher, self.klass, self.root))

    def test_admin_form_rejects_non_teacher(self):
        """REQ: P2-REQ-04"""
        outsider = make_user("outsider")
        self.client.force_login(self.root)
        resp = self.client.post(reverse("admin:schools_teacherassignment_add"),
                                {"teacher": outsider.pk, "school_class": self.klass.pk, "subject": ""})
        self.assertEqual(resp.status_code, 200)  # form re-rendered with errors
        self.assertEqual(TeacherAssignment.objects.count(), 0)

    def test_staff_without_permissions_cannot_reach_assignment_admin(self):
        """REQ: P2-REQ-17 (no grants exist in C1)"""
        staff = make_user("staff_plain", is_staff=True)
        self.client.force_login(staff)
        for name in ("admin:schools_teacherassignment_add", "admin:schools_teacherassignment_changelist",
                     "admin:schools_school_changelist", "admin:schools_schoolclass_add"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_teacher_cannot_reach_admin(self):
        """REQ: P2-REQ-17"""
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse("admin:schools_teacherassignment_changelist"))
        self.assertEqual(resp.status_code, 302)  # redirected to the admin login, not served

    def test_school_add_and_delete_are_superuser_only_and_code_is_locked(self):
        """REQ: P2-REQ-05"""
        staff = make_user("staff_perm", is_staff=True)
        staff.user_permissions.add(*Permission.objects.filter(content_type__app_label="schools",
                                                              content_type__model="school"))
        staff = User.objects.get(pk=staff.pk)  # drop the permission cache
        model_admin = SchoolAdmin(School, admin.site)
        request = self.request_for(staff)
        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_delete_permission(request, self.school))
        self.assertTrue(model_admin.has_change_permission(request, self.school))
        self.assertIn("code", model_admin.get_readonly_fields(request, self.school))
        root_request = self.request_for(self.root)
        self.assertTrue(model_admin.has_add_permission(root_request))
        self.assertNotIn("code", model_admin.get_readonly_fields(root_request, self.school))

    def test_teacher_group_holds_no_model_permissions(self):
        """REQ: P2-REQ-17"""
        group, _ = Group.objects.get_or_create(name=TEACHER)
        self.assertEqual(group.permissions.count(), 0)
