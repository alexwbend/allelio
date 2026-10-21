"""Invented inputs only: real research genomes must never run in public CI."""
import gzip
import importlib.util
import json
from pathlib import Path

import pytest

from allelio.database.store import AllelioDB
from allelio.runs import reference_identity, references

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("public_input_demo", ROOT / "scripts/demonstrate_public_input.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / "invented.vcf.gz"
    header = (b"##fileformat=VCFv4.2\n##reference=GRCh38\n##private_note=DO_NOT_EXPORT\n"
              b"#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tINVENTED_ONLY\n")
    rows = [b"22\t20000000\trs9\tA\tG\t.\tPASS\t.\tGT\t0/1\n",
            b"chr22\t20000001\trs1\tA\tG\t.\tPASS\t.\tGT\t0/1\n",
            b"22\t21000000\t.\tA\tG\t.\tPASS\t.\tGT\t0/1\n",
            b"22\t21000001\trs8\tA\tG\t.\tPASS\t.\tGT\t0/1\n"]
    with gzip.open(source, "wb") as out:
        out.write(header + b"".join(rows))
    database = tmp_path / "invented.db"
    db = AllelioDB(str(database)); db.initialize()
    db.insert_clinvar_batch([dict(rsid="rs1", ref_allele="A", alt_allele="G", assembly="GRCh38",
        chromosome="22", position_vcf=20000001, allele_id="1", variation_id="1",
        clinical_significance="Pathogenic", review_status="reviewed by expert panel", gene="INVENTED_ONLY")])
    db.close()
    protocol = json.loads(demo.PROTOCOL.read_text())
    protocol["source"]["published_md5"] = demo.fingerprints(source)["md5"]
    with references(database) as db:
        protocol["references"]["logical_sha256"] = reference_identity(db)["logical_sha256"]
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(protocol))
    return source, database, tmp_path / "out", path, header, rows


def test_original_rows_boundaries_replay_and_aggregate_privacy(setup, monkeypatch):
    source, database, output, protocol, header, rows = setup
    from allelio.ai import engine
    monkeypatch.setattr(engine, "AIEngine", lambda *a, **kw: pytest.fail("Model must not be constructed"))
    report = demo.run(source, database, output, protocol)
    assert (output / "selected.vcf").read_bytes() == header + rows[1] + rows[2]
    assert report["selection"]["source_rows_scanned"] == 4
    assert report["selection"]["selected_rows"] == 2
    p = report["processing"]
    assert p["parsed_rows"] == 1 and p["returned_findings"] == 1
    assert p["parser_dispositions"] == {"parsed": 1, "unsupported_identifier": 1}
    assert p["accounting_complete"] and p["evidence_contract_valid"] and p["annotation_replayed"]
    assert report["execution_checks_passed"] and not p["annotation_accuracy_assessed"]
    assert output.stat().st_mode & 0o777 == 0o700
    assert not (output / "INCOMPLETE").exists()
    serialized = json.dumps(report)
    for private in (str(source), "DO_NOT_EXPORT", "INVENTED_ONLY", '"rs1"', "0/1"):
        assert private not in serialized


def test_all_missing_ids_preserve_unsupported_result(setup):
    source, database, output, protocol, header, rows = setup
    with gzip.open(source, "wb") as out:
        out.write(header + rows[2])
    p = json.loads(protocol.read_text()); p["source"]["published_md5"] = demo.fingerprints(source)["md5"]
    protocol.write_text(json.dumps(p))
    report = demo.run(source, database, output, protocol)
    assert report["execution_checks_passed"]
    assert report["processing"]["parsed_rows"] == report["processing"]["returned_findings"] == 0
    assert report["processing"]["final_dispositions"] == {"unsupported_identifier": 1}
    assert not report["processing"]["annotation_accuracy_assessed"]


def test_raised_production_exception_stays_in_private_log_and_terminal_is_generic(setup, monkeypatch, capsys):
    source, database, output, protocol, header, rows = setup
    def broken(*args, **kwargs):
        raise ValueError("INVENTED_PRIVATE_DIAGNOSTIC")
    monkeypatch.setattr(demo, "record_run", broken)
    with pytest.raises(ValueError):
        demo.run(source, database, output, protocol)
    assert "INVENTED_PRIVATE_DIAGNOSTIC" in (output / "execution.log").read_text()
    assert not (output / "report.json").exists()
    assert "INVENTED_PRIVATE_DIAGNOSTIC" not in capsys.readouterr().err
    monkeypatch.setattr(demo, "run", broken)
    monkeypatch.setattr(demo.sys, "argv", ["demo", "--source", str(source), "--database", str(database), "--output", str(output)])
    assert demo.main() == 2
    terminal = capsys.readouterr()
    assert "INVENTED_PRIVATE_DIAGNOSTIC" not in terminal.err + terminal.out


@pytest.mark.parametrize("change", ["source", "database", "existing_output", "inside_git"])
def test_invalid_prerequisites_never_produce_report(setup, change):
    source, database, output, protocol, header, rows = setup
    if change == "source":
        source.write_bytes(b"wrong source")
    elif change == "database":
        db = AllelioDB(str(database)); db.set_metadata("mutation", "yes"); db.close()
    elif change == "existing_output":
        output.mkdir()
    else:
        (source.parent / ".git").mkdir()
    with pytest.raises(ValueError):
        demo.run(source, database, output, protocol)
    assert not (output / "report.json").exists()


@pytest.mark.parametrize("mutation", ["source", "evidence", "protocol", "network", "foreign_status"])
def test_midrun_mutations_and_network_cannot_silently_complete(setup, monkeypatch, mutation):
    source, database, output, protocol, header, rows = setup
    original = demo.record_run
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if mutation == "source": source.write_bytes(b"changed")
        if mutation == "protocol": protocol.write_text('{}')
        if mutation == "network": demo.socket.create_connection(("127.0.0.1", 1))
        if mutation == "foreign_status":
            result[1]["coverage"]["counts"] = {"DO_NOT_EXPORT": 2}
        return result
    monkeypatch.setattr(demo, "record_run", changed)
    if mutation == "evidence":
        replay = demo.replay_run
        def alter_artifact(*a, **kw):
            result = replay(*a, **kw)
            (output / "evidence.json").write_text('{}')
            return result
        monkeypatch.setattr(demo, "replay_run", alter_artifact)
    with pytest.raises((ValueError, RuntimeError)):
        demo.run(source, database, output, protocol)
    assert (output / "INCOMPLETE").exists()
    assert not (output / "report.json").exists()
