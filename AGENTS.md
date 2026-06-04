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

Target venue:

```text
ACM Symposium on Cloud Computing 2026 (SoCC 2026)
```

Default submission category:

```text
Full Research Paper
```

Use ACM `acmart` `sigconf` as the LaTeX basis.

Required provisional document class:

```latex
\documentclass[sigconf,review,anonymous]{acmart}
```

Read:

```text
docs/venue/socc2026_acm_prep.md
```

before generating paper scaffolding.

---

## SoCC-specific rules

SoCC 2026 full research papers use:

```text
12 pages + unlimited references
dual-anonymous review
9pt ACM proceedings format
single PDF
8.5" x 11" paper
PDF size <= 10 MB
paper type as subtitle: Research Full
```

Do not invent or alter official venue rules.

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

## SoCC positioning

Position FlowGap as:

```text
a cloud / AI-infrastructure monitoring and active probing system that reduces measurement-induced interference in accelerator servers.
```

Avoid positioning FlowGap as:

```text
a pure time-series prediction paper
a complete root-cause diagnosis system
a hardware-specific engineering note without broader cloud systems relevance
```

---

## Non-goals

FlowGap is not:

- a complete root-cause diagnosis system;
- a complete physical-link reconstruction system;
- a universal accelerator monitoring framework;
- a deep-learning traffic generation model;
- a paper that claims all Ascend workloads always have predictable gaps.

FlowGap is:

```text
a probing opportunity inference layer for low-interference active probing.
```

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

### scientific-writing

Use text-only mode.

Do not:

- generate graphical abstracts;
- generate AI images;
- call `generate-image`;
- call `scientific-schematics`;
- invent citations;
- invent numbers;
- invent experiments;
- invent hardware details.

### literature-review

Use only for search strategy, screening, matrix building, and synthesis.

Do not:

- generate AI figures;
- rank papers primarily by author prestige, h-index, or institution;
- write fake citations;
- write final Related Work before citations are verified.

### peer-review

Be harsh.

Focus on:

- SoCC systems-paper fit;
- evidence-to-claim alignment;
- missing baselines;
- missing detection utility;
- weak novelty;
- unclear relation to Hostping/HostDiag;
- unsupported claims;
- simulation vs real measurement confusion.

### venue-templates

Use only for formatting help.

The official SoCC 2026 CFP and ACM template are the source of truth.

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

Do not reveal author names, affiliations, institutions, acknowledgments, repository URLs, or identifying project names in the anonymous SoCC submission.

Mark unknowns as:

- TODO
- NEED_DATA
- NEED_CITATION
- NEED_EXPERIMENT
- NEED_TEACHER_CONFIRMATION
- NEED_MANUAL_CHECK

---

## Required project files

Read these before major tasks:

- `docs/MEGA_PROMPT.md`
- `docs/claims.md`
- `docs/topic.md`
- `docs/outline.md`
- `docs/skill_usage_policy.md`
- `docs/venue/socc2026_acm_prep.md`
- `docs/submission_checklist_socc2026.md` if present
- `PROGRESS.md` if present

Update `PROGRESS.md` after completing each task.
