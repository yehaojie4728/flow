# SoCC 2026 / ACM Template Preparation

Target venue:

```text
ACM Symposium on Cloud Computing 2026 (SoCC 2026)
```

Official site:

```text
https://acmsocc.org/2026/
```

Call for papers:

```text
https://acmsocc.org/2026/papers.html
```

Conference:

```text
November 18-20, 2026, Singapore
```

---

## 1. Submission category

Default target for FlowGap:

```text
Full Research Paper
```

SoCC 2026 categories:

```text
Full Research Papers: 12 pages + unlimited references
Short Research Papers: 6 pages + unlimited references
Industry Papers: 12 pages + unlimited references
Vision Papers: 6 pages + unlimited references
```

FlowGap should target:

```text
Full Research Paper, 12 pages + unlimited references
```

unless evaluation is not complete, in which case Short Research Paper may be considered.

---

## 2. Key dates

All deadlines use AoE timezone.

Second round is the relevant target:

```text
Abstract deadline: July 7, 2026 AoE
Submission deadline: July 14, 2026 AoE
Author response period: September 10-12, 2026
Author notification: September 26, 2026
Camera-ready deadline: October 17, 2026
Conference dates: November 18-20, 2026
```

Important:

```text
A paper rejected in the first round cannot be resubmitted in the second round.
```

---

## 3. Formatting rules

Use ACM Proceedings Format with ACM acmart.

Required LaTeX document class:

```latex
\documentclass[sigconf,review,anonymous]{acmart}
```

Submission requirements:

```text
9pt font size
8.5" x 11" paper
single PDF file
PDF size <= 10 MB
do not change margins
do not change inter-column spacing
do not change line spacing
paper must print clearly in black and white
```

Paper type must be indicated as a subtitle:

```text
Research Full
```

or the selected category.

---

## 4. Anonymity

Research full, research short, and vision papers are dual anonymous.

Rules:

```text
Do not reveal author names.
Do not reveal institutions.
Do not include acknowledgments in the anonymous submission.
Do not identify the authors explicitly or by implication.
Cite prior work, including own prior work, in third person.
If the project has appeared on arXiv, technical reports, talks, GitHub, or social media, use an anonymized system/project name different from the public name.
```

For FlowGap:

```text
Internal name: FlowGap
Anonymous submission name: choose one of AnonProbe / GapProbe / SafeProbe
```

Do not use the same public repository/project name if it is already publicly associated with the authors.

---

## 5. AI usage and authorship

SoCC 2026 follows ACM authorship policy.

Rules:

```text
Generative AI tools cannot be listed as authors.
Use of generative AI tools is permitted but must be disclosed in the Work.
Authors must take full responsibility for all content.
```

For FlowGap, maintain:

```text
docs/ai_usage_disclosure.md
```

Record:

```text
tools used
purpose
human review process
which outputs were accepted/rejected
confirmation that all citations, experiments, and claims were verified by authors
```

Do not include an identifying acknowledgment in the anonymous submission unless required by the submission system. Prepare disclosure text for camera-ready or HotCRP fields.

---

## 6. Reserve reviewer policy

SoCC 2026 requires at least one senior author per submitted paper to register as a reserve reviewer unless exempt.

A senior author is defined as someone who obtained a PhD five or more years ago.

Action items:

```text
Ask advisor/coauthors who is the senior author.
Check whether the paper is exempt.
Ensure the senior author has a TPMS account linked to the HotCRP email.
Prepare reserve reviewer information before submission.
```

Create:

```text
docs/submission_checklist_socc2026.md
```

---

## 7. Submission site

Submission site:

```text
https://socc26.hotcrp.com
```

---

## 8. FlowGap-specific positioning for SoCC

SoCC topic fit:

```text
Distributed and networked systems
Datacenter architectures
Networking and communication
Operating systems and system support
Resource management, allocation, scheduling, provisioning, and metering
Machine learning for clouds and cloud-based systems
Systems for machine learning training and/or serving
Tracing and monitoring systems
Fault tolerance, high availability, and reliability
```

Position FlowGap as:

```text
a cloud/AI-infrastructure monitoring and active probing system that reduces measurement-induced interference in accelerator servers.
```

Avoid positioning it as:

```text
a pure time-series prediction paper
a complete root-cause diagnosis system
a hardware-specific engineering note without broader cloud systems relevance
```

---

## 9. Provisional paper structure

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

## 10. Provisional main.tex skeleton

```latex
\documentclass[sigconf,review,anonymous]{acmart}

\setcopyright{none}
\settopmatter{printacmref=false}
\renewcommand\footnotetextcopyrightpermission[1]{}

\begin{document}

\title{FlowGap: Predictive Low-Interference Intra-Host Probing for Ascend Accelerator Traffic}
\subtitle{Research Full}

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

## 11. File size and PDF requirements

Before submission:

```text
compile to a single PDF
ensure PDF <= 10 MB
ensure PDF uses 8.5" x 11" paper
ensure it prints correctly
ensure figures are readable in grayscale
```

---

## 12. Desk-rejection risks

SoCC 2026 warns that violations can lead to rejection without review.

Avoid:

```text
over page limit
wrong template
wrong font size
modified margins
PDF over 10 MB
non-anonymized research submission
missing reserve reviewer information
submitting work under simultaneous review elsewhere
failing to cite and differentiate from relevant prior work
using an already-public system/project name that identifies authors
```
