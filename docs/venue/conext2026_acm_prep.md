# CoNEXT 2026 / ACM Template Preparation

Target venue:

```text
CoNEXT 2026
```

Official site:

```text
https://conferences.sigcomm.org/co-next/2026/#!/home
```

Current status:

```text
The CoNEXT 2026 official page exists, but this project must not assume final CFP details until the CFP/submission page is confirmed.
```

---

## 1. Provisional template basis

Use ACM Primary Article Template for LaTeX:

```text
acmart.cls
```

Provisional document class:

```latex
\documentclass[sigconf,review,anonymous]{acmart}
```

Important:

- `sigconf` is the provisional ACM proceedings format;
- `review` and `anonymous` are provisional until CoNEXT 2026 rules are confirmed;
- final accepted version may require different options;
- do not invent page limits.

---

## 2. Items requiring official confirmation

Mark these as:

```text
NEED_CONEXT2026_CFP_CONFIRMATION
```

until confirmed from official CoNEXT 2026 CFP:

1. submission deadline;
2. registration deadline;
3. paper page limit;
4. reference page treatment;
5. appendix policy;
6. artifact appendix policy;
7. anonymous / double-blind review policy;
8. conflict-of-interest policy;
9. ethics statement requirement;
10. artifact evaluation requirement;
11. camera-ready formatting requirements;
12. accepted-paper shepherding/rebuttal rules.

---

## 3. Provisional paper structure

Create:

```text
paper/
├── main.tex
├── references.bib
├── sections/
│   ├── 01_introduction.tex
│   ├── 02_background_motivation.tex
│   ├── 03_overview.tex
│   ├── 04_predictor_design.tex
│   ├── 05_prober_analyzer_design.tex
│   ├── 06_implementation.tex
│   ├── 07_evaluation.tex
│   ├── 08_related_work.tex
│   └── 09_conclusion.tex
└── figures/
```

---

## 4. Provisional main.tex skeleton

```latex
\documentclass[sigconf,review,anonymous]{acmart}

\setcopyright{none}
\settopmatter{printacmref=false}
\renewcommand\footnotetextcopyrightpermission[1]{}

\begin{document}

\title{FlowGap: Predictive Low-Interference Intra-Host Probing for Ascend Accelerator Traffic}

\begin{abstract}
TODO: Write after evaluation. Do not include unsupported numbers.
\end{abstract}

\maketitle

\input{sections/01_introduction}
\input{sections/02_background_motivation}
\input{sections/03_overview}
\input{sections/04_predictor_design}
\input{sections/05_prober_analyzer_design}
\input{sections/06_implementation}
\input{sections/07_evaluation}
\input{sections/08_related_work}
\input{sections/09_conclusion}

\bibliographystyle{ACM-Reference-Format}
\bibliography{references}

\end{document}
```

---

## 5. FlowGap-specific CoNEXT writing guidance

CoNEXT-style systems writing should emphasize:

1. problem clarity;
2. measurement-backed motivation;
3. simple and robust system design;
4. strong baselines;
5. credible implementation;
6. full evaluation;
7. honest limitations.

For FlowGap, the paper must repeatedly clarify:

```text
FlowGap is not a complete diagnosis system.
FlowGap is a probing opportunity inference layer.
```
