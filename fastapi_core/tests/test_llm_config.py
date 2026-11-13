"""S1 of change 0043 / ADR-0008: the AI-provider configuration surface, offline.

Checks that the committed `.env.llm.example` is valid configuration that maps NO school, that compose hands the file to
the `fastapi` service only and optionally, that `.gitignore` keeps the operator file out, and that `tools/llm_smoke.py`
passes in mock mode while never printing a key. Standard library only; no network, no provider, no key.
Run from fastapi_core/:  python -m unittest tests.test_llm_config -v
"""
import contextlib
import importlib.util
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / '.env.llm.example'
COMPOSE = REPO / 'docker-compose.yml'
TOOL = REPO / 'tools' / 'llm_smoke.py'
# The image run mounts only fastapi_core/ at /app, so these checks need the repository root (same guard as test_exposure).
REPO_AVAILABLE = EXAMPLE.is_file() and COMPOSE.is_file() and TOOL.is_file()
ONLY_IN_REPO = unittest.skipUnless(REPO_AVAILABLE, 'repository root not visible from this location (image run)')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm_adapter  # noqa: E402


def load_tool():
    spec = importlib.util.spec_from_file_location('llm_smoke_under_test', TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compose_service(name):
    """Lines of one top-level compose service (two-space key), comments removed."""
    lines = COMPOSE.read_text(encoding='utf-8').splitlines()
    start = next((i for i, l in enumerate(lines) if re.fullmatch(rf'  {re.escape(name)}:\s*(#.*)?', l)), None)
    if start is None:
        return None
    block = []
    for line in lines[start + 1:]:
        if re.match(r'  \S', line) and not line.lstrip().startswith('#'):
            break
        block.append(line)
    return [l for l in block if not l.lstrip().startswith('#')]


@ONLY_IN_REPO
class ExampleConfigTests(unittest.TestCase):
    """The committed example must be usable, inert and free of secrets."""

    def setUp(self):
        self.assertTrue(EXAMPLE.exists(), 'the example file is missing')
        self.values = load_tool().read_env_file(EXAMPLE)

    def test_the_example_parses_as_real_adapter_configuration(self):
        providers = llm_adapter.load_providers(self.values)
        self.assertEqual(sorted(providers), ['gapgpt'])
        provider = providers['gapgpt']
        self.assertEqual(provider.kind, llm_adapter.EXTERNAL)
        self.assertEqual(provider.model, 'gpt-4o-mini')
        self.assertTrue(provider.base_url.startswith('https://'))
        self.assertEqual(provider.api_key_env, 'LLM_KEY_GAPGPT')
        self.assertLessEqual(provider.max_tokens, 1000, 'the example must stay a defensive cap')
        self.assertLessEqual(provider.timeout, 60)

    def test_the_example_maps_no_school(self):
        """D1 = A: the default state is 'a provider exists, no school uses it'."""
        self.assertEqual(json.loads(self.values['LLM_SCHOOL_MAP']), {})
        for school_id in (1, 2, 0):
            self.assertIsNone(llm_adapter.provider_for_school(school_id, env=self.values))

    def test_the_key_is_an_empty_placeholder(self):
        self.assertEqual(self.values['LLM_KEY_GAPGPT'], '', 'the example must never contain a key value')

    def test_the_key_name_satisfies_the_dedicated_key_rule(self):
        """Review M1: only LLM_KEY_* names, and never a Django/secret-looking name."""
        name = llm_adapter.load_providers(self.values)['gapgpt'].api_key_env
        self.assertRegex(name, llm_adapter._ENV_NAME.pattern)
        self.assertFalse([bad for bad in llm_adapter._FORBIDDEN_IN_ENV_NAME if bad in name])
        self.assertNotIn('GAPGPT_API_KEY', (EXAMPLE.read_text(encoding='utf-8')))

    def test_the_example_has_no_secret_looking_value(self):
        text = EXAMPLE.read_text(encoding='utf-8')
        for line in text.splitlines():
            live = line.split('=', 1)[1] if '=' in line and not line.lstrip().startswith('#') else ''
            self.assertNotRegex(live, r'(?i)bearer\s+\S')
            self.assertNotRegex(live, r'\bsk-[A-Za-z0-9]')
            self.assertNotRegex(live, r'[A-Za-z0-9_\-]{24,}', f'a long token-like value in: {line.split("=", 1)[0]}')

    def test_the_daily_cap_is_a_defensive_value(self):
        self.assertEqual(self.values['LLM_DAILY_CAP'], '100')
        self.assertLessEqual(int(self.values['LLM_DAILY_CAP']), 200)


@ONLY_IN_REPO
class ComposeWiringTests(unittest.TestCase):
    """The file reaches exactly one service, and it is optional."""

    def setUp(self):
        self.fastapi = compose_service('fastapi')
        self.assertIsNotNone(self.fastapi, 'fastapi service not found in docker-compose.yml')

    def test_fastapi_receives_the_llm_env_file_optional(self):
        text = '\n'.join(self.fastapi)
        self.assertIn('path: .env.llm', text)
        self.assertIn('required: false', text)
        self.assertNotRegex(text, r'(?m)^\s+-\s+\.env\.llm\s*$', 'a required .env.llm would break a non-AI deployment')

    def test_fastapi_still_does_not_receive_djangos_env(self):
        text = '\n'.join(self.fastapi)
        self.assertNotRegex(text, r'(?m)^\s+-\s+\.env\s*(#.*)?$')
        self.assertNotIn('.env.minio', text)

    def test_only_fastapi_receives_the_llm_env_file(self):
        live = '\n'.join(l for l in COMPOSE.read_text(encoding='utf-8').splitlines()
                         if not l.lstrip().startswith('#'))
        self.assertEqual(live.count('.env.llm'), 1, 'the AI key must reach one service only')


@ONLY_IN_REPO
class SmokeToolTests(unittest.TestCase):
    """tools/llm_smoke.py: mock by default, live only on request, never a key in the output."""

    def setUp(self):
        self.tool = load_tool()
        self.example = self.tool.read_env_file(EXAMPLE)

    def run_tool(self, argv, env):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = self.tool.run(argv, env=env)
        return code, buffer.getvalue()

    def test_mock_passes_with_the_committed_example(self):
        code, out = self.run_tool(['--mock', '--env-file', str(EXAMPLE)], {})
        self.assertEqual(code, 0, out)
        self.assertIn('RESULT  OK', out)
        self.assertIn('sent no student data', out)

    def test_mock_shows_decision_62_refusing_document_qa_for_external(self):
        code, out = self.run_tool(['--mock', '--env-file', str(EXAMPLE), '--purpose', 'document_qa'], {})
        self.assertEqual(code, 1, out)
        self.assertIn("purpose 'document_qa' -> purpose_refused", out)

    def test_mock_never_prints_the_key(self):
        secret = 'TOP-SECRET-VALUE-1234567890'
        env = dict(self.example, LLM_KEY_GAPGPT=secret)
        code, out = self.run_tool(['--mock'], env)
        self.assertEqual(code, 0, out)
        self.assertNotIn(secret, out)
        self.assertNotIn('Bearer', out)

    def test_live_without_a_key_exits_2(self):
        code, out = self.run_tool(['--live', '--env-file', str(EXAMPLE)], {})
        self.assertEqual(code, 2, out)
        self.assertIn('needs a key', out)

    def test_missing_configuration_exits_2(self):
        code, out = self.run_tool(['--mock'], {})
        self.assertEqual(code, 2, out)

    def test_an_unknown_provider_name_exits_2(self):
        code, out = self.run_tool(['--mock', '--env-file', str(EXAMPLE), '--provider', 'nope'], {})
        self.assertEqual(code, 2, out)

    def test_an_unreadable_env_file_exits_2(self):
        code, out = self.run_tool(['--mock', '--env-file', str(REPO / 'no-such-env-file')], {})
        self.assertEqual(code, 2, out)

    def test_broken_provider_json_is_reported_not_raised(self):
        code, out = self.run_tool(['--mock'], {'LLM_PROVIDERS': '{not json'})
        self.assertEqual(code, 2, out)
        self.assertIn('bad_config', out)

    def test_the_env_reader_strips_quotes_and_skips_comments(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.env'
            path.write_text("# comment\nexport_style=1\nA='x'\nB=\"y\"\n\nno_equals\n", encoding='utf-8')
            self.assertEqual(self.tool.read_env_file(path), {'export_style': '1', 'A': 'x', 'B': 'y'})


@ONLY_IN_REPO
class GitignoreTests(unittest.TestCase):
    """The operator file must never be committable; the template must be."""

    def setUp(self):
        self.lines = (REPO / '.gitignore').read_text(encoding='utf-8').splitlines()

    def test_the_operator_file_is_ignored_and_the_template_is_kept(self):
        self.assertIn('.env.*', self.lines)
        self.assertIn('!.env.llm.example', self.lines)
        self.assertLess(self.lines.index('.env.*'), self.lines.index('!.env.llm.example'),
                        'the exception must come after the wildcard')

    def test_there_is_no_exception_for_the_operator_file_itself(self):
        self.assertNotIn('!.env.llm', self.lines)


if __name__ == '__main__':
    unittest.main()

