"""Shared test fixtures for Allelio."""

import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Generator
import sqlite3

from allelio.database.store import AllelioDB


@pytest.fixture
def tmp_dir() -> Generator[str, None, None]:
    """Create a temporary directory for test files.
    
    Yields:
        Path to temporary directory
        
    Cleans up after the test completes.
    """
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def sample_23andme_file(tmp_dir) -> str:
    """Create a synthetic 23andMe format file with real-looking variants.
    
    Args:
        tmp_dir: Temporary directory fixture
        
    Returns:
        Path to the synthetic 23andMe file
    """
    file_path = Path(tmp_dir) / "sample_23andme.txt"
    
    # 23andMe format: rsid, chromosome, position, genotype
    # Real rsIDs used for testing
    content = """# This is a test 23andMe file
# Generated for testing purposes
# Format: RSID\tCHROMOSOME\tPOSITION\tGENOTYPE
rs1234\t1\t100000\tAA
rs429358\t19\t45411941\tCT
rs7412\t19\t45412079\tTC
rs12913832\t15\t28000000\tGG
rs1805007\t16\t89919949\tAA
rs4988235\t2\t135951944\tCC
rs762551\t11\t62326389\tAA
rs1800497\t11\t647902\tAA
rs6311\t13\t47401470\tGG
rs1042713\t5\t148827325\tGG
rs1042714\t5\t148828133\tCC
rs2229991\t8\t42408344\tTT
rs4819132\t10\t123256215\tAG
rs3918290\t10\t123256314\t--
rs1805008\t16\t89919977\t--
rs1052373\t11\t116648917\tAA
rs7594645\t15\t28000001\tCG
rs4680\t22\t19963669\tGG
rs1799836\t11\t62327395\tCC
rs1800795\t7\t22766320\tGG
"""
    
    file_path.write_text(content)
    return str(file_path)


@pytest.fixture
def sample_ancestry_file(tmp_dir) -> str:
    """Create a synthetic AncestryDNA format file.
    
    AncestryDNA format: rsid, chromosome, position, allele1, allele2
    
    Args:
        tmp_dir: Temporary directory fixture
        
    Returns:
        Path to the synthetic AncestryDNA file
    """
    file_path = Path(tmp_dir) / "sample_ancestry.txt"
    
    content = """rsid\tchromosome\tposition\tallele1\tallele2
rs1234\t1\t100000\tA\tA
rs429358\t19\t45411941\tC\tT
rs7412\t19\t45412079\tT\tC
rs12913832\t15\t28000000\tG\tG
rs1805007\t16\t89919949\tA\tA
rs4988235\t2\t135951944\tC\tC
rs762551\t11\t62326389\tA\tA
rs1800497\t11\t647902\tA\tA
rs6311\t13\t47401470\tG\tG
rs1042713\t5\t148827325\tG\tG
rs1042714\t5\t148828133\tC\tC
rs2229991\t8\t42408344\tT\tT
rs4819132\t10\t123256215\tA\tG
rs3918290\t10\t123256314\t0\t0
rs1805008\t16\t89919977\t0\t0
rs1052373\t11\t116648917\tA\tA
rs7594645\t15\t28000001\tC\tG
rs4680\t22\t19963669\tG\tG
rs1799836\t11\t62327395\tC\tC
rs1800795\t7\t22766320\tG\tG
"""
    
    file_path.write_text(content)
    return str(file_path)


@pytest.fixture
def sample_vcf_file(tmp_dir) -> str:
    """Create a minimal VCF format file.
    
    Args:
        tmp_dir: Temporary directory fixture
        
    Returns:
        Path to the synthetic VCF file
    """
    file_path = Path(tmp_dir) / "sample.vcf"
    
    content = """##fileformat=VCFv4.1
##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">
##contig=<ID=1>
##contig=<ID=19>
##contig=<ID=15>
##contig=<ID=16>
##contig=<ID=2>
##contig=<ID=11>
##contig=<ID=13>
##contig=<ID=5>
##contig=<ID=10>
##contig=<ID=22>
##contig=<ID=7>
#CHROM	POS	ID	REF	ALT	QUAL	FILTER	INFO	FORMAT	SAMPLE
1	100000	rs1234	A	G	60	PASS	.	GT	0/0
19	45411941	rs429358	C	T	60	PASS	.	GT	0/1
19	45412079	rs7412	T	C	60	PASS	.	GT	0/1
15	28000000	rs12913832	G	A	60	PASS	.	GT	0/0
16	89919949	rs1805007	A	G	60	PASS	.	GT	0/0
2	135951944	rs4988235	C	T	60	PASS	.	GT	0/0
11	62326389	rs762551	A	G	60	PASS	.	GT	0/0
11	647902	rs1800497	A	G	60	PASS	.	GT	0/0
13	47401470	rs6311	G	A	60	PASS	.	GT	0/0
5	148827325	rs1042713	G	A	60	PASS	.	GT	0/0
"""
    
    file_path.write_text(content)
    return str(file_path)


@pytest.fixture
def sample_db(tmp_dir) -> AllelioDB:
    """Create a temporary AllelioDB with test data pre-loaded.
    
    Includes:
    - ClinVar entries for variants with real rsIDs
    - GWAS entries for traits associated with sample variants
    
    Args:
        tmp_dir: Temporary directory fixture
        
    Returns:
        Initialized AllelioDB instance with test data
    """
    db_path = str(Path(tmp_dir) / "test_allelio.db")
    db = AllelioDB(db_path=db_path)
    db.initialize()
    
    # Insert ClinVar entries matching sample variant rsIDs
    clinvar_records = [
        {
            "rsid": "rs429358",
            "gene": "APOE",
            "clinical_significance": "risk factor",
            "conditions": "Alzheimer disease",
            "review_status": "criteria provided, single submitter",
            "last_evaluated": "2020-01-01"
        },
        {
            "rsid": "rs7412",
            "gene": "APOE",
            "clinical_significance": "risk factor",
            "conditions": "Alzheimer disease",
            "review_status": "criteria provided, single submitter",
            "last_evaluated": "2020-01-01"
        },
        {
            "rsid": "rs12913832",
            "gene": "OCA2",
            "clinical_significance": "benign",
            "conditions": "Eye color",
            "review_status": "benign",
            "last_evaluated": "2019-01-01"
        },
        {
            "rsid": "rs4988235",
            "gene": "MCM6",
            "clinical_significance": "association",
            "conditions": "Lactose intolerance",
            "review_status": "criteria provided, single submitter",
            "last_evaluated": "2018-01-01"
        },
        {
            "rsid": "rs762551",
            "gene": "CYP1A2",
            "clinical_significance": "pathogenic",
            "conditions": "Caffeine sensitivity",
            "review_status": "criteria provided, multiple submitters",
            "last_evaluated": "2021-01-01"
        },
    ]
    
    db.insert_clinvar_batch(clinvar_records)
    
    # Insert GWAS entries
    gwas_records = [
        {
            "rsid": "rs429358",
            "trait": "Alzheimer's disease",
            "p_value": 5.3e-47,
            "odds_ratio": "1.73",
            "mapped_gene": "APOE",
            "study": "Jansen et al. 2019",
            "pubmed_id": "30617256",
            "link": "https://pubmed.ncbi.nlm.nih.gov/30617256"
        },
        {
            "rsid": "rs7412",
            "trait": "Cognitive decline",
            "p_value": 3.2e-15,
            "odds_ratio": "1.35",
            "mapped_gene": "APOE",
            "study": "Davies et al. 2018",
            "pubmed_id": "29618526",
            "link": "https://pubmed.ncbi.nlm.nih.gov/29618526"
        },
        {
            "rsid": "rs4988235",
            "trait": "Lactose intolerance",
            "p_value": 2.1e-100,
            "odds_ratio": "2.1",
            "mapped_gene": "MCM6",
            "study": "Itan et al. 2010",
            "pubmed_id": "20418890",
            "link": "https://pubmed.ncbi.nlm.nih.gov/20418890"
        },
        {
            "rsid": "rs1052373",
            "trait": "Caffeine metabolism",
            "p_value": 1.5e-20,
            "odds_ratio": "1.5",
            "mapped_gene": "CYP1A2",
            "study": "Cornelis et al. 2011",
            "pubmed_id": "21217178",
            "link": "https://pubmed.ncbi.nlm.nih.gov/21217178"
        },
        {
            "rsid": "rs1234",
            "trait": "General trait",
            "p_value": 1e-5,
            "odds_ratio": "1.1",
            "mapped_gene": "GENE1",
            "study": "Test Study",
            "pubmed_id": "12345678",
            "link": ""
        },
    ]
    
    db.insert_gwas_batch(gwas_records)
    
    return db
