"""Mission module, Slice 2: the rule engine and the evaluation hook. Pure arithmetic checks against the guide's own worked
example, then the data rules (not observed, duplicates, minimums, differences, periods, scope). Synthetic data only."""
from decimal import Decimal

from django.utils import timezone

from .engine import NEEDS_DIFF, NEEDS_MORE, USABLE, period_profiles, student_profile
from .evaluation import anonymised_rows, top_k_agreement
from .models import Activity, Observation, ObservationSession, Period, WeightSet
from .tests import MissionBase

D = Decimal
KP = 'knowledge_production'     # weights: 1=25 2=25 3=10 5=5 6=5 9=5 10=5 11=10 12=10, zero for 4, 7, 8


class EngineBase(MissionBase):
    def setUp(self):
        super().setUp()
        self.by_code = {i.code: i for i in self.ind}
        self.n = 0

    def activity(self, title, period=None):
        return Activity.objects.create(school=self.a, grade=7, period=period or self.period, title=title,
                                       held_on=timezone.localdate(), activity_type=self.kind, created_by=self.t1)

    def add(self, act, observer, code, score, key='', student=None):
        """score None = "not observed"."""
        session, _ = ObservationSession.objects.get_or_create(activity=act, observer=observer)
        return Observation.objects.create(
            session=session, student=student or self.s7, indicator=self.by_code[code], score=score,
            not_observed=score is None, evidence='saw it' if score else '', dedupe_key=key)

    def profile(self, period=None, user=None, student=None):
        qs = Observation.objects.all()
        return student_profile(student or self.s7, qs, period or self.period)

    def fill_all(self, acts, score=4):
        """Enough evidence for all 12 indicators: 2 observers x len(acts) activities."""
        for act in acts:
            for code in self.by_code:
                self.add(act, self.t1, code, score)
                self.add(act, self.t1b, code, score)


class IndicatorTests(EngineBase):
    def test_guide_worked_example_two_stage_mean(self):
        build, poster, game = self.activity('build'), self.activity('poster'), self.activity('game')
        for act, scores in ((build, (3, 4)), (poster, (4, 4)), (game, (2, 3))):
            self.add(act, self.t1, 3, scores[0])
            self.add(act, self.t1b, 3, scores[1])
        ind = self.profile().indicators[3]
        self.assertEqual(sorted(ind.per_activity.values()), [D('2.5'), D('3.5'), D('4')])
        self.assertEqual(_r(ind.score), D('3.33'))
        self.assertEqual((ind.evidences, ind.activities, ind.provisional), (6, 3, False))

    def test_more_rows_in_one_activity_do_not_add_weight(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        self.add(a1, self.t1, 1, 5)
        self.add(a1, self.t1b, 1, 5)
        self.add(a1, self.lead, 1, 5)
        self.add(a2, self.t1, 1, 1)
        self.assertEqual(self.profile().indicators[1].score, D(3))          # (5 + 1) / 2, not (5*3 + 1) / 4

    def test_not_observed_is_excluded_and_is_not_a_low_score(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        self.add(a1, self.t1, 1, 4)
        self.add(a1, self.t1b, 1, None)
        self.add(a2, self.t1, 1, 4)
        ind = self.profile().indicators[1]
        self.assertEqual((ind.score, ind.evidences), (D(4), 2))
        self.add(a1, self.t1, 2, None)
        only_no = self.profile().indicators[2]
        self.assertEqual((only_no.score, only_no.status), (None, NEEDS_MORE))

    def test_duplicates_with_one_key_are_one_independent_evidence(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        self.add(a1, self.t1, 1, 4, key='same-event')
        self.add(a1, self.t1b, 1, 2, key='same-event')
        self.add(a2, self.t1, 1, 4)
        ind = self.profile().indicators[1]
        self.assertEqual(ind.evidences, 2)                                  # 3 rows, 2 independent evidences
        self.assertTrue(ind.provisional)                                    # below the minimum of 3
        self.assertEqual(ind.per_activity[a1.pk], D(3))                     # the pair is averaged, not stacked

    def test_minimums_three_evidences_in_two_activities(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        for who in (self.t1, self.t1b, self.lead):
            self.add(a1, who, 1, 4)
        one_activity = self.profile().indicators[1]
        self.assertEqual((one_activity.evidences, one_activity.activities, one_activity.provisional), (3, 1, True))
        self.assertEqual(one_activity.status, NEEDS_MORE)
        self.add(a2, self.t1, 1, 4)
        self.assertFalse(self.profile().indicators[1].provisional)
        self.assertEqual(self.profile().indicators[1].status, USABLE)

    def test_thresholds_come_from_the_weight_set(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        self.add(a1, self.t1, 1, 4)
        self.add(a2, self.t1, 1, 4)
        WeightSet.objects.filter(school=self.a).update(min_observations=2)     # test-only shortcut around the lifecycle
        self.assertFalse(self.profile().indicators[1].provisional)

    def test_difference_between_activities_is_flagged_and_kept(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        for who in (self.t1, self.t1b):
            self.add(a1, who, 6, 5)
            self.add(a2, who, 6, 3)
        ind = self.profile().indicators[6]
        self.assertEqual((ind.activity_spread, ind.status), (D(2), NEEDS_DIFF))
        self.assertEqual({k: v for k, v in ind.per_activity.items()}, {a1.pk: D(5), a2.pk: D(3)})

    def test_difference_between_observers_is_flagged(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        self.add(a1, self.t1, 6, 5)
        self.add(a2, self.t1, 6, 5)
        self.add(a1, self.t1b, 6, 3)
        self.add(a2, self.t1b, 6, 3)
        ind = self.profile().indicators[6]
        self.assertEqual((ind.activity_spread, ind.observer_spread, ind.status), (D(0), D(2), NEEDS_DIFF))

    def test_small_difference_stays_usable(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        for who in (self.t1, self.t1b):
            self.add(a1, who, 6, 4)
            self.add(a2, who, 6, 3)
        self.assertEqual(self.profile().indicators[6].status, USABLE)       # spread 1 < 1.5


class BranchTests(EngineBase):
    def test_equal_scores_give_that_score_in_every_branch(self):
        self.fill_all([self.activity('a1'), self.activity('a2')], score=4)
        profile = self.profile()
        self.assertEqual({r.score for r in profile.branches.values()}, {D(4)})   # every column sums to 100
        self.assertEqual({r.status for r in profile.branches.values()}, {USABLE})
        self.assertEqual(len(profile.branches), 8)
        self.assertIn('اعتبارسنجی', profile.notice)

    def test_formula_is_sum_of_score_times_weight_over_100(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        self.fill_all([a1, a2], score=3)
        for act in (a1, a2):                     # raise indicator 1 (weight 25 in knowledge_production) to 5
            Observation.objects.filter(session__activity=act, indicator=self.by_code[1]).update(score=5)
        self.assertEqual(self.profile().branches[KP].score, D('3') + D(2) * 25 / 100)      # 3.5

    def test_missing_positive_weight_indicator_means_no_score(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        self.fill_all([a1, a2])
        Observation.objects.filter(indicator=self.by_code[1]).delete()
        branch = self.profile().branches[KP]
        self.assertEqual((branch.score, branch.missing, branch.status), (None, [1], NEEDS_MORE))
        self.assertEqual(self.profile().branches['culture_production'].missing, [1])

    def test_zero_weight_indicator_never_blocks_a_branch(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        self.fill_all([a1, a2])
        Observation.objects.filter(indicator__code__in=[4, 7, 8]).delete()     # weight 0 in knowledge_production
        profile = self.profile()
        self.assertEqual(profile.branches[KP].score, D(4))
        self.assertEqual(profile.branches[KP].missing, [])
        self.assertIsNone(profile.branches['culture_production'].score)         # indicator 4 weighs 20 there

    def test_provisional_indicator_makes_the_branch_provisional_but_scored(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        self.fill_all([a1, a2])
        Observation.objects.filter(indicator=self.by_code[2], session__activity=a2).delete()
        branch = self.profile().branches[KP]
        self.assertEqual(branch.provisional, [2])
        self.assertEqual((branch.score, branch.status), (D(4), NEEDS_MORE))

    def test_differing_indicator_flags_the_branch(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        self.fill_all([a1, a2])
        Observation.objects.filter(indicator=self.by_code[2], session__activity=a2).update(score=1)
        branch = self.profile().branches[KP]
        self.assertEqual((branch.differing, branch.status), ([2], NEEDS_DIFF))

    def test_x20_only_when_the_set_says_so(self):
        self.fill_all([self.activity('a1'), self.activity('a2')], score=3)
        self.assertIsNone(self.profile().branches[KP].score_x20)
        WeightSet.objects.filter(school=self.a).update(show_x20=True)
        self.assertEqual(self.profile().branches[KP].score_x20, D(60))

    def test_params_version_is_recorded(self):
        self.assertEqual(self.profile().params_version, WeightSet.objects.get(school=self.a, status='active').pk)


class PeriodAndScopeTests(EngineBase):
    def setUp(self):
        super().setUp()
        self.period2 = Period.objects.create(school=self.a, academic_year=self.period.academic_year, label='term 2')

    def test_periods_are_never_blended_and_change_is_reported(self):
        self.fill_all([self.activity('old1'), self.activity('old2')], score=2)
        self.fill_all([self.activity('new1', self.period2), self.activity('new2', self.period2)], score=4)
        now = self.profile(self.period2)
        self.assertEqual(now.branches[KP].score, D(4))                     # old scores of 2 are not mixed in
        self.assertEqual(now.branches[KP].change, D(2))
        self.assertEqual(now.indicators[1].change, D(2))
        self.assertEqual(now.previous_period_id, self.period.pk)
        first = self.profile(self.period)
        self.assertEqual((first.branches[KP].score, first.branches[KP].change, first.previous_period_id), (D(2), None, None))

    def test_no_change_when_the_previous_period_has_no_score(self):
        self.fill_all([self.activity('new1', self.period2), self.activity('new2', self.period2)])
        self.assertIsNone(self.profile(self.period2).branches[KP].change)

    def test_engine_uses_only_the_observations_it_is_given(self):
        a1, a2 = self.activity('a1'), self.activity('a2')
        self.fill_all([a1, a2], score=4)
        Observation.objects.filter(session__observer=self.t1b).update(score=2)
        from .access import visible_observations
        own = student_profile(self.s7, visible_observations(self.t1), self.period)          # teacher: own rows only
        wide = student_profile(self.s7, visible_observations(self.lead), self.period)       # grade lead: every observer
        other = student_profile(self.s7, visible_observations(self.t2), self.period)        # teacher of another grade
        self.assertEqual((own.branches[KP].score, wide.branches[KP].score), (D(4), D(3)))
        self.assertEqual(other.branches[KP].score, None)
        self.assertEqual(other.indicators[1].evidences, 0)

    def test_one_query_profiles_for_a_period_skip_students_without_data(self):
        self.fill_all([self.activity('a1'), self.activity('a2')])
        profiles = period_profiles(Observation.objects.all(), self.period)
        self.assertEqual(set(profiles), {self.s7.pk})

    def test_no_active_weight_set_is_an_error_not_a_default(self):
        WeightSet.objects.filter(school=self.a).update(status='retired')
        with self.assertRaises(ValueError):
            self.profile()


class EvaluationHookTests(EngineBase):
    def setUp(self):
        super().setUp()
        self.fill_all([self.activity('a1'), self.activity('a2')])

    def rows(self, **kw):
        return anonymised_rows(Observation.objects.all(), self.period, **kw)

    def test_rows_are_anonymised_and_salted(self):
        rows = self.rows(salt='s1')
        self.assertEqual(len(rows), 1)
        text = repr(rows)
        for forbidden in (self.s7.first_name, self.s7.last_name, 'saw it', 't1'):
            self.assertNotIn(forbidden, text)
        self.assertEqual(set(rows[0]), {'pid', 'grade', 'params_version', 'indicators', 'branches', 'status'})
        self.assertEqual(self.rows(salt='s1')[0]['pid'], rows[0]['pid'])           # stable within one study
        self.assertNotEqual(self.rows(salt='s2')[0]['pid'], rows[0]['pid'])        # unlinkable across salts
        self.assertEqual(len(rows[0]['indicators']), 12)

    def test_top_k_agreement(self):
        row = self.rows(salt='s')[0]
        row['branches'] = {'a': 5.0, 'b': 4.0, 'c': 3.0, 'd': 2.0, 'e': None}
        self.assertEqual(top_k_agreement([row], {row['pid']: {'a': 1, 'b': 2, 'c': 3, 'd': 4}}, k=2), 0.0)   # {a,b} vs {d,c}: no overlap
        self.assertEqual(top_k_agreement([row], {row['pid']: dict(row['branches'])}, k=3), 1.0)
        self.assertIsNone(top_k_agreement([row], {}))


def _r(value):
    return value.quantize(D('0.01'))
