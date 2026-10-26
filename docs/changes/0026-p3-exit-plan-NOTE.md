# 0026 — P3 exit plan: what the owner starts now, and what code does, in order (NOTE, 2026-10-26)

Source: the P3 exit table of `0021-mvp-gap-REPORT.md` and the exit criteria in `docs/SECURITY.md` ("Security Baseline Exit Criteria (Phase 3)"). "P3 exit" means real students' data may be loaded in one school. Docs only; nothing is implemented. Dependencies are marked `needs`; "unblocks" says what becomes possible.

## A. Owner / legal / operations tasks (slow; start now, they do not need code)
| # | Task | Owner | Needs | Unblocks | Notes |
|---|---|---|---|---|---|
| O1 | **Legal, consent and retention policy** for children's data: what may be stored, parental consent wording, retention periods (alerts, plans, risk events 3 years per doc 12, exam attempts, counseling records, audit log), deletion and access requests, who is the data controller | owner + legal adviser | nothing | C-R (consent states), C-D (retention commands), questionnaires, real counseling referrals, the final text of the PENDING POLICY items in `docs/manuals/` | Longest lead time; start first. Decisions already waiting: retention period, parent access to the individual record (C5a-R3/C6), consent before a case is recorded |
| O2 | **Hosting and operator model**: where it runs (country, provider or school server), who operates it day to day, who has root and database access | owner | O1 (data location rules) | C-H (production settings and HTTPS), O3, O4 | Decide before buying anything |
| O3 | **Off-site encrypted backups**: where copies go, who holds the key, retention of backups, a restore rehearsal on the real infrastructure | owner / operator | O2 | the P3 backup criterion | Code side (rehearsal script) exists; this is infrastructure |
| O4 | **HTTPS and reverse proxy**: domain, certificate, who renews | operator | O2 | C-H; the throttle's trusted-proxy setting | |
| O5 | **Secrets rotation**: rotate every secret that was ever committed or shared (Django secret key, DB passwords, MinIO and FastAPI credentials); store them outside the repository; record who has them | owner / operator | O2 (where secrets live) | the P3 "secrets rotated" criterion; closes S-03 | Rotation, never a history rewrite (hard rule) |
| O6 | **Decide the external-LLM question** (any provider at all, which, which country) | owner | O1 | the tutor and `advisor_ai`; it is not a P3 blocker if those stay off | Can be "no, not now" |
| O7 | **Approve the authorization matrix** in `SECURITY.md` (the generic table predates the real roles; the per-feature tables are current) | owner | nothing | the P3 "matrix implemented and tested" criterion (docs half) | I prepare the text, you approve |
| O8 | **Pilot agreements**: which school, which grades, which teachers, written agreement and parents' information | owner | O1 | the first real-data load | Also: a named SchoolAdmin and a named platform operator |
| O9 | Pricing and trial-length policy | owner | nothing | billing work (not a P3 blocker) | Listed so it is not forgotten |

## B. Code tasks (I do them; each is a small slice with tests and a security review)
| # | Task | Needs | Unblocks | Size |
|---|---|---|---|---|
| C-H | **Production settings hardening**: HTTPS-only cookies, HSTS, allowed hosts, debug off, secure proxy header, logging that never contains personal data; a check command that fails on unsafe settings | O2, O4 for real values; can start with the checks now | the P3 "hardened production settings" criterion; throttle behind a proxy | 1-2 commits |
| C-A | **Django admin closure (S9)**: school-scope or remove the user, assignment and staff lists; make sure no school account can be staff; superuser must not see student/parent accounts (national-id usernames) | nothing | the P3 "scoping on every endpoint" criterion; closes the superuser account-list caveat of `0024` | 2 commits (Tier C) |
| C-B | **`create_school` command** with an audit event (school creation is not audited today) | nothing | safe onboarding of the second pilot school; recommended before it | 1 commit |
| C-D | **Dependency audit** and the tracked pickle/joblib model files (S-11): list, pin, remove or justify | nothing | the P3 "dependency audit" criterion | 1 commit |
| C-S | **Upload validation policy** for CSV/Excel/documents: size, type, malware-scan policy (a scan, or an explicit documented "none") | O7 for the policy line | the P3 "upload validation" criterion | 1 commit after the decision |
| C-L | **Audit log completeness pass**: list pages, the Student 360 tile, alert and plan lists, exports (there are none), admin actions; add the missing events | nothing | the P3 "audit log for student-data access" criterion | 1-2 commits |
| C-G | **Gate re-run on real data**: `check_access_switch_ready --multi-school` and `compare_access_parity --multi-school` on the real data copy before loading | the real data copy (after O1, O8) | the go-live step itself | a procedure, run by me with you |
| C-R | **Referral consent states (roadmap 2.6)**: submitted, counselor declined, awaiting parent consent, parent declined, active, closed; parental consent with no exception path | O1, and the crisis/escalation policy (D18) | real counseling referrals with children | 3-4 commits (Tier C) |
| C-T | **Retention commands**: cleanup of alerts, plans, risk events, exam attempts, audit rows after the period | O1 (periods) | the legal retention duty | 1-2 commits |
| C-P | **Parent individual-record access** per decision (C5a-R3/C6) | O1 and your decision | parents on the platform with real children | 1 commit |
| C-Q | Whole-branch **`/security-review`** and a final **permission-test sweep** green in CI (the CI job exists) | all other C tasks done | the last P3 criterion | 1 session |
| C-M | Manual TO VERIFY / PENDING POLICY items closed (`docs/manuals/`) | O1, O6, C-R | publishable manuals | with each slice |
| C-F | Optional before the second school: FastAPI module claim in the service token (S5/S8-S10 family); S7/S8/S9/S10 per the second-school gate | second school planned | the second real school (not a single-school P3 blocker) | later |

## C. Suggested order
1. **This week, owner:** O1, O2, O7, O8 (start the conversations; they have the longest lead time and gate the rest). Then O3, O4, O5 once O2 is decided.
2. **In parallel, code (no dependencies):** C-B, C-D, C-L, then C-A (Tier C, needs your approval to start). C-H starts with the check command and finishes when O2/O4 give real values.
3. **After O1:** C-T, C-P, C-R (consent states) and the questionnaires proposal.
4. **After O2-O5 and the code tasks:** C-S, C-G on a copy of the real data, C-Q, then your sign-off on the exit criteria.
Not on the P3 critical path: rules and alerts engine (`0025`), exam slices 3-4, questionnaires, LLM work, billing, S7-S10 (second school), React frontend.

## D. What each criterion of `SECURITY.md` needs
| Exit criterion | Owner tasks | Code tasks |
|---|---|---|
| Authorization matrix implemented and tested | O7 | tests exist; C-Q sweep |
| Object/school scoping on every student-data endpoint | — | done for Django (S3/S4 tests); C-A closes the admin gap |
| Service-to-service auth | — | done (ADR-0002, Phase 1); module claim C-F optional |
| Secrets from env only, rotated | O5 | C-H (settings checks) |
| Audit log for student-data access and exports | — | C-L (exports do not exist) |
| Upload validation | O7 | C-S |
| Production settings hardened | O2, O4 | C-H |
| Dependency audit | — | C-D |
| Permission tests green in CI | — | done; kept green |
| Backups (not a listed criterion, required for real data) | O3 | rehearsal script exists |
| Legal / consent / retention (not a listed criterion, required by you) | O1 | C-T, C-R, C-P |
