"""The FastAPI service (incl. /llm/complete/) must not be reachable from browsers or the public network (owner 2026-11-02):
no published port in docker-compose.yml, no reverse-proxy rule to it, and a service token on every route. Static checks over the
repository files; they need only the standard library (the repository root is the parent of fastapi_core/)."""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def service_block(text, name):
    """Lines of one top-level compose service (two-space indented key), without needing a YAML library."""
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if re.fullmatch(rf'  {re.escape(name)}:\s*(#.*)?', l)), None)
    if start is None:
        return None
    block = []
    for line in lines[start + 1:]:
        if re.match(r'  \S', line) and not line.lstrip().startswith('#'):      # the next service
            break
        block.append(line)
    return [l for l in block if not l.lstrip().startswith('#')]


@unittest.skipUnless((REPO / 'docker-compose.yml').exists(), 'repository root not available')
class ExposureTests(unittest.TestCase):
    def test_the_fastapi_service_publishes_no_port(self):
        block = service_block((REPO / 'docker-compose.yml').read_text(encoding='utf-8'), 'fastapi')
        self.assertIsNotNone(block, 'fastapi service not found in docker-compose.yml')
        text = '\n'.join(block)
        self.assertNotRegex(text, r'(?m)^\s+ports\s*:', 'FastAPI must not publish a port (not even on loopback)')
        self.assertNotRegex(text, r'(?m)^\s+network_mode\s*:\s*["\']?host', 'FastAPI must not use host networking')
        self.assertNotRegex(text, r'(?m)^\s+-\s*["\']?(\d{1,3}\.){3}\d{1,3}:\d+:8001')

    def test_no_compose_override_or_extra_compose_file_exists(self):
        extra = [p.name for p in REPO.glob('docker-compose*.y*ml') if p.name != 'docker-compose.yml'] + \
                [p.name for p in REPO.glob('compose*.y*ml')]
        self.assertEqual(extra, [], 'an override file could publish a port: review it and extend this test')
        text = (REPO / 'docker-compose.yml').read_text(encoding='utf-8')
        live = '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#'))
        self.assertNotRegex(live, r'network_mode\s*:\s*["\']?(host|service:fastapi)')
        self.assertNotRegex(live, r'(?m)^\s+extends\s*:')

    def test_no_other_service_publishes_8001(self):
        text = (REPO / 'docker-compose.yml').read_text(encoding='utf-8')
        live = '\n'.join(l for l in text.splitlines() if not l.lstrip().startswith('#'))
        self.assertNotRegex(live, r':8001["\']?\s*$', 'no service may publish port 8001')

    def test_the_reverse_proxy_example_never_proxies_to_fastapi(self):
        for path in (REPO / 'deploy').rglob('*'):
            if path.is_file():
                text = path.read_text(encoding='utf-8', errors='ignore')
                for forbidden in ('8001', 'fastapi', '/llm', 'llm/complete'):
                    self.assertNotIn(forbidden, text, f'{path.name} must not reference {forbidden}')

    def test_django_is_the_only_caller_it_names_fastapi_by_internal_host(self):
        # Django reaches FastAPI by the compose service name only (never a public URL).
        for rel in ('django_core/dashboard/views.py', 'django_core/students/views.py'):
            text = (REPO / rel).read_text(encoding='utf-8')
            for url in re.findall(r'https?://[^"\']*8001[^"\']*', text):
                self.assertTrue(url.startswith('http://fastapi:8001/'), url)


if __name__ == '__main__':
    unittest.main()
