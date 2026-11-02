# DATA_MODEL — written at the start of P4 (2026-11-02) from the Django models

**Status: CURRENT, derived from the models (code wins).** Regenerate the table after a model change. Layers follow `CLAUDE.md` §8
(Raw > Extracted > Validated > Canonical > Derived > Predictions/Insights); decision P4-1: the Django models ARE the canonical layer,
provenance is added only to derived rows (rule hits, risk events, alerts, mission reports carry version/`detected_by` fields); no new data platform.
AI output is not stored as trusted data (none exists yet; P7).

## Models (app, layer, concrete fields, outgoing foreign keys)
| Model | Layer | Fields | Foreign keys |
|---|---|---|---|
| `schools.School` | Configuration | 8 | — |
| `schools.SchoolClass` | Canonical | 8 | school->schools.School |
| `schools.TeacherAssignment` | — | 7 | teacher->auth.User, school_class->schools.SchoolClass, created_by->auth.User |
| `schools.GradeLeadAssignment` | — | 9 | user->auth.User, school->schools.School, created_by->auth.User |
| `schools.SchoolMembership` | — | 7 | user->auth.User, school->schools.School, created_by->auth.User |
| `schools.AcademicYear` | Configuration | 9 | school->schools.School |
| `schools.SchoolStaff` | — | 5 | school->schools.School, created_by->auth.User |
| `schools.AuditEvent` | Audit | 10 | user->auth.User, school->schools.School |
| `schools.AccountProfile` | — | 5 | — |
| `schools.SchoolModule` | — | 6 | school->schools.School |
| `schools.AICallUsage` | — | 5 | school->schools.School |
| `students.Student` | Canonical | 17 | parent_user->auth.User, school->schools.School, school_class->schools.SchoolClass |
| `students.Grade` | Canonical | 11 | student->students.Student, enrollment->students.Enrollment, import_batch->students.ImportBatch |
| `students.Attendance` | Canonical | 9 | student->students.Student, enrollment->students.Enrollment, import_batch->students.ImportBatch |
| `students.Document` | — | 7 | — |
| `students.ImportBatch` | Raw (import provenance) | 8 | academic_year->schools.AcademicYear, uploaded_by->auth.User |
| `students.Enrollment` | Canonical | 13 | student->students.Student, academic_year->schools.AcademicYear, school_class->schools.SchoolClass, import_batch->students.ImportBatch, created_by->auth.User |
| `students.Recommendation` | Canonical (staff text) | 7 | student->students.Student, author->auth.User |
| `students.Referral` | — | 9 | student->students.Student, school->schools.School, counselor->auth.User, referred_by->auth.User |
| `students.CounselorNote` | — | 5 | referral->students.Referral, author->auth.User |
| `students.BehaviorNote` | Canonical (staff text) | 9 | school->schools.School, student->students.Student, recorded_by->auth.User |
| `risk.RiskEvent` | Derived | 9 | school->schools.School, student->students.Student |
| `risk.Alert` | Derived / human review | 12 | school->schools.School, student->students.Student, risk_event->risk.RiskEvent, raised_by->auth.User, reviewed_by->auth.User |
| `risk.RuleSettings` | Configuration | 5 | — |
| `risk.Rule` | Configuration | 18 | school->schools.School, created_by->auth.User, last_edited_by->auth.User, approved_by->auth.User |
| `risk.RuleHit` | Derived (provenance of an alert) | 7 | school->schools.School, rule->risk.Rule, student->students.Student, alert->risk.Alert |
| `risk.RuleRun` | Derived (run record) | 13 | school->schools.School, rule->risk.Rule, triggered_by->auth.User |
| `interventions.Strategy` | Configuration | 8 | school->schools.School |
| `interventions.InterventionPlan` | Canonical (human decision) | 18 | school->schools.School, student->students.Student, alert->risk.Alert, owner->auth.User, created_by->auth.User, strategy->interventions.Strategy |
| `interventions.InterventionFollowUp` | Canonical (human decision) | 7 | plan->interventions.InterventionPlan, author->auth.User |
| `vocabulary.VocabularyTerm` | Configuration | 10 | school->schools.School, replaces->vocabulary.VocabularyTerm |
| `missions.Indicator` | — | 3 | — |
| `missions.Branch` | — | 5 | — |
| `missions.RubricLevel` | — | 4 | indicator->missions.Indicator |
| `missions.WeightSet` | — | 15 | school->schools.School, created_by->auth.User, approved_by->auth.User |
| `missions.Weight` | — | 5 | weight_set->missions.WeightSet, indicator->missions.Indicator, branch->missions.Branch |
| `missions.Period` | — | 6 | school->schools.School, academic_year->schools.AcademicYear |
| `missions.Activity` | — | 9 | school->schools.School, period->missions.Period, activity_type->vocabulary.VocabularyTerm, created_by->auth.User |
| `missions.ObservationSession` | — | 4 | activity->missions.Activity, observer->auth.User |
| `missions.Observation` | — | 11 | session->missions.ObservationSession, student->students.Student, indicator->missions.Indicator, condition->vocabulary.VocabularyTerm |
| `missions.ActivityChoice` | — | 8 | student->students.Student, period->missions.Period, recorded_by->auth.User |
| `missions.ParentMeeting` | — | 8 | student->students.Student, recorded_by->auth.User |
| `missions.PathSuggestion` | — | 10 | student->students.Student, period->missions.Period, branch->missions.Branch, author->auth.User |
| `exams.Question` | — | 12 | school->schools.School, topic->vocabulary.VocabularyTerm, author->auth.User, approved_by->auth.User |
| `exams.Option` | — | 6 | question->exams.Question |
| `exams.Exam` | — | 9 | school->schools.School, created_by->auth.User |
| `exams.ExamQuestion` | — | 4 | exam->exams.Exam, question->exams.Question |
| `exams.ExamSession` | — | 5 | exam->exams.Exam, student->students.Student |
| `exams.QuestionAttempt` | — | 8 | session->exams.ExamSession, question->exams.Question |

`—` in Layer = not classified here (mission/exam/test-bank models; see `MODULE_MAP.md`).

## Grading scale (P4-2, decision 47)
Each school has one scale: `risk.RuleSettings.grade_scale_max` (empty = the Iranian default 20; `students/scale.py::school_scale`). Every `Grade` stores the scale it was entered under (`Grade.scale_max`, default 20, migration `students/0022`); teacher entry and the history import validate against the school's scale and store it. **NOT YET IMPLEMENTED:** normalising mixed-scale rows in averages and charts (all current averages use raw scores, correct while a school keeps one scale; a school that changes its scale mid-year must not be mixed until normalisation exists). Attendance codes stay the fixed `Attendance.STATUS_CHOICES` (present, absent, late, sick); moving them to `VocabularyTerm` is DEFERRED until a school asks for another vocabulary.

## Import formats (P4-3; Excel/CSV remains the only integration path)
| Entity | Entry | Columns (Persian aliases accepted) |
|---|---|---|
| Students (live) | SchoolAdmin upload `students/views.py` | first_name, last_name, national_id, grade, class_name, phone_number, father/mother job and phone |
| Accounts (bulk) | `/school/accounts/` | sheet `Students`: name, national_id, grade, class [father_national_id, mother_national_id, father_name, mother_name]; sheet `Teachers`: name, national_id [phone] |
| History roster | `manage.py import_history --kind roster` | national_id, grade, status [class] |
| History grades | `--kind grades` | national_id, subject, exam_type, score, date (score validated against the school scale, or `--max-score`) |
| History attendance | `--kind attendance` | national_id, date, status [note] |
Dry-run is the default; `--apply` writes under an `ImportBatch` that can be reverted. Integrations with national or school systems only on a school's request.
