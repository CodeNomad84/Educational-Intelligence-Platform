"""S2 tests: backfill_student_school (changes/0010 S2). Synthetic data only.

Since S6-2 only the pure planning rule is tested here; the command itself needs school-less rows, which exist only
at students.0014, so its behaviour is tested in ``test_migration_0015`` (migration-state tests).

Rules: a student that already has a school is never changed; a class gives its school; no class and exactly one
School gives that School; several Schools: nothing is guessed. Dry-run default, batch-logged, revertible.
"""

from django.test import SimpleTestCase

from students.management.commands.backfill_student_school import plan_assignments

class PlanTests(SimpleTestCase):
    def test_rules_in_order(self):
        rows = [(1, 7), (2, None), (3, 8)]
        self.assertEqual(plan_assignments(rows, [5]), ({1: 7, 2: 5, 3: 8}, 0))

    def test_several_schools_guess_nothing_for_classless_students(self):
        rows = [(1, 7), (2, None)]
        self.assertEqual(plan_assignments(rows, [5, 6]), ({1: 7}, 1))

    def test_no_school_guess_nothing(self):
        self.assertEqual(plan_assignments([(1, None)], []), ({}, 1))

    def test_a_class_school_wins_over_the_only_school(self):
        self.assertEqual(plan_assignments([(1, 9)], [5]), ({1: 9}, 0))
