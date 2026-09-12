"""Mode of inheritance for one ClinVar assertion, resolved per condition.

ClinGen curates gene-disease pairs, each with its own mode of inheritance.
A gene can carry a dominant and a recessive curation at once (GBA1: Parkinson
disease AD, Gaucher disease AR), so the gene alone cannot say whether one
copy of an allele is carrier status. What can is the condition the ClinVar
assertion is about: ClinVar gives a MONDO identifier for most conditions in
PhenotypeIDS, ClinGen gives one for every curation, and the two are compared
as identifiers, never as names.

Both views are kept. ``resolve_inheritance`` returns the condition-specific
answer (or why there is none) and the gene-level summary beside it.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from allelio.database.clingen import MOI_LABELS

# How a ClinVar condition is mapped to a ClinGen curation, recorded on every
# resolution so an export says which rule produced it. "mondo-exact" means
# the MONDO identifiers are equal after the alias table below; nothing is
# inferred from disease names. Bump the version when the rule or the table
# changes.
CONDITION_MAPPING_METHOD = "mondo-exact"
CONDITION_MAPPING_VERSION = "1.0"

# Explicit, reviewed equivalences: a MONDO identifier as ClinVar writes it
# mapped to the identifier ClinGen curates under. Empty until a case has been
# checked against both sources; never populated from name similarity.
CONDITION_ALIASES: Dict[str, str] = {}

# ClinGen classifications that count as an established gene-disease link when
# deciding the mode of inheritance. Limited / Disputed / Refuted / "No Known
# Disease Relationship" do not decide it.
CLINGEN_ESTABLISHED = ("Definitive", "Strong", "Moderate")

# Display phrase for one mode; anything else falls back to MOI_LABELS.
_MODE_PHRASES = {
    "AR": "autosomal recessive",
    "AD": "autosomal dominant",
    "XL": "X-linked",
    "SD": "semidominant",
    "MT": "mitochondrial",
}

# Resolution statuses, in the order a reader is likely to meet them.
RESOLVED = "resolved"
CONFLICTING = "conflicting"          # matched conditions are inherited differently
UNMAPPED = "unmapped"                # identifiers present, none curated by ClinGen
NO_IDENTIFIERS = "no_identifiers"    # ClinVar gives no MONDO id for the assertion
NOT_STORED = "identifiers_not_stored"  # legacy database, refresh reference data
NOT_ESTABLISHED = "not_established"  # matched, but Limited/Disputed/Refuted only
NOT_CURATED = "not_curated"          # gene absent from ClinGen


@dataclass
class ClinGenEntry:
    """One ClinGen gene-disease validity curation."""
    gene: str
    disease: Optional[str] = None
    moi: Optional[str] = None
    classification: Optional[str] = None
    report_url: Optional[str] = None
    mondo_id: Optional[str] = None


@dataclass
class ConditionRef:
    """One condition ClinVar names for an assertion, with its identifiers.

    ``identifiers`` are the DB:ID pairs verbatim; ``mondo_id`` is the MONDO
    one among them (``MONDO:0021001``), or None when ClinVar gives none.
    """
    name: Optional[str]
    mondo_id: Optional[str] = None
    identifiers: List[str] = field(default_factory=list)


@dataclass
class InheritanceResolution:
    """What ClinGen says about the condition this assertion is about.

    ``inheritance`` and ``note`` are the display phrase and its provenance;
    ``status`` says how the phrase was reached. ``matched`` lists every
    ClinGen curation whose MONDO identifier the assertion carries, so a
    conflict stays visible. ``gene_inheritance`` is the gene-level summary,
    kept separately: it never decides the carrier label.
    """
    status: str
    inheritance: str
    note: Optional[str] = None
    condition: Optional[str] = None
    condition_id: Optional[str] = None
    matched: List[ClinGenEntry] = field(default_factory=list)
    conditions: List[ConditionRef] = field(default_factory=list)
    unmatched_condition_ids: List[str] = field(default_factory=list)
    gene_inheritance: str = "not curated"
    gene_note: Optional[str] = None
    mapping: Dict[str, str] = field(default_factory=lambda: {
        "method": CONDITION_MAPPING_METHOD, "version": CONDITION_MAPPING_VERSION,
    })


def _mondo(token: str) -> Optional[str]:
    """``MONDO:MONDO:0021001`` (ClinVar) or ``MONDO:0021001`` -> ``MONDO:0021001``."""
    token = token.strip()
    if token.startswith("MONDO:MONDO:"):
        token = token[len("MONDO:"):]
    if token.startswith("MONDO:") and token[len("MONDO:"):].isdigit():
        return token
    return None


def parse_conditions(names: Optional[str], ids: Optional[str]) -> List[ConditionRef]:
    """Pair ClinVar's PhenotypeList with PhenotypeIDS, entry by entry.

    Both columns are ``|``-separated with one entry per condition set; inside
    an entry ``;`` separates co-occurring conditions and ``,`` separates the
    identifiers of one condition. When the two columns do not have the same
    number of entries they cannot be paired; the identifiers are then kept
    without names rather than guessed onto the wrong ones.
    """
    name_items = [n.strip() for n in names.split("|")] if names else []
    id_items = [i.strip() for i in ids.split("|")] if ids else []
    refs: List[ConditionRef] = []
    aligned = bool(name_items) and len(name_items) == len(id_items)
    if not id_items:
        return [ConditionRef(name=n or None) for n in name_items]
    for index, id_item in enumerate(id_items):
        name_parts = name_items[index].split(";") if aligned else []
        for part_index, id_part in enumerate(id_item.split(";")):
            identifiers = [t.strip() for t in id_part.split(",") if t.strip()]
            mondo = next((m for m in (_mondo(t) for t in identifiers) if m), None)
            name = name_parts[part_index].strip() if part_index < len(name_parts) else ""
            refs.append(ConditionRef(name=name or None, mondo_id=mondo, identifiers=identifiers))
    return refs


def gene_inheritance(entries: List[ClinGenEntry]) -> Tuple[str, Optional[str]]:
    """Summarise ClinGen's curations for a gene as one inheritance phrase.

    Only established curations (see CLINGEN_ESTABLISHED) decide it. A gene
    curated for both dominant and recessive conditions reads "mixed": with
    one copy, whether that is carrier status depends on which condition the
    allele causes, which gene-level curation cannot say.

    Returns:
        (inheritance, note), e.g. ("autosomal recessive", "ClinGen:
        hemochromatosis type 1 (Definitive)").
    """
    established = [e for e in entries if (e.classification or "") in CLINGEN_ESTABLISHED]
    if not entries:
        return "not curated", None
    if not established:
        return "not established", (
            "ClinGen lists no established gene-disease relationship for this gene ("
            + "; ".join(f"{e.disease}: {e.classification}" for e in entries[:3]) + ")"
        )
    mois = {e.moi for e in established if e.moi}
    note = "ClinGen: " + "; ".join(
        f"{e.disease} ({MOI_LABELS.get(e.moi, e.moi or '?')}, {e.classification})" for e in established[:4]
    )
    if len(mois) == 1:
        mode = next(iter(mois))
        if mode in _MODE_PHRASES:
            return _MODE_PHRASES[mode], note
    if "AR" in mois and ("AD" in mois or "SD" in mois or "XL" in mois):
        return "mixed (dominant and recessive conditions)", note
    return ", ".join(sorted(MOI_LABELS.get(m, m) for m in mois)) or "undetermined", note


def _describe(entry: ClinGenEntry) -> str:
    mode = MOI_LABELS.get(entry.moi, entry.moi or "undetermined")
    return f"{entry.disease} ({entry.mondo_id or 'no MONDO id'}; {mode}, {entry.classification})"


def resolve_inheritance(
    conditions: Optional[str],
    condition_ids: Optional[str],
    clingen_entries: List[ClinGenEntry],
) -> InheritanceResolution:
    """Resolve the mode of inheritance for one ClinVar assertion.

    Args:
        conditions: ClinVar PhenotypeList for the assertion.
        condition_ids: ClinVar PhenotypeIDS for it. ``""`` means ClinVar
            gives none; ``None`` means the database predates the column and
            the value was never stored, which is a different thing to say.
        clingen_entries: ClinGen curations for the assertion's gene.

    Only a curation whose MONDO identifier the assertion carries can decide
    the mode. No match, no identifier, or matches that disagree leave the
    resolution unresolved with the reason recorded; the gene-level summary
    travels alongside as context.
    """
    gene_phrase, gene_note = gene_inheritance(clingen_entries)
    refs = parse_conditions(conditions, condition_ids)
    base = dict(conditions=refs, gene_inheritance=gene_phrase, gene_note=gene_note)
    mapping = {"method": CONDITION_MAPPING_METHOD, "version": CONDITION_MAPPING_VERSION}

    if not clingen_entries:
        return InheritanceResolution(NOT_CURATED, "not curated", mapping=mapping, **base)

    context = f"gene-level: {gene_phrase}" + (f" ({gene_note})" if gene_note else "")
    named = "; ".join(r.name for r in refs if r.name) or "none named"

    if condition_ids is None:
        return InheritanceResolution(
            NOT_STORED, "unresolved (condition identifiers not stored)",
            note=f"this database predates condition identifiers; run allelio update. "
                 f"ClinVar conditions: {named}. {context}",
            mapping=mapping, **base,
        )

    wanted = {CONDITION_ALIASES.get(r.mondo_id, r.mondo_id) for r in refs if r.mondo_id}
    if not wanted:
        return InheritanceResolution(
            NO_IDENTIFIERS, "unresolved (no condition identifiers)",
            note=f"ClinVar gives no MONDO identifier for this assertion's conditions ({named}), "
                 f"so no ClinGen curation can be matched. {context}",
            mapping=mapping, **base,
        )

    matched = [e for e in clingen_entries if e.mondo_id and e.mondo_id in wanted]
    unmatched = sorted(wanted - {e.mondo_id for e in matched})
    if not matched:
        return InheritanceResolution(
            UNMAPPED, "unresolved (conditions not curated by ClinGen)",
            note=f"none of the assertion's conditions ({', '.join(unmatched)}) is a ClinGen "
                 f"curation for this gene; matched by {CONDITION_MAPPING_METHOD} "
                 f"{CONDITION_MAPPING_VERSION}. {context}",
            matched=[], unmatched_condition_ids=unmatched, mapping=mapping, **base,
        )

    established = [e for e in matched if (e.classification or "") in CLINGEN_ESTABLISHED]
    if not established:
        labels = ", ".join(sorted({e.classification or "unclassified" for e in matched}))
        return InheritanceResolution(
            NOT_ESTABLISHED, f"not established ({labels})",
            note="ClinGen matched the condition but does not classify the relationship as "
                 f"established: {'; '.join(_describe(e) for e in matched)}. {context}",
            matched=matched, unmatched_condition_ids=unmatched, mapping=mapping, **base,
        )

    modes = sorted({e.moi for e in established if e.moi})
    described = "; ".join(_describe(e) for e in established)
    provenance = f"matched by {CONDITION_MAPPING_METHOD} {CONDITION_MAPPING_VERSION}"
    if len(modes) == 1:
        phrase = _MODE_PHRASES.get(modes[0], MOI_LABELS.get(modes[0], modes[0]))
        note = f"ClinGen: {described}; {provenance}"
        if gene_phrase != phrase:
            note += f". {context}"
        first = established[0]
        return InheritanceResolution(
            RESOLVED, phrase, note=note, condition=first.disease, condition_id=first.mondo_id,
            matched=matched, unmatched_condition_ids=unmatched, mapping=mapping, **base,
        )
    if not modes:
        return InheritanceResolution(
            CONFLICTING, "undetermined",
            note=f"ClinGen gives no mode of inheritance for the matched condition: {described}. {context}",
            matched=matched, unmatched_condition_ids=unmatched, mapping=mapping, **base,
        )
    labels = ", ".join(_MODE_PHRASES.get(m, MOI_LABELS.get(m, m)) for m in modes)
    return InheritanceResolution(
        CONFLICTING, f"conflicting (matched conditions differ: {labels})",
        note=f"the assertion names conditions ClinGen inherits differently: {described}; "
             f"{provenance}. Which condition this allele causes is not decided here. {context}",
        matched=matched, unmatched_condition_ids=unmatched, mapping=mapping, **base,
    )


def is_carrier(resolution: Optional[InheritanceResolution], alt_copies: Optional[int],
               genotype: Optional[str]) -> bool:
    """One copy of the allele, where the resolved condition makes that a carrier.

    Only a resolved condition-specific mode decides it: a recessive condition,
    or an X-linked one on a diploid genotype (a single-letter genotype is
    hemizygous, so one copy is the affected genotype). Conflicting,
    unmapped, or absent resolutions never produce a carrier label.
    """
    if resolution is None or resolution.status != RESOLVED or alt_copies != 1:
        return False
    if resolution.inheritance == "autosomal recessive":
        return True
    if resolution.inheritance == "X-linked":
        return len(genotype or "") == 2
    return False
