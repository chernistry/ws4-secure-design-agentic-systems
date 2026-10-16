"""Grade reach.py against the committed fixtures.

The expected outcomes live in expected.json and are read only here, never by
reach.py (the paper's §7.4 C6). Fixtures are graded as committed; nothing is
regenerated before grading.
"""

import json
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).parent
EXPECTED = json.loads((HERE / "expected.json").read_text())


def run(name):
    return subprocess.run(
        [sys.executable, str(HERE / "reach.py"),
         str(HERE / "reachable-set.json"), str(HERE / "fixtures" / f"{name}.json")],
        capture_output=True, text=True,
    )


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_fixture(name):
    want = EXPECTED[name]
    proc = run(name)
    assert proc.returncode == want["exit"], proc.stderr
    if want["exit"] != 0:
        # A processing failure emits no verdict (§7.4 C2).
        assert proc.stdout.strip() == ""
        assert proc.stderr.strip() != ""
        return
    got = json.loads(proc.stdout)
    assert got["outcome"] == want["outcome"]
    assert [[v["index"], v["kind"], v["id"]] for v in got["violations"]] == want["violations"]
    assert [[n["index"], n["reason"]] for n in got["not_determinable"]] == want["not_determinable"]
    if "excess" in want:
        assert got["excess"] == want["excess"]
    inventory = json.loads((HERE / "reachable-set.json").read_text())
    assert got["inventory"]["version"] == inventory["version"]
    assert got["inventory"]["digest"].startswith("sha256:")


def test_expectations_are_not_read_by_the_checker():
    assert "expected" not in (HERE / "reach.py").read_text()
