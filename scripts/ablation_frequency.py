#!/usr/bin/env python3
"""What the gnomAD frequency adjustment changes: the example, ranked both ways.

    python3 scripts/ablation_frequency.py            # fixture database (what CI sees)
    python3 scripts/ablation_frequency.py --real     # your full local database

Prints a Markdown table of every site the example reports under either
setting: the ClinVar classification, the gnomAD allele frequency, the rank
with the adjustment off (significance weighted by review stars only) and on
(the default), and where the site lands in each ordering. The table in the
paper is produced by this script against the fixture database, so a reader
can regenerate it from the repository alone. Author-chosen constants are
documented in allelio/analysis/lookup.py.
"""

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from allelio.analysis.example_check import EXAMPLE_FILE, build_fixture_db  # noqa: E402
from allelio.analysis.lookup import analyze_variants_with_stats  # noqa: E402
from allelio.database.store import AllelioDB  # noqa: E402
from allelio.parsers.base import parse_genotype_file  # noqa: E402


def ablation_rows(db, example_file: Path = EXAMPLE_FILE):
    """One dict per site reported under either setting, in adjusted order."""
    variants = parse_genotype_file(str(example_file))
    off, _ = analyze_variants_with_stats(variants, db, include_benign=True, frequency_adjustment=False)
    on, _ = analyze_variants_with_stats(variants, db, include_benign=True, frequency_adjustment=True)
    pos_off = {r.rsid: i + 1 for i, r in enumerate(off)}
    pos_on = {r.rsid: i + 1 for i, r in enumerate(on)}
    rank_off = {r.rsid: r.significance_rank for r in off}
    rows = []
    for r in on:
        cv = r.clinvar_entries[0] if r.clinvar_entries else None
        af = r.gnomad_entry.allele_frequency if r.gnomad_entry else None
        rows.append({
            "rsid": r.rsid,
            "gene": (cv.gene if cv and cv.gene else (r.gwas_entries[0].mapped_gene if r.gwas_entries else "")) or "",
            "classification": (cv.clinical_significance if cv else "GWAS association") or "",
            "af": af,
            "rank_off": rank_off.get(r.rsid),
            "rank_on": r.significance_rank,
            "pos_off": pos_off.get(r.rsid),
            "pos_on": pos_on[r.rsid],
            "shown_by_default": r.significance_rank < 8,
        })
    return rows


def render(rows) -> str:
    out = ["| rsID | Gene | ClinVar classification | gnomAD AF | Rank (no adjustment) | Rank (adjusted) | Position: no adj. → adj. | Shown by default |",
           "|---|---|---|---:|---:|---:|---|---|"]
    for r in rows:
        af = "—" if r["af"] is None else f"{r['af']:.3g}"
        cls = r["classification"]
        if len(cls) > 40:
            cls = cls[:37] + "…"
        moved = f"{r['pos_off']} → {r['pos_on']}" + ("" if r["pos_off"] == r["pos_on"] else " ↓" if r["pos_on"] > r["pos_off"] else " ↑")
        out.append(f"| {r['rsid']} | {r['gene']} | {cls} | {af} | {r['rank_off']:.1f} | {r['rank_on']:.1f} | {moved} | {'yes' if r['shown_by_default'] else 'no'} |")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="use ~/.allelio/data/allelio.db instead of the fixture excerpts")
    args = ap.parse_args()
    if args.real:
        db = AllelioDB()
        if not db.is_initialized():
            print("Database not initialised — run `allelio setup` first.")
            return 2
        print(f"Database: {db.describe_sources()}\n")
    else:
        db = build_fixture_db(str(Path(tempfile.mkdtemp()) / "ablation.db"))
        print("Database: fixture excerpts in tests/fixtures/ (same rows CI uses)\n")
    rows = ablation_rows(db)
    print(render(rows))
    hidden = [r["rsid"] for r in rows if not r["shown_by_default"] and r["rank_off"] is not None and r["rank_off"] < 8]
    print(f"\n{len(rows)} sites; the adjustment moved {sum(1 for r in rows if r['pos_off'] != r['pos_on'])} of them and "
          f"hid {len(hidden)} that would otherwise show by default: {', '.join(hidden) or 'none'}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
