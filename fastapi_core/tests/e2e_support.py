"""Shared doubles for the FastAPI end-to-end audit (used by ``tests/test_e2e_llm_flow.py`` only).

NOT a test module (no ``test_`` prefix, so ``unittest discover`` ignores it).

* ``install_fakes()`` replaces the heavy modules main.py imports (torch, numpy, joblib,
  train_nn_model, rag_service) so the real ``main`` can be imported without a GPU, Ollama or
  PostgreSQL -- the same trick ``test_security.py`` uses.
* ``StubProvider`` is a REAL HTTP server on 127.0.0.1 (OpenAI-compatible
  ``POST /v1/chat/completions``). The audit needs the real transport: ``llm_adapter`` builds its own
  urllib opener (no proxies, no redirects) and enforces the timeout, so a mocked transport would
  prove nothing about the wiring that ships.
* ``make_token`` / ``bearer`` mint service tokens with the claims Django signs
  (config/service_auth.py): iss/aud/sub/roles/schools, optional ``scope: ai``.

All data is synthetic; the signing secret is generated per run.
"""
import json
import secrets
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ISS, AUD = 'school-django', 'school-fastapi'
SECRET = secrets.token_urlsafe(48)


def install_fakes():
    """Install the five fake modules main.py needs. Returns the ``calls`` list rag_service records."""
    calls = []

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Out:
        def item(self):
            return 0.7

    class StudentRiskModel:
        def __init__(self, *a, **k):
            pass

        def load_state_dict(self, *a, **k):
            pass

        def eval(self):
            pass

        def __call__(self, x):
            return _Out()

    class _Scaler:
        mean_ = [0.0] * 8

        def transform(self, x):
            return x

    torch = types.ModuleType('torch')
    torch.no_grad = lambda: _Ctx()
    torch.load = lambda *a, **k: {}
    torch.device = lambda x: x
    torch.float32 = 'float32'
    torch.tensor = lambda x, dtype=None: x

    numpy = types.ModuleType('numpy')
    numpy.array = lambda x: x

    joblib = types.ModuleType('joblib')
    joblib.load = lambda p: _Scaler()

    train = types.ModuleType('train_nn_model')
    train.StudentRiskModel = StudentRiskModel

    rag = types.ModuleType('rag_service')
    rag.calls = calls
    rag.documents_table_exists = lambda: calls.append(('documents_table_exists',)) or True
    rag.chat = lambda q, schools=(): calls.append(('chat', q)) or {'answer': 'ok', 'sources': []}
    rag.add_document = lambda *a, **k: calls.append(('add_document', a, k))
    rag.add_documents_batch = lambda docs, school_id=None: calls.append(('add_documents_batch', len(docs), school_id))
    rag.get_all_documents = lambda schools=(): calls.append(('get_all_documents', list(schools))) or []
    rag.search_documents = lambda q, k=3, schools=(): calls.append(('search_documents', q)) or []
    rag.delete_document_by_parent_id = lambda pid, schools=(): calls.append(('delete_parent', pid)) or True
    rag.delete_document = lambda i, schools=(): calls.append(('delete_document', i)) or True

    import sys
    sys.modules.update({'torch': torch, 'numpy': numpy, 'joblib': joblib,
                        'train_nn_model': train, 'rag_service': rag})
    return calls


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):        # keep the test output readable
        pass

    def do_POST(self):
        state = self.server.state
        length = int(self.headers.get('Content-Length') or 0)
        raw = self.rfile.read(length)
        state['calls'].append({'path': self.path, 'headers': dict(self.headers), 'body': raw})
        if state['delay']:
            time.sleep(state['delay'])
        if state['mode'] == 'http500':
            self.send_response(500)
            self.send_header('Content-Length', '0')
            self.end_headers()
            return
        if state['mode'] == 'garbage':
            body = b'this is not json'
        elif state['mode'] == 'noselect':
            body = b'{"choices": []}'
        else:
            body = json.dumps({'model': 'stub-1',
                               'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': state['answer']}}],
                               'usage': {'prompt_tokens': 12, 'completion_tokens': 7}}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class StubProvider:
    """A real OpenAI-compatible endpoint. ``mode``: ok | http500 | garbage | noselect. ``delay`` in seconds."""

    def __init__(self):
        self.server = _Server(('127.0.0.1', 0), _Handler)
        self.server.state = {'mode': 'ok', 'answer': 'پاسخ آزمایشی [1]', 'calls': [], 'delay': 0}
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self):
        return self.server.server_address[1]

    @property
    def base_url(self):
        return f'http://127.0.0.1:{self.port}/v1'

    @property
    def state(self):
        return self.server.state

    @property
    def calls(self):
        return self.server.state['calls']

    def configure(self, mode='ok', answer='پاسخ آزمایشی [1]', delay=0):
        self.server.state.update(mode=mode, answer=answer, delay=delay)
        return self

    def reset(self):
        self.server.state['calls'].clear()
        self.configure()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def make_token(roles, secret=None, **over):
    """A service token exactly as config/service_auth.py signs it (schools claim, optional scope)."""
    import jwt
    now = int(time.time())
    claims = {'iss': ISS, 'aud': AUD, 'sub': '1', 'roles': list(roles), 'schools': [1], 'iat': now, 'exp': now + 60}
    claims.update(over)
    claims = {k: v for k, v in claims.items() if v is not None}      # a None override removes the claim
    return jwt.encode(claims, secret or SECRET, algorithm='HS256')


def bearer(roles, secret=None, **over):
    return {'Authorization': f'Bearer {make_token(roles, secret, **over)}'}

