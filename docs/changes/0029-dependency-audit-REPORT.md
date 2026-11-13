# 0029 — Dependency audit (C-D, P3) — REPORT, 2026-11-01

Scope: P3 exit criterion "dependency audit" (`SECURITY.md`) and S-11 (tracked model files). Plan: `0026-p3-exit-plan-NOTE.md` C-D.
Tool: `pip-audit` 2.10.1 (PyPI/OSV advisory data of 2026-11-01), installed in a throw-away virtualenv outside the repository; it is **not** a project dependency. Commands: `pip-audit --no-deps --disable-pip -r <file>` for each requirements file, and `pip-audit --path <site-packages>` for the installed Django venv (includes transitive packages).

## 1. Findings and actions
| Package (file) | Was | Advisories | Now | Evidence |
|---|---|---|---|---|
| Django (`django_core`) | 5.2.15 | 5 | **5.2.18** (same LTS line) | Django gate: see §3 |
| requests (`django_core`) | 2.32.3 | 2 | **2.34.2** | idem |
| djangorestframework (`django_core`) | 3.15.2 | 5 | **3.18.3** | idem |
| djangorestframework-simplejwt (`django_core`) | 5.4.0 | 1 | **5.5.1** (keeps `CHECK_REVOKE_TOKEN`, decision 19) | idem; `dashboard`/`students` JWT tests |
| fastapi + starlette (both FastAPI files) | 0.111.0 / 0.37.2 | starlette 7 | **0.162.0 / 1.7.0** (starlette now pinned explicitly) | FastAPI suite 28 OK from a clean install of `requirements-test.txt` (Python 3.10, as CI) |
| PyJWT (FastAPI) | 2.9.0 | 17 (1 without a fix) | **2.15.1** (same as Django) | idem |
| python-multipart (FastAPI) | 0.0.9 | 7 | **0.0.32** (0.0.33 needs a newer Python) | idem |
| pydantic / httpx (FastAPI) | 2.14.0 / 0.27.2 | 0 | 2.14.2 / 0.28.1 (versions the suite ran with) | idem |
| certifi (transitive of requests) | 2026.7.22 | 1 | not pinned; a fresh install/image build takes the current release | — |
| `torch.load` of `student_risk_model.pth` (S-11) | pickle load | — | `weights_only=True` (tensors only, no code) in `fastapi_core/main.py` | real file loaded with `weights_only=True` inside the existing FastAPI image (torch 2.0.1, `--network none`): 8 tensors |

New transitive package: `fastapi` 0.162 pulls `opentelemetry-api` (API only; without an SDK and exporter it records and sends nothing) and `annotated-doc`. No new direct dependency.

## 2. Residual risk — CURRENT RISK, NOT YET FIXED (FastAPI ML/RAG stack)
`fastapi_core/requirements.txt` (the runtime image, not the test file) still pins packages with many advisories: **torch 2.0.1** (23, 5 without a fix; fixes up to 2.13), **transformers 4.41.2** (26, 9 without a fix; fixes in 5.x), **sentence-transformers 2.6.1**, **langchain 0.2.10** / **langchain-community 0.2.9**, **chromadb 0.5.3** (3, none fixed). They are major-version jumps over code paths that no test covers (the suite fakes them), so upgrading them blind would be a rewrite risk.
Mitigation today: the FastAPI port is bound to loopback only (`docker-compose.yml`), RAG answers HTTP 403 (disabled), Phase 2/3 run no LLM, and no real data exists.
**Recommendation (decision pack 0028, P7-1):** at P7 start, replace the in-process ML/RAG stack with the OpenAI-compatible HTTP adapter (embeddings and chat via Ollama or an external API) and `pgvector`, which removes torch/transformers/sentence-transformers/langchain/chromadb from the image; keep the small risk model only if the experiment survives (then torch latest, or export the weights to a plain format). Until then the FastAPI ML image must not be exposed beyond loopback. The full runtime image with the new web-stack pins was **NOT VERIFIED** by a build in this change (heavy ML layers; it is not part of CI); the web stack itself is verified by the suite.

## 3. S-11 tracked model files
Still tracked: `fastapi_core/models/scaler.joblib` (807 B, pickle via joblib), `fastapi_core/models/student_risk_model.pth` (now loaded tensors-only), `fastapi_core/student_model.joblib` (not loaded by `main.py`; only commented code in `main_HuggingFace.py`). File-mode normalization and untracking stay with the owner (deferral of 2026-10-13). Residual: `joblib.load(scaler.joblib)` executes pickle; the file comes from the repository, not from users. Proposed at P7: store the scaler as JSON (`mean_`, `scale_`) and drop `joblib`.

## 4. Gate
Django gate after the upgrade (2026-11-01, `scripts/run_tests.sh all` on a snapshot of the tree with C-B and C-D): SQLite 1454 tests OK (11 skipped) + `demo_intel` 62 OK; PostgreSQL 16 1454 OK. FastAPI: 28 OK (clean install of `requirements-test.txt`, Python 3.10).
Re-run the audit before every release and at the P3 exit: same commands; any advisory with a fix in the Django requirements blocks the release.
