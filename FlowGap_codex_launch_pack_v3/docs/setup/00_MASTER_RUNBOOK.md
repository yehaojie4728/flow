# 00. FlowGap 从零启动总流程

适用环境：

- SSH 远程 Ascend 910A；
- aarch64；
- EulerOS / openEuler；
- 有 root 权限；
- VSCode Remote SSH 中使用 Codex Agent；
- 不直接修改原始参考代码；
- 目标投稿 CoNEXT 2026。

---

## 0. 总原则

流程分为 8 阶段：

```text
阶段 1：系统环境检查与依赖安装
阶段 2：创建隔离工作区
阶段 3：放入原始参考代码，只读
阶段 4：放入本文件包
阶段 5：安装 scientific-agent-skills
阶段 6：在 VSCode 中启动 Codex，第一轮只分析
阶段 7：Codex 生成环境检查计划和第一版 patch plan
阶段 8：你审核后，才允许 Codex 生成 trace parser / predictor / scheduler replay
```

最重要原则：

```text
第一轮 Codex 只能分析，不允许改 external/reference_repo/。
```

---

## 1. 最终目录结构

```text
~/FlowGap-work/
├── reference_repo/             # 原始参考代码，保持干净
└── FlowGap-paper/              # Codex 工作目录
    ├── AGENTS.md
    ├── docs/
    │   ├── MEGA_PROMPT.md
    │   ├── claims.md
    │   ├── skill_usage_policy.md
    │   ├── topic.md
    │   ├── outline.md
    │   ├── setup/
    │   ├── prompts/
    │   └── venue/
    ├── external/
    │   └── reference_repo/     # 只读参考代码副本
    ├── .agent/
    │   └── skills/
    ├── code/
    ├── data/
    ├── results/
    ├── paper/
    └── scripts/
```

---

## 2. 阶段 1：系统环境检查与依赖安装

先阅读并执行：

```text
docs/setup/01_environment_setup_aarch64_910A.md
```

这一步检查：

```text
uname -m
/etc/os-release
Ascend/CANN 路径
libascendcl.so
eBPF/uprobe 能力
Python/Conda/uv
GitHub CLI gh
Codex 是否可用
```

---

## 3. 阶段 2：创建隔离工作区

阅读并执行：

```text
docs/setup/02_create_workspace_and_reference_repo.md
```

核心命令：

```bash
mkdir -p ~/FlowGap-work
cd ~/FlowGap-work

git clone <你的原始参考仓库URL> reference_repo

mkdir -p FlowGap-paper
cd FlowGap-paper
git init
git checkout -b flowgap-agent-analysis
```

如果你的参考代码已经在本地：

```bash
rsync -a --exclude .git /path/to/original_repo/ ~/FlowGap-work/reference_repo/
```

---

## 4. 阶段 3：复制参考代码到 external/reference_repo/

```bash
cd ~/FlowGap-work/FlowGap-paper
mkdir -p external/reference_repo
rsync -a --exclude .git ~/FlowGap-work/reference_repo/ external/reference_repo/
chmod -R a-w external/reference_repo
```

作用：

```text
让 Codex 能看到参考代码，但第一轮只读，不修改。
```

---

## 5. 阶段 4：放入本文件包

把 `FlowGap_codex_launch_pack_v3.zip` 上传到：

```text
~/FlowGap-work/FlowGap-paper/
```

然后：

```bash
cd ~/FlowGap-work/FlowGap-paper
unzip FlowGap_codex_launch_pack_v3.zip
rsync -a FlowGap_codex_launch_pack_v3/ ./
bash scripts/check_flowgap_pack_manifest.sh
```

这会把以下文件放到正确位置：

```text
AGENTS.md
docs/MEGA_PROMPT.md
docs/claims.md
docs/skill_usage_policy.md
docs/venue/conext2026_acm_prep.md
docs/prompts/*.md
docs/setup/*.md
scripts/*.sh
```

---

## 6. 阶段 5：安装 scientific-agent-skills

阅读并执行：

```text
docs/setup/03_install_scientific_agent_skills_for_codex.md
```

建议安装：

```text
paper-lookup
exploratory-data-analysis
aeon
statsmodels
scikit-learn
statistical-analysis
scientific-visualization
markdown-mermaid-writing
simpy
pymoo
scientific-writing
literature-review
peer-review
venue-templates
```

不要全量安装。

---

## 7. 阶段 6：启动 Codex

在 VSCode Remote SSH 中打开：

```text
~/FlowGap-work/FlowGap-paper
```

不要打开：

```text
~/FlowGap-work/reference_repo
```

第一轮投喂：

```text
docs/prompts/00_codex_bootstrap_analyze_only.md
```

预期产物：

```text
docs/topic_init.md
docs/problem_decompose.md
docs/paper_storyline.md
docs/work_items.md
PROGRESS.md
```

第二轮投喂：

```text
docs/prompts/01_codex_reference_repo_analysis.md
```

预期产物：

```text
docs/repo_map.md
docs/reference_repo_analysis.md
docs/reuse_plan.md
docs/first_patch_plan.md
```

---

## 8. 阶段 7：环境检查计划和第一版 patch plan

第三轮：

```text
docs/prompts/02_codex_environment_probe_plan.md
```

预期产物：

```text
docs/environment_probe_plan.md
docs/ebpf_ascend_readiness_checklist.md
scripts/check_flowgap_env.sh
```

第四轮：

```text
docs/prompts/03_codex_first_patch_plan.md
```

预期产物：

```text
docs/trace_schema.md
docs/implementation_plan_v1.md
docs/experiment_plan_v1.yaml
docs/test_plan_v1.md
docs/figure_plan_v1.md
```

---

## 9. 阶段 8：你确认后才生成代码

只有当你确认：

```text
1. reference_repo 分析正确；
2. first_patch_plan 安全；
3. trace_schema 合理；
4. 不会污染 external/reference_repo；
5. 不会乱动系统或 CANN；
```

才投喂：

```text
docs/prompts/04_codex_trace_parser_generation.md
docs/prompts/05_codex_gap_predictor_generation.md
docs/prompts/06_codex_scheduler_replay_generation.md
```

---

## 10. CoNEXT 2026 写作准备

Codex 必须读取：

```text
docs/venue/conext2026_acm_prep.md
```

当前状态：

```text
CoNEXT 2026 官方页面已存在，但不要假设 CFP 细则完整公布。
投稿模板先按 ACM acmart sigconf review 格式准备。
页数、匿名、轮次、appendix、artifact 规则全部标为 NEED_CONEXT2026_CFP_CONFIRMATION。
```

---

## 11. 本文件包校对清单

| 步骤 | 需要文件 | 本包是否包含 |
|---|---|---|
| 环境配置 | docs/setup/01_environment_setup_aarch64_910A.md | 是 |
| 创建工作区 | docs/setup/02_create_workspace_and_reference_repo.md | 是 |
| 安装 skills | docs/setup/03_install_scientific_agent_skills_for_codex.md | 是 |
| Codex 总规则 | AGENTS.md | 是 |
| 论文总控 | docs/MEGA_PROMPT.md | 是 |
| Claim 台账 | docs/claims.md | 是 |
| Skill 策略 | docs/skill_usage_policy.md | 是 |
| CoNEXT/ACM 准备 | docs/venue/conext2026_acm_prep.md | 是 |
| 第一轮 Codex | docs/prompts/00_codex_bootstrap_analyze_only.md | 是 |
| 参考仓库分析 | docs/prompts/01_codex_reference_repo_analysis.md | 是 |
| 环境检查计划 | docs/prompts/02_codex_environment_probe_plan.md | 是 |
| 第一版 patch plan | docs/prompts/03_codex_first_patch_plan.md | 是 |
| trace parser 生成 | docs/prompts/04_codex_trace_parser_generation.md | 是 |
| predictor 生成 | docs/prompts/05_codex_gap_predictor_generation.md | 是 |
| scheduler replay 生成 | docs/prompts/06_codex_scheduler_replay_generation.md | 是 |
| CoNEXT 论文骨架 | docs/prompts/07_codex_conext_paper_scaffold.md | 是 |
| 文件检查脚本 | scripts/check_flowgap_pack_manifest.sh | 是 |
