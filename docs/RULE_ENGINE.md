# RULE_ENGINE (created with 0031, 2026-11-02; derived from the code, code wins)
- **Closed metrics** (`risk/signals.py::METRICS`): absence_rate, absence_shift_pp, late_count, absent_days, max_consecutive_absences, avg_score, grades_count, subject_drop, concern_count (concern entries only, counts, decision 50).
- **Rule** (`risk.Rule`): versioned row per school, status draft > pending_approval > active > paused > archived, params hash, human simulation + approval before Active (`risk/lifecycle.py`). Risk types only academic / attendance / behavioral.
- **Catalog** (`risk/catalog.py`): 13 read-only templates (decisions 54), families with ranks (decision 53). Activation = a DRAFT rule with provenance.
- **Runner** (`risk/rules.py::run_school`): reads only through `students.access.system_scope_*`, one explicit school; circuit breaker, cooldown, family supersession, upgrade in place; alerts through `risk.services.raise_alert`; run counts in `RuleRun`.
- **Import** (`risk/catalog_services.py`): see decision 55. **Notifications**: `risk/notifications.py` (decision 51).
