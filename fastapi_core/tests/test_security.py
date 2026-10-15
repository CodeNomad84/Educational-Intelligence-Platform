"""Phase 1 tests for the FastAPI service: import sanity, authentication, role authorization,
and "no schema creation at startup".

Run from fastapi_core/:   python -m unittest discover -s tests -t . -v

Test doubles: the heavy ML/DB modules (torch, numpy, joblib, rag_service, train_nn_model) are
replaced by tiny fakes declared below so the tests are deterministic and need no GPU, Ollama or
PostgreSQL. This verifies routing/auth/validation wiring ONLY -- not model loading or RAG.
All data is synthetic; the signing secret is generated per run.
"""
import logging
import os
import re
import secrets
import sys
import time
import types
import unittest
from pathlib import Path
from unittest import mock

import jwt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SECRET = secrets.token_urlsafe(48)
ISS, AUD = 'school-django', 'school-fastapi'
ADMIN_ROLE = 'SchoolAdmin'  # the one place this suite names the role (ADR-0010 rename)


def _fake_modules():
    calls = []

    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    torch = types.ModuleType('torch')
    torch.no_grad = lambda: _Ctx()
    torch.load = lambda *a, **k: {}
    torch.device = lambda x: x
    torch.float32 = 'float32'
    torch.tensor = lambda x, dtype=None: x

    numpy = types.ModuleType('numpy')
    numpy.array = lambda x: x

    class _Scaler:
        mean_ = [0.0] * 8
        def transform(self, x): return x

    joblib = types.ModuleType('joblib')
    joblib.load = lambda p: _Scaler()

    class _Out:
        def item(self): return 0.7

    class StudentRiskModel:
        def __init__(self, *a, **k): pass
        def load_state_dict(self, *a, **k): pass
        def eval(self): pass
        def __call__(self, x): return _Out()

    train = types.ModuleType('train_nn_model')
    train.StudentRiskModel = StudentRiskModel

    rag = types.ModuleType('rag_service')
    rag.calls = calls
    rag.documents_table_exists = lambda: calls.append(('documents_table_exists',)) or True
    rag.chat = lambda q: calls.append(('chat', q)) or {'answer': 'ok', 'sources': []}
    rag.add_document = lambda *a, **k: calls.append(('add_document', a, k))
    rag.add_documents_batch = lambda docs: calls.append(('add_documents_batch', docs))
    rag.get_all_documents = lambda: calls.append(('get_all_documents',)) or []
    rag.search_documents = lambda q, k=3: calls.append(('search_documents', q, k)) or []
    rag.delete_document_by_parent_id = lambda pid: calls.append(('delete_parent', pid)) or True
    rag.delete_document = lambda i: calls.append(('delete_document', i)) or True
    return {'torch': torch, 'numpy': numpy, 'joblib': joblib, 'train_nn_model': train, 'rag_service': rag}


_saved = {k: sys.modules.get(k) for k in ('torch', 'numpy', 'joblib', 'train_nn_model', 'rag_service', 'main', 'auth')}
FAKES = _fake_modules()
sys.modules.update(FAKES)
sys.modules.pop('main', None)
os.environ['SERVICE_JWT_SECRET'] = SECRET
import main  # noqa: E402  (the real main.py, with fakes for heavy modules)
import auth  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def setUpModule():
    logging.disable(logging.CRITICAL)  # main.py enables DEBUG logging at import; keep test output readable


def tearDownModule():
    logging.disable(logging.NOTSET)
    for name, mod in _saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod


def token(_roles, **over):
    now = int(time.time())
    claims = {'iss': ISS, 'aud': AUD, 'sub': '1', 'roles': _roles, 'iat': now, 'exp': now + 60}
    claims.update(over)
    claims = {k: v for k, v in claims.items() if v is not None}  # a None override removes the claim
    return jwt.encode(claims, SECRET, algorithm='HS256')


def bearer(_roles, **over):
    return {'Authorization': f'Bearer {token(_roles, **over)}'}


FEATURES = {'grade': 8, 'attendance_rate': 0.9, 'avg_completion_rate': 0.8, 'avg_exam_score': 15.0,
            'total_absences': 1, 'total_lates': 0, 'total_communications': 3, 'completed_homework': 12}

PUBLIC_PATHS = {'/', '/docs', '/redoc', '/openapi.json', '/docs/oauth2-redirect'}
MUTATIONS = [
    ('post', '/documents/', {'json': {'title': 't', 'content': 'c'}}),
    ('post', '/upload-document/', {'files': {'file': ('x.txt', b'x', 'text/plain')}}),
    ('delete', '/documents/1', {}),
    ('delete', '/documents/parent/abc', {}),
]
STAFF_READS = [
    ('post', '/predict/', {'json': FEATURES}),
    ('post', '/api/v1/predict/', {'json': FEATURES}),
    ('post', '/chat/', {'json': {'query': 'q'}}),
    ('get', '/documents/list/', {}),
    ('get', '/documents/search/', {'params': {'query': 'q'}}),
]
# Phase 1 policy: predict = Admin/Teacher; document list = Admin only; chat, search and ingestion
# (POST /documents/, /upload-document/) are disabled for EVERY role; delete = Admin only.
PREDICT = [r for r in STAFF_READS if 'predict' in r[1]]
DISABLED = [r for r in STAFF_READS if r[1] in ('/chat/', '/documents/search/')] + MUTATIONS[:2]
ADMIN_ONLY = [('get', '/documents/list/', {})] + MUTATIONS[2:]
OTHER_ROLES = (['Parent'], [], ['Counselor'], ['Mentor'], ['Manager'], ['Student'])


class BaseCase(unittest.TestCase):
    def setUp(self):
        FAKES['rag_service'].calls.clear()
        self.client = TestClient(main.app)


class BootTests(BaseCase):
    def test_main_imports_and_health_is_public(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)

    def test_every_non_public_route_requires_authentication(self):
        def uses_verify_jwt(dep):
            return any(d.call is auth.verify_jwt or uses_verify_jwt(d) for d in dep.dependencies)

        unprotected = [
            r.path for r in main.app.routes
            if getattr(r, 'dependant', None) is not None and r.path not in PUBLIC_PATHS
            and not uses_verify_jwt(r.dependant)
        ]
        self.assertEqual(unprotected, [])

    def test_startup_does_no_schema_work(self):
        with TestClient(main.app):
            pass
        names = [c[0] for c in FAKES['rag_service'].calls]
        self.assertIn('documents_table_exists', names)
        self.assertFalse(hasattr(FAKES['rag_service'], 'create_documents_table'))

    def test_no_schema_ddl_in_service_source(self):
        pattern = re.compile(r'CREATE\s+(TABLE|EXTENSION|INDEX)|DROP\s+TABLE|ALTER\s+TABLE|create_all', re.I)
        for name in ('main.py', 'rag_service.py', 'auth.py'):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertIsNone(pattern.search(text), f'schema DDL found in {name}')


class AuthenticationTests(BaseCase):
    def test_anonymous_denied_on_all_protected_routes(self):
        for method, path, kw in MUTATIONS + STAFF_READS:
            resp = getattr(self.client, method)(path, **kw)
            self.assertEqual(resp.status_code, 401, f'{method} {path}')
        self.assertEqual(FAKES['rag_service'].calls, [])

    def test_anonymous_with_malformed_body_is_still_401(self):
        resp = self.client.post('/documents/', json={'bad': 1})
        self.assertEqual(resp.status_code, 401)

    def test_bad_tokens_denied(self):
        cases = {
            'expired': bearer([ADMIN_ROLE], exp=int(time.time()) - 5),
            'wrong audience': bearer([ADMIN_ROLE], aud='other'),
            'wrong issuer': bearer([ADMIN_ROLE], iss='other'),
            'no roles claim': bearer([ADMIN_ROLE], roles=None),
            'roles not a list': bearer([ADMIN_ROLE], roles=ADMIN_ROLE),
            'garbage': {'Authorization': 'Bearer not-a-jwt'},
            'wrong scheme': {'Authorization': 'Basic abc'},
        }
        for label, headers in cases.items():
            resp = self.client.delete('/documents/1', headers=headers)
            self.assertEqual(resp.status_code, 401, label)
        forged = jwt.encode({'iss': ISS, 'aud': AUD, 'sub': '1', 'roles': [ADMIN_ROLE],
                             'exp': int(time.time()) + 60}, secrets.token_urlsafe(48), algorithm='HS256')
        self.assertEqual(self.client.delete('/documents/1', headers={'Authorization': f'Bearer {forged}'}).status_code, 401)
        self.assertEqual(FAKES['rag_service'].calls, [])

    def test_unsigned_token_denied(self):
        none_token = jwt.encode({'iss': ISS, 'aud': AUD, 'sub': '1', 'roles': [ADMIN_ROLE],
                                 'exp': int(time.time()) + 60}, None, algorithm='none')
        self.assertEqual(self.client.delete('/documents/1', headers={'Authorization': f'Bearer {none_token}'}).status_code, 401)

    def test_fails_closed_when_secret_missing_or_short(self):
        headers = bearer([ADMIN_ROLE])
        for value in ('', 'short'):
            with mock.patch.dict(os.environ, {'SERVICE_JWT_SECRET': value}):
                self.assertEqual(self.client.delete('/documents/1', headers=headers).status_code, 503)

    def test_fails_closed_for_placeholder_or_low_entropy_secret(self):
        for value in ('django-insecure-' + 'x' * 40, 'changeme' * 6, 'a' * 64, 'your-secret-key-' + 'Qz9' * 10):
            with mock.patch.dict(os.environ, {'SERVICE_JWT_SECRET': value}):
                # even a correctly signed token is refused when the configured secret is weak
                forged = jwt.encode({'iss': ISS, 'aud': AUD, 'sub': '1', 'roles': [ADMIN_ROLE],
                                     'exp': int(time.time()) + 60}, value, algorithm='HS256')
                resp = self.client.delete('/documents/1', headers={'Authorization': f'Bearer {forged}'})
                self.assertEqual(resp.status_code, 503, value[:8])

    def test_startup_validates_service_secret(self):
        good = secrets.token_urlsafe(48)
        with mock.patch.dict(os.environ, {'SERVICE_JWT_SECRET': good}):
            with TestClient(main.app):  # valid secret: startup succeeds
                pass
        bad = {'missing': None, 'empty': '', 'short': 'short', 'placeholder': 'changeme' * 6,
               'django-insecure': 'django-insecure-' + 'x' * 40, 'low-entropy': 'a' * 64}
        for label, value in bad.items():
            env = {} if value is None else {'SERVICE_JWT_SECRET': value}
            with mock.patch.dict(os.environ, env):
                if value is None:
                    os.environ.pop('SERVICE_JWT_SECRET', None)
                with self.assertRaises(RuntimeError, msg=label) as ctx:
                    with TestClient(main.app):
                        pass
                self.assertIn('SERVICE_JWT_SECRET', str(ctx.exception))
                if value and len(value) >= 16:  # ('short' is a substring of the word 'shorter')
                    self.assertNotIn(value, str(ctx.exception), label)  # the value is never reported

    def test_django_user_token_is_not_a_service_token(self):
        # Cross-token: a Django (simplejwt-style) access token, different key, no iss/aud/roles.
        user_token = jwt.encode({'token_type': 'access', 'user_id': 1, 'jti': 'x',
                                 'exp': int(time.time()) + 60}, secrets.token_urlsafe(48), algorithm='HS256')
        for method, path, kw in MUTATIONS + STAFF_READS:
            resp = getattr(self.client, method)(path, headers={'Authorization': f'Bearer {user_token}'}, **kw)
            self.assertEqual(resp.status_code, 401, f'{method} {path}')

    def test_wrong_algorithm_denied(self):
        for alg in ('HS384', 'HS512'):
            t = jwt.encode({'iss': ISS, 'aud': AUD, 'sub': '1', 'roles': [ADMIN_ROLE],
                            'exp': int(time.time()) + 60}, SECRET, algorithm=alg)
            self.assertEqual(self.client.delete('/documents/1', headers={'Authorization': f'Bearer {t}'}).status_code, 401, alg)


class AuthorizationTests(BaseCase):
    def test_non_admin_roles_denied_on_mutations(self):
        for roles in (['Teacher'],) + OTHER_ROLES:
            for method, path, kw in MUTATIONS:
                resp = getattr(self.client, method)(path, headers=bearer(roles), **kw)
                self.assertEqual(resp.status_code, 403, f'{roles} {method} {path}')
        self.assertEqual(FAKES['rag_service'].calls, [])

    def test_parent_and_unmapped_roles_denied_on_every_protected_route(self):
        for roles in OTHER_ROLES:
            for method, path, kw in STAFF_READS + MUTATIONS:
                resp = getattr(self.client, method)(path, headers=bearer(roles), **kw)
                self.assertEqual(resp.status_code, 403, f'{roles} {method} {path}')
        self.assertEqual(FAKES['rag_service'].calls, [])

    def test_predict_is_admin_only(self):
        for method, path, kw in PREDICT:
            resp = getattr(self.client, method)(path, headers=bearer([ADMIN_ROLE]), **kw)
            self.assertEqual(resp.status_code, 200, f'Admin {method} {path}')
            for roles in (['Teacher'],) + OTHER_ROLES:
                resp = getattr(self.client, method)(path, headers=bearer(roles), **kw)
                self.assertEqual(resp.status_code, 403, f'{roles} {method} {path}')

    def test_teacher_cannot_get_a_prediction_for_an_arbitrary_student(self):
        # /predict/ has no student lookup: it scores caller-supplied numbers. A Teacher must still not
        # be able to use it (e.g. with another student's figures or a student_id) until teacher->student
        # assignment exists (S-04).
        body = dict(FEATURES, student_id=999)
        for path in ('/predict/', '/api/v1/predict/'):
            resp = self.client.post(path, headers=bearer(['Teacher']), json=body)
            self.assertEqual(resp.status_code, 403, path)
            self.assertNotIn('risk_probability', resp.text)

    def test_chat_search_and_ingestion_disabled_for_every_role(self):
        for roles in ([ADMIN_ROLE], ['Teacher'], [ADMIN_ROLE, 'Teacher']) + OTHER_ROLES:
            for method, path, kw in DISABLED:
                resp = getattr(self.client, method)(path, headers=bearer(roles), **kw)
                self.assertEqual(resp.status_code, 403, f'{roles} {method} {path}')
        self.assertEqual(FAKES['rag_service'].calls, [])  # nothing reached the RAG layer

    def test_document_list_and_delete_are_admin_only(self):
        h = bearer([ADMIN_ROLE])
        self.assertEqual(self.client.get('/documents/list/', headers=h).status_code, 200)
        self.assertEqual(self.client.delete('/documents/parent/abc', headers=h).status_code, 200)
        self.assertEqual(self.client.delete('/documents/1', headers=h).status_code, 200)
        self.assertEqual(self.client.get('/documents/list/', headers=bearer(['Teacher'])).status_code, 403)

    def test_delete_missing_document_is_404_not_500(self):
        h = bearer([ADMIN_ROLE])
        with mock.patch.object(main, 'delete_document', lambda i: False), \
                mock.patch.object(main, 'delete_document_by_parent_id', lambda p: False):
            self.assertEqual(self.client.delete('/documents/999999', headers=h).status_code, 404)
            self.assertEqual(self.client.delete('/documents/parent/none', headers=h).status_code, 404)

    def test_delete_internal_error_is_500_without_leaking_details(self):
        def boom(_):
            raise RuntimeError('db-host-secret-detail')
        h = bearer([ADMIN_ROLE])
        with mock.patch.object(main, 'delete_document', boom), mock.patch.object(main, 'delete_document_by_parent_id', boom):
            for path in ('/documents/1', '/documents/parent/x'):
                resp = self.client.delete(path, headers=h)
                self.assertEqual(resp.status_code, 500, path)
                self.assertNotIn('db-host-secret-detail', resp.text)

    def test_admin_malformed_requests_fail_safely(self):
        h = bearer([ADMIN_ROLE])
        self.assertEqual(self.client.delete('/documents/not-an-int', headers=h).status_code, 422)
        # Disabled routes refuse before touching the body, even when it is malformed.
        self.assertEqual(self.client.post('/documents/', headers=h, json={'title': 't'}).status_code, 403)
        self.assertEqual(self.client.post('/upload-document/', headers=h).status_code, 403)
        self.assertEqual(self.client.post('/predict/', headers=h, json={'grade': 'x'}).status_code, 422)


class EmbeddingFailureTests(unittest.TestCase):
    """The REAL rag_service.py (only ollama/psycopg2/pgvector are faked): an embedding failure must
    raise, never fall back to a zero vector, and nothing may be written or searched with one."""

    def setUp(self):
        import importlib.util
        self.db_calls = []
        outer = self

        class _Client:
            def __init__(self, *a, **k): pass
            def embeddings(self, **k): raise RuntimeError('model not found (secret-internal-detail)')

        ollama = types.ModuleType('ollama'); ollama.Client = _Client
        psycopg2 = types.ModuleType('psycopg2')
        psycopg2.connect = lambda **k: outer.db_calls.append('connect') or (_ for _ in ()).throw(AssertionError('DB used'))
        pg = types.ModuleType('pgvector'); pgp = types.ModuleType('pgvector.psycopg2')
        pgp.register_vector = lambda c: None
        self._saved = {k: sys.modules.get(k) for k in ('ollama', 'psycopg2', 'pgvector', 'pgvector.psycopg2')}
        sys.modules.update({'ollama': ollama, 'psycopg2': psycopg2, 'pgvector': pg, 'pgvector.psycopg2': pgp})
        spec = importlib.util.spec_from_file_location('rag_service_real', ROOT / 'rag_service.py')
        self.rag = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.rag)  # the import-time dimension probe fails, as it does without a model

    def tearDown(self):
        for k, v in self._saved.items():
            sys.modules.pop(k, None) if v is None else sys.modules.__setitem__(k, v)

    def test_get_embedding_raises_generic_error(self):
        with self.assertRaises(self.rag.EmbeddingError) as ctx:
            self.rag.get_embedding('x')
        self.assertNotIn('secret-internal-detail', str(ctx.exception))

    def test_no_write_or_search_with_a_placeholder_vector(self):
        for call in (lambda: self.rag.add_document('t', 'c'),
                     lambda: self.rag.add_documents_batch([('t', 'c', {}, 'p')]),
                     lambda: self.rag.search_documents('q')):
            with self.assertRaises(self.rag.EmbeddingError):
                call()
        self.assertEqual(self.db_calls, [])  # the database was never reached



class NoRoleLiteralTests(unittest.TestCase):
    """The old group name must not survive in service code; roles come from auth.ADMIN."""

    def test_no_admin_literal_outside_tests(self):
        pattern = re.compile(r"""['"]Admin['"]""")
        offenders = [
            str(path.relative_to(ROOT))
            for path in ROOT.rglob('*.py')
            if 'tests' not in path.relative_to(ROOT).parts and '.venv' not in path.parts
            and pattern.search(path.read_text(encoding='utf-8'))
        ]
        self.assertEqual(offenders, [])

    def test_admin_constant_value(self):
        self.assertEqual(auth.ADMIN, ADMIN_ROLE)


if __name__ == '__main__':
    unittest.main()
