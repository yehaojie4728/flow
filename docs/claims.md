# FlowGap Claims Ledger

This file controls what the agent may or may not claim.

---

## C1. Scope claim

FlowGap is a probing opportunity inference layer, not a complete root-cause diagnosis system.

Status: allowed.

Allowed wording:

```text
FlowGap decides when active probes are likely to be low-interference.
```

Forbidden wording:

```text
FlowGap is a complete root-cause diagnosis system.
FlowGap localizes all root causes.
```

---

## C2. Cloud systems relevance claim

FlowGap addresses monitoring interference in AI accelerator servers used in cloud-scale training/serving infrastructure.

Status: NEED_CITATION and NEED_EXPERIMENT.

Required evidence:

- SoCC topic fit;
- AI cluster / accelerator server motivation;
- real or demo Ascend traces;
- workload impact experiment.

Allowed wording after evidence:

```text
FlowGap targets measurement-induced interference in accelerator-server monitoring for AI infrastructure.
```

Forbidden wording:

```text
FlowGap solves all cloud monitoring overheads.
```

---

## C3. Traffic structure claim

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

## C4. Safe-window prediction claim

FlowGap predicts high-confidence safe windows for probe placement.

Status: NEED_EXPERIMENT.

Required evidence:

- safe-window precision;
- false-safe rate;
- lower-bound coverage;
- calibration error;
- horizon-wise precision/recall.

Forbidden wording:

```text
FlowGap perfectly predicts memcpy timing.
```

---

## C5. Representation claim

Probe-aware event-driven intervalization improves safe-window prediction over fixed windows and raw event inputs.

Status: NEED_EXPERIMENT.

Required evidence:

- representation ablation;
- fixed-window predictor baseline;
- raw-event baseline;
- false-safe rate and recall comparison.

---

## C6. Scheduling claim

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

## C7. Workload impact claim

FlowGap reduces AI workload slowdown compared with fixed/random/threshold probing.

Status: NEED_EXPERIMENT.

Required evidence:

- no-probe baseline;
- fixed/random/threshold baseline;
- iteration slowdown;
- p95/p99 latency;
- throughput loss;
- repeated runs.

Forbidden wording:

```text
FlowGap has zero overhead.
```

---

## C8. Detection utility claim

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

## C9. Robustness claim

FlowGap degrades conservatively under event loss, async uncertainty, and workload drift.

Status: NEED_EXPERIMENT.

Required evidence:

- event loss experiment;
- async uncertainty experiment;
- drift recovery experiment;
- confidence downgrade behavior.

---

## C10. System overhead claim

FlowGap has acceptable monitoring and prediction overhead.

Status: NEED_EXPERIMENT.

Required evidence:

- eBPF hook overhead;
- event processing latency;
- predictor inference latency;
- CPU/memory usage;
- ring buffer drop rate.

---

## C11. SoCC compliance claim

The paper follows SoCC 2026 submission rules.

Status: NEED_FINAL_CHECK.

Required evidence:

- final PDF uses ACM acmart sigconf review anonymous;
- 12-page full research body limit is respected;
- references are separated/unlimited;
- 9pt font;
- 8.5" x 11" paper;
- PDF <= 10 MB;
- dual anonymous;
- paper type subtitle included;
- reserve reviewer information prepared.

Forbidden wording before final check:

```text
The paper is ready for SoCC 2026 submission.
```
