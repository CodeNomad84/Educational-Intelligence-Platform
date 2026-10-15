"""C5a tests: Grade Lead and Subject Teacher visibility, field policy, search, writes, union (ADR-0005).

Traceability: REQ: P2-REQ-02 (class/grade scoped read), P2-REQ-16 (identity fields), TEACHER_ACCESS_REVIEW
R1-R7, owner decisions D-C5a-1 (linked class year, unlinked invisible) and D7 (no attendance for Subject Teacher).
All data is synthetic.
"""
import ast
import re
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from schools.models import GradeLeadAssignment, School, SchoolClass, TeacherAssignment
from students.access import (
    ADMIN, GRADE_LEAD, PARENT, TEACHER, visible_attendances, visible_grades, visible_students,
)
from students.models import Attendance, Grade, Student

User = get_user_model()
RESTRICTED = ('national_id', 'phone_number', 'father_job', 'mother_job', 'parent_user')


def make_user(username, *groups, **extra):
    user = User.objects.create_user(username=username, **extra)
    user.set_unusable_password()
    user.save()
    for name in groups:
        user.groups.add(Group.objects.get_or_create(name=name)[0])
    return user


class Base(TestCase):
    """School A: 10-A (1404, grade 10), 10-B (1404, grade 10), 11-A (1404, grade 11), 10-OLD (1403, grade 10).
    School B: 10-A (1404). One unlinked grade-10 student of school A."""

    def setUp(self):
        self.school = School.objects.create(name="A", code="a")
        self.other_school = School.objects.create(name="B", code="b")
        mk = lambda school, title, year, **kw: SchoolClass.objects.create(  # noqa: E731
            school=school, title=title, academic_year=year, **kw)
        self.c10a = mk(self.school, "10-A", "1404")
        self.c10b = mk(self.school, "10-B", "1404")
        self.c11a = mk(self.school, "11-A", "1404")
        self.c10old = mk(self.school, "10-OLD", "1403")
        self.c10x = mk(self.other_school, "10-A", "1404")
        self.n = 0
        self.s10a = self.student(10, self.c10a, "S10A")
        self.s10b = self.student(10, self.c10b, "S10B")
        self.s11a = self.student(11, self.c11a, "S11A")
        self.s10old = self.student(10, self.c10old, "S10OLD")
        self.s10x = self.student(10, self.c10x, "S10X")
        self.s10none = self.student(10, None, "S10NONE")
        for st in (self.s10a, self.s10b, self.s11a, self.s10x):
            for subject in ("math", "physics"):
                Grade.objects.create(student=st, subject=subject, exam_type="quiz", score=15, date=date(2026, 1, 1))
            Attendance.objects.create(student=st, date=date(2026, 1, 2), status="absent")
        self.admin = make_user("admin", ADMIN)

    def student(self, grade, klass, first, **kw):
        self.n += 1
        return Student.objects.create(
            first_name=first, last_name="Test", national_id=f"{self.n:010d}", grade=grade,
            phone_number=f"0912{self.n:07d}", father_job="job", school_class=klass, **kw)

    def lead(self, username="lead", grade=10, year="1404", school=None, **kw):
        user = make_user(username, GRADE_LEAD)
        GradeLeadAssignment.objects.create(
            user=user, school=school or self.school, grade=grade, academic_year=year, **kw)
        return user

    def teacher(self, username="teacher", klass=None, subject="math", **kw):
        user = make_user(username, TEACHER)
        if klass is not None:
            TeacherAssignment.objects.create(teacher=user, school_class=klass, subject=subject, **kw)
        return user

    def ids(self, user):
        return set(visible_students(user).values_list("pk", flat=True))


class GradeLeadScopeTests(Base):
    def test_sees_own_grade_only(self):
        self.assertEqual(self.ids(self.lead()), {self.s10a.pk, self.s10b.pk})

    def test_two_grades(self):
        user = self.lead()
        GradeLeadAssignment.objects.create(user=user, school=self.school, grade=11, academic_year="1404")
        self.assertEqual(self.ids(user), {self.s10a.pk, self.s10b.pk, self.s11a.pk})

    def test_other_school_not_visible(self):
        self.assertNotIn(self.s10x.pk, self.ids(self.lead()))
        self.assertEqual(self.ids(self.lead("lead_b", school=self.other_school)), {self.s10x.pk})

    def test_inactive_assignment_grants_nothing(self):
        self.assertEqual(self.ids(self.lead(is_active=False)), set())

    def test_other_academic_year_grants_nothing(self):
        self.assertEqual(self.ids(self.lead(year="1405")), set())
        self.assertNotIn(self.s10old.pk, self.ids(self.lead("lead2")))  # student of a 1403 class

    def test_unlinked_student_is_invisible(self):
        self.assertNotIn(self.s10none.pk, self.ids(self.lead()))

    def test_inactive_class_grants_nothing(self):
        self.c10b.is_active = False
        self.c10b.save()
        self.assertEqual(self.ids(self.lead()), {self.s10a.pk})

    def test_left_the_group_grants_nothing(self):
        user = self.lead()
        user.groups.clear()
        self.assertEqual(self.ids(user), set())


class SubjectTeacherScopeTests(Base):
    def test_assigned_class_only(self):
        self.assertEqual(self.ids(self.teacher(klass=self.c10a)), {self.s10a.pk})

    def test_inactive_class_and_unassigned_see_nothing(self):
        user = self.teacher(klass=self.c10a)
        self.c10a.is_active = False
        self.c10a.save()
        self.assertEqual(self.ids(user), set())
        self.assertEqual(self.ids(self.teacher("t2")), set())

    def test_blank_legacy_subject_grants_nothing(self):
        user = make_user("legacy", TEACHER)
        TeacherAssignment.objects.create(teacher=user, school_class=self.c10a, subject="")
        self.assertEqual(self.ids(user), set())
        self.assertEqual(list(visible_grades(user)), [])

    def test_teacher_without_group_grants_nothing(self):
        user = self.teacher(klass=self.c10a)
        user.groups.clear()
        self.assertEqual(self.ids(user), set())


class UnionTests(Base):
    def test_lead_plus_teacher_union_without_duplicates_and_tiers(self):
        user = self.lead()
        user.groups.add(Group.objects.get_or_create(name=TEACHER)[0])
        TeacherAssignment.objects.create(teacher=user, school_class=self.c11a, subject="physics")
        TeacherAssignment.objects.create(teacher=user, school_class=self.c10a, subject="math")  # overlaps grade 10
        rows = {s.pk: s.full_tier for s in visible_students(user)}
        self.assertEqual(set(rows), {self.s10a.pk, self.s10b.pk, self.s11a.pk})
        self.assertEqual(len(list(visible_students(user))), 3)
        self.assertTrue(rows[self.s10a.pk] and rows[self.s10b.pk])  # own grade: full
        self.assertFalse(rows[self.s11a.pk])  # only via teacher grant: limited

    def test_non_widening_grades_and_attendance(self):
        user = self.lead()
        user.groups.add(Group.objects.get_or_create(name=TEACHER)[0])
        TeacherAssignment.objects.create(teacher=user, school_class=self.c11a, subject="physics")
        grades = visible_grades(user)
        self.assertEqual({g.subject for g in grades.filter(student=self.s11a)}, {"physics"})
        self.assertEqual({g.subject for g in grades.filter(student=self.s10a)}, {"math", "physics"})
        att = set(visible_attendances(user).values_list("student_id", flat=True))
        self.assertEqual(att, {self.s10a.pk, self.s10b.pk})  # none for the teacher-only grade 11 student

    def test_parent_plus_lead(self):
        user = self.lead()
        user.groups.add(Group.objects.get_or_create(name=PARENT)[0])
        child = self.student(9, self.c10x, "KID", parent_user=user)
        rows = {s.pk: s.full_tier for s in visible_students(user)}
        self.assertEqual(set(rows), {self.s10a.pk, self.s10b.pk, child.pk})
        self.assertTrue(all(rows.values()))

    def test_admin_plus_any_sees_all_full(self):
        user = self.lead()
        user.groups.add(Group.objects.get_or_create(name=ADMIN)[0])
        rows = list(visible_students(user))
        self.assertEqual(len(rows), Student.objects.count())
        self.assertTrue(all(s.full_tier for s in rows))

    def test_no_role_sees_nothing(self):
        user = make_user("nobody")
        self.assertEqual(self.ids(user), set())
        self.assertEqual(list(visible_grades(user)), [])
        self.assertEqual(list(visible_attendances(user)), [])


class GradesAndAttendanceTests(Base):
    def test_teacher_only_own_subject_and_no_attendance(self):
        user = self.teacher(klass=self.c10a, subject="math")
        TeacherAssignment.objects.create(teacher=user, school_class=self.c10b, subject="physics")
        got = {(g.student_id, g.subject) for g in visible_grades(user)}
        self.assertEqual(got, {(self.s10a.pk, "math"), (self.s10b.pk, "physics")})
        self.assertEqual(list(visible_attendances(user)), [])

    def test_lead_all_subjects_and_attendance_of_own_grade(self):
        user = self.lead()
        self.assertEqual(
            {(g.student_id, g.subject) for g in visible_grades(user)},
            {(s.pk, sub) for s in (self.s10a, self.s10b) for sub in ("math", "physics")})
        self.assertEqual(
            set(visible_attendances(user).values_list("student_id", flat=True)), {self.s10a.pk, self.s10b.pk})


class ApiFieldPolicyTests(Base):
    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_teacher_payload_has_no_identity_fields(self):
        client = self.client_for(self.teacher(klass=self.c10a))
        listing = client.get("/api/students/")
        self.assertEqual(listing.status_code, 200)
        data = listing.json()
        rows = data["results"] if isinstance(data, dict) else data
        rows = rows + [client.get(f"/api/students/{self.s10a.pk}/").json()]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertIn("first_name", row)
            for name in RESTRICTED:
                self.assertNotIn(name, row)

    def test_lead_payload_full_in_own_grade_and_limited_elsewhere(self):
        user = self.lead()
        user.groups.add(Group.objects.get_or_create(name=TEACHER)[0])
        TeacherAssignment.objects.create(teacher=user, school_class=self.c11a, subject="math")
        client = self.client_for(user)
        own = client.get(f"/api/students/{self.s10a.pk}/").json()
        other = client.get(f"/api/students/{self.s11a.pk}/").json()
        for name in RESTRICTED:
            self.assertIn(name, own)
            self.assertNotIn(name, other)
        self.assertEqual(own["national_id"], self.s10a.national_id)

    def test_out_of_scope_is_404(self):
        client = self.client_for(self.lead())
        self.assertEqual(client.get(f"/api/students/{self.s11a.pk}/").status_code, 404)
        self.assertEqual(client.get(f"/api/students/{self.s10none.pk}/").status_code, 404)

    def test_search_by_national_id(self):
        teacher = self.client_for(self.teacher(klass=self.c10a))
        found = teacher.get("/api/students/", {"search": self.s10a.national_id}).json()
        self.assertEqual(len(found.get("results", found)), 0)  # limited row cannot be probed
        by_name = teacher.get("/api/students/", {"search": "S10A"}).json()
        self.assertEqual(len(by_name.get("results", by_name)), 1)

        lead = self.client_for(self.lead())
        inside = lead.get("/api/students/", {"search": self.s10a.national_id}).json()
        self.assertEqual(len(inside.get("results", inside)), 1)
        out_of_scope = lead.get("/api/students/", {"search": self.s11a.national_id}).json()
        missing = lead.get("/api/students/", {"search": "9999999999"}).json()
        self.assertEqual(out_of_scope, missing)

    def test_writes_and_actions_forbidden(self):
        for user in (self.lead("l"), self.teacher("t", klass=self.c10a)):
            client = self.client_for(user)
            pk = self.s10a.pk
            self.assertEqual(client.post("/api/students/", {}, format="json").status_code, 403)
            self.assertEqual(client.patch(f"/api/students/{pk}/", {"first_name": "X"}, format="json").status_code, 403)
            self.assertEqual(client.delete(f"/api/students/{pk}/").status_code, 403)
            self.assertEqual(client.post("/api/students/import/").status_code, 403)
            self.assertEqual(client.get(f"/api/students/{pk}/features/").status_code, 403)
            self.assertEqual(client.get(f"/api/students/{pk}/predict/").status_code, 403)
        self.s10a.refresh_from_db()
        self.assertEqual(self.s10a.first_name, "S10A")


class DashboardHtmlTests(Base):
    def test_teacher_list_and_detail_hide_identity_attendance_and_other_subjects(self):
        user = self.teacher(klass=self.c10a, subject="math")
        self.client.force_login(user)
        lst = self.client.get(reverse("dashboard:student_list"))
        self.assertEqual(lst.status_code, 200)
        html = lst.content.decode()
        self.assertNotIn(self.s10a.national_id, html)
        self.assertIn("S10A", html)
        self.assertNotIn("S10B", html)
        detail = self.client.get(reverse("dashboard:student_detail", args=[self.s10a.pk]))
        self.assertEqual(detail.status_code, 200)
        body = detail.content.decode()
        for secret in (self.s10a.national_id, "job"):
            self.assertNotIn(secret, body)
        self.assertEqual({g.subject for g in detail.context["grades"]}, {"math"})
        self.assertEqual(list(detail.context["attendances"]), [])
        self.assertNotIn("predict=true", body)
        self.assertEqual(
            self.client.get(reverse("dashboard:student_detail", args=[self.s10b.pk])).status_code, 404)

    def test_lead_detail_shows_identity_and_attendance_in_own_grade(self):
        self.client.force_login(self.lead())
        resp = self.client.get(reverse("dashboard:student_detail", args=[self.s10a.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.s10a.national_id, resp.content.decode())
        self.assertEqual(len(resp.context["attendances"]), 1)
        self.assertEqual({g.subject for g in resp.context["grades"]}, {"math", "physics"})
        self.assertEqual(self.client.get(reverse("dashboard:student_detail", args=[self.s11a.pk])).status_code, 404)

    def test_html_search_cannot_probe_identity(self):
        self.client.force_login(self.teacher(klass=self.c10a))
        resp = self.client.get(reverse("dashboard:student_list"), {"search": self.s10a.national_id})
        self.assertEqual(list(resp.context["students"]), [])

    def test_landing_and_gate_for_union_roles(self):
        combos = {
            "lead": (self.lead("c_lead"),),
            "teacher": (self.teacher("c_teacher", klass=self.c10a),),
        }
        pl = self.lead("c_pl")
        pl.groups.add(Group.objects.get_or_create(name=PARENT)[0])
        lt = self.lead("c_lt")
        lt.groups.add(Group.objects.get_or_create(name=TEACHER)[0])
        sa = self.lead("c_sa")
        sa.groups.add(Group.objects.get_or_create(name=ADMIN)[0])
        users = [combos["lead"][0], combos["teacher"][0], pl, lt, sa]
        for user in users:
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("dashboard:student_list")).status_code, 200, user.username)
            landing = self.client.get(reverse("dashboard:dashboard")).status_code
            self.assertEqual(landing, 200 if user is sa else 302, user.username)
        for user in users[:-1]:
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse("dashboard:student_add")).status_code, 403, user.username)
            self.assertEqual(self.client.get(reverse("dashboard:upload_students")).status_code, 403, user.username)
        # no role at all: the list is denied, not empty
        self.client.force_login(make_user("none"))
        self.assertEqual(self.client.get(reverse("dashboard:student_list")).status_code, 403)

    def test_menu_follows_all_roles_not_first_group(self):
        user = self.lead("menu")
        user.groups.add(Group.objects.get_or_create(name=ADMIN)[0])  # GradeLead is the first group
        self.client.force_login(user)
        html = self.client.get(reverse("dashboard:student_list")).content.decode()
        self.assertIn(reverse("dashboard:upload_students"), html)


class QuerysetChokePointTests(TestCase):
    """Grep-style guard: every Student/Grade/Attendance read in the student/dashboard views and the
    serializers goes through the access layer, except functions reviewed as SchoolAdmin-only."""

    ROOT = Path(__file__).resolve().parents[1]
    PATTERN = re.compile(r"\b(Student|Grade|Attendance)\.objects\b|\.grades\b|\.attendances\b")
    FILES = {
        "students/views.py": {
            # SchoolAdmin only (get_permissions -> IsAdminUser for import_students); no user-supplied scope
            "_linked_national_ids", "_plan_class_links", "_write_import_row", "import_students",
        },
        "students/serializers.py": set(),
        "dashboard/views.py": {"dashboard_view"},  # aggregates behind `ADMIN not in roles`
    }

    def functions(self, relpath):
        source = (self.ROOT / relpath).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield node.name, ast.get_source_segment(source, node)

    def test_no_unscoped_reads(self):
        offenders = []
        for relpath, allowed in self.FILES.items():
            source = (self.ROOT / relpath).read_text(encoding="utf-8")
            inside = set()
            for name, segment in self.functions(relpath):
                if self.PATTERN.search(segment):
                    inside.add(segment)
                    if name not in allowed:
                        offenders.append(f"{relpath}:{name}")
            # module-level usage (outside any function) is never allowed
            for segment in sorted(inside, key=len, reverse=True):
                source = source.replace(segment, "")
            if self.PATTERN.search(source):
                offenders.append(f"{relpath}:<module level>")
        self.assertEqual(offenders, [])

    def test_read_paths_use_the_access_layer(self):
        views = (self.ROOT / "students/views.py").read_text(encoding="utf-8")
        dash = (self.ROOT / "dashboard/views.py").read_text(encoding="utf-8")
        self.assertIn("return visible_students(self.request.user)", views)
        self.assertIn("get_object_or_404(visible_students(request.user), pk=pk)", dash)
        self.assertIn("visible_grades(request.user)", dash)
        self.assertIn("visible_attendances(request.user)", dash)

    def test_allowlist_is_exhaustive_for_admin_only_functions(self):
        """Allow-listed functions must still be SchoolAdmin only: import is IsAdminUser, aggregates gate on ADMIN."""
        views = (self.ROOT / "students/views.py").read_text(encoding="utf-8")
        self.assertRegex(views, r"if self\.action == 'import_students':\s+return \[IsAdminUser\(\)\]")
        dash = (self.ROOT / "dashboard/views.py").read_text(encoding="utf-8")
        self.assertIn("if ADMIN not in roles:", dash)
