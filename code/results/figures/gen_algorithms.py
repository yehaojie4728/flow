"""
Generate algorithm pseudocode figures in three-line-box style for academic papers.
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.font_manager import FontProperties
import numpy as np

MONO = FontProperties(family='DejaVu Sans Mono', size=9)
MONO_BOLD = FontProperties(family='DejaVu Sans Mono', size=9, weight='bold')
MONO_ITALIC = FontProperties(family='DejaVu Sans Mono', size=9, style='italic')
TITLE_FONT = FontProperties(family='DejaVu Sans', size=10, weight='bold')

def render_algorithm(lines, title, outpath, figwidth=7.2):
    """
    lines: list of (indent_level, text, style)
      style: 'normal' | 'bold' | 'italic' | 'keyword_line'
    A 'keyword_line' has mixed segments: list of (text, style) tuples passed as text.
    """
    n = len(lines)
    line_h = 0.32   # inches per line
    pad_top = 0.55  # title area
    pad_bot = 0.25
    fig_h = pad_top + n * line_h + pad_bot

    fig, ax = plt.subplots(figsize=(figwidth, fig_h))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis('off')

    # Normalize coordinates
    content_h = 1.0
    top_y = 1.0
    bot_y = 0.0

    lw_thick = 2.0
    lw_thin  = 0.8

    # Top thick line
    ax.axhline(top_y, color='black', linewidth=lw_thick, xmin=0.0, xmax=1.0)
    # Title separator (thin)
    title_sep_y = 1.0 - pad_top / fig_h
    ax.axhline(title_sep_y, color='black', linewidth=lw_thin, xmin=0.0, xmax=1.0)
    # Bottom thick line
    ax.axhline(bot_y, color='black', linewidth=lw_thick, xmin=0.0, xmax=1.0)

    # Title
    ax.text(0.5, (1.0 + title_sep_y) / 2, title,
            ha='center', va='center', fontproperties=TITLE_FONT,
            transform=ax.transAxes)

    # Content lines
    x_base = 0.025
    indent_unit = 0.03
    content_area = title_sep_y - bot_y  # fraction of figure
    line_frac = line_h / fig_h

    for i, line_def in enumerate(lines):
        # y position: from top of content area downward
        y = title_sep_y - (i + 0.55) * line_frac

        if isinstance(line_def, dict):
            indent = line_def.get('indent', 0)
            segments = line_def.get('segments', [])  # list of (text, style)
            x = x_base + indent * indent_unit
            for seg_text, seg_style in segments:
                if seg_style == 'bold':
                    fp = MONO_BOLD
                elif seg_style == 'italic':
                    fp = MONO_ITALIC
                else:
                    fp = MONO
                t = ax.text(x, y, seg_text, ha='left', va='center',
                            fontproperties=fp, transform=ax.transAxes)
                # Approximate width: each char ~ 0.0068 in axes units at this figwidth
                x += len(seg_text) * 0.0068
        else:
            indent, text, style = line_def
            x = x_base + indent * indent_unit
            if style == 'bold':
                fp = MONO_BOLD
            elif style == 'italic':
                fp = MONO_ITALIC
            else:
                fp = MONO
            ax.text(x, y, text, ha='left', va='center',
                    fontproperties=fp, transform=ax.transAxes)

    plt.tight_layout(pad=0)
    fig.savefig(outpath, dpi=200, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close(fig)
    print(f"Saved: {outpath}")


# ─────────────────────────────────────────────────────────────────────────────
# Algorithm 1: Online Predictive Probe Scheduling
# ─────────────────────────────────────────────────────────────────────────────
alg1_lines = [
    (0, 'Input:  Network topology G=(V,E), probe budget B, history window W', 'bold'),
    (0, 'Output: Scheduled probe sequence P, predicted flow gaps ĝ',           'bold'),
    (0, '',                                                                     'normal'),
    {'indent':0, 'segments':[('1:  ','normal'),('procedure ','bold'),('OnlineProbeScheduling','normal'),('(G, B, W)','normal')]},
    (1, '2:  Initialize flow record cache C ← ∅',              'normal'),
    (1, '3:  Load pre-trained GBDT models M = {M₁, ..., M₈}',  'normal'),
    (0, '',                                                      'normal'),
    {'indent':1,'segments':[('4:  ','normal'),('while ','bold'),('system running  ','normal'),('do','bold')]},
    (2, '5:  F ← CollectActiveFlows(G)',                       'normal'),
    (2, '6:  Update cache C with new flow records in F',        'normal'),
    (2, '7:  φ ← ExtractFeatures(C, W)',                       'normal'),
    (0, '',                                                     'normal'),
    {'indent':2,'segments':[('8:  ','normal'),('for ','bold'),('each flow f ∈ F  ','normal'),('do','bold')]},
    (3, '9:  ĝ_f ← {Mₕ.predict(φ_f) | h ∈ {1,...,8}}',       'normal'),
    {'indent':2,'segments':[('10: ','normal'),('end for','bold')]},
    (0, '',                                                     'normal'),
    (2, '11: Rank flows by urgency score s(f) = max(ĝ_f)',      'normal'),
    (2, '12: P ← SelectTopK(ranked flows, budget B)',           'normal'),
    (2, '13: DispatchProbes(P)',                                 'normal'),
    (2, '14: Wait for next scheduling epoch',                    'normal'),
    {'indent':1,'segments':[('15: ','normal'),('end while','bold')]},
    {'indent':0,'segments':[('16: ','normal'),('end procedure','bold')]},
]

# ─────────────────────────────────────────────────────────────────────────────
# Algorithm 2: Feature Extraction (30-dim)
# ─────────────────────────────────────────────────────────────────────────────
alg2_lines = [
    (0, 'Input:  Flow record cache C, history window W',               'bold'),
    (0, 'Output: Feature vector φ ∈ ℝ³⁰ per flow',                    'bold'),
    (0, '',                                                             'normal'),
    {'indent':0,'segments':[('1:  ','normal'),('function ','bold'),('ExtractFeatures','normal'),('(C, W)','normal')]},
    (1, '2:  // Group 1: Basic flow statistics (5 dims)',              'italic'),
    (1, '3:  φ[1:5]  ← {pkt_count, byte_count, duration, pkt_rate, byte_rate}','normal'),
    (0, '',                                                             'normal'),
    (1, '4:  // Group 2: Inter-arrival time features (5 dims)',        'italic'),
    (1, '5:  φ[6:10] ← {IAT_mean, IAT_std, IAT_min, IAT_max, IAT_cv}','normal'),
    (0, '',                                                             'normal'),
    (1, '6:  // Group 3: Packet length features (5 dims)',             'italic'),
    (1, '7:  φ[11:15] ← {len_mean, len_std, len_min, len_max, len_cv}','normal'),
    (0, '',                                                             'normal'),
    (1, '8:  // Group 4: Historical gap features (10 dims)',           'italic'),
    {'indent':1,'segments':[('9:  ','normal'),('for ','bold'),('h = 1 to 8  ','normal'),('do','bold')]},
    (2, '10: φ[15+h] ← HistoricalGap(C, h)',                          'normal'),
    {'indent':1,'segments':[('11: ','normal'),('end for','bold')]},
    (1, '12: φ[24:25] ← {gap_mean_W, gap_std_W}',                     'normal'),
    (0, '',                                                             'normal'),
    (1, '13: // Group 5: Flow lifecycle features (3 dims)',            'italic'),
    (1, '14: φ[26:28] ← {flow_age, last_seen_delta, flow_phase}',     'normal'),
    (0, '',                                                             'normal'),
    (1, '15: // Group 6: Network context features (2 dims)',           'italic'),
    (1, '16: φ[29:30] ← {link_utilization, concurrent_flows}',        'normal'),
    (0, '',                                                             'normal'),
    (1, '17: return φ',                                                'normal'),
    {'indent':0,'segments':[('18: ','normal'),('end function','bold')]},
]

# ─────────────────────────────────────────────────────────────────────────────
# Algorithm 3: GBDT Offline Training
# ─────────────────────────────────────────────────────────────────────────────
alg3_lines = [
    (0, 'Input:  Historical trace dataset D, horizons H={1,...,8}',         'bold'),
    (0, '        Feature extractor ExtractFeatures, GBDT hyper-params θ',   'bold'),
    (0, 'Output: Trained model set M = {M₁, ..., M₈}',                     'bold'),
    (0, '',                                                                   'normal'),
    {'indent':0,'segments':[('1:  ','normal'),('procedure ','bold'),('TrainGBDT','normal'),('(D, H, θ)','normal')]},
    (1, '2:  // Build labeled dataset from trace',                          'italic'),
    {'indent':1,'segments':[('3:  ','normal'),('for ','bold'),('each flow record r ∈ D  ','normal'),('do','bold')]},
    (2, '4:  φ_r ← ExtractFeatures(r, W)',                                  'normal'),
    {'indent':1,'segments':[('5:  ','normal'),('end for','bold')]},
    (0, '',                                                                   'normal'),
    (1, '6:  // Train one binary classifier per horizon',                   'italic'),
    {'indent':1,'segments':[('7:  ','normal'),('for ','bold'),('each horizon h ∈ H  ','normal'),('do','bold')]},
    (2, '8:  y_h ← {1 if gap(r,h)>τ else 0 | r ∈ D}',                     'normal'),
    (2, '9:  X  ← {φ_r | r ∈ D}',                                          'normal'),
    (2, '10: X_train, X_val ← SplitTemporalCV(X, y_h)',                    'normal'),
    (2, '11: Mₕ ← GBDTClassifier(θ).fit(X_train)',                         'normal'),
    (2, '12: Evaluate(Mₕ, X_val)',                                          'normal'),
    (2, '13: // Hyper-parameter: n_estimators=200, max_depth=5, lr=0.05',   'italic'),
    {'indent':1,'segments':[('14: ','normal'),('end for','bold')]},
    (0, '',                                                                   'normal'),
    (1, '15: return M = {M₁, ..., M₈}',                                    'normal'),
    {'indent':0,'segments':[('16: ','normal'),('end procedure','bold')]},
]

BASE = '/root/FlowGap-work/FlowGap-paper/code/results/figures'

render_algorithm(alg1_lines,
    'Algorithm 1: Online Predictive Probe Scheduling',
    f'{BASE}/algorithm1_online_scheduling.png')

render_algorithm(alg2_lines,
    'Algorithm 2: Flow Feature Extraction (30-dim)',
    f'{BASE}/algorithm2_feature_extraction.png')

render_algorithm(alg3_lines,
    'Algorithm 3: GBDT Offline Training',
    f'{BASE}/algorithm3_gbdt_training.png')
