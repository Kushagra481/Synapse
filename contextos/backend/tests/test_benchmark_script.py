import shlex
import sys
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
    assert result["resume_summary"]["1200"]["resume_success_rate"] == 1.0
    assert result["resume_summary"]["task_only_baseline"]["context_coverage"] < 1.0
    assert result["resume_summary"]["agent_mode"] == "deterministic_simulation"
    assert report_path.is_file()
    contents = report_path.read_text(encoding="utf-8")
    assert "Aggregate retrieval metrics" in contents
    assert "Fresh-agent resume evaluation" in contents
    assert "access token validation" in contents
    assert "Jev row is a local hybrid fallback" in contents
    assert "No external agent command was configured" in contents
    assert "pytest fixture assertion: passed" in contents


@pytest.mark.asyncio
async def test_external_agent_adapter_runs_in_isolated_json_protocol(tmp_path: Path):
    adapter = tmp_path / "echo_agent.py"
    adapter.write_text(
        "import json, re, sys\n"
        "payload = json.load(sys.stdin)\n"
        "packet = payload['handoff_packet']\n"
        "files = re.findall(r'(?<![A-Za-z0-9_.-])(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\\.py', packet)\n"
        "json.dump({'task_state': packet, 'decisions': [packet], "
        "'changed_files': files, 'next_actions': [packet]}, sys.stdout)\n",
        encoding="utf-8",
    )
    result = await run(
        tmp_path / "external-agent-results.md",
        [],
        agent_command=shlex.join([sys.executable, str(adapter)]),
        allow_agent_command=True,
    )

    assert result["resume_summary"]["agent_mode"] == "configured external agent command"
    assert result["resume_summary"]["512"]["success_count"] == 3
    assert result["resume_summary"]["512"]["agent_runtime_ms"] is not None
    assert all(row["agent_status"] == "ok" for row in result["resume_results"])


@pytest.mark.asyncio
async def test_external_agent_command_requires_explicit_opt_in(tmp_path: Path):
    with pytest.raises(ValueError, match="allow_agent_command"):
        await run(tmp_path / "unused.md", [], agent_command="some-agent")
