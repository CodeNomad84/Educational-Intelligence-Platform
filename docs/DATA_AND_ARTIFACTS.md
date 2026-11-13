# DATA, ARTIFACTS AND LOCAL SECRETS (Phase 1)

## Scope: single-school prototype (CURRENT)
Phase 1 is a **single-school prototype**. It has **no multi-tenant isolation**: there is no school key on any table, and no cross-school access control exists or has been tested. It must not be described or deployed as multi-school ready. A school key is a TARGET (see `ARCHITECTURE.md`); adding it is a separate, owner-approved change.

## Dataset in `data/student-performance-attendance/` (kept locally, never in Git)

**Rule:** the local CSV files must **not** be imported into real school records (the `students` tables, the Django student import, or any production database). They are used only for offline development and model training (`fastapi_core/data_pipeline.py`) and are excluded from Git (`/data/` in `.gitignore`). They are preserved unchanged.

### Official source (verified from the Kaggle page on 2026-10-12)
Read with a plain HTTP GET of `https://www.kaggle.com/datasets/marvyaymanhalim/student-performance-and-attendance-dataset` and its embedded schema.org metadata (the web-fetch tool was blocked for kaggle.com).

| Item | Value | Status |
|---|---|---|
| Title | Student Performance and Attendance Dataset | VERIFIED (page metadata) |
| Creator | Marvy Ayman Halim (Kaggle user `marvyaymanhalim`) | VERIFIED |
| Canonical URL | https://www.kaggle.com/marvyaymanhalim/student-performance-and-attendance-dataset (the owner supplied the `.../data` tab URL of the same dataset) | VERIFIED |
| Version | 1 | VERIFIED (page metadata) |
| Last modified | 2025-03-10T22:05:09Z | VERIFIED (page metadata) |
| Official archive | one zip, 5,849,540 bytes (`contentSize`); download requires a Kaggle login | VERIFIED (metadata); archive **not downloaded** |
| License named | MIT | VERIFIED (page metadata). **Caveat:** the linked text is a generic MIT template carrying copyright lines of unrelated parties, not the dataset creator's; whether that satisfies the attribution/notice requirement is **OWNER INPUT REQUIRED** |
| Synthetic | The creator's description calls it a "synthetic dataset" with intentionally injected errors | Creator's own statement; **not independently verified** |
| Person data / anonymization | No statement beyond "synthetic" | **NOT VERIFIED** |
| Local files hash-matched to the official archive | not possible without the archive | **NOT VERIFIED** (see below: they cannot be the official content) |

### Schemas of the local files
| File | Columns |
|---|---|
| `students.csv` | Student_ID, Full_Name, Date_of_Birth, Grade_Level, Emergency_Contact |
| `attendance.csv` | Student_ID, Date, Subject, Attendance_Status |
| `homework.csv` | Student_ID, Subject, Assignment_Name, Due_Date, Status, Grade_Feedback, Guardian_Signature |
| `performance.csv` | Student_ID, Subject, Exam_Score, Homework_Completion_%, Teacher_Comments |
| `teacher_parent_communication.csv` | Student_ID, Date, Message_Type, Message_Content |

### Local file integrity (read-only checks, 2026-10-12; aggregate counts only)
| File | Rows in file | Non-empty rows | SHA-256 (first 16 hex) |
|---|---|---|---|
| `students.csv` | 12,156 | 49 | `7b11ad655f72cc16` |
| `attendance.csv` | 364,680 | 49 | `5353467f648fa902` |
| `homework.csv` | 60,780 | 49 | `908077f28a73640f` |
| `performance.csv` | 36,468 | 49 | `88febf750bab2ec0` |
| `teacher_parent_communication.csv` | 24,312 | 49 | `bc96ae69eb51541b` |

- Each file holds **49 non-empty rows followed by blank filler rows** (`,,,,` lines with CRLF endings). The 49 rows are the first 49 rows of every file (contiguous); 99.6–100 % of all cells are missing.
- Row counts stand in exact ratios 1 : 30 : 5 : 3 : 2 (students : attendance : homework : performance : communication).
- The 49 IDs per file are unique (format `S` + 5 digits). `students.csv` retains IDs 1–49; the other files retain IDs spread from about 4 to 12,119. Overlap with `students.csv` is 0, 1, 0, 0 of 49; no ID appears in all five files. The retained rows therefore do not join.
- The retained rows show the data-quality problems the page describes as intentional (scores over 100, `%` signs and negative completion rates, mixed date formats, lower-case names).
- The five files together compress to 12,921 bytes, while the official archive is 5,849,540 bytes: **the local files cannot contain the official content.**
- `data_pipeline.load_and_clean_data()` (read-only) returns 49 rows x 9 columns.

**Interpretation, not proven:** the files are cleared copies of a larger dataset whose row structure was kept. **The reason for the blanking and who or what caused it are unknown.** The official archive must be downloaded by the owner (Kaggle login) into a new directory and compared before the local files are used for anything.

## Model artifacts (excluded from Git)
| Artifact | Path | Produced by |
|---|---|---|
| Risk model weights | `fastapi_core/models/student_risk_model.pth` (dated 2026-07-09) | `fastapi_core/train_nn_model.py` (`train_model()`, run as a script) |
| Feature scaler | `fastapi_core/models/scaler.joblib` (dated 2026-07-09) | same script |
| Legacy sklearn model | `fastapi_core/student_model.joblib` | `fastapi_core/train_model.py` (not used by the running service) |

- FastAPI **refuses to start** if `student_risk_model.pth` or `scaler.joblib` is missing (`fastapi_core/main.py`). A fresh checkout therefore needs the artifacts generated or supplied before `docker compose up`.
- Documented regeneration (not executed in review; it overwrites the artifacts): from `fastapi_core/` with the project's dependencies, `python train_nn_model.py`. It reads the CSVs through `data_pipeline.py` (`/data/student-performance-attendance` in the container). No download URL exists, and none is invented here.
- **Reproducibility: NOT VERIFIED.** The split is seeded (`random_state=42`) but torch is not, the training environment and the dataset used for the existing artifacts are not recorded, and the current CSVs provide only 49 usable rows. Retraining from these files would not reproduce the existing weights.
- **Model quality (re-checked 2026-10-12, nothing retrained):** on five fixed synthetic inputs the existing model's pre-sigmoid outputs are -30.685, -35.945, -20.861, -40.525, -52.253 (probability 0.0 for every input), i.e. it does not discriminate between inputs. It stays **EXPERIMENTAL/PROTOTYPE and advisory only** (`AI_GOVERNANCE.md`); its output must not be relied on.
- **Operational model validation is blocked** until coherent data (verified against the official archive), a documented target label, a reproducible training procedure and meaningful evaluation metrics exist.
- **Torch:** the image keeps `torch 2.0.1+cu117` (owner decision: CPU migration not approved). It runs on CPU; the CUDA libraries are unused in the current CPU-only VMware environment. A GPU deployment would need its own host, driver, container runtime and a separate image (not part of Phase 1).

## Local secret files (all gitignored; never commit)
| File | Contents | Read by |
|---|---|---|
| `.env` | Django `SECRET_KEY`, Django DB owner password (`school_user`), non-secret settings. It does **not** contain `SERVICE_JWT_SECRET`. | Django, Celery, Celery Beat; PostgreSQL gets only the `POSTGRES_*` values that Compose interpolates from it, not the file itself |
| `.env.service` | `SERVICE_JWT_SECRET` (>= 32 random chars, different from `SECRET_KEY`) | Django, FastAPI |
| `.env.fastapi` | `DB_USER=fastapi_user` and its password (least-privilege role) | FastAPI only |
| `.env.minio` | non-default MinIO root credentials | MinIO only |
| `.env.llm` | optional AI provider config: `LLM_PROVIDERS`, `LLM_SCHOOL_MAP`, `LLM_DAILY_CAP` and one `LLM_KEY_*` value (change 0043, ADR-0008). Absent = AI off. Template: `.env.llm.example` (committed, placeholders, empty key) | FastAPI only — Django, Celery, PostgreSQL, MinIO and the frontends never receive it |

`.env.example` holds placeholders only. Generate values with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.

## Least-privilege database role for FastAPI
FastAPI connects as `fastapi_user` (not a superuser), which holds `CONNECT`, `USAGE` on schema `public`, and `SELECT, DELETE` on `documents` only. It cannot read any Django-owned table. The full, repeatable setup, verification and rollback procedure is in **`FASTAPI_DB_ROLE.md`**. Re-enabling document ingestion or search later needs `INSERT` and `USAGE` on `documents_id_seq` (an explicit, reviewed grant).
