# Allelio v0.2.0 — Smarter Ranking & Redesigned Reports

**Evidence-quality weighting, reorganized sections, and tab navigation**

This release brings two major improvements: ClinVar review star ratings now influence variant ranking so expert-reviewed findings rise to the top, and HTML reports have been reorganized with a new tab navigation bar for faster browsing.

---

## What's new

### Review quality now affects variant ranking

Previously, Allelio treated all ClinVar entries equally regardless of how thoroughly they'd been reviewed. A variant classified as "pathogenic" by a single submitter got the same weight as one confirmed by an expert panel.

Now, Allelio maps each variant's ClinVar review status to a 0–4 star rating:

| Stars | Meaning |
|-------|---------|
| ★★★★ | Practice guideline |
| ★★★☆ | Reviewed by expert panel |
| ★★☆☆ | Multiple submitters, no conflicts |
| ★☆☆☆ | Single submitter or conflicting interpretations |
| ☆☆☆☆ | No assertion criteria provided |

Higher-star variants sort above lower-star variants within the same significance tier (e.g., two "pathogenic" variants will be ordered by review quality). Star ratings never override clinical significance — a 4-star benign variant will never outrank a 0-star pathogenic one.

### Star ratings in your report

HTML reports now display a visual star rating on each variant card, color-coded for quick scanning: green for well-reviewed (3–4 stars), amber for moderate (1–2 stars), and gray for unreviewed. The Review Quality row only appears on ClinVar-backed variant cards — GWAS-only cards stay clean.

### Reorganized report sections

Report sections are now ordered by clinical actionability rather than alphabetically:

1. Health Conditions
2. Risk Factors
3. Pharmacogenomics
4. Traits
5. Carrier Status

This puts the most medically relevant findings at the top of your report.

### Tab navigation

A sticky navigation bar at the top of the report lets you jump between sections instantly. Only sections that contain results are shown — no empty tabs cluttering the view. Each tab displays a variant count badge so you can see at a glance where findings are concentrated. The tab bar is hidden when printing.

### Smarter AI explanations

The local AI model now receives review quality context alongside clinical data, producing explanations that account for how well-established a finding is.

---

## Upgrading

If you're upgrading from v0.1.0, no database re-download is needed — Allelio already stores the review status field. Just update the package:

```bash
pip install --upgrade allelio
```

---

## What's next

The v0.2 roadmap continues with gnomAD population frequency integration, gene-level variant grouping, zygosity-aware interpretation, and improved AI prompts with richer clinical context. See the [ROADMAP](ROADMAP.md) for details.

---

## Important disclaimer

Allelio is for educational and informational purposes only. It is not a medical device and does not provide medical advice. Always consult qualified healthcare professionals before making health decisions based on genetic information.
