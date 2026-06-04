# AGENTS.md

You are assisting with the FlowGap paper and codebase.

This repository is an isolated FlowGap workspace. Do not modify the original reference repository unless explicitly instructed.

---

## Project

FlowGap is a predictive low-interference intra-host probing system for Ascend 910A/910B memcpy traffic.

The paper answers one question:

> How can we learn burst-gap patterns from Ascend intra-host memcpy traffic and predict safe probing windows to reduce interference to AI workloads?

---

## Target venue

Target venue: CoNEXT 2026.

Use ACM `acmart` `sigconf` as the provisional LaTeX basis.

Important:

- CoNEXT 2026 official page exists, but CFP details must be confirmed before final submission.
- Mark page limit, anonymity, appendix, artifact, and rebuttal rules as `NEED_CONEXT2026_CFP_CONFIRMATION` until confirmed.
- Do not invent venue rules.

Read:

```text
docs/venue/conext2026_acm_prep.md
```

before generating paper scaffolding.

---

## Core pipeline

```text
eBPF event monitor
-> event normalization
-> path/link busy-idle timeline
-> safe-window prediction
-> prober scheduling
-> analyzer feedback
```

---

## System modules

1. Predictor
   - collect AscendCL memcpy/sync/device/memory events with eBPF/uprobe;
   - normalize events into path/link busy-idle timelines;
   - estimate async memcpy intervals conservatively;
   - predict multi-horizon safe windows;
   - calibrate confidence.

2. Prober
   - run tiny latency, normal latency, bandwidth, or confirmation probes;
   - downgrade or cancel probes when the predicted window becomes unsafe;
   - respect probe budget.

3. Analyzer
   - analyze probe latency/bandwidth results;
   - determine whether probe results are trustworthy;
   - preserve detection utility while reducing harmful probe overlap;
   - feed actual overlap and probe duration back to predictor.

---

## Non-goals

FlowGap is not:

- a complete root-cause diagnosis system;
- a complete physical-link reconstruction system;
- a universal accelerator monitoring framework;
- a deep-learning traffic generation model;
- a paper that claims all Ascend workloads always have predictable gaps.

FlowGap is a probing opportunity inference layer for low-interference active probing.

---

## Reference repository policy

The directory `external/reference_repo/` is read-only reference material.

First-round tasks may inspect it, but must not modify it.

When analyzing it, produce:

- `docs/repo_map.md`
- `docs/reference_repo_analysis.md`
- `docs/reuse_plan.md`
- `docs/first_patch_plan.md`

Only after explicit user approval may code be copied or adapted into FlowGap-owned directories.

---

## Skills

Use installed Agent Skills when relevant. Prefer:

- `paper-lookup`
- `exploratory-data-analysis`
- `aeon`
- `statsmodels`
- `scikit-learn`
- `statistical-analysis`
- `scientific-visualization`
- `markdown-mermaid-writing`
- `simpy`
- `pymoo`
- `scientific-writing`
- `literature-review`
- `peer-review`
- `venue-templates`

If project-local skills exist under `.agent/skills/`, read the relevant `SKILL.md` before using that skill.

---

## Skill overrides

scientific-writing:

- text-only mode;
- no graphical abstracts;
- no AI images;
- no fake citations;
- no fake numbers;
- no fake experiments;
- no fake hardware details.

literature-review:

- search, screening, matrix, synthesis only;
- no AI figures;
- no fake references;
- no final Related Work before citations are verified.

peer-review:

- be harsh;
- focus on evidence-to-claim alignment, missing baselines, detection utility, CoNEXT fit.

venue-templates:

- formatting help only;
- official venue template is source of truth.

---

## Hard restrictions

Do not invent citations.

Do not invent experiments.

Do not invent metrics.

Do not invent Ascend hardware details.

Do not claim simulation results as real Ascend measurements.

Do not generate decorative AI figures.

Do not modify `external/reference_repo/`.

Do not run root-level or system-changing commands unless the user explicitly asks.

Do not alter `/usr/local/Ascend`, kernel settings, or production runtime files.

Mark unknowns as:

- TODO
- NEED_DATA
- NEED_CITATION
- NEED_EXPERIMENT
- NEED_TEACHER_CONFIRMATION
- NEED_MANUAL_CHECK
- NEED_CONEXT2026_CFP_CONFIRMATION

---

## Required project files

Read these before major tasks:

- `docs/MEGA_PROMPT.md`
- `docs/claims.md`
- `docs/topic.md`
- `docs/outline.md`
- `docs/skill_usage_policy.md`
- `docs/venue/conext2026_acm_prep.md`
- `PROGRESS.md` if present

Update `PROGRESS.md` after completing each task.
