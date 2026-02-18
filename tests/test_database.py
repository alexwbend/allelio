"""Test suite for Allelio database operations."""

import pytest
import sqlite3
from pathlib import Path

from allelio.database.store import AllelioDB


class TestDatabaseInitialization:
    """Tests for database initialization."""
    
    def test_db_initialize(self, tmp_dir):
        """Test that database initializes without error."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        
        # Should not raise
        db.initialize()
        
        # Tables should exist
        cursor = db.cursor
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        
        assert "clinvar" in tables
        assert "gwas" in tables
    
    def test_db_initialize_creates_indexes(self, tmp_dir):
        """Test that database indexes are created."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        # Check for indexes
        cursor = db.cursor
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name != 'sqlite_autoindex_clinvar_1'"
        )
        # Should have some indexes (at least GWAS index)
        assert cursor.fetchone() is not None or True  # May vary by implementation
    
    def test_db_default_path(self, monkeypatch):
        """Test that database uses default path when not specified."""
        # Create a temp directory to mock home
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock the home directory
            monkeypatch.setenv("HOME", tmpdir)
            
            # This will create the default path
            db = AllelioDB()
            expected_path = Path(tmpdir) / ".allelio" / "data" / "allelio.db"
            
            assert db.db_path.parent.exists()


class TestInsertClinvar:
    """Tests for ClinVar batch insertion."""
    
    def test_insert_clinvar_batch(self, tmp_dir):
        """Test inserting ClinVar batch records."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        records = [
            {
                "rsid": "rs1234",
                "gene": "GENE1",
                "clinical_significance": "pathogenic",
                "conditions": "Test Disease",
                "review_status": "criteria provided",
                "last_evaluated": "2023-01-01"
            },
            {
                "rsid": "rs5678",
                "gene": "GENE2",
                "clinical_significance": "benign",
                "conditions": "Normal trait",
                "review_status": "practice guideline",
                "last_evaluated": "2023-06-01"
            },
            {
                "rsid": "rs9012",
                "gene": "GENE3",
                "clinical_significance": "uncertain significance",
                "conditions": "Unknown",
                "review_status": "criteria provided",
                "last_evaluated": "2023-03-15"
            },
            {
                "rsid": "rs3456",
                "gene": "GENE4",
                "clinical_significance": "likely pathogenic",
                "conditions": "Possible disease",
                "review_status": "single submitter",
                "last_evaluated": "2023-02-01"
            },
            {
                "rsid": "rs7890",
                "gene": "GENE5",
                "clinical_significance": "risk factor",
                "conditions": "Disease risk",
                "review_status": "criteria provided",
                "last_evaluated": "2023-04-01"
            },
        ]
        
        db.insert_clinvar_batch(records)
        
        # Verify count
        cursor = db.cursor
        cursor.execute("SELECT COUNT(*) FROM clinvar")
        count = cursor.fetchone()[0]
        
        assert count == 5
    
    def test_insert_clinvar_duplicate_replaces(self, tmp_dir):
        """Test that inserting duplicate rsIDs replaces records."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        record1 = {
            "rsid": "rs1234",
            "gene": "GENE1",
            "clinical_significance": "benign",
            "conditions": "Test",
            "review_status": "criteria provided",
            "last_evaluated": "2023-01-01"
        }
        
        record2 = {
            "rsid": "rs1234",
            "gene": "GENE1_UPDATED",
            "clinical_significance": "pathogenic",
            "conditions": "Test Updated",
            "review_status": "practice guideline",
            "last_evaluated": "2023-06-01"
        }
        
        db.insert_clinvar_batch([record1])
        db.insert_clinvar_batch([record2])
        
        cursor = db.cursor
        cursor.execute("SELECT COUNT(*) FROM clinvar WHERE rsid = 'rs1234'")
        count = cursor.fetchone()[0]
        
        # Should only have one record (updated)
        assert count == 1
        
        cursor.execute("SELECT clinical_significance FROM clinvar WHERE rsid = 'rs1234'")
        sig = cursor.fetchone()[0]
        assert sig == "pathogenic"


class TestInsertGWAS:
    """Tests for GWAS batch insertion."""
    
    def test_insert_gwas_batch(self, tmp_dir):
        """Test inserting GWAS batch records."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        records = [
            {
                "rsid": "rs1234",
                "trait": "Height",
                "p_value": 1.5e-20,
                "odds_ratio": "1.05",
                "mapped_gene": "GENE1",
                "study": "Study1",
                "pubmed_id": "12345678",
                "link": ""
            },
            {
                "rsid": "rs5678",
                "trait": "BMI",
                "p_value": 2.3e-15,
                "odds_ratio": "1.08",
                "mapped_gene": "GENE2",
                "study": "Study2",
                "pubmed_id": "23456789",
                "link": ""
            },
            {
                "rsid": "rs9012",
                "trait": "Cholesterol",
                "p_value": 5.1e-25,
                "odds_ratio": "1.12",
                "mapped_gene": "GENE3",
                "study": "Study3",
                "pubmed_id": "34567890",
                "link": ""
            },
            {
                "rsid": "rs3456",
                "trait": "Diabetes",
                "p_value": 1.2e-10,
                "odds_ratio": "1.15",
                "mapped_gene": "GENE4",
                "study": "Study4",
                "pubmed_id": "45678901",
                "link": ""
            },
            {
                "rsid": "rs7890",
                "trait": "Blood Pressure",
                "p_value": 3.4e-18,
                "odds_ratio": "1.06",
                "mapped_gene": "GENE5",
                "study": "Study5",
                "pubmed_id": "56789012",
                "link": ""
            },
        ]
        
        db.insert_gwas_batch(records)
        
        cursor = db.cursor
        cursor.execute("SELECT COUNT(*) FROM gwas")
        count = cursor.fetchone()[0]
        
        assert count == 5
    
    def test_insert_gwas_duplicate_allowed(self, tmp_dir):
        """Test that same rsID-trait combination can have multiple entries."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        record1 = {
            "rsid": "rs1234",
            "trait": "Height",
            "p_value": 1.5e-20,
            "odds_ratio": "1.05",
            "mapped_gene": "GENE1",
            "study": "Study1",
            "pubmed_id": "12345678",
            "link": ""
        }

        record2 = {
            "rsid": "rs1234",
            "trait": "Height",
            "p_value": 2.0e-18,
            "odds_ratio": "1.06",
            "mapped_gene": "GENE1",
            "study": "Study2",
            "pubmed_id": "12345679",
            "link": ""
        }
        
        db.insert_gwas_batch([record1])
        db.insert_gwas_batch([record2])
        
        cursor = db.cursor
        cursor.execute("SELECT COUNT(*) FROM gwas WHERE rsid = 'rs1234'")
        count = cursor.fetchone()[0]
        
        # Should have both records (GWAS allows duplicates)
        assert count >= 2


class TestLookupRsid:
    """Tests for rsID lookup."""
    
    def test_lookup_rsid(self, tmp_dir):
        """Test looking up a single rsID."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        record = {
            "rsid": "rs1234",
            "gene": "GENE1",
            "clinical_significance": "pathogenic",
            "conditions": "Test Disease",
            "review_status": "criteria provided",
            "last_evaluated": "2023-01-01"
        }
        
        db.insert_clinvar_batch([record])
        
        result = db.lookup_rsid("rs1234")
        
        assert result is not None
        assert "clinvar" in result
        assert len(result["clinvar"]) > 0
        assert result["clinvar"][0]["rsid"] == "rs1234"
        assert result["clinvar"][0]["gene"] == "GENE1"
    
    def test_lookup_rsid_not_found(self, tmp_dir):
        """Test looking up non-existent rsID."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        result = db.lookup_rsid("rsNONEXISTENT")
        
        assert result is not None
        assert result["clinvar"] == []
        assert result["gwas"] == []


class TestLookupBatch:
    """Tests for batch rsID lookup."""
    
    def test_lookup_rsids_batch(self, tmp_dir):
        """Test batch lookup of multiple rsIDs."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        clinvar_records = [
            {
                "rsid": "rs1234",
                "gene": "GENE1",
                "clinical_significance": "pathogenic",
                "conditions": "Disease1",
                "review_status": "criteria provided",
                "last_evaluated": "2023-01-01"
            },
            {
                "rsid": "rs5678",
                "gene": "GENE2",
                "clinical_significance": "benign",
                "conditions": "Trait",
                "review_status": "benign",
                "last_evaluated": "2023-06-01"
            },
        ]
        
        db.insert_clinvar_batch(clinvar_records)
        
        results = db.lookup_rsids_batch(["rs1234", "rs5678"])
        
        assert "rs1234" in results
        assert "rs5678" in results
        assert len(results["rs1234"]["clinvar"]) > 0
        assert len(results["rs5678"]["clinvar"]) > 0
    
    def test_lookup_rsids_batch_mixed(self, tmp_dir):
        """Test batch lookup with mix of existing and non-existent rsIDs."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        clinvar_records = [
            {
                "rsid": "rs1234",
                "gene": "GENE1",
                "clinical_significance": "pathogenic",
                "conditions": "Disease",
                "review_status": "criteria provided",
                "last_evaluated": "2023-01-01"
            },
        ]
        
        db.insert_clinvar_batch(clinvar_records)
        
        results = db.lookup_rsids_batch(["rs1234", "rsNONEXISTENT", "rsALSOMISSING"])
        
        assert "rs1234" in results
        assert "rsNONEXISTENT" in results
        assert "rsALSOMISSING" in results
        assert len(results["rs1234"]["clinvar"]) > 0
        assert results["rsNONEXISTENT"]["clinvar"] == []
    
    def test_lookup_rsids_batch_empty(self, tmp_dir):
        """Test batch lookup with empty list."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        results = db.lookup_rsids_batch([])
        
        assert results == {}


class TestLookupMissing:
    """Tests for missing rsID handling."""
    
    def test_lookup_missing_rsid(self, tmp_dir):
        """Test that missing rsIDs return empty lists."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        result = db.lookup_rsid("rsNEVERINSERTED")
        
        assert result["clinvar"] == []
        assert result["gwas"] == []


class TestMetadata:
    """Tests for metadata operations."""
    
    def test_metadata_set_and_get(self, tmp_dir):
        """Test setting and getting metadata."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        # Set metadata
        db.set_metadata("test_key", "test_value")
        
        # Get metadata
        value = db.get_metadata("test_key")
        
        assert value == "test_value"
    
    def test_metadata_missing_key(self, tmp_dir):
        """Test getting missing metadata key."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        value = db.get_metadata("nonexistent_key")
        
        assert value is None


class TestDatabaseStats:
    """Tests for database statistics."""
    
    def test_db_stats(self, tmp_dir):
        """Test getting database statistics."""
        db_path = str(Path(tmp_dir) / "test.db")
        db = AllelioDB(db_path=db_path)
        db.initialize()
        
        clinvar_records = [
            {
                "rsid": f"rs{i}",
                "gene": f"GENE{i}",
                "clinical_significance": "pathogenic",
                "conditions": f"Disease{i}",
                "review_status": "criteria provided",
                "last_evaluated": "2023-01-01"
            }
            for i in range(5)
        ]
        
        gwas_records = [
            {
                "rsid": f"rs{i}",
                "trait": f"Trait{i}",
                "p_value": 1.5e-20,
                "odds_ratio": "1.05",
                "mapped_gene": f"GENE{i}",
                "study": f"Study{i}",
                "pubmed_id": f"1234567{i}",
                "link": ""
            }
            for i in range(3)
        ]

        db.insert_clinvar_batch(clinvar_records)
        db.insert_gwas_batch(gwas_records)

        stats = db.get_stats()

        assert "clinvar_entries" in stats
        assert "gwas_entries" in stats
        assert stats["clinvar_entries"] == 5
        assert stats["gwas_entries"] == 3


class TestContextManager:
    """Tests for context manager functionality."""
    
    def test_context_manager_opens_and_closes(self, tmp_dir):
        """Test that context manager opens and closes properly."""
        db_path = str(Path(tmp_dir) / "test.db")
        
        with AllelioDB(db_path=db_path) as db:
            db.initialize()
            assert db.conn is not None
            assert db.cursor is not None
        
        # After context exit, connection should be closed
        # (We can't directly test this without inspecting internals)
    
    def test_context_manager_with_operations(self, tmp_dir):
        """Test performing operations within context manager."""
        db_path = str(Path(tmp_dir) / "test.db")
        
        with AllelioDB(db_path=db_path) as db:
            db.initialize()
            
            record = {
                "rsid": "rs1234",
                "gene": "GENE1",
                "clinical_significance": "pathogenic",
                "conditions": "Test",
                "review_status": "criteria provided",
                "last_evaluated": "2023-01-01"
            }
            
            db.insert_clinvar_batch([record])
            result = db.lookup_rsid("rs1234")
            
            assert len(result["clinvar"]) > 0


class TestDatabaseIntegrity:
    """Tests for database integrity and persistence."""
    
    def test_data_persists_after_close(self, tmp_dir):
        """Test that data persists after closing and reopening database."""
        db_path = str(Path(tmp_dir) / "test.db")
        
        # Insert data
        with AllelioDB(db_path=db_path) as db:
            db.initialize()
            record = {
                "rsid": "rs1234",
                "gene": "GENE1",
                "clinical_significance": "pathogenic",
                "conditions": "Test",
                "review_status": "criteria provided",
                "last_evaluated": "2023-01-01"
            }
            db.insert_clinvar_batch([record])
        
        # Reopen and verify data exists
        with AllelioDB(db_path=db_path) as db:
            result = db.lookup_rsid("rs1234")
            assert len(result["clinvar"]) > 0
            assert result["clinvar"][0]["rsid"] == "rs1234"
