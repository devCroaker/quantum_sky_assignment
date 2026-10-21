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
| R7 | Critical if losing it partitions, strands a demand elsewhere, or overloads a link. Losing only its own traffic does not count, see D24 | `criticality.py` |
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
| Baseline peak utilization | 71.0% on Berlin to Hamburg, link `L12` |
| Baseline peak load | 390.5468671679198 units of 550, not 390.5 |

The backbone being 2-connected is the key structural finding: every single point of failure
in the merged network comes from the added sites, not from the backbone.

Six of the 37 nodes and six of the 55 links are critical. Three nodes partition the graph
when lost, `Athens`, `Dublin` and `HUB-EAST`, along with the three access links serving those
single-homed sites. `Warsaw` strands a demand without partitioning anything, and `Berlin` and
`Hamburg` are critical only for overloading a surviving link.

`Warsaw` is the case to understand. It partitions **nothing**, because `OPS-EAST-2` attaches
to both `HUB-EAST` and `Budapest` and so accidentally dual-homes the hub. The hub is still cut
off operationally, because `OPS-EAST-2` may not forward traffic under R6, so two demands die
while the graph stays in one piece. `Warsaw` is critical under R7b and not under R7a. Do not
assume a connectivity check answers the resilience question on this network.

A demand lost because its own endpoint failed is reported, per R8, but does not make an
element critical. That was read the other way for a while and marked 37 of 37 nodes critical;
see D24 before trusting a criticality figure from an older commit.

## Delegating to a subagent

A subagent starts cold. It has none of this conversation, none of the reasoning that led
here, and no way to ask a quick question. **A brief that assumes any of that produces work
that has to be redone.** Write every brief so that a smaller, cheaper model could execute it
without further input, because that is the test of whether the brief is complete.

A brief is not ready until it contains all seven of these.

1. **What to read first**, in order, naming files. Always `CLAUDE.md`, then the plan entry,
   then the decision log entries that bind the task, then the specific modules it builds on.
2. **File ownership, both halves.** Which files the agent may create or edit, and which it
   must not touch. Name the forbidden ones explicitly when other agents are running, because
   two agents editing one file is a conflict nobody asked for. Tell it to **report** a file
   that needs changing outside its scope rather than changing it.
3. **The facts it needs, as measured values.** Never say "the network has some single points
   of failure". Say which, with the numbers. An agent given a figure can check it; an agent
   given a description has to guess.
4. **Explicit permission to contradict you.** State that if a fact in the brief is false
   against the data, it must say so plainly rather than adjusting a test to agree. This is
   the single highest-value line in any brief here, for the reason below.
5. **The acceptance check**, as the exact assertion that proves the task is done, not a
   description of success.
6. **The quality gates, as commands to run**, and the traps: `make install` rather than
   `make install-backend`, mypy's strictness, that ruff formats before it checks.
7. **Git rules.** Branch name, one commit, the message style, and **do not push, do not open
   a pull request, do not merge, do not touch `main`**. Review happens before anything is
   published.

Then ask for a report back that names: the exact gate output, every judgement call it made
that is not already in `docs/DECISIONS.md` with the alternative it rejected, and anything it
could not do. **A limitation reported is cheap; a limitation hidden is a defect.**

`docs/delegation.md` holds the briefing template and the evidence behind these rules.

### Why rule 4 matters more than it looks

Three briefs in this project contained a factual error, and an agent caught each one because
it had been given a checkable value and told it was allowed to disagree:

- A claim that one site row referred forward to a later row. It referred backwards.
- A claim that losing `Warsaw` partitions the network. It does not, and finding out why
  produced the most interesting result in the project.
- A filter described as excluding a reason when it had to include two others. The wrong
  version would have hidden three of the four nodes that matter, with plausible counts and a
  passing test.

Every one was caught by an agent checking the data instead of complying. None would have been
caught by a type checker, a linter or a test written from the same wrong brief.

**So: never put a number in a brief you have not run.** If you cannot measure it, say that it
is unverified and ask the agent to establish it.

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
