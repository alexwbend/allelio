"""Rebuild deliberately synthetic evaluation cases, separate from prompt fixtures.

Run from the repository root with Allelio installed. Changes to frozen cases
must be reviewed as dataset revisions, not silently regenerated for scoring.
"""
import json
import tempfile
from pathlib import Path
from allelio.database.store import AllelioDB
from allelio.runs import record_run
from allelio.evidence import write_evidence_export

output=Path(__file__).parent
with tempfile.TemporaryDirectory() as work:
    work=Path(work);source=work/'synthetic.txt'
    source.write_text('rs99001\t1\t123\tAG\nrs99002\t2\t456\tCT\n')
    db=AllelioDB(str(work/'refs.db'));db.initialize()
    db.insert_clinvar_batch([
        dict(rsid='rs99001',ref_allele='G',alt_allele='A',chromosome='1',position_vcf=123,assembly='GRCh38',allele_id='1',gene='EVALUATION_A',conditions='Invented condition A',clinical_significance='Pathogenic'),
        dict(rsid='rs99002',ref_allele='C',alt_allele='T',chromosome='2',position_vcf=456,assembly='GRCh38',allele_id='2',gene='EVALUATION_B',conditions='Invented condition B',clinical_significance='Uncertain significance')])
    db.set_metadata('clinvar_release','synthetic-evaluation/1');db.close()
    manifest,evidence,_=record_run(source,work/'refs.db')
    write_evidence_export(manifest,output/'run.json');write_evidence_export(evidence,output/'evidence.json')
    cases=[{'id':'evaluation-'+str(i+1),'evidence':'evidence.json','run_manifest':'run.json','finding_id':row['finding_id']} for i,row in enumerate(evidence['findings'])]
    write_evidence_export({'schema':'allelio-evaluation/1','split':'evaluation','data_kind':'synthetic','reuse_rights':'MIT; invented by Allelio contributors, no patient or external source material','cases':cases},output/'bundle.json')
