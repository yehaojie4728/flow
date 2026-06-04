Read first:

- `AGENTS.md`
- `docs/MEGA_PROMPT.md`
- `docs/claims.md`
- `docs/skill_usage_policy.md`
- `docs/venue/conext2026_acm_prep.md`

# Codex Prompt 01: Reference Repository Analysis

If `external/reference_repo/` exists, inspect it.

This is an analyze-only task.

Do not modify `external/reference_repo/`.

Do not modify code.

Do not run root-level commands.

---

## Current task

Analyze the reference repository for potential reuse in FlowGap.

---

## What to find

Search for:

1. eBPF, bcc, libbpf, uprobe, kprobe, tracepoint code;
2. AscendCL / CANN APIs:
   - `aclrtSetDevice`
   - `aclrtMallocHost`
   - `aclrtMallocDevice`
   - `aclrtMemcpy`
   - `aclrtMemcpyAsync`
   - `aclrtMemcpy2d`
   - `aclrtMemcpy2dAsync`
   - `aclrtSynchronizeStream`
   - `aclrtFreeHost`
   - `aclrtFree`
3. prober code;
4. analyzer code;
5. trace/log schema;
6. build scripts;
7. risky code.

---

## Outputs

Create:

- `docs/repo_map.md`
- `docs/reference_repo_analysis.md`
- `docs/reuse_plan.md`
- `docs/first_patch_plan.md`

---

## Rules

- Do not invent code that is not present.
- If a file is unclear, mark NEED_MANUAL_CHECK.
- If a capability is only inferred, mark INFERRED.
- Do not modify code.
