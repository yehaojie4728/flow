Read first:

- `AGENTS.md`
- `docs/MEGA_PROMPT.md`
- `docs/claims.md`
- `docs/skill_usage_policy.md`
- `docs/venue/conext2026_acm_prep.md`

# Codex Prompt 06: Generate Scheduler Replay

Use this after gap predictor code exists.

Read also:

- `docs/trace_schema.md`
- `docs/implementation_plan_v1.md`
- `docs/gap_predictor_design.md`

Use `simpy` if useful.

---

## Current task

Generate FlowGap scheduler replay under `code/scheduler_replay/`.

Do not modify `external/reference_repo/`.

---

## Policies

Implement replay policies:

1. no probing;
2. fixed interval probing;
3. random probing;
4. threshold probing;
5. EWMA-only probing;
6. FlowGap predictive probing;
7. oracle gap-aware probing.

---

## Outputs

Create:

- `code/scheduler_replay/README.md`
- `code/scheduler_replay/replay.py`
- `code/scheduler_replay/policies.py`
- `code/scheduler_replay/metrics.py`
- `code/scheduler_replay/test_replay.py`
- `docs/scheduler_replay_design.md`
