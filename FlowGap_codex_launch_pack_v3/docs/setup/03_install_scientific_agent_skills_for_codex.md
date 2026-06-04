# 03. 为 Codex 安装 scientific-agent-skills

---

## 1. 原则

不要全量安装 `K-Dense-AI/scientific-agent-skills`。

只安装 FlowGap 需要的 skills。

---

## 2. 推荐 skills

核心：

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
```

写作/审稿：

```text
scientific-writing
literature-review
peer-review
venue-templates
```

不建议安装：

```text
autoskill
generate-image
scientific-schematics
infographics
clinical-decision-support
clinical-reports
treatment-plans
research-grants
```

---

## 3. gh skill 方式

```bash
cd ~/FlowGap-work/FlowGap-paper

export SKILL_REPO=K-Dense-AI/scientific-agent-skills
export AGENT=codex
export SKILL_PIN=$(git ls-remote https://github.com/K-Dense-AI/scientific-agent-skills.git HEAD | awk '{print $1}')
echo "$SKILL_PIN" | tee .skill-pin
```

安装：

```bash
for s in   paper-lookup   exploratory-data-analysis   aeon   statsmodels   scikit-learn   statistical-analysis   scientific-visualization   markdown-mermaid-writing   simpy   pymoo   scientific-writing   literature-review   peer-review   venue-templates
do
  echo "=== Preview $s ==="
  gh skill preview "$SKILL_REPO" "$s" --pin "$SKILL_PIN" || true

  echo "=== Install $s ==="
  gh skill install "$SKILL_REPO" "$s" --agent "$AGENT" --scope user --pin "$SKILL_PIN"
done
```

如果 `--pin` 不支持，查看：

```bash
gh skill install --help
```

---

## 4. 手动复制方式

```bash
cd ~/FlowGap-work/FlowGap-paper

mkdir -p third_party .agent/skills

git clone --depth 1 https://github.com/K-Dense-AI/scientific-agent-skills.git   third_party/scientific-agent-skills

for s in   paper-lookup   exploratory-data-analysis   aeon   statsmodels   scikit-learn   statistical-analysis   scientific-visualization   markdown-mermaid-writing   simpy   pymoo   scientific-writing   literature-review   peer-review   venue-templates
do
  cp -a "third_party/scientific-agent-skills/scientific-skills/$s" ".agent/skills/$s"
done

find .agent/skills -maxdepth 2 -name SKILL.md | sort
```

---

## 5. 检查

```bash
find .agent/skills -maxdepth 2 -name SKILL.md | sort
gh skill list --agent codex || true
```
