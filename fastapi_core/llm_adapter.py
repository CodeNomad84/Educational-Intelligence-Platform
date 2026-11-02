"""P7 provider-agnostic LLM adapter (decisions 56-57). ONE small client for the OpenAI-compatible chat API (``POST {base_url}/chat/completions``),
which is what ChatGPT/OpenAI, DeepSeek, Azure-style gateways, resellers (e.g. GapGPT), and local servers (Ollama ``/v1``, vLLM, LM Studio)
speak. No vendor SDK, no new dependency (stdlib ``urllib``). ChatGPT is a CONFIGURATION example, never a code path: any provider that
speaks this API is added by configuration only.

Two provider classes (owner OW-6): ``external`` (hosted API, data leaves the platform) and ``local`` (runs on the platform's / school's own
server). BOTH ARE OFF unless an operator configures a provider AND maps a school to it. Keys come only from environment variables named in
the config (never stored, logged, returned or put in an error). Outbound text for the ``external`` class passes a PII filter and a purpose
whitelist (non-personal content only; hard rule: no student PII to external LLMs); counseling data is never a purpose for either class.

Configuration (environment, operator-owned; nothing is read from a request):
  LLM_PROVIDERS   JSON {"<name>": {"class": "external"|"local", "base_url": "...", "model": "...", "api_key_env": "ENV_NAME",
                  "timeout": 30, "max_tokens": 600}}
  LLM_SCHOOL_MAP  JSON {"<school id>": "<provider name>"}      (a school absent from the map has NO AI)
  LLM_DAILY_CAP   integer, per-school calls per UTC day (default 200; 0 = block all)
"""
import json
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import urlsplit

logger = logging.getLogger("llm")

EXTERNAL, LOCAL = "external", "local"
LABEL_FA = "هوش مصنوعی؛ فقط پیشنهادی و ممکن است اشتباه باشد. تصمیم با انسان است."
PURPOSES_EXTERNAL = frozenset({"policy_document", "curriculum_text", "question_draft", "pedagogy"})
PURPOSES_LOCAL = PURPOSES_EXTERNAL | {"school_data_summary"}      # data the requesting user may already see (ACL is applied BEFORE this call)
ROLES = ("system", "user", "assistant")
MAX_MESSAGES, MAX_CHARS = 20, 8000
_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class LLMError(Exception):
    """A refusal or failure with a fixed ``code`` (never carries a key, a URL or provider text)."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class Provider:
    __slots__ = ("name", "kind", "base_url", "model", "api_key_env", "timeout", "max_tokens")

    def __init__(self, name, kind, base_url, model, api_key_env, timeout, max_tokens):
        self.name, self.kind, self.base_url, self.model = name, kind, base_url, model
        self.api_key_env, self.timeout, self.max_tokens = api_key_env, timeout, max_tokens

    def __repr__(self):       # no URL, no key name
        return f"<Provider {self.name} {self.kind}>"


def _parse_provider(name, raw):
    if not isinstance(raw, dict) or raw.get("class") not in (EXTERNAL, LOCAL):
        raise LLMError("bad_config")
    url = urlsplit(str(raw.get("base_url", "")))
    ok_scheme = url.scheme == "https" or (raw["class"] == LOCAL and url.scheme == "http")      # external must be TLS
    if not ok_scheme or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise LLMError("bad_config")
    model = raw.get("model")
    if not isinstance(model, str) or not model.strip() or len(model) > 100:
        raise LLMError("bad_config")
    env_name = raw.get("api_key_env", "")
    if env_name and not _ENV_NAME.fullmatch(str(env_name)):
        raise LLMError("bad_config")
    if raw["class"] == EXTERNAL and not env_name:
        raise LLMError("bad_config")
    timeout, max_tokens = raw.get("timeout", 30), raw.get("max_tokens", 600)
    if not (isinstance(timeout, int) and 1 <= timeout <= 120 and isinstance(max_tokens, int) and 1 <= max_tokens <= 4000):
        raise LLMError("bad_config")
    return Provider(str(name), raw["class"], f"{url.scheme}://{url.netloc}{url.path.rstrip('/')}", model.strip(), str(env_name), timeout, max_tokens)


def load_providers(env=None):
    env = os.environ if env is None else env
    text = env.get("LLM_PROVIDERS", "")
    if not text.strip():
        return {}
    try:
        raw = json.loads(text)
    except ValueError:
        raise LLMError("bad_config") from None
    if not isinstance(raw, dict):
        raise LLMError("bad_config")
    return {name: _parse_provider(name, spec) for name, spec in raw.items()}


def provider_for_school(school_id, env=None):
    """The provider configured for ``school_id``, or ``None`` (AI OFF). A mapping to an unknown provider is a configuration error."""
    env = os.environ if env is None else env
    text = env.get("LLM_SCHOOL_MAP", "")
    if not text.strip():
        return None
    try:
        mapping = json.loads(text)
    except ValueError:
        raise LLMError("bad_config") from None
    name = mapping.get(str(school_id)) if isinstance(mapping, dict) else None
    if name is None:
        return None
    providers = load_providers(env)
    if name not in providers:
        raise LLMError("bad_config")
    return providers[name]


# ---- outbound filter (external class) ----
_NATIONAL_ID = re.compile(r"(?<!\d)\d{10}(?!\d)")
_PHONE = re.compile(r"(?<!\d)(?:\+?98|0)?9\d{9}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def check_outbound(text, roster_names=()):
    """Refuse text that looks like personal data: national id, mobile number, e-mail, or any name of the school's roster (>= 3 chars)."""
    flat = text.translate(_DIGITS)
    squeezed = re.sub(r"[\s\-_.،,/]", "", flat)
    if _NATIONAL_ID.search(flat) or _NATIONAL_ID.search(squeezed) or _PHONE.search(squeezed) or _EMAIL.search(flat):
        raise LLMError("pii_refused")
    low = text.casefold()
    for name in roster_names:
        if len(name) >= 3 and name.casefold() in low:
            raise LLMError("pii_refused")


# ---- usage cap (per school per UTC day, in memory: defence in depth; the licensed per-school caps live in Django) ----
_USAGE = {}


def _take_slot(school_id, env):
    try:
        cap = int(env.get("LLM_DAILY_CAP", "200"))
    except ValueError:
        raise LLMError("bad_config") from None
    key = (school_id, datetime.now(timezone.utc).date())
    for old in [k for k in _USAGE if k[1] != key[1]]:
        del _USAGE[old]
    if _USAGE.get(key, 0) >= cap:
        raise LLMError("cap_reached")
    _USAGE[key] = _USAGE.get(key, 0) + 1


def reset_usage():
    _USAGE.clear()


def _urllib_transport(url, headers, body, timeout):
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:      # operator-configured URL only, never a request value
            return response.status, response.read(1_000_000)
    except urllib.error.HTTPError as exc:
        return exc.code, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        raise LLMError("upstream_error") from None


def _validate_messages(messages):
    if not isinstance(messages, list) or not 1 <= len(messages) <= MAX_MESSAGES:
        raise LLMError("bad_request")
    total = 0
    clean = []
    for m in messages:
        if not isinstance(m, dict) or set(m) != {"role", "content"} or m["role"] not in ROLES or not isinstance(m["content"], str):
            raise LLMError("bad_request")
        total += len(m["content"])
        clean.append({"role": m["role"], "content": m["content"]})
    if total == 0 or total > MAX_CHARS:
        raise LLMError("bad_request")
    return clean


def complete(provider, messages, purpose, *, school_id, roster_names=(), env=None, transport=None):
    """One chat completion. Returns ``{text, label, provider_class, model, usage}``; raises ``LLMError`` with a fixed code
    (bad_request, purpose_refused, pii_refused, not_configured, cap_reached, upstream_error)."""
    env = os.environ if env is None else env
    allowed = PURPOSES_EXTERNAL if provider.kind == EXTERNAL else PURPOSES_LOCAL
    if purpose not in allowed:
        raise LLMError("purpose_refused")
    messages = _validate_messages(messages)
    if provider.kind == EXTERNAL:
        for m in messages:
            check_outbound(m["content"], roster_names)
    key = env.get(provider.api_key_env, "") if provider.api_key_env else ""
    if provider.kind == EXTERNAL and not key:
        raise LLMError("not_configured")
    _take_slot(school_id, env)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = json.dumps({"model": provider.model, "messages": messages, "max_tokens": provider.max_tokens, "temperature": 0.2}).encode()
    status, raw = (transport or _urllib_transport)(provider.base_url + "/chat/completions", headers, body, provider.timeout)
    usage = {}
    try:
        if status != 200:
            raise ValueError
        data = json.loads(raw)
        text = data["choices"][0]["message"]["content"]
        if not isinstance(text, str):
            raise ValueError
        usage = {k: data.get("usage", {}).get(k) for k in ("prompt_tokens", "completion_tokens") if isinstance(data.get("usage"), dict)}
    except (ValueError, KeyError, IndexError, TypeError):
        logger.warning("llm_call school=%s class=%s status=error http=%s", school_id, provider.kind, status)
        raise LLMError("upstream_error") from None
    logger.info("llm_call school=%s class=%s purpose=%s status=ok tokens=%s", school_id, provider.kind, purpose, usage)      # no content
    return {"text": text, "label": LABEL_FA, "provider_class": provider.kind, "model": provider.model, "usage": usage}
