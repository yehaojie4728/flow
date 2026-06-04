#!/usr/bin/env bash
set -u

echo "== Create FlowGap project directories =="

mkdir -p docs/prompts docs/setup docs/venue refs papers/raw papers/notes
mkdir -p external/reference_repo
mkdir -p .agent/skills
mkdir -p code/trace_parser code/gap_predictor code/probe_scheduler code/scheduler_replay code/ebpf_monitor code/evaluation
mkdir -p data/traces data/processed
mkdir -p results/raw results/processed results/stats results/figures_data results/quality_reports
mkdir -p paper/sections paper/figures
mkdir -p scripts

echo "Done."
