#!/usr/bin/env bash
set -u

echo "== FlowGap launch pack manifest check =="

required_files="
AGENTS.md
docs/MEGA_PROMPT.md
docs/claims.md
docs/skill_usage_policy.md
docs/venue/conext2026_acm_prep.md
docs/setup/00_MASTER_RUNBOOK.md
docs/setup/01_environment_setup_aarch64_910A.md
docs/setup/02_create_workspace_and_reference_repo.md
docs/setup/03_install_scientific_agent_skills_for_codex.md
docs/prompts/00_codex_bootstrap_analyze_only.md
docs/prompts/01_codex_reference_repo_analysis.md
docs/prompts/02_codex_environment_probe_plan.md
docs/prompts/03_codex_first_patch_plan.md
docs/prompts/04_codex_trace_parser_generation.md
docs/prompts/05_codex_gap_predictor_generation.md
docs/prompts/06_codex_scheduler_replay_generation.md
docs/prompts/07_codex_conext_paper_scaffold.md
scripts/check_flowgap_pack_manifest.sh
scripts/bootstrap_flowgap_dirs.sh
"

missing=0

for f in $required_files; do
  if [ -f "$f" ]; then
    echo "[OK] $f"
  else
    echo "[MISSING] $f"
    missing=$((missing + 1))
  fi
done

echo
if [ "$missing" -eq 0 ]; then
  echo "All required files are present."
else
  echo "$missing required file(s) are missing."
  exit 1
fi
