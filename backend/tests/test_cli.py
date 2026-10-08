"""CLI success and failure codes represent the same ledger gate used by the library."""

import json

from conftest import ROOT

from book_core.cli import main


def test_cli_fixture_success_and_cache_reuse(tmp_path, capsys):
    source = ROOT / "experiments/fixtures/column_26.pdf"
    report_path = tmp_path / "report.json"
    args = [
        "ledger-check",
        str(source),
        "--cache-dir",
        str(tmp_path / "cache"),
        "--report",
        str(report_path),
    ]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["passing"] and result["missing_token_count"] == result["extra_token_count"] == 0
    assert result["node_token_count"] == 564
    assert json.loads(report_path.read_text("utf-8")) == result
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["cache_hits"] == 1 and result["cache_misses"] == 0
