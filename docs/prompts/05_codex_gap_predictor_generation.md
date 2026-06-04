Read first:

- `AGENTS.md`
- `docs/MEGA_PROMPT.md`
- `docs/claims.md`
- `docs/skill_usage_policy.md`
- `docs/venue/socc2026_acm_prep.md`

# Codex Prompt 05: Generate Gap Predictor

Use this after the trace parser exists.

Read also:

- `docs/trace_schema.md`
- `docs/implementation_plan_v1.md`

Use `statsmodels`, `scikit-learn`, and `aeon` if available.

---

## Current task

Generate the first FlowGap safe-window predictor under `code/gap_predictor/`.

---

## Input

```text
data/processed/burst_gap_events.parquet
```

If this input does not exist, create code only and do not fabricate results.

---

## Required model family

Implement:

1. phase-aware EWMA / quantile baseline;
2. multi-horizon logistic regression or gradient boosting classifier;
3. calibration table;
4. false-safe rate calculation;
5. time-series split validation.

Metrics:

- safe-window precision;
- false-safe rate;
- safe-window recall;
- lower-bound coverage if available;
- calibration error;
- Brier score;
- per-horizon precision/recall.
