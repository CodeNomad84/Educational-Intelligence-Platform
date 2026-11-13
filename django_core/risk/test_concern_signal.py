"""P6 (decision 50): the ``concern_count`` metric reads staff 'concern' behavior entries through ONE system read path. Counts only:
the note text is never read or stored in evidence, messages or alerts; positive entries, other schools and students outside the
current enrollment are never counted. Mutation checks: each assertion below fails if the matching filter in
``students.access.system_scope_concern_notes`` / ``risk.rules.load_concerns`` is removed."""
from datetime import timedelta

from risk import rules
from risk.models import Alert, RuleHit
from risk.rules_testing import TODAY, RulesBase
from students import access
from students.models import BehaviorNote

SECRET = 'SECRET-NOTE-TEXT-9f3'


class ConcernSignalTests(RulesBase):
    def note(self, student, kind='concern', days=3, text=SECRET):
        return BehaviorNote.objects.create(school_id=student.school_id, student=student, kind=kind, category='conduct', note=text,
                                           occurred_on=TODAY - timedelta(days=days), recorded_by=self.lead)

    def test_the_system_read_path_returns_concern_entries_of_one_school_only(self):
        mine, other = self.note(self.s7), self.note(self.sb)
        self.note(self.s7, kind='positive', text='praise')
        rows = list(access.system_scope_concern_notes(self.a.pk))
        self.assertEqual([r.pk for r in rows], [mine.pk])                 # no positive entry, no other school
        self.assertNotIn(other.pk, [r.pk for r in rows])
        with self.assertRaises(ValueError):
            access.system_scope_concern_notes(True)

    def test_loader_selects_dates_only_and_windows_by_date(self):
        for d in (2, 5, 9):
            self.note(self.s7, days=d)
        self.note(self.s7, days=2000)
        loaded = rules.load_concerns(self.a.pk, TODAY, TODAY)
        self.assertEqual(sorted(c.date for c in loaded[self.s7.pk]), [TODAY - timedelta(days=d) for d in (9, 5, 2)])
        self.assertFalse(hasattr(loaded[self.s7.pk][0], 'note'))          # a plain date tuple: no text, no category

    def test_rule_fires_on_three_concerns_not_on_positive_or_foreign_entries_and_leaks_no_text(self):
        rule = self.live('repeated_concerns')
        for d in (2, 6, 12):
            self.note(self.s7, days=d)
        for d in (1, 2, 3, 4):
            self.note(self.s8, kind='positive', days=d)                    # positives never count
        for d in (1, 2, 3, 4):
            self.note(self.sb, days=d)                                     # another school never counts
        (run,) = rules.run_school(self.a.pk, as_of=TODAY)
        self.assertEqual((run.hits, run.alerts_raised), (1, 1))
        alert = Alert.objects.get(student=self.s7)
        hit = RuleHit.objects.get(student=self.s7)
        self.assertEqual(alert.risk_event.risk_type, 'behavioral')
        for text in (alert.message, alert.risk_event.explanation, str(hit.evidence)):
            self.assertNotIn(SECRET, text)
        self.assertFalse(Alert.objects.filter(student__in=[self.s8, self.sb]).exists())

    def test_below_threshold_and_inactive_students_do_not_fire(self):
        self.live('repeated_concerns')
        self.note(self.s7, days=2)
        self.note(self.s7, days=4)
        self.assertEqual(rules.run_school(self.a.pk, as_of=TODAY)[0].hits, 0)
        for d in (1, 2, 3):
            self.note(self.s8, days=d)
        from students.models import Enrollment
        Enrollment.objects.filter(student=self.s8).update(status='withdrawn')   # not a current enrollment: outside the system scope
        self.assertEqual(rules.run_school(self.a.pk, as_of=TODAY)[0].hits, 0)

    def test_simulation_withholds_small_groups_and_starts_as_a_draft(self):
        rule = self.starter(code='repeated_concerns')
        self.assertEqual(rule.status, 'draft')
        for d in (2, 6, 12):
            self.note(self.s7, days=d)
        weeks = rules.simulate(rule, as_of=TODAY)
        self.assertTrue(all(w['fired'] is None for w in weeks))            # one student: under MIN_GROUP, withheld
