Read first:

- `AGENTS.md`
- `docs/MEGA_PROMPT.md`
- `docs/claims.md`
- `docs/skill_usage_policy.md`
- `docs/venue/conext2026_acm_prep.md`

# Codex Prompt 04: Generate Trace Parser

Use this only after you approve the first patch plan.

Read also:

- `docs/trace_schema.md`
- `docs/implementation_plan_v1.md`
- `docs/test_plan_v1.md`

You may use `exploratory-data-analysis` if available.

---

## Current task

Generate the first FlowGap trace parser under `code/trace_parser/`.

Do not modify `external/reference_repo/`.

---

## Required behavior

The parser must validate required columns, normalize timestamps, sort events by time, derive busy intervals per path/link, derive gaps, merge micro-gaps shorter than `min_probe_duration_ns + safety_margin_ns`, calculate overlap if probe events exist, and export processed files.

---

## Outputs

Create:

- `code/trace_parser/README.md`
- `code/trace_parser/parse_trace.py`
- `code/trace_parser/intervalize.py`
- `code/trace_parser/schema.py`
- `code/trace_parser/test_trace_parser.py`
- `docs/trace_parser_design.md`

Only create synthetic data if no real trace exists, and clearly label it synthetic.
