"""Exercise the real curated identity with invented observations/reference assertions."""
from pathlib import Path
import pytest
from allelio.database.store import AllelioDB
from allelio.runs import record_run, replay_run
from allelio.schema import validate_evidence

MAP = Path(__file__).resolve().parents[1] / 'data/probe-mappings/23andme-grch37-f2-v1.json'
CATALOGUE = Path(__file__).resolve().parents[1] / 'data/probe-mappings/23andme-grch37-f2-gba1-v1.json'


@pytest.mark.parametrize('genotype,recovered', [('AG', True), ('GG', True), ('AA', True), ('TG', False)])
def test_curated_f2_mapping_runs_and_replays(tmp_path, genotype, recovered):
    source = tmp_path / 'invented.txt'
    source.write_text('# Synthetic observation, not a participant sample\n'
                      '# Allelio product: 23andme-raw\n# build 37\n'
                      f'i3002432\t11\t46761055\t{genotype}\n'
                      'i999999999\t11\t46761055\tAG\n')
    database = tmp_path / 'reference.db'
    db = AllelioDB(str(database)); db.initialize()
    db.insert_clinvar_batch([dict(rsid='rs1799963', chromosome='11', position_vcf=46739505,
                                 assembly='GRCh38', ref_allele='G', alt_allele='A',
                                 allele_id='28349', gene='SYNTHETIC', clinical_significance='Pathogenic')])
    db.close()
    manifest, evidence, _ = record_run(source, database, probe_map=MAP)
    observation = evidence['inputs'][0]
    assert observation['rsid'] == ('rs1799963' if recovered else 'i3002432')
    assert observation['probe_recovery']['observed_genotype'] == genotype
    assert observation['probe_recovery']['original_probe'] == 'i3002432'
    assert evidence['inputs'][1]['rsid'] == 'i999999999'
    assert evidence['inputs'][1]['probe_recovery']['reason'] == 'probe_not_mapped'
    assert evidence['coverage']['accounted_rows'] == 2
    assert validate_evidence(evidence) == []
    assert replay_run(manifest, source, database, probe_map=MAP)[0]['annotation_replayed']
    _, default_evidence, _ = record_run(source, database)
    assert default_evidence['inputs'][0]['rsid'] == 'i3002432'
    if recovered:
        assert observation['probe_recovery']['identity']['position'] == 46761055
        assert observation['probe_recovery']['reference_anchor']['position'] == 46739505


def test_curated_gba1_mapping_selects_the_explicit_t_to_c_allele(tmp_path):
    source = tmp_path / 'invented.txt'
    source.write_text('# Synthetic observation, not a participant sample\n'
                      '# Allelio product: 23andme-raw\n# build 37\n'
                      'i4000415\t1\t155205634\tCT\n')
    database = tmp_path / 'reference.db'
    db = AllelioDB(str(database)); db.initialize()
    db.insert_clinvar_batch([
        dict(rsid='rs76763715', chromosome='1', position_vcf=155235843,
             assembly='GRCh38', ref_allele='T', alt_allele='C', allele_id='19329',
             gene='GBA1', clinical_significance='Pathogenic'),
        dict(rsid='rs76763715', chromosome='1', position_vcf=155235843,
             assembly='GRCh38', ref_allele='T', alt_allele='G', allele_id='47036',
             gene='GBA1', clinical_significance='not provided'),
    ])
    db.close()

    manifest, evidence, _ = record_run(source, database, probe_map=CATALOGUE)
    observation = evidence['inputs'][0]
    assert observation['rsid'] == 'rs76763715'
    assert observation['probe_recovery']['reference_anchor']['allele_id'] == '19329'
    assert evidence['findings'][0]['rsid'] == 'rs76763715'
    assert replay_run(manifest, source, database, probe_map=CATALOGUE)[0]['annotation_replayed']
