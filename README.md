# FlowGap Codex Launch Pack v3

用于在远程 Ascend 910A / aarch64 / EulerOS 或 openEuler 环境中启动 FlowGap 论文与代码项目。

核心目标：

1. 不污染原始参考代码；
2. 让 Codex 第一轮只分析，不改代码；
3. 准备 scientific-agent-skills；
4. 准备 CoNEXT 2026 / ACM acmart 写作约束；
5. 为 trace parser、safe-window predictor、scheduler replay、论文撰写做准备。

推荐用法：

```bash
cd ~/FlowGap-work/FlowGap-paper
unzip FlowGap_codex_launch_pack_v3.zip
rsync -a FlowGap_codex_launch_pack_v3/ ./
bash scripts/check_flowgap_pack_manifest.sh
```

第一条投喂 Codex：

```text
请读取并执行 docs/prompts/00_codex_bootstrap_analyze_only.md。
严格遵守 AGENTS.md、docs/MEGA_PROMPT.md、docs/claims.md、docs/skill_usage_policy.md、docs/venue/conext2026_acm_prep.md。
本轮只分析，不要修改 external/reference_repo/，不要生成代码，不要运行 root 命令，不要安装依赖。
```

第二条投喂 Codex：

```text
请读取并执行 docs/prompts/01_codex_reference_repo_analysis.md。
本轮只分析 external/reference_repo/，不要修改代码，不要运行 root 命令。
```

详细流程见：

```text
docs/setup/00_MASTER_RUNBOOK.md
```
