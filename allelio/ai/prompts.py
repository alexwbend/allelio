"""
Prompt templates and formatting utilities for the Allelio AI explanation engine.

This module provides templates for communicating with the language model,
along with formatting functions to convert raw variant data into
human-readable text suitable for inclusion in prompts.
"""

from typing import List, Optional


SYSTEM_PROMPT = """You are a genetics education assistant for Allelio, an open-source genomics tool. Your role is to explain genetic variant findings in clear, accessible language. You MUST: 1) Use plain English that a non-scientist can understand. 2) Explain what the variant means in practical terms. 3) Provide relevant lifestyle or dietary context from published research when applicable. 4) Always note limitations and uncertainties. 5) Never make definitive medical diagnoses. 6) Cite the source databases (ClinVar, GWAS Catalog) and relevant studies. 7) Recommend consulting a genetic counselor for clinically significant findings. Keep explanations concise (2-4 paragraphs). Be warm, informative, and reassuring without minimizing genuine risks."""


VARIANT_PROMPT_TEMPLATE = """Please explain the following genetic variant finding for the user:

**Variant:** {rsid}
**User's Genotype:** {genotype}
**Gene:** {gene}
**Chromosome:** {chromosome}, Position: {position}

**Population Frequency (gnomAD):**
{gnomad_summary}

**ClinVar Data:**
{clinvar_summary}

**GWAS Associations:**
{gwas_summary}

Please provide:
1. A plain-English explanation of what this variant means
2. What the user's specific genotype ({genotype}) implies
3. How the population frequency affects interpretation (e.g., common variants are less likely to cause rare diseases)
4. Any relevant lifestyle, dietary, or environmental context from research
5. Important caveats and limitations"""


def format_clinvar_summary(clinvar_entries: List[dict]) -> str:
    """
    Format ClinVar data into readable text for inclusion in prompts.
    
    Args:
        clinvar_entries: List of dictionaries with ClinVar information
        
    Returns:
        Formatted string summarizing ClinVar data
    """
    if not clinvar_entries:
        return "No ClinVar data available for this variant."
    
    formatted_lines = []
    
    for entry in clinvar_entries:
        significance = entry.get('clinical_significance', 'Unknown')
        condition = entry.get('condition', 'Unknown condition')
        review_status = entry.get('review_status', 'criteria provided, single submitter')
        review_stars = entry.get('review_stars', 0)
        stars_display = "\u2605" * review_stars + "\u2606" * (4 - review_stars)

        line = f"- {condition}: {significance} ({stars_display} {review_status})"
        formatted_lines.append(line)
    
    if formatted_lines:
        return "\n".join(formatted_lines)
    else:
        return "No ClinVar interpretations available."


def format_gwas_summary(gwas_entries: List[dict]) -> str:
    """
    Format GWAS data into readable text for inclusion in prompts.
    
    Args:
        gwas_entries: List of dictionaries with GWAS association information
        
    Returns:
        Formatted string summarizing GWAS associations
    """
    if not gwas_entries:
        return "No GWAS associations available for this variant."
    
    formatted_lines = []
    
    for entry in gwas_entries:
        trait = entry.get('trait', 'Unknown trait')
        p_value = entry.get('p_value', 'Unknown')
        odds_ratio = entry.get('odds_ratio', None)
        population = entry.get('population_ancestry', 'Mixed ancestry')
        
        if odds_ratio:
            line = f"- {trait}: p-value = {p_value}, Odds Ratio = {odds_ratio} ({population})"
        else:
            line = f"- {trait}: p-value = {p_value} ({population})"
        
        formatted_lines.append(line)
    
    if formatted_lines:
        return "\n".join(formatted_lines)
    else:
        return "No GWAS associations available."


def format_gnomad_summary(gnomad_entry) -> str:
    """
    Format gnomAD population frequency data for inclusion in prompts.

    Args:
        gnomad_entry: A GnomADEntry object or None

    Returns:
        Formatted string summarizing population frequency data
    """
    if gnomad_entry is None:
        return "No population frequency data available for this variant."

    af = getattr(gnomad_entry, 'allele_frequency', None)
    if af is None:
        return "No population frequency data available for this variant."

    af_percent = af * 100
    af_popmax = getattr(gnomad_entry, 'af_popmax', None)
    ac = getattr(gnomad_entry, 'ac', None)
    an = getattr(gnomad_entry, 'an', None)

    lines = []

    # Main frequency line
    if ac is not None and an is not None:
        lines.append(f"- Global Allele Frequency: {af_percent:.4f}% ({ac:,} / {an:,} alleles)")
    else:
        lines.append(f"- Global Allele Frequency: {af_percent:.4f}%")

    # Popmax
    if af_popmax is not None and af_popmax > af:
        lines.append(f"- Highest in any population: {af_popmax * 100:.4f}%")

    # Interpretation hint for the LLM
    if af > 0.05:
        lines.append("- Context: Common variant (>5% frequency) — typically benign or population-specific")
    elif af > 0.01:
        lines.append("- Context: Moderately common variant (1-5% frequency)")
    elif af > 0.001:
        lines.append("- Context: Uncommon variant (0.1-1% frequency)")
    elif af > 0.00001:
        lines.append("- Context: Rare variant (<0.1% frequency) — more likely to be clinically significant")
    else:
        lines.append("- Context: Very rare variant (<0.001% frequency) — warrants careful interpretation")

    return "\n".join(lines)


def build_variant_prompt(result) -> str:
    """
    Build a complete prompt for explaining a variant by formatting all relevant data.
    
    Args:
        result: A VariantResult object from allelio.analysis.lookup
        
    Returns:
        Complete prompt string ready to send to the language model
    """
    # Extract variant data
    rsid = result.rsid or "Unknown"
    genotype = result.genotype or "Unknown"
    chromosome = result.chromosome or "Unknown"
    position = result.position or "Unknown"

    # Extract gene from clinvar or gwas entries
    gene = "Unknown"
    if result.clinvar_entries:
        entry = result.clinvar_entries[0]
        gene = getattr(entry, 'gene', None) or "Unknown"
    elif result.gwas_entries:
        entry = result.gwas_entries[0]
        gene = getattr(entry, 'mapped_gene', None) or "Unknown"

    # Format clinical and research data — convert dataclass entries to dicts for formatters
    clinvar_dicts = []
    for e in (result.clinvar_entries or []):
        clinvar_dicts.append({
            'clinical_significance': getattr(e, 'clinical_significance', None),
            'condition': getattr(e, 'conditions', None),
            'review_status': getattr(e, 'review_status', None),
            'review_stars': getattr(e, 'review_stars', 0),
        })
    gwas_dicts = []
    for e in (result.gwas_entries or []):
        gwas_dicts.append({
            'trait': getattr(e, 'trait', None),
            'p_value': getattr(e, 'p_value', None),
            'odds_ratio': getattr(e, 'odds_ratio', None),
        })
    clinvar_summary = format_clinvar_summary(clinvar_dicts)
    gwas_summary = format_gwas_summary(gwas_dicts)

    # Format gnomAD frequency data
    gnomad_entry = getattr(result, 'gnomad_entry', None)
    gnomad_summary = format_gnomad_summary(gnomad_entry)

    # Build the prompt using the template
    prompt = VARIANT_PROMPT_TEMPLATE.format(
        rsid=rsid,
        genotype=genotype,
        gene=gene,
        chromosome=chromosome,
        position=position,
        gnomad_summary=gnomad_summary,
        clinvar_summary=clinvar_summary,
        gwas_summary=gwas_summary,
    )

    return prompt
