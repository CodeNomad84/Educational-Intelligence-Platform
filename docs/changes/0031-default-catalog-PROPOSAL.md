# 0031 — Default catalog of rules, risk types, alerts and interventions (PROPOSAL, Level 2)

Status: **PROPOSED — awaiting owner review of the catalog content. Nothing is built.** Date: 2026-11-02. Truth labels per `CLAUDE.md` §2.

## 1. What the owner asked
A default catalog based on established practice (rules, risk types, alerts, interventions), plus school-specific additions or replacements through forms or an Excel import.

## 2. Research basis (cited from memory; **NOT VERIFIED** against the sources, to be checked before any external use)
| Source | What it supports | Status |
|---|---|---|
| Balfanz, Herzog and Mac Iver (2007), *Educational Psychologist* 42(4), "Preventing student disengagement and keeping students on the graduation path in urban middle-grades schools" | The ABC early-warning indicators: Attendance, Behavior, Course performance, as predictors of dropping out | NOT VERIFIED (citation from memory) |
| Allensworth and Easton (2005, 2007), University of Chicago Consortium on Chicago School Research, "On-Track indicator" | Course performance plus credits as a strong early signal; the idea of a simple on-track flag | NOT VERIFIED |
| Attendance Works (attendanceworks.org), chronic absence = missing about 10% or more of enrolled days | A 10% absence-rate watch level; tiers of response (prevention, early intervention, intensive) | NOT VERIFIED; a US convention, not Iranian |
| Sugai and Horner (PBIS / MTSS literature); Response to Intervention tiers | Three tiers: universal, targeted, intensive; escalate only on data and review | NOT VERIFIED |
| What Works Clearinghouse / Education Endowment Foundation toolkit entries (small-group tuition, peer tutoring, feedback, behaviour interventions) | Typical effective generic strategies for the tier 2 list | NOT VERIFIED |
| Panorama Student Success and similar vendors (marketing pages) | Product shape only (indicators plus tiers plus library) | **Vendor claims, unverified; used for product shape, not for thresholds** |

Adaptation to Iran: scores on the school's own scale (`Grade.scale_max`, default 20), thresholds stored as **percent of the scale** and converted when a template becomes a rule; Persian labels; weekly school week (Friday excluded already in the seed). **No claim is made about Iranian law or ministry thresholds: every number below is a configurable default proposal, not a legal limit.** The platform's standing rules stay: deterministic, explainable, human review, no emotional or family automated rules, small groups withheld.

## 3. Proposed defaults (all "unvalidated until the school's own teachers review them", as today)
### 3.1 Rule templates (existing closed metrics only; built = already in `risk.rules.STARTERS`)
| Code | Title (fa) | Metric, op, threshold, window | Severity | Intended tier on acceptance | Status |
|---|---|---|---|---|---|
| attendance_shift | افزایش غیبت نسبت به دورهٔ قبل | absence_shift_pp ≥ 10, 30 d vs 60 d, min 5 | yellow | 2 | built |
| repeated_absence | غیبت مکرر در دو هفتهٔ اخیر | absent_days ≥ 3 or max_consecutive_absences ≥ 2, 14 d | yellow | 2 | built |
| low_average | میانگین پایین نمرات اخیر | avg_score < 60% of scale (12 of 20), 45 d, min 3 | yellow | 2 | built |
| grade_drop | افت نمرهٔ یک درس | subject_drop ≥ 15% of scale (3 of 20), 45 d vs 75 d, min 2 | orange | 2 | built |
| repeated_concerns | نگرانی‌های رفتاری مکرر | concern_count ≥ 3, 30 d | yellow | 2 | built (draft) |
| chronic_absence_watch | غیبت مزمن (نظارتی) | absence_rate ≥ 10, 60 d, min 20 | yellow | 1→2 | new |
| chronic_absence_high | غیبت مزمن شدید | absence_rate ≥ 20, 60 d, min 20 | orange | 3 | new |
| absence_run | غیبت پیاپی طولانی | max_consecutive_absences ≥ 5, 14 d, min 5 | orange | 2 | new |
| late_pattern | تأخیر مکرر | late_count ≥ 5, 30 d | yellow | 1 | new |
| failing_average | میانگین بسیار پایین | avg_score < 50% of scale (10 of 20), 45 d, min 3 | orange | 3 | new |
| off_track_combo | نیمه‌رها‌شدن هم‌زمان نمره و حضور | avg_score < 60% AND absence_rate ≥ 10, 45 d | orange | 3 | new (ABC combination) |
| concern_surge | افزایش نگرانی‌های رفتاری | concern_count ≥ 5, 30 d | orange | 2 | new |
| concern_with_absence | نگرانی رفتاری همراه با غیبت | concern_count ≥ 2 AND absence_rate ≥ 10, 30 d | orange | 2 | new |
All new templates are behavioral / attendance / academic types only. Cooldown default 14 days, as today. Scale-based thresholds are stored as percents and converted with the school's `grade_scale_max` (the existing fail-closed rule applies: no scale, no activation).

### 3.2 Risk types and alert types
Rule risk types stay `academic`, `attendance`, `behavioral`. Manual alert types stay the seven existing ones (academic, emotional, behavioral, social, attendance, motivation, family; emotional and family remain manual, human-raised and text-gated). **No new type is proposed.** Severity labels unchanged (green, yellow, orange, red); rules produce yellow or orange only.

### 3.3 Intervention strategies (extends the 30 already seeded; all generic, no student data)
Proposed additions (≈18): tier 1: دقایق مرور پایان درس، آموزش مهارت یادداشت‌برداری، برنامهٔ هفتگی حضور و خوشامدگویی، گفت‌وگوی کلاسی دربارهٔ اهداف؛ tier 2: تماس هفتگی کوتاه معلم با خانواده دربارهٔ حضور، هم‌یار حضور (دوست حمایتی)، بازخورد سریع و هدف‌گذاری کوتاه‌مدت، تکلیف تقسیم‌شده به گام‌های کوچک، جلسهٔ مرور نمرات با دانش‌آموز، برنامهٔ ورود و خروج (check-in/check-out) با یک بزرگسال، آموزش مهارت مدیریت زمان؛ tier 3: برنامهٔ حمایتی فردی با تیم (معلم، مسئول پایه، خانواده)، بررسی موانع رفت‌وآمد و خانوادگی با مدیریت، هماهنگی با مشاور از مسیر ارجاع رسمی، بازبینی ماهانهٔ برنامه با تاریخ ارزیابی مجدد. Tier 3 items that involve professionals are **referral steps only**; the platform never prescribes treatment. Each strategy keeps its intervention type and the typical duration.

### 3.4 Metrics that would need a NEW read path (NOT in this proposal's defaults; each needs owner approval)
| Candidate | Why | Read path needed |
|---|---|---|
| homework completion rate | common ABC-adjacent signal | `Homework` is not school-scoped today; needs a scoped system read |
| exam results (exams module) | course performance from tests | system read of exam sessions; module licensing |
| grade trend slope | steadier than a two-period drop | none (computed from existing grades) but a new function: owner may approve as "no new read path" |
| mission indicators (mission module) | strengths-based signals | system read of mission records |
None is needed for 3.1.

## 4. Design
- **System templates**: a read-only, versioned catalog in code (`risk/catalog.py`: `CATALOG_VERSION`, template dicts; same shape as `STARTERS`). Not editable by any school or user. Strategy defaults extend `seed_strategies` (already per-school editable).
- **Use by a school**: *Activate/clone* creates a **Draft** `Rule` for that school from a template (new nullable columns `Rule.template_code` and `Rule.template_version` for provenance). The existing lifecycle then applies unchanged: simulate (aggregates only), submit, approve, Active. *Replace* = pause the default-derived rule and activate the school's own. A later catalog version never changes an existing rule; the school sees "newer version available" and may clone again.
- **Excel import** (`/rules/import/`, SchoolAdmin only, own school): downloadable template workbook (sheets `Rules` and `Strategies`, header row, example rows, allowed values in a notes sheet). Upload `.xlsx` only, size and row caps (1 MB, 200 rows), read without evaluating formulas, ignoring macros. Each row goes through **exactly** the existing validators (`validate_clauses`, `validate_rule_fields`, `StrategyForm`): unknown metric, emotional/family type, out-of-scale threshold, duplicate code are row errors. Valid rule rows land as **Draft** (never Active); strategy rows land **inactive** until the admin enables them. A two-step flow (dry-run report, then confirm) with a per-row report (created / refused with a fixed reason code). One audit event per import (counts only: `rules_import` / `strategies_import`). Cells beginning with `=`, `+`, `-`, `@` in text fields are refused (spreadsheet formula injection).
- **No new automatic behavior**: nothing runs until a human approves a rule; breaker, cooldown and withheld-small-groups rules are unchanged.

## 5. Impact (CHANGE_GUIDE headings)
- **Data**: `Rule.template_code`, `Rule.template_version` (nullable, one migration, reversible); catalog in code; audit actions `rules_import`, `strategies_import`, `rule_from_template`.
- **API**: none public. **UI**: catalog page (`/rules/catalog/`), import page, the existing rules pages unchanged; Persian only.
- **Security**: no new read path for 3.1; import is school-scoped (school from the session via `_current_school`, never from the file), role SchoolAdmin only, CSRF, file limits, no formula evaluation, row-level refusals, audit. Emotional and family automated rules stay impossible (validator plus test).
- **Tests**: catalog templates all validate and start Draft; import refuses each bad class; another school's id in a file is ignored/refused; Persian digits; mutation checks on the import's school scope and on "lands Draft"; a template never becomes Active without simulation and approval.
- **Docs**: `RULE_ENGINE.md` (deferred doc created at this work), manuals (school-admin), `CHANGE_GUIDE`, `DECISIONS_BY_CODE`, `SECURITY.md` (import row).
- **Level**: L2 (new feature on existing rules; no access rule, tenancy or read-path change). Reversible.

## 6. DECISION REQUIRED (owner)
1. Review the **content** of 3.1 (thresholds and Persian titles) and 3.3 (strategy titles): approve, edit, or drop each row. Recommended: have a school counselor review the thresholds before any school activates them.
2. Imported strategies land **inactive** (recommended) or active?
3. Is "percent of scale" storage for score thresholds acceptable (recommended), or fixed 0-20 numbers?
4. Which of the candidates in 3.4 (if any) should be proposed next.
