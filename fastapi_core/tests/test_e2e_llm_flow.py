"""End-to-end audit of the FastAPI service contract used by Django (QA audit of 2026-11-14).

Report: ``E2E_AUDIT_REPORT.md``. This module drives the REAL ``main.py`` (routing, auth dependency,
pydantic validation, status mapping) against a REAL HTTP provider on 127.0.0.1 -- the OpenAI-compatible
stub in ``tests/e2e_support.py`` -- so the transport, the timeout, the TLS rule and the response
parsing are the ones that ship. torch/numpy/joblib/rag_service are faked (as in test_security.py) so
no GPU or database is needed; that means ``/predict/`` is checked for its CONTRACT (shape, 0..1
range, validation, auth), not for the quality of the model.

Plain tests assert correct behaviour; ``@unittest.expectedFailure`` tests assert the TARGET of a
finding (Fxx) that the current code does not meet, and print the measured current value first.

Run from fastapi_core/:  python -m unittest discover -s tests -t . -v
"""
import json
import logging
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:                                                   # CI: -t . -> tests is a package
    from tests.e2e_support import SECRET, StubProvider, bearer, install_fakes, make_token
except ImportError:                                    # run from inside fastapi_core/tests
    from e2e_support import SECRET, StubProvider, bearer, install_fakes, make_token

_saved = {k: sys.modules.get(k) for k in ('torch', 'numpy', 'joblib', 'train_nn_model', 'rag_service', 'main', 'auth')}
install_fakes()
sys.modules.pop('main', None)
os.environ['SERVICE_JWT_SECRET'] = SECRET
import main  # noqa: E402  (the real main.py, heavy modules faked)
import llm_adapter  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FEATURES = {'grade': 7, 'attendance_rate': 0.9, 'avg_completion_rate': 0.8, 'avg_exam_score': 15.0,
            'total_absences': 1, 'total_lates': 0, 'total_communications': 3, 'completed_homework': 12}
MESSAGES = [{'role': 'system', 'content': 'answer only from the excerpts'},
            {'role': 'user', 'content': 'ساعت شروع کلاس‌ها چه زمانی است؟'}]
STUB = StubProvider()          # one real provider for the whole module (reset per test)


def setUpModule():
    logging.disable(logging.CRITICAL)     # main.py configures logging at import


def tearDownModule():
    logging.disable(logging.NOTSET)
    STUB.close()
    for name, mod in _saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


class LLMFlowTests(unittest.TestCase):
    def setUp(self):
        llm_adapter.reset_usage()
        STUB.reset()
        patcher = mock.patch.dict(os.environ, {'SERVICE_JWT_SECRET': SECRET})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(main.app)
        self.client.__enter__()                       # runs the startup hook (validate_service_secret)
        self.addCleanup(self.client.__exit__, None, None, None)

    # ---------- helpers ----------
    def configure(self, *, provider=True, school_map=None, cap='200', timeout=30, api_key_env='', kind='local',
                  model='stub-1', extra_env=None):
        providers = ({'stub': {'class': kind, 'base_url': STUB.base_url, 'model': model,
                               'timeout': timeout, 'max_tokens': 600}} if provider else {})
        if provider and api_key_env:
            providers['stub']['api_key_env'] = api_key_env
        env = {'LLM_PROVIDERS': json.dumps(providers),
               'LLM_SCHOOL_MAP': json.dumps(school_map if school_map is not None
                                            else ({'1': 'stub'} if provider else {})),
               'LLM_DAILY_CAP': cap}
        env.update(extra_env or {})
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def complete(self, headers=None, **body):
        payload = {'purpose': 'document_qa', 'messages': MESSAGES}
        payload.update(body)
        return self.client.post('/llm/complete/', json=payload,
                                headers=bearer(['Teacher']) if headers is None else headers)

    def status(self, headers=None, **params):
        return self.client.get('/llm/status/', params=params,
                               headers=bearer(['Teacher']) if headers is None else headers)

    def test_01_status_reports_the_provider_class_for_a_mapped_school(self):
        self.configure()
        response = self.status()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'enabled': True, 'class': 'local'})
        self.assertEqual(STUB.calls, [])                       # a status check must not spend a call

    def test_02_status_is_off_for_a_school_without_a_mapping(self):
        self.configure(school_map={})
        self.assertEqual(self.status().json(), {'enabled': False, 'class': None})
        self.configure(school_map={'2': 'stub'})
        self.assertEqual(self.status().json(), {'enabled': False, 'class': None})

    def test_03_a_broken_configuration_reads_as_off_not_as_an_error(self):
        patcher = mock.patch.dict(os.environ, {'LLM_PROVIDERS': '{not json', 'LLM_SCHOOL_MAP': '{"1": "stub"}'})
        patcher.start()
        self.addCleanup(patcher.stop)
        response = self.status()
        self.assertEqual((response.status_code, response.json()), (200, {'enabled': False, 'class': None}))
        self.assertEqual(self.complete().status_code, 503)     # bad_config -> 503, never a 500

    def test_04_an_external_provider_over_plain_http_is_refused(self):
        """llm_adapter allows http only for the local class (a key would travel in clear text)."""
        self.configure(kind='external', api_key_env='LLM_KEY_STUB', extra_env={'LLM_KEY_STUB': 'sk-test'})
        self.assertEqual(self.status().json(), {'enabled': False, 'class': None})
        self.assertEqual(self.complete().status_code, 503)
        self.assertEqual(STUB.calls, [])

    def test_05_complete_returns_the_answer_over_real_http(self):
        self.configure()
        response = self.complete()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['text'], 'پاسخ آزمایشی [1]')
        self.assertEqual(body['provider_class'], 'local')
        self.assertEqual(body['model'], 'stub-1')
        self.assertIn('هوش مصنوعی', body['label'])
        self.assertEqual(body['usage'], {'prompt_tokens': 12, 'completion_tokens': 7})
        self.assertEqual(len(STUB.calls), 1)
        sent = STUB.calls[0]
        self.assertEqual(sent['path'], '/v1/chat/completions')
        self.assertNotIn('authorization', {k.lower() for k in sent['headers']})     # local class, no key
        payload = json.loads(sent['body'])
        self.assertEqual((payload['model'], payload['temperature'], payload['max_tokens']), ('stub-1', 0.2, 600))
        self.assertEqual([m['role'] for m in payload['messages']], ['system', 'user'])
        self.assertNotIn('avoid_names', payload)                                  # never forwarded upstream

    def test_06_a_key_is_sent_as_a_bearer_token_and_never_returned(self):
        self.configure(api_key_env='LLM_KEY_STUB', extra_env={'LLM_KEY_STUB': 'sk-e2e-secret-value'})
        response = self.complete()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(STUB.calls[0]['headers'].get('Authorization'), 'Bearer sk-e2e-secret-value')
        self.assertNotIn('sk-e2e-secret-value', response.text)

    def test_07_a_provider_5xx_is_502_upstream_error(self):
        self.configure()
        STUB.configure(mode='http500')
        response = self.complete()
        self.assertEqual((response.status_code, response.json()['detail']), (502, 'upstream_error'))

    def test_08_garbage_or_differently_shaped_json_is_502(self):
        self.configure()
        for mode in ('garbage', 'noselect'):
            with self.subTest(mode=mode):
                STUB.configure(mode=mode)
                response = self.complete()
                self.assertEqual((response.status_code, response.json()['detail']), (502, 'upstream_error'))

    def test_09_a_slow_provider_is_cut_off_by_the_configured_timeout(self):
        self.configure(timeout=1)
        STUB.configure(delay=2)
        started = time.perf_counter()
        response = self.complete()
        elapsed = time.perf_counter() - started
        print(f'[E2E] provider timeout=1s, stub sleeps 2s -> status={response.status_code} elapsed={elapsed:.2f}s')
        self.assertEqual((response.status_code, response.json()['detail']), (502, 'upstream_error'))
        self.assertLess(elapsed, 1.9)

    def test_10_a_purpose_outside_the_local_whitelist_is_refused_before_any_call(self):
        self.configure()
        for purpose in ('counseling', 'student_profile', ''):
            with self.subTest(purpose=purpose):
                response = self.complete(purpose=purpose)
                self.assertEqual((response.status_code, response.json()['detail']), (422, 'purpose_refused'))
        self.assertEqual(STUB.calls, [])

    def test_11_auth_is_checked_before_the_provider(self):
        self.configure()
        cases = [({}, 401),                                        # no header
                 (bearer(['Teacher'], secret='x' * 40), 401),      # wrong secret
                 (bearer(['Parent']), 403),                        # a role that may not use the assistant
                 (bearer([]), 403)]
        for headers, expected in cases:
            with self.subTest(expected=expected, headers=sorted(headers)):
                response = self.client.post('/llm/complete/', json={'purpose': 'document_qa', 'messages': MESSAGES},
                                            headers=headers)
                self.assertEqual(response.status_code, expected)
                self.assertEqual(STUB.calls, [])

    def test_11b_an_ai_scope_token_is_valid_on_the_llm_routes_only(self):
        """A Django-minted token for ONE AI call (scope 'ai') must never widen access anywhere else (review F8)."""
        self.configure()
        ai_token = bearer(['Teacher'], scope='ai')
        self.assertEqual(self.complete(headers=ai_token).status_code, 200)
        self.assertEqual(self.client.get('/documents/list/', headers=ai_token).status_code, 403)
        self.assertEqual(self.client.post('/predict/', json=FEATURES, headers=ai_token).status_code, 403)

    def test_12_a_token_without_a_schools_claim_is_refused(self):
        self.configure()
        response = self.complete(headers=bearer(['Teacher'], schools=None))
        self.assertEqual(response.status_code, 401)
        response = self.complete(headers=bearer(['Teacher'], schools='1'))
        self.assertEqual(response.status_code, 401)

    def test_13_a_token_with_two_schools_must_choose_one(self):
        self.configure()
        response = self.complete(headers=bearer(['Teacher'], schools=[1, 2]))
        self.assertEqual((response.status_code, response.json()['detail']), (403, 'Exactly one school is required.'))
        self.assertEqual(STUB.calls, [])

    def test_14_the_school_comes_from_the_signed_token_not_from_the_body(self):
        self.configure()
        response = self.complete(school=2, school_id=2, payload={'school': 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(STUB.calls), 1)                      # extra body keys are ignored by the model
        response = self.complete(headers=bearer(['Teacher'], schools=[2]))
        self.assertEqual((response.status_code, response.json()['detail']), (403, 'AI is not enabled for this school.'))

    def test_15_the_daily_cap_returns_429_without_a_provider_call(self):
        self.configure(cap='1')
        self.assertEqual(self.complete().status_code, 200)
        response = self.complete()
        self.assertEqual((response.status_code, response.json()['detail']), (429, 'cap_reached'))
        self.assertEqual(len(STUB.calls), 1)

    def test_16_F05_a_call_that_failed_at_the_provider_does_not_use_up_the_cap(self):
        """F05 (service side): ``_take_slot`` used to keep the slot after a 5xx, so one outage could use the school's
        whole cap up with zero answers. Change 0044 refunds the slot unless the call returns an answer; companion
        test_15 proves the 429 mapping, test_07 proves the 502, so this test is about accounting only."""
        self.configure(cap='1')
        STUB.configure(mode='http500')
        first = self.complete()
        self.assertEqual(first.status_code, 502)
        STUB.configure(mode='ok')
        second = self.complete()
        print(f'[E2E] F05 service side: after a 502 the next call returns {second.status_code}')
        self.assertEqual(second.status_code, 200)

    def test_17_a_burst_of_four_asks_from_one_school_gets_one_429_busy(self):
        """MAX_CONCURRENT_PER_SCHOOL = 3 with a non-blocking acquire: the 4th concurrent ask is refused with 429
        'busy' instead of queueing. Measured so the report can describe what a staff room hitting 'ask' together sees."""
        self.configure()
        STUB.configure(delay=0.4)
        codes, lock = [], threading.Lock()

        def ask():
            response = self.complete()
            with lock:
                codes.append(response.status_code)

        threads = [threading.Thread(target=ask) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        print(f'[E2E] burst of 4 concurrent asks -> {sorted(codes)}')
        self.assertEqual(sorted(codes), [200, 200, 200, 429])
        self.assertEqual(len(STUB.calls), 3)

    def test_18_predict_answers_with_a_probability_in_the_0_1_range(self):
        for path in ('/predict/', '/api/v1/predict/'):
            with self.subTest(path=path):
                response = self.client.post(path, json=FEATURES, headers=bearer(['SchoolAdmin']))
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(set(body), {'risk_probability', 'is_high_risk', 'message'})
                self.assertGreaterEqual(body['risk_probability'], 0.0)
                self.assertLessEqual(body['risk_probability'], 1.0)
                self.assertEqual(body['is_high_risk'], body['risk_probability'] > 0.5)

    def test_19_predict_rejects_a_bad_vector(self):
        headers = bearer(['SchoolAdmin'])
        bad = [({k: v for k, v in FEATURES.items() if k != 'grade'}, 422),
               ({**FEATURES, 'grade': 'seven'}, 422),
               ({**FEATURES, 'attendance_rate': None}, 422)]
        for payload, expected in bad:
            with self.subTest(payload=sorted(payload)[:3]):
                self.assertEqual(self.client.post('/predict/', json=payload, headers=headers).status_code, expected)

    def test_20_predict_is_admin_only_and_ignores_the_ai_scope(self):
        for headers, expected in ((bearer(['Teacher']), 403), (bearer(['Parent']), 403),
                                  (bearer(['SchoolAdmin'], scope='ai'), 403), ({}, 401)):
            with self.subTest(expected=expected):
                self.assertEqual(self.client.post('/predict/', json=FEATURES, headers=headers).status_code, expected)

    def test_21_the_phase1_disabled_routes_stay_disabled_for_every_role(self):
        admin = bearer(['SchoolAdmin'])
        for method, path, kwargs in (('post', '/chat/', {'json': {'query': 'q'}}),
                                     ('post', '/documents/', {'json': {'title': 't', 'content': 'c'}}),
                                     ('get', '/documents/search/', {'params': {'query': 'q'}})):
            with self.subTest(path=path):
                self.assertEqual(getattr(self.client, method)(path, headers=admin, **kwargs).status_code, 403)
        self.assertEqual(self.client.get('/').status_code, 200)          # the health route stays public

    def test_22_a_response_never_echoes_the_prompt_a_key_or_a_traceback(self):
        self.configure(api_key_env='LLM_KEY_STUB', extra_env={'LLM_KEY_STUB': 'sk-e2e-secret-value'})
        ok = self.complete()
        STUB.configure(mode='http500')
        failed = self.complete()
        for response in (ok, failed):
            self.assertNotIn('sk-e2e-secret-value', response.text)
            self.assertNotIn('answer only from the excerpts', response.text)
            self.assertNotIn(str(STUB.port), response.text)              # no upstream host/port leaks
            self.assertNotIn('Traceback', response.text)
        self.assertEqual(failed.json(), {'detail': 'upstream_error'})

    def test_23_startup_refuses_a_missing_or_weak_secret_and_requests_fail_closed(self):
        weak = 'short-secret'
        patcher = mock.patch.dict(os.environ, {'SERVICE_JWT_SECRET': weak})
        patcher.start()
        self.addCleanup(patcher.stop)
        with self.assertRaises(RuntimeError):
            with TestClient(main.app):
                pass
        self.assertEqual(self.complete().status_code, 503)               # the request-time check, fail closed
        self.assertEqual(STUB.calls, [])

    def test_24_the_llm_routes_do_not_accept_a_blank_bearer_token(self):
        self.configure()
        response = self.complete(headers={'Authorization': 'Bearer '})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(STUB.calls, [])



