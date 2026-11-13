#!/usr/bin/env python3
"""Key-free smoke check for the LLM adapter (change 0043, ADR-0008).

Default mode is ``--mock``: the adapter's real code path runs (config parsing, purpose whitelist, PII tripwire, the
deterministic daily cap, request construction and response parsing), but the HTTP call goes to a fake transport. So this
tool needs no key, works offline and sends nothing anywhere.

``--live`` performs exactly ONE real completion against the configured provider with a fixed non-personal Persian prompt
(no student data, no school data). It needs the key in the environment named by the provider config.

Rules this tool keeps:
  * it never prints a key, credentials or a provider error body — only fixed codes, counts and its own answer;
  * it reads an env file only when you name it (``--env-file``), as data; nothing is exported into the environment;
  * exit codes: 0 all checks passed, 1 a check failed, 2 configuration/environment problem.

Usage (repository root, host python3 — the adapter is stdlib-only):
  python3 tools/llm_smoke.py --mock                       # safe everywhere; the default
  python3 tools/llm_smoke.py --mock --env-file .env.llm   # validate the operator file without sending anything
  python3 tools/llm_smoke.py --live --env-file .env.llm   # ONE real call with a non-personal prompt

Options: ``--provider NAME`` (required when several are configured), ``--purpose NAME`` (default ``policy_document``).
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

SENTINEL_KEY = "mock-key-not-a-secret"      # only for --mock: no real key is needed and this is never printed
SMOKE_SCHOOL = 0                            # not a real school; the cap counter for it is harmless
PROMPT = "یک تمرین کوتاه ریاضی برای پایهٔ هفتم پیشنهاد بده. فقط خود تمرین را بنویس."
PII_PROBE = "شمارهٔ تماس 09121234567 و کد ملی 0012345678"        # synthetic values, for the tripwire check
FAKE_ANSWER = "۱) ۳/۴ + ۱/۴ را حساب کن. ۲) حاصل ۲/۵ × ۳ را بنویس."


class EnvFileError(Exception):
    """The env file could not be read or parsed. Carries no value."""


def read_env_file(path):
    """``KEY=VALUE`` lines as data: blank/comment lines skipped, a matching pair of quotes stripped.

    No ``export``, no interpolation, and no value is ever echoed in an error (same rule as ``scripts/preflight.py``).
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        raise EnvFileError(f"cannot read the env file {path}") from None
    values = {}
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator:
            continue
        name, value = name.strip(), value.strip()
        if not name.isidentifier():
            raise EnvFileError(f"invalid variable name on line {number} of {path}")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[name] = value
    return values


def adapter_module():
    """Import ``fastapi_core/llm_adapter.py`` by path (it imports only the standard library)."""
    service = Path(__file__).resolve().parents[1] / "fastapi_core"
    if str(service) not in sys.path:
        sys.path.insert(0, str(service))
    import llm_adapter
    return llm_adapter


class FakeTransport:
    """Records the request and answers 200 with a fixed body, so the adapter really parses a response."""

    def __init__(self, answer=FAKE_ANSWER):
        self.answer, self.calls = answer, []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": dict(headers), "body": json.loads(body.decode()), "timeout": timeout})
        payload = {"choices": [{"message": {"content": self.answer}}],
                   "usage": {"prompt_tokens": 37, "completion_tokens": 11}}
        return 200, json.dumps(payload, ensure_ascii=False).encode()


class Report:
    """Collects PASS/FAIL/note lines; ``failures`` decides the exit code."""

    def __init__(self):
        self.lines, self.failures = [], 0

    def ok(self, text):
        self.lines.append(f"  PASS  {text}")

    def fail(self, text):
        self.failures += 1
        self.lines.append(f"  FAIL  {text}")

    def note(self, text):
        self.lines.append(f"  note  {text}")


def build_parser():
    parser = argparse.ArgumentParser(description="Smoke check for the LLM adapter (mock by default; live only on request).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="fake transport, no key, nothing sent (default)")
    mode.add_argument("--live", action="store_true", help="ONE real call; needs the provider key in the environment")
    parser.add_argument("--provider", help="provider name from LLM_PROVIDERS (needed only when several are configured)")
    parser.add_argument("--purpose", default="policy_document", help="adapter purpose for the call (default: policy_document)")
    parser.add_argument("--env-file", help="read KEY=VALUE lines from this file as data (e.g. .env.llm)")
    return parser


def _attempt(llm, provider, purpose, messages, env, transport):
    """One adapter call; returns ``(code, result)`` where code is ``"ok"`` or the adapter's fixed error code."""
    try:
        return "ok", llm.complete(provider, messages, purpose, school_id=SMOKE_SCHOOL, env=env, transport=transport)
    except llm.LLMError as exc:
        return exc.code, None


def _expect(report, llm, provider, purpose, expected, env, messages=None):
    transport = FakeTransport()
    code, _ = _attempt(llm, provider, purpose, messages or [{"role": "user", "content": PROMPT}], env, transport)
    if code == expected:
        report.ok(f"purpose {purpose!r} -> {expected}")
    else:
        report.fail(f"purpose {purpose!r} -> {code}, expected {expected}")
    return code


def run(argv=None, env=None):
    args = build_parser().parse_args(argv)
    base = dict(os.environ if env is None else env)
    lines = [f"LLM smoke check — mode={'live' if args.live else 'mock'} (no key or provider text is ever printed)"]

    if args.env_file:
        try:
            base.update(read_env_file(args.env_file))
        except EnvFileError as exc:
            print(f"{lines[0]}\n  FAIL  {exc}\nRESULT  exit 2 (configuration)")
            return 2
        lines.append(f"  note  read {args.env_file} as data (values never printed)")

    try:
        llm = adapter_module()
    except Exception:       # wrong tree; no secret is involved
        print(f"{lines[0]}\n  FAIL  cannot import fastapi_core/llm_adapter.py from this location\nRESULT  exit 2")
        return 2

    report = Report()

    # 1. The provider list must be valid configuration, and it must not be empty.
    try:
        providers = llm.load_providers(base)
    except llm.LLMError as exc:
        report.fail(f"LLM_PROVIDERS is not valid configuration ({exc.code})")
        providers = {}
    if not providers:
        if not report.failures:
            report.fail("no provider configured: LLM_PROVIDERS is empty (template: .env.llm.example)")
        print("\n".join(lines + report.lines + ["RESULT  exit 2 (configuration)"]))
        return 2

    # 2. Pick the provider: explicit, or the only one.
    if args.provider:
        if args.provider not in providers:
            print(f"{lines[0]}\n  FAIL  provider {args.provider!r} is not in LLM_PROVIDERS "
                  f"(configured: {sorted(providers)})\nRESULT  exit 2")
            return 2
        provider = providers[args.provider]
    elif len(providers) == 1:
        provider = next(iter(providers.values()))
    else:
        print(f"{lines[0]}\n  FAIL  several providers are configured; choose one with --provider "
              f"(configured: {sorted(providers)})\nRESULT  exit 2")
        return 2
    report.ok(f"provider {provider.name!r} loaded: class={provider.kind}, model={provider.model}")

    # 3. Default OFF: a school that is not in LLM_SCHOOL_MAP has no provider at all.
    try:
        if llm.provider_for_school(987654321, env=base) is None:
            report.ok("a school absent from LLM_SCHOOL_MAP has no provider (AI OFF by default)")
        else:
            report.fail("a school absent from LLM_SCHOOL_MAP got a provider: check LLM_SCHOOL_MAP")
    except llm.LLMError as exc:
        report.fail(f"LLM_SCHOOL_MAP is not valid configuration ({exc.code})")

    # 4. Purpose whitelist (decision 59) and decision 62 (document_qa is LOCAL-class only).
    _expect(report, llm, provider, "definitely_not_a_purpose", "purpose_refused", base)
    _expect(report, llm, provider, "counseling", "purpose_refused", base)
    local_only = "ok" if provider.kind == llm.LOCAL else "purpose_refused"
    for purpose in ("document_qa", "school_data_summary"):
        if _expect(report, llm, provider, purpose, local_only, base) == "ok" and provider.kind == llm.LOCAL:
            report.note(f"{purpose} is allowed for class=local (that class may already see this school's data)")

    # 5. The external-class PII tripwire refuses a synthetic phone number / national id.
    if provider.kind == llm.EXTERNAL:
        _expect(report, llm, provider, args.purpose, "pii_refused", base,
                messages=[{"role": "user", "content": PII_PROBE}])

    # 6. Key handling: a missing key is not_configured (never a crash); mock never uses a real key.
    key = base.get(provider.api_key_env, "") if provider.api_key_env else ""
    if provider.kind == llm.EXTERNAL and not key:
        _expect(report, llm, provider, args.purpose, "not_configured", base)
        if args.live:
            report.fail(f"--live needs a key in {provider.api_key_env} (put it in .env.llm or export it)")
            print("\n".join(lines + report.lines + ["RESULT  exit 2 (no key)"]))
            return 2
        base[provider.api_key_env] = SENTINEL_KEY
        report.note(f"{provider.api_key_env} is empty; mock uses a sentinel so the request path still runs")
    elif not args.live:
        base[provider.api_key_env] = SENTINEL_KEY        # never send a real key through the fake transport

    # 7. One completion: fake transport by default, the real network only with --live.
    llm.reset_usage()
    transport = None if args.live else FakeTransport()
    started = time.monotonic()
    code, result = _attempt(llm, provider, args.purpose, [{"role": "user", "content": PROMPT}], base, transport)
    elapsed = int((time.monotonic() - started) * 1000)
    if result is None:
        report.fail(f"the completion failed with the fixed code {code!r}")
        print("\n".join(lines + report.lines + ["RESULT  exit 1 (refused)"]))
        return 2 if code in ("not_configured", "bad_config") else 1
    report.ok(f"completion returned in {elapsed} ms, usage={result['usage']}, advisory label={bool(result['label'])}")

    if transport is not None:           # mock: assert exactly what would have been sent
        call = transport.calls[-1]
        if call["url"] == provider.base_url + "/chat/completions":
            report.ok(f"request target is {{base_url}}/chat/completions for class={provider.kind}")
        else:
            report.fail("request target is not {base_url}/chat/completions")
        if call["body"].get("model") == provider.model and call["body"].get("max_tokens") == provider.max_tokens:
            report.ok("request body carries the configured model and max_tokens (defensive cap)")
        else:
            report.fail("request body does not match the configured model/max_tokens")
        if set(call["body"]) == {"model", "messages", "max_tokens", "temperature"}:
            report.ok("request body holds exactly four fields (no school id, no user, no role from the caller)")
        else:
            report.fail(f"unexpected request fields: {sorted(call['body'])}")
        if provider.kind == llm.EXTERNAL and "Authorization" in call["headers"]:
            report.ok("Authorization header present (its value is never printed)")
        elif provider.kind == llm.EXTERNAL:
            report.fail("no Authorization header for an external provider")

    report.note(f"answer preview: {(result['text'] or '').strip()[:300]!r}")
    report.note("this check sent no student data" if transport is not None
                else "one fixed non-personal prompt was sent to the configured provider")

    verdict = "OK" if report.failures == 0 else f"{report.failures} failure(s)"
    text = "\n".join(lines + report.lines + [f"RESULT  {verdict} — exit {0 if report.failures == 0 else 1}"])
    secret = base.get(provider.api_key_env, "") if provider.api_key_env else ""
    if secret and secret in text:      # self-check: the tool must never be able to leak a key
        text += "\n  FAIL  a key appeared in the output; this must never happen"
        report.failures += 1
    print(text)
    return 0 if report.failures == 0 else 1


def main(argv=None):
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())


