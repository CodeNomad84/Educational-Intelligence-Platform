"""C4b tests: subject vocabulary, GradeLeadAssignment, SchoolClass.grade, check_assignment_subjects.

Traceability: ADR-0005 decisions 2 and 3, ADR-0004 amendments. No visibility change: ``visible_students`` is
untouched and a guard test proves a Grade Lead assignment grants no access.
"""
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from students.access import GRADE_LEAD, TEACHER, visible_students
from students.models import Grade, Student

from .admin import GradeLeadAssignmentForm
from .models import GradeLeadAssignment, School, SchoolClass, TeacherAssignment
from .vocabulary import SUBJECT_CHOICES, SUBJECT_KEYS, classify_subject

User = get_user_model()


def make_user(username, group=None, **extra):
    user = User.objects.create_user(username=username, **extra)
    user.set_unusable_password()
    user.save()
    if group:
        user.groups.add(Group.objects.get_or_create(name=group)[0])
    return user


class VocabularyTests(TestCase):
    def test_grade_subject_reexports_shared_vocabulary(self):
        self.assertEqual(Grade.SUBJECT_CHOICES, SUBJECT_CHOICES)
        self.assertEqual(len(SUBJECT_KEYS), 15)

    def test_classification_is_exact_match_only(self):
        self.assertEqual(classify_subject('math'), ('valid', 'math'))
        self.assertEqual(classify_subject('ریاضی'), ('exact_label', 'math'))
        self.assertEqual(classify_subject(''), ('blank', None))
        for value in (' math', 'Math', 'ریاضی ', 'ریاضیات', 'math/physics'):
            self.assertEqual(classify_subject(value), ('unmatched', None), value)


class AssignmentSubjectTests(TestCase):
    def setUp(self):
        school = School.objects.create(name="A", code="a")
        self.klass = SchoolClass.objects.create(school=school, title="10-A", academic_year="1404")
        self.teacher = make_user("t", TEACHER)

    def make(self, subject):
        return TeacherAssignment(teacher=self.teacher, school_class=self.klass, subject=subject)

    def test_blank_subject_rejected_for_new_rows(self):
        with self.assertRaises(ValidationError) as ctx:
            self.make("").full_clean()
        self.assertIn("subject", ctx.exception.message_dict)

    def test_value_outside_vocabulary_rejected(self):
        for value in ("ریاضی", "Math", "klingon"):
            with self.assertRaises(ValidationError) as ctx:
                self.make(value).full_clean()
            self.assertIn("subject", ctx.exception.message_dict, value)

    def test_every_vocabulary_key_is_accepted(self):
        for key in SUBJECT_KEYS:
            self.make(key).full_clean()

    def test_existing_legacy_blank_row_stays_valid(self):
        row = TeacherAssignment.objects.create(teacher=self.teacher, school_class=self.klass, subject="")
        row.full_clean()


class SchoolClassGradeTests(TestCase):
    def test_grade_is_nullable_and_validated(self):
        school = School.objects.create(name="A", code="a")
        klass = SchoolClass.objects.create(school=school, title="10-A")
        klass.full_clean()
        self.assertIsNone(klass.grade)
        klass.grade = 5
        with self.assertRaises(ValidationError):
            klass.full_clean()
        klass.grade = 10
        klass.full_clean()

    def test_linking_students_does_not_backfill_grade(self):
        school = School.objects.create(name="A", code="a")
        klass = SchoolClass.objects.create(school=school, title="10-A")
        Student.objects.create(
            first_name="S", last_name="T", national_id="0000000001", grade=10, phone_number="1",
            school_class=klass)
        klass.refresh_from_db()
        self.assertIsNone(klass.grade)


class GradeLeadAssignmentTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="A", code="a")
        SchoolClass.objects.create(school=self.school, title="10-A", academic_year="1404")
        self.lead = make_user("lead", GRADE_LEAD)

    def make(self, **kw):
        data = {"user": self.lead, "school": self.school, "grade": 10, "academic_year": "1404"}
        data.update(kw)
        return GradeLeadAssignment(**data)

    def test_valid_assignment_passes(self):
        self.make().full_clean()

    def test_only_active_non_staff_grade_lead_group_members(self):
        bad = (
            make_user("nogroup"), make_user("teacher", TEACHER), make_user("gone", GRADE_LEAD, is_active=False),
            make_user("staff", GRADE_LEAD, is_staff=True), make_user("root", GRADE_LEAD, is_superuser=True),
        )
        for user in bad:
            with self.assertRaises(ValidationError) as ctx:
                self.make(user=user).full_clean()
            self.assertIn("user", ctx.exception.message_dict, user.username)

    def test_grade_must_be_in_vocabulary_and_year_required(self):
        with self.assertRaises(ValidationError) as ctx:
            self.make(grade=3, academic_year="  ").full_clean()
        self.assertIn("grade", ctx.exception.message_dict)
        self.assertIn("academic_year", ctx.exception.message_dict)

    def test_duplicate_is_rejected_other_year_allowed(self):
        self.make().save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make().save()
        self.make(academic_year="1405").full_clean()

    def test_year_warning_is_non_blocking(self):
        self.assertIsNone(self.make().year_warning())
        row = self.make(academic_year="1999")
        row.full_clean()  # no error
        self.assertIn("1999", row.year_warning())

    def test_form_year_choices_come_from_existing_classes(self):
        SchoolClass.objects.create(school=self.school, title="11-A", academic_year="1405")
        SchoolClass.objects.create(school=self.school, title="blank-year")
        form = GradeLeadAssignmentForm()
        values = [v for v, _ in form.fields["academic_year"].choices if v]
        self.assertEqual(values, ["1404", "1405"])
        form = GradeLeadAssignmentForm(data={
            "user": self.lead.pk, "school": self.school.pk, "grade": 10, "academic_year": "9999"})
        self.assertFalse(form.is_valid())
        self.assertIn("academic_year", form.errors)

    def test_assignment_grants_no_student_access(self):
        """Guard: nothing reads GradeLeadAssignment before C5a."""
        Student.objects.create(first_name="S", last_name="T", national_id="0000000002", grade=10, phone_number="1",
                               school=School.objects.order_by('pk').first())
        self.make().save()
        self.assertEqual(visible_students(self.lead).count(), 0)


class CheckAssignmentSubjectsTests(TestCase):
    def run_cmd(self):
        out = StringIO()
        call_command('check_assignment_subjects', stdout=out)
        return out.getvalue()

    def test_reports_counts_and_writes_nothing(self):
        school = School.objects.create(name="A", code="a")
        klass = SchoolClass.objects.create(school=school, title="10-A", academic_year="1404")
        for i, subject in enumerate(["math", "فیزیک", "", "ریاضیات"]):
            TeacherAssignment.objects.create(
                teacher=make_user(f"t{i}", TEACHER), school_class=klass, subject=subject)
        before = list(TeacherAssignment.objects.order_by('pk').values_list('subject', flat=True))
        text = self.run_cmd()
        self.assertIn('assignments: 4', text)
        self.assertIn('valid_key: 1', text)
        self.assertIn('exact_label_convertible: 1', text)
        self.assertIn('blank: 1', text)
        self.assertIn('unmatched: 1', text)
        self.assertEqual(
            before, list(TeacherAssignment.objects.order_by('pk').values_list('subject', flat=True)))

    def test_empty_table(self):
        self.assertIn('assignments: 0', self.run_cmd())
