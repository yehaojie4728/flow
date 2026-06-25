# FlowGap docs/ 目录文件整理

> 共 44 个 .md 文件。按用途分 10 类，标注每个文件的用途和是否对论文仍有参考价值。

---

## A. 论文写作类（Paper Writing）— 7 个

写作时最常参考的文件，产出论文大纲和系统描述。

| 文件 | 用途 | 状态/备注 |
|------|------|---------|
| `paper_storyline.md` | 论文故事情节：问题→洞察→系统→证据链→SoCC 定位 | 写作前需重读，确保逻辑一致 |
| `topic.md` | 论文主题定义：题目、问题陈述、核心洞察、模块、设计原则 | 写作前需重读 |
| `topic_init.md` | 早期主题草稿：贡献、非目标、风险评估 | 写作时仅需核对贡献是否一致 |
| `outline.md` | 旧版中文大纲（12 节，含实验计划） | 已被 `../paper_outline_socc.md` 取代，仅历史参考 |
| `figure_plan_v1.md` | v1 版配图计划 | 已被 `../paper_outline_socc.md` 附录 A 取代 |
| `claims.md` | 声明账本：11 条 claim，标记了允许/禁止措辞和证据要求 | 写作时作为措辞约束 |
| `ai_usage_disclosure.md` | AI 使用声明 | 投稿时需附 |

---

## B. 系统架构与设计类（System Architecture & Design）— 6 个

描写 §3 System Design 时的核心参考。

| 文件 | 用途 | 状态/备注 |
|------|------|---------|
| `system_architecture.md` | **主文档**：系统概述、5 模块详解、实验结果、Roadmap | 写 Design 和 Evaluation 的第一手参考 |
| `architecture_diagram_spec.md` | **绘制的**架构图规格（4 区块 + Mermaid + 绘图 checklist） | 今天的产出，供绘图工具使用 |
| `trace_schema.md` | FlowEvent 数据结构定义（binary wire format + timeline schema） | 写 §3.4 Trace Parser 的细节来源 |
| `trace_parser_design.md` | Trace Parser 设计文档：CSV→FlowEvent→Timeline 的完整流程 | 同上 |
| `scheduler_replay_design.md` | Scheduler Replay 设计（用于离线评估策略对比） | 写 §3.6 的部分细节 |
| `problem_decompose.md` | 9 部分问题分解：采集/标准化/时间线/异步估计/预测/校准/探测器/分析器/评估 | 架构设计的参考地图，写 Intro 可用 |

---

## C. 实验设计与结果类（Experiments & Results）— 4 个

| 文件 | 用途 | 状态/备注 |
|------|------|---------|
| `experiment_checklist.md` | 实验矩阵清单（P0.x / P1.x / P2.x） | 所有实验已标记完成，历史参考 |
| `P0.4_HOWTO.md` | P0.4 故障注入实验操作手册 | 待补充 P0.4 后续重跑的详细记录 |
| `real_workload_characteristics.md` | GLM-6B 真实负载特征分析（20+ 图表级统计） | 写 §2.3（关键观察）的数据宝库 |
| `test_plan_v1.md` | v1 版测试计划 | 历史参考 |

---

## D. 相关文献类（Literature）— 2 个

| 文件 | 用途 | 状态/备注 |
|------|------|---------|
| `literature/related_work_final.md` | **终版** Related Work（4 主题，~1.5 页，含 SoCC 定位和 GBDT 选型理由） | 直接用于 §7 |
| `literature/related_work_outline.md` | 旧版 Related Work 草稿 | 已被 final.md 取代 |

---

## E. 实现计划类（Implementation Plans）— 3 个

| 文件 | 用途 | 状态/备注 |
|------|------|---------|
| `implementation_plan_v1.md` | v1 版实现计划（模块优先级和工期） | 历史参考 |
| `reuse_plan.md` | 从 HostDiagV2 的复用计划（4 tier: direct / adapt / reference / from-scratch） | 写 Implementation 章可引用"复用思路"，但非必须 |
| `first_patch_plan.md` | 首个 Patch 计划（P0–P3） | 历史参考 |

---

## F. 参考仓库分析类（Reference Repo Analysis）— 3 个

| 文件 | 用途 | 状态/备注 |
|------|------|---------|
| `reference_repo_analysis.md` | HostDiagV2 代码级差距分析（vs FlowGap） | 历史存档，写 Related Work 时可能提及 HostDiag 细节 |
| `repo_map.md` | HostDiagV2 仓库文件清单 + 搜索分类 | 历史存档 |
| `real_workload_characteristics.md` | （同 C 类） | 也属于仓库分析产出 |

---

## G. Agent 工作流类（Agent Workflow Prompts）— 7 个

执行分步任务的 Agent 指令文件，项目 bootstrap 阶段的产物。写作阶段不再需要，仅历史存档。

| 文件 | 用途 |
|------|------|
| `prompts/00_codex_bootstrap_analyze_only.md` | 第 0 步：只读分析，不改代码 |
| `prompts/01_codex_reference_repo_analysis.md` | 第 1 步：分析 HostDiagV2 参考仓库 |
| `prompts/02_codex_environment_probe_plan.md` | 第 2 步：环境探测计划 |
| `prompts/03_codex_first_patch_plan.md` | 第 3 步：首个代码 Patch 计划 |
| `prompts/04_codex_trace_parser_generation.md` | 第 4 步：生成 Trace Parser |
| `prompts/05_codex_gap_predictor_generation.md` | 第 5 步：生成 Gap Predictor |
| `prompts/06_codex_scheduler_replay_generation.md` | 第 6 步：生成 Scheduler Replay |
| `prompts/07_codex_socc_paper_scaffold.md` | 第 7 步：论文脚手架 |

---

## H. 环境部署类（Environment Setup）— 5 个

| 文件 | 用途 | 状态/备注 |
|------|------|---------|
| `setup/00_MASTER_RUNBOOK.md` | 总运行手册：远程服务器启动 FlowGap 的全流程 | 部署参考 |
| `setup/01_environment_setup_aarch64_910A.md` | Ascend 910A 环境搭建（CANN, conda, bpfcc） | 部署参考 |
| `setup/02_create_workspace_and_reference_repo.md` | 工作区创建 + 参考仓库导入 | 部署参考 |
| `setup/03_install_scientific_agent_skills_for_codex.md` | 安装 Agent skills（aeon/statistical-analysis 等） | 仅 Agent 使用，非论文内容 |
| `ebpf_ascend_readiness_checklist.md` | eBPF 就绪检查清单（50+ 检查项） | 部署参考 |
| `environment_probe_plan.md` | 环境探测计划（9 类检查） | 部署参考 |

---

## I. 项目管理类（Project Management）— 5 个

| 文件 | 用途 | 状态/备注 |
|------|------|---------|
| `MEGA_PROMPT.md` | Agent 的"总身份"文件：项目规则、SoCC 约束、skill 覆盖、硬限制 | Agent 使用，非论文内容 |
| `skill_usage_policy.md` | Agent 可用的 skill 白名单和限制 | Agent 使用 |
| `session_handover.md` | 项目交接文档：已完成工作、关键数据、待办 | 多轮协作的"上下文快照" |
| `work_items.md` | 12 阶段任务拆解（环境→分析→解析→预测→探测器→评估→写作） | 整体进度追踪 |
| `submission_checklist_socc2026.md` | SoCC 投稿检查清单 | 投稿前逐项核对 |

---

## J. 投稿规范类（Venue）— 1 个

| 文件 | 用途 | 状态/备注 |
|------|------|---------|
| `venue/socc2026_acm_prep.md` | SoCC 2026 投稿要求：deadline、formatting、anonymity、reserve reviewer、AI usage | 投稿前必读 |

---

## 汇总

| 类别 | 数量 | 论文写作时需参考？ |
|------|:---:|:---:|
| A. 论文写作 | 7 | ✅ 核心参考 |
| B. 系统架构与设计 | 6 | ✅ 写 Design/Implementation 时参考 |
| C. 实验设计与结果 | 4 | ✅ 写 Evaluation 时参考 |
| D. 相关文献 | 2 | ✅ 直写入 §7 |
| E. 实现计划 | 3 | 可选引用（Implementation 章） |
| F. 参考仓库分析 | 2(+1) | 仅 Related Work 可能提及 HostDiag |
| G. Agent 工作流 | 8 | 历史存档，写作阶段不再需要 |
| H. 环境部署 | 5(+1) | 写作时不需要（环境已搭建完成） |
| I. 项目管理 | 5 | Agent 使用 / 投稿 checklist |
| J. 投稿规范 | 1 | 投稿前必读 |
| **合计** | **44** | 写作核心：A+B+C+D ≈ 19 个文件 |

---

## 推荐：从哪些文件开始写作

按论文章节顺序，推荐阅读顺序如下：

| 论文章节 | 优先参考的文件 |
|---------|---------------|
| §1 Introduction | `paper_storyline.md`, `topic.md`, `problem_decompose.md`, `outline.md` |
| §2 Background & Motivation | `system_architecture.md` §2-4, `real_workload_characteristics.md` |
| §3 System Design | `system_architecture.md` §5-6, `trace_schema.md`, `trace_parser_design.md`, `architecture_diagram_spec.md` |
| §4 Implementation | `implementation_plan_v1.md`, `reuse_plan.md` |
| §5 Evaluation | `system_architecture.md` §7, `../code/results/P*.md` 各实验报告, `experiment_checklist.md` |
| §6 Discussion | `claims.md`, `session_handover.md` |
| §7 Related Work | `literature/related_work_final.md` |
| 投稿 | `venue/socc2026_acm_prep.md`, `submission_checklist_socc2026.md`, `ai_usage_disclosure.md` |
