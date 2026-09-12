"""Public data release assembly requires complete, verified source chunks."""
import gzip
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from rebuild_gnomad_release import combine, digest, recover_sites, save_json
from build_gnomad_freq import OUTPUT_COLUMNS


def test_recover_only_public_rsid_column(tmp_path):
    source=tmp_path/'old.gz'
    with gzip.open(source,'wt') as f:
        f.write('## source\nrsid\tAF\nrs1\t.4\nrs2\t.3\nrs1\t.2\n')
    target=tmp_path/'sites'
    assert recover_sites(source,target)==2
    assert target.read_text()=='rs1\nrs2\n'


def chunk(tmp_path, chrom, config):
    file=tmp_path/(chrom+'.tsv.gz')
    with gzip.open(file,'wt') as f:
        f.write('## Format: 2\n'+'\t'.join(OUTPUT_COLUMNS)+'\n')
        f.write('\t'.join(['rs1',chrom[3:],'100','A','G']+['.']*10)+'\n')
    save_json(tmp_path/(chrom+'.complete.json'),dict(config=config,sha256=digest(file),rows=1))
    return file


def test_combine_validates_checkpoints_and_keeps_existing_output_on_failure(tmp_path):
    config=dict(version='4.1.1',legacy_sha256='a'*64,selected_sites=1)
    source=chunk(tmp_path,'chr1',config)
    output=tmp_path/'release.gz'
    assert combine(['chr1'],tmp_path,output,config)==(1,1)
    original=output.read_bytes()
    with source.open('ab') as f: f.write(b'corrupt')
    with pytest.raises(ValueError,match='checksum'):
        combine(['chr1'],tmp_path,output,config)
    assert output.read_bytes()==original


def test_missing_chromosome_prevents_release(tmp_path):
    config=dict(version='4.1.1',legacy_sha256='a'*64,selected_sites=1)
    chunk(tmp_path,'chr1',config)
    output=tmp_path/'release.gz'
    with pytest.raises(FileNotFoundError):
        combine(['chr1','chr2'],tmp_path,output,config)
    assert not output.exists()


def test_release_validator_checks_real_fixture_and_checksum(tmp_path):
    import shutil
    from validate_gnomad_release import validate
    source=Path(__file__).parent/'fixtures/example_gnomad.tsv.gz'
    artifact=tmp_path/'extract.tsv.gz'
    shutil.copyfile(source,artifact)
    with gzip.open(artifact,'rt') as f:
        rows=[line for line in f if line.startswith('rs') and not line.startswith('rsid')]
    sites={line.split('\t',1)[0] for line in rows}
    (tmp_path/'selected-rsids.txt').write_text('\n'.join(sorted(sites))+'\n')
    manifest=tmp_path/'manifest.json'
    save_json(manifest,dict(file=artifact.name,sha256=digest(artifact),rows=len(rows),
                            format=2,assembly="GRCh38",version="v4.1"))
    report=validate(manifest)
    assert report['errors']==[]
    assert report['rows']==len(rows)
    artifact.write_bytes(b'corrupt')
    assert validate(manifest)['errors']==['artifact checksum mismatch']
