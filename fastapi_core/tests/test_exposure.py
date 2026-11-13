"""The FastAPI service (incl. /llm/complete/) must not be reachable from browsers or the public network (owner 2026-11-02):
no published port in docker-compose.yml, no reverse-proxy rule to it, and a service token on every route. Static checks over the
repository files; they need only the standard library (the repository root is the parent of fastapi_core/)."""
import ast
import fnmatch
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SERVICE_ROOT = REPO / 'fastapi_core'


def dockerignored(path, patterns):
    """True when ``path`` (under fastapi_core/) matches a ``.dockerignore`` entry.

    Only the entries this repository uses are handled: a bare name (``.env``), a glob (``*.pyc``) and a directory
    (``venv/``, matched against the first path component)."""
    rel = path.relative_to(SERVICE_ROOT).as_posix()
    for pattern in patterns:
        name = pattern.strip().strip('/')
        if not name:
            continue
        if fnmatch.fnmatch(rel, name) or rel.split('/')[0] == name:
            return True
    return False


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


@unittest.skipUnless(SERVICE_ROOT.exists(), 'fastapi_core/ not visible from this location (image run)')
class SingleApplicationTests(unittest.TestCase):
    """M-4 (T7): exactly one FastAPI application may ship in the image, and it must be the authenticated one.

    ``main_HuggingFace.py`` (untracked, local) is a second, entirely unauthenticated application with an unscoped RAG
    backend: no route declares a dependency, and its backend has no ``school_id``. It is not in git but the Dockerfile
    ends with ``COPY . .``, so it *would* ship. These checks read the build context as ``.dockerignore`` defines it."""

    NAMES = ('main_HuggingFace.py', 'rag_service_HuggingFace_Models.py')

    def ignore_patterns(self):
        return (SERVICE_ROOT / '.dockerignore').read_text(encoding='utf-8').splitlines()

    def applications(self):
        found = {}
        for path in sorted(SERVICE_ROOT.glob('*.py')):
            if dockerignored(path, self.ignore_patterns()):
                continue
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'FastAPI':
                    found.setdefault(path.name, []).append(node.lineno)
        return found

    def test_only_one_fastapi_application_is_in_the_build_context(self):
        found = self.applications()
        self.assertEqual(sorted(found), ['main.py'], f'a second FastAPI application would ship: {found}')

    def test_the_huggingface_variants_are_excluded_from_the_build_context(self):
        patterns = self.ignore_patterns()
        for name in self.NAMES:
            path = SERVICE_ROOT / name
            if path.exists():
                self.assertTrue(dockerignored(path, patterns), f'{name} is still copied into the image')


if __name__ == '__main__':
    unittest.main()
