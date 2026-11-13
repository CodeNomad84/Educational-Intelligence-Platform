# PHASE 1 — FINAL VERIFICATION (acceptance closure pass)

> **Point-in-time record (2026-10-12).** The evidence and results below stand as dated. Its status statements ("0 commits", "Phase 1 is not accepted", "Phase 2 has not started", "nothing was committed") were true then and are **superseded**: Phase 1 was committed and closed on 2026-10-13 (`4c096de`); see `PHASE1_FINAL_STATUS.md` and `ROADMAP.md`.

**Date:** 2026-10-12 (reconciled with the dataset-provenance follow-up the same day) · **Branch:** `phase-1/boot-security` (0 commits) · **Reviewer:** Claude Code
**Labels:** PASS · FAIL · NOT VERIFIED · OWNER INPUT REQUIRED
**Safety:** no secret value or secret hash appears in this document. No commit, `git add`, reset, clean, stash, branch switch, credential rotation, image build, port change or data deletion happened in this pass. No Docker volume, dataset, model or database content was deleted or modified.

## 0. Status update 2026-10-12 (documentation reconciliation)
This update reflects the dataset-provenance follow-up. Evidence was executed on 2026-10-12; commands and results are in `TESTING.md`, `DATA_AND_ARTIFACTS.md` and section 7.

| Topic | Current status |
|---|---|
| Official dataset | **Verified** from the official page: *Student Performance and Attendance Dataset*, creator Marvy Ayman Halim (`marvyaymanhalim`), version 1, last modified 2025-03-10T22:05:09Z, license named MIT, canonical URL `https://www.kaggle.com/marvyaymanhalim/student-performance-and-attendance-dataset`. The creator's description calls it synthetic; this is **not independently verified**. |
| License caveat | The MIT text linked from the page carries other parties' copyright lines, not the creator's. Attribution/notice adequacy is **OWNER INPUT REQUIRED**. |
| Local CSVs | Each has **49 non-empty rows followed by blank filler rows**; they have not been hash-matched to the official archive and **cannot contain its content** (12,921 bytes compressed vs 5,849,540 bytes). The reason for the blanking and who caused it are **unknown**. Files preserved unchanged; not imported into school records. |
| Model | Re-checked on the fixed inputs, nothing retrained: logits −30.685, −35.945, −20.861, −40.525, −52.253; probability 0.0 for all. **Non-discriminating**; must stay experimental and advisory-only. |
| Operational model validation | **Blocked** until coherent data (checked against the official archive), a target-label definition, reproducibility and meaningful evaluation metrics exist. |
| Infrastructure | All technical criteria passed when executed (Django 38 tests, FastAPI 24 tests, live authorization/role/token probes, DB role runbook verification, ports, secrets). |
| Deferred by the owner | `school_user` PostgreSQL superuser; healthchecks and restart policies; Torch `2.0.1+cu117` retained (CPU migration not approved); VMware network retained, NAT not independently confirmed. See `SECURITY.md`. |
| Baseline | The repository has 0 commits. `Verified-at: 3404a1a` stamps refer to the owner's original repository history and are qualified in each document. |

## 1. Result at a glance

| # | Acceptance criterion | Result |
|---|---|---|
| A1 | Environment files present, non-placeholder, consistent across services | **PASS** |
| A2 | `.env.example` contains no real credential | **PASS** |
| A3 | PostgreSQL container does not receive Django `SECRET_KEY` / service secret | **PASS** (fixed in this pass) |
| A4 | Service JWT secret has one runtime source; no blank duplicate in `.env` | **PASS** (fixed in this pass) |
| B1 | FastAPI runs as least-privilege `fastapi_user`; cannot touch Django tables or write beyond need | **PASS** |
| B2 | Django, Celery keep their intended role | **PASS** |
| B3 | Role setup is documented, repeatable, verifiable, reversible | **PASS** (new `docs/FASTAPI_DB_ROLE.md`); interactive `\password` step **NOT VERIFIED** |
| C1 | PostgreSQL, Redis, MinIO not published to the host | **PASS** |
| C2 | Django 8000 exposure decision | **OWNER INPUT REQUIRED** — owner retains the current VMware network; NAT is not independently confirmed |
| D1 | Risky paths ignored by Git; nothing sensitive in a first commit | **PASS** |
| D2 | Historical comparison of code/tests against a baseline | **NOT VERIFIED** (no commit exists) |
| E1 | Dataset title, creator, URL, version, license | **PASS (verified from the official Kaggle page)**: MIT named; **OWNER INPUT REQUIRED** for the copyright/attribution caveat |
| E2 | Dataset synthetic / real-person status | **Creator states "synthetic" (not independently verified); anonymization/person-data status NOT VERIFIED** |
| E3 | Dataset must not enter real school records until confirmed | **PASS** (documented; not imported) |
| E5 | Local CSVs are the official content | **FAIL** — 49 non-empty rows per file, cannot contain the official 5,849,540-byte archive; hash matching impossible without the archive (**NOT VERIFIED**) |
| E4 | Model artifacts reproducible from documented steps; model discriminates | **FAIL** (output saturated, 0.0 for all fixed inputs) / reproducibility **NOT VERIFIED** — blocks operational model validation, not infrastructure |
| F1 | Torch pinned; build deterministic enough to review | **PASS with caveats** (pin present; transitive packages and base image floating) |
| F2 | Torch packaging change | **Not approved by owner**; `2.0.1+cu117` retained, nothing changed (assessment in section 6) |
| G1 | Django tests, `check`, migration consistency | **PASS** (38 tests) |
| G2 | FastAPI tests | **PASS** (24 tests) |
| G3 | Teacher restrictions, disabled RAG routes, delete 404, startup validation (live) | **PASS** |
| G4 | Celery executes a task end to end | **PASS** |

**Final recommendation: READY FOR INDEPENDENT INFRASTRUCTURE REVIEW** — infrastructure only. Operational model validation is **blocked** (section 4, E4/E5). Phase 1 is not accepted.

## 2. Changes made in this pass

| File | Change | Reason |
|---|---|---|
| `docs/FASTAPI_DB_ROLE.md` (new) | Repeatable setup, verification and rollback runbook for `fastapi_user`; SQL kept in Markdown because `.gitignore` ignores `*.sql` | Blocker B3 / R-01 |
| `docs/DATA_AND_ARTIFACTS.md` | Dataset provenance table with explicit OWNER INPUT REQUIRED items, file metadata and hashes, do-not-import rule, model-artifact facts, corrected secret-file table | Blocker E / R-02 |
| `docker-compose.yml` | Removed `env_file: .env` from the `postgres` service | N-2: the DB server received Django's `SECRET_KEY` |
| `.env` (local, gitignored) | Removed the blank `SERVICE_JWT_SECRET=` line and its stale 2-line comment; replaced by one comment pointing to `.env.service`. No secret value was changed or printed. | N-1 |
| `docs/PHASE1_FINAL_VERIFICATION.md` | This document | — |

Services recreated: `postgres`, `celery`, `celery_beat`. Django and FastAPI were not recreated (their effective configuration did not change). The PostgreSQL data directory and every volume were untouched.

## 3. Task 1 — FastAPI database role (B1, B2, B3)

**What FastAPI executes** (`fastapi_core/rag_service.py`, read again): `to_regclass` check, pgvector type lookup on connect, the list `SELECT`, `DELETE … WHERE id` / `WHERE parent_id`. `INSERT` and the search `SELECT` exist but sit behind routes that are disabled for every role. Minimum grants: `CONNECT`, `USAGE` on `public`, `SELECT, DELETE` on `public.documents`. Nothing else is granted.

**Runbook:** `docs/FASTAPI_DB_ROLE.md` — fresh-install order, pre-checks, idempotent setup (admin role `school_user`), interactive password step, `.env.fastapi` format, three verification methods, rollback that revokes and sets `NOLOGIN` without touching data. It contains no password or secret.

**Tests executed** (the SQL was extracted from the Markdown file and run against the live database; every run was wrapped so it rolled back):

| Test | Result |
|---|---|
| T1 pre-checks on live (`documents` table, pgvector, role existence) | PASS |
| T2 setup + verify, **fresh path** with a probe role that did not exist: role created, grants applied, 5 operations allowed, 10 denied, `RESULT: 0 problem(s)`; role absent afterwards | PASS |
| T3 setup + verify on the **existing** `fastapi_user` (idempotent/converge path), rolled back; role and grants unchanged afterwards | PASS |
| T4 verify block alone against the live `fastapi_user` via `SET LOCAL ROLE`: 0 problems | PASS |
| T5 rollback block on a probe role: `can_login=false`, no `SELECT`/`DELETE` on `documents` afterwards | PASS |
| T6 abort path: simulated missing `documents` table → `ABORT … Run the Django migrations first`, no role created | PASS |
| Live service role: through `rag_service.get_db_connection()` → `('fastapi_user', superuser=False)`, `documents_table_exists()` True, after the Postgres container was recreated | PASS |
| Django and Celery connect as `school_user` after the Postgres recreate | PASS |

**Not verified:** (a) `\password fastapi_user` is interactive and needs a TTY — not run; (b) a full run of the setup SQL on a genuinely empty cluster (a fresh `docker compose` project) — not run because it needs a second database instance; the fresh-path test used the live cluster with a role that did not exist. (c) The `COMMIT` path of the setup block was only exercised through its idempotent re-application of the already committed state (T3 rolled back); the block's transaction is plain `BEGIN … COMMIT`.

## 4. Task 2 — Dataset provenance (E1–E5)
Official page read on 2026-10-12 with a plain HTTP GET (`curl`) of the dataset URL and its embedded schema.org metadata; the web-fetch tool was blocked for kaggle.com and the archive itself was not downloaded (login required).

| Item | Status | Evidence |
|---|---|---|
| Title | **VERIFIED** | "Student Performance and Attendance Dataset" |
| Creator / slug | **VERIFIED** | Marvy Ayman Halim / `marvyaymanhalim` |
| Canonical URL | **VERIFIED** | `https://www.kaggle.com/marvyaymanhalim/student-performance-and-attendance-dataset` (owner supplied the `/data` tab) |
| Version / date | **VERIFIED** | version 1; dateModified 2025-03-10T22:05:09Z |
| License | **VERIFIED as named (MIT)**; attribution caveat **OWNER INPUT REQUIRED** | linked text is a generic MIT template with unrelated copyright lines |
| Synthetic | Creator's own statement; **not independently verified** | page description: "This synthetic dataset…" |
| Person data / anonymization | **NOT VERIFIED** | no statement beyond "synthetic" |
| Local files match the official version | **NOT VERIFIED / FAIL** | archive not obtained; compressed local size 12,921 bytes vs 5,849,540 bytes official |
| Not imported into real records | **PASS** | only `data_pipeline.py` reads the folder; DB has 0 students |

**Integrity findings (aggregate counts only, no record content):** 49 non-empty rows per file, contiguous at the top, then blank filler (`,,,,`); 99.6–100 % missing cells overall; row counts in exact ratios 1 : 30 : 5 : 3 : 2; IDs unique within each file; `students.csv` keeps IDs 1–49 while the other files keep IDs spread up to ~12,119 (overlap 0, 1, 0, 0; none in all five); retained rows show the intentional data-quality issues the page describes. The pipeline yields 49 × 9 rows. Interpretation (not proven): cleared copies of a larger dataset whose row structure was kept; cause and actor unknown.

Consequence: nothing meaningful can be trained from these files, so the model cannot be shown to derive from them (E4).

## 5. Task 3 — Secret exposure (A1–A4)

**A3 PostgreSQL.** Before: `env_file: .env` gave the DB container Django's `SECRET_KEY`, the Django password and CORS/Redis settings. After: no `env_file`; effective container environment is exactly `POSTGRES_DB`, `POSTGRES_PASSWORD`, `POSTGRES_USER` (interpolated by Compose). Verified on the recreated container (variable names only). Data intact afterwards: roles `fastapi_user`, `school_user`; 26 migrations applied incl. `students.0007`; 17 public tables; `documents` 0 rows; pgvector 0.8.5.

**A4 Service secret.** Source at runtime: `.env.service` is loaded by `django` (after `.env`) and by `fastapi`; the blank `.env` entry was only an empty default overridden by file order. It is removed from `.env`. Effective configuration (checked as booleans from the rendered config): Django and FastAPI each have a secret of at least 32 characters; it differs from `SECRET_KEY`; Celery and Beat no longer receive the variable (they never call FastAPI); PostgreSQL has none. `.env.example` has no `SERVICE_JWT_SECRET` value (only a comment).

**Interoperability after the change (live):** a token minted by Django's `service_headers` was accepted by FastAPI — Admin `list` 200, `chat` 403, `delete` of a missing id 404; Teacher 403 on `list`, `chat` and `delete`; anonymous 401.

**Startup validation, real container:** configured secret → `startup OK`; empty secret → refused; `short` → refused. (Unit tests additionally cover unset, placeholder and low-entropy values; the message never contains the value.)

**A1/A2 environment files** (reported without values, from the previous pass and not changed since except `.env` above): `.env`, `.env.service`, `.env.minio`, `.env.fastapi` have mode 600 and no duplicate keys; credentials are consistent between files and running containers; `.env.example` has blank secret keys and equals no real value. Residual: `.env` retains a comment block the owner may want to tidy (project rule: `.env` is owner-edited; only the one blank entry was removed on explicit instruction).

## 6. Task 4 — Torch packaging assessment (no change made)

**Facts (measured in the running image):**
- `requirements.txt` pins `torch==2.0.1`; the Dockerfile's separate CPU-install line is commented out. Resolution therefore uses the default PyPI wheel: installed `torch 2.0.1+cu117` with 11 `nvidia-*-cu11` packages and `triton 2.0.0`.
- Python 3.10.22, numpy 1.26.4 (pinned), scikit-learn 1.5.1.
- Sizes in site-packages: `torch` 1.3 GB, `nvidia` 2.6 GB (cuDNN 0.86 GB, cuBLAS 0.46 GB, …), `triton` 0.19 GB. Whole image: 8.26 GB.
- No GPU use: `torch.cuda.is_available()` is False; the only model load is `torch.load(..., map_location=cpu)` (`main.py:49`); there is no `.cuda()` / `device=` anywhere in the service.
- `torch` is imported directly by `main.py` and the training script; `sentence-transformers` (pinned, used only by the unused HuggingFace variant files) requires `torch>=1.11`.
- The CPU wheel `torch-2.0.1+cpu-cp310-cp310-linux_x86_64.whl` exists on `https://download.pytorch.org/whl/cpu` and is 195,422,835 bytes (HTTP HEAD answered 200 from this host).

| | Option A — keep current (`torch 2.0.1+cu117`) | Option B — `torch==2.0.1+cpu` + constraints file |
|---|---|---|
| Compatibility | Verified: model loads, `/predict/` 200, 24 tests pass | Same torch version and Python API → state_dict loads unchanged; numpy 1.26.4 already satisfies 2.0.1 (do not allow numpy 2.x). Needs verification. |
| Image size | 8.26 GB; ~2.6 GB nvidia + 0.19 GB triton unused | Saves at least the measured 2.8 GB (nvidia + triton), plus a smaller torch wheel (not measured) |
| Build robustness | Large downloads, repeated pip read timeouts; ~2 h on this network | One 186 MiB torch wheel from a second index; fewer bytes to time out |
| Package index risk | Single index (PyPI) | Second index: install torch in its own step from the PyTorch CPU index and everything else from PyPI, so a same-named package on the extra index cannot replace a PyPI dependency |
| Attack surface | Carries unused CUDA libraries | Smaller |
| Owner effort | none | one reviewed Dockerfile change + one long build |

**Recommendation:** adopt Option B, **after owner approval**, as one isolated change, because the service is CPU-only and the unused CUDA stack is the main cause of the size and the timeout-prone builds. Do not combine it with any version change.
1. Dockerfile: before the requirements step, `pip install --default-timeout=300 --retries=5 --no-cache-dir torch==2.0.1+cpu --index-url https://download.pytorch.org/whl/cpu`; `requirements.txt` keeps `torch==2.0.1` (PEP 440 matches the local `+cpu` label).
2. Create a constraints file from the verified image (`pip freeze`) and install with `-c`; pin the base image by digest. This also addresses the ~140 floating transitive packages.
3. Build to a **separate tag**; keep the current image as the rollback.

**Verification plan for the existing model** (success criteria in brackets):
- `pip check` clean; `torch.__version__ == 2.0.1+cpu`; `cuda.is_available()` False; no `nvidia-*` packages.
- Load `student_risk_model.pth` + `scaler.joblib` (no load errors).
- Pre-sigmoid logits on five fixed synthetic inputs must match the recorded baseline within 1e-4. Baseline recorded today on `2.0.1+cu117`: `[-30.68502, -35.94512, -20.8611, -40.52522, -52.25304]` for the rows `(8,0.95,0.9,17.0,1,0,3,12)`, `(9,0.50,0.4,8.0,20,9,1,2)`, `(10,0.80,0.7,12.5,5,3,2,6)`, `(11,1.00,1.0,19.5,0,0,5,15)`, `(12,0.30,0.2,5.0,30,12,0,0)`.
- FastAPI tests 24/24; live `/predict/` returns 200 for Admin, 403 for others; startup validation unchanged.
- Compare `docker images` size and build time against this report.

Note: the existing model's output is saturated (every probability 0.0; logits −21 … −52), so probabilities alone are a useless baseline; use the logits.

## 7. Tests and checks run in this pass

| Command / probe | Result |
|---|---|
| `docker compose exec -T django python manage.py check` | no issues |
| `docker compose exec -T django python manage.py test students dashboard` | 38 tests OK |
| `docker compose exec -T fastapi python -m unittest discover -s tests -t .` | 24 tests OK |
| Runbook SQL extracted from `docs/FASTAPI_DB_ROLE.md`, run T2–T6 in rolled-back transactions | all PASS (section 3) |
| `rag_service.get_db_connection()` in the FastAPI container | `fastapi_user`, not superuser |
| Django-minted token against the live FastAPI (Admin / Teacher / anonymous) | as in section 5 |
| Real `main.py` startup with valid / empty / short `SERVICE_JWT_SECRET` | startup OK / refused / refused |
| Celery `debug_task.delay()` through the recreated worker | result `None`, state `SUCCESS` |
| `docker compose config` (booleans only) | postgres env = 3 `POSTGRES_*` keys; service secret effective in django and fastapi |

Not re-run (inherited from the previous pass, unchanged files): the full live per-role matrix across all FastAPI routes and the host reachability checks (5432/6379/9000/9001 closed). Test integrity (no assertion weakened) remains **NOT VERIFIED mechanically** because no baseline commit exists; changed expectations are policy-driven and listed in the Round 3 report.

## 8. Remaining risks

| ID | Severity | Risk | Status |
|---|---|---|---|
| R-01 | — | `fastapi_user` not reproducible | **Closed** (runbook, tested); interactive password step NOT VERIFIED |
| R-02 | **MEDIUM (compliance)** | MIT license named on the official page; the linked text lacks the creator's copyright notice; synthetic status is the creator's claim only; person-data status not verified | OWNER INPUT REQUIRED (attribution/notice) |
| R-12 | **HIGH (model validation)** | Local dataset files are blanked copies (49 usable rows; not hash-matched; cause unknown) and the model output is saturated; the "risk model" carries no information and its artifacts cannot be tied to documented training. Does not affect the infrastructure. | Open — blocks operational model validation |
| R-03 | MEDIUM | Django `0.0.0.0:8000` exposure; the owner retains the current VMware configuration; NAT is not independently confirmed (guest `192.168.91.128/24`, gateway `.2` is typical of NAT, not proof) | OWNER INPUT REQUIRED |
| R-04 | MEDIUM | Django, Celery and the bootstrap use `school_user`, a superuser | Deferred (outside Phase 1 scope) |
| R-05 | MEDIUM | Build: floating transitive packages, base image by tag, 8.26 GB image | Open — Option B above, awaiting approval |
| R-06 | MEDIUM | Model artifact reproducibility (torch unseeded, training environment not recorded) | Open |
| R-07 | LOW | `.env` keeps legacy template comments; Redis has no authentication (internal only) | Deferred |
| R-08 | LOW | Unused `DB_USER_READONLY` branch in `rag_service.py`; other handlers still return `str(e)` in 500 bodies; `torch.load` uses pickle (artifact is a trusted local file) | Deferred |
| R-09 | INFO | No baseline commit: history and "assertions not weakened" cannot be machine-verified | Open — the owner should make the baseline commit after review |
| R-10 | INFO | Single-school prototype; no multi-tenant isolation; teacher assignment (S-04) absent | Documented |

## 9. Owner input required
1. Download the official archive (Kaggle login) into a **new** directory, compare it with the local files and the hashes in `DATA_AND_ARTIFACTS.md`, and explain or replace the blanked files. (R-12)
2. Decide whether the MIT text linked from Kaggle satisfies the attribution/notice requirement for the intended use; record the attribution if needed. (R-02)
3. Confirm in the VMware network settings whether the VM is NAT or bridged. (R-03)
4. Decide on `school_user` superuser privileges (deferred) and on healthchecks/restart policies. (R-04)
5. Create the baseline Git commit after review; do not let tooling commit. (R-09)
6. Model validation (separate gate): target label, features, metrics and a reproducible training procedure on coherent data.

## 10. Recommendation

**READY FOR INDEPENDENT INFRASTRUCTURE REVIEW** — scoped to the software infrastructure only.

The infrastructure criteria that could be tested all passed when executed (authorization and disabled RAG, least-privilege DB role with a tested runbook, secrets handling, port exposure, startup validation, Celery, and 38 + 24 passing tests). The official dataset source and MIT license are identified; the attribution caveat and the remaining owner decisions in section 9 are open but do not affect the infrastructure.

**Operational model validation is not ready and is blocked:** the local dataset files are blanked copies of unknown cause, they cannot be shown to match the official archive, and the model is non-discriminating. It must remain experimental and advisory-only.

Phase 1 is **not accepted**. Nothing was committed or staged, and Phase 2 has not started.
