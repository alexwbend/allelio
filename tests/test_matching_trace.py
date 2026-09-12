"""The evidence export explains why each candidate record was kept or not.

All reference rows here are synthetic. The trace is read back through
``build_evidence_export`` so the document-local references are what is
tested, not internal objects.
"""

import json
from collections import Counter

import pytest

from allelio.analysis.lookup import analyze_variants, analyze_variants_with_stats
from allelio.analysis.trace import PATHS, reason_from_note
from allelio.database.store import AllelioDB
from allelio.evidence import build_evidence_export
from allelio.parsers.base import VCFEvidence, Variant


def _clinvar(rsid, ref, alt, sig, chrom="11", pos=5227002, allele_id="1", gene="HBB", **extra):
    row = dict(rsid=rsid, ref_allele=ref, alt_allele=alt, gene=gene, clinical_significance=sig,
               conditions="Cond", condition_ids="MONDO:MONDO:0900001,MedGen:C1", review_status="practice guideline",
               last_evaluated="", assembly="GRCh38", chromosome=chrom, position_vcf=pos, allele_id=allele_id)
    row.update(extra)
    return row


def _gwas(rsid, risk_allele, trait="Trait", study="Study A", pubmed="1"):
    return dict(rsid=rsid, trait=trait, p_value=1e-9, odds_ratio="1.2", mapped_gene="HBB", study=study,
                pubmed_id=pubmed, link="", risk_allele=risk_allele)


def _gnomad(rsid, ref, alt, af, chrom="11", pos=5227002, assembly="GRCh38"):
    return dict(rsid=rsid, chromosome=chrom, position=pos, ref_allele=ref, alt_allele=alt, assembly=assembly,
                source_version="v4.1.1", allele_frequency=af, af_popmax=None, ac=None, an=None, nhomalt=None,
                af_afr=None, af_eas=None, af_fin=None, af_nfe=None, af_sas=None)


def _pgx(rsid, genotype, level, annotation_id, drugs="drug"):
    return dict(annotation_id=annotation_id, genotype=genotype, rsid=rsid, gene="HBB", level=level, score=1.0,
                phenotype_category="Efficacy", drugs=drugs, phenotypes="", url="", annotation_text="text",
                allele_function="")


@pytest.fixture
def db(tmp_path):
    db = AllelioDB(str(tmp_path / "trace.db"))
    db.initialize()
    db.insert_clinvar_batch([
        # Multiallelic site with two records for one allele and a haplotype row.
        _clinvar("rs334", "T", "A", "Pathogenic", allele_id="15333"),
        _clinvar("rs334", "T", "G", "Likely benign", allele_id="15334"),
        _clinvar("rs334", "T", "A", "Conflicting classifications of pathogenicity", allele_id="99999",
                 review_status="criteria provided, conflicting classifications"),
        _clinvar("rs334", "T", "T", "Benign", allele_id="77777"),
        # A record whose allele ClinVar does not give.
        _clinvar("rs500", "", "", "Pathogenic", chrom="1", pos=500, allele_id="500", gene="G2"),
        # Reference-only site.
        _clinvar("rs600", "C", "T", "Pathogenic", chrom="1", pos=600, allele_id="600", gene="G3"),
        # VCF-anchored site.
        _clinvar("rs700", "A", "G", "Pathogenic", chrom="1", pos=700, allele_id="700", gene="G4"),
    ])
    db.insert_gwas_batch([_gwas("rs334", "A"), _gwas("rs334", "T", trait="Other", study="Study B", pubmed="2"),
                          _gwas("rs334", None, trait="No allele", study="Study C", pubmed="3"),
                          _gwas("rs600", "T", study="Study D", pubmed="4")])
    db.insert_gnomad_batch([_gnomad("rs334", "T", "A", 0.0127), _gnomad("rs334", "T", "G", 0.0005),
                            _gnomad("rs600", "C", "T", 0.3), _gnomad("rs700", "A", "G", 0.2, chrom="1", pos=700),
                            _gnomad("rs700", "A", "G", 0.9, chrom="1", pos=700, assembly="GRCh37")])
    db.insert_clinpgx_batch([_pgx("rs334", "AT", "1A", "pa1"), _pgx("rs334", "TT", "1A", "pa2"),
                             _pgx("rs334", "AT", "3", "pa3")])
    db.insert_clingen_batch([
        dict(gene="HBB", hgnc_id="HGNC:4827", disease="named condition", mondo_id="MONDO:0900001", moi="AR",
             classification="Definitive", report_url="", classification_date=""),
        dict(gene="HBB", hgnc_id="HGNC:4827", disease="other condition", mondo_id="MONDO:0900002", moi="AD",
             classification="Definitive", report_url="", classification_date=""),
    ])
    return db


def _export(db, variants, detailed=False, **kwargs):
    results = analyze_variants(variants, db, **kwargs)
    document = build_evidence_export(results, variants, {}, {"detailed_trace": detailed}, results.stats,
                                     detailed_trace=detailed)
    json.dumps(document, allow_nan=False)
    return document


def _by_reason(candidates, source=None):
    return Counter((c["source"], c["reason"]) for c in candidates if source in (None, c["source"]))


class TestMultipleCandidatesAtOneSite:
    def test_every_record_gets_a_decision_and_the_finding_links_to_its_support(self, db):
        variants = [Variant("rs334", "11", 5227002, "TA")]
        document = _export(db, variants)
        [finding] = document["findings"]
        [site] = [s for s in document["matching"]["sites"] if s["rsid"] == "rs334"]
        candidates = {c["candidate_id"]: c for c in document["matching"]["candidates"]}
        assert site["finding_id"] == finding["finding_id"] and site["input_ids"] == ["input-1"]
        assert site["candidates_listed"] and set(site["candidate_ids"]) <= set(candidates)
        reasons = _by_reason(candidates.values())
        # ClinVar: two distinct pathogenic-side records carried; the T>G record cannot be judged against
        # a TA genotype (A is not one of its alleles) and is unresolved; the haplotype row is dropped
        assert reasons[("clinvar", "allele_carried")] == 2
        assert reasons[("clinvar", "genotype_allele_mismatch")] == 1
        assert reasons[("clinvar", "haplotype_row_superseded")] == 1
        # GWAS rides on the ClinVar match: every association, allele or not, is shown with it
        assert reasons[("gwas", "reported_with_clinvar_match")] == 3
        # ClinPGx: the AT row matched, TT is another genotype, level 3 is below the threshold
        assert reasons[("clinpgx", "pgx_genotype_matched")] == 1
        assert reasons[("clinpgx", "pgx_other_genotype")] == 1
        assert reasons[("clinpgx", "pgx_below_min_level")] == 1
        # gnomAD: T>A matched, T>G is the other allele
        assert reasons[("gnomad", "frequency_identity_matched")] == 1
        assert reasons[("gnomad", "frequency_other_allele")] == 1
        # ClinGen: the named condition matched, the other curation is not named
        assert reasons[("clingen", "condition_matched_by_mondo")] == 1
        assert reasons[("clingen", "condition_not_named_by_assertion")] == 1
        # The finding's supporting candidates are exactly the retained ones at the site
        retained = {cid for cid in site["candidate_ids"] if candidates[cid]["decision"] == "retained"}
        assert set(finding["candidate_ids"]) == retained and retained
        assert all(candidates[cid]["finding_id"] == finding["finding_id"] for cid in retained)
        rejected = [candidates[cid] for cid in site["candidate_ids"] if candidates[cid]["decision"] == "rejected"]
        assert all(c["finding_id"] is None and c["identity"] for c in rejected)

    def test_rejected_and_unresolved_candidates_keep_source_identity(self, db):
        document = _export(db, [Variant("rs334", "11", 5227002, "TA")])
        other_allele = next(c for c in document["matching"]["candidates"]
                            if c["source"] == "clinvar" and c["reason"] == "genotype_allele_mismatch")
        assert other_allele["identity"]["allele_id"] == "15334" and other_allele["identity"]["alt_allele"] == "G"
        assert other_allele["decision"] == "unresolved" and other_allele["stage"] == "allele"
        assert other_allele["note"].startswith("genotype TA does not match annotated alleles T/G")
        assert "not shown" in other_allele["note"]
        absent = _export(db, [Variant("rs600", "1", 600, "CC")], detailed=True)["matching"]["candidates"]
        [c] = [c for c in absent if c["source"] == "clinvar"]
        assert c["decision"] == "rejected" and c["reason"] == "allele_absent" and c["note"] == "no copy of T"
        assert c["identity"]["allele_id"] == "600" and c["identity"]["position_vcf"] == 600
        frequency = next(c for c in document["matching"]["candidates"] if c["reason"] == "frequency_other_allele")
        assert frequency["identity"]["alt_allele"] == "G" and "T>G" in frequency["note"]


class TestAmbiguousAndUnresolved:
    def test_allele_not_recorded_is_unresolved(self, db):
        document = _export(db, [Variant("rs500", "1", 500, "AG")])
        [c] = [c for c in document["matching"]["candidates"] if c["source"] == "clinvar"]
        assert c["decision"] == "unresolved" and c["reason"] == "allele_not_recorded"
        assert document["findings"][0]["candidate_ids"] == []  # unresolved records do not support a finding

    def test_strand_ambiguous_risk_allele(self, db):
        db.insert_gwas_batch([_gwas("rs900", "G", study="Study E", pubmed="5")])
        document = _export(db, [Variant("rs900", "1", 900, "CC")])
        [c] = document["matching"]["candidates"]
        assert (c["source"], c["decision"], c["reason"]) == ("gwas", "unresolved", "strand_ambiguous")
        assert "may be on the opposite strand" in c["note"]

    def test_opposite_strand_read_is_named_in_the_note(self, db):
        document = _export(db, [Variant("rs334", "11", 5227002, "CC")], include_benign=True)
        carried = [c for c in document["matching"]["candidates"]
                   if c["source"] == "clinvar" and c["reason"] == "allele_carried"]
        assert [c["note"] for c in carried] == ["2 copies of G (genotype read on the opposite strand)"]

    def test_no_call_is_unresolved_across_sources(self, db):
        document = _export(db, [Variant("rs334", "11", 5227002, "--")])
        reasons = _by_reason(document["matching"]["candidates"])
        assert reasons[("clinvar", "genotype_no_call")] == 3
        assert reasons[("clinpgx", "genotype_unavailable")] == 3


class TestBuildAndFilter:
    def test_vcf_build_mismatch_is_an_identity_stage_decision(self, db):
        evidence = VCFEvidence("A", ("G",), (0, 1), ("A", "G"), False, reference_declaration="GRCh37")
        document = _export(db, [Variant("rs700", "1", 700, "AG", evidence)])
        [c] = [c for c in document["matching"]["candidates"] if c["source"] == "clinvar"]
        assert (c["decision"], c["stage"], c["reason"]) == ("unresolved", "identity", "build_mismatch")

    def test_frequency_build_mismatch_is_rejected_with_its_identity(self, db):
        # The fixture's second rs700 row (GRCh37) replaced the GRCh38 one: one extract is one assembly.
        evidence = VCFEvidence("A", ("G",), (0, 1), ("A", "G"), False, reference_declaration="GRCh38")
        document = _export(db, [Variant("rs700", "1", 700, "AG", evidence)])
        [c] = [c for c in document["matching"]["candidates"] if c["source"] == "gnomad"]
        assert (c["decision"], c["stage"], c["reason"]) == ("rejected", "frequency", "frequency_build_mismatch")
        assert c["identity"]["assembly"] == "GRCh37" and c["identity"]["allele_frequency"] == 0.9
        assert document["findings"][0]["candidate_ids"] and c["candidate_id"] not in document["findings"][0]["candidate_ids"]

    def test_filter_failure_rejects_every_candidate_at_the_filter_stage(self, db):
        evidence = VCFEvidence("T", ("A",), (0, 1), ("T", "A"), False, reference_declaration="GRCh38",
                               filter_status="LowQual")
        results, stats = analyze_variants_with_stats([Variant("rs334", "11", 5227002, "TA", evidence)], db)
        assert results == [] and stats.dispositions["rs334"] == "failed_filter"
        document = build_evidence_export(results, [Variant("rs334", "11", 5227002, "TA", evidence)], {}, stats=stats)
        candidates = document["matching"]["candidates"]
        assert candidates and all(c["stage"] == "filter" and c["reason"] == "vcf_filter_failed" for c in candidates)
        assert {c["source"] for c in candidates} == {"clinvar", "gwas", "clinpgx", "gnomad"}
        [site] = document["matching"]["sites"]
        assert site["finding_id"] is None and site["disposition"] == "failed_filter"

    def test_non_snp_vcf_record_marks_snp_paths_unsupported(self, db):
        evidence = VCFEvidence("T", ("TA",), (0, 1), ("T", "TA"), False, reference_declaration="GRCh38")
        results, stats = analyze_variants_with_stats([Variant("rs334", "11", 5227002, "TTA", evidence)], db)
        reasons = Counter((c.source, c.reason) for c in stats.trace.candidates)
        assert reasons[("gwas", "non_snp_unsupported")] == 3 and reasons[("clinpgx", "non_snp_unsupported")] == 3
        clinvar = [c for c in stats.trace.candidates if c.source == "clinvar"]
        assert Counter(c.reason for c in clinvar) == {"non_snp_unsupported": 3, "haplotype_row_superseded": 1}


class TestReferenceOnlyAndCounts:
    def test_reference_site_is_counted_but_listed_only_in_detail(self, db):
        variants = [Variant("rs600", "1", 600, "CC"), Variant("rs334", "11", 5227002, "TA"), Variant("rs999", "1", 1, "AA")]
        summary = _export(db, variants)
        matching = summary["matching"]
        [ref_site] = [s for s in matching["sites"] if s["rsid"] == "rs600"]
        assert ref_site["disposition"] == "reference_or_no_applicable_annotation"
        assert ref_site["finding_id"] is None and ref_site["candidates_listed"] is False
        assert ref_site["candidate_ids"] is None and ref_site["counts"] == {"rejected": 2}
        assert matching["candidate_count"] == matching["listed_candidate_count"] + ref_site["candidate_count"]
        assert not any(c["rsid"] == "rs600" for c in matching["candidates"])
        # rs999 has no reference record at all: no candidates, but it is in coverage
        assert not any(s["rsid"] == "rs999" for s in matching["sites"])
        assert any(row["rsid"] == "rs999" for row in summary["coverage"]["rows"])
        detailed = _export(db, variants, detailed=True)["matching"]
        assert detailed["detailed"] and detailed["listed_candidate_count"] == detailed["candidate_count"]
        listed = [c for c in detailed["candidates"] if c["rsid"] == "rs600"]
        assert {(c["source"], c["reason"]) for c in listed} == {("clinvar", "allele_absent"), ("gwas", "risk_allele_absent")}

    def test_counts_are_records_not_rows_or_findings(self, db):
        variants = [Variant("rs334", "11", 5227002, "TA"), Variant("rs334", "11", 5227002, "TA"),
                    Variant("rs600", "1", 600, "CC")]
        document = _export(db, variants)
        matching, coverage = document["matching"], document["coverage"]
        assert coverage["total_rows"] == 3 and coverage["returned_findings"] == 1
        assert matching["sites_with_candidates"] == 2
        assert matching["candidate_count"] == sum(matching["counts"].values()) > coverage["total_rows"]
        assert sum(sum(v.values()) for v in matching["by_source"].values()) == matching["candidate_count"]
        [site] = [s for s in matching["sites"] if s["rsid"] == "rs334"]
        assert site["input_ids"] == ["input-1", "input-2"]

    def test_retained_candidates_at_a_site_set_aside_later_have_no_finding(self, db):
        db.insert_clinvar_batch([_clinvar("rs800", "G", "A", "Benign", chrom="1", pos=800, allele_id="800", gene="G5")])
        document = _export(db, [Variant("rs800", "1", 800, "GA")])
        assert document["findings"] == []
        [site] = document["matching"]["sites"]
        assert site["disposition"] == "rank_filtered" and site["finding_id"] is None
        [c] = document["matching"]["candidates"]
        assert c["decision"] == "retained" and c["finding_id"] is None


class TestCrossSourceAndPaths:
    def test_gwas_only_site_judged_on_its_own_risk_allele(self, db):
        db.insert_gwas_batch([_gwas("rs900", "G", study="Study E", pubmed="5")])
        document = _export(db, [Variant("rs900", "1", 900, "AG")])
        [c] = document["matching"]["candidates"]
        assert (c["source"], c["decision"], c["reason"]) == ("gwas", "retained", "risk_allele_carried")
        assert document["findings"][0]["candidate_ids"] == [c["candidate_id"]]

    def test_every_path_is_declared(self, db):
        document = _export(db, [Variant("rs334", "11", 5227002, "TA")])
        assert set(document["matching"]["paths"]) == {"clinvar", "gwas", "clinpgx", "gnomad", "clingen"} == set(PATHS)
        assert all(text.startswith("traced") for text in document["matching"]["paths"].values())
        assert "trace" not in document["analysis_stats"]
        assert any("AI-generated" in line for line in document["matching"]["limitations"])

    def test_reason_codes_are_stable_for_known_notes(self):
        assert reason_from_note("VCF and ClinVar positions differ") == "position_mismatch"
        assert reason_from_note("genotype AG does not match annotated alleles C/T") == "genotype_allele_mismatch"
        assert reason_from_note("something new") == "unresolved_other"
        assert reason_from_note(None) == "unresolved_other"
