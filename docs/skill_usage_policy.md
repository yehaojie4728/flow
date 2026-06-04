# FlowGap Skill Usage Policy

This project uses Scientific Agent Skills selectively.

---

## Allowed core skills

Use these freely when relevant:

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

---

## Restricted writing/review skills

The following skills are allowed only with overrides:

```text
scientific-writing
literature-review
peer-review
venue-templates
```

---

## scientific-writing override

Use scientific-writing in text-only mode.

Do not:

- generate graphical abstract;
- generate AI images;
- call generate-image;
- call scientific-schematics;
- invent results;
- invent citations;
- invent hardware details;
- invent implementation details;
- write unsupported numeric claims.

---

## literature-review override

Use literature-review only for search strategy, literature screening, literature matrix, synthesis from verified papers, and related work outline.

Do not generate figures, rank papers primarily by author prestige, invent references, or write final Related Work before BibTeX is verified.

---

## peer-review override

Use peer-review to be harsh.

Focus on novelty, relation to Hostping/HostDiag, whether FlowGap is more than generic time-series forecasting, missing baselines, missing detection utility, evidence-to-claim alignment, simulation vs real-measurement confusion, overclaiming, and CoNEXT systems-paper fit.

---

## venue-templates override

Use venue-templates only for formatting support.

The official target conference template is the source of truth.
