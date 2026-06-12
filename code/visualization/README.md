# FlowGap 可视化脚本

## 最新图表位置

**⚠️ 重要：最新生成的图表在以下目录**

```
/root/FlowGap-work/FlowGap-paper/code/results/figures/
```

包含：
- `fig1_policy_comparison.pdf` / `.png` - 策略对比（安全率、BW探针数、开销）
- `fig2_calibration.pdf` / `.png` - 模型校准曲线
- `fig3_overhead_breakdown.pdf` / `.png` - 探针开销分解

## 生成脚本

```bash
cd /root/FlowGap-work/FlowGap-paper/code/visualization
python generate_p0_figures.py
```

## 图表特性

- ✅ ACM sigconf 格式（双栏 7"，单栏 3.33"）
- ✅ 300 DPI 高分辨率
- ✅ Okabe-Ito 色盲友好配色
- ✅ Hatch patterns（填充图案）用于黑白打印
- ✅ PDF（矢量）+ PNG（位图）双格式

## 旧文件

`visualization/output/` 目录下的文件是旧版本，已过期。
