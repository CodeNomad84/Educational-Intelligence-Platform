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


@unittest.skipUnless((REPO / 'docker-compose.yml').exists(), 'repository root not available')
class FrontendExposureTests(unittest.TestCase):
    """ADR-0015 (change 0042): the two SSR frontends are reachable **only** through the loopback gateway.

    A published frontend port, a frontend on the database network, or a gateway route to FastAPI/database would quietly
    undo the topology; these checks read the repository files so such a regression fails here instead of in production.
    """

    FRONTENDS = ('frontend_men', 'frontend_women')

    def compose(self):
        return (REPO / 'docker-compose.yml').read_text(encoding='utf-8')

    def block(self, name):
        block = service_block(self.compose(), name)
        self.assertIsNotNone(block, f'{name} service not found in docker-compose.yml')
        return '\n'.join(block)

    def test_the_frontends_publish_no_port(self):
        for name in self.FRONTENDS:
            self.assertNotRegex(self.block(name), r'(?m)^\s+ports\s*:', f'{name} must not publish a port')

    def test_the_gateway_listens_on_loopback_only(self):
        text = self.block('gateway')
        self.assertIn('"127.0.0.1:${FRONTEND_HTTP_PORT:-8080}:80"', text)
        self.assertNotRegex(text, r'(?m)^\s+-\s*["\']?0\.0\.0\.0:', 'the gateway must stay on loopback')

    def test_the_database_never_shares_a_network_with_a_frontend(self):
        for name in self.FRONTENDS:
            self.assertNotIn('- backend', self.block(name), f'{name} must not join the backend network')
        gateway = self.block('gateway')
        self.assertIn('- edge', gateway)
        self.assertNotIn('- backend', gateway)
        postgres = self.block('postgres')
        self.assertIn('- backend', postgres)
        self.assertNotIn('- edge', postgres, 'the database must not be reachable from the edge network')
        django = self.block('django')
        self.assertIn('- edge', django)
        self.assertIn('- backend', django)

    def test_the_gateway_never_routes_to_fastapi_or_the_datastores(self):
        for path in sorted((REPO / 'deploy' / 'nginx').glob('*.conf')):
            text = path.read_text(encoding='utf-8')
            for forbidden in ('fastapi', '8001', 'postgres', 'redis', 'minio', 'ollama'):
                self.assertNotIn(forbidden, text, f'{path.name} must not reference {forbidden}')

    def test_the_frontend_images_run_the_node_server_not_a_workers_bundle(self):
        for name, directory in zip(self.FRONTENDS, ('frontend-men', 'frontend-women')):
            dockerfile = (REPO / directory / 'Dockerfile').read_text(encoding='utf-8')
            self.assertIn('.output/server/index.mjs', dockerfile, f'{name} must start the nitro node-server output')
            self.assertIn('bun install --frozen-lockfile', dockerfile, f'{name} must install from the lockfile')
            self.assertNotIn('--no-frozen-lockfile', dockerfile)
            config = (REPO / directory / 'vite.config.ts').read_text(encoding='utf-8')
            self.assertIn('preset: "node-server"', config, f'{name} must build a node server, not a Workers bundle')


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
