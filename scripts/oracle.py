"""An independent check on every number this project reports.

Why this file exists
--------------------
The question a reviewer should ask about any analysis tool is "how do you know
the numbers are right, other than the tool saying so?". A test suite that only
exercises the shipped code cannot answer it: if the router is wrong, the tests
written against the router are wrong in the same direction and still pass.

This script is the answer. It computes the same figures by a different route,
and ``backend/tests/test_oracle.py`` asserts the two agree. When they disagree,
one of them is wrong and a human has to decide which, which is the point.

It began as a throwaway probe written before this repository contained a single
line of code, to check whether the task was even well posed. It reproduced the
figures the brief gives, which is how we knew the brief was consistent. It was
committed later, once it became clear that quoting evidence a reviewer cannot
run is no better than quoting no evidence at all.

What makes it independent
-------------------------
Independence is a property of the code, not a label, so it is worth being exact
about what is and is not shared.

**It imports nothing from netscope.** Not the loaders, not the models, not the
router. It parses the XML with regular expressions and the CSV by splitting on
commas, so a parsing mistake in the shipped loaders cannot propagate into the
expected values.

**It uses a deliberately naive algorithm.** The shipped router never enumerates
paths: it builds the predecessor directed acyclic graph of minimum-hop edges,
counts paths through each node, and gives every link a share proportional to
the paths crossing it. That is exact and linear, and it is also clever enough to
be wrong in ways that look plausible. This one enumerates every minimum-hop path
and divides the demand by their number, which is the naive reading of R5 and the
obvious thing a person would do by hand. The two share no reasoning, so an error
in one is unlikely to be mirrored in the other.

**What it does share.** The input files, the requirements, and the fact that one
author wrote both. It catches an implementation mistake. It cannot catch a wrong
shared assumption about what the requirements mean. That limit is real and worth
stating rather than glossing: the honest claim is "two independent routes to the
same number", not "externally validated".

Scope
-----
The baseline over the real network, the merge figures, and a named set of
failure scenarios. Not all 92 single failures: enumerating paths for 391 demands
is fast once and slow ninety-two times, and the scenarios chosen below are the
ones the findings report actually makes claims about.

Run it directly to see the figures:

    python scripts/oracle.py
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNDLIB = ROOT / "data" / "nobel-eu.xml"
SITES = ROOT / "data" / "sites.csv"

#: R3. The shipped code reads this from configuration with the same default.
#: Restated here rather than imported, because importing it would be one more
#: thing the two implementations share.
BACKBONE_CAPACITY = 550.0

#: R4.
OPS_TO_DATA_CENTER = 10.0
DATA_CENTER_PAIR = 50.0

#: R6. Only these kinds forward traffic for other nodes. Spelled out rather than
#: derived from NodeKind, for the same reason as the capacity above.
TRANSIT_KINDS = frozenset({"backbone-city", "aggregation-hub"})


@dataclass(frozen=True)
class Network:
    """The merged network in plain dictionaries, with no netscope types."""

    kinds: dict[str, str]
    capacity: dict[frozenset[str], float]
    demands: list[tuple[str, str, float]]

    @property
    def nodes(self) -> set[str]:
        return set(self.kinds)

    @property
    def transit(self) -> set[str]:
        return {node for node, kind in self.kinds.items() if kind in TRANSIT_KINDS}


def load() -> Network:
    """Parse both inputs and merge them, per R1, R3 and R4.

    The XML is read with regular expressions on purpose. It is the crudest
    thing that works, which is what we want: there is no chance of sharing a
    subtle parsing decision with the real loader.
    """
    raw = SNDLIB.read_text(encoding="ISO-8859-1")

    kinds = {node: "backbone-city" for node in re.findall(r'<node id="([^"]+)">', raw)}
    capacity: dict[frozenset[str], float] = {}
    for _, a, b in re.findall(
        r'<link id="([^"]+)">\s*<source>([^<]+)</source>\s*<target>([^<]+)</target>',
        raw,
    ):
        capacity[frozenset((a, b))] = BACKBONE_CAPACITY

    demands: list[tuple[str, str, float]] = [
        (a, b, float(value))
        for a, b, value in re.findall(
            r'<demand id="[^"]*">\s*<source>([^<]+)</source>\s*'
            r"<target>([^<]+)</target>\s*<demandValue>([0-9.]+)</demandValue>",
            raw,
        )
    ]

    with SITES.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        kinds[row["site_id"]] = row["site_type"]
    for row in rows:
        for target in row["attaches_to"].split(";"):
            capacity[frozenset((row["site_id"], target))] = float(
                row["access_capacity"]
            )

    # R4. Derived from the site_type column rather than from a list of names, so
    # that renaming a site in the CSV cannot silently change the demand set.
    ops = sorted(r["site_id"] for r in rows if r["site_type"] == "operations-site")
    dcs = sorted(r["site_id"] for r in rows if r["site_type"] == "data-center")
    demands += [(o, d, OPS_TO_DATA_CENTER) for o in ops for d in dcs]
    demands.append((dcs[0], dcs[1], DATA_CENTER_PAIR))

    return Network(kinds=kinds, capacity=capacity, demands=demands)


def _adjacency(
    net: Network, dead_nodes: frozenset[str], dead_links: frozenset[frozenset[str]]
) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for node in net.nodes - dead_nodes:
        adjacency[node] = set()
    for pair in net.capacity:
        if pair in dead_links or pair & dead_nodes:
            continue
        a, b = tuple(pair)
        adjacency[a].add(b)
        adjacency[b].add(a)
    return adjacency


def _minimum_hop_paths(
    adjacency: dict[str, set[str]], transit: set[str], source: str, target: str
) -> list[list[str]]:
    """Every minimum-hop path from source to target, honouring R6.

    Breadth-first, expanding a node only when it is the source or may forward.
    That is what lets a path end at a data center without passing through one.
    Enumerating rather than counting is the whole point of this file.
    """
    distance = {source: 0}
    parents: dict[str, list[str]] = defaultdict(list)
    queue = deque([source])
    while queue:
        node = queue.popleft()
        if node != source and node not in transit:
            continue
        for neighbour in adjacency[node]:
            if neighbour not in distance:
                distance[neighbour] = distance[node] + 1
                parents[neighbour].append(node)
                queue.append(neighbour)
            elif distance[neighbour] == distance[node] + 1:
                parents[neighbour].append(node)
    if target not in distance:
        return []

    paths: list[list[str]] = []

    def walk(node: str, tail: list[str]) -> None:
        if node == source:
            paths.append([source, *tail])
            return
        for parent in parents[node]:
            walk(parent, [node, *tail])

    walk(target, [])
    return paths


@dataclass(frozen=True)
class Scenario:
    loads: dict[frozenset[str], float]
    undeliverable: list[tuple[str, str, float]]
    endpoint_affected: list[tuple[str, str, float]]
    components: int

    def utilisation(self, net: Network) -> dict[frozenset[str], float]:
        return {pair: self.loads[pair] / net.capacity[pair] for pair in self.loads}


def analyse(
    net: Network,
    dead_nodes: frozenset[str] = frozenset(),
    dead_links: frozenset[frozenset[str]] = frozenset(),
) -> Scenario:
    """Route every demand and report what could not be carried."""
    adjacency = _adjacency(net, dead_nodes, dead_links)
    transit = net.transit - dead_nodes
    loads: dict[frozenset[str], float] = {
        pair: 0.0
        for pair in net.capacity
        if pair not in dead_links and not pair & dead_nodes
    }

    undeliverable: list[tuple[str, str, float]] = []
    endpoint_affected: list[tuple[str, str, float]] = []
    for source, target, volume in net.demands:
        if source in dead_nodes or target in dead_nodes:
            # R8 keeps these apart: the demand died with its own endpoint, not
            # because the network could not carry it.
            endpoint_affected.append((source, target, volume))
            continue
        paths = _minimum_hop_paths(adjacency, transit, source, target)
        if not paths:
            undeliverable.append((source, target, volume))
            continue
        # R5, the naive reading: every minimum-hop path takes an equal share.
        share = volume / len(paths)
        for path in paths:
            for a, b in pairwise(path):
                loads[frozenset((a, b))] += share

    # R7a is judged on the plain surviving graph, ignoring the transit rule:
    # the question is whether the network is in one piece, not whether traffic
    # is allowed to cross it.
    seen: set[str] = set()
    components = 0
    for start in sorted(net.nodes - dead_nodes):
        if start in seen:
            continue
        components += 1
        stack = [start]
        seen.add(start)
        while stack:
            node = stack.pop()
            for neighbour in adjacency[node]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
    return Scenario(loads, undeliverable, endpoint_affected, components)


def reasons(net: Network, scenario: Scenario) -> set[str]:
    """R7, as three independent reasons. Matches CriticalityReason's values.

    Losing only your own traffic is deliberately absent. See docs/DECISIONS.md
    D24: an element is critical when its loss costs a node that is still there.
    """
    fired: set[str] = set()
    if scenario.components > 1:
        fired.add("partitions-network")
    if scenario.undeliverable:
        fired.add("demands-undeliverable")
    if any(u > 1.0 for u in scenario.utilisation(net).values()):
        fired.add("links-overloaded")
    return fired


#: The failures the findings report makes claims about. Not all 92: enumerating
#: paths for 391 demands is quick once and slow ninety-two times, and these are
#: the ones with an assertion attached.
NAMED_FAILURES: tuple[tuple[str, str], ...] = (
    ("node", "Dublin"),
    ("node", "Athens"),
    ("node", "Warsaw"),
    ("node", "HUB-EAST"),
    ("node", "Berlin"),
    ("node", "Hamburg"),
    ("node", "Amsterdam"),
    ("link", "Berlin|Hamburg"),
    ("link", "Frankfurt|Munich"),
)


def failure_sets(
    name: str, kind: str
) -> tuple[frozenset[str], frozenset[frozenset[str]]]:
    if kind == "node":
        return frozenset({name}), frozenset()
    return frozenset(), frozenset({frozenset(name.split("|"))})


def main() -> int:
    net = load()
    print(
        f"nodes {len(net.nodes)}  links {len(net.capacity)}  demands {len(net.demands)}"
    )
    print(f"demand units {sum(v for _, _, v in net.demands)}")
    print()

    base = analyse(net)
    util = sorted(
        ((u, pair) for pair, u in base.utilisation(net).items()),
        key=lambda item: (-item[0], sorted(item[1])),
    )
    print("five most utilised links at rest:")
    for rank, (u, pair) in enumerate(util[:5], start=1):
        a, b = sorted(pair)
        print(f"  {rank}. {u * 100:5.1f}%  {a} to {b}  load {base.loads[pair]:.4f}")

    print("\nnamed failures:")
    for kind, name in NAMED_FAILURES:
        dead_nodes, dead_links = failure_sets(name, kind)
        scenario = analyse(net, dead_nodes, dead_links)
        fired = reasons(net, scenario)
        worst = max(scenario.utilisation(net).values(), default=0.0)
        print(
            f"  {kind:<5}{name:<20} components {scenario.components}  "
            f"undeliverable {len(scenario.undeliverable):<3} "
            f"peak {worst * 100:6.1f}%  {','.join(sorted(fired)) or 'not critical'}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
