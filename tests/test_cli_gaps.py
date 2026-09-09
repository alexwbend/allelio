"""PUB-11-lite: `allelio analyze` and `allelio info` disclose skipped 23andMe
internal (i) ID rows rather than silently dropping them. See README "Known
gaps: 23andMe internal IDs" and PUBLICATION_PLAN.md.
"""

from pathlib import Path

from click.testing import CliRunner

from allelio import cli
from allelio.database.store import AllelioDB


class _NoAIEngine:
    """Stand-in AIEngine whose ``client`` is None, so the CLI skips the network.

    Mirrors the fixture in tests/test_downloader.py — these tests only care
    about the parse-stats line, not AI status.
    """

    def __init__(self, model=None):
        self.client = None


def _mixed_id_file(tmp_dir: str) -> str:
    file_path = Path(tmp_dir) / "mixed_ids.txt"
    content = """# rsid\tchromosome\tposition\tgenotype
rs1234\t1\t100000\tAA
i3002432\t11\t46761055\tGA
i4000415\t1\t155205634\tAG
"""
    file_path.write_text(content)
    return str(file_path)


def _seed_default_db(home: str) -> AllelioDB:
    db_path = Path(home) / ".allelio" / "data" / "allelio.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = AllelioDB(db_path=str(db_path))
    db.initialize()
    return db


class TestInfoDisclosesSkippedIIDRows:
    def test_info_prints_skipped_count_for_23andme_file(self, tmp_dir, monkeypatch):
        monkeypatch.setenv("HOME", tmp_dir)
        monkeypatch.setenv("COLUMNS", "250")
        monkeypatch.setattr("allelio.ai.engine.AIEngine", _NoAIEngine)
        genotype_file = _mixed_id_file(tmp_dir)

        result = CliRunner().invoke(cli.info, [genotype_file])

        assert result.exit_code == 0
        assert "Skipped 2 rows with 23andMe internal (i) IDs" in result.output

    def test_info_says_nothing_skipped_without_i_id_rows(self, tmp_dir, monkeypatch, sample_23andme_file):
        monkeypatch.setenv("HOME", tmp_dir)
        monkeypatch.setenv("COLUMNS", "250")
        monkeypatch.setattr("allelio.ai.engine.AIEngine", _NoAIEngine)

        result = CliRunner().invoke(cli.info, [sample_23andme_file])

        assert result.exit_code == 0
        assert "Skipped" not in result.output

    def test_info_without_a_file_argument_still_works(self, tmp_dir, monkeypatch):
        """FILE is optional — `allelio info` alone must keep working."""
        monkeypatch.setenv("HOME", tmp_dir)
        monkeypatch.setenv("COLUMNS", "250")
        monkeypatch.setattr("allelio.ai.engine.AIEngine", _NoAIEngine)

        result = CliRunner().invoke(cli.info, [])

        assert result.exit_code == 0
        assert "Skipped" not in result.output


class TestAnalyzeDisclosesSkippedIIDRows:
    def test_analyze_prints_skipped_count(self, tmp_dir, monkeypatch):
        monkeypatch.setenv("HOME", tmp_dir)
        monkeypatch.setenv("COLUMNS", "250")
        monkeypatch.setattr("allelio.ai.engine.AIEngine", _NoAIEngine)
        db = _seed_default_db(tmp_dir)
        db.insert_clinvar_batch([
            {
                "rsid": "rs1234",
                "gene": "GENE1",
                "clinical_significance": "pathogenic",
                "conditions": "Test condition",
                "review_status": "criteria provided, single submitter",
                "last_evaluated": "2024-01-01",
            }
        ])
        db.close()
        genotype_file = _mixed_id_file(tmp_dir)

        result = CliRunner().invoke(
            cli.analyze, [genotype_file, "--no-ai", "-o", str(Path(tmp_dir) / "report.html")]
        )

        assert result.exit_code == 0
        assert "Skipped 2 rows with 23andMe internal (i) IDs" in result.output

        report_html = (Path(tmp_dir) / "report.html").read_text()
        assert "skipped 2 rows with 23andMe internal (i) IDs" in report_html
