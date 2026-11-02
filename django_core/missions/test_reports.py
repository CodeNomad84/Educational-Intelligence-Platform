"""Mission module, Slice 3: report, plan, the two forms and the admin aggregate. Gating (allowed / denied / expired / trial /
cross-school / trial data readable after a licensed row), scope per role, what each role may see, the write rules, audit,
and the no-ranking / no-export / small-group rules. Synthetic data only."""
from datetime import timedelta

from django.urls import get_resolver, reverse

from dashboard.page_testing import without_own_name
from dashboard.test_counselor import make_user
from schools.models import AuditEvent, SchoolModule, TeacherAssignment
from schools.module_grants import grant

from .models import ActivityChoice, Branch, Observation, ParentMeeting, PathSuggestion, WeightSet
from .test_engine import EngineBase
from .tests import TODAY

FOOTER_TEXT = 'هرگز برای پذیرش یا جانمایی'


class ReportBase(EngineBase):
    def setUp(self):
        super().setUp()
        for user, name in ((self.t1, 'Obsone'), (self.t1b, 'Obstwo')):
            user.first_name = name
            user.save()
        self.a1, self.a2 = self.activity('Bridge-A'), self.activity('Poster-B')
        # t1 scores 4 and t1b scores 2 on indicator 6 in both activities; t1 alone covers indicator 1 (strong, 5)
        for act in (self.a1, self.a2):
            self.add(act, self.t1, 6, 4)
            self.add(act, self.t1b, 6, 2)
            self.add(act, self.t1, 1, 5)
        Observation.objects.filter(indicator__code=6, session__observer=self.t1b).update(evidence='t1b-evidence-text')
        Observation.objects.filter(indicator__code=1).update(evidence='found-two-causes')
        self.report_url = reverse('missions:report', args=[self.s7.pk])
        self.counselor_user = self.counselor

    def get(self, user, url):
        self.client.force_login(user)
        return self.client.get(url)

    def post(self, user, url, data):
        self.client.force_login(user)
        return self.client.post(url, data)

    def urls(self, student=None):
        pk = (student or self.s7).pk
        return [reverse('missions:students'), reverse('missions:report', args=[pk]), reverse('missions:choices', args=[pk]),
                reverse('missions:meetings', args=[pk])]

    def plan_data(self, paths, period=None):
        data = {'period': (period or self.period).pk}
        for i, (branch, review) in enumerate(paths, 1):
            data.update({f'p{i}_branch': Branch.objects.get(code=branch).pk, f'p{i}_experience': f'exp {i}',
                         f'p{i}_goal': f'goal {i}', f'p{i}_review': review})
        return data

    def future(self, days=30):
        return (TODAY() + timedelta(days=days)).isoformat()


class GatingTests(ReportBase):
    def test_allowed_denied_expired_not_started_and_cross_school(self):
        for url in self.urls():
            self.assertEqual(self.get(self.lead, url).status_code, 200, url)
        self.assertEqual(self.get(self.admin, reverse('missions:aggregate')).status_code, 200)
        SchoolModule.objects.filter(school=self.a).delete()                         # no row for A
        for url in [*self.urls(), reverse('missions:aggregate')]:
            self.assertEqual(self.get(self.lead if 'aggregate' not in url else self.admin, url).status_code, 403, url)
        grant(self.a, 'mission', starts_on=TODAY() - timedelta(days=9), ends_on=TODAY() - timedelta(days=1))    # expired
        self.assertEqual(self.get(self.lead, self.report_url).status_code, 403)
        SchoolModule.objects.filter(school=self.a).delete()
        grant(self.a, 'mission', starts_on=TODAY() + timedelta(days=2))                                         # not started
        self.assertEqual(self.get(self.lead, self.report_url).status_code, 403)
        SchoolModule.objects.filter(school=self.a).delete()
        grant(self.a, 'mission')
        self.assertEqual(self.get(self.lead, reverse('missions:report', args=[self.sb.pk])).status_code, 404)   # student of school B

    def test_trial_works_and_trial_data_is_readable_after_a_licensed_row(self):
        SchoolModule.objects.filter(school=self.a).delete()
        SchoolModule.objects.create(school=self.a, module_key='mission', kind='trial', starts_on=TODAY() - timedelta(days=3),
                                    ends_on=TODAY() + timedelta(days=3))
        self.assertEqual(self.post(self.lead, reverse('missions:choices', args=[self.s7.pk]),
                                   {'period': self.period.pk, 'ch_book': 'trial-book', 'rs_book': 'because'}).status_code, 302)
        self.assertEqual(self.post(self.lead, reverse('missions:plan', args=[self.s7.pk]),
                                   self.plan_data([('nurturing', self.future()), ('culture_promotion', self.future())])).status_code, 302)
        SchoolModule.objects.filter(school=self.a).update(ends_on=TODAY() - timedelta(days=1))                  # trial ended
        self.assertEqual(self.get(self.lead, self.report_url).status_code, 403)
        self.assertEqual(self.post(self.lead, reverse('missions:meetings', args=[self.s7.pk]),
                                   {'held_on': TODAY().isoformat(), 'parents_present': 'both'}).status_code, 403)
        self.assertEqual((ActivityChoice.objects.count(), PathSuggestion.objects.count(), ParentMeeting.objects.count()), (1, 2, 0))
        grant(self.a, 'mission', starts_on=TODAY())                                                             # licensed
        page = self.get(self.lead, self.report_url)
        self.assertContains(page, 'trial-book')
        self.assertContains(page, 'exp 1')


class ScopeAndRoleTests(ReportBase):
    def test_who_may_open_which_report(self):
        self.assertEqual(self.get(self.lead, self.report_url).status_code, 200)
        self.assertEqual(self.get(self.lead, reverse('missions:report', args=[self.s8.pk])).status_code, 404)  # another grade
        self.assertEqual(self.get(self.t1, self.report_url).status_code, 200)                                  # has own observations
        self.assertEqual(self.get(self.t2, self.report_url).status_code, 404)
        self.assertEqual(self.get(self.tb, self.report_url).status_code, 404)
        for user in (self.admin, self.parent):
            self.assertEqual(self.get(user, self.report_url).status_code, 403)
            self.assertEqual(self.get(user, reverse('missions:students')).status_code, 403)
        self.assertEqual(self.get(self.t1, reverse('missions:aggregate')).status_code, 403)
        self.assertEqual(self.get(self.lead, reverse('missions:aggregate')).status_code, 403)

    def test_a_teacher_without_own_observations_gets_404(self):
        self.assertEqual(self.get(self.t2, self.report_url).status_code, 404)
        Observation.objects.filter(session__observer=self.t1b).delete()
        self.assertEqual(self.get(self.t1b, self.report_url).status_code, 404)

    def test_counselor_only_through_an_open_referral(self):
        self.assertEqual(self.get(self.counselor, self.report_url).status_code, 404)
        referral = self.refer(self.s7, self.counselor)
        self.assertEqual(self.get(self.counselor, self.report_url).status_code, 200)
        self.assertEqual(self.get(self.counselor, reverse('missions:report', args=[self.s8.pk])).status_code, 404)
        self.assertEqual(self.get(self.counselor_b, self.report_url).status_code, 404)
        referral.status = 'closed'
        referral.save()
        self.assertEqual(self.get(self.counselor, self.report_url).status_code, 404)

    def test_only_the_grade_lead_writes(self):
        self.refer(self.s7, self.counselor)
        for user in (self.t1, self.counselor):
            self.assertEqual(self.get(user, reverse('missions:choices', args=[self.s7.pk])).status_code, 403)
            self.assertEqual(self.get(user, reverse('missions:meetings', args=[self.s7.pk])).status_code, 403)
            self.assertEqual(self.post(user, reverse('missions:plan', args=[self.s7.pk]),
                                       self.plan_data([('nurturing', self.future()), ('culture_promotion', self.future())])).status_code, 403)
        self.assertEqual(self.post(self.lead, reverse('missions:choices', args=[self.s8.pk]), {}).status_code, 404)
        self.assertEqual(PathSuggestion.objects.count() + ActivityChoice.objects.count(), 0)


class WhatEachRoleSeesTests(ReportBase):
    def test_teacher_sees_only_status_of_own_observations(self):
        page = self.get(self.t1, self.report_url)
        self.assertEqual(page.status_code, 200)
        self.assertTemplateUsed(page, 'missions/report_status.html')
        text = without_own_name(page)   # t1 is 'Obsone': its own top bar may name it, nothing else on the page may
        for hidden in ('t1b-evidence-text', 'found-two-causes', 'Obstwo', 'Obsone', 'مسیرهای پیشنهادی', 'دغدغه'):
            self.assertNotIn(hidden, text)
        self.assertIn('<span class="eip-user-name">Obsone', page.content.decode())   # the helper removed only the top bar
        ind = page.context['indicators']
        self.assertTrue(all('score' not in row for row in ind))
        self.assertTrue(all('score' not in row for row in page.context['branches']))
        self.assertEqual(ind[5]['evidences'], 2)                                    # own two rows on indicator 6, not t1b's

    def test_grade_lead_sees_evidence_and_who_gave_what(self):
        page = self.get(self.lead, self.report_url)
        self.assertContains(page, 'found-two-causes')
        self.assertContains(page, 'Obsone')
        self.assertContains(page, 'Obstwo')
        self.assertContains(page, 'Bridge-A')
        self.assertEqual([s['name'] for s in page.context['situations']], ['بیان و انتقال معنا'])      # 4 vs 2: observers differ
        self.assertEqual([i['name'] for i in page.context['strong']], ['کاوشگری و فهم عمیق'])           # score 5 >= 4.0

    def test_counselor_sees_evidence_but_not_who_gave_it(self):
        self.refer(self.s7, self.counselor)
        page = self.get(self.counselor, self.report_url)
        self.assertContains(page, 'found-two-causes')
        for hidden in ('Obsone', 'Obstwo'):
            self.assertNotContains(page, hidden)
        self.assertNotContains(page, 'name="p1_branch"')                           # no plan form for the counselor

    def test_missing_indicators_are_listed_by_name(self):
        page = self.get(self.lead, self.report_url)
        branch = next(b for b in page.context['branches'] if b['name'] == 'تولید دانش')
        self.assertFalse(branch['scored'])
        self.assertIn('تحلیل و استدلال', branch['missing'])
        self.assertNotIn('کاوشگری و فهم عمیق', branch['missing'])
        self.assertContains(page, 'تحلیل و استدلال')
        status = self.get(self.t1, self.report_url)
        self.assertIn('تحلیل و استدلال', next(b for b in status.context['branches'] if b['name'] == 'تولید دانش')['missing'])

    def test_thresholds_come_from_the_weight_set(self):
        WeightSet.objects.filter(school=self.a).update(strong_at='4.5', growth_at='4.5')
        page = self.get(self.lead, self.report_url)
        self.assertEqual({i['name'] for i in page.context['strong']}, {'کاوشگری و فهم عمیق'})
        WeightSet.objects.filter(school=self.a).update(strong_at='5.0', growth_at='1.0')
        page = self.get(self.lead, self.report_url)
        self.assertEqual({i['name'] for i in page.context['strong']}, {'کاوشگری و فهم عمیق'})
        WeightSet.objects.filter(school=self.a).update(strong_at='5.0', growth_at='1.0')
        self.assertEqual(page.context['growth'], [])

    def test_choices_are_shown_apart_from_scores(self):
        ActivityChoice.objects.create(student=self.s7, period=self.period, category='book', choice='a novel', reason='liked-it')
        page = self.get(self.lead, self.report_url)
        self.assertContains(page, 'liked-it')
        self.assertEqual(page.context['branches'], self.get(self.lead, self.report_url).context['branches'])
        before = [b['score'] for b in page.context['branches']]
        ActivityChoice.objects.all().delete()
        self.assertEqual([b['score'] for b in self.get(self.lead, self.report_url).context['branches']], before)

    def test_no_ranking_branches_and_students_in_fixed_order(self):
        page = self.get(self.lead, self.report_url)
        self.assertEqual([b['name'] for b in page.context['branches']], list(Branch.objects.values_list('name_fa', flat=True)))
        s_a = self.student('Aaa', self.c7, 7)
        s_b = self.student('Bbb', self.c7, 7)
        for st, score in ((s_a, 1), (s_b, 5)):
            self.add(self.a1, self.t1, 1, score, student=st)
        listing = self.get(self.lead, reverse('missions:students'))
        self.assertEqual([s.first_name for s in listing.context['students']], ['Aaa', 'Bbb', 'Seven'])

    def test_footer_on_every_page(self):
        for url in [*self.urls(), reverse('missions:students')]:
            self.assertContains(self.get(self.lead, url), FOOTER_TEXT)
        self.assertContains(self.get(self.t1, self.report_url), FOOTER_TEXT)
        self.assertContains(self.get(self.admin, reverse('missions:aggregate')), FOOTER_TEXT)

    def test_no_export_route_exists(self):
        names = [p.name for p in get_resolver().url_patterns[0].url_patterns] if False else []
        from . import urls
        names = [p.name for p in urls.urlpatterns]
        self.assertFalse([n for n in names if n and any(w in n for w in ('export', 'csv', 'download', 'xls'))])
        self.assertNotIn('attachment', self.get(self.lead, self.report_url).get('Content-Disposition', ''))
        self.assertIn('no-store', self.get(self.lead, self.report_url)['Cache-Control'])


class PlanAndFormsTests(ReportBase):
    def save_plan(self, paths, **kw):
        return self.post(self.lead, reverse('missions:plan', args=[self.s7.pk]), self.plan_data(paths, **kw))

    def test_plan_saved_with_params_version_and_replaced(self):
        response = self.save_plan([('nurturing', self.future()), ('culture_promotion', self.future()), ('value_production', self.future(60))])
        self.assertEqual(response.status_code, 302)
        ws = WeightSet.objects.get(school=self.a, status='active')
        self.assertEqual(set(PathSuggestion.objects.values_list('params_version', flat=True)), {ws.pk})
        self.assertEqual(PathSuggestion.objects.count(), 3)
        self.save_plan([('nurturing', self.future(90)), ('culture_promotion', self.future())])
        self.assertEqual(set(PathSuggestion.objects.values_list('branch__code', flat=True)), {'nurturing', 'culture_promotion'})
        self.assertEqual(PathSuggestion.objects.get(branch__code='nurturing').review_date, TODAY() + timedelta(days=90))
        page = self.get(self.lead, self.report_url)
        self.assertContains(page, 'exp 1')
        self.refer(self.s7, self.counselor)
        self.assertContains(self.get(self.counselor, self.report_url), 'exp 1')                                 # counselor reads it

    def test_plan_rules(self):
        for bad in ([('nurturing', self.future())],                                                             # one path
                    [('nurturing', self.future()), ('nurturing', self.future())],                               # duplicate branch
                    [('nurturing', (TODAY() - timedelta(days=1)).isoformat()), ('culture_promotion', self.future())],   # past date
                    [('nurturing', ''), ('culture_promotion', self.future())]):                                 # no date
            self.save_plan(bad)
            self.assertEqual(PathSuggestion.objects.count(), 0, bad)
        data = self.plan_data([('nurturing', self.future()), ('culture_promotion', self.future())])
        data['p2_goal'] = ''
        self.post(self.lead, reverse('missions:plan', args=[self.s7.pk]), data)
        self.assertEqual(PathSuggestion.objects.count(), 0)

    def test_model_caps_three_paths(self):
        from django.core.exceptions import ValidationError
        for code in ('nurturing', 'culture_promotion', 'value_production'):
            PathSuggestion.objects.create(student=self.s7, period=self.period, branch=Branch.objects.get(code=code), experience='e',
                                          growth_goal='g', review_date=TODAY(), params_version=1)
        with self.assertRaises(ValidationError):
            PathSuggestion.objects.create(student=self.s7, period=self.period, branch=Branch.objects.get(code='value_circulation'),
                                          experience='e', growth_goal='g', review_date=TODAY(), params_version=1)

    def test_choices_form_saves_updates_and_clears(self):
        url = reverse('missions:choices', args=[self.s7.pk])
        self.post(self.lead, url, {'period': self.period.pk, 'ch_book': 'novel', 'rs_book': 'story', 'ch_sport': 'football'})
        self.assertEqual(ActivityChoice.objects.count(), 2)
        self.post(self.lead, url, {'period': self.period.pk, 'ch_book': 'poems', 'rs_book': 'rhythm'})
        self.assertEqual(list(ActivityChoice.objects.values_list('category', 'choice', 'reason')), [('book', 'poems', 'rhythm')])
        self.assertContains(self.get(self.lead, url + f'?period={self.period.pk}'), 'rhythm')
        self.post(self.lead, url, {'period': self.period.pk, 'ch_book': 'x' * 151})
        self.assertEqual(ActivityChoice.objects.get().choice, 'poems')                                         # invalid input saves nothing

    def test_meetings_log(self):
        url = reverse('missions:meetings', args=[self.s7.pk])
        self.assertEqual(self.post(self.lead, url, {'held_on': TODAY().isoformat(), 'parents_present': 'one',
                                                    'agreements': 'read daily', 'quality': 'partial'}).status_code, 302)
        self.assertEqual(self.post(self.lead, url, {'held_on': 'bad', 'parents_present': 'one'}).status_code, 200)
        self.assertEqual(ParentMeeting.objects.count(), 1)
        self.assertContains(self.get(self.lead, self.report_url), 'read daily')

    def test_audit_has_counts_and_no_content(self):
        self.get(self.lead, self.report_url)
        self.save_plan([('nurturing', self.future()), ('culture_promotion', self.future())])
        self.post(self.lead, reverse('missions:choices', args=[self.s7.pk]), {'period': self.period.pk, 'ch_book': 'secret-title'})
        self.post(self.lead, reverse('missions:meetings', args=[self.s7.pk]),
                  {'held_on': TODAY().isoformat(), 'parents_present': 'both', 'agreements': 'secret-agreement'})
        events = AuditEvent.objects.filter(action__startswith='mission_')
        actions = set(events.values_list('action', flat=True))
        self.assertTrue({'mission_report_view', 'mission_plan_save', 'mission_choices_save', 'mission_meeting_add'} <= actions)
        self.assertEqual(events.get(action='mission_plan_save').detail, '2')
        self.assertFalse(any(w in str(v) for e in events for v in (e.detail, e.object_type, e.object_id) for w in ('secret', 'exp ')))


class AggregateTests(ReportBase):
    def fill_students(self, count):
        for i in range(count):
            self.add(self.a1, self.t1, 1, 3, student=self.student(f'Extra{i}', self.c7, 7))

    def test_a_small_group_is_suppressed(self):
        page = self.get(self.admin, reverse('missions:aggregate'))
        self.assertEqual(page.context['blocks'][0]['groups'], [{'grade': 7, 'suppressed': True}])
        self.assertNotContains(page, 'Seven')
        self.fill_students(3)                                                                                  # 4 students: still hidden
        self.assertTrue(self.get(self.admin, reverse('missions:aggregate')).context['blocks'][0]['groups'][0]['suppressed'])

    def test_a_group_of_five_is_shown_with_small_cells_hidden(self):
        self.fill_students(4)
        page = self.get(self.admin, reverse('missions:aggregate'))
        group = page.context['blocks'][0]['groups'][0]
        self.assertEqual((group['suppressed'], group['n']), (False, 5))
        self.assertEqual(group['rows'][0]['cells'], [5, '<5', '<5'])                                           # all five need more observation
        for hidden in ('Extra0', 'Seven', 'found-two-causes', 'Obsone'):
            self.assertNotContains(page, hidden)
        self.assertTrue(AuditEvent.objects.filter(action='mission_aggregate_view', school=self.a).exists())

    def test_admin_of_another_school_sees_nothing_of_this_one(self):
        self.fill_students(4)
        blocks = self.get(self.admin_b, reverse('missions:aggregate')).context['blocks']
        self.assertEqual([(b['school_id'], b['groups']) for b in blocks], [(self.b.pk, [])])        # own school only, no data


class WeightsPageAndHelpTests(ReportBase):
    def url(self):
        return reverse('missions:weights')

    def test_school_admin_sees_the_active_set_with_column_sums_and_lifecycle(self):
        page = self.get(self.admin, self.url())
        self.assertEqual(page.status_code, 200)
        block = page.context['blocks'][0]
        ws = WeightSet.objects.get(school=self.a, status='active')
        self.assertEqual((block['school_id'], block['active'].pk, block['sums']), (self.a.pk, ws.pk, [100] * 8))
        self.assertEqual(len(block['table']), 12)
        self.assertContains(page, f'params_version): {ws.pk}')
        self.assertContains(page, 'فعال')
        self.assertContains(page, FOOTER_TEXT)
        self.assertNotContains(page, 'Seven')                                    # parameters only, no student data
        self.assertFalse(any(tag in page.content.decode() for tag in ('<form', 'type="submit"')))   # read only

    def test_other_roles_and_other_schools_are_refused_and_it_is_gated(self):
        for user in (self.lead, self.t1, self.counselor, self.parent):
            self.assertEqual(self.get(user, self.url()).status_code, 403, user.username)
        self.assertEqual([b['school_id'] for b in self.get(self.admin_b, self.url()).context['blocks']], [self.b.pk])
        SchoolModule.objects.filter(school=self.a).delete()
        self.assertEqual(self.get(self.admin, self.url()).status_code, 403)
        grant(self.a, 'mission', starts_on=TODAY() - timedelta(days=9), ends_on=TODAY() - timedelta(days=1))
        self.assertEqual(self.get(self.admin, self.url()).status_code, 403)

    def test_a_non_active_version_is_listed_but_the_table_is_the_active_one(self):
        ws = WeightSet.objects.get(school=self.a, status='active')
        WeightSet.objects.create(school=self.a, version=2, note='draft v2')
        block = self.get(self.admin, self.url()).context['blocks'][0]
        self.assertEqual([(v.version, v.status) for v in block['versions']], [(2, 'draft'), (1, 'active')])
        self.assertEqual(block['active'].pk, ws.pk)
        self.assertTrue(AuditEvent.objects.filter(action='mission_weights_view', school=self.a).exists())

    def test_teacher_status_page_lists_the_exact_missing_indicators_without_scores(self):
        page = self.get(self.t1, self.report_url)
        self.assertContains(page, 'شاخه‌ها: چه چیزی هنوز باید مشاهده شود؟')
        self.assertContains(page, 'تحلیل و استدلال')                              # missing for 'تولید دانش'
        branch = next(b for b in page.context['branches'] if b['name'] == 'تولید دانش')
        self.assertNotIn('کاوشگری و فهم عمیق', branch['missing'])                  # t1 did observe indicator 1
        self.assertNotIn('score', branch)

    def test_grid_explains_not_observed_and_the_minimums_from_the_active_set(self):
        page = self.get(self.t1, self.grid_url())
        for text in ('«مشاهده نشد»', 'نمرهٔ ۱', '3 مشاهدهٔ معتبر در 2 فعالیت'):
            self.assertContains(page, text)
        WeightSet.objects.filter(school=self.a).update(min_observations=4, min_activities=3)
        self.assertContains(self.get(self.t1, self.grid_url()), '4 مشاهدهٔ معتبر در 3 فعالیت')
