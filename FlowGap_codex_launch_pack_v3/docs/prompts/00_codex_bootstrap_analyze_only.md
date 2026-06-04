Read first:

- `AGENTS.md`
- `docs/MEGA_PROMPT.md`
- `docs/claims.md`
- `docs/skill_usage_policy.md`
- `docs/venue/conext2026_acm_prep.md`

# Codex Prompt 00: Bootstrap Analyze-Only

If project-local skills exist under `.agent/skills/`, read relevant `SKILL.md` files only when needed.

---

## Current task

Initialize the FlowGap project context.

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

Target venue:

```text
CoNEXT 2026
```

Use ACM acmart sigconf provisionally. Mark all unconfirmed venue rules as NEED_CONEXT2026_CFP_CONFIRMATION.

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

## Rules

- Mark missing data as NEED_DATA.
- Mark missing citations as NEED_CITATION.
- Mark missing experiments as NEED_EXPERIMENT.
- Mark missing CoNEXT rules as NEED_CONEXT2026_CFP_CONFIRMATION.
- Do not invent citations.
- Do not invent results.
- Do not invent implementation status.
- Do not claim that eBPF hooks work until verified on this machine.
