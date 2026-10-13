# CUSTOMIZATION

Goal: configuration over custom code. Structure: **Core Platform + School Configuration + Customer Integrations + Optional Modules**. Status: TARGET (nothing implemented); school key per ADR-0004 (PROPOSED).

| Category | Examples | Where (TARGET) |
|---|---|---|
| Configuration (data) | branding, school profile, academic calendar, grade scale, classes, assessment categories, roles/labels, thresholds, alert & notification policies | per-school config records |
| Rules | risk rules/thresholds, alert rules (template → school-custom) | rule store, approval lifecycle (AI_GOVERNANCE) |
| Integrations | SIS/DB import, SMS/email, storage | isolated adapters under a clearly named integrations area |
| Optional modules / feature flags | counseling, study assistant, parent portal | flags per school |

## Rules
- No school name, grade scale, threshold or vocabulary hard-coded in core (current violations: D-09 hard-coded choices, D-07/D-08 scale/vocab assumptions).
- Customer-specific code lives only in an isolated, documented location; it never modifies core models.
- Any customization request: classify (config / rule / integration / module) before coding; if none fits, L3 proposal.
