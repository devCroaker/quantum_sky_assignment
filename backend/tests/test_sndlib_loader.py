"""Tests for the SNDlib XML loader.

Two halves. The first loads the real committed ``data/nobel-eu.xml`` and
checks it against the figures in the brief: 28 nodes, 41 links, 378 demands
and 1898 units. The second is a table of one small malformed fixture per
validation rule in R2, each asserting that the rejection names the file and
the line.

Every expected number here is sourced. The counts and the demand total come
from the brief's "verified facts" table. The individual coordinates, link
endpoints and demand extremes are quoted from the real file and the source
line is named where it matters. The line numbers in the malformed table are
counted off the fixture written immediately above them, which is why the
fixtures are laid out one element per line.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from netscope.errors import InputError
from netscope.loaders.sndlib_xml import ParsedBackbone, ParsedLink, load_backbone
from netscope.models import Coordinates, Endpoints, NodeKind

DATA = Path(__file__).resolve().parents[2] / "data"
SNDLIB = DATA / "nobel-eu.xml"


@pytest.fixture(scope="module")
def backbone() -> ParsedBackbone:
    return load_backbone(SNDLIB)


# --------------------------------------------------------------------------
# The real file
# --------------------------------------------------------------------------


def test_real_file_matches_the_counts_in_the_brief(backbone: ParsedBackbone) -> None:
    """28 / 41 / 378 and 1898 units, from the brief's verified facts table."""
    assert len(backbone.nodes) == 28
    assert len(backbone.links) == 41
    assert len(backbone.demands) == 378
    assert sum(demand.volume for demand in backbone.demands) == 1898.0


def test_every_backbone_node_is_a_city_that_may_forward_traffic(
    backbone: ParsedBackbone,
) -> None:
    """R6: file A contributes backbone cities only, and they all transit."""
    assert {node.kind for node in backbone.nodes} == {NodeKind.BACKBONE_CITY}
    assert all(node.can_transit for node in backbone.nodes)


def test_longitude_is_x_and_latitude_is_y(backbone: ParsedBackbone) -> None:
    """Asserted explicitly because the failure mode is silent and total.

    Quoted from data/nobel-eu.xml: Hamburg is <x>10.0</x><y>53.33</y> at
    lines 77 to 82, Warsaw is <x>20.59</x><y>52.14</y> at lines 155 to 160.
    Hamburg near 10 degrees east and 53 north and Warsaw near 21 east and 52
    north are both right for northern Europe. Reading them the other way
    round would place Hamburg at 53 east, in Kazakhstan, and would put most
    of the map in the sea, while every count above would still pass.
    """
    by_id = {node.id: node for node in backbone.nodes}

    assert by_id["Hamburg"].coordinates == Coordinates(x=10.0, y=53.33)
    assert by_id["Hamburg"].coordinates.longitude == 10.0
    assert by_id["Hamburg"].coordinates.latitude == 53.33

    assert by_id["Warsaw"].coordinates == Coordinates(x=20.59, y=52.14)
    assert by_id["Warsaw"].coordinates.longitude == 20.59
    assert by_id["Warsaw"].coordinates.latitude == 52.14

    # Every city in nobel-eu is in Europe, so latitude is the larger of the
    # two for all of them. A swap would break this for the whole file.
    assert all(node.coordinates.latitude > node.coordinates.longitude for node in backbone.nodes)


def test_a_known_link_round_trips(backbone: ParsedBackbone) -> None:
    """L12 is <source>Berlin</source><target>Hamburg</target> in the file.

    It is also the link the brief names as carrying the baseline peak, so
    getting its identity wrong would be expensive later.
    """
    by_id = {link.id: link for link in backbone.links}
    assert by_id["L12"].endpoints == Endpoints("Berlin", "Hamburg")
    # Link ids run L1 to L41, per the brief.
    assert [link.id for link in backbone.links] == [f"L{n}" for n in range(1, 42)]


def test_endpoints_come_back_sorted_whatever_order_the_file_used(
    backbone: ParsedBackbone,
) -> None:
    """R3: L39 is written <source>Zurich</source><target>Lyon</target>.

    It is the one link in the real file whose source sorts after its target,
    so it is the only real evidence available that Endpoints normalises
    rather than preserving file order.
    """
    by_id = {link.id: link for link in backbone.links}
    assert by_id["L39"].endpoints == Endpoints("Lyon", "Zurich")
    assert by_id["L39"].endpoints.a == "Lyon"
    assert by_id["L39"].endpoints == Endpoints("Zurich", "Lyon")
    assert all(link.endpoints.a < link.endpoints.b for link in backbone.links)


def test_demand_values_are_all_positive_and_span_the_expected_range(
    backbone: ParsedBackbone,
) -> None:
    """Minimum 2.0 and maximum 54.0, read off the real file by the brief."""
    volumes = [demand.volume for demand in backbone.demands]
    assert min(volumes) == 2.0
    assert max(volumes) == 54.0
    assert all(volume > 0 for volume in volumes)


def test_ids_are_unique_within_each_section(backbone: ParsedBackbone) -> None:
    """The brief states all ids in the file are unique, so none of the
    duplicate rules below should fire on the real input."""
    assert len({node.id for node in backbone.nodes}) == 28
    assert len({link.id for link in backbone.links}) == 41
    assert len({demand.id for demand in backbone.demands}) == 378
    # Undirected, so 378 distinct pairs, which is 28 choose 2.
    assert len({demand.endpoints for demand in backbone.demands}) == 378


def test_demand_ids_look_like_the_concatenated_pair(backbone: ParsedBackbone) -> None:
    """The brief gives AmsterdamAthens as the shape of a demand id."""
    assert backbone.demands[0].id == "AmsterdamAthens"
    assert backbone.demands[0].endpoints == Endpoints("Amsterdam", "Athens")


# --------------------------------------------------------------------------
# Capacity modules are not read at all (R3)
# --------------------------------------------------------------------------

# Namespaced, as the real file is, and carrying the <additionalModules> block
# that R3 tells us to ignore. The capacities here are invented for the
# fixture and must never reach the model, which is the point of the test.
WITH_MODULES = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network xmlns="http://sndlib.zib.de/network" version="1.0">
 <networkStructure>
  <nodes coordinatesType="geographical">
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1">
    <source>A</source>
    <target>B</target>
    <additionalModules>
     <addModule><capacity>20.0</capacity><cost>3580.0</cost></addModule>
     <addModule><capacity>40.0</capacity><cost>4580.0</cost></addModule>
    </additionalModules>
   </link>
  </links>
 </networkStructure>
 <demands>
  <demand id="AB"><source>A</source><target>B</target><demandValue>5.0</demandValue></demand>
 </demands>
</network>
"""


def _write(tmp_path: Path, body: str, name: str = "fixture.xml") -> Path:
    """Write a fixture so that its first line is the XML declaration."""
    path = tmp_path / name
    path.write_text(body.lstrip("\n"), encoding="ISO-8859-1")
    return path


def test_a_parsed_link_has_no_capacity_even_when_the_file_offers_one(
    tmp_path: Path,
) -> None:
    """R3: capacity modules are ignored, so ParsedLink has nowhere to put one.

    Asserting the absence of the field rather than a value is what proves the
    loader never looked: there is no 20.0 or 40.0 to compare against.
    """
    parsed = load_backbone(_write(tmp_path, WITH_MODULES))
    (link,) = parsed.links
    assert link == ParsedLink(id="L1", endpoints=Endpoints("A", "B"))
    assert not hasattr(link, "capacity")
    assert tuple(ParsedLink.__dataclass_fields__) == ("id", "endpoints")


def test_a_file_without_the_namespace_declaration_still_parses(tmp_path: Path) -> None:
    """Elements are matched on local name, so the declaration is optional.

    A namespace mismatch would otherwise be reported as a missing <nodes>
    section on a file whose nodes are plainly present.
    """
    plain = WITH_MODULES.replace(' xmlns="http://sndlib.zib.de/network"', "")
    assert load_backbone(_write(tmp_path, plain)).nodes[0].id == "A"


# --------------------------------------------------------------------------
# One malformed fixture per R2 rule
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Case:
    """One rejection: the fixture, the line it must name, and the reason."""

    rule: str
    xml: str
    line: int
    fragment: str


# Line numbers below were counted off each fixture, which is why every
# element sits on its own line. The declaration is line 1 in all of them.
NOT_XML = """
<?xml version="1.0"?>
<network>
 <networkStructure>
</network>
"""

NO_STRUCTURE = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network xmlns="http://sndlib.zib.de/network">
 <demands>
 </demands>
</network>
"""

NO_NODES = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <links>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

NO_LINKS = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
  </nodes>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

NO_DEMANDS = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
  </nodes>
  <links>
  </links>
 </networkStructure>
</network>
"""

NODE_WITHOUT_ID = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

DUPLICATE_NODE_ID = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="A"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

NODE_WITHOUT_COORDINATES = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"></node>
  </nodes>
  <links>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

NODE_WITH_NON_NUMERIC_X = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>east</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

NODE_WITHOUT_Y = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x></coordinates></node>
  </nodes>
  <links>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

NODE_WITH_A_NAN_COORDINATE = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>nan</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

LINK_WITHOUT_ID = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link><source>A</source><target>B</target></link>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

LINK_WITHOUT_SOURCE = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><target>B</target></link>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

LINK_WITH_UNKNOWN_TARGET = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><source>A</source><target>Atlantis</target></link>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

LINK_JOINING_A_NODE_TO_ITSELF = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><source>A</source><target>A</target></link>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

DUPLICATE_LINK_ID = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
   <node id="C"><coordinates><x>5.0</x><y>6.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><source>A</source><target>B</target></link>
   <link id="L1"><source>A</source><target>C</target></link>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

REVERSED_DUPLICATE_LINK_PAIR = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
   <node id="C"><coordinates><x>5.0</x><y>6.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><source>A</source><target>B</target></link>
   <link id="L2"><source>B</source><target>A</target></link>
  </links>
 </networkStructure>
 <demands>
 </demands>
</network>
"""

DEMAND_WITHOUT_ID = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><source>A</source><target>B</target></link>
  </links>
 </networkStructure>
 <demands>
  <demand><source>A</source><target>B</target><demandValue>5.0</demandValue></demand>
 </demands>
</network>
"""

DEMAND_WITH_UNKNOWN_SOURCE = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><source>A</source><target>B</target></link>
  </links>
 </networkStructure>
 <demands>
  <demand id="ZB"><source>Z</source><target>B</target><demandValue>5.0</demandValue></demand>
 </demands>
</network>
"""

DEMAND_FROM_A_NODE_TO_ITSELF = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><source>A</source><target>B</target></link>
  </links>
 </networkStructure>
 <demands>
  <demand id="AA"><source>A</source><target>A</target><demandValue>5.0</demandValue></demand>
 </demands>
</network>
"""

DUPLICATE_DEMAND_ID = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><source>A</source><target>B</target></link>
  </links>
 </networkStructure>
 <demands>
  <demand id="AB"><source>A</source><target>B</target><demandValue>5.0</demandValue></demand>
  <demand id="AB"><source>A</source><target>B</target><demandValue>7.0</demandValue></demand>
 </demands>
</network>
"""

DEMAND_WITHOUT_A_VALUE = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><source>A</source><target>B</target></link>
  </links>
 </networkStructure>
 <demands>
  <demand id="AB"><source>A</source><target>B</target></demand>
 </demands>
</network>
"""

DEMAND_WITH_NON_NUMERIC_VALUE = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><source>A</source><target>B</target></link>
  </links>
 </networkStructure>
 <demands>
  <demand id="AB"><source>A</source><target>B</target><demandValue>lots</demandValue></demand>
 </demands>
</network>
"""

DEMAND_WITH_A_ZERO_VALUE = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><source>A</source><target>B</target></link>
  </links>
 </networkStructure>
 <demands>
  <demand id="AB"><source>A</source><target>B</target><demandValue>0.0</demandValue></demand>
 </demands>
</network>
"""

DEMAND_WITH_A_NEGATIVE_VALUE = """
<?xml version="1.0" encoding="ISO-8859-1"?>
<network>
 <networkStructure>
  <nodes>
   <node id="A"><coordinates><x>1.0</x><y>2.0</y></coordinates></node>
   <node id="B"><coordinates><x>3.0</x><y>4.0</y></coordinates></node>
  </nodes>
  <links>
   <link id="L1"><source>A</source><target>B</target></link>
  </links>
 </networkStructure>
 <demands>
  <demand id="AB"><source>A</source><target>B</target><demandValue>-5.0</demandValue></demand>
 </demands>
</network>
"""

MALFORMED: tuple[_Case, ...] = (
    # Reported at the line ElementTree's own ParseError gives, which is the
    # mismatched </network> on line 4.
    _Case("not valid XML", NOT_XML, 4, "is not valid XML"),
    # A missing section has no line of its own, so it is reported at the
    # parent that should have held it: <network> on line 2 for the two
    # sections directly under the root, <networkStructure> on line 3 for the
    # two sections inside it.
    _Case("no networkStructure", NO_STRUCTURE, 2, "has no <networkStructure> section"),
    _Case("no nodes", NO_NODES, 3, "has no <nodes> section"),
    _Case("no links", NO_LINKS, 3, "has no <links> section"),
    _Case("no demands", NO_DEMANDS, 2, "has no <demands> section"),
    # Line 6 is the second <node> in each of these fixtures. An element with
    # no id is found by its position among its siblings; one with an id is
    # found by the line its id attribute appears on, which is the same line.
    _Case("node with no id", NODE_WITHOUT_ID, 6, "has a <node> with no id"),
    _Case("duplicate node id", DUPLICATE_NODE_ID, 6, "declares node 'A' twice"),
    _Case("node with no coordinates", NODE_WITHOUT_COORDINATES, 6, "has no <coordinates>"),
    _Case("node with non-numeric x", NODE_WITH_NON_NUMERIC_X, 6, "non-numeric <x>: 'east'"),
    _Case("node with no y", NODE_WITHOUT_Y, 6, "has no <y>"),
    # float() accepts "nan", and a NaN is neither positive nor negative, so
    # it would slip through a plain range check and poison every later sum.
    _Case("node with a NaN coordinate", NODE_WITH_A_NAN_COORDINATE, 6, "non-numeric <x>: 'nan'"),
    # Line 9 is the only <link> in each of these.
    _Case("link with no id", LINK_WITHOUT_ID, 9, "has a <link> with no id"),
    _Case("link with no source", LINK_WITHOUT_SOURCE, 9, "has no <source>"),
    _Case("link with unknown target", LINK_WITH_UNKNOWN_TARGET, 9, "unknown node 'Atlantis'"),
    _Case("link joining a node to itself", LINK_JOINING_A_NODE_TO_ITSELF, 9, "to itself"),
    # These two fixtures carry a third node, so the offending link sits on
    # line 11 rather than line 10.
    _Case("duplicate link id", DUPLICATE_LINK_ID, 11, "declares link 'L1' twice"),
    _Case("reversed duplicate link pair", REVERSED_DUPLICATE_LINK_PAIR, 11, "repeats the pair"),
    # Line 13 is the only <demand>, except in the duplicate fixture where the
    # second copy is on line 14.
    _Case("demand with no id", DEMAND_WITHOUT_ID, 13, "has a <demand> with no id"),
    _Case("demand with unknown source", DEMAND_WITH_UNKNOWN_SOURCE, 13, "unknown node 'Z'"),
    _Case("demand from a node to itself", DEMAND_FROM_A_NODE_TO_ITSELF, 13, "to itself"),
    _Case("duplicate demand id", DUPLICATE_DEMAND_ID, 14, "declares demand 'AB' twice"),
    _Case("demand with no value", DEMAND_WITHOUT_A_VALUE, 13, "has no <demandValue>"),
    _Case(
        "demand with non-numeric value",
        DEMAND_WITH_NON_NUMERIC_VALUE,
        13,
        "non-numeric <demandValue>: 'lots'",
    ),
    _Case("demand with a zero value", DEMAND_WITH_A_ZERO_VALUE, 13, "is not positive: 0.0"),
    _Case(
        "demand with a negative value",
        DEMAND_WITH_A_NEGATIVE_VALUE,
        13,
        "is not positive: -5.0",
    ),
)


@pytest.mark.parametrize("case", MALFORMED, ids=[case.rule for case in MALFORMED])
def test_malformed_input_is_rejected_with_the_file_and_the_line(
    case: _Case, tmp_path: Path
) -> None:
    """R2: one rule per row, each naming the file and the offending line."""
    path = _write(tmp_path, case.xml, name="broken.xml")

    with pytest.raises(InputError) as raised:
        load_backbone(path)

    message = str(raised.value)
    assert "broken.xml" in message
    assert f"line {case.line}" in message, message
    assert case.fragment in message
    assert raised.value.line == case.line


def test_a_missing_file_is_an_input_error_naming_it(tmp_path: Path) -> None:
    """Reported at line 1 rather than with no line at all.

    R2 wants every rejection locatable, and a caller that has to special-case
    one error with no position is worse served than one pointed at the start
    of a file that is not there.
    """
    missing = tmp_path / "absent.xml"

    with pytest.raises(InputError) as raised:
        load_backbone(missing)

    assert "absent.xml" in str(raised.value)
    assert raised.value.line == 1
    assert "cannot be read" in str(raised.value)


def test_the_field_is_named_when_one_element_is_at_fault(tmp_path: Path) -> None:
    """R2 asks for the location. The field turns "line 6" into an instruction."""
    with pytest.raises(InputError) as raised:
        load_backbone(_write(tmp_path, NODE_WITH_NON_NUMERIC_X))

    assert raised.value.field == "x"
    assert "column 'x'" in str(raised.value)


def test_a_bad_file_never_escapes_as_a_model_value_error(tmp_path: Path) -> None:
    """D15: the model's ValueError means a programming mistake, not bad input.

    A self-loop is the case where the two could be confused, because
    Endpoints raises ValueError for it. The loader must reject it first.
    """
    for body in (LINK_JOINING_A_NODE_TO_ITSELF, DEMAND_FROM_A_NODE_TO_ITSELF):
        with pytest.raises(InputError):
            load_backbone(_write(tmp_path, body))
