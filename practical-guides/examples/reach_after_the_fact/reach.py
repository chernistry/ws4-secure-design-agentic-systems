"""Compare what a run touched with the reachable set it was declared to have.

    python reach.py <reachable-set.json> <journal.json>

Prints one of the agent-containment paper's three §6.1 outcomes, `within`,
`outside` or `not_established`, with the violating calls, every reason the
comparison could not be decided, and the declared entries nothing touched.
An observed violation settles `outside` without complete coverage (§7.4 C3).
A malformed input is a processing failure: exit 2, a message on stderr,
nothing on stdout, never an outcome (§7.4 C2).
"""

import hashlib
import json
import sys

import rfc8785

ENTRY_KINDS = {"host", "path_prefix", "tool", "credential"}
TOUCHED_KINDS = {"host", "path", "credential"}


class Malformed(Exception):
    pass


def need(obj, key, kind, where):
    if not isinstance(obj, dict) or key not in obj:
        raise Malformed(f"{where}: missing {key!r}")
    value = obj[key]
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise Malformed(f"{where}.{key}: must be {getattr(kind, '__name__', kind)}")
    return value


def digest(obj):
    return "sha256:" + hashlib.sha256(rfc8785.dumps(obj)).hexdigest()


def under(path, prefix):
    """Match on whole path segments: /a/b covers /a/b and /a/b/c, not /a/bc."""
    return path == prefix or path.startswith(prefix.rstrip("/") + "/")


def compare(inventory, journal):
    need(inventory, "inventory_id", str, "inventory")
    need(inventory, "version", str, "inventory")
    declared = {}
    for n, e in enumerate(need(inventory, "entries", list, "inventory")):
        kind = need(e, "kind", str, f"inventory.entries[{n}]")
        if kind not in ENTRY_KINDS:
            raise Malformed(f"inventory.entries[{n}].kind: unknown {kind!r}")
        need(e, "required_by_task", bool, f"inventory.entries[{n}]")
        declared[need(e, "id", str, f"inventory.entries[{n}]")] = kind
    sequence = need(journal, "sequence", dict, "journal")
    first = need(sequence, "first_index", int, "journal.sequence")
    last = need(sequence, "last_index", int, "journal.sequence")
    if "truncated" not in sequence or not isinstance(sequence["truncated"], (bool, dict)):
        raise Malformed("journal.sequence.truncated: must be false or an object")
    calls = need(journal, "calls", list, "journal")

    of_kind = lambda kind: [i for i, k in declared.items() if k == kind]
    violations, unplaced, used = [], [], set()
    for n, call in enumerate(calls):
        where = f"journal.calls[{n}]"
        index = need(call, "index", int, where)
        action_id = need(call, "action_id", str, where)
        tool = need(call, "tool", str, where)
        if "touched" not in call:
            raise Malformed(f"{where}: missing 'touched'")
        touched = call["touched"]
        found = [(("tool", tool), tool if declared.get(tool) == "tool" else None)]
        if touched == "not_established":
            unplaced.append(index)
        elif isinstance(touched, list):
            for m, item in enumerate(touched):
                kind = need(item, "kind", str, f"{where}.touched[{m}]")
                rid = need(item, "id", str, f"{where}.touched[{m}]")
                if kind not in TOUCHED_KINDS:
                    raise Malformed(f"{where}.touched[{m}].kind: unknown {kind!r}")
                if kind == "path":
                    match = next((p for p in of_kind("path_prefix") if under(rid, p)), None)
                else:
                    match = rid if declared.get(rid) == kind else None
                found.append(((kind, rid), match))
        else:
            raise Malformed(f"{where}.touched: must be a list or 'not_established'")
        for (kind, rid), match in found:
            if match is None:
                violations.append({"index": index, "action_id": action_id, "kind": kind, "id": rid})
            else:
                used.add(match)

    inv_digest = digest(inventory)
    not_determinable = []
    named = journal.get("inventory")
    if named is None:
        not_determinable.append({"index": None, "reason": "inventory_not_named"})
    elif need(named, "digest", str, "journal.inventory") != inv_digest:
        not_determinable.append({"index": None, "reason": "inventory_mismatch"})
    if isinstance(sequence["truncated"], dict):
        not_determinable.append({"index": None, "reason": "truncated"})
    present = {c["index"] for c in calls}
    not_determinable += [{"index": i, "reason": "sequence_gap"}
                         for i in range(first, last + 1) if i not in present]
    not_determinable += [{"index": i, "reason": "touched_not_established"} for i in unplaced]

    if violations:
        outcome = "outside"
    elif not_determinable:
        outcome = "not_established"
    else:
        outcome = "within"
    return {
        "outcome": outcome,
        "inventory": {"inventory_id": inventory["inventory_id"],
                      "version": inventory["version"], "digest": inv_digest},
        "violations": violations,
        "not_determinable": not_determinable,
        "excess": sorted(set(declared) - used),
    }


def main(argv):
    if len(argv) != 3:
        print("usage: reach.py <reachable-set.json> <journal.json>", file=sys.stderr)
        return 2
    try:
        with open(argv[1]) as f:
            inventory = json.load(f)
        with open(argv[2]) as f:
            journal = json.load(f)
        result = compare(inventory, journal)
    except (OSError, ValueError, Malformed) as err:
        print(f"processing failure: {err}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
