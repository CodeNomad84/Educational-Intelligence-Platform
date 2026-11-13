"""0031 (decisions 53-55): the default catalog, family supersession and the Excel import. Mutation checks (by hand, see the commit):
removing the stronger-open suppression, the in-place upgrade, the 'lands as draft' rule, the school scope or the formula guard
each fails a test here."""
import io

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from interventions.models import Strategy
from risk import catalog, catalog_services as svc, lifecycle, rules
from risk.models import Alert, Rule, RuleHit, RuleSettings
from risk.rules_testing import TODAY, RulesBase
from schools.models import AuditEvent


def activate(test, code, school=None):
    return svc.activate_template(test.admin, (school or test.a).pk, code)


class CatalogContentTests(RulesBase):
    def test_kinds_match_the_catalog_and_every_template_validates(self):
        self.assertEqual(set(Rule.KINDS), set(catalog.TEMPLATES))
        for code, template in catalog.TEMPLATES.items():
            clauses = catalog.instantiate(code, 20)
            self.assertTrue(rules.validate_clauses(clauses, template['connective'], school_id=self.a.pk), code)
            rules.validate_rule_fields(kind=code, risk_type=template['risk_type'], severity=template['severity'], cooldown_days=14)
            self.assertIn(template['risk_type'], ('academic', 'attendance', 'behavioral'))

    def test_built_templates_equal_the_starters_and_the_starter_pack_is_six(self):
        for code, spec in rules.STARTERS.items():
            self.assertEqual(catalog.instantiate(code, 20), spec['clauses'], code)
        self.assertEqual(set(catalog.STARTER_PACK), {'attendance_shift', 'repeated_absence', 'low_average', 'grade_drop',
                                                     'repeated_concerns', 'chronic_absence_watch'})
        self.assertEqual(catalog.TEMPLATES['off_track_combo']['title'], 'افت هم‌زمان نمره و حضور')

    def test_percent_thresholds_follow_the_school_scale(self):
        self.assertEqual(catalog.instantiate('low_average', 100)[0]['threshold'], 60)
        self.assertEqual(catalog.instantiate('low_average', 20)[0]['threshold'], 12)
        self.assertIsNone(catalog.instantiate('low_average', None))
        self.assertEqual(catalog.instantiate('absence_run', None)[0]['threshold'], 5)      # no score clause: no scale needed

    def test_activation_makes_a_draft_with_provenance_and_refuses_bad_cases(self):
        rule = activate(self, 'failing_average')
        self.assertEqual((rule.status, rule.template_code, rule.template_version), ('draft', 'failing_average', catalog.CATALOG_VERSION))
        self.assertEqual(rule.clauses[0]['threshold'], 10)
        self.assertTrue(AuditEvent.objects.filter(action='rule_from_template', detail__startswith='failing_average').exists())
        with self.assertRaises(ValidationError):
            activate(self, 'failing_average')                                              # already there
        with self.assertRaises(ValidationError):
            svc.activate_template(self.admin, self.a.pk, 'nope')
        RuleSettings.objects.filter(school=self.a).update(grade_scale_max=None)
        with self.assertRaises(ValidationError):
            activate(self, 'low_average')                                                  # score template, no scale: fail closed
        self.assertEqual(activate(self, 'late_pattern').status, 'draft')                   # no score clause: fine

    def test_pages_are_school_admin_only_and_scoped(self):
        for user in (self.lead, self.teacher, self.parent, self.counselor):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('rules:catalog')).status_code, 403, user.username)
            self.assertEqual(self.client.post(reverse('rules:catalog'), {'code': 'late_pattern'}).status_code, 403)
        self.client.force_login(self.admin)
        page = self.client.get(reverse('rules:catalog'))
        self.assertContains(page, 'بسته پیشنهادی شروع')
        self.assertNotContains(page, 'Balfanz')
        self.client.post(reverse('rules:catalog'), {'code': 'late_pattern'})
        self.assertTrue(Rule.objects.filter(school=self.a, code='late_pattern', status='draft').exists())
        self.assertFalse(Rule.objects.filter(school=self.b).exists())                    # never another school


class FamilySupersessionTests(RulesBase):
    def go(self, code):
        template = catalog.TEMPLATES[code]
        rule = lifecycle.create(self.admin, self.a.pk, code=code, kind=code, title=template['title'], risk_type=template['risk_type'],
                                severity=template['severity'], connective=template['connective'],
                                clauses=catalog.instantiate(code, 20), template=(code, 1))
        lifecycle.simulate(rule, self.admin, as_of=TODAY)
        lifecycle.submit(rule, self.admin)
        return lifecycle.approve(rule, self.admin)

    def run_all(self):
        return {r.rule.code: r for r in rules.run_school(self.a.pk, as_of=TODAY)}

    def test_stronger_and_weaker_together_raise_one_alert(self):
        self.absent_streak(self.s7, days=range(1, 9))
        self.go('repeated_absence')                      # weaker
        self.go('absence_run')                           # stronger, same family
        runs = self.run_all()
        self.assertEqual(Alert.objects.filter(student=self.s7).count(), 1)
        self.assertEqual(Alert.objects.get(student=self.s7).risk_event.severity, 'orange')
        self.assertEqual((runs['absence_run'].alerts_raised, runs['repeated_absence'].skipped_superseded), (1, 1))

    def test_a_stronger_hit_upgrades_the_weaker_new_alert_in_place(self):
        self.absent_streak(self.s7, days=range(1, 9))
        self.go('repeated_absence')
        self.run_all()
        weak = Alert.objects.get(student=self.s7)
        self.assertEqual(weak.risk_event.severity, 'yellow')
        self.go('absence_run')
        runs = self.run_all()
        self.assertEqual(Alert.objects.filter(student=self.s7).count(), 1)             # still one alert
        weak.refresh_from_db()
        self.assertEqual((weak.risk_event.severity, runs['absence_run'].alerts_upgraded, runs['absence_run'].alerts_raised), ('orange', 1, 0))
        self.assertEqual(RuleHit.objects.filter(alert=weak).count(), 2)               # both rules are on the one alert (provenance)

    def test_reviewed_weaker_alert_does_not_block_a_stronger_one(self):
        self.absent_streak(self.s7, days=range(1, 9))
        self.go('repeated_absence')
        self.run_all()
        from risk.services import review_alert
        review_alert(self.admin, Alert.objects.get(student=self.s7), Alert.DISMISSED, reason='other', note='checked')
        self.go('absence_run')
        self.run_all()
        self.assertEqual(Alert.objects.filter(student=self.s7).count(), 2)            # dismissed = not open: a new alert is legitimate

    def test_other_families_and_other_students_are_independent(self):
        RuleSettings.objects.filter(school=self.a).update(breaker_percent=100)
        self.absent_streak(self.s7, days=range(1, 9))
        self.absent_streak(self.s8, days=range(1, 9))
        self.go('repeated_absence')
        self.go('late_pattern')                          # no family
        self.run_all()
        self.assertEqual(Alert.objects.filter(student=self.s8).count(), 1)
        self.assertEqual(Alert.objects.filter(student=self.s7).count(), 1)


def book(rules_rows=(), strategy_rows=()):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Rules'
    header = svc.RULE_COLUMNS + [f'{n}{i}' for i in range(1, 5) for n in svc.CLAUSE_COLUMNS]
    ws.append(header)
    for row in rules_rows:
        ws.append([row.get(h) for h in header])
    st = wb.create_sheet('Strategies')
    st.append(svc.STRATEGY_COLUMNS)
    for row in strategy_rows:
        st.append([row.get(h) for h in svc.STRATEGY_COLUMNS])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


GOOD = dict(code='mine', kind='late_pattern', title='Mine', risk_type='attendance', severity='yellow', connective='all', cooldown_days=14,
            metric1='late_count', op1='>=', threshold1=4, window_days1=30)
GOOD_S = dict(title='My strategy', intervention_type='academic', tier=2, typical_days=21, description='d')


class ImportTests(RulesBase):
    def report(self, rows, apply=False):
        r_rows, _s = svc.read_workbook(book(rows))
        return svc.import_rules(self.admin, self.a.pk, r_rows, apply=apply)

    def test_the_download_template_is_itself_importable(self):
        r_rows, s_rows = svc.read_workbook(svc.template_workbook())
        self.assertTrue(all(x[1] == 'ok' for x in svc.import_rules(self.admin, self.a.pk, r_rows, apply=False)))
        self.assertTrue(all(x[1] == 'ok' for x in svc.import_strategies(self.a, s_rows, apply=False)))

    def test_rows_use_the_form_validators_and_land_as_drafts(self):
        bad = {'emotional': {**GOOD, 'code': 'e1', 'risk_type': 'emotional'}, 'family': {**GOOD, 'code': 'e2', 'risk_type': 'family'},
               'metric': {**GOOD, 'code': 'm1', 'metric1': 'eval'}, 'op': {**GOOD, 'code': 'o1', 'op1': '=='},
               'number': {**GOOD, 'code': 'n1', 'threshold1': 'abc'}, 'sev': {**GOOD, 'code': 's1', 'severity': 'red'},
               'formula': {**GOOD, 'code': 'f1', 'title': '=HYPERLINK("x")'}, 'at': {**GOOD, 'code': 'a1', 'title': '@cmd'},
               'scale': {**GOOD, 'code': 'sc', 'metric1': 'avg_score', 'op1': '<', 'threshold1': 99, 'window_days1': 30},
               'kind': {**GOOD, 'code': 'k1', 'kind': 'custom'}}
        report = self.report([GOOD, *bad.values(), {**GOOD, 'code': 'mine'}])
        self.assertEqual([x[1] for x in report], ['ok'] + ['refused'] * len(bad) + ['refused'])      # last: duplicate code in file
        self.assertEqual(Rule.objects.count(), 0)                                    # dry run wrote nothing
        applied = self.report([GOOD, {**GOOD, 'code': 'e1', 'risk_type': 'emotional'}], apply=True)
        self.assertEqual([x[1] for x in applied], ['ok', 'refused'])
        self.assertEqual(Rule.objects.get(code='mine').status, 'draft')
        self.assertFalse(Rule.objects.filter(code='e1').exists())

    def test_persian_digits_and_existing_codes(self):
        self.assertEqual(self.report([{**GOOD, 'threshold1': '۴', 'window_days1': '۳۰'}])[0][1], 'ok')
        self.report([GOOD], apply=True)
        self.assertEqual(self.report([GOOD])[0][1], 'refused')                       # code exists in this school

    def test_strategies_land_inactive_and_are_validated(self):
        _r, s_rows = svc.read_workbook(book(strategy_rows=[GOOD_S, {**GOOD_S, 'title': 'x2', 'tier': 9}, {**GOOD_S, 'title': '=1+1'},
                                                           {**GOOD_S, 'title': 'x3', 'typical_days': 0}]))
        report = svc.import_strategies(self.a, s_rows, apply=True)
        self.assertEqual([x[1] for x in report], ['ok', 'refused', 'refused', 'refused'])
        obj = Strategy.objects.get(title='My strategy')
        self.assertEqual((obj.school_id, obj.is_active), (self.a.pk, False))

    def test_file_level_refusals(self):
        for data, code in ((b'not a workbook', 'not_xlsx'), (b'PK' + b'x' * 10, 'not_xlsx'), (b'PK' + b'x' * (svc.MAX_BYTES + 1), 'file_too_large'),
                           (book([{**GOOD, 'code': f'r{i}'} for i in range(svc.MAX_ROWS + 1)]), 'too_many_rows')):
            with self.assertRaises(svc.ImportRefused) as ctx:
                svc.read_workbook(data)
            self.assertEqual(ctx.exception.code, code)

    def post_file(self, data, name='f.xlsx'):
        return self.client.post(reverse('rules:import'), {'file': SimpleUploadedFile(name, data)})

    def test_view_is_a_two_step_scoped_flow_and_audited(self):
        for user in (self.lead, self.teacher, self.parent):
            self.client.force_login(user)
            self.assertEqual(self.client.get(reverse('rules:import')).status_code, 403)
            self.assertEqual(self.post_file(book([GOOD])).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('rules:import_template')).status_code, 200)
        page = self.post_file(book([GOOD], [GOOD_S]))
        self.assertContains(page, 'گزارش بررسی')
        self.assertEqual((Rule.objects.count(), Strategy.objects.filter(title='My strategy').count()), (0, 0))   # nothing before confirm
        nonce = self.client.session['rules_import']['nonce']
        from django.test import Client
        other = Client()
        other.force_login(self.admin_b)                                            # another school's admin cannot confirm this one
        other.post(reverse('rules:import'), {'step': 'confirm', 'nonce': nonce})
        self.assertEqual(Rule.objects.count(), 0)
        self.assertEqual(self.client.post(reverse('rules:import'), {'step': 'confirm', 'nonce': 'wrong'}).status_code, 302)
        self.assertEqual(Rule.objects.count(), 0)
        self.client.post(reverse('rules:import'), {'step': 'confirm', 'nonce': nonce})
        self.assertEqual(Rule.objects.get(code='mine').school_id, self.a.pk)
        self.assertEqual(Rule.objects.get(code='mine').status, 'draft')
        self.assertFalse(Strategy.objects.get(title='My strategy').is_active)
        self.assertTrue(AuditEvent.objects.filter(action='rules_import', detail='c1r0').exists())
        self.assertTrue(AuditEvent.objects.filter(action='strategies_import', detail='c1r0').exists())
        self.assertEqual(self.post_file(b'junk').status_code, 200)                  # a bad file is a message, not an error page


class ReviewFixesTests(RulesBase):
    """Review of 0031 (decision 58): M1 bomb guards and throttle, L1 overflow, L3 session payload, L4 recheck, L5 family keying."""
    report = ImportTests.report
    post_file = ImportTests.post_file
    absent_streak = RulesBase.absent_streak

    def test_zip_bomb_member_count_blank_rows_and_overflow_cells_are_refused_or_reported(self):
        import zipfile
        good = book([GOOD])
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                dst.writestr(item, src.read(item.filename))
            dst.writestr('xl/junk.bin', b'\0' * (svc.MAX_UNCOMPRESSED + 1))      # tiny when compressed, huge when read
        self.assertLess(len(out.getvalue()), svc.MAX_BYTES)
        with self.assertRaises(svc.ImportRefused) as ctx:
            svc.read_workbook(out.getvalue())
        self.assertEqual(ctx.exception.code, 'file_too_large')
        many = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(good)) as src, zipfile.ZipFile(many, 'w') as dst:
            for item in src.infolist():
                dst.writestr(item, src.read(item.filename))
            for n in range(svc.MAX_MEMBERS + 1):
                dst.writestr(f'xl/x{n}.txt', b'x')
        with self.assertRaises(svc.ImportRefused):
            svc.read_workbook(many.getvalue())
        wb = Workbook()
        wb.active.title = 'Rules'
        wb.active.append(svc.RULE_COLUMNS)
        for _ in range(svc.MAX_SCANNED + 5):
            wb.active.append([' '])                                                 # blank-looking rows still count as scanned
        buf = io.BytesIO()
        wb.save(buf)
        with self.assertRaises(svc.ImportRefused) as ctx:
            svc.read_workbook(buf.getvalue())
        self.assertEqual(ctx.exception.code, 'too_many_rows')
        report = self.report([{**GOOD, 'window_days1': 'inf'}, {**GOOD, 'code': 'o2', 'cooldown_days': '1e999'}])
        self.assertEqual([x[1] for x in report], ['refused', 'refused'])             # OverflowError is a row refusal, not a 500
        _r, s_rows = svc.read_workbook(book(strategy_rows=[{**GOOD_S, 'tier': 'inf'}]))
        self.assertEqual(svc.import_strategies(self.a, s_rows, apply=False)[0][1:], ('refused', 'invalid_row'))

    def test_uploads_are_throttled_per_user(self):
        from django.core.cache import cache
        cache.clear()
        self.client.force_login(self.admin)
        for _ in range(svc.UPLOADS_PER_WINDOW):
            self.post_file(book([GOOD]))
        page = self.post_file(book([GOOD]))
        self.assertContains(page, 'بیش از حد مجاز')
        self.assertNotIn('preview', page.context or {})
        cache.clear()

    def test_the_session_keeps_only_whitelisted_short_cells(self):
        self.client.force_login(self.admin)
        r_rows, _s = svc.read_workbook(book([{**GOOD, 'title': 'T' * 900}]))
        r_rows[0]['evil_extra_column'] = 'x' * 5000
        kept = svc.trim(r_rows)
        self.assertNotIn('evil_extra_column', kept[0])
        self.assertEqual(len(kept[0]['title']), svc.MAX_CELL)

    def test_a_weaker_alert_reviewed_in_the_gap_is_not_upgraded(self):
        self.absent_streak(self.s7, days=range(1, 9))
        FamilySupersessionTests.go(self, 'repeated_absence')
        rules.run_school(self.a.pk, as_of=TODAY)
        alert = Alert.objects.get(student=self.s7)
        from risk.services import review_alert
        review_alert(self.admin, alert, Alert.ACCEPTED)                              # reviewed after _family_state read it as NEW
        rule = Rule.objects.get(code='repeated_absence')
        self.assertFalse(rules._upgrade_alert(rule, alert, 'm', 'e', self.a.pk, self.s7, TODAY, [], self.admin))
        alert.refresh_from_db()
        self.assertEqual(alert.message == 'm', False)

    def test_only_rules_made_from_the_catalog_join_a_family(self):
        self.absent_streak(self.s7, days=range(1, 9))
        FamilySupersessionTests.go(self, 'repeated_absence')                         # catalog rule
        custom = lifecycle.create(self.admin, self.a.pk, code='absence_run', kind='absence_run', title='custom', risk_type='attendance',
                                  severity='orange', connective='all', clauses=catalog.instantiate('absence_run', 20))
        lifecycle.simulate(custom, self.admin, as_of=TODAY)
        lifecycle.submit(custom, self.admin)
        lifecycle.approve(custom, self.admin)                                        # same code as a template, but NOT made from it
        rules.run_school(self.a.pk, as_of=TODAY)
        self.assertEqual(Alert.objects.filter(student=self.s7).count(), 2)           # no supersession, no upgrade
