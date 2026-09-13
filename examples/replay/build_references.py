"""Create only synthetic references for the offline replay demonstration."""
import argparse
from pathlib import Path
from allelio.database.store import AllelioDB

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('database')
args = parser.parse_args()
if Path(args.database).exists():
    parser.error('destination already exists; use a new database path')
with AllelioDB(args.database) as db:
    db.initialize()
    db.insert_clinvar_batch([dict(rsid='rs1', chromosome='1', position_vcf=100,
        assembly='GRCh38', ref_allele='G', alt_allele='A', allele_id='1',
        gene='SYNTHETIC', conditions='Invented demonstration condition',
        clinical_significance='Pathogenic', condition_ids='MONDO:0000001')])
    db.set_metadata('clinvar_release', 'synthetic-replay/1')
