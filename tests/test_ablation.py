"""The frequency adjustment can be switched off, and the ablation is stable."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from allelio.analysis.example_check import build_fixture_db
from allelio.analysis.lookup import analyze_variants_with_stats
from allelio.parsers.base import Variant
from ablation_frequency import ablation_rows, render  # noqa: E402


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    return build_fixture_db(str(tmp_path_factory.mktemp("abl") / "a.db"))


def test_adjustment_off_leaves_base_rank(db):
    # rs429358: conflicting (6), 1 star, AF 0.16 → adjusted 9.0, base 5.9
    v = [Variant("rs429358", "19", 45411941, "TC")]
    [on] = analyze_variants_with_stats(v, db, include_benign=True)[0]
    [off] = analyze_variants_with_stats(v, db, include_benign=True, frequency_adjustment=False)[0]
    assert off.significance_rank < on.significance_rank
    assert off.significance_rank == pytest.approx(5.9)
    assert on.significance_rank == pytest.approx(8.9)


def test_ablation_table_is_deterministic_and_shows_the_hidden_sites(db):
    rows = ablation_rows(db)
    again = ablation_rows(db)
    assert rows == again
    by = {r["rsid"]: r for r in rows}
    # The two common conflicting variants are visible without the adjustment
    # and hidden with it — the effect the paper's table is there to show.
    for rsid in ("rs429358", "rs1799945"):
        assert by[rsid]["rank_off"] < 8 and not by[rsid]["shown_by_default"]
    # A rare pathogenic allele is untouched.
    assert by["rs28897696"]["rank_off"] == by["rs28897696"]["rank_on"]
    table = render(rows)
    assert table.startswith("| rsID |") and "rs429358" in table
