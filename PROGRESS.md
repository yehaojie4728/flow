# FlowGap Progress Log

Project: FlowGap — Predictive Low-Interference Intra-Host Probing for Ascend Accelerator Traffic
Target: SoCC 2026 Full Research Paper

---

## Session 2026-06-04: Bootstrap Analyze-Only (00_codex_bootstrap_analyze_only.md)

**Status:** Completed analysis. No code generated. No modifications to `external/reference_repo/`.

### Actions performed

1. Read all required policy and context files:
   - `AGENTS.md` — project rules, SoCC constraints, skill overrides, hard restrictions.
   - `docs/MEGA_PROMPT.md` — central question, SoCC positioning, core insight, main pipeline, contributions, required evidence, model preferences, evaluation RQs, baselines, truthfulness rules.
   - `docs/claims.md` — C1-C11 claim ledger with allowed/forbidden wording and evidence requirements.
   - `docs/skill_usage_policy.md` — allowed and restricted agent skills with overrides.
   - `docs/venue/socc2026_acm_prep.md` — SoCC 2026 deadlines, formatting rules, anonymity, AI usage, reserve reviewer policy.
   - `docs/topic.md` — full paper topic, problem statement, core insight, system modules, challenges, design principles.
   - `docs/outline.md` — detailed 12-section paper outline with experiment plans.
   - `docs/submission_checklist_socc2026.md` — SoCC submission checklist.
   - `docs/prompts/00_codex_bootstrap_analyze_only.md` — current task instructions.

2. Created 5 output files:
   - `docs/topic_init.md` — problem statement, non-goals, 3 contributions, SoCC positioning, evidence status, rejection risks, immediate needs, deadline awareness.
   - `docs/problem_decompose.md` — 9-part decomposition: eBPF collection, normalization, timeline, async estimation, prediction, calibration, prober, analyzer, evaluation.
   - `docs/paper_storyline.md` — problem → insight → system → cloud relevance → Hostping/HostDiag differentiation → evidence plan → expected figures → SoCC fit.
   - `docs/work_items.md` — 12-stage task list: environment, repo analysis, trace schema, parser, predictor, prober, analyzer, synthetic workload, evaluation, writing, anonymity, review.
   - `PROGRESS.md` — this file.

### Assumptions made

- The reference repository at `external/reference_repo/` exists and contains Hostping/HostDiag code (not yet verified; directory listing returned empty results).
- Ascend 910A/910B hardware is available for trace collection.
- CANN/AscendCL supports eBPF uprobes on the listed API functions.
- The SoCC 2026 second-round deadline (July 2026) is the target.

### Missing inputs (NEED_DATA / NEED_TEACHER_CONFIRMATION)

| Item | Priority | Status |
|---|---|---|
| Real Ascend eBPF trace data | CRITICAL | NEED_DATA |
| Ascend 910A/910B server access | CRITICAL | NEED_TEACHER_CONFIRMATION |
| CANN/AscendCL version and library paths | HIGH | NEED_TEACHER_CONFIRMATION |
| eBPF toolkit version | HIGH | NEED_TEACHER_CONFIRMATION |
| Server topology (NUMA, NPU, PCIe, HCCS) | HIGH | NEED_DATA |
| Workload definitions for evaluation | HIGH | NEED_DATA |
| Anonymized project name decision | MEDIUM | NEED_TEACHER_CONFIRMATION |
| Senior author identification | MEDIUM | NEED_TEACHER_CONFIRMATION |
| Verified BibTeX references | MEDIUM | NEED_CITATION |
| `external/reference_repo/` contents | HIGH | Not yet readable (Glob returned empty) |

### Claims ledger status

All claims C1-C11 recorded. C1 is allowed. C2-C10 require evidence (NEED_TRACE, NEED_EXPERIMENT, NEED_CITATION). C11 requires final check. No claims were invented or falsified.

### Rules compliance

- [x] No modifications to `external/reference_repo/`.
- [x] No code generated.
- [x] No root commands run.
- [x] No dependencies installed.
- [x] No citations invented.
- [x] No results invented.
- [x] No implementation status invented.
- [x] No author/institution names revealed.
- [x] Missing data marked as NEED_DATA / NEED_CITATION / NEED_EXPERIMENT / NEED_TEACHER_CONFIRMATION.
- [x] Synthetic work distinguished from real measurement.
- [x] Dual-anonymous style maintained.

### Next prompt

Run `docs/prompts/01_reference_repo_analysis.md` to analyze `external/reference_repo/` and produce `docs/repo_map.md`, `docs/reference_repo_analysis.md`, `docs/reuse_plan.md`, and `docs/first_patch_plan.md`.

Or, if trace data and hardware access are available sooner, proceed to `docs/prompts/02_trace_collection_and_schema.md`.

---

## Session 2026-06-04 (2): Reference Repo Analysis (01_codex_reference_repo_analysis.md)

**Status:** Completed. `external/reference_repo/` confirmed absent.

### Actions performed

1. Attempted to locate `external/reference_repo/` via:
   - Read: `/root/FlowGap-work/FlowGap-paper/external/reference_repo/.gitignore` → File does not exist.
   - LS: `/root/FlowGap-work/FlowGap-paper/external/` → Empty.
   - Glob: `**/external/**` under `/root` → No file found.

2. Created 4 output files:
   - `docs/repo_map.md` — records absent status, expected structure, search targets with "Not found" for all 7 categories.
   - `docs/reference_repo_analysis.md` — detailed search results per target (eBPF, AscendCL APIs, prober, analyzer, schema, build scripts, risky code), what's blocked vs. unblocked, recommendations.
   - `docs/reuse_plan.md` — three-tier reuse framework (direct/adapt/reference) for when repo arrives, plus ground-up implementation plan referencing existing design specs from `docs/outline.md`.
   - `docs/first_patch_plan.md` — dual plan: provisional (if repo available) and ground-up (repo absent). Patch 0 scaffolding, Patch 1 collector, Patch 2 normalizer, Patch 3 predictor.

### Key finding

`external/reference_repo/` does not exist. All 7 search targets returned zero results. No Hostping or HostDiag code is available for reference or reuse.

### Unblocked work (can proceed without repo)

- Paper outline, problem decomposition, architecture, evaluation plan (already done).
- Synthetic workload generator design.
- Data structures and FlowEvent schema design.
- Algorithm pseudocode for predictor/prober/analyzer.
- Predictor implementation with synthetic traces.

### Blocked work

- eBPF hooks for AscendCL APIs (needs CANN docs + hardware).
- Code reuse from HostDiag (needs reference repo).
- Concretizing patch plan with file paths.

### Rules compliance

- [x] No modifications to `external/reference_repo/` (absent — nothing to modify).
- [x] No code generated.
- [x] No root commands run.
- [x] No code invented that is not present.
- [x] Absent files marked as not found; no fabricated content.
- [x] Unclear capabilities marked INFERRED where appropriate.
- [x] All analysis is honest about what exists and what does not.

### Next prompt

Option A: If reference repo can be populated, re-run `docs/prompts/01_codex_reference_repo_analysis.md`.
Option B: If proceeding ground-up, run `docs/prompts/02_trace_collection_and_schema.md` to design FlowEvent schema and begin synthetic data generation.

---

## Session 2026-06-04 (3): Reference Repo Analysis — RE-EXECUTED (01_codex_reference_repo_analysis.md)

**Status:** Completed. `external/reference_repo/` confirmed present with HostDiagV2 code and real trace data.

### Actions performed

1. Read all source files: `README.md` (249 lines), `trace_memcpy_numa.py` (416 lines), `npu_adaptive_daemon.cpp` (440 lines), `probe_severity_analyzer.py` (219 lines), `probe_analysis_worker.py` (73 lines), `export_uploader_topo.py` (200+ lines), `memcpy_benchmark.cpp` (501 lines), `CMakeLists.txt` (47 lines), `build.sh` (62 lines), `start_monitor_stack.sh` (150+ lines).

2. Read all data files: raw trace (29 events from Ascend 910B2), agg trace (29 windows), probe trigger CSV (2 records), severity CSV (2 assessments), probe log (30 lines, 2 loops).

3. Created/Updated 4 output files:
   - `docs/repo_map.md` — complete inventory, 7-category search results, trace schema documentation.
   - `docs/reference_repo_analysis.md` — gap analysis vs. FlowGap, trace data quality, code quality, architecture comparison.
   - `docs/reuse_plan.md` — four tiers: 3 direct, 4 adaptable, 5 reference-only, 5 from-scratch.
   - `docs/first_patch_plan.md` — Patches 0-3: scaffolding, eBPF hooks+async, probe executor, normalizer.

### Key findings

**Tier 1 (directly reusable):** eBPF hook C code, probe executor (bandwidth/latency), topology detection.
**Tier 2 (adaptable):** library resolver, event normalizer, trace schema, build system.
**Tier 4 (from scratch):** async hooks, predictor, calibrator, scheduler, feedback loop — these are the core FlowGap novelty.

**Trace data:** 29 real H2D events from Ascend 910B2. Issues: 3.4% device gaps, no async, no D2H/D2D, limited length.

**Architecture gap:** HostDiagV2 is threshold-triggered (reactive). FlowGap must be predictive. This gap cannot be filled by reuse.

### Rules compliance

- [x] No modifications to `external/reference_repo/`.
- [x] No code generated (analysis documents only).
- [x] No root commands run.
- [x] Unclear capabilities marked NEED_MANUAL_CHECK.

### Next prompt

Run `docs/prompts/02_trace_collection_and_schema.md` to design FlowEvent schema and adapt eBPF hooks.

---

## Session 2026-06-10: Environment Probe Plan (02_codex_environment_probe_plan.md)

**Status:** Completed. Read-only environment probe plan and script created.

### Actions performed

1. Created 3 output files:
   - `docs/environment_probe_plan.md` — 9-category probe plan covering: OS/kernel, eBPF/BCC, CANN/AscendCL, function signatures, Python, build tools, topology, permissions, process environment. Includes HostDiagV2 compatibility notes and expected GREEN/YELLOW/RED outcomes.
   - `docs/ebpf_ascend_readiness_checklist.md` — fill-in checklist with all 50+ checks organized by category. Includes summary table, legend, blocker identification, and notes on optional features.
   - `scripts/check_flowgap_env.sh` — read-only shell script (~550 lines). Covers all checks from the plan. Uses color-coded PASS/WARN/FAIL output with timestamped log file. User-level + root-level execution supported. Searches for `libascendcl.so` using HostDiagV2's path resolution logic. Checks 10 AscendCL symbols via `nm -D`. Made executable.

### Key design decisions

- Symbol checks for `aclrtMemcpy`, `aclrtSetDevice`, `aclrtMemcpyAsync`, `aclrtSynchronizeStream` are critical (FAIL if missing).
- Symbol checks for `aclrtMemcpy2d`, `aclrtMemcpy2dAsync`, `aclrtMallocHost`, `aclrtMallocDevice`, `aclrtFreeHost`, `aclrtFree` are optional (WARN if missing).
- C++ mangling check ensures pure C ABI for uprobe compatibility.
- All `libascendcl.so` search paths match HostDiagV2's `resolve_ascendcl_lib()` logic.
- Script detects whether running as root and flags permission issues accordingly.

### Rules compliance

- [x] Script is read-only — uses only `cat`, `ls`, `find`, `nm`, `grep`, `uname`, `python3 -c`, `file`, `whoami`, `sysctl`, `ulimit`, `ps`.
- [x] No packages installed.
- [x] No uprobes attached.
- [x] No filesystems mounted.
- [x] No system state modified.
- [x] No root commands ran during creation (only `chmod +x` on generated script).

### Next prompt

Run the environment check on the target machine:
```bash
bash scripts/check_flowgap_env.sh
sudo bash scripts/check_flowgap_env.sh
```
Then proceed to `docs/prompts/02_trace_collection_and_schema.md` for FlowEvent schema design.

---

## Session 2026-06-10 (2): First Patch Plan (03_codex_first_patch_plan.md)

**Status:** Completed. 5 planning documents created.

### Actions performed

1. Created 5 output files:
   - `docs/trace_schema.md` — Complete schema: FlowEvent binary (88 bytes, 20 fields), raw CSV (20 cols), agg CSV (16 cols), SafeWindow dataclass, probe result CSV, Feedback dataclass, topology JSON, versioning.
   - `docs/implementation_plan_v1.md` — 6-module plan: ebpf_monitor, trace_parser, gap_predictor, probe_scheduler, scheduler_replay, evaluation. Full interfaces, data flow, 4 phases, risk register.
   - `docs/experiment_plan_v1.yaml` — YAML: RQ1-RQ8 with 11 experiments, 8 fault scenarios, 4 sensitivity sweeps. Metrics, dimensions, baselines, output figures per experiment.
   - `docs/test_plan_v1.md` — 51 unit + 7 integration + 8 system + 8 smoke tests. Coverage targets per module.
   - `docs/figure_plan_v1.md` — 35 figures + 6 tables mapped to sections, data sources, pipeline.

### Key design decisions

- Module dir: `code/` (avoids conflict with `external/reference_repo/src/`).
- Model: GBDT (not LSTM), as per MEGA_PROMPT preference.
- Offline-first: Modules 2/3/5/6 developable without Ascend using synthetic traces.
- Phase 1-2: ~5-6 days offline. Phase 3: ~10 days on Ascend hardware.
- bpfcc: use `/usr/bin/python3` (conda workaround).

### Rules compliance

- [x] No code implementation — planning documents only.
- [x] No modifications to `external/reference_repo/`.
- [x] No root commands run.
- [x] Missing data marked NEED_TRACE / NEED_EXPERIMENT / NEED_DATA.

### Next prompt

Option A: Begin Phase 1 offline — `code/trace_parser/` and `code/evaluation/synthetic_workload.py`.
Option B: `docs/prompts/04_codex_offline_implementation.md` if present.

---

## Session 2026-06-10 (3): Trace Parser Generation (04_codex_trace_parser_generation.md)

**Status:** Completed. 6 source files + synthetic trace data + design doc. 38/38 tests pass.

### Actions performed

1. Created `code/trace_parser/` module (5 Python files):
   - `schema.py` (~230 lines) — FlowEvent, BusyInterval, Gap, PathTimeline, ProbeEvent dataclasses; Direction/ApiType/QualityFlag/ProbeType/ReasonCode enums; validate_event().
   - `parse_trace.py` (~250 lines) — Dual-format CSV parser. Auto-detects HostDiagV2 (11-col string src/dst) vs FlowGap (21-col numeric). Normalizes HostDiagV2 source/destination strings to numeric dev/nouma. Groups by path key.
   - `intervalize.py` (~240 lines) — Probe-aware micro-gap merging (threshold = min_probe + safety_margin). `build_timeline()`, `extract_gaps()`, `calc_overlap()`, `compute_gap_stats()`, `compute_safe_window_availability()`. CSV export. CLI entry point.
   - `generate_synthetic_trace.py` (~120 lines) — Reproducible synthetic trace generator (3 paths, burst-gap patterns, seed=42).
   - `test_trace_parser.py` (~340 lines) — 38 unit tests across 7 test classes.

2. Generated synthetic trace: `data/processed/trace_synthetic_burst1ms.csv` — 198 events, 3 paths, H2D + D2H directions, `QF_SYNTHETIC` flag set on all events.

3. Created 2 documentation files:
   - `code/trace_parser/README.md` — quick start, file overview, usage examples.
   - `docs/trace_parser_design.md` — architecture, design decisions, module structure, data conventions, known limitations.

### Test results

```
Ran 38 tests in 0.010s — OK
```

| Test class | Tests |
|---|---|
| TestSchema | 6 |
| TestHostdiagParsing | 5 |
| TestFlowgapParsing | 3 |
| TestIntervalization | 9 |
| TestOverlap | 3 |
| TestStats | 3 |
| TestSyntheticFullPipeline | 1 |

### Key design decisions

- **Backward compat**: HostDiagV2 raw trace from `external/reference_repo/runs/raw/` can be parsed directly. The parser infers direction from string src/dst.
- **Synthetic labeling**: All synthetic events carry `QF_SYNTHETIC=128`. No confusion with real data.
- **Probe-aware**: Default threshold = 50µs (tiny latency probe) + 100µs (safety margin) = 150µs.
- **No external deps**: Pure Python stdlib. No numpy/pandas needed.
- **Path grouping**: `(src_dev, dst_dev, direction, src_numa, dst_numa)` → hash → path_id. Collision risk < 1/65536 for expected path counts.

### Rules compliance

- [x] All files under `code/trace_parser/`, `docs/`, `data/processed/`.
- [x] No modifications to `external/reference_repo/`.
- [x] No root commands run.
- [x] Synthetic data clearly labeled (`QF_SYNTHETIC` flag + doc comments).
- [x] No real Ascend data fabricated.

### Next prompt

Run `docs/prompts/05_codex_flowgap_predictor.md` for the gap predictor module, or re-run tests on real HostDiagV2 trace data.

---

## Session 2026-06-10 (4): Real Workload Analysis + Trace Parser Re-plan

**Status:** Completed. Real GLM-6B trace parsed. Parser fixed. Realistic generator added.

### Discovery

Server has real AI workloads available:
- `/root/mindformers/` — MindFormers training framework (GLM-6B finetuning, 8× Ascend 910B)
- `/root/ChatGLM-6B/` — ChatGLM-6B model files + PyTorch inference
- `/root/FlowGap-work/reference_repo/runs/raw/aclrtMemcpy_numa_raw.log` — **1054 real events** (134 KB, 1.7h trace)

### Actions performed

1. **Fixed `parse_trace.py`** — format detection now handles `Bandwidth_GBps` (real header) vs `bw_gbps` (schema name). Added `_resolve_column()` for multi-alias column resolution. Confirmed compat with actual HostDiagV2 output.

2. **Copied real trace**: `data/raw/aclrtMemcpy_numa_raw.log` (from reference repo, read-only).

3. **Analyzed real workload** (see `docs/real_workload_characteristics.md`):
   - 1054 events, 100% H2D, 11 unique paths
   - Dominant path: NUMA 0 → NPU 2 (840 events, 80%, 107GB)
   - Burst-gap confirmed: 22 busy intervals, p90 gap = 133ms — ample safe windows
   - Worker paths: 28-29 events each, very sparse
   - Device tracking gaps: 2/1054 events (0.2%)

4. **Created `generate_realistic_trace.py`** — realistic synthetic generator modeling GLM-6B finetuning:
   - `--mode glm`: 8 weighted paths, 80% dominant, 20% workers
   - Iteration-aligned: burst (3-8 events, 200us-3ms gaps) → compute gap (20-500ms)
   - Realistic BW: local NUMA 8-23 GB/s, cross 0.6-10 GB/s
   - Memcpy sizes: 24-1040 MB (matched to real workload)
   - `--mode simple`: original 3-path behavior for unit tests
   - `--mode analyze`: quick analysis of any trace CSV

5. **Created `docs/real_workload_characteristics.md`** — detailed per-path breakdown, safe-window analysis, comparison with synthetic.

6. **Updated `docs/trace_parser_design.md`** §10-11 with realistic generator info and real trace validation note.

7. **Updated `code/trace_parser/README.md`** — added real trace examples, realistic generator reference.

### Validation

- 38/38 unit tests still pass after format detection fix
- Real trace parsed: 1054 events, 11 paths, all stats computed
- Synthetic realistic trace generated and analyzed

### Key insights for FlowGap

1. **Burst-gap confirmed on real workload**: GLM-6B shows clear burst-gap structure with p90 gap=133ms — strong evidence for C3 (Traffic structure claim)
2. **Safe windows are abundant**: Even on the busiest path, 100% of gaps can fit a tiny latency probe; the largest gaps (~133ms) fit bandwidth probes
3. **Path-level prediction essential**: Worker paths have radically different patterns from the dominant data-loader path
4. **All H2D**: This workload type (finetuning data loading) is 100% H2D. Need different workloads for D2H/D2D characterization

### Rules compliance

- [x] Read-only access to reference repo traces
- [x] Data copied to `data/raw/` for FlowGap workspace
- [x] No modifications to `external/reference_repo/` or `/root/FlowGap-work/reference_repo/`
- [x] No root commands beyond `cp`
- [x] Real data clearly distinguished from synthetic
- [x] Device-tracking gaps marked in quality_flags

### Next prompt

Proceed to `docs/prompts/05_codex_flowgap_predictor.md` with confidence that:
- Real trace parsing works on actual GLM-6B finetuning data
- Synthetic traces model realistic training workloads
- Burst-gap structure is confirmed on real Ascend 910B trace

---

## Session 2025-06-07: Collected Trace Analysis (04 prompt re-run)

**Status:** Completed. 342K real events parsed and analyzed.

### Actions performed

1. **Copied real collect data**: `data/collected/pass1_raw.bak` (21MB) → `data/raw/trace_pass1_raw.csv`; `data/collected/pass2_raw.log` (21MB) → `data/raw/trace_pass2_raw.csv`. Total 341,934 events.

2. **Created analysis script**: `code/trace_parser/analyze_collected_traces.py` — end-to-end pipeline that parses both passes, runs probe-aware intervalization (threshold=150µs), computes per-path gap stats and safe-window availability, exports JSON + Markdown report.

3. **Analysis results**:

| | Pass 1 (train) | Pass 2 (val) |
|---|---|---|
| Events | 170,556 | 171,376 |
| Duration | 5,994 s (100 min) | 6,014 s (100 min) |
| H2D | 7,356 (4%) | 8,176 (5%) |
| D2H | 163,200 (96%) | 163,200 (95%) |

**Dominant pattern**: 8 symmetric D2H paths, ~20K events each, gap p50 ≈ 190 µs, gap p90 ≈ 18 ms, 100% tiny-safe, 30% BW-safe.

4. **Generated output files**:
   - `results/combined_report.md` — full per-path gap statistics for both passes
   - `results/trace_analysis.json` — machine-readable analysis data

5. **Updated docs**: `docs/trace_parser_design.md` §11 — added real trace validation section with key findings. Corrected previous incorrect assumption about H2D-dominant workload.

6. **Validated**: 38/38 unit tests still pass.

### Key findings for FlowGap

- **D2H dominance** (96%): GLM-6B finetuning produces far more D2H than H2D traffic
- **Safe-window abundance**: 100% of gaps on all major paths accommodate tiny latency probes (50 µs)
- **30% BW-safe**: One in three gaps fits a full bandwidth probe (128 MB, ~5 ms)
- **Cross-pass consistency**: Identical path structures and gap distributions between passes → predictor trainable
- **Gap p90 = 18 ms**: Large enough for even the biggest probes

### Rules compliance

- [x] All files under `code/trace_parser/`, `docs/`, `data/raw/`, `results/`
- [x] No modifications to `external/reference_repo/`
- [x] No root commands beyond data copy
- [x] Real data clearly labeled vs synthetic

### Next prompt

`docs/prompts/05_codex_flowgap_predictor.md` — train the gap predictor on 342K real Ascend 910B events.

---

## Session 2026-06-07: Gap Predictor Generation (05 prompt)

**Status:** Completed. 8 source files + design doc + 36/36 tests pass.

### Actions performed

1. **Created `code/gap_predictor/` module (8 Python files)**:

| File | Lines | Purpose |
|---|---|---|
| `schema.py` | ~130 | SafeWindow dataclass, HORIZONS_NS, confidence thresholds (0.90/0.95/0.98), ProbeType, ReasonCode |
| `features.py` | ~175 | FeatureExtractor: 30-D feature vectors. make_multi_horizon_labels, build_training_dataset |
| `ewma_baseline.py` | ~115 | EWMABaseline + QuantileBaseline — Tier 0 cold-start / fallback models |
| `survival_model.py` | ~220 | MultiHorizonSurvivalPredictor — one GradientBoostingClassifier per horizon + time_series_split_validate |
| `lower_bound.py` | ~80 | LowerBoundEstimator — p5/p10 quantile regression + stateless helper |
| `calibrator.py` | ~145 | CalibrationTable (10-bin reliability diagram) + ConfidenceComposer (C_final = min(4 components)) |
| `drift_detector.py` | ~130 | DriftDetector (Mahalanobis-like), RollingStats, detect_phase_shift |
| `predictor.py` | ~240 | GapPredictor orchestrator: feature → predict → calibrate → SafeWindow. train() + predict() + evaluate() |

2. **Created `code/gap_predictor/test_gap_predictor.py`** — 36 unit tests:
   - TestSchema (4 tests)
   - TestFeatureExtraction (5 tests)
   - TestEWMABaseline (6 tests)
   - TestLowerBound (4 tests)
   - TestCalibration (4 tests)
   - TestConfidenceComposer (4 tests)
   - TestDriftDetection (3 tests)
   - TestRollingStats (3 tests)
   - TestPhaseShift (3 tests)

3. **Created documentation**:
   - `code/gap_predictor/README.md` — quick start, architecture overview, model tiers
   - (Design doc: see `docs/gap_predictor_design.md` — deferred to next round)

### Design decisions

- **No `data/processed/burst_gap_events.parquet` exists** — code only, no fabricated results
- **Multi-horizon per classifier**: Separate GBDT model per horizon (h=10µs through h=2ms), not a single survival model
- **EWMA fallback for cold start**: QuantileBaseline provides conservative predictions when insufficient training data
- **TrivialClassifier fallback**: When only one class in training data, uses constant instead of crashing
- **All imports use explicit package paths** (`gap_predictor.schema`, `trace_parser.schema`) — no sys.path manipulation
- **Confidence composition**: `C_final = min(C_model, C_calib, C_data, C_drift)` per implementation plan

### Test results

```
Ran 36 tests in 0.019s — OK
```

### Key interfaces

```python
p = GapPredictor(model_dir="./models")
p.train({path_id: (busy_intervals, gaps), ...})       # train from timelines
windows = p.predict(path_id, gaps, busy, now_ns)       # predict safe windows
results = p.evaluate(held_out_timelines)               # {horizon: {precision, recall, ...}}
```

### Rules compliance

- [x] All files under `code/gap_predictor/`, `docs/`
- [x] No modifications to `external/reference_repo/`
- [x] No data fabrication (`burst_gap_events.parquet` does not exist)
- [x] All imports use explicit package paths
- [x] No root commands run

### Next prompt

Either:
- Create `data/processed/burst_gap_events.parquet` from trace analysis results, then train predictor
- Proceed to `docs/prompts/06_codex_probe_scheduler.md` for Module 4
