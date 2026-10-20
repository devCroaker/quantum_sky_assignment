"""Read the SNDlib ``nobel-eu`` XML: nodes with coordinates, links, demands.

What this loader deliberately does not do
-----------------------------------------
It does not read ``<additionalModules>``. R3 says every backbone link carries
550 units and the capacity modules in the file are ignored, so ``ParsedLink``
has no capacity field at all. Applying the 550 is the merge's job in P7, not
this loader's, and leaving the field off is what makes that impossible to get
wrong here.

Locating a rejection (R2)
-------------------------
R2 asks for an error naming the file and the row. XML has no rows, so every
rejection carries a line number instead, which is the working answer recorded
under "Open questions" in ``docs/DECISIONS.md``.

``ElementTree`` does not expose line numbers through its public API, and
neither a private attribute nor a second XML library is worth the cost of
that one number. Instead the raw bytes are scanned once, before parsing, to
record the line of every ``id="..."`` attribute and the line of every opening
tag. An element with an id is reported at its own line; an element missing the
id that would identify it is reported at its position among its siblings; a
missing section is reported at the line of the parent that should have
contained it.

Namespaces
----------
The real file declares ``http://sndlib.zib.de/network``. Elements are matched
on local name, so a file that omits the declaration still parses. A namespace
mismatch would otherwise surface as "missing <nodes>" on a file whose nodes
are plainly there, which is a worse error than no error.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Final
from xml.etree.ElementTree import Element, ParseError, fromstring

from netscope.errors import InputError
from netscope.models import Coordinates, Demand, Endpoints, Node, NodeKind

__all__ = ["ParsedBackbone", "ParsedLink", "load_backbone"]


@dataclass(frozen=True, slots=True)
class ParsedLink:
    """A backbone link as the file states it: an id and an unordered pair.

    No capacity. R3 sets every backbone link to 550 and that happens in the
    merge, so there is nowhere here for a capacity module to leak in.
    """

    id: str
    endpoints: Endpoints


@dataclass(frozen=True, slots=True)
class ParsedBackbone:
    """Everything file A contributes, in file order."""

    nodes: tuple[Node, ...]
    links: tuple[ParsedLink, ...]
    demands: tuple[Demand, ...]


def load_backbone(path: Path) -> ParsedBackbone:
    """Parse ``path`` as an SNDlib network file.

    Raises:
        InputError: on any content this loader will not vouch for, naming the
            file, the line, and the attribute or element at fault when one
            element is clearly responsible.
    """
    name = str(path)
    raw = _read_bytes(path, name)
    index = _index_lines(raw)
    root = _parse(raw, name)

    structure = _require_section(root, "networkStructure", name, index, parent_tag="network")
    nodes_element = _require_section(structure, "nodes", name, index, parent_tag="networkStructure")
    links_element = _require_section(structure, "links", name, index, parent_tag="networkStructure")
    # The real file closes </networkStructure> before opening <demands>, so
    # demands are a sibling of the structure and not a child of it. Looking
    # under the structure as a fallback costs nothing and accepts both shapes.
    demands_element = _find_demands(root, structure, name, index)

    nodes = _parse_nodes(nodes_element, name, index)
    known = {node.id for node in nodes}
    links = _parse_links(links_element, name, index, known)
    demands = _parse_demands(demands_element, name, index, known)
    return ParsedBackbone(nodes=nodes, links=links, demands=demands)


# --------------------------------------------------------------------------
# Line index
# --------------------------------------------------------------------------

# An opening tag: "<node id=", "<nodes>", "<coordinates>". The leading "<?xml"
# declaration and closing "</node>" tags do not match, which is what keeps the
# positional lists aligned with the elements ElementTree reports.
_OPEN_TAG: Final = re.compile(r"<([A-Za-z_][\w.-]*)[\s/>]")
_ID_ATTRIBUTE: Final = re.compile(r'\bid="([^"]*)"')

# Reported when nothing better is known, for instance a file that is not XML
# at all or one whose root element is missing.
_FIRST_LINE: Final = 1


@dataclass(frozen=True, slots=True)
class _LineIndex:
    """Where things are in the raw file, by id and by document position."""

    by_id: Mapping[str, int]
    by_tag: Mapping[str, Sequence[int]]

    def of_tag(self, tag: str, position: int = 0) -> int:
        lines = self.by_tag.get(tag, ())
        if position < len(lines):
            return lines[position]
        return _FIRST_LINE

    def locate(self, element_id: str | None, tag: str, position: int) -> int:
        """The best line for one element: its own id, else its position."""
        if element_id is not None:
            line = self.by_id.get(element_id)
            if line is not None:
                return line
        return self.of_tag(tag, position)


def _index_lines(raw: bytes) -> _LineIndex:
    """Scan the raw bytes once for id attributes and opening tags.

    Decoding is ISO-8859-1 because it cannot fail and maps one byte to one
    character, so line boundaries and the ASCII patterns above are exact
    whatever the file's declared encoding turns out to be. An id containing
    non-ASCII bytes would therefore be indexed under a mis-decoded key and
    simply not be found later, at which point ``locate`` falls back to the
    element's position. SNDlib ids are ASCII, so that path is theoretical.
    """
    by_id: dict[str, int] = {}
    by_tag: dict[str, list[int]] = {}
    for number, line in enumerate(raw.decode("ISO-8859-1").splitlines(), start=_FIRST_LINE):
        for tag in _OPEN_TAG.finditer(line):
            by_tag.setdefault(tag.group(1), []).append(number)
        for attribute in _ID_ATTRIBUTE.finditer(line):
            # First occurrence wins. A duplicate id therefore cannot be
            # located through this mapping, which is why the duplicate checks
            # below report the offending element's own position instead.
            by_id.setdefault(attribute.group(1), number)
    return _LineIndex(by_id=by_id, by_tag=by_tag)


# --------------------------------------------------------------------------
# Reading and structure
# --------------------------------------------------------------------------


def _read_bytes(path: Path, name: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        # Line 1 rather than no line: R2 wants every rejection locatable, and
        # a caller that has to special-case "this one has no line" is worse
        # than pointing at the start of a file that is not there.
        raise InputError(name, f"cannot be read: {error.strerror}", line=_FIRST_LINE) from error


def _parse(raw: bytes, name: str) -> Element:
    """Parse the bytes, letting the declared encoding do its job.

    ``fromstring`` on bytes honours the XML declaration, which is how the
    real file's ISO-8859-1 author names survive.
    """
    try:
        return fromstring(raw)
    except ParseError as error:
        line, column = error.position
        raise InputError(
            name, f"is not valid XML: {error.msg} at column {column}", line=line
        ) from error
    except ValueError as error:
        # Raised when the declaration names an encoding Python cannot find.
        raise InputError(name, f"is not valid XML: {error}", line=_FIRST_LINE) from error


def _local(tag: str) -> str:
    """The tag without its ``{namespace}`` prefix."""
    return tag.rpartition("}")[2]


def _children(parent: Element, name: str) -> list[Element]:
    return [child for child in parent if _local(child.tag) == name]


def _child(parent: Element, name: str) -> Element | None:
    found = _children(parent, name)
    return found[0] if found else None


def _require_section(
    parent: Element, name: str, file: str, index: _LineIndex, *, parent_tag: str
) -> Element:
    """A required child section, reported at its parent's line when absent.

    Pointing at the parent is the useful location for a missing section:
    there is no line of its own to point at, and the parent is where it
    should have been written.
    """
    found = _child(parent, name)
    if found is None:
        raise InputError(
            file,
            f"has no <{name}> section",
            line=index.of_tag(parent_tag),
            field=name,
        )
    return found


def _find_demands(root: Element, structure: Element, file: str, index: _LineIndex) -> Element:
    # Compared against None rather than tested for truth: an element with no
    # children is falsy, so an empty <demands> section would read as absent.
    found = _child(root, "demands")
    if found is None:
        found = _child(structure, "demands")
    if found is None:
        raise InputError(
            file,
            "has no <demands> section",
            line=index.of_tag("network"),
            field="demands",
        )
    return found


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------


def _element_id(element: Element, file: str, index: _LineIndex, *, tag: str, position: int) -> str:
    """The ``id`` attribute, or a rejection naming the line it is missing from."""
    element_id = element.get("id")
    if element_id is None or not element_id.strip():
        raise InputError(
            file,
            f"has a <{tag}> with no id",
            line=index.of_tag(tag, position),
            field="id",
        )
    return element_id


def _text(element: Element, name: str) -> str | None:
    child = _child(element, name)
    if child is None or child.text is None:
        return None
    stripped = child.text.strip()
    return stripped or None


def _number(raw: str | None, file: str, *, line: int, field: str, owner: str) -> float:
    if raw is None:
        raise InputError(file, f"{owner} has no <{field}>", line=line, field=field)
    try:
        value = float(raw)
    except ValueError as error:
        raise InputError(
            file, f"{owner} has a non-numeric <{field}>: {raw!r}", line=line, field=field
        ) from error
    # float() also accepts "nan" and "inf". Neither is a coordinate or a
    # volume, and a NaN would pass every later comparison silently: it is
    # neither positive nor negative, so a NaN demand would survive the
    # positivity check below and poison every total computed from it.
    if not isfinite(value):
        raise InputError(
            file, f"{owner} has a non-numeric <{field}>: {raw!r}", line=line, field=field
        )
    return value


def _parse_nodes(section: Element, file: str, index: _LineIndex) -> tuple[Node, ...]:
    nodes: list[Node] = []
    seen: set[str] = set()
    for position, element in enumerate(_children(section, "node")):
        node_id = _element_id(element, file, index, tag="node", position=position)
        line = index.locate(node_id, "node", position)
        if node_id in seen:
            # Point at the second copy, not the first: the first one is fine.
            raise InputError(
                file,
                f"declares node {node_id!r} twice",
                line=index.of_tag("node", position),
                field="id",
            )
        seen.add(node_id)

        coordinates = _child(element, "coordinates")
        if coordinates is None:
            raise InputError(
                file,
                f"node {node_id!r} has no <coordinates>",
                line=line,
                field="coordinates",
            )
        owner = f"node {node_id!r}"
        # SNDlib names longitude x and latitude y. Swapping them would put
        # the whole map in the Atlantic, so the mapping is stated once here
        # and asserted in the tests against two known cities.
        longitude = _number(_text(coordinates, "x"), file, line=line, field="x", owner=owner)
        latitude = _number(_text(coordinates, "y"), file, line=line, field="y", owner=owner)
        nodes.append(
            Node(
                id=node_id,
                kind=NodeKind.BACKBONE_CITY,
                coordinates=Coordinates(x=longitude, y=latitude),
            )
        )
    return tuple(nodes)


def _endpoints(
    element: Element,
    file: str,
    *,
    line: int,
    owner: str,
    known: frozenset[str],
) -> Endpoints:
    """Resolve <source> and <target> into a canonical pair.

    Both ends are checked against the declared nodes and against each other
    before ``Endpoints`` is constructed. Per D15 the model raises
    ``ValueError`` for a self-loop, which is a programming mistake; a
    self-loop in a file is bad input and belongs here as an ``InputError``.
    """
    ends: dict[str, str] = {}
    for field in ("source", "target"):
        value = _text(element, field)
        if value is None:
            raise InputError(file, f"{owner} has no <{field}>", line=line, field=field)
        if value not in known:
            raise InputError(
                file,
                f"{owner} names unknown node {value!r} as its {field}",
                line=line,
                field=field,
            )
        ends[field] = value
    if ends["source"] == ends["target"]:
        raise InputError(
            file,
            f"{owner} joins {ends['source']!r} to itself",
            line=line,
            field="target",
        )
    return Endpoints(ends["source"], ends["target"])


def _parse_links(
    section: Element, file: str, index: _LineIndex, known: set[str]
) -> tuple[ParsedLink, ...]:
    declared = frozenset(known)
    links: list[ParsedLink] = []
    seen_ids: set[str] = set()
    seen_pairs: set[Endpoints] = set()
    for position, element in enumerate(_children(section, "link")):
        link_id = _element_id(element, file, index, tag="link", position=position)
        line = index.locate(link_id, "link", position)
        if link_id in seen_ids:
            raise InputError(
                file,
                f"declares link {link_id!r} twice",
                line=index.of_tag("link", position),
                field="id",
            )
        seen_ids.add(link_id)

        endpoints = _endpoints(
            element,
            file,
            line=line,
            owner=f"link {link_id!r}",
            known=declared,
        )
        # Endpoints sorts its own pair (R3), so a link given in the reverse
        # order of an earlier one produces the same value and collides here.
        if endpoints in seen_pairs:
            raise InputError(
                file,
                f"link {link_id!r} repeats the pair {endpoints}, which another link already joins",
                line=line,
            )
        seen_pairs.add(endpoints)
        links.append(ParsedLink(id=link_id, endpoints=endpoints))
    return tuple(links)


def _parse_demands(
    section: Element, file: str, index: _LineIndex, known: set[str]
) -> tuple[Demand, ...]:
    declared = frozenset(known)
    demands: list[Demand] = []
    seen_ids: set[str] = set()
    for position, element in enumerate(_children(section, "demand")):
        demand_id = _element_id(element, file, index, tag="demand", position=position)
        line = index.locate(demand_id, "demand", position)
        if demand_id in seen_ids:
            raise InputError(
                file,
                f"declares demand {demand_id!r} twice",
                line=index.of_tag("demand", position),
                field="id",
            )
        seen_ids.add(demand_id)

        owner = f"demand {demand_id!r}"
        endpoints = _endpoints(element, file, line=line, owner=owner, known=declared)
        volume = _number(
            _text(element, "demandValue"), file, line=line, field="demandValue", owner=owner
        )
        # Checked here rather than left to Demand, for the D15 reason: a
        # zero in the file is bad input, not a broken invariant.
        if volume <= 0:
            raise InputError(
                file,
                f"{owner} has a <demandValue> that is not positive: {volume}",
                line=line,
                field="demandValue",
            )
        demands.append(Demand(id=demand_id, endpoints=endpoints, volume=volume))
    return tuple(demands)
