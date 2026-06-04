# 02. 创建隔离工作区并放入参考代码

---

## 1. 创建总目录

```bash
mkdir -p ~/FlowGap-work
cd ~/FlowGap-work
```

---

## 2. 放入原始参考代码

从 Git clone：

```bash
git clone <你的原始参考仓库URL> reference_repo
```

或从已有目录复制：

```bash
rsync -a --exclude .git /path/to/original_repo/ ~/FlowGap-work/reference_repo/
```

---

## 3. 创建 FlowGap-paper 工作区

```bash
mkdir -p ~/FlowGap-work/FlowGap-paper
cd ~/FlowGap-work/FlowGap-paper

git init
git checkout -b flowgap-agent-analysis
```

---

## 4. 创建目录结构

```bash
mkdir -p docs/prompts docs/setup docs/venue refs papers/raw papers/notes
mkdir -p external/reference_repo
mkdir -p .agent/skills
mkdir -p code/trace_parser code/gap_predictor code/probe_scheduler code/scheduler_replay code/ebpf_monitor code/evaluation
mkdir -p data/traces data/processed
mkdir -p results/raw results/processed results/stats results/figures_data results/quality_reports
mkdir -p paper/sections paper/figures
mkdir -p scripts
```

---

## 5. 复制参考代码到项目内部

```bash
rsync -a --exclude .git ~/FlowGap-work/reference_repo/ external/reference_repo/
chmod -R a-w external/reference_repo
```

---

## 6. 初始化主题文件

如果你已有主题和大纲，复制到：

```text
docs/topic.md
docs/outline.md
```

否则先写最小版：

```bash
cat > docs/topic.md <<'EOF'
# FlowGap 论文主题

论文题目：
基于流量模式预测的低干扰主机内探测系统

面向平台：
Ascend 910A/910B memcpy traffic

一句话问题：
如何从 Ascend 主机内 memcpy 流量中学习 burst-gap 模式，并预测 probe 的安全发送窗口，从而降低 probe 对 AI workload 的干扰？

系统主线：
eBPF 采集 memcpy/sync 事件
-> 构建 path/link 级 busy-idle 时间线
-> 预测未来 safe window
-> 在 safe window 中发起 probe
-> 分析 probe 结果并反馈给预测器

非目标：
- 不做完整 root cause diagnosis；
- 不精确重建所有物理链路流量；
- 不保证预测每一次 memcpy 的精确开始时间；
- 不把深度学习模型作为主贡献。
EOF

touch docs/outline.md
```

---

## 7. 初始提交

```bash
git add .
git commit -m "Initialize isolated FlowGap workspace"
```
