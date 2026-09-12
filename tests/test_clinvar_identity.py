"""Reference provenance survives parsing and non-destructive schema migration."""
import sqlite3
import pytest
from allelio.database.clinvar import parse_clinvar
from allelio.database.store import AllelioDB
from allelio.analysis.lookup import _clinvar_entry


def source(tmp_path, position='101'):
    row = [''] * 34
    for i, value in {0:'123', 4:'GENE', 5:'HGNC:1', 6:'Pathogenic', 9:'1',
                     16:'GRCh38', 18:'X', 24:'reviewed by expert panel',
                     30:'456', 31:position, 32:'A', 33:'G'}.items():
        row[i] = value
    path = tmp_path / 'source.tsv'
    path.write_text('\t'.join(row) + '\n')
    return next(parse_clinvar(str(path)))


def test_round_trip(tmp_path):
    record = source(tmp_path)
    db = AllelioDB(str(tmp_path / 'a.db'))
    db.initialize()
    db.insert_clinvar_batch([record])
    single = db.lookup_rsid('rs1')['clinvar'][0]
    batch = db.lookup_rsids_batch(['rs1'])['rs1']['clinvar'][0]
    assert single == batch
    entry = _clinvar_entry(single)
    assert (entry.assembly, entry.chromosome, entry.position_vcf) == ('GRCh38', 'X', 101)
    assert (entry.allele_id, entry.variation_id, entry.hgnc_id) == ('123', '456', 'HGNC:1')


@pytest.mark.parametrize('value', ['', 'na', '-1', '0', 'junk', str(2**63)])
def test_missing_or_invalid_position(tmp_path, value):
    assert source(tmp_path, value)['position_vcf'] is None


def test_legacy_migration_preserves_rows(tmp_path):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as con:
        con.execute('CREATE TABLE clinvar (rsid TEXT, ref_allele TEXT, alt_allele TEXT, gene TEXT, clinical_significance TEXT, conditions TEXT, review_status TEXT, last_evaluated TEXT, PRIMARY KEY(rsid, ref_allele, alt_allele))')
        con.execute("INSERT INTO clinvar VALUES ('rs1','A','G','GENE','Pathogenic','','','')")
    db = AllelioDB(str(path))
    db.initialize()
    db.initialize()  # Idempotent.
    row, = db.lookup_rsid('rs1')['clinvar']
    assert row['gene'] == 'GENE' and row['alt_allele'] == 'G'
    assert all(row[key] is None for key in ('assembly', 'position_vcf', 'variation_id', 'hgnc_id'))
    # Key columns cannot be NULL; '' is "not recorded" and reads as None on the entry.
    assert (row['chromosome'], row['allele_id']) == ('', '')
    from allelio.analysis.lookup import _clinvar_entry
    entry = _clinvar_entry(row)
    assert entry.chromosome is None and entry.allele_id is None and entry.classification_type == "unknown"
