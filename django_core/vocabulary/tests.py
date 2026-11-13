from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from schools.models import AcademicYear, School
from vocabulary.defaults import DEFAULTS
from vocabulary.models import OBSERVATION_CATEGORY, RECOMMENDATION_TAG, VocabularyTerm
from vocabulary.terms import rename_term, terms_on

TODAY = timezone.localdate


class VocabularyBase(TestCase):
    def setUp(self):
        self.a = School.objects.create(name='A', code='a')
        self.b = School.objects.create(name='B', code='b')

    def term(self, school=None, code='emotional', domain=OBSERVATION_CATEGORY, start=date(2020, 1, 1), **kw):
        return VocabularyTerm.objects.create(school=school or self.a, domain=domain, code=code, label_fa='x',
                                             effective_from=start, **kw)


class ImmutabilityTests(VocabularyBase):
    def test_a_term_cannot_be_edited_or_deleted_in_place(self):
        t = self.term()
        t.label_fa = 'changed'
        with self.assertRaises(ValidationError):
            t.save()
        t.refresh_from_db()
        t.code = 'other'
        with self.assertRaises(ValidationError):
            t.save()
        with self.assertRaises(ValidationError):
            t.delete()
        self.assertEqual(VocabularyTerm.objects.get().label_fa, 'x')

    def test_only_the_closing_fields_may_change(self):
        t = self.term()
        t.effective_to = date(2021, 1, 1)
        t.active = False
        t.save()
        self.assertFalse(VocabularyTerm.objects.get().active)

    def test_constraints_and_validation(self):
        self.term()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.term()                                                      # same version twice
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.term(code='social', effective_to=date(2019, 1, 1))          # ends before it starts
        with self.assertRaises(ValidationError):
            VocabularyTerm.objects.create(school=self.a, domain='nope', code='c', label_fa='x', effective_from=TODAY())

    def test_a_replacement_must_stay_in_the_same_school_and_domain(self):
        t = self.term()
        with self.assertRaises(ValidationError):
            VocabularyTerm.objects.create(school=self.b, domain=OBSERVATION_CATEGORY, code='emotional', label_fa='y',
                                          effective_from=TODAY(), replaces=t)
        with self.assertRaises(ValidationError):
            VocabularyTerm.objects.create(school=self.a, domain=RECOMMENDATION_TAG, code='emotional', label_fa='y',
                                          effective_from=TODAY(), replaces=t)


class RenameTests(VocabularyBase):
    def test_a_rename_creates_a_new_term_and_closes_the_old_one(self):
        old = self.term(start=date(2020, 1, 1))
        new = rename_term(old, label_fa='جدید', on=date(2025, 9, 23))
        old.refresh_from_db()
        self.assertEqual((new.replaces_id, new.label_fa, new.effective_from, new.effective_to), (old.pk, 'جدید', date(2025, 9, 23), None))
        self.assertEqual((old.label_fa, old.active, old.effective_to), ('x', False, date(2025, 9, 22)))
        self.assertEqual([t.pk for t in terms_on(self.a, OBSERVATION_CATEGORY, on=date(2025, 9, 23))], [new.pk])
        self.assertEqual(VocabularyTerm.objects.count(), 2)                  # history kept

    def test_rename_refuses_a_closed_or_not_yet_started_term(self):
        old = self.term(start=date(2020, 1, 1))
        rename_term(old, label_fa='n', on=date(2025, 1, 1))
        old.refresh_from_db()
        with self.assertRaises(ValueError):
            rename_term(old, label_fa='again', on=date(2025, 6, 1))
        fresh = self.term(code='social', start=date(2026, 1, 1))
        with self.assertRaises(ValueError):
            rename_term(fresh, label_fa='n', on=date(2026, 1, 1))

    def test_terms_on_is_school_scoped_and_dated(self):
        self.term(start=date(2020, 1, 1), effective_to=date(2020, 12, 31))
        self.term(school=self.b, code='social')
        self.assertEqual(terms_on(self.a, OBSERVATION_CATEGORY, on=date(2020, 6, 1)).count(), 1)
        self.assertEqual(terms_on(self.a, OBSERVATION_CATEGORY, on=date(2021, 6, 1)).count(), 0)
        self.assertEqual(terms_on(self.a, OBSERVATION_CATEGORY, on=date(2019, 6, 1)).count(), 0)
        self.assertEqual(list(terms_on(self.b, OBSERVATION_CATEGORY).values_list('code', flat=True)), ['social'])

    def test_two_schools_can_hold_different_sets_for_the_same_domain(self):
        rename_term(self.term(), label_fa='A-label', on=date(2025, 1, 1))
        self.term(school=self.b, code='charter_principle')
        self.assertEqual(set(terms_on(self.a, OBSERVATION_CATEGORY).values_list('code', flat=True)), {'emotional'})
        self.assertEqual(set(terms_on(self.b, OBSERVATION_CATEGORY).values_list('code', flat=True)), {'charter_principle'})


class SeedTests(VocabularyBase):
    def test_seed_creates_defaults_for_every_domain_and_is_idempotent(self):
        call_command('seed_vocabulary', '--school', 'a', '--effective-from', '2020-01-01', verbosity=0)
        total = sum(len(rows) for rows in DEFAULTS.values())
        self.assertEqual(VocabularyTerm.objects.filter(school=self.a).count(), total)
        self.assertEqual(VocabularyTerm.objects.filter(school=self.b).count(), 0)
        call_command('seed_vocabulary', '--school', 'a', verbosity=0)
        self.assertEqual(VocabularyTerm.objects.filter(school=self.a).count(), total)
        self.assertEqual({t.domain for t in VocabularyTerm.objects.all()}, set(DEFAULTS))

    def test_seed_never_touches_a_school_s_own_change(self):
        call_command('seed_vocabulary', '--school', 'a', '--effective-from', '2020-01-01', verbosity=0)
        term = VocabularyTerm.objects.get(school=self.a, domain=OBSERVATION_CATEGORY, code='emotional')
        rename_term(term, label_fa='own', on=date(2025, 1, 1))
        call_command('seed_vocabulary', '--all-schools', verbosity=0)
        self.assertEqual(VocabularyTerm.objects.filter(school=self.a, code='emotional', domain=OBSERVATION_CATEGORY).count(), 2)
        self.assertEqual(VocabularyTerm.objects.filter(school=self.b).count(), sum(len(r) for r in DEFAULTS.values()))

    def test_seed_starts_at_the_earliest_academic_year_else_today(self):
        AcademicYear.objects.create(school=self.a, code='1404-1405', start_date=date(2025, 9, 23), end_date=date(2026, 6, 21),
                                    is_current=True)
        call_command('seed_vocabulary', '--all-schools', verbosity=0)
        self.assertEqual({t.effective_from for t in VocabularyTerm.objects.filter(school=self.a)}, {date(2025, 9, 23)})
        self.assertEqual({t.effective_from for t in VocabularyTerm.objects.filter(school=self.b)}, {TODAY()})

    def test_unknown_school_is_an_error(self):
        with self.assertRaises(Exception):
            call_command('seed_vocabulary', '--school', 'nope')


class NothingElseChangedTests(TestCase):
    def test_the_unbuilt_shell_apps_are_still_not_installed(self):
        from django.apps import apps
        for name in ('behavior', 'academics', 'governance'):   # risk and interventions are installed since change 0022
            self.assertFalse(apps.is_installed(name), name)
