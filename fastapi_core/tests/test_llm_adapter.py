"""P7 adapter tests: no network, no real keys; a mock transport stands in for every provider. Synthetic data only."""
import json
import logging
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import llm_adapter as ad  # noqa: E402

KEY = 'sk-test-' + 'k' * 24          # a fake key for the mock only
EXT = {'chatgpt': {'class': 'external', 'base_url': 'https://api.example.test/v1', 'model': 'model-x', 'api_key_env': 'EXT_KEY'}}
LOC = {'ollama': {'class': 'local', 'base_url': 'http://ollama:11434/v1', 'model': 'local-model'}}


def env(providers=None, school_map=None, **extra):
    out = {'LLM_PROVIDERS': json.dumps(providers or {**EXT, **LOC}), 'LLM_SCHOOL_MAP': json.dumps(school_map or {'1': 'chatgpt', '2': 'ollama'}),
           'EXT_KEY': KEY}
    out.update(extra)
    return out


class Mock:
    def __init__(self, status=200, body=None):
        self.calls, self.status = [], status
        self.body = body if body is not None else json.dumps({'choices': [{'message': {'content': 'answer'}}],
                                                              'usage': {'prompt_tokens': 3, 'completion_tokens': 2}}).encode()

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, json.loads(body), timeout))
        return self.status, self.body


class AdapterBase(unittest.TestCase):
    def setUp(self):
        ad.reset_usage()
        self.env = env()
        self.mock = Mock()

    def call(self, school=1, purpose='pedagogy', messages=None, **kw):
        provider = ad.provider_for_school(school, self.env)
        return ad.complete(provider, messages if messages is not None else [{'role': 'user', 'content': 'Explain fractions simply.'}], purpose,
                           school_id=school, env=self.env, transport=self.mock, **kw)

    def refused(self, code, **kw):
        with self.assertRaises(ad.LLMError) as ctx:
            self.call(**kw)
        self.assertEqual(ctx.exception.code, code)
        self.assertEqual(self.mock.calls, [])               # nothing left the process
        return ctx.exception


class OffByDefaultTests(AdapterBase):
    def test_no_config_means_no_provider(self):
        self.assertEqual(ad.load_providers({}), {})
        self.assertIsNone(ad.provider_for_school(1, {}))
        self.assertIsNone(ad.provider_for_school(1, {'LLM_PROVIDERS': json.dumps(EXT)}))          # providers but no school map
        self.assertIsNone(ad.provider_for_school(3, self.env))                                     # school not mapped

    def test_bad_configuration_is_refused_not_guessed(self):
        bad = [{'x': {'class': 'cloud', 'base_url': 'https://a.test/v1', 'model': 'm'}},
               {'x': {'class': 'external', 'base_url': 'http://a.test/v1', 'model': 'm', 'api_key_env': 'K'}},           # external must be TLS
               {'x': {'class': 'external', 'base_url': 'https://u:p@a.test/v1', 'model': 'm', 'api_key_env': 'K'}},       # credentials in URL
               {'x': {'class': 'external', 'base_url': 'https://a.test/v1?k=1', 'model': 'm', 'api_key_env': 'K'}},
               {'x': {'class': 'external', 'base_url': 'https://a.test/v1', 'model': 'm'}},                               # external needs a key env
               {'x': {'class': 'external', 'base_url': 'https://a.test/v1', 'model': 'm', 'api_key_env': 'bad name'}},
               {'x': {'class': 'local', 'base_url': 'ftp://a.test', 'model': 'm'}},
               {'x': {'class': 'local', 'base_url': 'http://a.test/v1', 'model': ''}},
               {'x': {'class': 'local', 'base_url': 'http://a.test/v1', 'model': 'm', 'timeout': 0}}]
        for providers in bad:
            with self.assertRaises(ad.LLMError, msg=providers):
                ad.load_providers({'LLM_PROVIDERS': json.dumps(providers)})
        with self.assertRaises(ad.LLMError):
            ad.load_providers({'LLM_PROVIDERS': '{not json'})
        with self.assertRaises(ad.LLMError):
            ad.provider_for_school(1, env(school_map={'1': 'ghost'}))                              # mapped to an unknown provider


class GeneralPurposeTests(AdapterBase):
    def test_the_request_is_the_openai_compatible_shape_for_any_provider(self):
        for school, url in ((1, 'https://api.example.test/v1/chat/completions'), (2, 'http://ollama:11434/v1/chat/completions')):
            self.mock = Mock()
            result = self.call(school=school)
            url_, headers, body, timeout = self.mock.calls[0]
            self.assertEqual(url_, url)
            self.assertEqual(set(body), {'model', 'messages', 'max_tokens', 'temperature'})
            self.assertEqual(body['messages'], [{'role': 'user', 'content': 'Explain fractions simply.'}])
            self.assertEqual(result['text'], 'answer')
            self.assertIn('ممکن است اشتباه باشد', result['label'])
        self.assertEqual(self.mock.calls[0][1].get('Authorization'), None)                        # local without a key sends no auth header

    def test_the_key_comes_only_from_the_named_variable_and_is_never_echoed(self):
        result = self.call()
        self.assertEqual(self.mock.calls[0][1]['Authorization'], f'Bearer {KEY}')
        self.assertNotIn(KEY, json.dumps(result))
        self.assertNotIn(KEY, repr(ad.provider_for_school(1, self.env)))
        self.env.pop('EXT_KEY')
        self.mock = Mock()
        self.refused('not_configured')                                                              # external without a key: refused, no call

    def test_another_openai_compatible_provider_needs_configuration_only(self):
        self.env = env(providers={'deepseek-like': {'class': 'external', 'base_url': 'https://other.example.test', 'model': 'm2',
                                                    'api_key_env': 'OTHER_KEY'}}, school_map={'7': 'deepseek-like'}, OTHER_KEY='other-' + 'x' * 20)
        result = self.call(school=7)
        self.assertEqual(self.mock.calls[0][0], 'https://other.example.test/chat/completions')
        self.assertEqual((result['provider_class'], result['model']), ('external', 'm2'))

    def test_upstream_failures_become_one_fixed_error_without_provider_text(self):
        for status, body in ((500, b'secret provider text'), (200, b'not json'), (200, b'{"choices": []}'), (200, b'{"choices":[{"message":{"content":5}}]}')):
            self.mock = Mock(status, body)
            with self.assertRaises(ad.LLMError) as ctx:
                self.call()
            self.assertEqual(ctx.exception.code, 'upstream_error')
            self.assertNotIn('secret', str(ctx.exception))

    def test_usage_is_logged_without_content_or_key(self):
        with self.assertLogs('llm', level='INFO') as logs:
            self.call(messages=[{'role': 'user', 'content': 'PRIVATE-CONTENT-123 about fractions'}])
        text = ' '.join(logs.output)
        self.assertIn('class=external', text)
        self.assertNotIn('PRIVATE-CONTENT', text)
        self.assertNotIn(KEY, text)

    def test_daily_cap_per_school(self):
        self.env['LLM_DAILY_CAP'] = '2'
        self.call()
        self.call()
        self.mock = Mock()
        self.refused('cap_reached')
        self.mock = Mock()
        self.call(school=2)                                                                        # another school has its own counter
        self.env['LLM_DAILY_CAP'] = '0'
        ad.reset_usage()
        self.mock = Mock()
        self.refused('cap_reached', school=2)

    def test_message_shape_limits(self):
        for bad in ([], 'text', [{'role': 'user'}], [{'role': 'tool', 'content': 'x'}], [{'role': 'user', 'content': 5}],
                    [{'role': 'user', 'content': 'x', 'extra': 1}], [{'role': 'user', 'content': 'x' * (ad.MAX_CHARS + 1)}],
                    [{'role': 'user', 'content': ''}], [{'role': 'user', 'content': 'x'}] * (ad.MAX_MESSAGES + 1)):
            self.refused('bad_request', messages=bad)


class ExternalClassRulesTests(AdapterBase):
    def test_only_whitelisted_non_personal_purposes_go_out(self):
        for purpose in ('school_data_summary', 'student_report', 'counseling', 'anything'):
            self.refused('purpose_refused', purpose=purpose)
        for purpose in sorted(ad.PURPOSES_EXTERNAL):
            self.mock = Mock()
            self.call(purpose=purpose)

    def test_personal_data_patterns_never_leave_the_platform(self):
        samples = ['کد ملی ۰۰۱۲۳۴۵۶۷۸ است', 'id 0012345678', 'id 001-234-5678', 'call 09123456789', 'call ۰۹۱۲۳۴۵۶۷۸۹', 'call +989123456789',
                   'mail a.b@example.org', 'student Ali Rezaei struggles']
        for text in samples:
            self.refused('pii_refused', messages=[{'role': 'user', 'content': text}], roster_names=['Rezaei'])

    def test_a_system_message_is_filtered_too(self):
        self.refused('pii_refused', messages=[{'role': 'system', 'content': 'context 0012345678'}, {'role': 'user', 'content': 'hi'}])

    def test_clean_text_passes(self):
        self.call(messages=[{'role': 'user', 'content': 'Write 3 easy questions about fractions for grade 7 (page 12 of 2026).'}],
                  roster_names=['Rezaei'])


class LocalClassRulesTests(AdapterBase):
    def test_local_class_may_summarise_school_data_but_never_counseling(self):
        self.call(school=2, purpose='school_data_summary', messages=[{'role': 'user', 'content': 'Summarise: attendance 91%'}])
        self.mock = Mock()
        for purpose in ('counseling', 'counselor_notes', 'student_report'):
            self.refused('purpose_refused', school=2, purpose=purpose)

    def test_local_class_does_not_apply_the_external_pii_filter(self):
        self.call(school=2, purpose='school_data_summary', messages=[{'role': 'user', 'content': 'Class 7-A has 24 students'}])
        self.assertEqual(len(self.mock.calls), 1)


class SourceSafetyTests(unittest.TestCase):
    def test_no_vendor_sdk_and_no_secret_in_source(self):
        text = (ROOT / 'llm_adapter.py').read_text(encoding='utf-8')
        for forbidden in ('import openai', 'from openai', 'anthropic', 'sk-'):
            self.assertNotIn(forbidden, text)



if __name__ == '__main__':
    unittest.main()
