# 0028 — Decision pack P3 to P8 (PROPOSAL, 2026-11-01)

Written for the owner. Purpose: put every open decision between today and P8 in one place, each with a recommended default, so they can be approved or changed in one pass and the next phases can run with few stops.
Basis: the repository (`PROJECT_CHECKLIST.md`, `0026-p3-exit-plan-NOTE.md`, `SECURITY.md`, `ROADMAP.md`), common practice for school platforms, and Panorama Education's product list (fetched 2026-11-01 from panoramaed.com/products: Student Success = early warning + MTSS + interventions; Solara = AI grounded in district data, "walled garden"; Surveys & Engagement; Pathways = graduation/career; Class Companion = practice; 200+ integrations; SOC 2 / FERPA claims; vendor claims, NOT independently verified).
Legend: **DECIDED** = owner decision recorded here · **PROPOSED** = recommended default waiting for approval (approve by ID, e.g. "approve P3-2, P3-3; change P7-2 to ...") · **LEGAL** = needs a legal adviser, the recommendation is only a starting point.

## 1. Owner decisions recorded 2026-11-01 (DECIDED)
| ID | Decision | Consequence in code and docs |
|---|---|---|
| OW-1 | **Hosting:** shared instance on servers inside Iran for most schools; a dedicated install on the school's own server for large schools or on request. | One codebase, two deployment profiles. Shared = multi-school (S1-S6 already built); dedicated = the same code with one `School` row. Every setting comes from the environment; nothing provider-specific in code. Closes the "where" half of O2; "who operates day to day" stays open (P3-1). |
| OW-2 | **Backups are mandatory** (data-loss risk on Iranian hosting). | Backups move into the P3 code track as slice C-K (scripted, encrypted, rotated, off-site, rehearsed). Proposed policy: P3-2. |
| OW-3 | **Domain `.ir`**, HTTPS chosen to fit it. | TLS by any ACME CA or a commercial certificate; no reliance on one CA or CDN. Proposed details: P3-3. |
| OW-4 | **Server-side, provider-agnostic controls**: whatever can be enforced on the server (TLS, headers, rate limits, upload limits, scanning, backups) is done with generic open tools, not with one hosting provider's proprietary features. | nginx (or any reverse proxy) + Django settings + open tools (ClamAV, fail2ban/firewall, `pg_dump`, `openssl`). A provider's CDN/WAF may be added in front but the platform must stay secure without it. |
| OW-5 | **No real student data yet.** Goal: reach the end of the frontend and an MVP that can be shown to school principals. | Synthetic data only (unchanged hard rule). The demo track gets priority after the P3 code tasks (P8-1). |
| OW-6 | **AI assistants in two provider classes:** (1) external API providers (for example ChatGPT, DeepSeek, or a reseller such as GapGPT); (2) offline/local models (for example Ollama, Hermes-family models). | One provider adapter with two classes; per-school choice; data rules per class (P7-1..P7-4). The hard rule "no student PII to external LLMs" stays. |
| OW-7 | **Push** allowed to any branch except `main`. | `CLAUDE.md` §6a-bis and §7. |

## 2. P3 — Security baseline (exit = real data may be loaded in one school)
| ID | Question | Recommended default | Why | Reversible |
|---|---|---|---|---|
| P3-1 | Who operates the platform day to day (root, DB access) | One named operator plus one deputy for the shared instance; for a dedicated install, the school names its own operator and signs a short operations sheet (backups, updates, who has keys). Every root/DB holder listed in `RUNBOOK.md`. | Smallest workable model; a named list is what an audit asks for first. | yes |
| P3-2 | Backup policy | **3-2-1 inside Iran:** nightly encrypted `pg_dump` + media archive; keep 14 daily, 8 weekly, 12 monthly; one copy on the server, one on S3-compatible object storage of a **different provider in a different city** (any S3-compatible service, or `rsync`/SSH target), one monthly offline copy held by the owner. Encryption with a key that never lives on the server (public-key encryption, private key offline with owner + deputy). Restore rehearsal monthly and after every major upgrade, logged. Target RPO 24 h (later: WAL archiving for RPO 15 min on the shared instance), RTO 4 h. Dedicated installs: same script, off-site target chosen by the school. Backups stay inside Iran by default. | Hosting risk named by the owner; 3-2-1 is the common standard; a key off the server means a stolen server does not leak the backups. | yes |
| P3-3 | HTTPS for `.ir` | TLS 1.2+ at the reverse proxy; certificate from any ACME CA (renew at 30 days left, expiry monitored) or a commercial certificate; HSTS staged (1 hour, then 1 week, then 1 year), `includeSubDomains` only when every subdomain is HTTPS, **no preload** until 3 months stable; secure cookies; HTTP redirects to HTTPS at the proxy. Whether a given CA issues for `.ir` and is reachable from the hosting network: **NOT VERIFIED**, check at setup; the design does not depend on one CA. | Common baseline; staged HSTS avoids locking users out by mistake. | yes (HSTS: only after max-age expires) |
| P3-4 | Resilience to international internet outages | **No external CDN, fonts or scripts in pages**: Bootstrap, icons and Chart.js are served from the platform itself. Today 4 template references load from `cdn.jsdelivr.net` (`dashboard/base.html`, `grade_dashboard.html`). | A server inside Iran keeps working on the national network only if the pages need nothing from abroad. | yes |
| P3-5 | Upload policy (C-S) | Size limit 10 MB per file at proxy and app; types allowed by extension and content check: CSV, XLSX, PDF, DOCX; ClamAV scan where installed, otherwise the documented status "no scan" shown to the operator; uploads never executed or served from the app domain without `Content-Disposition: attachment`. | Generic, server-side, matches OW-4. | yes |
| P3-6 | Authorization matrix (O7) | Make the **per-feature tables** in `SECURITY.md` normative and retire the old generic table (its cells predate the real roles). | The per-feature tables are what the tests pin. | yes |
| P3-7 | Password policy | Django validators: minimum length 10, common-password and numeric-only checks, similarity to username; applies at next change, existing passwords keep working. | Server-side, no dependency. | yes |
| P3-8 | 2FA for SchoolAdmin and platform operators | TOTP after the demo (needs a dependency such as `django-otp`, so an L3 proposal); until then: throttling (built), audit (built), short sessions for admins (8 h). | Valuable, but not needed for a synthetic-data demo. | yes |
| P3-9 | Legal, consent, retention (O1) | **LEGAL.** Starting points: parental consent at enrolment for the platform and separately for counseling referrals; retention: alerts/plans/follow-ups 3 years after the student leaves, risk events 3 years (doc 12), exam attempts 2 years, audit log 3 years, counseling records per the counselor's professional rules; deletion on request handled by the SchoolAdmin with an audit event. Data stays in Iran. | Needed before real data; cannot be decided by code. | — |
| P3-10 | Django admin closure (C-A, Tier C) | Superuser and Django admin see platform tables only (schools, modules, groups); user lists filtered to staff accounts; no school account can be `is_staff`; student/parent accounts never listed. | Closes S9 before real data. Needs your go because it changes access. | yes |

## 3. P4 — Core domain architecture
| ID | Question | Recommended default | Why |
|---|---|---|---|
| P4-1 | Data layers (Raw > Validated > Canonical > Derived) | Keep the Django models as the canonical layer; add provenance only to derived rows (rule hits, alerts, mission reports already carry version fields); no new data platform. `DATA_MODEL.md` written at P4 start from the models. | Zero rewrite; derived provenance is what the 360 needs. |
| P4-2 | Grading scale and attendance vocabulary (D-07, D-08) | Per-school setting with 0-20 as default (Iranian scale), stored scale on each grade record so mixed scales stay correct; attendance codes from `VocabularyTerm`. | Configuration over code; matches Iran. |
| P4-3 | Integrations (Panorama: 200+ systems) | Excel/CSV import (built) stays the only path for the MVP; a documented import format per entity; integration with national/school systems (for example SIS exports) only on a school's request. | Panorama's moat is integrations, but Iranian schools mostly have spreadsheets. |

## 4. P5 — Student 360 and analytics
| ID | Question | Recommended default | Why |
|---|---|---|---|
| P5-1 | Principal dashboard (the demo screen) | One school page for the SchoolAdmin/principal: students needing attention by grade/class, attendance and grade trends, open alerts by status, interventions due, rule quality; aggregates with groups under 5 withheld (existing rule). | This is Panorama Student Success's first screen and what principals will judge. |
| P5-2 | MTSS-style tiers | Show a **support level** per student (1 universal, 2 targeted, 3 intensive), **derived** from open alerts and active interventions, never typed by hand, labelled "derived, not a diagnosis"; visible to who already sees the alerts. | Familiar MTSS language without a new access path. |
| P5-3 | Behavior log (backlog item 6) | Simple positive/concern entries by staff, school-scoped, feeding a rule signal; Grade Lead and SchoolAdmin read; parents see positive entries only. Parent visibility = **DECISION REQUIRED** (access). | Panorama lists behavior analytics; small model. |
| P5-4 | Printable report card (backlog) | Per-term printable page from existing grades (HTML print stylesheet, no PDF dependency). | Principals expect it; no new data. |

## 5. P6 — Rules, risk, alerts, interventions (mostly built)
| ID | Question | Recommended default | Why |
|---|---|---|---|
| P6-1 | Strategy library (Panorama: 700+ strategies) | A school-editable library of intervention strategies (title, tier, description, typical duration) seeded with ~30 generic Persian entries, picked when creating a plan. | Turns plans from free text into something countable; low risk. |
| P6-2 | Notifications | In-app notifications first (alert raised, follow-up due); SMS/e-mail later through one generic adapter (any Iranian SMS gateway), opt-in per school, no student details in SMS text beyond "you have a new item". | Provider-agnostic (OW-4); SMS leaves the platform, so minimal content. |
| P6-3 | Effectiveness | Outcome per plan (built) aggregated per strategy, groups under 5 withheld. | Uses existing data. |
| P6-4 | Referral consent states (C-R) | After P3-9 only. | Legal dependency. |

## 6. P7 — AI assistants (two provider classes, OW-6)
| ID | Question | Recommended default | Why |
|---|---|---|---|
| P7-1 | Adapter | One provider adapter in FastAPI speaking the **OpenAI-compatible chat API** (the common format of hosted APIs, resellers and Ollama's `/v1` endpoint), configured per school: `class` (external / local), base URL, model, key from the environment; no vendor SDK. | Covers both classes and every named provider with one small client; swapping providers = configuration. |
| P7-2 | What may go to the **external** class | Only non-personal content: school policy documents, curriculum text, question drafting from a topic, generic pedagogy. **Never** student names, national ids, grades, alerts, counseling or free text about a student. Outbound text passes a filter (national-id and name patterns from the school's roster) and is refused on a match. | Hard rule in `CLAUDE.md` §7; Panorama's "walled garden" claim points the same way. |
| P7-3 | What may go to the **local** class | School data the requesting user may already see (ACL before retrieval, as designed), never counseling data without an approved policy; runs on the platform's or school's own server. | Data stays on the server. |
| P7-4 | Defaults | Both classes **off** per school; the SchoolAdmin sees which class is active; every answer labelled "AI, advisory, may be wrong"; existing per-school call caps apply; usage logged without content. | Matches `AI_GOVERNANCE.md`. |
| P7-5 | First AI feature | Staff assistant (`advisor_ai`) over **school documents** (non-personal RAG), then exam question suggestions (exams Slice 4), then the student tutor on the local class. | Lowest data risk first; principals see value early. |

## 7. P8 — Frontend
| ID | Question | Recommended default | Why |
|---|---|---|---|
| P8-1 | Order after P3 code | **Demo track before P7:** P5-1 principal dashboard, P5-2 tiers, P6-1 library, UI polish, then P7. | OW-5: the goal is a demo to principals. |
| P8-2 | React or server-rendered pages | **For the MVP: keep Django templates + Bootstrap 5 RTL** (self-hosted, P3-4) with small JavaScript where needed (charts); React only for screens that truly need rich interaction, added as islands; a full React SPA is **DEFERRED** after pilot feedback. This is a change to the TARGET in `ARCHITECTURE.md` and needs your explicit approval. | Zero rewrite; every existing page already works and is access-tested; a SPA would duplicate all views behind a new API and re-open authorization work. |
| P8-3 | Design system | One base template, Persian font self-hosted (Vazirmatn, OFL licence), consistent cards/tables, dark mode optional, mobile-friendly. | Demo quality at low cost. |

## 8. Not decided here
Pricing and trial length (O9), billing, S7-S10 (second school), Google sign-in/LTI: unchanged, still waiting for the owner.
