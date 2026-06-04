Read first:

- `AGENTS.md`
- `docs/MEGA_PROMPT.md`
- `docs/claims.md`
- `docs/skill_usage_policy.md`
- `docs/venue/conext2026_acm_prep.md`

# Codex Prompt 07: Create CoNEXT Paper Scaffold

Use only after initial design and experiment plan exist.

Read also:

- `docs/venue/conext2026_acm_prep.md`
- `docs/paper_storyline.md`
- `docs/experiment_plan_v1.yaml`
- `docs/figure_plan_v1.md`

Use `scientific-writing` in text-only mode and `venue-templates` only for formatting reference.

---

## Current task

Create a provisional ACM acmart paper scaffold for CoNEXT 2026.

Do not claim final CoNEXT compliance.

---

## Outputs

Create:

- `paper/main.tex`
- `paper/references.bib`
- `paper/sections/01_introduction.tex`
- `paper/sections/02_background_motivation.tex`
- `paper/sections/03_overview.tex`
- `paper/sections/04_predictor_design.tex`
- `paper/sections/05_prober_analyzer_design.tex`
- `paper/sections/06_implementation.tex`
- `paper/sections/07_evaluation.tex`
- `paper/sections/08_related_work.tex`
- `paper/sections/09_conclusion.tex`
- `paper/README.md`

---

## Requirements

- Use provisional `\documentclass[sigconf,review,anonymous]{acmart}`.
- Mark page limit as NEED_CONEXT2026_CFP_CONFIRMATION.
- Mark anonymity rules as NEED_CONEXT2026_CFP_CONFIRMATION.
- Do not add fake references.
- Do not write final results.
- Use TODO / NEED_EXPERIMENT placeholders.
- Keep paper centered on predictive low-interference probing.
