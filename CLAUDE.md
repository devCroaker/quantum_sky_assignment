# Instructions for AI tools working in this repository

This file is the standing brief. Read it before changing anything. If a request conflicts
with a rule here, say so rather than quietly picking one.

## What this project is

A local analysis tool for a European backbone network. It merges the public SNDlib
`nobel-eu` topology with an invented site table, routes every demand, and reports single
points of failure, link dependency and the impact of any single node or link failure on an
interactive map.

Read `docs/IMPLEMENTATION_PLAN.md` for the task sequence and `docs/DECISIONS.md` for every
design fork already settled. Do not re-litigate a decision recorded there. If you believe
one is wrong, raise it, do not silently diverge.

## Non-negotiable rules

1. **Never invent a number.** Every figure in a test, a document or a slide is either
   derived from the brief, computed by the code, or worked out by hand with the working
   shown. If you cannot source a number, say that you cannot.
2. **Never commit a credential.** No keys, tokens or passwords, not even placeholders that
   look real. Configuration comes from the environment. The committed templates are
   `.env.example` for the back end and `frontend/.env.example` for the front end, which are
   separate because Vite only reads variables from its own directory and only those prefixed
   `VITE_`. Both hold names and safe defaults, never a secret.
3. **No network calls at runtime.** The application reads committed input files. Input data
   is fetched once, by a human, and committed with provenance.
4. **Quality gates are not optional.** `make check` must pass before any commit. It runs
   ruff, ruff format, mypy in strict mode, pytest, and the front end equivalents.
5. **Do not squash.** The git history is a graded deliverable. One logical change per
   commit, with a message that explains why and not only what.
6. **Ask when a requirement is ambiguous.** Record the question and its resolution in the
   "Open questions" section of `docs/DECISIONS.md`.

## Architecture invariants

- Layering is strict. `models` and `errors` depend on nothing. `loaders` may import
  `models` and `errors`. `routing` and `analysis` may import `models` but never `loaders`.
  Only `api` imports from everything, and nothing imports from `api`.
- **Links and demands are undirected.** Endpoints are stored as a sorted pair, so
  `(Paris, Lyon)` and `(Lyon, Paris)` are one key. Never add a direction.
- **The capacity modules in the SNDlib file are ignored.** Every backbone link is 550 units.
  Access links take the capacity from the site row.
- **Transit eligibility is a property of node kind.** Backbone cities and the aggregation hub
  forward traffic. Data centers and operations sites never do.
- **Geometry belongs to the back end.** The front end renders the coordinates it is given
  and never computes placement.
- **No graph library in shipped code.** `networkx` is a test-time oracle only. The routing
  and connectivity code must be short enough to explain on a slide.
- **The API is stateless.** The front end owns the set of failed elements and sends it with
  the request. There is no session and no database.

## Requirement map

Cite the requirement id in the commit message and the pull request description.

| Id | Requirement | Home |
|----|-------------|------|
| R1 | Load both inputs into one model. 37 nodes, 55 links, 391 demands, 2068 units | `loaders/merge.py` |
| R2 | Reject bad input naming the file and the row | `errors.py`, both loaders |
| R3 | Backbone links are 550. Ignore capacity modules. Nothing has direction | `loaders/merge.py`, `models.py` |
| R4 | Each operations site sends 10 to each data center. Data centers exchange 50 | `loaders/merge.py` |
| R5 | Route over minimum-hop paths, splitting the demand equally per path | `routing.py` |
| R6 | Only backbone cities and the aggregation hub forward traffic | `routing.py`, `models.py` |
| R7 | Critical if losing it partitions, strands a demand, or overloads a link | `analysis.py` |
| R8 | Per-failure report. Endpoint-affected demands listed separately | `analysis.py` |
| R9 | Map laid out from coordinates, each site near its attachments | `loaders/geometry.py`, `frontend/src/map` |
| R10 | Show critical elements and the five most utilized, not by colour alone | `frontend/src/panels` |
| R11 | Fail and restore any element, see the R8 result, without a reload | `frontend/src/state` |

## Verified facts, use these as test literals

Reproduced from the real input files. If your code disagrees with one of these, your code is
wrong until proven otherwise.

| Fact | Value |
|------|-------|
| Backbone nodes / links / demands | 28 / 41 / 378 |
| File A demand total | 1898 units |
| Merged nodes / links / demands | 37 / 55 / 391 |
| Merged demand total | 2068 units |
| Backbone articulation points / bridges | 0 / 0 |
| Baseline undeliverable demands | 0 |
| Baseline links above 100% | 0 |
| Baseline peak utilization | 71.0% on Berlin to Hamburg |

The backbone being 2-connected is the key structural finding: every single point of failure
in the merged network comes from the four single-homed sites, not from the backbone.

## Testing policy

- Expected values are justified. Each non-obvious literal gets a comment or docstring saying
  where it came from: the brief, a hand calculation, or the independent oracle.
- Routing correctness rests on three independent legs, not on one implementation agreeing
  with itself: a hand-worked small graph with loads derived on paper, a naive
  path-enumerating reference implementation in the test suite, and `networkx` as an oracle
  for path sets. All three must agree.
- Validation tests are table-driven, one malformed fixture per rule, each asserting that the
  message names the file and the row.
- Prefer a test that would have caught a real mistake over a test that raises coverage.

## Style

- Python: full type annotations, `from __future__ import annotations`, no `Any`, no bare
  `except`. Comments explain why, not what.
- TypeScript: `strict` on, no `any`, no non-null assertions. Types for the wire format are
  generated from the Pydantic schemas, never hand-maintained in parallel.
- Prose, in code and documents alike: no em-dashes.

## Workflow

One branch and one pull request per task in the plan, named for the task, for example
`p5-sndlib-loader`. Merge with a merge commit so the individual commits survive. The pull
request description names the requirement ids touched and the acceptance check that proves
the task is done.
