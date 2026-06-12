# Codex Prompt 00: Bootstrap Analyze-Only

Read first:

- `AGENTS.md`
- `docs/MEGA_PROMPT.md`
- `docs/claims.md`
- `docs/topic.md`
- `docs/outline.md`
- `docs/skill_usage_policy.md`
- `docs/venue/socc2026_acm_prep.md`
- `docs/submission_checklist_socc2026.md` if present

If project-local skills exist under `.agent/skills/`, read relevant `SKILL.md` files only when needed.

---

## Current task

Initialize the FlowGap project context for SoCC 2026.

This is an analyze-only task.

Do not modify `external/reference_repo/`.

Do not modify any original/reference code.

Do not run root-level commands.

Do not install packages.

---

## Project reminder

FlowGap is a predictive low-interference intra-host probing system for Ascend 910A/910B memcpy traffic.

Central question:

```text
How can we learn burst-gap patterns from Ascend intra-host memcpy traffic and predict safe probing windows to reduce interference to AI workloads?
```

Core pipeline:

```text
eBPF event monitor
-> event normalization
-> path/link busy-idle timeline
-> safe-window prediction
-> prober scheduling
-> analyzer feedback
```

Target venue:

```text
SoCC 2026 Full Research Paper
```

---

## Outputs to create or update

Create:

- `docs/topic_init.md`
- `docs/problem_decompose.md`
- `docs/paper_storyline.md`
- `docs/work_items.md`
- `PROGRESS.md`

Do not create code yet.

---

## Required content

### docs/topic_init.md

Include:

1. one-sentence problem statement;
2. non-goals;
3. three contributions;
4. SoCC cloud systems positioning;
5. required evidence;
6. biggest rejection risks;
7. immediate data/code needs;
8. SoCC deadline awareness.

### docs/problem_decompose.md

Break the project into:

1. eBPF event collection;
2. event normalization;
3. path/link busy-idle timeline;
4. async interval estimation;
5. safe-window prediction;
6. confidence calibration;
7. prober scheduling;
8. analyzer feedback;
9. SoCC evaluation and paper writing.

For each item include:

- goal;
- input files;
- output files;
- evidence needed;
- risk;
- TODO markers.

### docs/paper_storyline.md

Write the paper story:

- problem;
- insight;
- system;
- cloud systems relevance;
- key difference from Hostping/HostDiag;
- evidence plan;
- expected figures;
- SoCC fit.

### docs/work_items.md

Make a staged task list:

- environment;
- reference repo analysis;
- trace schema;
- trace parser;
- predictor;
- scheduler replay;
- SoCC evaluation;
- writing;
- anonymity check;
- review.

### PROGRESS.md

Initialize a progress log.

---

## Rules

- Mark missing data as NEED_DATA.
- Mark missing citations as NEED_CITATION.
- Mark missing experiments as NEED_EXPERIMENT.
- Do not invent citations.
- Do not invent results.
- Do not invent implementation status.
- Do not claim that eBPF hooks work until verified on this machine.
- Distinguish real Ascend measurements from synthetic/replay/demo.
- Maintain dual-anonymous style.
- Do not reveal author names, institutions, repository URLs, or public system names.

At the end, summarize:

1. files created;
2. assumptions;
3. missing inputs;
4. next prompt to run.
