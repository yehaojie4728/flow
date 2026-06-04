Read first:

- `AGENTS.md`
- `docs/MEGA_PROMPT.md`
- `docs/claims.md`
- `docs/skill_usage_policy.md`
- `docs/venue/conext2026_acm_prep.md`

# Codex Prompt 03: First Safe Patch Plan

Read also:

- `docs/reference_repo_analysis.md`
- `docs/reuse_plan.md`
- `docs/environment_probe_plan.md`
- `docs/ebpf_ascend_readiness_checklist.md`

This is still primarily a planning task.

Do not modify `external/reference_repo/`.

Do not modify system files.

Do not run root-level commands.

---

## Current task

Create the first implementation plan for FlowGap-owned code.

---

## Outputs

Create or update:

- `docs/trace_schema.md`
- `docs/implementation_plan_v1.md`
- `docs/experiment_plan_v1.yaml`
- `docs/test_plan_v1.md`
- `docs/figure_plan_v1.md`

Do not implement code yet unless the user explicitly asks.

---

## Required implementation modules

Plan these modules:

```text
code/trace_parser/
code/gap_predictor/
code/probe_scheduler/
code/scheduler_replay/
code/ebpf_monitor/
code/evaluation/
```

Use RQ1-RQ8 from MEGA_PROMPT.
