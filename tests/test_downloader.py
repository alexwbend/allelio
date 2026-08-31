"""Tests for download hardening: GWAS source URL and staleness warnings."""

from datetime import datetime, timedelta
from pathlib import Path

from click.testing import CliRunner

from allelio.database import downloader
from allelio.database.downloader import (
    GWAS_URL,
    STALENESS_THRESHOLD_DAYS,
    staleness_warning,
)
from allelio.database.store import AllelioDB
from allelio import cli


class TestGwasUrl:
    """The GWAS Catalog moved off the retiring v1 API to the versioned FTP path."""

    def test_gwas_url_is_ftp_releases_latest(self):
        """GWAS downloads point at the release-versioned FTP path."""
        assert GWAS_URL == (
            "https://ftp.ebi.ac.uk/pub/databases/gwas/releases/latest/"
            "gwas-catalog-associations_ontology-annotated-full.zip"
        )

    def test_gwas_url_is_not_the_retired_v1_api(self):
        """The retired EBI API v1 endpoint must not be used."""
        assert "api/search/downloads" not in GWAS_URL
        assert "/v1.0" not in GWAS_URL

    def test_gwas_url_is_a_zip(self):
        """The FTP asset is a zip, which the extractor already handles."""
        assert GWAS_URL.endswith(".zip")


class TestDaysSinceUpdate:
    """AllelioDB.days_since_update reports the age of the local data."""

    def test_none_when_never_updated(self, tmp_dir):
        db = AllelioDB(db_path=str(Path(tmp_dir) / "test.db"))
        db.initialize()
        assert db.days_since_update() is None

    def test_zero_when_just_updated(self, tmp_dir):
        db = AllelioDB(db_path=str(Path(tmp_dir) / "test.db"))
        db.initialize()
        db.set_metadata("last_update", datetime.now().isoformat())
        age = db.days_since_update()
        assert age is not None
        assert age < 1

    def test_reports_age_for_old_timestamp(self, tmp_dir):
        db = AllelioDB(db_path=str(Path(tmp_dir) / "test.db"))
        db.initialize()
        old = (datetime.now() - timedelta(days=200)).isoformat()
        db.set_metadata("last_update", old)
        age = db.days_since_update()
        assert age is not None
        assert 199 < age < 201

    def test_none_for_unparseable_timestamp(self, tmp_dir):
        db = AllelioDB(db_path=str(Path(tmp_dir) / "test.db"))
        db.initialize()
        db.set_metadata("last_update", "not-a-date")
        assert db.days_since_update() is None


class TestStalenessWarning:
    """staleness_warning nudges the user to `allelio update` when data is old."""

    def test_no_warning_when_unknown(self, tmp_dir):
        db = AllelioDB(db_path=str(Path(tmp_dir) / "test.db"))
        db.initialize()
        assert staleness_warning(db) is None

    def test_no_warning_when_fresh(self, tmp_dir):
        db = AllelioDB(db_path=str(Path(tmp_dir) / "test.db"))
        db.initialize()
        db.set_metadata("last_update", datetime.now().isoformat())
        assert staleness_warning(db) is None

    def test_warns_when_stale(self, tmp_dir):
        db = AllelioDB(db_path=str(Path(tmp_dir) / "test.db"))
        db.initialize()
        old = (datetime.now() - timedelta(days=STALENESS_THRESHOLD_DAYS + 30)).isoformat()
        db.set_metadata("last_update", old)
        msg = staleness_warning(db)
        assert msg is not None
        assert "allelio update" in msg

    def test_boundary_just_under_threshold_is_fresh(self, tmp_dir):
        db = AllelioDB(db_path=str(Path(tmp_dir) / "test.db"))
        db.initialize()
        old = (datetime.now() - timedelta(days=STALENESS_THRESHOLD_DAYS - 1)).isoformat()
        db.set_metadata("last_update", old)
        assert staleness_warning(db) is None

    def test_custom_threshold(self, tmp_dir):
        db = AllelioDB(db_path=str(Path(tmp_dir) / "test.db"))
        db.initialize()
        old = (datetime.now() - timedelta(days=10)).isoformat()
        db.set_metadata("last_update", old)
        assert staleness_warning(db, threshold_days=5) is not None
        assert staleness_warning(db, threshold_days=30) is None


def _seed_default_db(home: str) -> AllelioDB:
    """Create an initialized default-path database under a fake HOME."""
    db_path = Path(home) / ".allelio" / "data" / "allelio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = AllelioDB(db_path=str(db_path))
    db.initialize()
    db.insert_clinvar_batch([
        {
            "rsid": "rs1234",
            "gene": "GENE1",
            "clinical_significance": "pathogenic",
            "conditions": "Test",
            "review_status": "criteria provided",
            "last_evaluated": "2023-01-01",
        }
    ])
    return db


class _NoAIEngine:
    """Stand-in AIEngine whose ``client`` is None so `info` skips the network.

    The real AIEngine tries to reach a local Ollama daemon in its connection
    check; these tests only care about the data-freshness row, so we short out
    the AI path (client=None makes `info` print "AI module not available").
    """

    def __init__(self, model=None):
        self.client = None


class TestInfoFreshness:
    """`allelio info` surfaces the data-freshness row."""

    def test_info_shows_stale_nudge(self, tmp_dir, monkeypatch):
        monkeypatch.setenv("HOME", tmp_dir)
        # Widen the console so the table cell doesn't wrap mid-phrase.
        monkeypatch.setenv("COLUMNS", "250")
        monkeypatch.setattr("allelio.ai.engine.AIEngine", _NoAIEngine)
        db = _seed_default_db(tmp_dir)
        old = (datetime.now() - timedelta(days=STALENESS_THRESHOLD_DAYS + 5)).isoformat()
        db.set_metadata("last_update", old)
        db.close()

        result = CliRunner().invoke(cli.info, [])
        assert result.exit_code == 0
        assert "allelio update" in result.output

    def test_info_shows_fresh(self, tmp_dir, monkeypatch):
        monkeypatch.setenv("HOME", tmp_dir)
        monkeypatch.setenv("COLUMNS", "250")
        monkeypatch.setattr("allelio.ai.engine.AIEngine", _NoAIEngine)
        db = _seed_default_db(tmp_dir)
        db.set_metadata("last_update", datetime.now().isoformat())
        db.close()

        result = CliRunner().invoke(cli.info, [])
        assert result.exit_code == 0
        assert "Data Freshness" in result.output
