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


@pytest.fixture
def journal():
    return json.loads((HERE / "fixtures" / "within.json").read_text())


def assert_processing_failure(journal, tmp_path):
    path = tmp_path / "journal.json"
    path.write_text(json.dumps(journal))
    proc = subprocess.run(
        [sys.executable, str(HERE / "reach.py"),
         str(HERE / "reachable-set.json"), str(path)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2, proc.stdout
    assert proc.stdout == ""
    assert proc.stderr.strip() != ""


def test_truncation_true_is_a_processing_failure(journal, tmp_path):
    journal["sequence"]["truncated"] = True
    assert_processing_failure(journal, tmp_path)


def test_duplicate_call_indices_are_a_processing_failure(journal, tmp_path):
    journal["calls"].append(journal["calls"][0].copy())
    assert_processing_failure(journal, tmp_path)


@pytest.mark.parametrize("boundary,offset", [("first_index", -1), ("last_index", 1)],
                         ids=["before-first", "after-last"])
def test_call_indices_outside_declared_bounds_are_a_processing_failure(
        journal, tmp_path, boundary, offset):
    call = journal["calls"][0].copy()
    call["index"] = journal["sequence"][boundary] + offset
    journal["calls"].append(call)
    assert_processing_failure(journal, tmp_path)


def test_nonempty_inverted_bounds_are_a_processing_failure(journal, tmp_path):
    journal["sequence"]["first_index"] = 5
    journal["sequence"]["last_index"] = 2
    assert_processing_failure(journal, tmp_path)
