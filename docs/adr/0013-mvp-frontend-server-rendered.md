# ADR-0013: MVP frontend = server-rendered Django templates + Bootstrap 5 RTL; React only as islands; SPA deferred
- Status: **ACCEPTED 2026-11-01** (owner, decision pack `changes/0028` item P8-2, approved as written)
- Date: 2026-11-01
- Decider: owner
- Level: L3 (changes the TARGET in `ARCHITECTURE.md`, established decision 4)
- Relation: amends `ARCHITECTURE.md` established decision 4 ("React + Bootstrap 5 … TARGET"); ADR-0006 (React mechanics) stays reserved and is written when the first island is built.

## Context
The goal for P3-P8 is an MVP that can be shown to school principals (owner decision OW-5). Every existing page is a Django template behind `role_required` and the `visible_*` access functions in `students/access.py`, with permission tests per role. A React single-page app would need a JSON API for every page and re-open the authorization work for each of them (the API would become a second path to the same data). Pages must load nothing from abroad (0028 P3-4; checked by `check --deploy` eip.E004).

## Decision
1. For the MVP the frontend stays **server-rendered Django templates with Bootstrap 5 RTL**, served from the platform itself (no CDN), with one shared base template and design system (0028 P3-4, P8-3).
2. Small JavaScript is allowed where it adds real value (charts with the self-hosted Chart.js, show/hide, confirmation). No build step.
3. **React only as islands**: a screen that truly needs rich interaction may mount a React component into one element of a server-rendered page, fed by an endpoint that uses the same `visible_*` scopes. Each island is its own L2 proposal; the first one writes ADR-0006 (bundling, where the files live, how they are self-hosted).
4. A full React SPA is **DEFERRED** until after pilot feedback. Reopening it needs a new ADR.

## Alternatives considered
- **React SPA now** (previous TARGET): rejected for the MVP. Duplicates every view behind an API, re-opens authorization for each, delays the demo by weeks, and adds a build toolchain and npm dependencies.
- **htmx or a similar library**: not needed for the current pages; would be a new dependency (L3). Can be proposed later per screen.

## Consequences (security, data, testing, customization)
- Security: one access path per page (the view), already tested per role; no new API surface.
- Testing: page tests stay Django test-client tests; no JS test stack.
- Customization: branding and labels stay in templates and school settings; RTL is the default.
- Cost: highly interactive screens (drag-and-drop planners, large editable grids) are harder; they are the candidates for islands.

## Evidence (Stage 0 IDs, files)
`dashboard/templates/dashboard/base.html` (shared base), `dashboard/static/dashboard/vendor/` (self-hosted libraries), `dashboard/deploy_checks.py` (eip.E004), DOC-01 (frontend is Django templates).

## Supersedes / superseded by
Amends `ARCHITECTURE.md` established decision 4. Not superseded.
