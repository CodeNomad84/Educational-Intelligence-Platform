# DEMO PRESENTATION CHECKLIST (DEMO SCOPE)

## A. The day before / morning of the meeting

- [ ] **Re-seed on the meeting day** (data is relative to "today"; a week-old seed drifts and stories change):
  ```bash
  DEMO_PASSWORD='<choose one>' scripts/start_demo.sh --reseed --check
  ```
  Expect: `DEMO MODE ACTIVE`, `Database: demo_db.sqlite3`, `Students: 40`, `Seed date: <today> (age 0 day(s))`
  and, from the seed, `Risk distribution: {'HIGH': 2, 'MEDIUM': 7, 'LOW': 31}`.
- [ ] Demo users exist (`demo_admin`, `demo_counselor`); log in with each once; note the password in a safe place.
- [ ] Start for real: `scripts/start_demo.sh` (it refuses a wrong settings module and a seed older than 1 day).
- [ ] **Offline test:** turn Wi-Fi off, reload every page — all must still be styled (assets are local).
- [ ] Port free (the Docker stack also uses 8000); otherwise `DEMO_PORT=8001 scripts/start_demo.sh`.
- [ ] Rehearse the script once on the presentation machine and projector.

## B. Browser preparation

- [ ] One clean window, full screen, zoom 100–110 %, bookmarks bar hidden, notifications off.
- [ ] Logged in as `demo_admin` (not as parent). Tab order: Dashboard · Counselor · Student A (رضا کاظمی) · Student C (مهسا فرهادی) · Assistant.
- [ ] Check legibility from the back of the room (fonts, chart labels, colour contrast).
- [ ] Browser autofill/passwords manager popups disabled.

## C. Backup plan

- [ ] Screenshots of the six key screens (dashboard, counselor, profile A, profile C, assistant answer, list) saved as PDF.
- [ ] Short screen recording of a full run-through on the laptop.
- [ ] Second terminal ready with `scripts/start_demo.sh` (server crashed → restart takes ~3 s; sessions survive because the secret key is fixed; log in again only if the cookie is lost).
- [ ] If the data looks wrong (banner missing, 2 students, no charts) → **stop**, run `scripts/start_demo.sh --check`; never improvise on the real database.

## D. During the demo — exact navigation

| # | Action | Expected on screen |
|---|---|---|
| 1 | Login page `/` | DEMO banner, product name, no sidebar |
| 2 | Log in `demo_admin` → dashboard | Cards: 40 students · 2 پرخطر · 7 نیازمند توجه; doughnut 2/7/31; two trend charts; class table; attention list led by Sina/Reza |
| 3 | Top bar → «داشبورد مشاور» | 9 case cards with reasons and actions |
| 4 | «دانش‌آموزان» → search «رضا» → پروفایل | Level پرخطر, 4 reasons with Persian rule names, actions, 2 charts |
| 5 | Back → search «مهسا» → پروفایل | Level کم‌خطر, "بهبود پس از مداخله", strengths |
| 6 | «دستیار هوشمند» → «مهسا فرهادی چگونه بهتر شد؟» | previous state / intervention / current / evidence, caveat, "Rule-Based Prototype Assistant" |
| 7 | Chip «کدام دانش‌آموزان نیاز به توجه دارند؟» | 9 names ordered by priority |
| 8 | Back to dashboard for the close | — |

Things that must **not** appear: Latin digits next to ٪, English rule ids, an "AI prediction" button, a CDN-unstyled page, a Django error page.

## E. After the meeting

- [ ] Collect feedback (ask each person, write verbatim):
  * CEO: which weekly decisions should this support? what would make it a "yes" for a pilot?
  * Planning: which indicators/periods/reports do you need? who owns the data?
  * Counseling: which actions do you really take? what is missing from the suggestions? what must never be shown?
- [ ] Note questions the demo could not answer; list "data we would need" and "policies we would need" (privacy, access, parents).
- [ ] Agree owner + date for the next step (pilot scope, data-protection review).
- [ ] Stop the server; the demo database holds only synthetic data and can be deleted or re-seeded.
