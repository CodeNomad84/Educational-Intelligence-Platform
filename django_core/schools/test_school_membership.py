"""S1 tests: SchoolMembership, school_ids_for_admin, setup_platform_role (ADR-0012, proposal changes/0010).

Traceability: changes/0010 §4 (membership hygiene, query-time re-check, fail closed) and §9 stage S1
("no access change"). Nothing here switches a visibility rule: guard tests prove that creating memberships
or the PlatformAdmin group changes what no role can see.
"""
import inspect
from io import StringIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import RequestFactory, TestCase

from students import access
from students.access import (
    ADMIN, ALL_ROLES, GRADE_LEAD, PARENT, PLATFORM_ADMIN, TEACHER, roles_for, school_ids_for_admin,
    visible_attendances, visible_grades, visible_students,
)
from students.models import Attendance, Grade, Student

from .admin import SchoolMembershipAdmin
from .models import School, SchoolClass, SchoolMembership

User = get_user_model()


def make_user(username, group=None, **extra):
    user = User.objects.create_user(username=username, **extra)
    user.set_unusable_password()
    user.save()
    if group:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    return user


class MembershipHygieneTests(TestCase):
    def setUp(self):
        self.a = School.objects.create(name="A", code="a")
        self.b = School.objects.create(name="B", code="b")

    def membership(self, user, school=None):
        return SchoolMembership(user=user, school=school or self.a)

    def test_school_admin_can_be_a_member(self):
        self.membership(make_user("sa", ADMIN)).full_clean()

    def test_staff_school_admin_is_allowed_until_the_admin_is_restricted(self):
        self.membership(make_user("sa", ADMIN, is_staff=True)).full_clean()

    def test_superuser_cannot_be_a_member(self):
        user = make_user("root", ADMIN, is_superuser=True)
        with self.assertRaises(ValidationError) as ctx:
            self.membership(user).full_clean()
        self.assertIn("user", ctx.exception.message_dict)

    def test_superuser_without_the_group_cannot_be_a_member(self):
        with self.assertRaises(ValidationError):
            self.membership(make_user("root", is_superuser=True)).full_clean()

    def test_inactive_user_cannot_be_a_member(self):
        with self.assertRaises(ValidationError):
            self.membership(make_user("off", ADMIN, is_active=False)).full_clean()

    def test_user_outside_the_school_admin_group_cannot_be_a_member(self):
        for name, group in (("t", TEACHER), ("l", GRADE_LEAD), ("p", PARENT), ("n", None), ("pa", PLATFORM_ADMIN)):
            with self.subTest(group=group), self.assertRaises(ValidationError):
                self.membership(make_user(name, group)).full_clean()

    def test_user_holding_both_school_admin_and_platform_admin_cannot_be_a_member(self):
        """Review finding F1: separation of duties."""
        user = make_user("both", ADMIN)
        user.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        with self.assertRaises(ValidationError) as ctx:
            self.membership(user).full_clean()
        self.assertIn("user", ctx.exception.message_dict)

    def test_joining_platform_admin_later_does_not_make_clean_pass_again(self):
        user = make_user("later", ADMIN)
        membership = SchoolMembership.objects.create(user=user, school=self.a)
        user.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_user_and_school_pair_is_unique(self):
        user = make_user("sa", ADMIN)
        SchoolMembership.objects.create(user=user, school=self.a)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SchoolMembership.objects.create(user=user, school=self.a)

    def test_pair_uniqueness_is_also_a_validation_error_in_forms(self):
        user = make_user("sa", ADMIN)
        SchoolMembership.objects.create(user=user, school=self.a)
        with self.assertRaises(ValidationError):
            SchoolMembership(user=user, school=self.a).full_clean()  # constraints are validated by full_clean

    def test_many_to_many_one_user_several_schools_and_several_users_one_school(self):
        u1, u2 = make_user("u1", ADMIN), make_user("u2", ADMIN)
        for user, school in ((u1, self.a), (u1, self.b), (u2, self.a)):
            SchoolMembership.objects.create(user=user, school=school)
        self.assertEqual(self.a.memberships.count(), 2)
        self.assertEqual(u1.school_memberships.count(), 2)

    def test_a_school_with_memberships_cannot_be_deleted(self):
        SchoolMembership.objects.create(user=make_user("sa", ADMIN), school=self.a)
        with self.assertRaises(ProtectedError):
            self.a.delete()

    def test_deleting_the_user_removes_the_membership(self):
        user = make_user("sa", ADMIN)
        SchoolMembership.objects.create(user=user, school=self.a)
        user.delete()
        self.assertEqual(SchoolMembership.objects.count(), 0)


class SchoolIdsForAdminTests(TestCase):
    """The helper re-checks account state, group and membership at query time (fail closed)."""

    def setUp(self):
        self.a = School.objects.create(name="A", code="a")
        self.b = School.objects.create(name="B", code="b")
        self.user = make_user("sa", ADMIN)

    def join(self, school, user=None, **extra):
        return SchoolMembership.objects.create(user=user or self.user, school=school, **extra)

    def test_no_membership_means_no_school(self):
        self.assertEqual(school_ids_for_admin(self.user), set())

    def test_one_membership(self):
        self.join(self.a)
        self.assertEqual(school_ids_for_admin(self.user), {self.a.pk})

    def test_several_memberships_are_the_union_and_nothing_else(self):
        school_c = School.objects.create(name="C", code="c")
        self.join(self.a)
        self.join(self.b)
        self.assertEqual(school_ids_for_admin(self.user), {self.a.pk, self.b.pk})
        self.assertNotIn(school_c.pk, school_ids_for_admin(self.user))

    def test_inactive_membership_grants_nothing(self):
        self.join(self.a, is_active=False)
        self.join(self.b)
        self.assertEqual(school_ids_for_admin(self.user), {self.b.pk})

    def test_only_inactive_memberships_grant_nothing(self):
        self.join(self.a, is_active=False)
        self.assertEqual(school_ids_for_admin(self.user), set())

    def test_deactivated_account_grants_nothing(self):
        self.join(self.a)
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.assertEqual(school_ids_for_admin(User.objects.get(pk=self.user.pk)), set())

    def test_user_who_left_the_group_grants_nothing(self):
        self.join(self.a)
        self.user.groups.clear()
        self.assertEqual(school_ids_for_admin(self.user), set())

    def test_user_who_became_superuser_grants_nothing(self):
        self.join(self.a)
        User.objects.filter(pk=self.user.pk).update(is_superuser=True)
        self.assertEqual(school_ids_for_admin(User.objects.get(pk=self.user.pk)), set())

    def test_superuser_row_created_around_clean_still_grants_nothing(self):
        root = make_user("root", ADMIN, is_superuser=True)
        self.join(self.a, user=root)  # bypasses clean(): the query-time check is what protects
        self.assertEqual(school_ids_for_admin(root), set())

    def test_membership_of_a_user_outside_the_group_grants_nothing(self):
        for name, group in (("t", TEACHER), ("l", GRADE_LEAD), ("p", PARENT), ("n", None), ("pa", PLATFORM_ADMIN)):
            user = make_user(name, group)
            self.join(self.a, user=user)  # bypasses clean()
            with self.subTest(group=group):
                self.assertEqual(school_ids_for_admin(user), set())

    def test_user_added_to_platform_admin_after_the_membership_exists_gets_the_empty_set(self):
        """Review finding G1: the model check is creation-time, so the helper re-checks the group."""
        self.join(self.a)
        self.join(self.b)
        self.assertEqual(school_ids_for_admin(self.user), {self.a.pk, self.b.pk})
        self.user.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        self.assertEqual(school_ids_for_admin(User.objects.get(pk=self.user.pk)), set())

    def test_leaving_platform_admin_again_restores_the_scope(self):
        """Documents the behaviour: the rows are untouched, only the dual-role state neutralises them."""
        self.join(self.a)
        group = Group.objects.get_or_create(name=PLATFORM_ADMIN)[0]
        self.user.groups.add(group)
        self.assertEqual(school_ids_for_admin(self.user), set())
        self.user.groups.remove(group)
        self.assertEqual(school_ids_for_admin(User.objects.get(pk=self.user.pk)), {self.a.pk})

    def test_bulk_created_row_for_a_dual_role_user_grants_nothing(self):
        """Review finding G2: bulk_create/ORM writes bypass clean(); the query-time check is the control."""
        dual = make_user("dual", ADMIN)
        dual.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        SchoolMembership.objects.bulk_create([
            SchoolMembership(user=dual, school=self.a), SchoolMembership(user=dual, school=self.b)])
        self.assertEqual(SchoolMembership.objects.filter(user=dual).count(), 2)
        self.assertEqual(school_ids_for_admin(dual), set())

    def test_orm_created_row_for_a_dual_role_user_grants_nothing(self):
        dual = make_user("dual", ADMIN)
        dual.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        self.join(self.a, user=dual)  # bypasses clean()
        self.assertEqual(school_ids_for_admin(dual), set())

    def test_other_users_scope_is_unaffected_by_a_dual_role_user(self):
        dual = make_user("dual", ADMIN)
        dual.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        self.join(self.a, user=dual)
        self.join(self.b)
        self.assertEqual(school_ids_for_admin(self.user), {self.b.pk})

    def test_anonymous_and_none_grant_nothing(self):
        self.join(self.a)
        self.assertEqual(school_ids_for_admin(AnonymousUser()), set())
        self.assertEqual(school_ids_for_admin(None), set())

    def test_staff_school_admin_keeps_the_membership_until_s9(self):
        self.join(self.a)
        User.objects.filter(pk=self.user.pk).update(is_staff=True)
        self.assertEqual(school_ids_for_admin(User.objects.get(pk=self.user.pk)), {self.a.pk})

    def test_other_users_memberships_do_not_leak(self):
        other = make_user("other", ADMIN)
        self.join(self.b, user=other)
        self.assertEqual(school_ids_for_admin(self.user), set())


class StageS1ChangesNoAccessTests(TestCase):
    """S1 stores the entity and the helper only: no visibility rule, role or token reads them."""

    def setUp(self):
        self.a = School.objects.create(name="A", code="a")
        self.b = School.objects.create(name="B", code="b")
        class_a = SchoolClass.objects.create(school=self.a, title="7-A", academic_year="1404-1405", grade=7)
        class_b = SchoolClass.objects.create(school=self.b, title="7-B", academic_year="1404-1405", grade=7)
        self.sa_a = Student.objects.create(
            first_name="Ali", last_name="A", national_id="1000000001", grade=7, phone_number="1", school_class=class_a)
        self.sa_b = Student.objects.create(
            first_name="Bita", last_name="B", national_id="1000000002", grade=7, phone_number="2", school_class=class_b)
        self.loose = Student.objects.create(
            first_name="Cyrus", last_name="C", national_id="1000000003", grade=8, phone_number="3")
        for student in (self.sa_a, self.sa_b, self.loose):
            Grade.objects.create(student=student, subject="math", exam_type="quiz", score=15, date="2026-01-01")
            Attendance.objects.create(student=student, date="2026-01-02", status="present")
        self.admin_user = make_user("sa", ADMIN)
        self.parent = make_user("parent", PARENT)
        Student.objects.filter(pk=self.sa_a.pk).update(parent_user=self.parent)

    def snapshot(self):
        users = {name: User.objects.get(username=name) for name in ("sa", "parent")}
        return {
            name: (
                sorted(visible_students(user).values_list("pk", flat=True)),
                sorted(visible_grades(user).values_list("pk", flat=True)),
                sorted(visible_attendances(user).values_list("pk", flat=True)),
                sorted(roles_for(user)),
            )
            for name, user in users.items()
        }

    def test_creating_memberships_changes_nothing_anyone_sees(self):
        before = self.snapshot()
        SchoolMembership.objects.create(user=self.admin_user, school=self.a)
        SchoolMembership.objects.create(user=self.parent, school=self.b)  # bypasses clean(): still no effect
        self.assertEqual(self.snapshot(), before)

    def test_school_admin_without_membership_still_sees_everything(self):
        self.assertEqual(visible_students(self.admin_user).count(), 3)
        self.assertEqual(visible_grades(self.admin_user).count(), 3)
        self.assertEqual(visible_attendances(self.admin_user).count(), 3)

    def test_school_admin_with_a_membership_still_sees_every_school(self):
        SchoolMembership.objects.create(user=self.admin_user, school=self.a)
        self.assertEqual(visible_students(self.admin_user).count(), 3)

    def test_a_platform_admin_group_member_has_no_role_and_sees_nothing(self):
        platform = make_user("platform", PLATFORM_ADMIN)
        self.assertEqual(roles_for(platform), set())
        self.assertEqual(visible_students(platform).count(), 0)
        self.assertEqual(visible_grades(platform).count(), 0)
        self.assertEqual(visible_attendances(platform).count(), 0)

    def test_platform_admin_is_not_a_recognised_role(self):
        self.assertNotIn(PLATFORM_ADMIN, ALL_ROLES)

    def test_no_visibility_rule_reads_the_new_entity(self):
        for func in (visible_students, visible_grades, visible_attendances, roles_for):
            source = inspect.getsource(func)
            self.assertNotIn("school_ids_for_admin", source, func.__name__)
            self.assertNotIn("SchoolMembership", source, func.__name__)

    def test_no_view_serializer_permission_or_token_code_reads_the_new_entity(self):
        import config.service_auth as service_auth
        import dashboard.views as dashboard_views
        import students.permissions as permissions
        import students.serializers as serializers
        import students.views as student_views

        for module in (dashboard_views, student_views, serializers, permissions, service_auth):
            source = inspect.getsource(module)
            self.assertNotIn("school_ids_for_admin", source, module.__name__)
            self.assertNotIn("SchoolMembership", source, module.__name__)

    def test_helper_lives_in_the_access_module(self):
        self.assertIs(access.school_ids_for_admin, school_ids_for_admin)


class SetupPlatformRoleTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("setup_platform_role", *args, stdout=out)
        return out.getvalue()

    def test_creates_an_empty_group(self):
        output = self.run_command()
        group = Group.objects.get(name=PLATFORM_ADMIN)
        self.assertEqual(group.permissions.count(), 0)
        self.assertEqual(group.user_set.count(), 0)
        self.assertIn("created", output)

    def test_is_idempotent(self):
        self.run_command()
        output = self.run_command()
        self.assertEqual(Group.objects.filter(name=PLATFORM_ADMIN).count(), 1)
        self.assertIn("exists", output)

    def test_creates_no_user_and_sets_no_staff_flag(self):
        make_user("sa", ADMIN)
        before = list(User.objects.order_by("pk").values_list("pk", "is_staff", "is_superuser"))
        self.run_command()
        self.assertEqual(list(User.objects.order_by("pk").values_list("pk", "is_staff", "is_superuser")), before)

    def test_does_not_touch_other_groups(self):
        admin_group = Group.objects.create(name=ADMIN)
        admin_group.permissions.add(Permission.objects.first())
        self.run_command()
        self.assertEqual(admin_group.permissions.count(), 1)

    def test_reports_and_fails_on_a_permission_unless_fixed(self):
        group = Group.objects.create(name=PLATFORM_ADMIN)
        group.permissions.add(Permission.objects.get(codename="view_school"))
        with self.assertRaises(CommandError):
            self.run_command()
        self.assertEqual(group.permissions.count(), 1)  # nothing removed without --fix
        self.run_command("--fix")
        self.assertEqual(group.permissions.count(), 0)

    def test_the_new_group_changes_nobodys_role(self):
        user = make_user("platform")
        before = roles_for(user)
        self.run_command()
        user.groups.add(Group.objects.get(name=PLATFORM_ADMIN))
        self.assertEqual(roles_for(user), before)


class SchoolMembershipAdminTests(TestCase):
    def setUp(self):
        self.site = admin.site
        self.model_admin = SchoolMembershipAdmin(SchoolMembership, self.site)
        self.school = School.objects.create(name="A", code="a")
        self.factory = RequestFactory()

    def request(self, user):
        request = self.factory.get("/")
        request.user = user
        return request

    def grant(self, user, *actions):
        for action in actions:
            user.user_permissions.add(Permission.objects.get(codename=f"{action}_schoolmembership"))
        return User.objects.get(pk=user.pk)

    def permissions(self, user):
        request = self.request(user)
        return (
            self.model_admin.has_module_permission(request),
            self.model_admin.has_view_permission(request),
            self.model_admin.has_add_permission(request),
            self.model_admin.has_change_permission(request),
            self.model_admin.has_delete_permission(request),
        )

    def test_superuser_has_every_permission(self):
        root = User.objects.create_superuser("root", password="x")
        self.assertEqual(self.permissions(root), (True,) * 5)

    def test_school_admin_with_the_model_permissions_is_still_refused(self):
        user = make_user("sa", ADMIN, is_staff=True)
        user = self.grant(user, "view", "add", "change", "delete")
        self.assertEqual(self.permissions(user), (False,) * 5)

    def test_platform_admin_without_permissions_gets_nothing(self):
        user = make_user("pa", PLATFORM_ADMIN, is_staff=True)
        self.assertEqual(self.permissions(user), (False,) * 5)

    def test_platform_admin_needs_the_model_permission_too(self):
        user = make_user("pa", PLATFORM_ADMIN, is_staff=True)
        user = self.grant(user, "view", "change")
        self.assertEqual(self.permissions(user), (True, True, False, True, False))

    def test_inactive_platform_admin_gets_nothing(self):
        user = make_user("pa", PLATFORM_ADMIN, is_staff=True, is_active=False)
        user = self.grant(user, "view", "add", "change", "delete")
        self.assertEqual(self.permissions(user), (False,) * 5)

    def test_user_choices_are_active_non_superuser_school_admins(self):
        eligible = make_user("sa", ADMIN)
        make_user("teacher", TEACHER)
        make_user("off", ADMIN, is_active=False)
        make_user("root", ADMIN, is_superuser=True)
        field = self.model_admin.formfield_for_foreignkey(
            SchoolMembership._meta.get_field("user"), self.request(User.objects.create_superuser("r2", password="x")))
        self.assertEqual(list(field.queryset), [eligible])

    def test_user_choices_exclude_a_user_who_also_holds_platform_admin(self):
        """Review finding F1: the picker never offers a dual-role account."""
        eligible = make_user("sa", ADMIN)
        both = make_user("both", ADMIN)
        both.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        field = self.model_admin.formfield_for_foreignkey(
            SchoolMembership._meta.get_field("user"), self.request(User.objects.create_superuser("r3", password="x")))
        self.assertEqual(list(field.queryset), [eligible])

    def test_created_by_is_set_on_creation(self):
        root = User.objects.create_superuser("root", password="x")
        member = make_user("sa", ADMIN)
        obj = SchoolMembership(user=member, school=self.school)
        self.model_admin.save_model(self.request(root), obj, form=None, change=False)
        obj.refresh_from_db()
        self.assertEqual(obj.created_by_id, root.pk)

    def test_changelist_opens_for_a_superuser_and_is_denied_to_a_school_admin(self):
        root = User.objects.create_superuser("root", password="x")
        self.client.force_login(root)
        self.assertEqual(self.client.get("/admin/schools/schoolmembership/").status_code, 200)
        sa = make_user("sa", ADMIN, is_staff=True)
        sa = self.grant(sa, "view")
        self.client.force_login(sa)
        self.assertEqual(self.client.get("/admin/schools/schoolmembership/").status_code, 403)


class OrphanRowLifecycleTests(TestCase):
    """S2 / review finding G3: an orphan or dual-role row must be deactivatable and is not re-validated once inactive."""

    def setUp(self):
        self.school = School.objects.create(name="A", code="a")
        self.root = User.objects.create_superuser("root", password="x")
        self.client.force_login(self.root)

    def orphan(self, kind):
        user = make_user(f"o_{kind}", ADMIN)
        membership = SchoolMembership.objects.create(user=user, school=self.school)
        if kind == "dual":
            user.groups.add(Group.objects.get_or_create(name=PLATFORM_ADMIN)[0])
        elif kind == "left_group":
            user.groups.clear()
        elif kind == "inactive_user":
            User.objects.filter(pk=user.pk).update(is_active=False)
        elif kind == "superuser":
            User.objects.filter(pk=user.pk).update(is_superuser=True)
        return SchoolMembership.objects.get(pk=membership.pk)

    def test_active_orphan_fails_full_clean_with_a_non_field_error(self):
        for kind in ("dual", "left_group", "inactive_user", "superuser"):
            with self.subTest(kind=kind), self.assertRaises(ValidationError) as ctx:
                self.orphan(kind).full_clean()
            self.assertNotIn("user", ctx.exception.message_dict)

    def test_inactive_orphan_is_not_revalidated(self):
        for kind in ("dual", "left_group", "inactive_user", "superuser"):
            membership = self.orphan(kind)
            membership.is_active = False
            with self.subTest(kind=kind):
                membership.full_clean()  # does not raise

    def test_creation_still_reports_a_field_error(self):
        user = make_user("new", ADMIN, is_superuser=True)
        with self.assertRaises(ValidationError) as ctx:
            SchoolMembership(user=user, school=self.school).full_clean()
        self.assertIn("user", ctx.exception.message_dict)

    def test_admin_change_form_deactivates_an_orphan_row(self):
        for kind in ("dual", "left_group", "inactive_user", "superuser"):
            membership = self.orphan(kind)
            response = self.client.post(
                f"/admin/schools/schoolmembership/{membership.pk}/change/", {"school": self.school.pk})
            with self.subTest(kind=kind):
                self.assertEqual(response.status_code, 302)
                membership.refresh_from_db()
                self.assertFalse(membership.is_active)

    def test_admin_change_form_refuses_to_keep_an_orphan_active_without_a_server_error(self):
        membership = self.orphan("dual")
        response = self.client.post(
            f"/admin/schools/schoolmembership/{membership.pk}/change/", {"school": self.school.pk, "is_active": "on"})
        self.assertEqual(response.status_code, 200)
        membership.refresh_from_db()
        self.assertTrue(membership.is_active)  # unchanged, form error shown

    def test_user_is_read_only_on_an_existing_row_and_editable_on_add(self):
        model_admin = SchoolMembershipAdmin(SchoolMembership, admin.site)
        request = RequestFactory().get("/")
        request.user = self.root
        membership = self.orphan("dual")
        self.assertIn("user", model_admin.get_readonly_fields(request, membership))
        self.assertNotIn("user", model_admin.get_readonly_fields(request, None))

    def test_the_user_of_an_existing_row_cannot_be_changed_through_the_form(self):
        membership = self.orphan("dual")
        other = make_user("other", ADMIN)
        self.client.post(
            f"/admin/schools/schoolmembership/{membership.pk}/change/",
            {"school": self.school.pk, "user": other.pk})
        membership.refresh_from_db()
        self.assertNotEqual(membership.user_id, other.pk)
