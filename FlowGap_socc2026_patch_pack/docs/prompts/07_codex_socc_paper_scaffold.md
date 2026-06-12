# Codex Prompt 07: Create SoCC Paper Scaffold

Read first:

- `AGENTS.md`
- `docs/MEGA_PROMPT.md`
- `docs/claims.md`
- `docs/skill_usage_policy.md`
- `docs/venue/socc2026_acm_prep.md`
- `docs/submission_checklist_socc2026.md`
- `docs/ai_usage_disclosure.md`

Read also:

- `docs/paper_storyline.md`
- `docs/experiment_plan_v1.yaml`
- `docs/figure_plan_v1.md`

Use `scientific-writing` in text-only mode and `venue-templates` only for formatting reference.

---

## Current task

Create a provisional ACM acmart paper scaffold for SoCC 2026 Full Research Paper.

Do not claim final submission readiness.

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

- Use `\documentclass[sigconf,review,anonymous]{acmart}`.
- Target Full Research Paper: 12 pages + unlimited references.
- Use 9pt ACM proceedings format.
- Use 8.5" x 11" paper.
- Keep PDF size target <= 10 MB.
- Include `\subtitle{Research Full}` or equivalent subtitle.
- Do not change margins, inter-column spacing, or line spacing.
- Do not add fake references.
- Do not write final results.
- Use TODO / NEED_EXPERIMENT placeholders.
- Keep paper centered on predictive low-interference probing.
- Maintain dual-anonymous submission style.
- Remove acknowledgments in anonymous draft.
- Prepare AI usage disclosure separately in `docs/ai_usage_disclosure.md`.

---

## Section guidance

1. Introduction:
   - cloud/AI infrastructure motivation;
   - measurement-induced interference problem;
   - insight;
   - FlowGap overview;
   - three contributions;
   - no unsupported numbers.

2. Background and Motivation:
   - Ascend intra-host communication;
   - why existing probing fails;
   - three observations.

3. Overview:
   - Predictor / Prober / Analyzer.

4. Predictor Design:
   - eBPF event collection;
   - busy-idle intervalization;
   - async interval estimation;
   - multi-horizon survival predictor;
   - confidence calibration.

5. Prober and Analyzer:
   - safe-window admission;
   - downgrade/cancel;
   - failure-aware probing;
   - feedback.

6. Implementation:
   - platform;
   - hooks;
   - daemon;
   - limitations.

7. Evaluation:
   - RQ1-RQ8 skeleton only.

8. Related Work:
   - intra-host diagnosis;
   - active probing;
   - cloud/AI accelerator monitoring;
   - tracing and monitoring systems.

9. Conclusion:
   - placeholder.

---

## Rules

- Text-only.
- No AI figures.
- No fake citations.
- No invented results.
- Do not identify authors or institutions.
- Cite prior work in third person.
