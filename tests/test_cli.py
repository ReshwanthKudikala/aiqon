import json

from shipment_decision.cli import main


def test_score_json_output_and_exit_codes(tmp_path, capsys):
    main(["show", "S03", "--out", str(tmp_path / "s03.json")])
    capsys.readouterr()
    assert main(["score", str(tmp_path / "s03.json")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "recommended" and out["recommended_route_id"] == "R"
    assert out["schema_version"] == 1

    main(["show", "X01", "--out", str(tmp_path / "x01.json")])
    capsys.readouterr()
    assert main(["score", str(tmp_path / "x01.json"), "--text"]) == 2
    assert "incomplete_risk" in capsys.readouterr().out


def test_score_tolerates_utf8_bom(tmp_path, capsys):
    main(["show", "S12", "--out", str(tmp_path / "s12.json")])
    capsys.readouterr()
    raw = (tmp_path / "s12.json").read_bytes()
    (tmp_path / "s12_bom.json").write_bytes(b"\xef\xbb\xbf" + raw)
    assert main(["score", str(tmp_path / "s12_bom.json"), "--priority", "min_time"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["priority"] == "min_time" and out["recommended_route_id"] == "Q"


def test_evaluate_writes_files(tmp_path, capsys):
    j, m = tmp_path / "r" / "e.json", tmp_path / "r" / "e.md"
    assert main(["evaluate", "--json", str(j), "--markdown", str(m)]) == 0
    report = json.loads(j.read_text(encoding="utf-8"))
    assert report["corpus_size"] == 20
    assert "## Winners per shipment" in m.read_text(encoding="utf-8")


def test_show_unknown_id(capsys):
    assert main(["show", "S99"]) == 1
