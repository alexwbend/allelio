"""The example file must produce exactly the findings it is documented to.

A database is built from the real ClinVar / GWAS Catalog / gnomAD rows for the
example's rsIDs (tests/fixtures/example_*, extracted by
scripts/build_example_fixtures.py) with the real parsers, the example is run
through the real analysis, and every expectation in
examples/expected_findings.json is checked: which sites are reported, with
which zygosity and category, and which are set aside and why. This is the
suite's recall test: a known pathogenic allele in the input must surface, and a
site where the person carries only the reference allele must not.
"""

from pathlib import Path

import pytest

from allelio.analysis.example_check import compare, load_expected
from allelio.database.clinvar import parse_clinvar
from allelio.database.gnomad import parse_gnomad
from allelio.database.gwas import parse_gwas
from allelio.database.store import AllelioDB

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def example_db(tmp_path_factory):
    db = AllelioDB(str(tmp_path_factory.mktemp("example") / "example.db"))
    db.initialize()
    db.insert_clinvar_batch(list(parse_clinvar(str(FIXTURES / "example_clinvar.tsv"))))
    db.insert_gwas_batch(list(parse_gwas(str(FIXTURES / "example_gwas.tsv"))))
    db.insert_gnomad_batch(list(parse_gnomad(str(FIXTURES / "example_gnomad.tsv.gz"))))
    return db


def test_fixture_database_is_populated(example_db):
    example_db.cursor.execute("SELECT COUNT(*) FROM clinvar")
    assert example_db.cursor.fetchone()[0] > 20
    example_db.cursor.execute("SELECT COUNT(*) FROM gwas WHERE risk_allele IS NOT NULL")
    assert example_db.cursor.fetchone()[0] > 0


def test_every_expectation_holds(example_db):
    rows = compare(example_db, load_expected())
    failures = [f"{name}: {detail}" for name, ok, detail in rows if not ok]
    assert not failures, "\n".join(failures)


def test_expectations_cover_every_line_of_the_example():
    ids = [
        line.split("\t")[0]
        for line in (Path(__file__).parent.parent / "examples" / "example_23andme.txt").read_text().splitlines()
        if line and not line.startswith("#")
    ]
    assert set(ids) == set(load_expected()["sites"])
