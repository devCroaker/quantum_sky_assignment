"""The three invariants the domain model exists to enforce.

Undirectedness (R3), transit eligibility by node kind (R6), and referential
wholeness. Each is tested at the model layer so that no loader, router or
endpoint has to defend against a violation.
"""

from __future__ import annotations

import pytest

from netscope.models import (
    Coordinates,
    Demand,
    Endpoints,
    Link,
    LinkKind,
    Network,
    Node,
    NodeKind,
)


class TestEndpointsAreUndirected:
    def test_either_construction_order_gives_the_same_value(self) -> None:
        assert Endpoints("Paris", "Lyon") == Endpoints("Lyon", "Paris")

    def test_the_pair_is_stored_sorted(self) -> None:
        for pair in (Endpoints("Paris", "Lyon"), Endpoints("Lyon", "Paris")):
            assert (pair.a, pair.b) == ("Lyon", "Paris")

    def test_reversed_pairs_collapse_to_one_dictionary_key(self) -> None:
        """This is the property the loaders rely on to spot a duplicate link."""
        seen = {Endpoints("Paris", "Lyon"): 1, Endpoints("Lyon", "Paris"): 2}
        assert len(seen) == 1
        assert seen[Endpoints("Paris", "Lyon")] == 2

    def test_a_self_loop_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="distinct"):
            Endpoints("Paris", "Paris")

    def test_other_returns_the_far_end(self) -> None:
        pair = Endpoints("Paris", "Lyon")
        assert pair.other("Paris") == "Lyon"
        assert pair.other("Lyon") == "Paris"

    def test_other_rejects_a_node_that_is_not_on_the_link(self) -> None:
        with pytest.raises(KeyError):
            Endpoints("Paris", "Lyon").other("Madrid")

    def test_membership_and_iteration(self) -> None:
        pair = Endpoints("Paris", "Lyon")
        assert "Paris" in pair
        assert "Madrid" not in pair
        assert list(pair) == ["Lyon", "Paris"]


class TestTransitEligibility:
    """R6: only backbone cities and the aggregation hub forward traffic."""

    def test_backbone_cities_and_the_hub_forward(self) -> None:
        assert NodeKind.BACKBONE_CITY.can_transit
        assert NodeKind.AGGREGATION_HUB.can_transit

    def test_data_centers_and_operations_sites_do_not(self) -> None:
        assert not NodeKind.DATA_CENTER.can_transit
        assert not NodeKind.OPERATIONS_SITE.can_transit

    def test_every_kind_has_an_answer(self) -> None:
        """A new node kind must make a deliberate choice, not inherit one."""
        assert {kind: kind.can_transit for kind in NodeKind} == {
            NodeKind.BACKBONE_CITY: True,
            NodeKind.AGGREGATION_HUB: True,
            NodeKind.DATA_CENTER: False,
            NodeKind.OPERATIONS_SITE: False,
        }

    def test_a_node_defers_to_its_kind(self) -> None:
        node = Node("OPS-WEST", NodeKind.OPERATIONS_SITE, Coordinates(-6.15, 53.21))
        assert not node.can_transit

    def test_the_wire_value_of_a_kind_matches_the_csv_vocabulary(self) -> None:
        """sites.csv writes these strings, so the enum must spell them the same."""
        assert NodeKind.AGGREGATION_HUB.value == "aggregation-hub"
        assert NodeKind.OPERATIONS_SITE.value == "operations-site"
        assert NodeKind.DATA_CENTER.value == "data-center"
        assert NodeKind.BACKBONE_CITY.value == "backbone-city"


def _node(node_id: str, kind: NodeKind = NodeKind.BACKBONE_CITY) -> Node:
    return Node(node_id, kind, Coordinates(0.0, 0.0))


class TestNetworkIsReferentiallyWhole:
    def test_a_link_naming_an_unknown_node_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown node 'Atlantis'"):
            Network(
                nodes={"Paris": _node("Paris")},
                links={"L1": Link("L1", Endpoints("Paris", "Atlantis"), 550, LinkKind.BACKBONE)},
                demands=[],
            )

    def test_a_demand_naming_an_unknown_node_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown node 'Atlantis'"):
            Network(
                nodes={"Paris": _node("Paris")},
                links={},
                demands=[Demand("D1", Endpoints("Paris", "Atlantis"), 10)],
            )

    def test_a_link_needs_positive_capacity(self) -> None:
        with pytest.raises(ValueError, match="positive capacity"):
            Link("L1", Endpoints("Paris", "Lyon"), 0, LinkKind.BACKBONE)

    def test_a_demand_needs_positive_volume(self) -> None:
        with pytest.raises(ValueError, match="positive volume"):
            Demand("D1", Endpoints("Paris", "Lyon"), 0)


class TestDerivedViews:
    """A four-node fixture small enough to check the expected values by eye.

        OPS -- Paris -- Lyon -- Milan

    Paris and Lyon are backbone cities and may forward. OPS is an operations
    site and may not. Milan is a backbone city.
    """

    @staticmethod
    def fixture() -> Network:
        nodes = {
            "OPS": _node("OPS", NodeKind.OPERATIONS_SITE),
            "Paris": _node("Paris"),
            "Lyon": _node("Lyon"),
            "Milan": _node("Milan"),
        }
        links = {
            "ACC-OPS-Paris": Link("ACC-OPS-Paris", Endpoints("OPS", "Paris"), 40, LinkKind.ACCESS),
            "L1": Link("L1", Endpoints("Paris", "Lyon"), 550, LinkKind.BACKBONE),
            "L2": Link("L2", Endpoints("Lyon", "Milan"), 550, LinkKind.BACKBONE),
        }
        demands = [Demand("D1", Endpoints("OPS", "Milan"), 10)]
        return Network(nodes=nodes, links=links, demands=demands)

    def test_adjacency_is_symmetric_and_names_the_link(self) -> None:
        network = self.fixture()
        assert network.adjacency["Paris"] == {"OPS": "ACC-OPS-Paris", "Lyon": "L1"}
        assert network.adjacency["Lyon"] == {"Paris": "L1", "Milan": "L2"}
        assert network.adjacency["Milan"] == {"Lyon": "L2"}

    def test_an_isolated_node_still_appears_in_adjacency(self) -> None:
        """Routing iterates adjacency, so a missing key would be a crash."""
        network = Network(nodes={"Lone": _node("Lone")}, links={}, demands=[])
        assert network.adjacency == {"Lone": {}}

    def test_links_are_findable_by_their_endpoints_in_either_order(self) -> None:
        network = self.fixture()
        assert network.link_by_endpoints[Endpoints("Lyon", "Paris")] == "L1"

    def test_transit_nodes_exclude_the_operations_site(self) -> None:
        assert self.fixture().transit_nodes == frozenset({"Paris", "Lyon", "Milan"})

    def test_total_demand_sums_the_volumes(self) -> None:
        assert self.fixture().total_demand == 10
