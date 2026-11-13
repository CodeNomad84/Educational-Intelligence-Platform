# PILOT CONFIG (T6)

Scope of "pilot-ready": **base + mission + exams**. The AI assistants (`advisor_ai`, `tutor_ai`, `docqa`)
and the **Counselor role** are OFF by default.

## Feature flags (Django settings, `config/settings/base.py`)

| Setting | Default | Environment | Effect |
|---|---|---|---|
| `PILOT_MODE` | `False` | `PILOT_MODE` | Marker only — it does not itself block anything; the two switches below are the real gates. |
| `ENABLE_AI_FEATURES` | `False` | `ENABLE_AI_FEATURES` | Gates the assistant routes: the School Assistant `docqa` (`/assistant/…`) and the Study Assistant (`/me/assistant/`, `tutor_ai`). Off → HTTP 403. FastAPI chat/RAG is also 403 while off. |
| `ENABLE_COUNSELOR_ROLE` | `False` | `ENABLE_COUNSELOR_ROLE` | Gates the Counselor pages (`/counselor/`, `/counselor/case/<pk>/`, close) and the referral path (`/students/<pk>/refer/`). Off → HTTP 403. |
| `FEEDBACK_URL` | `''` (empty) | `FEEDBACK_URL` | Global feedback link shown in the footer of every authenticated page. Empty = hidden. |

All defaults are **fail-closed** (False). `config/settings/development.py` (and therefore `test_sqlite`,
`test_postgres`, and `demo`, which import it) turns `ENABLE_AI_FEATURES` and `ENABLE_COUNSELOR_ROLE` back
**ON** so local dev/demo/tests keep the pre-pilot behaviour. `production.py` (which imports `base.py`
directly) stays off unless an operator sets the environment variables.

## What the pilot blocks

- Counselor home / case / close — 403 (gated by `ENABLE_COUNSELOR_ROLE`).
- Referral POST (`dashboard:student_refer`) — 403 (same switch).
- School Assistant `docqa` (`home`, `documents`, `document_action`, `ai_setting`) — 403 (gated by `ENABLE_AI_FEATURES`).
- Study Assistant `dashboard:me_assistant` (`tutor_ai`) — 403 (same switch).
- FastAPI `/chat/`, `POST /documents/`, `GET /documents/search/`, `POST /upload-document/` — 403 while `ENABLE_AI_FEATURES` is off (and still 403 while RAG is unverified; see below).
- Django `/chat/` (`dashboard:chat`) is already `@role_required()` (always 403) and is unchanged.

The gate is `dashboard.decorators.require_pilot_flag(flag)`, stacked **inside** `role_required`, so the
order is: login redirect → role/module check → flag check (403). Anonymous users still get the login
redirect; the flag only affects authenticated users.

## Feedback footer

`dashboard/templates/dashboard/base.html` renders `<a href="{{ FEEDBACK_URL }}">بازخورد و پیشنهاد</a>` only
when `FEEDBACK_URL` is non-empty. The value is rendered **verbatim** — the template appends nothing, so the
URL can never carry a student id, a query string built from request data, or any other per-request value.
Set it to a fixed form/survey URL.

## FastAPI chat/RAG

`fastapi_core/auth.py::disabled_in_phase1` refuses with HTTP 403 while `ENABLE_AI_FEATURES` is off (the
pilot default). Turning the flag on does **not** by itself enable RAG: the embedding model, vector dimension
and document-level ACL are still unverified, so the dependency keeps refusing 403 until those are done, at
which point it is swapped for `require_roles(...)`.

## Can one server run two isolated instances?

**Short answer: one server can host two isolated instances, but not by sharing a single Django/FastAPI
process or a single database.**

- Two isolated instances = two **independent deployments**: separate Django + FastAPI processes, separate
  databases (two databases, or two schemas on one PostgreSQL server), separate `SECRET_KEY` and
  `SERVICE_JWT_SECRET`, separate media/static storage and separate environment files.
- They must **not** share a process, a database (or schema), a secret, or the media/static volume. Sharing
  any of those breaks isolation — data, sessions, or the service-token trust boundary.
- The application is single-school-per-deployment in spirit ("school-ready, not enterprise multi-tenant"):
  a school key can be added and the access layer scopes by school membership *within one deployment*, but it
  does not run several tenants inside one shared process. So "two isolated instances on one server" means two
  containers/VMs/databases, **not** two schools inside one shared process.
- Concretely on one box: run two `docker compose` stacks (or two systemd units) with distinct project names,
  ports, data directories and env files. Each is fully isolated; the OS is the only shared resource.
