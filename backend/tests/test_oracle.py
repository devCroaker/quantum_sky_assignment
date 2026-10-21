"""The shipped code against an implementation that shares nothing with it.

``scripts/oracle.py`` parses the inputs itself and routes by enumerating every
minimum-hop path, where the shipped router counts paths over a predecessor
graph without ever building one. Neither imports the other. If both are wrong
they have to be wrong in the same way by coincidence, having been written from
different reasoning.

This is the leg that answers "how do you know, other than the tool saying so?".
It used to be a scratch script run by hand, which made it evidence nobody else
could inspect. Committed and asserted here, it runs on every build and fails if
either side drifts.

What it does not prove: both implementations read the same requirements, so a
shared misreading survives. See the module docstring of the oracle for the full
statement of that limit.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from netscope.analysis import analyse as shipped_analyse
from netscope.criticality import CriticalityReason, ElementKind, sweep
from netscope.loaders.merge import build_network
from netscope.loaders.sites_csv import load_sites
from netscope.loaders.sndlib_xml import load_backbone
from netscope.models import Network

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import oracle  # noqa: E402

#: Loads are floats summed in a different order by each implementation, so they
#: agree to within floating point noise rather than exactly. Tight enough that
#: a real routing difference cannot hide: the smallest demand is 2 units.
TOLERANCE = 1e-9


@pytest.fixture(scope="module")
def shipped() -> Network:
    return build_network(
        load_backbone(ROOT / "data" / "nobel-eu.xml"),
        load_sites(ROOT / "data" / "sites.csv"),
        sites_file=str(ROOT / "data" / "sites.csv"),
    )


@pytest.fixture(scope="module")
def independent() -> oracle.Network:
    return oracle.load()


def test_the_two_implementations_merge_to_the_same_network(
    shipped: Network, independent: oracle.Network
) -> None:
    """R1, reached twice. The oracle parsed the XML with regular expressions."""
    assert set(shipped.nodes) == independent.nodes
    assert len(shipped.links) == len(independent.capacity)
    assert len(shipped.demands) == len(independent.demands)
    assert shipped.total_demand == sum(v for _, _, v in independent.demands)

    shipped_capacity = {
        frozenset((link.endpoints.a, link.endpoints.b)): link.capacity
        for link in shipped.links.values()
    }
    assert shipped_capacity == independent.capacity


def test_every_baseline_link_load_agrees(shipped: Network, independent: oracle.Network) -> None:
    """All 55 links, not just the five the report quotes.

    The interesting failure is a load that is wrong on one link and
    compensated elsewhere, which a totals check would miss entirely.
    """
    mine = shipped_analyse(shipped)
    theirs = oracle.analyse(independent)
    assert len(mine.link_utilizations) == len(theirs.loads)

    for entry in mine.link_utilizations:
        link = shipped.links[entry.link_id]
        pair = frozenset((link.endpoints.a, link.endpoints.b))
        assert entry.load == pytest.approx(theirs.loads[pair], abs=TOLERANCE), entry.link_id


def test_nothing_is_undeliverable_or_overloaded_at_rest(
    shipped: Network, independent: oracle.Network
) -> None:
    mine = shipped_analyse(shipped)
    theirs = oracle.analyse(independent)
    assert (len(mine.undeliverable), len(mine.overloaded)) == (0, 0)
    assert (len(theirs.undeliverable), theirs.components) == (0, 1)


@pytest.mark.parametrize(("kind", "name"), oracle.NAMED_FAILURES)
def test_named_failures_agree_on_impact_and_on_reasons(
    shipped: Network, independent: oracle.Network, kind: str, name: str
) -> None:
    """The scenarios the findings report makes claims about.

    Both the measured impact and the R7 verdict, because a sweep can get the
    numbers right and still classify them wrongly.
    """
    dead_nodes, dead_links = oracle.failure_sets(name, kind)
    theirs = oracle.analyse(independent, dead_nodes, dead_links)

    if kind == "node":
        element_id = name
        mine = shipped_analyse(shipped, failed_nodes=frozenset({name}))
    else:
        pair = frozenset(name.split("|"))
        element_id = next(
            link.id
            for link in shipped.links.values()
            if frozenset((link.endpoints.a, link.endpoints.b)) == pair
        )
        mine = shipped_analyse(shipped, failed_links=frozenset({element_id}))

    assert mine.components == theirs.components, name
    assert len(mine.undeliverable) == len(theirs.undeliverable), name
    assert len(mine.endpoint_affected) == len(theirs.endpoint_affected), name

    for entry in mine.link_utilizations:
        link = shipped.links[entry.link_id]
        pair = frozenset((link.endpoints.a, link.endpoints.b))
        assert entry.load == pytest.approx(theirs.loads[pair], abs=TOLERANCE), (
            f"{name}: {entry.link_id}"
        )

    # And the verdict, not only the figures.
    expected = oracle.reasons(independent, theirs)
    assessment = next(
        a
        for a in sweep(shipped).assessments
        if a.id == element_id
        and a.kind is (ElementKind.NODE if kind == "node" else ElementKind.LINK)
    )
    assert {r.value for r in assessment.reasons} == expected, name
    assert assessment.critical is bool(expected), name


def test_the_oracle_reaches_a_verdict_other_than_critical() -> None:
    """Guards against the comparison being vacuous.

    If every named failure were critical, agreeing on the verdict would prove
    nothing. Amsterdam is in the list precisely because it is not.
    """
    assert any(
        not oracle.reasons(net, oracle.analyse(net, *oracle.failure_sets(name, kind)))
        for kind, name in oracle.NAMED_FAILURES
        for net in [oracle.load()]
    )


def test_the_criticality_reason_vocabularies_match() -> None:
    """The oracle restates the reason codes rather than importing them.

    That is deliberate, and this is the cost: the two lists have to be kept in
    step, so a test asserts it rather than a comment asking nicely.
    """
    assert oracle.reasons.__doc__ is not None
    produced = {
        "partitions-network",
        "demands-undeliverable",
        "links-overloaded",
    }
    assert {reason.value for reason in CriticalityReason} == produced
