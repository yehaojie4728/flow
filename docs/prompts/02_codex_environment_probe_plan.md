Read first:

- `AGENTS.md`
- `docs/MEGA_PROMPT.md`
- `docs/claims.md`
- `docs/skill_usage_policy.md`
- `docs/venue/socc2026_acm_prep.md`

# Codex Prompt 02: Environment Probe Plan

Read also:

- `docs/reference_repo_analysis.md`
- `docs/reuse_plan.md`

Do not run root-level commands unless the user explicitly approves.

---

## Current task

Create an environment probe plan for the Ascend 910A aarch64 EulerOS/openEuler machine.

---

## Outputs

Create:

- `docs/environment_probe_plan.md`
- `docs/ebpf_ascend_readiness_checklist.md`
- `scripts/check_flowgap_env.sh`

The script must be read-only.

It may run commands like `uname`, `cat /etc/os-release`, `find`, `nm`, `grep`, but it must not modify system state.

Do not mount filesystems.

Do not install packages.

Do not attach uprobes.
