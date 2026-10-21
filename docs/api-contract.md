# API contract, v1

The interface between the back end and the front end. `backend/src/netscope/api/schemas.py`
is the single source of truth. `contracts/schema.json` is generated from it, and the front
end generates its TypeScript types from that, so the two sides cannot drift apart by hand.

Regenerate with `make contract`. CI fails if the committed file is stale.

## Endpoints

| Method and path | Request body | Response body |
|---|---|---|
| `GET /api/v1/network` | none | `NetworkResponse` |
| `GET /api/v1/analysis/baseline` | none | `ScenarioReport` |
| `GET /api/v1/criticality` | none | `CriticalityResponse` |
| `POST /api/v1/scenario` | `ScenarioRequest` | `ScenarioReport` |

Errors use `ErrorResponse` with status 422 for a rejected request and 400 for a rejected
input file at startup.

## The four shaping decisions

### 1. Baseline and failure share one response type

`ScenarioReport` describes the network under a set of failures. The baseline is the report
for an empty set. `GET /api/v1/analysis/baseline` and `POST /api/v1/scenario` with no
failures return the same thing, the first from a cache.

This is the decision that most affects the front end. It has one map renderer and one panel
renderer regardless of whether anything is down, and "restore everything" is not a special
case, it is a request with an empty set. The cost is a slightly larger baseline payload,
since it carries empty arrays for the failure buckets.

### 2. The failed set lives in the request

There is no session and no server-side state. The front end owns the set of failed elements
and sends it with each request.

R11 requires failing and restoring without a reload, which is simplest when the server is a
pure function of the request. It also means every scenario is reproducible by replaying one
request body, which matters for the demonstration and for bug reports. And it keeps the
"no database" constraint genuine rather than nominal.

`ScenarioRequest` takes a set of nodes and a set of links even though R7 and R8 only ask
about a single element. A set is a superset of that case, it costs nothing to accept, and it
leaves room for a multi-element question without a contract change.

### 3. Criticality reports every element, not only the critical ones

`CriticalityResponse` returns an `Assessment` for all 37 nodes and all 55 links. An element
is critical when its `reasons` list is non-empty.

This is what lets one payload answer two of the team's three questions. Filtering on
`critical` answers "where are the single points of failure". Sorting on `impact` answers
"which links does the traffic depend on most", where dependency is measured as how much
traffic is lost or congested when the link goes away. Ninety-two assessments is a small
payload, so there is no reason to make the front end ask twice.

`FailureImpact` is reported for non-critical elements too, and that is the point. A link
whose failure strands nothing but pushes three other links to 95% is not critical under R7,
and the operations lead still wants to see it.

### 3b. Three reasons, all of them about somebody else

An element is critical when losing it costs a node that is still there: it partitions the
surviving graph, it strands a demand between two survivors, or it drives a surviving link
over capacity. Those are R7's three reasons and `CriticalityReason` has exactly three members.

**Traffic the failed node was itself sending or receiving is reported but is not a reason.**
It appears in `FailureImpact.endpoint_affected_demands` and `endpoint_affected_units`, and as
its own bucket in every `ScenarioReport`, because R8 requires it to be reported separately.
It simply does not set the `critical` flag.

This was decided the other way first, and the history is worth knowing because the numbers in
older commits reflect it. R7b says an element is critical if losing it leaves any demand
undeliverable, and read literally that includes the element's own demands. Under that reading
**37 of the real network's 37 nodes were critical**, since 36 originate traffic and the
thirty-seventh partitions the graph. A fourth reason code, `endpoint-demands-lost`, was added
so a reader could still filter out the noise.

The panel reverted it (`docs/DECISIONS.md` D24). A count that cannot be lower whatever the
network looks like measures the demand matrix, not the network, and the fourth code was a
mitigation for a bad metric rather than a good metric in its own right. Criticality now means
what an operations team was asking: losing this hurts somebody else.

**Measured effect:** critical nodes 37 to 6. Critical links unchanged at 6, because no link
ever carried the retired reason: losing a link never removes a node.

### 4. Ranks are computed on the server

`RankedLink` carries its own `rank`. The ordering rule, highest utilization first and ties
broken on link id ascending, is applied once on the server rather than reimplemented in the
view, a table and any future export. R10 asks the view to show the five most utilized links,
and this way the view cannot disagree with the API about which five they are.

## Conventions

- **No direction anywhere.** `endpoints` is always a sorted pair of node ids. See R3.
- **Utilization is a fraction**, not a percentage. `1.0` is exactly full, and R7c is
  `utilization > 1.0`.
- **Unknown fields are rejected.** Every model sets `extra="forbid"`, so a typo is an error
  rather than a silently dropped key.
- **Models are frozen**, on both sides of the wire.
- **`x` is longitude and `y` is latitude**, matching the SNDlib source. The names are kept
  so the payload reads like the input data, and `Position` documents the meaning.
- **Versioning** is a path prefix, `/api/v1`. A breaking change means `/api/v2` served
  alongside. The honest limit of this is discussed in the README.

## Fixtures

`contracts/fixtures/` holds three payloads, generated by `scripts/make_fixtures.py`:

| File | Type | What it is |
|---|---|---|
| `network.json` | `NetworkResponse` | A seven-node cut-down of the real network |
| `baseline.json` | `ScenarioReport` | That network with nothing failed |
| `scenario-berlin-down.json` | `ScenarioReport` | That network with Berlin failed |
| `criticality.json` | `CriticalityResponse` | All 15 elements of that network assessed |

They exist for two reasons. The front end lane builds its entire view against them before
any endpoint exists. And their numbers are worked out by hand, in the docstring of the
generator, rather than produced by the routing code. When P9 and P10 land, the routing
engine must reproduce them. A fixture generated from the code under test could not catch
the code being wrong.

The fixture network uses real SNDlib coordinates for its four cities, so the map renders in
the right place. It is not the real network and is not a substitute for the R1 acceptance
check.

The criticality fixture came from a separate brute-force implementation written before
netscope had any routing code, so it shares nothing with the module it will be used to check.
Its credential is that the same implementation reproduces all eight hand-derived baseline
link loads exactly, including the 105 over 550 that is the only value here which is not
round. Eight of the fifteen scenarios were then checked by hand.

Two things that fixture cannot show, stated so their absence is not mistaken for a result.
**No single failure in it overloads any link**, because the backbone links are 550 and the
largest demand is 100, so R7c never fires there and is exercised against the real network
instead, where the baseline peak is 71 percent. And because losing a link never removes a
node, no link scenario has an endpoint-affected demand.

At fixture scale the literal R7b reading shows its shape clearly: 6 of 7 nodes are critical
and only `Copenhagen` is not, mirroring the 36 of 37 in the real network.

## What v1 deliberately omits

- **The 391 individual demands.** The view never lists them all, and the ones it does show
  arrive with full detail inside a scenario report.
- **Per-demand paths.** Useful for a future "why does this link carry so much" view, and not
  needed by any requirement here.
- **Pagination and filtering.** The whole dataset is a few hundred kilobytes.
- **Any write operation.** The input files are read-only at runtime.
