# STAGE 0 BASELINE (accepted factual baseline)

Commit `3404a1a82fd6528a1f7e34c91012cb361889daf2`, branch `main` — **from the owner's previous repository history; not present in, and not resolvable from, this repository (0 commits as of 2026-10-12)**. Preserved from the Stage 0 audit. **Do not re-audit; cite IDs.** Status of every item: `CURRENT RISK — NOT YET FIXED` unless marked. "Not runtime-verified" = read from code, not executed. No secret values are reproduced here.

## Boot / backend
| ID | Finding |
|---|---|
| B-01 | `fastapi_core/main.py` uses `Depends` (≈lines 108, 156, 257) never imported → NameError at import. Introduced by HEAD. |
| B-02 | `django_core/dashboard/models.py` uses undefined `Student`/`User` (Homework, TeacherParentCommunication; no migrations) → Django app load fails. Introduced by HEAD. |
| B-03 | `predict_status` defined 3× in `students/views.py` (≈180 decorated, 236 undecorated override, 275 module-level using undefined `models`) → `/api/students/{id}/predict/` likely unregistered (not runtime-verified). |
| B-04 | `config/settings.py` shadowed by `config/settings/` package; manage.py/wsgi/asgi/celery default to the package; compose sets `config.settings.production`. |
| B-05 | Dashboard redirects lack `dashboard:` namespace; `upload.html` missing; `upload_students_view` is a stub. |
| B-06 | `POST /documents/` passes metadata into `parent_id`. |
| B-07 | Muddled route decoration in `main.py`. |
| B-08 | Django→FastAPI calls carry no JWT; host hard-coded (`fastapi:8001`). |
| B-09 | `IsAdminUser.has_permission` defined twice (superuser branch dead). |
| B-10 | Import action: no transaction, "nan" strings, possible leading-zero loss (likely, not run), no size cap. |
| B-11 | `send_welcome_email` unused, no beat schedule, `django_celery_results` in requirements but not in INSTALLED_APPS. |

## Security
| ID | Finding | Sev |
|---|---|---|
| S-01 | Dashboard views only `@login_required`: parents read all students; any user creates students, uploads/deletes docs, chats | CRITICAL |
| S-02 | FastAPI unauthenticated: `/chat/`, `POST /documents/`, `/documents/search/`, `/upload-document/`, `DELETE /documents/parent/{id}`; port 8001 published | CRITICAL |
| S-03 | Hard-coded/default secrets (dead `settings.py` Django key, `base.py` fallback, FastAPI default JWT-secret fallback); no `.env.example` | HIGH |
| S-04 | Teachers see all students; no class/school scoping; groups created manually (where: NOT VERIFIED) | HIGH |
| S-05 | No audit/access logs | HIGH |
| S-06 | Published ports 5432, 6379 (no auth), 9000/9001, 11434, 8000, 8001 | HIGH |
| S-07 | Debug/logging exposure: FastAPI global DEBUG logging incl. document sample, `str(e)` returned, default `/docs`, dead settings DEBUG=True, dev-mode Dockerfile CMDs | MED |
| S-08 | `get_db_connection(readonly)` ignores arg; FastAPI writes shared DB; `fastapi_user` role NOT VERIFIED | MED |
| S-09 | Uploads: FastAPI no size cap, extension-only check, `.doc` unreadable by python-docx; Django 10 MB cap | MED |
| S-10 | No production hardening (SECURE_*, CSRF_TRUSTED_ORIGINS, CORS, static server); `migrate` at start; gunicorn timeout 3000 | MED |
| S-11 | Pickle model files committed | MED |

## Data
| ID | Finding |
|---|---|
| D-01 | Migration `0006_document` has no model (commented out). |
| D-02 | Homework/Communication have no migrations. |
| D-03 | FastAPI creates/drops `documents` outside Django migrations in the shared DB; "Document" defined in 3 places. |
| D-04 | Probable `DROP TABLE documents` on every FastAPI startup (udt_name comparison) — NOT VERIFIED at runtime. |
| D-05 | Migration churn 0001→0002 delete→0003. |
| D-06 | `Student.national_id` globally unique (school-scoping implication, TARGET). |
| D-07 | `Grade.score` unbounded; probable scale mismatch (training 0–100 vs platform likely 0–20). |
| D-08 | Attendance vocabulary mismatch (Django present/absent/late/sick vs pipeline present/absent/late/excused, unknown→absent) and formula mismatch (serving `1 - abs/(days+1)` vs training `1 - abs/days`). |
| D-09 | Hard-coded grade/subject/status choices. |

## AI
| ID | Finding |
|---|---|
| A-01 | Risk model trained on synthetic label `(avg_exam_score<12)&(absences>5)`. |
| A-02 | 3 of 8 serving features are constants (0.8, 3, 12). |
| A-03 | Training data not in repo; provenance/licence NOT VERIFIED. |
| A-04 | RAG: no ACL/metadata/relevance threshold/injection defense; zero-vector embeddings on failure; hard-coded OLLAMA_HOST; unpinned models; `ollama:latest`. |
| A-05 | Unused deps chromadb/transformers/sentence-transformers; README claims Qdrant. |
| A-06 | Risk probability shown with "%" though range 0–1. |
| A-07 | Unused `student_model.joblib` / `train_model.py`. |

## Testing / docs / Git
| ID | Finding |
|---|---|
| T-01 | No tests (two empty `tests.py`), no CI. |
| DOC-01 | README conflicted with code (React/TS, Qdrant, FastAPI backend, Nginx, CI/CD). README rewritten in Phase 0 to mark CURRENT vs TARGET. |
| DOC-02 | No CLAUDE.md/docs — addressed by Phase 0. |
| DOC-03 | Requirements/ERD live outside the repo — import pending (`REQUIREMENTS.md`). |
| DOC-04 | `.gitignore` merge-conflict markers (lines 14, 246); `*.xlsx` ignored. Not changed in Phase 0 (documented only). |
| DOC-05 | Compose: first ~20 lines are a commented-out old version. |
| G-01 | History: 4 commits; removed `data.xlsx` (one-row placeholder) and `data.ods` (NOT VERIFIED) remain in history; dev-style Django key in public history. History rewrite forbidden; rotate instead. |

## Corrections after Phase 0 fact-check
None at Phase 0 install.

## Phase 1 re-verification (the table above is the unchanged baseline)
Re-verified at `3404a1a` by running real Django/FastAPI sources (ML/DB packages stubbed): B-01 (`NameError: Depends`), B-02 (`NameError: Student`), B-04 (default `config.settings` resolves to the empty package, so `manage.py check` "passes" vacuously) were reproduced by execution; B-03, B-05, B-06, B-07, B-09, S-01, S-02, D-03, D-04 were confirmed by reading code. Correction to S-01: the DRF API (`/api/students/`) already scoped parents via `parent_user`; the unscoped access was in the server-rendered dashboard views. Status after Phase 1: see `docs/SECURITY.md` (containment table) and the Phase 1 Change Report. Fixed in code: B-01, B-02, B-03, B-04, B-06, B-07, B-09, D-02, D-04 and the dashboard redirects of B-05. Still open: B-05 (`upload.html` missing), B-08 host hard-coding, B-10, B-11, S-03..S-11 (except as noted in SECURITY.md), D-01, D-05..D-09, A-*, T-01 (no CI), DOC-04, DOC-05, G-01.
