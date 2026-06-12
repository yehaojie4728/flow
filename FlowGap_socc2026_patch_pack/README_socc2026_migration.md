# FlowGap SoCC 2026 迁移补丁包

本补丁包用于把原先 CoNEXT 2026 目标配置切换为 SoCC 2026。

---

## 一、需要替换的文件

把本补丁包中的同名文件覆盖到项目根目录：

```text
AGENTS.md
docs/MEGA_PROMPT.md
docs/claims.md
docs/prompts/00_codex_bootstrap_analyze_only.md
scripts/check_flowgap_pack_manifest.sh
```

覆盖命令：

```bash
cd ~/FlowGap-work/FlowGap-paper
cp -a FlowGap_socc2026_patch_pack/AGENTS.md AGENTS.md
cp -a FlowGap_socc2026_patch_pack/docs/MEGA_PROMPT.md docs/MEGA_PROMPT.md
cp -a FlowGap_socc2026_patch_pack/docs/claims.md docs/claims.md
cp -a FlowGap_socc2026_patch_pack/docs/prompts/00_codex_bootstrap_analyze_only.md docs/prompts/00_codex_bootstrap_analyze_only.md
cp -a FlowGap_socc2026_patch_pack/scripts/check_flowgap_pack_manifest.sh scripts/check_flowgap_pack_manifest.sh
chmod +x scripts/check_flowgap_pack_manifest.sh
```

---

## 二、需要新增的文件

```text
docs/venue/socc2026_acm_prep.md
docs/prompts/07_codex_socc_paper_scaffold.md
docs/submission_checklist_socc2026.md
docs/ai_usage_disclosure.md
```

复制命令：

```bash
cd ~/FlowGap-work/FlowGap-paper
cp -a FlowGap_socc2026_patch_pack/docs/venue/socc2026_acm_prep.md docs/venue/socc2026_acm_prep.md
cp -a FlowGap_socc2026_patch_pack/docs/prompts/07_codex_socc_paper_scaffold.md docs/prompts/07_codex_socc_paper_scaffold.md
cp -a FlowGap_socc2026_patch_pack/docs/submission_checklist_socc2026.md docs/submission_checklist_socc2026.md
cp -a FlowGap_socc2026_patch_pack/docs/ai_usage_disclosure.md docs/ai_usage_disclosure.md
```

---

## 三、建议删除或归档的旧文件

如果你已经从 CoNEXT 切换到 SoCC，建议删除：

```text
docs/venue/conext2026_acm_prep.md
docs/prompts/07_codex_conext_paper_scaffold.md
```

删除命令：

```bash
cd ~/FlowGap-work/FlowGap-paper
rm -f docs/venue/conext2026_acm_prep.md
rm -f docs/prompts/07_codex_conext_paper_scaffold.md
```

如果你想保留历史，也可以移动到 archived：

```bash
mkdir -p docs/archived
mv docs/venue/conext2026_acm_prep.md docs/archived/ 2>/dev/null || true
mv docs/prompts/07_codex_conext_paper_scaffold.md docs/archived/ 2>/dev/null || true
```

---

## 四、保持不变的文件

下面这些文件不需要因为会议切换而修改：

```text
docs/prompts/01_codex_reference_repo_analysis.md
docs/prompts/02_codex_environment_probe_plan.md
docs/prompts/03_codex_first_patch_plan.md
docs/prompts/04_codex_trace_parser_generation.md
docs/prompts/05_codex_gap_predictor_generation.md
docs/prompts/06_codex_scheduler_replay_generation.md
docs/skill_usage_policy.md
docs/setup/01_environment_setup_aarch64_910A.md
docs/setup/02_create_workspace_and_reference_repo.md
docs/setup/03_install_scientific_agent_skills_for_codex.md
scripts/bootstrap_flowgap_dirs.sh
```

---

## 五、一条命令式迁移流程

假设你把 `FlowGap_socc2026_patch_pack.zip` 放到了：

```text
~/FlowGap-work/FlowGap-paper/
```

执行：

```bash
cd ~/FlowGap-work/FlowGap-paper

unzip FlowGap_socc2026_patch_pack.zip

cp -a FlowGap_socc2026_patch_pack/AGENTS.md AGENTS.md
cp -a FlowGap_socc2026_patch_pack/docs/MEGA_PROMPT.md docs/MEGA_PROMPT.md
cp -a FlowGap_socc2026_patch_pack/docs/claims.md docs/claims.md
cp -a FlowGap_socc2026_patch_pack/docs/prompts/00_codex_bootstrap_analyze_only.md docs/prompts/00_codex_bootstrap_analyze_only.md
cp -a FlowGap_socc2026_patch_pack/docs/venue/socc2026_acm_prep.md docs/venue/socc2026_acm_prep.md
cp -a FlowGap_socc2026_patch_pack/docs/prompts/07_codex_socc_paper_scaffold.md docs/prompts/07_codex_socc_paper_scaffold.md
cp -a FlowGap_socc2026_patch_pack/docs/submission_checklist_socc2026.md docs/submission_checklist_socc2026.md
cp -a FlowGap_socc2026_patch_pack/docs/ai_usage_disclosure.md docs/ai_usage_disclosure.md
cp -a FlowGap_socc2026_patch_pack/scripts/check_flowgap_pack_manifest.sh scripts/check_flowgap_pack_manifest.sh
chmod +x scripts/check_flowgap_pack_manifest.sh

rm -f docs/venue/conext2026_acm_prep.md
rm -f docs/prompts/07_codex_conext_paper_scaffold.md

bash scripts/check_flowgap_pack_manifest.sh
grep -R "CoNEXT\|conext\|CONEXT" -n AGENTS.md docs scripts || true

git add AGENTS.md docs scripts
git commit -m "Switch target venue to SoCC 2026"
```

---

## 六、迁移完成后 Codex 的第一条提示

```text
请读取并执行 docs/prompts/00_codex_bootstrap_analyze_only.md。
严格遵守 AGENTS.md、docs/MEGA_PROMPT.md、docs/claims.md、docs/skill_usage_policy.md、docs/venue/socc2026_acm_prep.md。
目标会议为 SoCC 2026 Full Research Paper。
本轮只分析，不要修改 external/reference_repo/，不要生成代码，不要运行 root 命令，不要安装依赖。
```

论文骨架生成时使用：

```text
docs/prompts/07_codex_socc_paper_scaffold.md
```
