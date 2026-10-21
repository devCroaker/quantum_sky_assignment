# netscope

Resilience analysis for a European backbone network. It merges the public SNDlib `nobel-eu`
topology with a table of operations sites and data centers, routes every traffic demand, and
answers three questions an operations team asked:

1. Where does the network have single points of failure?
2. Which links does the traffic depend on most?
3. What happens when a given link or site goes down?

The answers, with numbers, are in [docs/findings.md](docs/findings.md). That file is
generated from the data by `make findings`, so nothing in it is transcribed by hand.

## Running it

One command, from a clean clone:

```bash
make dev
```

It installs both halves, starts the API on <http://127.0.0.1:8000>, starts the front end on
<http://localhost:5173>, and waits. Press ctrl-c to stop both.

Open <http://localhost:5173>. You should see 37 nodes, 55 links, 391 demands and 2068 demand
units in the header, and a map of Europe with the topology drawn on it.

**Requirements:** Python 3.12 or newer, Node 22 or newer, `make`, and
[uv](https://docs.astral.sh/uv/). Nothing else, and no network access at runtime: the input
data is committed.

### Other commands

| Command | What it does |
|---|---|
| `make check` | Everything CI runs: lint, format, types, and both test suites |
| `make findings` | Regenerate `docs/findings.md` from the data |
| `make contract` | Regenerate the wire contract and its fixtures |
| `make lock` | Re-resolve `backend/uv.lock` after changing dependencies |
| `make clean` | Remove the virtualenv, `node_modules` and caches |

Configuration is environment variables, documented in `.env.example` and
`frontend/.env.example`. There are no secrets.

## How it is put together

```
backend/src/netscope/
  models.py      domain types. Undirected links and demands, node kinds
  errors.py      input errors that name the file and the row or line
  loaders/       parsing both inputs, merging them, placing the sites
  routing.py     equal-split minimum-hop routing with the transit restriction
  analysis.py    one scenario, from a failed set to loads and losses
  criticality.py the sweep over all 92 single failures
  api/           the HTTP surface
frontend/src/
  api/           generated wire types, boundary guards, data sources
  map/           projection, glyphs, overlays, the cluster popover
  panels/        critical list, five most utilized, failure impact
```

Layering is strict: `models` and `errors` depend on nothing, `loaders` may use them, `routing`
and `analysis` never import `loaders`, and only `api` imports from everything. The front end
never computes geometry or ranks; it renders what the API gives it.

The interface between the two halves is specified in [docs/api-contract.md](docs/api-contract.md).
`backend/src/netscope/api/schemas.py` is the single source of truth, `contracts/schema.json` is
generated from it, and the front end's TypeScript types are generated from that, so the two
sides cannot drift apart by hand.

Design decisions, including the ones that were close calls, are recorded with their rejected
alternatives in [docs/DECISIONS.md](docs/DECISIONS.md).

## How the numbers are checked

The routing engine rests on four independent legs rather than on its own tests agreeing with
themselves:

- A **hand-worked example** on a seven-node network, with every link load derived on paper
  before any routing code existed.
- A **second, deliberately naive implementation** in the test suite that enumerates every path
  rather than counting them. The two must agree on the real network, on the fixture, and on
  generated random graphs including under failure.
- **`networkx` as an oracle** for the set of minimum-hop paths. It is a test dependency only
  and never appears in shipped code.
- The committed **criticality fixture**, 15 failure scenarios produced before any of the
  analysis code existed, which the sweep must reproduce exactly.
- A **whole second implementation**, `scripts/oracle.py`, which parses the inputs itself and
  routes by enumerating every path. It imports nothing from `netscope`, and
  `backend/tests/test_oracle.py` asserts the two agree on the merged network, on all 55 link
  loads, and on both the impact and the R7 verdict for nine named failures.

The acceptance figures in the brief, 37 nodes, 55 links, 391 demands and 2068 units, are
asserted as literals against the real files rather than computed from the thing under test.

## What is not production-ready

This is an exercise. Two production concerns were implemented properly and the rest are
argued rather than built, which was a deliberate choice: two done well beats six done badly.

**Implemented.**

- **Input validation and error handling.** Every rejection names the file and the row, or the
  line for the XML input. Around 50 malformed-input cases are covered, one per rule. A bad
  input file at startup exits with one clear line and no traceback. Unknown ids in a request
  are a 422 that names them, and are checked before any analysis runs so that a genuine bug
  surfaces as a 500 rather than being dressed up as a client error.
- **Dependency and security checks.** `pip-audit` and `npm audit` on every pull request, Snyk
  on both halves, Dependabot weekly, and a lockfile on each side so an audit describes a
  reproducible artefact rather than whatever resolved that morning. The policy, and an honest
  list of what these checks miss, is in [docs/security.md](docs/security.md).

**Not implemented, and what a first internal release would need.**

- **Authentication and access control.** There is none. The API is read-only and serves public
  research data plus an invented site table, so there is nothing to protect yet. For an
  internal release this sits behind the existing identity provider, with the network topology
  treated as sensitive, since it is a map of what to attack.
- **Logging.** Requests and failures are logged through the standard library, and the startup
  summary prints the merged counts so a reader can confirm the merge from the log. There is no
  correlation id, no structured sink and no retention policy. For a first release: JSON lines
  to stdout with a request id, and let the platform collect them.
- **API versioning.** Only a `/api/v1` path prefix. Nothing enforces that a change is
  compatible. The generated contract makes a breaking change visible in review, which is most
  of the value, but there is no deprecation policy and no second version served alongside.
- **Configuration and secrets.** Configuration is environment variables with documented
  defaults, and there are no secrets to manage. A real deployment needs a secret store the
  moment it has a database or an upstream to authenticate to, and that is the point to adopt
  one rather than earlier.

**Other known limits.**

- **Scale.** Everything is computed in memory at startup, and the 92-scenario sweep takes
  about half a second on this network. It is quadratic in elements, so a network ten times the
  size would need the sweep moved off the request path and probably parallelised.
- **The model is a planning model, not the network.** Links have one capacity and no latency,
  demands are symmetric and static, and routing is minimum-hop rather than whatever the real
  control plane does. The conclusions are about structure, not about what the equipment would
  actually do on the night.
- **No persistence.** Every result is recomputed from the committed files on startup. There is
  no history, so "what changed since last quarter" cannot be answered.

## Inputs

The backbone is the `nobel-eu` network from SNDlib, the Survivable Network Design Library:

> S. Orlowski, M. Pióro, A. Tomaszewski, R. Wessäly. "SNDlib 1.0, Survivable Network Design
> Library." Networks, 55(3):276-286, 2010.

<https://sndlib.put.poznan.pl>

`data/sites.csv` is **invented for this exercise** and is not real network data. Provenance,
checksums and what we deliberately ignore are in [data/PROVENANCE.md](data/PROVENANCE.md).
