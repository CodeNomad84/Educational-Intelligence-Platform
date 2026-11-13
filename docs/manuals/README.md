# User manuals (source material, plain English first)

One short file per role. They are **source text**: at the end of the project they are turned into the real manuals (and translated to Persian). Until then they are kept honest by one rule.

| Role | File | Lands on after login |
|---|---|---|
| Platform admin (superuser, PlatformAdmin) | [platform-admin.md](platform-admin.md) | `/admin/` |
| School admin | [school-admin.md](school-admin.md) | `/school/` |
| Grade lead | [grade-lead.md](grade-lead.md) | `/grade/` |
| Teacher (subject teacher) | [teacher.md](teacher.md) | `/teacher/` |
| Counselor | [counselor.md](counselor.md) | `/counselor/` |
| Parent | [parent.md](parent.md) | `/students/` |
| Student | [student.md](student.md) | `/me/` |

## Convention (Definition of Done)
Every slice that changes what a role can see or do **adds a few lines to that role's manual**: how to do it, what you see, what you do NOT see, and who to ask. A slice without its manual lines is not done (`CLAUDE.md` §12, `docs/CHANGE_PROCESS.md`, the checklist template).

## How each file is written
- One short section per task, imperative sentences ("Open ... Click ...").
- Each task has: **Steps**, **You see**, **You do not see**, **Ask**.
- Page paths are given so the text can be checked against the product (`dashboard/urls.py`). Persian screen labels are added when the manuals are translated.
- Only what is built **and covered by a test or a code reading** is described. Nothing is invented.

## Markers
- **TO VERIFY**: the sentence comes from a code reading, or is not exercised; check it in the running product before publishing.
- **PENDING POLICY**: depends on a decision that is not made (consent, retention, external LLM, parent access). Do not publish as final.
- **NOT BUILT**: the feature does not exist yet; listed only so nobody promises it.

All examples use synthetic data. Real data is not allowed until the security baseline exit (`docs/SECURITY.md`).
