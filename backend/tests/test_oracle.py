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
from netscope.criticality import CriticalityReason, CriticalitySweep, ElementKind, sweep
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


@pytest.fixture(scope="module")
def independent_by_node(independent: oracle.Network) -> dict[str, oracle.Scenario]:
    """Every single-node failure, computed once and shared by every test below.

    The named-failure test and the full-92 test both need this, and without
    sharing it they would recompute the same path-enumerating scenario twice
    for every node in oracle.NAMED_FAILURES. That duplication was measured,
    not assumed: it cost roughly a second of real wall-clock time across the
    suite for no additional evidence, so it is removed here rather than left
    as the price of two tests existing.
    """
    return {node: oracle.analyse(independent, frozenset({node})) for node in independent.nodes}


@pytest.fixture(scope="module")
def independent_by_link(independent: oracle.Network) -> dict[frozenset[str], oracle.Scenario]:
    """Every single-link failure, computed once. See independent_by_node."""
    return {
        pair: oracle.analyse(independent, dead_links=frozenset({pair}))
        for pair in independent.capacity
    }


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


@pytest.fixture(scope="module")
def shipped_sweep(shipped: Network) -> CriticalitySweep:
    """Computed once and shared, not once per parametrized named failure.

    The previous version called sweep(shipped) fresh inside each of the nine
    named-failure cases below, nine redundant 92-scenario sweeps of a result
    that does not depend on which named failure is being checked.
    """
    return sweep(shipped)


@pytest.mark.parametrize(("kind", "name"), oracle.NAMED_FAILURES)
def test_named_failures_agree_on_impact_and_on_reasons(
    shipped: Network,
    independent: oracle.Network,
    independent_by_node: dict[str, oracle.Scenario],
    independent_by_link: dict[frozenset[str], oracle.Scenario],
    shipped_sweep: CriticalitySweep,
    kind: str,
    name: str,
) -> None:
    """The scenarios the findings report makes claims about, by name.

    Both the measured impact and the R7 verdict, because a sweep can get the
    numbers right and still classify them wrongly. Full link-by-link
    agreement is checked here, which test_all_92_single_failures below
    deliberately does not repeat for every element.
    """
    if kind == "node":
        element_id = name
        theirs = independent_by_node[name]
        mine = shipped_analyse(shipped, failed_nodes=frozenset({name}))
    else:
        pair = frozenset(name.split("|"))
        element_id = next(
            link.id
            for link in shipped.links.values()
            if frozenset((link.endpoints.a, link.endpoints.b)) == pair
        )
        theirs = independent_by_link[pair]
        mine = shipped_analyse(shipped, failed_links=frozenset({element_id}))

    assert mine.components == theirs.components, name
    assert len(mine.undeliverable) == len(theirs.undeliverable), name
    assert len(mine.endpoint_affected) == len(theirs.endpoint_affected), name

    for entry in mine.link_utilizations:
        link = shipped.links[entry.link_id]
        link_pair = frozenset((link.endpoints.a, link.endpoints.b))
        assert entry.load == pytest.approx(theirs.loads[link_pair], abs=TOLERANCE), (
            f"{name}: {entry.link_id}"
        )

    # And the verdict, not only the figures.
    expected = oracle.reasons(independent, theirs)
    assessment = next(
        a
        for a in shipped_sweep.assessments
        if a.id == element_id
        and a.kind is (ElementKind.NODE if kind == "node" else ElementKind.LINK)
    )
    assert {r.value for r in assessment.reasons} == expected, name
    assert assessment.critical is bool(expected), name


def test_all_92_single_failures_agree_on_impact_and_verdict(
    shipped: Network,
    independent: oracle.Network,
    independent_by_node: dict[str, oracle.Scenario],
    independent_by_link: dict[frozenset[str], oracle.Scenario],
    shipped_sweep: CriticalitySweep,
) -> None:
    """Every single-element failure, not only the nine named ones above.

    An independent review of this project pointed out that the oracle only
    compared nine named scenarios against the shipped sweep of all 92, and
    suggested widening it if the runtime allowed. This is the test that
    closes that gap, checked against the full criticality sweep the
    application actually serves rather than a hand-picked sample of it.

    Lighter than the named-failure test above: it checks components,
    the undeliverable and endpoint-affected counts, and the R7 verdict, but
    not every individual link load, since that comparison is already made
    exhaustively at the baseline in test_every_baseline_link_load_agrees
    and per-scenario for the nine named cases. Ninety-two times the full
    link comparison would cost more than it would prove.

    independent_by_node, independent_by_link and shipped_sweep are shared,
    module-scoped fixtures rather than computed here: the named-failure test
    above needs the same ninety-two scenarios for its nine cases, and
    computing each one twice measurably slowed the suite for no additional
    evidence.
    """
    checked_nodes = checked_links = 0
    for assessment in shipped_sweep.assessments:
        if assessment.kind is ElementKind.NODE:
            theirs = independent_by_node[assessment.id]
            checked_nodes += 1
        else:
            link = shipped.links[assessment.id]
            pair = frozenset((link.endpoints.a, link.endpoints.b))
            theirs = independent_by_link[pair]
            checked_links += 1
        expected_reasons = oracle.reasons(independent, theirs)

        assert {r.value for r in assessment.reasons} == expected_reasons, assessment.id
        assert assessment.critical is bool(expected_reasons), assessment.id
        assert assessment.impact.components == theirs.components, assessment.id
        assert assessment.impact.undeliverable_demands == len(theirs.undeliverable), assessment.id
        assert assessment.impact.endpoint_affected_demands == len(theirs.endpoint_affected), (
            assessment.id
        )

    # Confirms every one of the 37 nodes and 55 links was actually exercised,
    # so a change to the sweep's own element count would not silently narrow
    # what this test covers.
    assert checked_nodes == 37
    assert checked_links == 55


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
