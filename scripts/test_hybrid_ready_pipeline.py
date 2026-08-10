#!/usr/bin/env python3
from __future__ import annotations

import subprocess

from run_hybrid_ready_pipeline import command_plan, execute, extract_json_objects


def main() -> int:
    gate_only = command_plan(
        "night_scout",
        "ns_1600_original",
        1,
        apply=True,
    )
    assert len(gate_only) == 1
    exact = command_plan(
        "night_scout",
        "ns_1600_original",
        1,
        apply=True,
        queue_id="q1",
    )
    assert len(exact) == 2
    assert "--queue-id" in exact[1]
    assert "q1" in exact[1]

    media_exact = command_plan(
        "night_scout",
        "ns_1800_direct_media",
        1,
        apply=True,
        approval_mode="media",
        queue_id="q_media",
    )
    assert "--require-human-review" in media_exact[0]

    parsed = extract_json_objects(
        'noise\n{"status":"A"}\nmore\n{"updated_queue_ids":["q1"]}\n'
    )
    assert parsed[-1]["updated_queue_ids"] == ["q1"]

    commands: list[list[str]] = []
    responses = iter(
        [
            subprocess.CompletedProcess(
                [],
                0,
                '{"status":"PASS","results":[{"queue_id":"q1","status":"PASS"}]}\n',
                "",
            ),
            subprocess.CompletedProcess(
                [],
                0,
                '{"updated_queue_ids":["q1"]}\n',
                "",
            ),
        ]
    )

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return next(responses)

    result = execute(
        "night_scout",
        "ns_1600_original",
        1,
        apply=True,
        approval_mode="text",
        runner=runner,
    )
    assert result["status"] == "READY"
    assert result["selected_queue_id"] == "q1"
    assert "--queue-id" in commands[1]
    assert commands[1][commands[1].index("--queue-id") + 1] == "q1"

    no_candidate_calls = 0

    def no_candidate_runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        nonlocal no_candidate_calls
        no_candidate_calls += 1
        return subprocess.CompletedProcess(command, 0, '{"results":[]}\n', "")

    no_candidate = execute(
        "night_scout",
        "ns_1600_original",
        1,
        apply=True,
        runner=no_candidate_runner,
    )
    assert no_candidate["status"] == "NO_READY_CANDIDATE"
    assert no_candidate_calls == 1
    print("PASS test_hybrid_ready_pipeline.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
