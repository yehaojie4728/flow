# FlowGap Claims Ledger

This file controls what the agent may or may not claim.

---

## C1. Scope claim

FlowGap is a probing opportunity inference layer, not a complete root-cause diagnosis system.

Status: allowed.

Forbidden wording:

```text
FlowGap is a complete root-cause diagnosis system.
```

---

## C2. Traffic structure claim

Ascend memcpy traffic exhibits burst-gap structure in evaluated workloads.

Status: NEED_TRACE.

Required evidence:

- Figure 1 motivation trace;
- burst/gap duration distribution;
- iteration-aligned pattern;
- per-path trace analysis.

Forbidden wording:

```text
All Ascend workloads always have predictable gaps.
```

---

## C3. Safe-window prediction claim

FlowGap predicts high-confidence safe windows for probe placement.

Status: NEED_EXPERIMENT.

Required evidence:

- safe-window precision;
- false-safe rate;
- lower-bound coverage;
- calibration error;
- horizon-wise precision/recall.

---

## C4. Scheduling claim

FlowGap reduces harmful probe/memcpy overlap.

Status: NEED_EXPERIMENT.

Required evidence:

- overlap ratio;
- safe probing ratio;
- harmful probe count;
- same probe budget across baselines.

Forbidden wording:

```text
FlowGap eliminates interference.
```

---

## C5. Detection utility claim

FlowGap preserves useful detection capability while lowering probing interference.

Status: NEED_EXPERIMENT.

Required evidence:

- injected or simulated fault scenarios;
- detection recall;
- false positive rate;
- detection latency;
- useful probe ratio;
- failure-aware fallback result.

Forbidden wording:

```text
FlowGap guarantees diagnosis accuracy.
```

---

## C6. CoNEXT compliance claim

The paper follows CoNEXT 2026 submission rules.

Status: NEED_CONEXT2026_CFP_CONFIRMATION.

Required evidence:

- official CoNEXT 2026 CFP;
- page limit;
- anonymity policy;
- artifact / appendix policy;
- formatting instructions.

Forbidden wording:

```text
The paper is ready for CoNEXT 2026 submission.
```

until all official rules are checked.
