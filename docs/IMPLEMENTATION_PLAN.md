# Implementation Plan

Target: a local, one-command application that merges the SNDlib `nobel-eu` backbone with
an invented site table, routes 391 demands, and reports single points of failure,
link dependency and per-failure impact on an interactive map.

This plan is the sequencing contract for the build. Each numbered item below is intended
to be one pull request: small enough to read in a sitting, with its own tests and its own
acceptance check. Nothing is squashed.

## Decisions already fixed

| Decision | Choice | Rationale |
|---|---|---|
| Back end | Python 3.12, FastAPI, Pydantic v2, `uv` | Graph code stays short and readable for the live change in the follow-up session |
| Front end | React, Vite, TypeScript | Requested stack, fastest path to an interactive map |
| Map | Inline SVG with `d3-geo` and a Natural Earth outline | No tile server, no API key, works offline. See "Rejected" below |
| Demand split | Enumerate all minimum-hop paths, give each an equal share | R5 reads as per-path, not per-hop ECMP. Confirmed with the panel |
| Production concerns implemented | Input validation and error handling; dependency and security checks | Brief prefers two done well. The other four are argued in the deck |
| Persistence | None. Analysis is computed at startup and cached in memory | No database required, and the dataset is tiny |

### Rejected

- **MapLibre or Leaflet with raster tiles.** Both need a tile source. Public OSM tiles are
  against usage policy for an app, and anything else needs a key, which the brief forbids
  committing. R9 asks for a layout from coordinates, not a basemap, so an SVG projection
  satisfies it with no credentials and no network dependency.
- **A graph library as the production router.** `networkx` is used in tests as an
  independent oracle only. The shipped router is ours, so every number is explainable.

## Verified input facts

Reproduced from the real files before planning, not taken on trust.

| Check | Value |
|---|---|
| Backbone nodes / links / demands | 28 / 41 / 378 |
| File A demand units | 1898 |
| Merged nodes / links / demands | 37 / 55 / 391 |
| Merged demand units | 2068 |
| Backbone articulation points / bridges | 0 / 0 |
| Baseline undeliverable demands | 0 |
| Baseline links above 100% | 0 |
| Baseline peak utilization | 71.0% on Berlin to Hamburg |

Two consequences for the design. First, every structural single point of failure in the
merged model comes from the four single-homed sites, not from the backbone. Second,
capacity 550 leaves deliberate headroom, so the overload rule R7c is the rule that
actually produces findings.

## Architecture

```
backend/
  pyproject.toml
  src/netscope/
    models.py          # Node, Link, Demand, Network. Undirected, canonical endpoints
    errors.py          # InputError carrying file name and row or line
    loaders/
      sndlib_xml.py    # file A
      sites_csv.py     # file B
      merge.py         # R1, R3, R4
      geometry.py      # synthesized site coordinates for R9
    routing.py         # R5, R6. Equal split over minimum-hop paths
    analysis.py        # R7, R8, R10. Baseline, failure impact, criticality sweep
    api/
      schemas.py       # wire types, generated into TS
      routes.py
      app.py
  tests/
frontend/
  src/
    api/               # generated types plus fetch layer
    map/               # projection, node and link rendering
    panels/            # criticality table, top-five table, impact panel
    state/
data/
  nobel-eu.xml
  sites.csv
docs/
  IMPLEMENTATION_PLAN.md
  api-contract.md
  DECISIONS.md         # running log of forks, recommendation and reason
```

### Data model notes

- Links and demands are undirected. Endpoints are stored as a sorted pair so that
  `(Paris, Lyon)` and `(Lyon, Paris)` are the same key.
- `Node.kind` is one of `backbone-city`, `data-center`, `operations-site`,
  `aggregation-hub`. Transit eligibility is derived from kind, per R6: backbone cities and
  the aggregation hub forward, the rest do not.
- Access link ids are synthesized deterministically as `ACC-<site>-<attachment>` so that
  a link can be named in an API call and in a test.
- Every node carries coordinates. Backbone cities use the SNDlib values. Sites are placed
  by the back end, so the front end never computes geometry.

### Routing approach

The shipped router does not enumerate paths. For each demand it runs a breadth-first
search over the transit-constrained graph, builds the predecessor directed acyclic graph,
counts paths from the source to every node and from every node to the target, then assigns
each link a share proportional to the number of minimum-hop paths crossing it. This is
exact, linear in the number of links per demand, and cannot blow up combinatorially.

A second, deliberately naive implementation that does enumerate every path lives in the
test suite. The two must agree on the real network and on generated small graphs. That
agreement, plus hand-computed fixtures, is the verification story.

## Task list

Dependencies are given as task ids. Tasks with no shared dependency may run in parallel.
Four lanes exist once P4 lands: data, algorithm, front end, platform.

### Phase 0, foundation

**P1. Repo scaffolding and quality gates.** Depends: none. Delegable.
Create `backend/` and `frontend/` skeletons, `pyproject.toml` with ruff, mypy in strict
mode and pytest, a Makefile with `install`, `lint`, `typecheck`, `test`, pre-commit hooks
running the same checks, and a GitHub Actions workflow running all of them. Add `CLAUDE.md`
stating the house rules the tool must follow. No application logic.
Accept: `make lint typecheck test` passes on an empty suite, and CI is green.

**P2. Input data and provenance.** Depends: none. Delegable.
Commit `data/nobel-eu.xml` fetched from SNDlib, and `data/sites.csv` exactly as given in
the brief. Add `data/PROVENANCE.md` with the SNDlib citation and the retrieval date, and
state in it that `sites.csv` is invented for the exercise.
Accept: a test asserts the XML has 28 nodes, 41 links and 378 demands, and that the CSV
has 9 rows and 14 attachment values.

**P3. Domain model and error types.** Depends: P1. Delegable.
`models.py` and `errors.py`. Immutable dataclasses or Pydantic models, canonical undirected
endpoints, derived transit eligibility, and an `InputError` that carries file name plus row
number or XML line and renders a single-line message.
Accept: unit tests for endpoint canonicalization, transit derivation per kind, and error
message formatting. No parsing yet.

### Phase 1, the contract that unblocks parallel work

**P4. API contract.** Depends: P3. Needs review before merge.
Write `docs/api-contract.md` describing four endpoints, the Pydantic wire schemas in
`api/schemas.py`, a script that emits TypeScript types from them, and a hand-authored
fixture response committed under `frontend/src/api/fixtures/` so the front end can be built
before the back end is finished.

```
GET  /api/v1/network            nodes with coordinates and kind, links with capacity, totals
GET  /api/v1/analysis/baseline  per-link load and utilization, the five most utilized
GET  /api/v1/criticality        critical nodes and links, each with its reasons
POST /api/v1/scenario           body {failed_nodes:[], failed_links:[]} returns the R8 report
```

The scenario endpoint is stateless and takes a set rather than a single element. The front
end owns the failed set, which is what makes R11 work without a reload, and a set is a
superset of the single-failure case the requirements ask for.
Accept: types generate cleanly, the fixture validates against the schemas, and the document
explains each field.

### Phase 2, data lane

**P5. SNDlib XML loader.** Depends: P3, P2. Delegable.
Parse nodes with coordinates, links with endpoints, and demands with values. Ignore the
capacity modules entirely, per R3. Raise `InputError` naming the file and the offending
line for malformed structure, unknown endpoints and duplicate ids.
Accept: loads the real file to 28 / 41 / 378 and a demand total of 1898. Malformed fixtures
produce errors naming file and line.

**P6. Sites CSV loader.** Depends: P3, P2. Delegable. Parallel with P5.
Parse the nine rows, split `attaches_to` on semicolons, and validate per R2: missing or
unknown columns, bad site type, non-numeric or non-positive capacity, empty attachment
list, self-attachment, duplicate attachment within a row, and duplicate `site_id`.
Forward references between rows are legal, so resolution happens after all rows are read,
but an unresolvable target is an error naming the file and the row.
Accept: the real file yields 9 sites and 14 attachments. A table-driven test covers one
malformed fixture per rule, each asserting the file name and the row number in the message.

**P7. Merge.** Depends: P5, P6. Delegable.
Build one `Network`. Set every backbone link to capacity 550. Add one access link per
attachment value at the row capacity. Add the R4 demands: each of the six operations sites
sends 10 units to each data center, and the two data centers exchange 50.
Accept: the headline check, 37 nodes, 55 links, 391 demands, 2068 units, as an explicit
test with those literals. Also assert that `HUB-EAST` receives no synthetic demand, since
it is an aggregation hub and not an operations site.

**P8. Site coordinates.** Depends: P7. Delegable.
Place each site at the centroid of its attachment points, displaced by a small deterministic
offset so it does not sit on top of a city, resolving in dependency order because
`OPS-EAST-1` attaches to `HUB-EAST` rather than to a city.
Accept: every node has coordinates, placement is deterministic across runs, and each site
is nearer to its own attachments than to any unrelated city.

### Phase 3, algorithm lane

**P9. Routing engine.** Depends: P7. Delegable with care.
Implement the predecessor-DAG equal-split router honouring the R6 transit restriction. Add
the enumerating reference implementation under `tests/`.
Accept: three layers of evidence. A hand-worked fixture on a small graph whose expected link
loads are derived on paper and written into the test as literals. Agreement between the two
implementations on the real network and on randomly generated graphs. Agreement with
`networkx.all_shortest_paths` on path sets. Also assert that a demand with no legal path is
reported rather than silently dropped.

**P10. Baseline analysis.** Depends: P9. Delegable. Parallel with P11.
Per-link load, utilization against capacity, and the five most utilized links with
deterministic tie-breaking.
Accept: zero undeliverable, zero links above 100%, and a peak of 71.0% on Berlin to Hamburg,
as literals.

**P11. Single-failure impact.** Depends: P9. Delegable.
Given a set of failed nodes and links, re-route and report: demands that start or end at a
failed node, reported separately per R8; demands that are now undeliverable for any other
reason; and every link above 100% utilization with its new value.
Accept: failing `Warsaw` isolates `HUB-EAST` and `OPS-EAST-1`, and their demands appear in
the correct bucket. Failing a node with no attached site produces no endpoint-affected
demands.

**P12. Criticality sweep.** Depends: P11. Delegable.
Classify every node and link against R7: partitions the graph, leaves any demand
undeliverable, or pushes any link above 100%. Each verdict carries the reasons that fired.
Run all 92 single-element scenarios at startup and cache them.
Accept: no backbone city or link is critical for the partition reason alone, which follows
from the backbone being 2-connected. The single-homed sites and their access links are
critical. The sweep completes within a few seconds.

### Phase 4, API

**P13. Network and baseline endpoints.** Depends: P4, P8, P10. Delegable.
FastAPI app, startup load and analysis, `GET /api/v1/network` and
`GET /api/v1/analysis/baseline`. Structured logging of request and failure. A startup
failure caused by bad input exits with the `InputError` message rather than a stack trace.
Accept: endpoint tests against the real data, and responses validate against the P4 schemas.

**P14. Criticality and scenario endpoints.** Depends: P12, P13. Delegable.
`GET /api/v1/criticality` and `POST /api/v1/scenario`, with request validation rejecting
unknown node and link ids by name.
Accept: endpoint tests, including an unknown id returning a 422 that names the offending id.

### Phase 5, front end lane, starts at P4

**P15. Front end scaffold.** Depends: P1, P4. Delegable. Parallel with all back end work.
Vite, React, TypeScript, eslint, prettier, vitest, `tsc --noEmit` wired into the Makefile,
a dev proxy to the back end, and the generated API types plus a fixture-backed data source
toggle so the view can be developed before P13 lands.
Accept: typecheck, lint and an empty test suite pass in CI.

**P16. Map view.** Depends: P15. Delegable.
Project coordinates with `d3-geo`, draw a faint Natural Earth outline for orientation, then
draw links and nodes. Node glyph varies by kind. Pan, zoom and labels.
Accept: the fixture network renders in full, sites sit next to their attachments, and a
snapshot test guards the projection. Amended during P4: the committed fixture is a seven-node
cut-down rather than the whole network, because a full fixture would have to be produced by
the very routing code it is meant to check. The view switches to live data at P13, and the
R1 figures are asserted against the real loaders in P7.

**P17. Criticality and utilization overlays.** Depends: P16. Delegable.
Mark critical nodes and links and the five most utilized links using at least two channels
each, so R10 does not rely on colour: shape and ring for critical nodes, dash pattern and
stroke weight for critical links, numbered badges one to five for the most utilized. Add
the two tables that list the same facts in text, and a legend.
Accept: a test asserts every marked element also carries a non-colour attribute, and the
tables agree with the API payload.

**P18. Fail and restore.** Depends: P17, P14. Delegable.
Click or keyboard-select any node or link to fail it, toggle it back, show the current
failed set, and render the scenario response in a side panel with the three R8 buckets kept
visually distinct. No page reload.
Accept: an interaction test fails a node, asserts the panel content, restores it, and
asserts the panel returns to the baseline state.

### Phase 6, delivery

**P19. One command and the README.** Depends: P13, P18.
`make dev` creates the environment, installs both halves, and runs the API and the front
end together. The README documents that single command, the requirement-to-code map, and an
explicit "not production ready" section.
Accept: a clean clone reaches a working application with one command on a machine with only
Python, Node and Make.

**P20. Dependency and security checks.** Depends: P1.
Lockfiles for both halves, `pip-audit` and `npm audit` in CI with no credentials needed, and
a Snyk job that runs when the token secret is present and skips cleanly when it is not.
Document the policy in the README.
Accept: CI green on a clean tree, and the Snyk job skips rather than fails without a token.

**P21. Findings report.** Depends: P12.
A command that emits the numbers answering the team's three questions, so the deck quotes
generated output rather than hand-copied figures.
Accept: the committed report regenerates byte for byte.

**P22. Deck.** Depends: P19, P21. Needs the panel's own input for Findings, Steering,
Unclear and Time spent.

## Dependency summary

```
P1 ──┬── P3 ── P4 ──┬── P13 ── P14 ── P18 ── P19
     │               └── P15 ── P16 ── P17 ──┘
     └── P20
P2 ──┬── P5 ──┐
     └── P6 ──┴── P7 ──┬── P8 ──────────── P13
                       └── P9 ──┬── P10 ── P13
                                └── P11 ── P12 ──┬── P14
                                                 └── P21 ── P22
```

Critical path runs P1, P3, P4, then the data and algorithm lanes to P12, then P14, P18, P19.
The front end lane from P15 to P17 runs entirely in parallel against the P4 fixture.

## Definition of done, every PR

1. One logical change, with a message explaining why and not only what.
2. Tests covering the new behaviour, with expected values justified in the test or its
   docstring. Numbers derived by hand or from the brief are written as literals.
3. `make lint typecheck test` green locally and in CI.
4. Requirement ids touched are named in the PR description.
5. Any fork taken without asking is appended to `docs/DECISIONS.md` with the alternative
   that was rejected and the reason.
