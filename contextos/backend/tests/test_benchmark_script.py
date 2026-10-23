from pathlib import Path

import pytest

from scripts.run_benchmark import run


@pytest.mark.asyncio
async def test_local_benchmark_script_writes_reproducible_report(tmp_path: Path):
    report_path = tmp_path / "test_results.md"
    result = await run(report_path, ["pytest fixture assertion: passed"])

    assert result["index"]["file_count"] == 6
    assert result["index"]["symbol_count"] >= 5
    assert result["metrics"]["lexical"]["recall_at_k"] == 1.0
    assert result["metrics"]["hybrid"]["recall_at_k"] == 1.0
    assert result["metrics"]["jev"]["jev_used"] == 0.0
    assert report_path.is_file()
    contents = report_path.read_text(encoding="utf-8")
    assert "Aggregate retrieval metrics" in contents
    assert "access token validation" in contents
    assert "Jev row is a local hybrid fallback" in contents
    assert "pytest fixture assertion: passed" in contents
