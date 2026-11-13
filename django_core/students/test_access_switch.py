"""Stage 2.2a-4c tests: explicit NEGATIVE tests of the enrollment-based access rule (ADR-0011). Synthetic data only.

They complement ``test_access_c5a`` (positive scope, field policy, union) and ``test_access_parity`` (legacy vs new).
The fixture is the C5a one: both schools have 1404-1405 as the current year, students with a current-year class
are enrolled through the sync service.
"""
from datetime import date

from django.contrib.auth.models import AnonymousUser
from django.db.models import F
from django.test import TestCase

from schools.models import AcademicYear, SchoolClass
from students import test_access_c5a as c5a
from students.access import visible_attendances, visible_grades, visible_students
from students.models import Enrollment, Grade


class OutsideEnrollmentTests(c5a.Base):
    def test_mirror_alone_grants_nothing_to_a_grade_lead(self):
        """Mirror says grade 10 / active 1404 class, but the enrollment is closed or in another grade."""
        lead = self.lead()
        self.assertIn(self.s10a.pk, self.ids(lead))
        Enrollment.objects.filter(student=self.s10a).update(ended_on=F("started_on"))
        Enrollment.objects.filter(student=self.s10b).update(grade=11)
        self.assertEqual(self.ids(lead), set())

    def test_mirror_alone_grants_nothing_to_a_subject_teacher(self):
        teacher = self.teacher(klass=self.c10a)
        self.assertEqual(self.ids(teacher), {self.s10a.pk})
        Enrollment.objects.filter(student=self.s10a).update(school_class=self.c10b)  # mirror still says 10-A
        self.assertEqual(self.ids(teacher), set())
        self.assertEqual(visible_grades(teacher).count(), 0)
        self.assertEqual(visible_attendances(teacher).count(), 0)

    def test_non_current_statuses_grant_nothing(self):
        lead, teacher = self.lead(), self.teacher(klass=self.c10a)
        for status in ("withdrawn", "transferred_out", "graduated", "promoted", "retained"):
            Enrollment.objects.filter(student=self.s10a).update(status=status)
            self.assertNotIn(self.s10a.pk, self.ids(lead), status)
            self.assertNotIn(self.s10a.pk, self.ids(teacher), status)

    def test_enrollment_of_a_past_year_grants_nothing(self):
        lead, teacher = self.lead(), self.teacher(klass=self.c10a)
        old = AcademicYear.objects.create(school=self.school, code="1403-1404", start_date=date(2024, 9, 23),
                                          end_date=date(2025, 6, 21))
        Enrollment.objects.filter(student=self.s10a).update(academic_year=old)
        self.assertNotIn(self.s10a.pk, self.ids(lead))
        self.assertNotIn(self.s10a.pk, self.ids(teacher))

    def test_student_with_stale_mirror_class_and_no_current_enrollment_is_invisible(self):
        """The 'stale / unresolved class year' population: a mirror pointing at a past-year class, no enrollment."""
        lead = self.lead(year="1403")
        self.assertEqual(self.ids(lead), set())
        self.assertNotIn(self.s10old.pk, self.ids(self.lead("lead2")))
        self.assertFalse(Enrollment.objects.filter(student=self.s10old).exists())

    def test_current_enrollment_wins_over_an_unresolved_class_year_text(self):
        """Enrolled in the current year, but the class carries free text the normaliser cannot resolve: the
        Grade Lead (assignment year resolves) sees the student; the legacy rule could not."""
        self.c10a.academic_year = "سال جاری"
        self.c10a.save()
        self.assertIn(self.s10a.pk, self.ids(self.lead()))

    def test_unresolved_assignment_year_grants_nothing(self):
        for year in ("", "سال جاری", "14"):
            self.assertEqual(self.ids(self.lead(f"l{len(year)}{year[:1]}", year=year)), set(), year)


class SchoolIsolationTests(c5a.Base):
    def test_other_school_staff_see_nothing_of_this_school(self):
        lead_b = self.lead("lead_b", school=self.other_school)
        teacher_b = self.teacher("teacher_b", klass=self.c10x)
        self.assertEqual(self.ids(lead_b), {self.s10x.pk})
        self.assertEqual(self.ids(teacher_b), {self.s10x.pk})
        for st in (self.s10a, self.s10b, self.s11a):
            self.assertNotIn(st.pk, self.ids(lead_b))
            self.assertNotIn(st.pk, self.ids(teacher_b))

    def test_enrollment_in_another_schools_year_does_not_cross_the_boundary(self):
        """A student of school A whose enrollment points at school B's current year is visible to nobody of B
        and to nobody of A through that enrollment."""
        year_b = AcademicYear.objects.get(school=self.other_school, is_current=True)
        Enrollment.objects.filter(student=self.s10a).update(academic_year=year_b, school_class=self.c10x)
        lead_a, lead_b = self.lead("la"), self.lead("lb", school=self.other_school)
        teacher_b = self.teacher("tb", klass=self.c10x)
        self.assertNotIn(self.s10a.pk, self.ids(lead_a))
        self.assertNotIn(self.s10a.pk, self.ids(lead_b))   # the student's own school is A
        self.assertNotIn(self.s10a.pk, self.ids(teacher_b))
        self.assertNotIn(self.s10a.pk, set(visible_grades(teacher_b).values_list("student_id", flat=True)))

    def test_class_of_another_school_is_not_matched_by_class_id_alone(self):
        stray = SchoolClass.objects.create(school=self.other_school, title="X", academic_year="1404")
        Enrollment.objects.filter(student=self.s10a).update(school_class=stray)
        self.assertNotIn(self.s10a.pk, self.ids(self.teacher(klass=self.c10a)))


class FullTierTests(c5a.Base):
    def tiers(self, user):
        return dict(visible_students(user).values_list("pk", "full_tier"))

    def test_subject_teacher_rows_are_never_full_tier(self):
        self.assertEqual(self.tiers(self.teacher(klass=self.c10a)), {self.s10a.pk: False})

    def test_grade_lead_rows_are_full_tier(self):
        self.assertTrue(all(self.tiers(self.lead()).values()))

    def test_unauthorised_users_get_no_rows_and_no_full_tier(self):
        nobody = c5a.make_user("nobody")
        unknown_group = c5a.make_user("ug", "Counselor")
        inactive_lead = self.lead("il")
        inactive_lead.is_active = False
        staff_teacher = self.teacher("st", klass=self.c10a)
        staff_teacher.is_staff = True
        for user in (AnonymousUser(), None, nobody, unknown_group, inactive_lead, staff_teacher):
            rows = visible_students(user)
            self.assertEqual(list(rows), [], getattr(user, "username", user))
            self.assertFalse(any(r.full_tier for r in rows))
            self.assertEqual(visible_grades(user).count(), 0)
            self.assertEqual(visible_attendances(user).count(), 0)

    def test_teacher_tier_stays_false_when_the_student_is_also_enrolled_in_a_lead_grade(self):
        """Non-widening: a teacher without a Grade Lead grant never gets full detail on a grade-10 student."""
        self.assertFalse(self.tiers(self.teacher(klass=self.c10a))[self.s10a.pk])
        self.assertEqual(visible_attendances(self.teacher("t2", klass=self.c10a)).count(), 0)

    def test_grades_of_a_teacher_follow_the_enrollment_and_subject(self):
        teacher = self.teacher(klass=self.c10a, subject="math")
        self.assertEqual({(g.student_id, g.subject) for g in visible_grades(teacher)}, {(self.s10a.pk, "math")})
        Enrollment.objects.filter(student=self.s10a).update(ended_on=F("started_on"))
        self.assertEqual(visible_grades(teacher).count(), 0)
        self.assertTrue(Grade.objects.filter(student=self.s10a).exists())  # data untouched, only access changed
