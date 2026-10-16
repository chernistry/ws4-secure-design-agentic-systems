# Measuring Reach After the Fact

A procedure for comparing what an agent run actually touched with the reachable set it was declared to have. The agent-containment paper requires the versioning and the three outcomes (§6.1) and leaves the procedure to a practical guide. This is that procedure, with a worked example under [`examples/reach_after_the_fact/`](./examples/reach_after_the_fact/).

## What is being compared

| Quantity | Kind | Where it comes from |
| :---- | :---- | :---- |
| Declared reachable set | Declared, versioned | The inventory maintained as deployment configuration (§6.1): every host, path, credential and tool the agent can reach through any path in its effective reach (§3) |
| Touched set | Measured | The run's own tool-call journal: per call, the resources it touched |

The declared set is a claim made before the run. The touched set is an observation made during it. The two can be compared only after the run, and only when the run's record names the version of the inventory it ran under, by content digest (§6.1, §7.1).

## The three outcomes

| Outcome | Meaning | Settled by |
| :---- | :---- | :---- |
| `within` | Every touched resource lies inside the declared set, and the journal is complete for the run | A complete journal bound to the inventory version |
| `outside` | At least one call touched a resource, or used a tool, that the declared set does not contain | One admissible observation of the call. Complete coverage is not needed (§7.4 C3) |
| `not_established` | The comparison cannot be decided, and the reason is carried | Any missing premise: the inventory is not named or does not match, the journal is truncated, an index is missing, or a call's touched set could not be placed |

The third outcome must stay distinct from the first. A partial journal that is read as "within" is the failure this comparison exists to prevent (§6.1). A journal with a gap is not evidence that the missing calls stayed inside the set.

A malformed record, a missing required field or an unknown resource kind is a processing failure. It produces no outcome at all, so a broken checker cannot pass by returning `not_established` (§7.4 C2). In the example the checker exits 2, prints to stderr and writes nothing to stdout.

## Procedure

1. **Fix the declared set.** Keep the inventory as a versioned file. Its digest is SHA-256 over the RFC 8785 canonical form of the file, the same construction the evidence sample uses for its content digests. Record which entries the task requires.
2. **Bind the run to it.** The run's record names the inventory by `inventory_id` and digest at the start of the run, alongside the policy version (§7.1). If the record does not name it, or names a different digest, stop at `not_established`: the comparison would be against a set the run did not run under.
3. **Establish the journal's coverage.** Check that the journal is not marked truncated and that every index from the first to the last is present. In a hash-chained record such as the [containment evidence sample](./examples/containment_evidence/), check the chain and the checkpoint boundaries first. Each missing index is carried as its own reason.
4. **Derive the touched set.** Take the resources each call touched, from the journal and not from the model's narration. A call whose touched set the producer could not place is carried as `touched_not_established` for that call.
5. **Compare.** Match hosts and credentials exactly. Match paths on whole path segments, so `/workspace/repo` covers `/workspace/repo/src` but not `/workspace/repository-copy`. A tool that is not in the inventory is a violation in its own right.
6. **Decide and report.** Any violation means `outside`, with each violating call named by index and action identifier. Otherwise any missing premise means `not_established`, with every reason listed. Otherwise the outcome is `within`.
7. **Use the excess.** The declared entries that no call touched are the input to the minimization pass in §6.1. An entry the task does not require and no run touches is blast radius carried for no return.

## Worked example

```bash
pip install rfc8785 pytest
cd examples/reach_after_the_fact
python reach.py reachable-set.json fixtures/within.json
python -m pytest -q
```

`reachable-set.json` declares five entries, two of them not required by the task. The fixtures cover one case per branch of the procedure:

| Fixture | Outcome | Why |
| :---- | :---- | :---- |
| `within` | `within` | Complete journal, bound to the inventory. `excess` lists the two entries no call touched |
| `outside` | `outside` | Call 1 reaches an undeclared host |
| `undeclared-tool` | `outside` | Call 1 uses a tool the inventory does not declare |
| `prefix-boundary` | `outside` | A path that shares a string prefix but not a path segment |
| `outside-and-gap` | `outside` | Index 1 is missing, and call 2 touches an undeclared path. The observed violation settles the outcome. The gap is still reported |
| `sequence-gap` | `not_established` | Index 1 is missing |
| `truncated` | `not_established` | The producer marked the journal as truncated |
| `inventory-not-named` | `not_established` | The record does not name the inventory |
| `inventory-mismatch` | `not_established` | The record names another inventory version |
| `touched-not-established` | `not_established` | The producer could not place what call 2 touched |
| `malformed` | processing failure | Call 1 has no `touched` member |

The expected outcomes are in `expected.json`, which only the grading harness reads. The checker never sees them (§7.4 C6).

## What this measurement does not establish

- **That the agent could not have reached further.** The comparison covers what was touched, not what was reachable. An undeclared path the run never used stays invisible to it. Finding such paths is the design-time inventory work of §6.1 and the verification of §8.
- **That an unmediated channel did not exist.** The journal records the calls that passed through the mediation point (§3). Effects that bypass it are outside the journal by construction.
- **That the journal is honest.** A self-reported touched set is the producer's statement. Without an independent observer it supports `outside` only as an admission, and it cannot raise a claim of absence above `not_established` (§7.4 C3, C4). The record should say which vantage observed the calls.
- **Anything about other runs.** The outcome is bound to one run, one journal and one inventory version (§7.4 C5).

## Aggregating across a set of agents

When several agents share a principal, the per-run touched sets can be combined to show the reach consumed by the set (§4). The union is meaningful only if every run in it is `within` or `outside`. A single `not_established` run makes the union `not_established` for the same reason. Each run must also name the same inventory version, or the union mixes declared sets that differ.
