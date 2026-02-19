"""HTML report generator for Allelio variant analysis results."""

from datetime import datetime
from typing import Any, Dict, List, Optional
import html as html_escape

from allelio.analysis.lookup import _get_review_stars


def _get_gene(variant) -> str:
    """Extract gene name from a VariantResult's sub-entries."""
    if variant.clinvar_entries:
        return getattr(variant.clinvar_entries[0], 'gene', None) or "Unknown"
    elif variant.gwas_entries:
        return getattr(variant.gwas_entries[0], 'mapped_gene', None) or "Unknown"
    return "Unknown"


def _get_conditions(variant) -> str:
    """Extract condition/trait text from a VariantResult."""
    parts = []
    if variant.clinvar_entries:
        cond = getattr(variant.clinvar_entries[0], 'conditions', None)
        if cond and cond != "-":
            parts.append(cond)
    for gw in (variant.gwas_entries or []):
        trait = getattr(gw, 'trait', None)
        if trait and trait != "-" and trait not in parts:
            parts.append(trait)
    return "; ".join(parts[:3]) if parts else "No condition data"


def _get_clinical_significance(variant) -> str:
    """Extract clinical significance string."""
    if variant.clinvar_entries:
        return getattr(variant.clinvar_entries[0], 'clinical_significance', None) or "Unknown"
    return "GWAS association"


def _get_review_stars_html(variant) -> str:
    """Generate star rating HTML for a variant's ClinVar review status.

    Returns an HTML span with filled/empty stars and a color indicator.
    """
    if not variant.clinvar_entries:
        return ""
    entry = variant.clinvar_entries[0]
    stars = getattr(entry, 'review_stars', 0)
    filled = "\u2605" * stars        # ★
    empty = "\u2606" * (4 - stars)   # ☆
    if stars >= 3:
        color = "#16a34a"  # green
    elif stars >= 1:
        color = "#d97706"  # amber
    else:
        color = "#9ca3af"  # gray
    return f'<span style="color: {color}; letter-spacing: 2px;">{filled}{empty}</span>'


def _format_explanation_html(text: str) -> str:
    """Convert AI explanation text to safe HTML with paragraph breaks."""
    if not text:
        return ""
    safe = html_escape.escape(text)
    # Convert markdown-style bold
    import re
    safe = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', safe)
    # Convert line breaks to paragraphs
    paragraphs = [p.strip() for p in safe.split('\n\n') if p.strip()]
    if paragraphs:
        return ''.join(f'<p>{p}</p>' for p in paragraphs)
    return f'<p>{safe}</p>'


def generate_html_report(
    results: List[Any],
    explanations: Dict[str, str],
    summary: str,
    metadata: Dict[str, Any],
) -> str:
    """Generate a professional HTML report for variant analysis results.

    Args:
        results: List of VariantResult objects with analysis data
        explanations: Dict mapping rsid -> AI explanation text
        summary: Executive summary string
        metadata: Dict with keys: generated_at, db_version, model_used,
                  file_analyzed, total_variants, significant_variants

    Returns:
        Complete HTML report as a string
    """

    # Prepare data
    generated_at = metadata.get("generated_at", datetime.now().isoformat())
    db_version = metadata.get("db_version", "Unknown")
    model_used = metadata.get("model_used", "None")
    file_analyzed = metadata.get("file_analyzed", "Unknown")
    total_variants = metadata.get("total_variants", 0)
    significant_variants = metadata.get("significant_variants", 0)

    # Categorize results using actual VariantCategory values
    health_conditions = [r for r in results if r.category == "Health Conditions"]
    risk_factors = [r for r in results if r.category == "Risk Factors"]
    pharma = [r for r in results if r.category == "Pharmacogenomics"]
    traits = [r for r in results if r.category == "Traits"]
    carrier = [r for r in results if r.category == "Carrier Status"]
    other = [r for r in results if r.category in ("Unknown",)]

    def generate_variant_card(variant, explanation=None):
        """Generate HTML for a single variant card."""
        category_colors = {
            "Health Conditions": "#dc2626",
            "Risk Factors": "#ea580c",
            "Pharmacogenomics": "#7c3aed",
            "Traits": "#2563eb",
            "Carrier Status": "#16a34a",
            "Unknown": "#6b7280",
        }
        color = category_colors.get(variant.category, "#6b7280")

        gene = _get_gene(variant)
        conditions = _get_conditions(variant)
        clin_sig = _get_clinical_significance(variant)
        review_stars_html = _get_review_stars_html(variant)
        genotype = variant.genotype or "-"

        clinvar_url = f"https://www.ncbi.nlm.nih.gov/clinvar/?term={variant.rsid}"
        pubmed_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={gene}+{variant.rsid}" if gene != "Unknown" else "#"

        # Rank label
        rank = variant.significance_rank
        if rank <= 2:
            rank_label = "High"
            rank_color = "#dc2626"
        elif rank <= 4:
            rank_label = "Moderate"
            rank_color = "#ea580c"
        elif rank <= 6:
            rank_label = "Low"
            rank_color = "#eab308"
        else:
            rank_label = "Minimal"
            rank_color = "#6b7280"

        card_html = f'''
        <div class="variant-card" style="border-left: 5px solid {color};">
            <div class="variant-header">
                <h3>{variant.rsid}</h3>
                <span class="badge" style="background-color: {color};">{variant.category}</span>
                <span class="significance" style="background-color: {rank_color}20; color: {rank_color};">{rank_label}</span>
            </div>

            <div class="variant-info">
                <div class="info-row">
                    <span class="label">Gene:</span>
                    <span class="value">{html_escape.escape(gene)}</span>
                </div>
                <div class="info-row">
                    <span class="label">Clinical Significance:</span>
                    <span class="value">{html_escape.escape(clin_sig)}</span>
                </div>
'''
        if review_stars_html:
            card_html += f'''
                <div class="info-row">
                    <span class="label">Review Quality:</span>
                    <span class="value">{review_stars_html}</span>
                </div>
'''
        card_html += f'''
                <div class="info-row">
                    <span class="label">Condition / Trait:</span>
                    <span class="value">{html_escape.escape(conditions)}</span>
                </div>
                <div class="info-row">
                    <span class="label">Genotype:</span>
                    <span class="value" style="font-family: monospace; font-weight: bold;">{html_escape.escape(genotype)}</span>
                </div>
                <div class="info-row">
                    <span class="label">Chromosome:</span>
                    <span class="value">{variant.chromosome or "N/A"}</span>
                </div>
            </div>
'''
        if explanation:
            card_html += f'''
            <div class="explanation">
                <h4>AI Analysis</h4>
                {_format_explanation_html(explanation)}
            </div>
'''

        card_html += f'''
            <div class="variant-links">
                <a href="{clinvar_url}" target="_blank" class="link-btn">ClinVar</a>
                <a href="{pubmed_url}" target="_blank" class="link-btn">PubMed</a>
            </div>
        </div>
'''
        return card_html

    # Build category sections
    categories_html = ""

    sections = [
        (health_conditions, "Health Conditions", "#dc2626", "health-conditions", "Variants classified as pathogenic or likely pathogenic by ClinVar."),
        (risk_factors, "Risk Factors", "#ea580c", "risk-factors", "Variants associated with increased risk for certain conditions."),
        (pharma, "Pharmacogenomics", "#7c3aed", "pharmacogenomics", "Variants that may affect drug metabolism or response."),
        (traits, "Trait Associations", "#2563eb", "traits", "Variants associated with traits identified in genome-wide studies."),
        (carrier, "Carrier Status", "#16a34a", "carrier-status", "Benign or carrier-status variants."),
    ]

    # Build tab navigation — only for sections that have results
    active_sections = [(vl, t, c, sid, d) for vl, t, c, sid, d in sections if vl]
    tab_nav_html = ""
    if len(active_sections) > 1:
        tab_nav_html = '<nav class="tab-nav" id="tab-nav">\n'
        for _, title, color, section_id, _ in active_sections:
            count = len([vl for vl, t, c, sid, d in active_sections if sid == section_id][0])
            tab_nav_html += f'  <a href="#{section_id}" class="tab-link" style="--tab-color: {color};">{title} <span class="tab-count">{count}</span></a>\n'
        tab_nav_html += '</nav>\n'

    for variant_list, title, color, section_id, description in sections:
        if not variant_list:
            continue
        # Show up to 100 per category
        display_list = sorted(variant_list, key=lambda x: x.significance_rank)[:100]
        categories_html += f'<section class="category-section" id="{section_id}">\n'
        categories_html += f'<h2 class="category-title" style="color: {color}; border-color: {color};">{title} ({len(variant_list)})</h2>\n'
        categories_html += f'<p class="category-desc">{description}</p>\n'
        categories_html += '<div class="variants-grid">\n'
        for variant in display_list:
            explanation = explanations.get(variant.rsid)
            categories_html += generate_variant_card(variant, explanation)
        categories_html += '</div>\n</section>\n'

    # If no categories matched, show all results
    if not categories_html and results:
        tab_nav_html = ""
        categories_html = '<section class="category-section">\n'
        categories_html += '<h2 class="category-title">All Findings</h2>\n'
        categories_html += '<div class="variants-grid">\n'
        for variant in sorted(results, key=lambda x: x.significance_rank)[:100]:
            explanation = explanations.get(variant.rsid)
            categories_html += generate_variant_card(variant, explanation)
        categories_html += '</div>\n</section>\n'

    # AI explanation count
    ai_note = ""
    if explanations:
        ai_note = f'<div class="ai-note"><strong>AI Explanations:</strong> {len(explanations)} variants analyzed with {model_used}</div>'

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Allelio Variant Analysis Report</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            background-color: #f9fafb;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}

        header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 20px;
            border-radius: 8px;
            margin-bottom: 40px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}

        .header-content {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        .logo {{
            font-size: 32px;
            font-weight: bold;
            margin-bottom: 10px;
        }}

        .generated-date {{
            opacity: 0.9;
            font-size: 14px;
        }}

        .disclaimer {{
            background-color: #fef3c7;
            border-left: 5px solid #f59e0b;
            border-radius: 4px;
            padding: 20px;
            margin-bottom: 30px;
            color: #92400e;
        }}

        .disclaimer h3 {{
            margin-bottom: 10px;
            font-size: 16px;
        }}

        .disclaimer p {{
            font-size: 14px;
            line-height: 1.5;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}

        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            text-align: center;
        }}

        .stat-value {{
            font-size: 32px;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}

        .stat-label {{
            font-size: 14px;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .summary-section {{
            background: white;
            padding: 30px;
            border-radius: 8px;
            margin-bottom: 40px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }}

        .summary-section h2 {{
            margin-bottom: 15px;
            font-size: 22px;
            color: #1f2937;
        }}

        .summary-section p {{
            color: #4b5563;
            line-height: 1.8;
        }}

        .ai-note {{
            background: #ede9fe;
            border-left: 4px solid #7c3aed;
            padding: 12px 20px;
            border-radius: 4px;
            margin-bottom: 30px;
            font-size: 14px;
            color: #5b21b6;
        }}

        .category-section {{
            margin-bottom: 50px;
        }}

        .category-title {{
            font-size: 24px;
            margin-bottom: 8px;
            padding-bottom: 10px;
            border-bottom: 3px solid;
        }}

        .category-desc {{
            color: #6b7280;
            font-size: 14px;
            margin-bottom: 20px;
        }}

        .variants-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
            gap: 20px;
        }}

        .variant-card {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }}

        .variant-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        }}

        .variant-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}

        .variant-header h3 {{
            flex: 1;
            margin: 0;
            font-size: 18px;
            font-family: monospace;
            color: #1f2937;
        }}

        .badge {{
            padding: 4px 12px;
            border-radius: 20px;
            color: white;
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            white-space: nowrap;
        }}

        .significance {{
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
        }}

        .variant-info {{
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #e5e7eb;
        }}

        .info-row {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 8px;
            font-size: 14px;
        }}

        .label {{
            font-weight: 600;
            color: #6b7280;
            min-width: 140px;
        }}

        .value {{
            color: #1f2937;
            text-align: right;
            flex: 1;
            margin-left: 10px;
            word-break: break-word;
        }}

        .explanation {{
            background-color: #f0f4ff;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 15px;
            border: 1px solid #dbeafe;
        }}

        .explanation h4 {{
            font-size: 13px;
            color: #667eea;
            text-transform: uppercase;
            margin-bottom: 8px;
            font-weight: 600;
        }}

        .explanation p {{
            font-size: 13px;
            line-height: 1.7;
            color: #374151;
            margin-bottom: 8px;
        }}

        .explanation p:last-child {{
            margin-bottom: 0;
        }}

        .variant-links {{
            display: flex;
            gap: 10px;
        }}

        .link-btn {{
            flex: 1;
            padding: 8px 12px;
            border: 1px solid #d1d5db;
            border-radius: 4px;
            text-align: center;
            text-decoration: none;
            color: #667eea;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s;
        }}

        .link-btn:hover {{
            background-color: #667eea;
            color: white;
            border-color: #667eea;
        }}

        footer {{
            background-color: #1f2937;
            color: #d1d5db;
            padding: 30px 20px;
            margin-top: 60px;
            border-radius: 8px;
        }}

        .footer-content {{
            max-width: 1200px;
            margin: 0 auto;
            font-size: 13px;
            line-height: 1.8;
        }}

        .footer-section {{
            margin-bottom: 20px;
        }}

        .footer-section strong {{
            color: #f3f4f6;
        }}

        .footer-meta {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #374151;
            color: #9ca3af;
        }}

        .tab-nav {{
            position: sticky;
            top: 0;
            z-index: 100;
            background: white;
            display: flex;
            gap: 4px;
            padding: 12px 0;
            margin-bottom: 30px;
            border-bottom: 2px solid #e5e7eb;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
        }}

        .tab-link {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            border-radius: 6px;
            text-decoration: none;
            font-size: 14px;
            font-weight: 600;
            color: #4b5563;
            background: #f3f4f6;
            white-space: nowrap;
            transition: all 0.2s;
            border: 2px solid transparent;
        }}

        .tab-link:hover {{
            color: var(--tab-color);
            background: color-mix(in srgb, var(--tab-color) 10%, white);
            border-color: var(--tab-color);
        }}

        .tab-count {{
            font-size: 11px;
            font-weight: 700;
            background: #e5e7eb;
            color: #6b7280;
            padding: 1px 7px;
            border-radius: 10px;
        }}

        .tab-link:hover .tab-count {{
            background: color-mix(in srgb, var(--tab-color) 20%, white);
            color: var(--tab-color);
        }}

        @media print {{
            body {{ background-color: white; }}
            .container {{ max-width: 100%; }}
            header {{ break-after: avoid; }}
            .tab-nav {{ display: none; }}
            .category-section {{ break-inside: avoid; }}
            .variant-card {{ break-inside: avoid; page-break-inside: avoid; }}
            a {{ text-decoration: underline; }}
        }}
    </style>
</head>
<body>
    <header>
        <div class="header-content">
            <div class="logo">Allelio</div>
            <p>Genomic Variant Analysis Report</p>
            <div class="generated-date">Generated: {generated_at}</div>
        </div>
    </header>

    <div class="container">
        <div class="disclaimer">
            <h3>Medical Disclaimer</h3>
            <p>This report is for informational and educational purposes only. It is not intended as medical advice. Genetic findings should be discussed with a qualified healthcare provider or genetic counselor. Always consult with medical professionals before making health-related decisions based on genetic analysis.</p>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{total_variants:,}</div>
                <div class="stat-label">Total Variants Analyzed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{significant_variants:,}</div>
                <div class="stat-label">Significant Findings</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len(explanations)}</div>
                <div class="stat-label">AI Explanations</div>
            </div>
        </div>

        <div class="summary-section">
            <h2>Executive Summary</h2>
            <p>{html_escape.escape(summary)}</p>
        </div>

        {ai_note}

        {tab_nav_html}

        {categories_html}

    </div>

    <footer>
        <div class="footer-content">
            <div class="footer-section">
                <strong>Analysis Details</strong><br>
                File: {html_escape.escape(file_analyzed)}<br>
                AI Model: {html_escape.escape(model_used)}<br>
                Generated: {generated_at}
            </div>

            <div class="footer-section">
                <strong>Data Sources</strong><br>
                ClinVar: https://www.ncbi.nlm.nih.gov/clinvar<br>
                GWAS Catalog: https://www.ebi.ac.uk/gwas<br>
                dbSNP: https://www.ncbi.nlm.nih.gov/snp
            </div>

            <div class="footer-section">
                <strong>Important Notice</strong><br>
                This analysis is provided as-is. Results should be validated by qualified healthcare professionals. Allelio makes no guarantees about the accuracy or completeness of findings.
            </div>

            <div class="footer-meta">
                <div>Allelio Genomic Analysis Platform</div>
                <div>MIT License &mdash; Open Source</div>
            </div>
        </div>
    </footer>
</body>
</html>
'''

    return html
