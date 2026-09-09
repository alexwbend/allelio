"""SQLite storage layer for Allelio reference databases."""

import sqlite3
import os
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime


class AllelioDB:
    """Manages SQLite database for ClinVar and GWAS data."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file. Defaults to ~/.allelio/data/allelio.db
        """
        if db_path is None:
            db_path = os.path.expanduser("~/.allelio/data/allelio.db")
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = None
        self.cursor = None
        self._connect()
    
    def _connect(self) -> None:
        """Establish database connection and enable WAL mode."""
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        # Enable WAL mode for better concurrent read performance
        self.cursor.execute("PRAGMA journal_mode=WAL")
    
    def _columns(self, table: str) -> List[str]:
        """Column names of ``table``, or [] if it does not exist."""
        try:
            self.cursor.execute(f"PRAGMA table_info({table})")
            return [row[1] for row in self.cursor.fetchall()]
        except Exception:
            return []

    def clinvar_is_allele_aware(self) -> bool:
        """True if the clinvar table carries ref/alt alleles (schema 2).

        Databases built before zygosity support keyed ClinVar by rsID alone,
        which silently kept one arbitrary row per rsID and could not say
        whether the user carries the annotated allele. Such a database has
        to be rebuilt (``allelio setup`` or ``allelio update``).
        """
        cols = self._columns("clinvar")
        return bool(cols) and "alt_allele" in cols

    def initialize(self) -> None:
        """Create tables and indexes, migrating an older schema where needed."""
        # A pre-allele-aware clinvar table cannot be upgraded in place: its rows
        # are one-per-rsID and the allele columns cannot be recovered. Drop it;
        # setup re-parses the ClinVar file it already has on disk.
        if self._columns("clinvar") and not self.clinvar_is_allele_aware():
            self.cursor.execute("DROP TABLE clinvar")

        # Create ClinVar table — one row per (rsID, ref, alt). ClinVar carries
        # several rows for one rsID when different alternate alleles at the
        # same site have different classifications (rs334: T>A is pathogenic
        # sickle-cell, T>G is likely benign), so the allele is part of the key.
        # Rows whose alleles ClinVar does not give (large indels, "na") store
        # empty strings and are matched without zygosity.
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS clinvar (
                rsid TEXT NOT NULL,
                ref_allele TEXT NOT NULL DEFAULT '',
                alt_allele TEXT NOT NULL DEFAULT '',
                gene TEXT,
                clinical_significance TEXT,
                conditions TEXT,
                review_status TEXT,
                last_evaluated TEXT,
                PRIMARY KEY (rsid, ref_allele, alt_allele)
            )
        """)
        
        # Create GWAS table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS gwas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rsid TEXT NOT NULL,
                trait TEXT,
                p_value REAL,
                odds_ratio TEXT,
                mapped_gene TEXT,
                study TEXT,
                pubmed_id TEXT,
                link TEXT,
                risk_allele TEXT
            )
        """)
        # Older gwas tables lack the risk allele; add the column (NULL until
        # the next update re-parses the catalogue).
        if "risk_allele" not in self._columns("gwas"):
            self.cursor.execute("ALTER TABLE gwas ADD COLUMN risk_allele TEXT")
        
        # Create gnomAD population frequency table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS gnomad (
                rsid TEXT PRIMARY KEY,
                allele_frequency REAL,
                af_popmax REAL,
                ac INTEGER,
                an INTEGER,
                nhomalt INTEGER,
                af_afr REAL,
                af_eas REAL,
                af_fin REAL,
                af_nfe REAL,
                af_sas REAL
            )
        """)

        # Create metadata table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        # Create indexes for better query performance
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_clinvar_rsid ON clinvar(rsid)
        """)
        
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_gwas_rsid ON gwas(rsid)
        """)

        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_gnomad_rsid ON gnomad(rsid)
        """)

        self.conn.commit()
    
    def insert_clinvar_batch(self, records: List[Dict[str, Any]]) -> None:
        """Bulk insert ClinVar records.
        
        Args:
            records: List of dicts with keys: rsid, gene, clinical_significance,
                    conditions, review_status, last_evaluated, and optionally
                    ref_allele / alt_allele (default '' = allele not recorded)
        """
        if not records:
            return

        rows = [
            {
                "ref_allele": (r.get("ref_allele") or ""),
                "alt_allele": (r.get("alt_allele") or ""),
                **{k: r.get(k) for k in ("rsid", "gene", "clinical_significance",
                                         "conditions", "review_status", "last_evaluated")},
            }
            for r in records
        ]
        self.cursor.executemany(
            """INSERT OR REPLACE INTO clinvar
               (rsid, ref_allele, alt_allele, gene, clinical_significance, conditions, review_status, last_evaluated)
               VALUES (:rsid, :ref_allele, :alt_allele, :gene, :clinical_significance, :conditions, :review_status, :last_evaluated)
            """,
            rows
        )
        self.conn.commit()
    
    def insert_gwas_batch(self, records: List[Dict[str, Any]]) -> None:
        """Bulk insert GWAS records.
        
        Args:
            records: List of dicts with keys: rsid, trait, p_value, odds_ratio,
                    mapped_gene, study, pubmed_id, link, and optionally risk_allele
        """
        if not records:
            return

        rows = [{"risk_allele": r.get("risk_allele"), **r} for r in records]
        self.cursor.executemany(
            """INSERT INTO gwas
               (rsid, trait, p_value, odds_ratio, mapped_gene, study, pubmed_id, link, risk_allele)
               VALUES (:rsid, :trait, :p_value, :odds_ratio, :mapped_gene, :study, :pubmed_id, :link, :risk_allele)
            """,
            rows
        )
        self.conn.commit()
    
    def insert_gnomad_batch(self, records: List[Dict[str, Any]]) -> None:
        """Bulk insert gnomAD population frequency records.

        Args:
            records: List of dicts with keys: rsid, allele_frequency, af_popmax,
                    ac, an, nhomalt, af_afr, af_eas, af_fin, af_nfe, af_sas
        """
        if not records:
            return

        self.cursor.executemany(
            """INSERT OR REPLACE INTO gnomad
               (rsid, allele_frequency, af_popmax, ac, an, nhomalt,
                af_afr, af_eas, af_fin, af_nfe, af_sas)
               VALUES (:rsid, :allele_frequency, :af_popmax, :ac, :an, :nhomalt,
                        :af_afr, :af_eas, :af_fin, :af_nfe, :af_sas)
            """,
            records
        )
        self.conn.commit()

    def clear_gwas(self) -> None:
        """Empty the gwas table before a re-index.

        GWAS rows are plain inserts (one rsID has many associations, so there
        is no natural key to replace on). Without this, every setup or update
        appended a second copy of the whole catalogue on top of the first.
        """
        self.cursor.execute("DELETE FROM gwas")
        self.conn.commit()

    def _has_gnomad_table(self) -> bool:
        """Check whether the gnomad table exists (backward compatibility)."""
        try:
            self.cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='gnomad'"
            )
            return self.cursor.fetchone() is not None
        except Exception:
            return False

    def lookup_rsid(self, rsid: str) -> Dict[str, Any]:
        """Look up combined ClinVar, GWAS, and gnomAD data for a single rsID.

        Args:
            rsid: The rsID to look up (e.g., "rs123456")

        Returns:
            Dict with 'clinvar' (list of dicts), 'gwas' (list of dicts),
            and 'gnomad' (dict or None) keys
        """
        result = {"clinvar": [], "gwas": [], "gnomad": None}

        # Query ClinVar — every allele row for the rsID, in a stable order
        order = " ORDER BY ref_allele, alt_allele" if self.clinvar_is_allele_aware() else ""
        self.cursor.execute(f"SELECT * FROM clinvar WHERE rsid = ?{order}", (rsid,))
        result["clinvar"] = [dict(row) for row in self.cursor.fetchall()]

        # Query GWAS
        self.cursor.execute("SELECT * FROM gwas WHERE rsid = ?", (rsid,))
        gwas_rows = self.cursor.fetchall()
        result["gwas"] = [dict(row) for row in gwas_rows]

        # Query gnomAD (backward compatible — table may not exist)
        if self._has_gnomad_table():
            self.cursor.execute("SELECT * FROM gnomad WHERE rsid = ?", (rsid,))
            gnomad_row = self.cursor.fetchone()
            if gnomad_row:
                result["gnomad"] = dict(gnomad_row)

        return result
    
    def lookup_rsids_batch(self, rsids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Batch lookup for multiple rsIDs.

        Args:
            rsids: List of rsIDs to look up

        Returns:
            Dict mapping rsid -> {clinvar: [...], gwas: [...], gnomad: dict|None}
        """
        result = {}

        if not rsids:
            return result

        has_gnomad = self._has_gnomad_table()
        clinvar_order = (
            " ORDER BY rsid, ref_allele, alt_allele" if self.clinvar_is_allele_aware() else ""
        )

        # Initialize result dict with all rsids
        for rsid in rsids:
            result[rsid] = {"clinvar": [], "gwas": [], "gnomad": None}

        # SQLite has a variable limit — process in chunks of 500
        chunk_size = 500
        for i in range(0, len(rsids), chunk_size):
            chunk = rsids[i:i + chunk_size]
            placeholders = ",".join("?" * len(chunk))

            # Query ClinVar — one row per annotated allele
            query = f"SELECT * FROM clinvar WHERE rsid IN ({placeholders}){clinvar_order}"
            self.cursor.execute(query, chunk)
            for row in self.cursor.fetchall():
                rsid = row["rsid"]
                result[rsid]["clinvar"].append(dict(row))

            # Query GWAS
            query = f"SELECT * FROM gwas WHERE rsid IN ({placeholders})"
            self.cursor.execute(query, chunk)
            for row in self.cursor.fetchall():
                rsid = row["rsid"]
                result[rsid]["gwas"].append(dict(row))

            # Query gnomAD (backward compatible)
            if has_gnomad:
                query = f"SELECT * FROM gnomad WHERE rsid IN ({placeholders})"
                self.cursor.execute(query, chunk)
                for row in self.cursor.fetchall():
                    rsid = row["rsid"]
                    result[rsid]["gnomad"] = dict(row)

        return result
    
    def set_metadata(self, key: str, value: str) -> None:
        """Set metadata key-value pair.
        
        Args:
            key: Metadata key
            value: Metadata value
        """
        self.cursor.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (key, value)
        )
        self.conn.commit()
    
    def get_metadata(self, key: str) -> Optional[str]:
        """Get metadata value by key.
        
        Args:
            key: Metadata key
        
        Returns:
            Metadata value or None if not found
        """
        self.cursor.execute("SELECT value FROM metadata WHERE key = ?", (key,))
        row = self.cursor.fetchone()
        return row[0] if row else None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics.

        Returns:
            Dict with counts and metadata
        """
        # Get counts
        self.cursor.execute("SELECT COUNT(*) FROM clinvar")
        clinvar_count = self.cursor.fetchone()[0]

        self.cursor.execute("SELECT COUNT(*) FROM gwas")
        gwas_count = self.cursor.fetchone()[0]

        # Get gnomAD count (backward compatible)
        gnomad_count = 0
        if self._has_gnomad_table():
            try:
                self.cursor.execute("SELECT COUNT(*) FROM gnomad")
                gnomad_count = self.cursor.fetchone()[0]
            except Exception:
                pass

        # Count distinct genes across both tables
        gene_count = 0
        try:
            self.cursor.execute(
                "SELECT COUNT(DISTINCT gene) FROM clinvar WHERE gene IS NOT NULL AND gene != ''"
            )
            gene_count = self.cursor.fetchone()[0]
        except Exception:
            pass

        # Get last update time
        last_update = self.get_metadata("last_update")

        return {
            "clinvar_entries": clinvar_count,
            "gwas_entries": gwas_count,
            "gnomad_entries": gnomad_count,
            "variant_count": clinvar_count + gwas_count,
            "gene_count": gene_count,
            "last_update": last_update,
            "provenance": self.get_provenance(),
            "db_path": str(self.db_path)
        }
    
    def is_initialized(self) -> bool:
        """Check whether the database has been set up with data.

        Returns:
            True if the clinvar table exists in the current (allele-aware)
            schema and contains at least one row. A database built before
            zygosity support reports False so the CLI and web UI point the
            user at ``allelio setup``.
        """
        try:
            if not self.clinvar_is_allele_aware():
                return False
            self.cursor.execute("SELECT COUNT(*) FROM clinvar")
            return self.cursor.fetchone()[0] > 0
        except Exception:
            return False

    # Reference sources whose provenance is recorded at setup, in display order.
    SOURCES = (
        ("clinvar", "ClinVar"),
        ("gwas", "GWAS Catalog"),
        ("gnomad", "gnomAD"),
    )

    def get_provenance(self) -> Dict[str, Dict[str, Optional[str]]]:
        """Return which release of each reference source this database holds.

        Each source maps to a dict with ``label``, ``release`` (a YYYY-MM-DD
        date for the rolling ClinVar/GWAS releases, a version tag such as
        ``v4.1.1`` for gnomAD, ``unavailable`` when the source was not loaded,
        or ``unknown``), ``release_source`` (how the date was learned:
        ``http-last-modified`` from the server, ``file-mtime`` inferred from a
        file already on disk, or None), ``url`` and ``sha256`` of the exact
        file. Any key the metadata table does not carry is None, so callers
        can render "unknown" rather than guess.
        """
        prov: Dict[str, Dict[str, Optional[str]]] = {}
        for key, label in self.SOURCES:
            release = self.get_metadata(f"{key}_release")
            if release is None:
                # Databases built before release dates were recorded stored
                # the literal "latest" here; that is not a release, so say so.
                legacy = self.get_metadata(f"{key}_version")
                release = None if legacy in (None, "latest") else legacy
            prov[key] = {
                "label": label,
                "release": release,
                "release_source": self.get_metadata(f"{key}_release_source"),
                "url": self.get_metadata(f"{key}_url"),
                "sha256": self.get_metadata(f"{key}_sha256"),
            }
        return prov

    def describe_sources(self) -> str:
        """One line naming the release of every loaded source.

        Example: ``ClinVar 2026-09-06 · GWAS Catalog 2026-09-04 · gnomAD v4.1.1``.
        A source that was not loaded is omitted; one whose release is unknown
        reads ``unknown``.
        """
        parts = []
        for key, info in self.get_provenance().items():
            release = info.get("release")
            if release == "unavailable":
                continue
            parts.append(f"{info['label']} {release or 'unknown'}")
        return " · ".join(parts) if parts else "no reference data loaded"

    def version(self) -> str:
        """Return a human-readable version/status string for the database.

        Names the release of each reference source and when the database was
        built, so a report can say exactly what it was computed against.

        Returns:
            String such as ``ClinVar 2026-09-06 · GWAS Catalog 2026-09-04 ·
            gnomAD v4.1.1 (built 2026-09-09)``.
        """
        last_update = self.get_metadata("last_update")
        built = f" (built {last_update[:10]})" if last_update else ""
        return f"{self.describe_sources()}{built}"

    def days_since_update(self) -> Optional[float]:
        """Return the number of days since the last database update.

        Reads the ``last_update`` metadata timestamp (an ISO-8601 string set by
        ``setup_database``) and returns how many days ago that was. Returns None
        if the timestamp is missing or unparseable, so callers can distinguish
        "unknown" from "fresh".

        Returns:
            Age of the local data in days, or None if unknown.
        """
        last_update = self.get_metadata("last_update")
        if not last_update:
            return None
        try:
            updated_at = datetime.fromisoformat(last_update)
        except (ValueError, TypeError):
            return None
        delta = datetime.now() - updated_at
        return delta.total_seconds() / 86400.0

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
