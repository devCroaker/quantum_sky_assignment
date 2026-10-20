# Decision log

A running record of forks in the build: what the options were, what was chosen, who chose
it, and why. Maintained so that the design can be defended line by line, and so that the
"Structure and design" and "Steering" slides describe what actually happened rather than a
reconstruction.

`Decided by` is either **panel** for a decision the reviewer made or confirmed, or **tool**
for one taken by the assistant under the standing instruction to proceed. Tool decisions are
listed here precisely so they can be challenged and reversed.

---

## D1. Back end language and framework
**Options.** Python with FastAPI, or Go.
**Chosen.** Python 3.12, FastAPI, Pydantic v2, `uv` for dependency management.
**Decided by.** Tool recommended, panel confirmed.
**Why.** The graph and routing code is the part a reviewer will read most closely, and it is
shortest and clearest in Python. The follow-up session includes a live change, which favours
the language with less ceremony. Pydantic also gives the input validation that R2 requires
and makes the wire contract in D5 generable.

## D2. Front end stack
**Options.** React with Vite, or plain TypeScript with no framework.
**Chosen.** React, Vite, TypeScript.
**Decided by.** Tool recommended, panel confirmed.
**Why.** R11 needs interactive state across a map and three panels. React makes that state
explicit. Vite keeps the one-command startup honest.

## D3. Map rendering
**Options.** MapLibre or Leaflet with raster tiles, or inline SVG with a `d3-geo` projection
over a Natural Earth outline.
**Chosen.** Inline SVG with `d3-geo`.
**Decided by.** Tool.
**Why.** Tile-based maps need a tile source. Public OpenStreetMap tiles are outside their
usage policy for an application, and every alternative needs an API key, which the brief
forbids putting in the repository. R9 asks for a layout derived from the coordinates, not for
a basemap, so a projection satisfies the requirement with no credentials and no runtime
network dependency. The application therefore works fully offline.
**Cost accepted.** No street-level context and no off-the-shelf pan and zoom. Both are
acceptable for a topology view at continental scale.

## D4. Meaning of "split the demand equally" in R5
**Options.** Enumerate every minimum-hop path and give each an equal share of the demand, or
split per hop at each node the way equal-cost multipath routing does in practice.
**Chosen.** Equal share per path.
**Decided by.** Panel.
**Why.** R5 says "split the demand equally among them", where "them" refers to the paths. The
two readings produce different link loads whenever the shortest-path graph is not symmetric,
so the choice is material and was confirmed rather than assumed.

## D5. Shape of the back end to front end interface
**Options.** A stateful session where the server remembers the failed set, or a stateless
endpoint that takes the failed set in the request.
**Chosen.** Stateless. The front end owns the failed set and posts it.
**Decided by.** Tool.
**Why.** R11 requires failing and restoring without a reload, which is simplest when the
client holds the state and the server is a pure function of the request. It also means no
session storage, which keeps the "no database" constraint genuine, and it makes every
scenario reproducible by replaying one request body. The endpoint takes a set rather than a
single element, which is a superset of the single-failure case R7 and R8 describe, and it
leaves room for the live change in the follow-up session without a contract change.

## D6. Which production concerns to implement
**Options.** Spread effort across all six, or implement two or three properly and argue the
rest.
**Chosen.** Input validation and error handling, plus dependency and security checks with
Snyk on a free tier alongside credential-free `pip-audit` and `npm audit`. The remaining
four are argued in the deck.
**Decided by.** Panel.
**Why.** The brief states a preference for two done well over six done badly. Input
validation is already mandated by R2, so it is the natural first choice. API versioning is
partially covered for free by the `/api/v1` prefix.

## D7. Routing implementation strategy
**Options.** Enumerate all minimum-hop paths and divide, or compute each link's share from
path counts over the predecessor directed acyclic graph.
**Chosen.** Path counting in the shipped code. Enumeration kept as a test-only reference
implementation.
**Decided by.** Tool.
**Why.** Enumeration is the obvious reading of R5 but the number of equal-length paths can
grow exponentially, so it is not a safe production algorithm even though this particular
graph is small. Counting is exact and linear in the number of links per demand. Keeping the
naive version in the test suite converts the risk into an asset: two independent
implementations must agree, which is real evidence that the numbers are right and does not
depend on the assistant asserting it.

## D8. No graph library in the shipped path
**Options.** Use `networkx` for shortest paths and connectivity, or implement both.
**Chosen.** Implement both. `networkx` is a test-time oracle only.
**Decided by.** Tool.
**Why.** The brief requires that every meaningful piece can be explained and walked through.
Forty lines of breadth-first search can be explained on a slide. A library call cannot,
and it would also hide the R6 transit restriction inside a parameter.

## D9. Where site coordinates are computed
**Options.** Front end places the nine sites, or the back end returns coordinates for every
node.
**Chosen.** Back end.
**Decided by.** Tool.
**Why.** Placement has a real dependency order, because `OPS-EAST-1` attaches to `HUB-EAST`
rather than to a city, so it is graph logic and not presentation. Putting it in the back end
keeps it testable and keeps the front end a pure renderer.

## D10. Plan written and reviewed before any application code
**Chosen.** `docs/IMPLEMENTATION_PLAN.md` committed first, as 22 single-purpose pull
requests with explicit acceptance checks.
**Decided by.** Panel.
**Why.** The acceptance numbers in R1 were reproduced from the real input files before
planning, so the plan is built on measured facts. Writing the sequence down first is what
makes the work delegable and the git history legible.

---

## Open questions

Recorded here as they arise, with the resolution and its date.

- **R7a, does isolating a leaf site count as splitting the network?** Working answer: yes.
  Connectivity is judged on the graph remaining after the element is removed, and a node
  with no path to the rest is a partition. Flagged to the panel.
- **R2 for the XML input.** The requirement says "names the file and the row", but XML has no
  rows. Working answer: report the file and the line number, plus the element id when one
  exists.
