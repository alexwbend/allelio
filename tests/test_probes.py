import copy
import json
import pytest
from allelio.database.store import AllelioDB
from allelio.runs import record_run,replay_run


@pytest.fixture
def probe_case(tmp_path):
    source=tmp_path/'input.txt';source.write_text('# Allelio product: 23andme-raw\n# reference human assembly build 38\ni1\t1\t100\tAG\n')
    db=AllelioDB(str(tmp_path/'db'));db.initialize()
    db.insert_clinvar_batch([dict(rsid='rs1',chromosome='1',position_vcf=100,assembly='GRCh38',ref_allele='G',alt_allele='A',allele_id='1',gene='SYNTHETIC',clinical_significance='Pathogenic')]);db.close()
    mapping={'schema':'allelio-probes/1','source':'synthetic','version':'1','license':'MIT','source_url':'synthetic:fixture','product':'23andme-raw','assembly':'GRCh38','strand':'+','entries':[{'probe':'i1','rsid':'rs1','chromosome':'1','position':100,'ref':'G','alt':'A'}]}
    return source,tmp_path/'db',tmp_path/'mapping.json',mapping


def run(case):
    source,db,path,mapping=case;path.write_text(json.dumps(mapping))
    return record_run(source,db,probe_map=path)


def test_recovered_identity_and_replay(probe_case):
    manifest,evidence,_=run(probe_case)
    assert evidence['inputs'][0]['rsid']=='rs1'
    assert evidence['inputs'][0]['probe_recovery']['original_probe']=='i1'
    assert evidence['coverage']['probe_recovery_counts']=={'recovered':1}
    assert replay_run(manifest,*probe_case[:2],probe_map=probe_case[2])[0]['annotation_replayed']
    with pytest.raises(ValueError,match='mapping'): replay_run(manifest,*probe_case[:2])


@pytest.mark.parametrize('change,reason',[
    ('missing_build','missing_or_conflicting_product_build'),('conflicting_build','missing_or_conflicting_product_build'),
    ('product','missing_or_conflicting_product_build'),('coordinate','coordinate_mismatch'),
    ('allele','allele_mismatch'),('indel','unsupported_alleles'),('strand','strand_ambiguous'),
    ('conflict','conflicting_mapping'),('unmapped','probe_not_mapped'),('reference','reference_identity_unresolved')])
def test_abstentions(probe_case,change,reason):
    source,db,path,mapping=probe_case
    if change=='missing_build': source.write_text(source.read_text().replace('build 38','unknown'))
    if change=='conflicting_build': source.write_text('# build 37\n'+source.read_text())
    if change=='product': source.write_text(source.read_text().replace('23andme-raw','other'))
    if change=='coordinate': mapping['entries'][0]['position']=101
    if change=='allele': source.write_text(source.read_text().replace('AG','CC'))
    if change=='indel': mapping['entries'][0]['alt']='AT'
    if change=='strand': mapping['entries'][0].update(ref='A',alt='T')
    if change=='conflict': mapping['entries'].append(dict(mapping['entries'][0],rsid='rs2'))
    if change=='unmapped': mapping['entries']=[]
    if change=='reference': mapping['entries'][0]['rsid']='rs2'
    _,evidence,_=run(probe_case)
    assert evidence['inputs'][0]['probe_recovery']['reason']==reason
    assert evidence['inputs'][0]['rsid']=='i1' and not evidence['findings']
    assert evidence['coverage']['accounted_rows']==1


@pytest.mark.parametrize('genotype,expected',[('AG','duplicate_row'),('AA','conflicting_input')])
def test_recovered_and_native_duplicates_use_existing_conflict_rules(probe_case,genotype,expected):
    source=probe_case[0];source.write_text(source.read_text()+f'rs1\t1\t100\t{genotype}\n')
    _,evidence,_=run(probe_case)
    assert expected in evidence['coverage']['counts']
    assert evidence['coverage']['accounted_rows']==2
    if expected=='conflicting_input': assert not evidence['findings']


def test_provenance_required(probe_case):
    del probe_case[3]['license']
    with pytest.raises(ValueError,match='provenance'): run(probe_case)


def test_recovery_counts_are_validated(probe_case):
    from allelio.schema import validate_evidence
    _,evidence,_=run(probe_case)
    assert validate_evidence(evidence)==[]
    evidence['coverage']['probe_recovery_counts']['recovered']=5
    assert any('probe_recovery_counts' in error for error in validate_evidence(evidence))
