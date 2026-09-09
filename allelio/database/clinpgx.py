"""ClinPGx (formerly PharmGKB) clinical annotations parser.

ClinPGx's clinical annotations bundle (``clinicalAnnotations.zip``) holds
``clinical_annotations.tsv`` (one row per variant–drug annotation with its
level of evidence) and ``clinical_ann_alleles.tsv`` (one row per genotype of
that variant with the annotation text for people who carry it). Allelio keeps
only annotations whose variant is a single rsID: star-allele haplotypes
(``CYP2D6*4``) need phased calls and copy-number data a consumer array does
not give, so they are out of scope on purpose.

License: CC BY-SA 4.0 with a no-selling clause. The file is fetched from
ClinPGx at setup, never redistributed by Allelio; the report credits ClinPGx
and PharmGKB with the file date.
"""

import csv
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Generator, Optional

ANNOTATIONS_FILE = "clinical_annotations.tsv"
ALLELES_FILE = "clinical_ann_alleles.tsv"

_RSID_RE = re.compile(r"^rs\d+$")
_CREATED_RE = re.compile(r"CREATED_(\d{4}-\d{2}-\d{2})\.txt")

# ClinPGx levels of evidence, best first. 1A/1B: variant–drug pair with
# guideline or FDA-label backing (1A) or strong replicated evidence (1B);
# 2A/2B: moderate evidence; 3: low evidence (single study or conflicting);
# 4: case report / in vitro. See https://www.clinpgx.org/page/clinAnnLevels.
LEVELS = ("1A", "1B", "2A", "2B", "3", "4")


def level_rank(level: Optional[str]) -> int:
    """Position of a level in LEVELS (0 = best); unknown levels sort last."""
    try:
        return LEVELS.index((level or "").strip().upper())
    except ValueError:
        return len(LEVELS)


def clinpgx_release_date(path: str) -> Optional[str]:
    """The date in the bundle's ``CREATED_YYYY-MM-DD.txt`` marker, or None.

    ``path`` may be the zip or the directory it was extracted into.
    """
    p = Path(path)
    names = []
    if p.is_dir():
        names = [f.name for f in p.iterdir()]
    elif p.is_file() and zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as zf:
            names = [Path(n).name for n in zf.namelist()]
    for name in names:
        m = _CREATED_RE.match(name)
        if m:
            return m.group(1)
    return None


def extract_bundle(zip_path: str, dest_dir: str) -> Path:
    """Unpack the two tables (and the CREATED marker) from the bundle."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            base = Path(name).name
            if base in (ANNOTATIONS_FILE, ALLELES_FILE) or _CREATED_RE.match(base) or base == "LICENSE.txt":
                with zf.open(name) as src, open(dest / base, "wb") as out:
                    out.write(src.read())
    return dest


def _reader(path: Path):
    f = open(path, "r", encoding="utf-8", errors="ignore", newline="")
    return f, csv.DictReader(f, delimiter="\t")


def parse_clinpgx(directory: str) -> Generator[Dict[str, Any], None, None]:
    """Yield one record per (single-rsID annotation, genotype).

    Keys: annotation_id, rsid, gene, level, score, phenotype_category, drugs,
    phenotypes, url, genotype, annotation_text, allele_function.
    Annotations whose variant is not exactly one rsID are skipped.
    """
    d = Path(directory)
    ann_f, ann = _reader(d / ANNOTATIONS_FILE)
    try:
        annotations: Dict[str, Dict[str, Any]] = {}
        for row in ann:
            variant = (row.get("Variant/Haplotypes") or "").strip()
            if not _RSID_RE.match(variant):
                continue
            aid = (row.get("Clinical Annotation ID") or "").strip()
            if not aid:
                continue
            annotations[aid] = {
                "annotation_id": aid,
                "rsid": variant,
                "gene": (row.get("Gene") or "").strip() or None,
                "level": (row.get("Level of Evidence") or "").strip().upper() or None,
                "score": _float(row.get("Score")),
                "phenotype_category": (row.get("Phenotype Category") or "").strip() or None,
                "drugs": (row.get("Drug(s)") or "").strip() or None,
                "phenotypes": (row.get("Phenotype(s)") or "").strip() or None,
                "url": (row.get("URL") or "").strip() or None,
            }
    finally:
        ann_f.close()

    if not annotations:
        return
    al_f, alleles = _reader(d / ALLELES_FILE)
    try:
        for row in alleles:
            aid = (row.get("Clinical Annotation ID") or "").strip()
            base = annotations.get(aid)
            if base is None:
                continue
            genotype = (row.get("Genotype/Allele") or "").strip().upper()
            if not genotype:
                continue
            yield {
                **base,
                "genotype": genotype,
                "annotation_text": (row.get("Annotation Text") or "").strip() or None,
                "allele_function": (row.get("Allele Function") or "").strip() or None,
            }
    finally:
        al_f.close()


def _float(value: Optional[str]) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None
