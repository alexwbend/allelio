"""Regressions found while auditing PRs 32–36; all variants are synthetic."""
import json
from pathlib import Path

import pytest

from allelio.analysis.inheritance import ClinGenEntry, resolve_inheritance, is_carrier
from allelio.analysis.lookup import analyze_variants, analyze_variants_with_stats
from allelio.database.store import AllelioDB
from allelio.parsers.base import Variant, VCFEvidence
from allelio.schema import validate_evidence
from tests.test_frequency_identity import _db, _row
from scripts.build_gnomad_freq import allele_values, load_array_sites


@pytest.mark.parametrize('field,value', [('inputs', 1), ('findings', [1]), ('matching', {'counts': {'retained': 'bad'}}), ('coverage', 'bad')])
def test_malformed_evidence_returns_errors_without_crashing(field, value):
    doc = json.loads((Path(__file__).parent / 'fixtures/evidence_schema/valid_small.json').read_text())
    doc[field] = value
    assert validate_evidence(doc)


def test_missing_candidates_cannot_hide_dangling_support():
    doc = json.loads((Path(__file__).parent / 'fixtures/evidence_schema/valid_small.json').read_text())
    doc['matching']['candidates'] = []
    assert any('candidate' in error for error in validate_evidence(doc))


def test_wrong_candidate_site_is_rejected():
    doc = json.loads((Path(__file__).parent / 'fixtures/evidence_schema/valid_small.json').read_text())
    doc['matching']['candidates'][0]['rsid'] = 'rs999'
    assert any('rsID' in error for error in validate_evidence(doc))


def test_short_per_allele_field_is_not_reused():
    assert allele_values({'AF': '0.2', 'AC': '20', 'AN': '100'}, 1)[:4] == ['.', '.', '.', '100']


def test_array_site_list_accepts_spaces(tmp_path):
    path = tmp_path / 'sites.txt'
    path.write_text('rs1 1 100 AG\nrs2,2,200,CT\n')
    assert load_array_sites(str(path)) == {'rs1', 'rs2'}


@pytest.mark.parametrize('evidence', [
    VCFEvidence('T', ('A',), (0, 1), ('T', 'A'), False, reference_declaration='GRCh37'),
    VCFEvidence('C', ('A',), (0, 1), ('C', 'A'), False, reference_declaration='GRCh38'),
])
def test_unresolved_clinvar_identity_cannot_anchor_frequency(tmp_path, evidence):
    db = _db(tmp_path, [_row(.3)])
    variant = Variant('rs334', '11', 5227002, ''.join(evidence.alleles), evidence)
    results = analyze_variants([variant], db)
    baseline, _ = analyze_variants_with_stats([variant], db, frequency_adjustment=False)
    assert results[0].gnomad_entry.identity == 'unverified'
    assert results[0].significance_rank == baseline[0].significance_rank


def test_frequency_locations_and_builds_coexist(tmp_path):
    db = _db(tmp_path, [_row(.01), _row(.9, chromosome='X'), _row(.8, assembly='GRCh37'), _row(.7, position=5227003)])
    assert len(db.lookup_rsid('rs334')['gnomad']) == 4
    [result] = analyze_variants([Variant('rs334', '11', 5227002, 'TA')], db)
    assert result.gnomad_entry.allele_frequency == .01
    db.initialize()
    assert len(db.lookup_rsid('rs334')['gnomad']) == 4


def test_unmapped_condition_blocks_carrier():
    result = resolve_inheritance('A|B', 'MONDO:1|MONDO:2', [ClinGenEntry('G', 'A', 'AR', 'Definitive', mondo_id='MONDO:1')])
    assert result.status == 'unmapped'
    assert result.matched and result.unmatched_condition_ids == ['MONDO:2']
    assert not is_carrier(result, 1, 'AG')


def test_each_assertion_uses_its_own_gene_and_blocks_conflicting_carrier(tmp_path):
    db = AllelioDB(str(tmp_path / 'genes.db'))
    db.initialize()
    db.insert_clinvar_batch([dict(rsid='rs1', ref_allele='G', alt_allele='A', gene=g,
        allele_id=str(i), clinical_significance='Pathogenic', conditions=g,
        condition_ids='MONDO:1', review_status='practice guideline') for i,g in enumerate(('AR_GENE', 'AD_GENE'),1)])
    db.insert_clingen_batch([dict(gene=g, disease=g, mondo_id='MONDO:1', moi=m,
        classification='Definitive', hgnc_id=None, report_url=None, classification_date=None) for g,m in [('AR_GENE','AR'),('AD_GENE','AD')]])
    [result] = analyze_variants([Variant('rs1','1',100,'GA')], db)
    assert [e.inheritance.inheritance for e in result.clinvar_entries] == ['autosomal recessive','autosomal dominant']
    assert result.category == 'Health Conditions'


def test_legacy_lookup_does_not_require_update_first(tmp_path):
    db = AllelioDB(str(tmp_path / 'legacy.db'))
    db.cursor.executescript('''CREATE TABLE clinvar(rsid TEXT, ref_allele TEXT, alt_allele TEXT);
        CREATE TABLE gwas(rsid TEXT);
        CREATE TABLE gnomad(rsid TEXT PRIMARY KEY, allele_frequency REAL);
        INSERT INTO gnomad VALUES ('rs1', 0.4);''')
    assert db.lookup_rsid('rs1')['gnomad'][0]['allele_frequency'] == .4
    assert db.lookup_rsids_batch(['rs1'])['rs1']['gnomad'][0]['assembly'] is None


def test_builder_failure_does_not_replace_existing_extract(tmp_path, monkeypatch, capsys):
    from scripts import build_gnomad_freq as builder
    output = tmp_path / 'out.tsv.gz'
    output.write_bytes(b'existing release')
    monkeypatch.setattr('sys.argv', ['build', '--output', str(output), '--chromosomes', '21'])
    def fail(*args):
        raise OSError('synthetic interrupted source')
    monkeypatch.setattr(builder, 'stream_process_vcf', fail)
    assert builder.main() == 1
    assert output.read_bytes() == b'existing release'
    assert 'SHA-256:' not in capsys.readouterr().out


def test_absent_clinvar_column_does_not_borrow_neighbour(tmp_path):
    from allelio.database.clinvar import parse_clinvar
    source = Path(__file__).parent / 'fixtures/clinvar_context/variant_summary_split.tsv'
    lines = [line.split('\t') for line in source.read_text().splitlines()]
    removed = lines[0].index('OriginSimple')
    for row in lines:
        del row[removed]
    path = tmp_path / 'source.tsv'
    path.write_text('\n'.join('\t'.join(row) for row in lines)+'\n')
    records = list(parse_clinvar(str(path)))
    assert records and all(row['origin_simple'] is None for row in records)
    assert records[0]['assembly'] == 'GRCh38'


def test_ambiguous_clinvar_coordinates_do_not_pick_first_frequency():
    from allelio.analysis.lookup import _allele_anchor
    rows = [dict(assembly='GRCh38', chromosome='1', position_vcf=pos,
                 ref_allele='G', alt_allele='A') for pos in (100,200)]
    assert _allele_anchor(rows, 'A', None, '1', 100) is None


def test_existing_format2_database_migrates_without_losing_rows(tmp_path):
    db = AllelioDB(str(tmp_path / 'format2.db'))
    db.cursor.execute('''CREATE TABLE gnomad (
        rsid TEXT, ref_allele TEXT, alt_allele TEXT, chromosome TEXT,
        position INTEGER, assembly TEXT, source_version TEXT,
        allele_frequency REAL, af_popmax REAL, ac INTEGER, an INTEGER, nhomalt INTEGER,
        af_afr REAL, af_eas REAL, af_fin REAL, af_nfe REAL, af_sas REAL,
        PRIMARY KEY(rsid, ref_allele, alt_allele))''')
    db.cursor.execute("INSERT INTO gnomad(rsid,ref_allele,alt_allele,chromosome,position,assembly,source_version,allele_frequency) VALUES ('rs334','T','A','11',5227002,'GRCh38','v4.1.1',0.01)")
    db.conn.commit()
    db.initialize()
    db.insert_gnomad_batch([_row(.9, chromosome='X')])
    rows = db.lookup_rsid('rs334')['gnomad']
    assert {(r['chromosome'],r['allele_frequency']) for r in rows} == {('11',.01),('X',.9)}
