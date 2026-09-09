"""
Safety and disclaimer layer for AI-generated genetic explanations.

This module implements safety checks to ensure explanations don't contain
definitive medical language, and applies appropriate disclaimers based
on the significance of the findings.
"""

import re
from typing import List, NamedTuple, Tuple


# Mapping of high-impact variants and genes to warning messages
HIGH_IMPACT_VARIANTS = {
    'BRCA1': "Variants in BRCA1 are associated with significantly elevated cancer risk. It is strongly recommended to discuss these results with a genetic counselor.",
    'BRCA2': "Variants in BRCA2 are associated with significantly elevated cancer risk. It is strongly recommended to discuss these results with a genetic counselor.",
    'rs429358': "APOE variants are associated with Alzheimer's disease risk. These results can have significant psychological impact. Consider speaking with a genetic counselor before reviewing.",
    'rs7412': "APOE variants are associated with Alzheimer's disease risk. These results can have significant psychological impact. Consider speaking with a genetic counselor before reviewing.",
    'TP53': "TP53 variants are associated with elevated cancer risk across multiple cancer types. Genetic counseling is strongly recommended.",
    'MLH1': "MLH1 variants are associated with Lynch syndrome and hereditary cancer risk. Genetic counseling is strongly recommended.",
    'MSH2': "MSH2 variants are associated with Lynch syndrome and hereditary cancer risk. Genetic counseling is strongly recommended.",
    'MSH6': "MSH6 variants are associated with Lynch syndrome and hereditary cancer risk. Genetic counseling is strongly recommended.",
    'PMS2': "PMS2 variants are associated with Lynch syndrome and hereditary cancer risk. Genetic counseling is strongly recommended.",
}


# ---------------------------------------------------------------------------
# Lexical safety filter
#
# This is a pattern-based filter over the model's *answer*, not a classifier:
# it catches second-person medical language that states a diagnosis, a certain
# prognosis, or a medication instruction as fact. It is deliberately narrow.
# It does not judge whether an explanation is *correct*, and a determined
# paraphrase can evade it. Its measured catch rate on the labelled sentence set
# in tests/fixtures/safety_sentences.json is reported by
# scripts/safety_eval.py and quoted in the paper; that is the only claim made
# for it.
#
# Three families, each a list of compiled patterns. Every pattern is
# second-person ("you") or explicitly about *this* result, so third-person
# statements about the variant in general ("carriers have a higher risk") pass:
# they are the kind of hedged, population-level sentence the prompt asks for.
#
# Genotype nouns: "you have two copies of the risk allele" is a statement of
# fact about the data, not a diagnosis. The diagnostic patterns therefore
# exclude "you have" when a genotype noun follows within a few words.
# ---------------------------------------------------------------------------

_GENOTYPE_NOUNS = (
    r"variant|variants|genotype|genotypes|copy|copies|allele|alleles|snp|snps|"
    r"polymorphism|polymorphisms|version|versions|form|forms|mutation|mutations|"
    r"change|changes|marker|markers|result|results|data|finding|findings|"
    r"genetic|gene|genes|haplotype|haplotypes|substitution|base|bases|nucleotide|"
    # Risk language is what the prompt asks for, not a diagnosis.
    r"risk|risks|chance|chances|likelihood|predisposition|susceptibility|"
    r"tendency|odds|probability|association|associations"
)

# "you have <up to three words> <genotype noun>" is allowed.
_GENOTYPE_FOLLOWS = r"(?!\s+(?:[\w'-]+\s+){0,3}?(?:" + _GENOTYPE_NOUNS + r")\b)"

# Hedges that, if they sit between "you" and the verb, turn a certainty into a
# possibility. Patterns below match only when none of these intervene.
_HEDGE = (
    r"(?:may|might|could|can|likely|unlikely|probably|possibly|possible|"
    r"potentially|potential|perhaps|sometimes|often|usually|suggest|suggests|"
    r"suggested|uncertain|if|whether|"
    # Negations: "does not mean you have", "not certain to develop".
    r"not|no|never|without|doesn't|don't|isn't|aren't|rather\s+than)"
)

# 1. Diagnostic: asserts the user has a condition now.
DIAGNOSTIC_PATTERNS = [
    # "you have X" unless X is a genotype noun; "you've got X" the same.
    r"\byou(?:\s+have\s+got|'ve\s+got|\s+have|'ve)\b" + _GENOTYPE_FOLLOWS,
    r"\byou\s+(?:suffer|are\s+suffering)\s+from\b",
    r"\byou\s+(?:are|'re)\s+(?:a\s+)?(?:diagnosed|affected|diabetic|ill|sick)\b",
    r"\byou\s+(?:do\s+)?have\s+(?:the\s+|a\s+|an\s+)?(?:disease|disorder|condition|syndrome|cancer|illness)\b",
    r"\b(?:this|it|that|which)\s+(?:means|confirms|shows|proves|indicates|establishes)\s+(?:that\s+)?you\s+(?:have|are|suffer)\b" + _GENOTYPE_FOLLOWS,
    r"\byou\s+definitely\b",
    r"\byou\s+certainly\b",
    r"\byou\s+(?:are|'re)\s+(?:definitely|certainly|clearly|undoubtedly)\b",
    r"\b(?:this\s+is|here\s+is)\s+(?:your|a)\s+diagnosis\b",
    r"\bdiagnos(?:es|ing)\s+you\b",
    r"\byou\s+(?:are|'re)\s+(?:a\s+)?(?:carrier|patient)\s+(?:of|with)\s+(?:the\s+)?(?:disease|disorder|condition|syndrome)\b",
]

# 2. Prognostic: asserts what will happen, with no hedge in the way.
PROGNOSTIC_PATTERNS = [
    r"\byou(?:\s+will|'ll|\s+are\s+going\s+to|'re\s+going\s+to|\s+shall)\s+(?:(?:certainly|definitely|inevitably|surely|almost\s+certainly)\s+)?(?:develop|get|have|suffer|experience|contract|die|become|be\s+diagnosed|end\s+up|go\s+on\s+to)\b",
    r"\byou(?:\s+will|'ll)\s+(?:not\s+|never\s+)?(?:respond|tolerate|metabolize|metabolise)\b",
    r"\b(?:you\s+)?(?:are|'re)\s+(?:certain|guaranteed|destined|bound|sure)\s+to\b",
    r"\bguaranteed\s+to\b",
    r"\bcertain\s+to\s+(?:develop|get|have|suffer|cause|occur|happen)\b",
    r"\bwill\s+(?:certainly|definitely|inevitably|surely|undoubtedly)\b",
    r"\b(?:100|one\s+hundred)\s*(?:%|percent)\s+(?:chance|certain|certainty|likelihood|probability|sure)\b",
    r"\bno\s+(?:doubt|question)\s+(?:that\s+)?you\s+(?:will|have|are)\b",
    r"\byou\s+cannot\s+(?:avoid|escape|prevent)\b",
    r"\binevitabl[ey]\b",
]

# 3. Prescriptive: instructs the user to change a medication. Especially
# consequential once pharmacogenomic findings are in the report: a variant that
# affects drug metabolism is exactly where a model reaches for "stop taking".
_MED_NOUN = r"(?:medication|medications|medicine|medicines|drug|drugs|dose|doses|dosage|prescription|prescriptions|pill|pills|tablet|tablets|treatment|therapy|statin|statins|warfarin|clopidogrel|codeine|antidepressant|antidepressants|blood\s+thinner|blood\s+thinners)"
PRESCRIPTIVE_PATTERNS = [
    r"\b(?:stop|start|discontinue|quit|cease)\s+taking\b",
    r"\byou\s+(?:should|must|need\s+to|have\s+to|ought\s+to)\s+(?:stop|start|discontinue|quit|increase|decrease|reduce|lower|raise|double|halve|switch|change|adjust|skip|avoid|take)\s+(?:[\w'-]+\s+){0,5}?" + _MED_NOUN + r"\b",
    r"\b(?:increase|decrease|reduce|lower|raise|double|halve|adjust|change|skip)\s+your\s+(?:[\w'-]+\s+){0,2}?" + _MED_NOUN + r"\b",
    r"\b(?:do\s+not|don't|never)\s+take\s+(?:[\w'-]+\s+){0,3}?" + _MED_NOUN + r"\b",
    r"\byou\s+(?:should|must|need\s+to)\s+(?:not\s+)?(?:be\s+)?(?:prescribed|given|put\s+on|taken\s+off)\b",
    r"\byour\s+doctor\s+(?:must|has\s+to|needs\s+to)\s+(?:stop|change|switch|adjust|increase|decrease|reduce)\b",
]

SAFETY_CATEGORIES = {
    "diagnostic": DIAGNOSTIC_PATTERNS,
    "prognostic": PROGNOSTIC_PATTERNS,
    "prescriptive": PRESCRIPTIVE_PATTERNS,
}

_COMPILED = {
    category: [re.compile(p, re.IGNORECASE) for p in patterns]
    for category, patterns in SAFETY_CATEGORIES.items()
}


class SafetyMatch(NamedTuple):
    """One flagged span: which family caught it and the text it caught."""

    category: str
    text: str
    start: int
    end: int


def _hedged(text: str, match_start: int) -> bool:
    """True if a hedge word sits in the clause leading into the match.

    "You may have" / "you will probably develop" / "it is possible that you
    have" are the language the prompt asks for. The patterns themselves refuse
    hedges between "you" and the verb; this catches hedges just *before* the
    matched span, back to the previous clause boundary.
    """
    window_start = max(0, match_start - 60)
    prefix = text[window_start:match_start]
    # Only the current clause: cut at the last clause boundary.
    for boundary in (". ", "; ", ": ", "! ", "? "):
        idx = prefix.rfind(boundary)
        if idx != -1:
            prefix = prefix[idx + len(boundary):]
    return re.search(r"\b" + _HEDGE + r"\b", prefix, re.IGNORECASE) is not None


def find_unsafe_language(text: str) -> List[SafetyMatch]:
    """Return every span of unhedged second-person medical language in ``text``.

    The result is empty for hedged, population-level, or genotype-factual
    sentences, and non-empty for statements of diagnosis, certain prognosis,
    or medication instruction. Callers that only need a yes/no should test
    the list's truthiness; ``check_safety`` does that and appends the notice.
    """
    if not text:
        return []
    found: List[SafetyMatch] = []
    for category, patterns in _COMPILED.items():
        for pattern in patterns:
            for m in pattern.finditer(text):
                if _hedged(text, m.start()):
                    continue
                found.append(SafetyMatch(category, m.group(0), m.start(), m.end()))
    found.sort(key=lambda sm: (sm.start, sm.end))
    return found


SAFETY_NOTICE = (
    "\n[Safety Note: This explanation has been flagged for potentially "
    "definitive language ({categories}). Please review carefully and consult "
    "a healthcare provider.]"
)


STANDARD_DISCLAIMER = """
---

**Important Disclaimer:** This explanation is for educational purposes only and should not be interpreted as medical advice. Genetic findings can be complex and may have different implications for different individuals. Always consult with a qualified healthcare provider or genetic counselor before making any health decisions based on genetic information. Allelio and its AI explanation tools do not provide medical diagnosis or treatment recommendations.
"""


def check_safety(explanation: str) -> Tuple[str, List[str]]:
    """
    Check an AI-generated explanation for unhedged medical language.

    A lexical filter (see ``find_unsafe_language``): it flags statements of
    diagnosis, certain prognosis, or medication instruction addressed to the
    user, and appends a visible notice. It does not remove or rewrite the
    text, and it makes no judgement about factual accuracy.

    Args:
        explanation: The explanation text generated by the LLM

    Returns:
        Tuple of (cleaned_explanation, warnings_list)
        - cleaned_explanation: The explanation with the safety notice appended if needed
        - warnings_list: One message per category of language found
    """
    matches = find_unsafe_language(explanation)
    if not matches:
        return explanation, []

    categories = []
    for m in matches:
        if m.category not in categories:
            categories.append(m.category)
    warnings = [
        f"Explanation contained definitive medical language ({category}: "
        f"\"{next(m.text for m in matches if m.category == category)}\") "
        "that has been flagged for review."
        for category in categories
    ]
    cleaned = explanation + SAFETY_NOTICE.format(categories=", ".join(categories))
    return cleaned, warnings


def get_variant_warnings(result) -> List[str]:
    """
    Check if a variant is high-impact and return appropriate warnings.
    
    Args:
        result: A VariantResult object from allelio.analysis.lookup
        
    Returns:
        List of warning strings for high-impact variants
    """
    warnings = []

    # Extract gene from clinvar or gwas entries
    gene = None
    if hasattr(result, 'clinvar_entries') and result.clinvar_entries:
        gene = getattr(result.clinvar_entries[0], 'gene', None)
    elif hasattr(result, 'gwas_entries') and result.gwas_entries:
        gene = getattr(result.gwas_entries[0], 'mapped_gene', None)

    if gene and gene in HIGH_IMPACT_VARIANTS:
        warnings.append(HIGH_IMPACT_VARIANTS[gene])

    # Check by rsID
    rsid = getattr(result, 'rsid', None)
    if rsid and rsid in HIGH_IMPACT_VARIANTS:
        warnings.append(HIGH_IMPACT_VARIANTS[rsid])

    return warnings


def wrap_with_disclaimer(explanation: str, warnings: List[str]) -> str:
    """
    Wrap an explanation with the standard disclaimer and any specific warnings.
    
    Args:
        explanation: The explanation text
        warnings: List of specific warning messages about this variant
        
    Returns:
        Wrapped explanation with disclaimers and warnings
    """
    result = explanation
    
    # Add specific warnings first
    if warnings:
        warnings_section = "\n**⚠ Important Notes:**\n"
        for warning in warnings:
            warnings_section += f"- {warning}\n"
        result = result + "\n" + warnings_section
    
    # Add standard disclaimer
    result = result + STANDARD_DISCLAIMER
    
    return result
