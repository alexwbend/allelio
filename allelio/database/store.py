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
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        # Enable WAL mode for better concurrent read performance
        self.cursor.execute("PRAGMA journal_mode=WAL")
    
    def initialize(self) -> None:
        """Create tables and indexes."""
        # Create ClinVar table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS clinvar (
                rsid TEXT PRIMARY KEY,
                gene TEXT,
                clinical_significance TEXT,
                conditions TEXT,
                review_status TEXT,
                last_evaluated TEXT
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
                link TEXT
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
        
        self.conn.commit()
    
    def insert_clinvar_batch(self, records: List[Dict[str, Any]]) -> None:
        """Bulk insert ClinVar records.
        
        Args:
            records: List of dicts with keys: rsid, gene, clinical_significance, 
                    conditions, review_status, last_evaluated
        """
        if not records:
            return
        
        self.cursor.executemany(
            """INSERT OR REPLACE INTO clinvar 
               (rsid, gene, clinical_significance, conditions, review_status, last_evaluated)
               VALUES (:rsid, :gene, :clinical_significance, :conditions, :review_status, :last_evaluated)
            """,
            records
        )
        self.conn.commit()
    
    def insert_gwas_batch(self, records: List[Dict[str, Any]]) -> None:
        """Bulk insert GWAS records.
        
        Args:
            records: List of dicts with keys: rsid, trait, p_value, odds_ratio, 
                    mapped_gene, study, pubmed_id, link
        """
        if not records:
            return
        
        self.cursor.executemany(
            """INSERT INTO gwas 
               (rsid, trait, p_value, odds_ratio, mapped_gene, study, pubmed_id, link)
               VALUES (:rsid, :trait, :p_value, :odds_ratio, :mapped_gene, :study, :pubmed_id, :link)
            """,
            records
        )
        self.conn.commit()
    
    def lookup_rsid(self, rsid: str) -> Dict[str, Any]:
        """Look up combined ClinVar and GWAS data for a single rsID.
        
        Args:
            rsid: The rsID to look up (e.g., "rs123456")
        
        Returns:
            Dict with 'clinvar' (list of dicts) and 'gwas' (list of dicts) keys
        """
        result = {"clinvar": [], "gwas": []}
        
        # Query ClinVar
        self.cursor.execute("SELECT * FROM clinvar WHERE rsid = ?", (rsid,))
        clinvar_row = self.cursor.fetchone()
        if clinvar_row:
            result["clinvar"] = [dict(clinvar_row)]
        
        # Query GWAS
        self.cursor.execute("SELECT * FROM gwas WHERE rsid = ?", (rsid,))
        gwas_rows = self.cursor.fetchall()
        result["gwas"] = [dict(row) for row in gwas_rows]
        
        return result
    
    def lookup_rsids_batch(self, rsids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Batch lookup for multiple rsIDs.

        Args:
            rsids: List of rsIDs to look up

        Returns:
            Dict mapping rsid -> {clinvar: [...], gwas: [...]}
        """
        result = {}

        if not rsids:
            return result

        # Initialize result dict with all rsids
        for rsid in rsids:
            result[rsid] = {"clinvar": [], "gwas": []}

        # SQLite has a variable limit — process in chunks of 500
        chunk_size = 500
        for i in range(0, len(rsids), chunk_size):
            chunk = rsids[i:i + chunk_size]
            placeholders = ",".join("?" * len(chunk))

            # Query ClinVar
            query = f"SELECT * FROM clinvar WHERE rsid IN ({placeholders})"
            self.cursor.execute(query, chunk)
            for row in self.cursor.fetchall():
                rsid = row["rsid"]
                result[rsid]["clinvar"] = [dict(row)]

            # Query GWAS
            query = f"SELECT * FROM gwas WHERE rsid IN ({placeholders})"
            self.cursor.execute(query, chunk)
            for row in self.cursor.fetchall():
                rsid = row["rsid"]
                result[rsid]["gwas"].append(dict(row))

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
            "variant_count": clinvar_count + gwas_count,
            "gene_count": gene_count,
            "last_update": last_update,
            "db_path": str(self.db_path)
        }
    
    def is_initialized(self) -> bool:
        """Check whether the database has been set up with data.

        Returns:
            True if the clinvar table exists and contains at least one row.
        """
        try:
            self.cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='clinvar'"
            )
            if not self.cursor.fetchone():
                return False
            self.cursor.execute("SELECT COUNT(*) FROM clinvar")
            return self.cursor.fetchone()[0] > 0
        except Exception:
            return False

    def version(self) -> str:
        """Return a human-readable version/status string for the database.

        Returns:
            String describing the database version or last update time.
        """
        last_update = self.get_metadata("last_update") if self.get_metadata("last_update") else "unknown"
        return f"Updated: {last_update}"

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
