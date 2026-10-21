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

## D11. Git workflow
**Options.** One pull request per task merged with a merge commit, the same with a rebase
merge, or well-written commits straight onto `main`.
**Chosen.** One branch and one pull request per task, merged with a merge commit.
**Decided by.** Panel.
**Why.** The brief says the history will be read and must not be squashed. A merge commit
keeps every individual commit and also preserves the boundary of each task, so a reviewer
can see both the fine grain and the unit of work. The pull request description is also the
natural place to name the requirement ids a task satisfies.
**Cost accepted.** Twenty-two pull requests to review.

## D12. R7a, does isolating a leaf site count as splitting the network?
**Partly superseded: see D24.** The R7a answer below still stands. The R7b reading recorded
in the "Open questions" resolution and in the consequence paragraph was reverted.
**Options.** Judge connectivity on the whole remaining graph, so stranding a single-homed
site is a partition, or count only partitions of the backbone and report stranded sites
under R7b instead.
**Chosen.** Any partition of the remaining graph counts.
**Decided by.** Panel, after the tool raised it.
**Why.** It is the plain reading of R7a, and it is the finding the operations lead most
needs. Since the backbone is 2-connected, no backbone city or link partitions anything, so
under the narrower reading the partition rule would never fire and the four genuine single
points of failure would be reported under a softer label.
**Consequence, corrected on 2026-10-20 once P9 could measure it.** Critical for the
partition reason: three nodes, `Athens`, `Dublin` and `HUB-EAST`, and three links,
`ACC-OPS-SOUTHEAST-Athens`, `ACC-OPS-WEST-Dublin` and `ACC-OPS-EAST-1-HUB-EAST`. No backbone
city and no backbone link is critical for that reason.

The original version of this entry said four nodes and four links, including `Warsaw` and its
access link. That was wrong, and it is the most interesting error in the project so far.
`OPS-EAST-2` attaches to both `HUB-EAST` and `Budapest`, which accidentally gives the
aggregation hub a second route to the backbone, so losing `Warsaw` leaves the graph in one
piece of 36 nodes.

The hub is not actually safe. `OPS-EAST-2` is an operations site and may not forward traffic
under R6, so with `Warsaw` gone the hub's own traffic still cannot leave: two demands become
undeliverable while the graph is unbroken. `Warsaw` is therefore critical under R7b and not
under R7a.

That distinction is the whole point of keeping R7's reasons separate. A connectivity check
alone would call this network more resilient than it is, because it counts a path through a
node that is not allowed to carry traffic. See also D21 on reporting reasons individually.

## D13. Parallel execution with subagents
**Options.** Run the four lanes concurrently in separate git worktrees, pair up two tasks at
a time, or work strictly sequentially.
**Chosen.** Lane-parallel once the API contract lands, with every agent's output reviewed
before it reaches `main`.
**Decided by.** Panel.
**Why.** The plan's dependency graph has four genuinely independent lanes after P4, and the
front end lane can run against the committed fixture for its whole length. Each agent works
in its own worktree, so concurrent work cannot interleave in the history.
**Guard.** The foundation and the interface, P1 through P4, are not delegated. Those tasks
fix the house rules, the domain model and the wire contract that every later agent depends
on, so getting them wrong would propagate. They are done directly and reviewed first.

## D14. Fail fast on bad input, or collect every problem
**Options.** Raise on the first problem found, or validate the whole file and report every
violation at once.
**Chosen.** Raise on the first problem.
**Decided by.** Tool.
**Why.** R2 asks for "an error", singular, that names the file and the row. A malformed
input is a reason to stop rather than something to work around, and one precise message is
easier to act on than a list whose later entries are often consequences of the first. The
error object keeps `file`, `row`, `line` and `field` as separate attributes, so the API layer
can build a structured response and a future change to collecting all errors would not need
the message format to change.

## D15. Invariants live in the model, not in the loaders
**Chosen.** `Endpoints` sorts its own pair, `NodeKind` answers whether it may forward
traffic, and `Network` rejects a link or demand naming a node it does not have.
**Decided by.** Tool.
**Why.** Undirectedness (R3) and the transit rule (R6) are stated once each and cannot be
forgotten at a call site. Routing never has to defend against a dangling reference, which
keeps the router short enough to explain on a slide. The cost is that the model raises
`ValueError` rather than `InputError`, because a violation there is a programming mistake
and not a bad input file. Loaders are responsible for turning file content into valid
constructor arguments, and for reporting failures with file and row.

## D16. disallow_any_explicit versus Pydantic
**Problem.** P1 turned on mypy strict plus `disallow_any_explicit`. Every Pydantic model
class definition then failed, because `BaseModel`'s own machinery is typed with `Any`.
**Options.** Drop `disallow_any_explicit` from the whole project, or disable just the
`explicit-any` code for the one module that defines wire models.
**Chosen.** A per-module override for `netscope.api.schemas`.
**Decided by.** Tool.
**Why.** The `Any` is Pydantic's, not ours. The rule is worth keeping where it does its real
job, which is stopping us from writing an escape hatch in our own code. Full strict mode
still applies to the schemas module, so only this one error code is off, in one file, with a
comment saying why. The alternative would have weakened the check across the whole back end
to accommodate a third-party annotation.

## D17. Fixtures are hand-derived, not generated from the router
**Options.** Produce the front end fixture by running the real loaders and router over the
real data, or hand-author a small network and work its numbers out on paper.
**Chosen.** Hand-author a seven-node cut-down, with every link load derived by hand in the
generator's docstring.
**Decided by.** Tool.
**Why.** A fixture generated by the code under test cannot catch that code being wrong. These
numbers are the first worked example of R5 and R6, and P9 and P10 have to reproduce them, so
they need to come from somewhere other than the implementation. The cut-down keeps the hand
calculation small enough to check by eye: two demands, one with a single minimum-hop path
and one with two, which is exactly the split R5 describes.
**Cost accepted.** The front end builds against a network that is not the real one, and
switches to live data at P13. The plan's P16 acceptance check was amended to say so. The R1
acceptance figures are asserted against the real loaders in P7, not here.

## D18. What the backbone loader rejects beyond the brief's list
**Decided by.** Tool, raised by the P5 subagent.
Three calls worth recording, because each rejects input the brief did not mention.

**NaN and infinity are rejected as non-numeric**, for coordinates and demand values alike.
Python's `float()` accepts both. A NaN is neither greater than nor less than zero, so a NaN
demand value would pass a positivity check and then silently poison every total, including
the 2068 figure R1 pins. Rejected alternative: accept whatever `float()` accepts, which
leaves a hole in exactly the numbers the acceptance check depends on.

**Elements are matched on local name, so the namespace declaration is optional.** The real
file declares `http://sndlib.zib.de/network`. Requiring it would report "has no `<nodes>`
section" against a file whose nodes are plainly present, which is a worse failure than none.

**Two demands over the same node pair are accepted.** Only ids must be unique. Nothing in
the brief forbids it, and two demands between the same cities is legitimate data that simply
sums. Confirmed the real file contains none, so this is about robustness and not about the
committed input.

## D19. Locating an error when there is no row to point at
**Decided by.** Tool, raised by both loader subagents.
R2 asks for the file and the row. Three cases have no obvious row or line.

**A missing or unreadable file is reported at line 1**, and an **empty CSV at row 1**, where
its header should have been. Rejected alternative: omit the location, which forces every
caller to special-case the one error that has no position.

**A duplicate id is reported at the second copy, not the first.** The first occurrence is
valid content, and pointing a reader at correct data to explain a duplicate is unhelpful.

**CSV fields are stripped of surrounding whitespace before the blank checks run**, so a field
of only spaces is still rejected. Rejected alternative: byte-exact fields, which would reject
a hand-edited file over invisible formatting.

**A blank line mid-file is its own rule** rather than a field-count error, because the CSV
reader yields a zero-field record and "expected 4 fields, found 0" misdescribes what the
author did.

## D20. Screen layout
**Options.** Map with a persistent side panel, an equal split between map and tables, or a
full-bleed map with findings in an overlay on click.
**Chosen.** Map on the left at roughly two thirds, persistent side panel on the right
carrying the critical list, the five most utilized links, and the failure impact.
**Decided by.** Panel.
**Why.** The numbers stay on screen while an element is being failed, which is what an
operations lead needs and what makes the live demonstration answerable under questioning. A
full-bleed map looks better and hides the figures until something is clicked.
**Cost accepted.** The map is smaller than it could be, with 37 nodes and 55 links to place.

## D21. How R10 avoids relying on colour
**Options.** Shape, stroke pattern and numbered badges; text labels on the map; or tables as
the authoritative view with the map carrying only keyed markers.
**Chosen.** A second visual channel on every marked element. Critical nodes get a ring and a
warning glyph, critical links are dashed, the five most utilized get a rank badge numbered
one to five and a heavier stroke. Colour is decoration on top of all of that, never the
carrier of meaning. The tables remain as the textual statement of the same facts.
**Decided by.** Panel.
**Why.** The encoding survives greyscale, a projector with poor colour, and the common forms
of colour blindness. Text labels would be unambiguous but crowd badly at 55 links. P17 will
test that every marked element carries a non-colour attribute, so this is enforced rather
than merely intended.

## D22. Where site placement lives, and the P7 to P8 split
**Problem.** `Node` requires coordinates, so P7's merge cannot build a site node without
placing it, yet P8 is the task that owns placement.
**Chosen.** P7 places each site at the plain centroid of its attachment points, resolved
iteratively in dependency order. P8 then adds the deterministic offset that stops a marker
sitting on top of the city it attaches to, and owns the tests for non-overlap.
**Decided by.** Tool.
**Why.** The interesting part of placement is the dependency order, because `OPS-EAST-1`
attaches to `HUB-EAST`, which is itself a site whose position is derived. That cannot be
deferred, since the merge needs a coordinate for every node it builds. Splitting at the
centroid keeps both tasks meaningful and keeps geometry out of the front end, per D9.
**Consequence.** A circular attachment is detectable and is rejected in P7 with an
`InputError` naming the file and a row, which is a case the brief does not mention.

## D23. How a site is displaced from its attachments
**Context.** P7 placed each site at the plain centroid of its attachments, which left
`Warsaw`, `HUB-EAST` and `OPS-EAST-1` on one identical coordinate, and `OPS-WEST` and
`OPS-SOUTHEAST` exactly on top of Dublin and Athens. Three markers at one pixel are
unclickable, which breaks R11. The panel chose offset plus a proximity popover in the view,
so the back end half is a displacement that makes every coordinate distinct.
**Decided by.** Tool, within the panel's choice of approach.

**Magnitude: 0.35 degrees, measured against the map rather than guessed.** The two closest
backbone cities, Strasbourg and Zurich, are 1.4261 degrees apart, a figure taken from the file
and asserted in a test. One offset is 0.245 of that smallest gap, so even a chained site two
offsets out stays at half the gap and cannot reach a neighbouring city. It is also about 1.2
percent of the network's 29.57 degree longitude span, which is visible at whole-network zoom.
Rejected scaling by the cosine of latitude to equalise kilometres: the front end does the
projecting, and a latitude-dependent magnitude would be a constant nobody could explain on a
slide.

**Direction is derived, not fixed.** For a site with two or more distinct attachments, the
offset is perpendicular to the line through them, choosing whichever perpendicular points
away from the nearest unrelated node. Perpendicular keeps the site equidistant from both ends,
so it still reads as sitting between them. Rejected "outward from the centroid", which this
plan originally suggested: for two attachments the outward direction is degenerate, since the
unit vectors cancel, and for any symmetric set it gives no answer at all.

For a site with one attachment there is no "away" from a single point, so the bearing comes
from the surroundings: directly away from the nearest already-placed node that is not one of
its attachments. `HUB-EAST` moves away from Budapest, `OPS-WEST` from Glasgow,
`OPS-SOUTHEAST` from Belgrade. `OPS-EAST-1`'s nearest non-attachment is `Warsaw`, so the chain
extends outward in a straight line rather than doubling back. Rejected deriving the bearing
from a site's index among its siblings, which the plan suggested: that is arbitrary with
respect to the map, and would have put `HUB-EAST` and `OPS-EAST-1` on the same bearing by
coincidence rather than for a reason.

**Distinctness is a property of the algorithm, not a hope.** A candidate position that
coincides with one already taken is rotated by the golden angle until free. Rejected nudging
by an epsilon, and rejected trusting the direction rules to be distinct enough, because
neither makes the guarantee hold for two sites that attach to an identical set of nodes.
Verified on the real data: zero coincident pairs out of 666, and the closest pair in the whole
network is now `Athens` to `OPS-SOUTHEAST` at exactly one offset.

**Consequence for P7's tests.** Four of them asserted a site sits *at* its centroid, which
the offset makes false. They were amended rather than deleted or loosened to a tolerance that
would hide the displacement. Each now keeps the centroid arithmetic in its docstring and
asserts the placed point is exactly one offset from that centroid, plus, for `DC-NORTH`, that
it is equidistant from Hamburg and Copenhagen. That pair of constraints still pins the
centroid: a centroid computed from the wrong points lands at a different distance, and only a
point displaced from the true midpoint can be equidistant from both cities. Confirmed by
mutation: changing the centroid to take the first point's longitude instead of the mean fails
eight tests, including both amended ones.

**Known gap.** `contracts/fixtures/network.json` carries hand-invented site positions that
predate this rule and are not produced by `build_network`. Nothing is broken, because the
fixture is a cut-down network and not a snapshot of the real one, but P13 should not expect
the two to agree when it wires the real loaders to the API.

## D24. R7b reverted: losing only your own traffic is not critical
**Supersedes the R7b half of D12, and retires the fourth reason code added in P15b.**
**Decided by.** Panel.

**What changed.** An element is critical only when losing it costs somebody else something:
it partitions the surviving graph, it strands a demand between two nodes that both survive,
or it drives a surviving link over capacity. A demand lost because its own endpoint failed no
longer counts, and `endpoint-demands-lost` is gone from `CriticalityReason` on both sides of
the wire.

**Why the original reading was tried.** It is the literal text of R7b, which says an element
is critical if losing it leaves any demand undeliverable, without excepting the demands the
element itself originates. The cost was measured before the decision rather than discovered
after it, and the panel chose the literal reading knowing it.

**Why it was reverted.** The cost turned out to be the whole answer. All 37 of the 37 nodes
were critical: 36 originate traffic and the thirty-seventh partitions the graph. That count
cannot be lower whatever the network looks like, because it is a fact about the demand matrix
and not about the topology. A metric that cannot vary is not a measurement. The deck slide
built on it had to spend its space explaining why its own headline number should be ignored,
which is the clearest possible sign the number was wrong.

**What this costs.** Nothing in the data. R8 still requires demands lost to a failed endpoint
to be reported separately, and they still are, in `FailureImpact.endpoint_affected_demands`
and `endpoint_affected_units` and as their own bucket in every scenario report. The figures
are unchanged; only their effect on the `critical` flag is.

**Measured consequence.** Critical nodes go from 37 to **6**: `Athens`, `Dublin` and
`HUB-EAST` partition the network, `Warsaw` strands a demand between survivors, and `Berlin`
and `Hamburg` overload a surviving link. Critical links are **unchanged at 6**, because no
link ever carried the retired reason: losing a link never removes a node.

**Consequence for the view.** The Critical panel's reason filter was a way to hide 31 nodes
of noise and is now a way to narrow. Every reason is selected by default, because every
remaining reason describes harm to somebody else.

**Worth recording as a process point.** The fourth reason code was the right response to the
decision as it stood: it preserved the discriminating signal underneath a flag that had
stopped discriminating. It was a mitigation of a bad metric rather than a good metric, and
removing the cause removed the need for it. Keeping both would have left two ways to ask the
same question.

## D25. A subagent brief must be executable cold
**Decided by.** Panel.
**Rule in `CLAUDE.md`, template in `docs/delegation.md`.**

Every brief handed to a subagent must be complete enough that a smaller, cheaper model could
execute it without asking anything. Seven things are required: what to read first, file
ownership stated both ways, the facts it needs as measured values, explicit permission to
contradict the brief, the exact acceptance assertion, the gate commands with their traps, and
the git rules including no push and no merge. The report back must name every judgement call
and every limitation.

**Why this is a rule and not advice.** Three briefs in this project contained a factual error,
and an agent caught each one because it had a checkable value and had been told it could
disagree: a site row described as a forward reference that pointed backwards, a claim that
losing `Warsaw` partitions the network, and a filter described as excluding a reason when it
had to include two others. None would have been caught by a type checker, a linter, or a test
written from the same wrong brief. The last one would have silently hidden three of the four
nodes that matter.

The corollary is the strict part: **never put a number in a brief that has not been run.** If
it cannot be measured, say it is unverified and ask the agent to establish it.

**Why "a smaller model could execute it" is the test.** It is a statement about the brief, not
about the model. A task that needs a larger model to interpret it is underspecified. The
larger model's time belongs on reviewing output, designing the interfaces every other task
builds against, and writing the briefs, since several defects in merged work were found by
reading and running the result rather than by any gate.

**Rejected.** Briefing conversationally and answering questions as they arise. It works with
one agent and fails with four running in parallel worktrees, because each interruption is a
context switch for the reviewer and a stall for the agent. It also leaves no artefact: a
written brief can be checked against what came back, and a conversation cannot.

**Not delegated under this rule.** Decisions belonging to the reviewer, the design of an
interface every later task depends on, and anything hard to reverse. The foundation, the
domain model and the wire contract were written directly for that reason.

## D26. The verification oracle is committed, not a scratch script
**Decided by.** Panel, after asking whether the probe was in the repository. It was not.
**Why it matters.** The project's answer to "how do you know the numbers are right, other
than the tool saying so?" leaned on a probe written before the repository had any code,
which reproduced the figures the brief gives. That probe lived in a scratch directory. It
was therefore evidence a reviewer could not inspect, could not run, and would lose, and the
original file had already been overwritten in place by later work. Quoting it was no better
than quoting nothing.

`scripts/oracle.py` is that check, rebuilt and committed. It parses the XML with regular
expressions and the CSV by hand, merges per R1, R3 and R4, and routes by **enumerating**
every minimum-hop path, where the shipped router counts paths over a predecessor graph and
never builds one. It imports nothing from `netscope`.

`backend/tests/test_oracle.py` asserts the two agree on the merged network, on every one of
the 55 baseline link loads, and on both the measured impact and the R7 verdict for nine
named failures. Verified to bite: reversing which end of an edge the shipped router counts
from fails five of its tests. The oracle runs in 89ms, so this costs nothing.

**What it still does not prove.** Both implementations were written from the same
requirements by the same author, so a shared misreading survives both. It catches an
implementation mistake, not a wrong assumption. That limit is stated in the oracle's own
docstring rather than left for a reviewer to find.

**Rejected.** Keeping the probe as a scratch script and describing its result. That is the
practice this entry exists to end: evidence that cannot be re-run is an anecdote.

## D27. R3's capacity stays overridable, with the default enforcing it

**Context.** An independent review flagged that `NETSCOPE_BACKBONE_CAPACITY` can override the
550-unit capacity R3 fixes, so an operator can start the application with a value that no
longer satisfies the requirement as literally written.

**The finding is accurate.** Setting the variable to anything other than 550 produces a
network R3 does not describe. That is real and worth being explicit about rather than arguing
away.

**Decided by.** Tool, during P13's review, on the strength of an earlier finding: the setting
was committed in `.env.example` and read into `Settings`, but nothing wired it through, so it
silently did nothing. A documented setting that does nothing is worse than no setting, because
a reader believes it works and nothing from outside reveals otherwise. See the P13 review
discussion for that half of the reasoning, which this entry was supposed to follow up with a
decision record and did not, until an external review asked for one.

**Why it stays overridable rather than being removed.**

1. **The default is R3-compliant.** `DEFAULT_BACKBONE_CAPACITY = 550.0`, and every path that
   builds the application's `Network` uses it unless the environment says otherwise. A clean
   clone run with no configuration satisfies R3 exactly.
2. **It is the lever the follow-up session asks for.** The brief's panel session includes
   about fifteen minutes for a small change made live with the tool's own help. A capacity
   change is the most natural thing to ask for in that slot, and a setting that already exists
   and is already tested is a better answer than writing one under time pressure. The
   `scripts/oracle.py` independent verification also reads from the same input files rather
   than a hardcoded 550, so a presenter changing the capacity live does not silently
   desynchronize the one check a reviewer can run themselves.
3. **Removing it does not remove the underlying tension.** R3 says every backbone link has
   capacity 550. Nothing in the brief says that number may never be configurable, only that
   the application's behavior must satisfy it. A fixed constant with no parameter satisfies
   the letter more simply, but the brief's own production-concerns section asks explicitly
   whether configuration is handled, which argues for environment-driven settings generally
   rather than against this one specifically.

**What this means in practice, stated plainly for anyone presenting the application:** the
one time this matters is if `NETSCOPE_BACKBONE_CAPACITY` is changed to demonstrate something
live. Say so explicitly when doing it ("this is now running with a different capacity than
the brief specifies, to show X") rather than let a panel discover a 550 that silently became
something else. The README documents the default and this decision; it is the presenter's job
to say when the default has been overridden.

**What was fixed alongside this decision, not instead of it.** The review also found that
`Link.capacity` and `Demand.volume` both accepted NaN, because `value <= 0` is `False` for
NaN under IEEE 754 and so never rejects it. That is a real validation gap independent of
whether the capacity is configurable: a malformed environment variable, not just a malicious
one, could have produced a `Network` with an unusable capacity that nothing caught until
somewhere downstream divided by it. Both constructors now check `isfinite` first, matching
the precedent already set in the SNDlib XML loader for the same reason. This closes the gap
regardless of what happens to the configurability question above.

**Rejected.** Removing the override and hardcoding 550 with no parameter, which was the
state before P13 and the state the review's recommendation would restore. Rejected because it
removes real capability for a requirement the default already satisfies, and because the
brief rewards exactly this kind of configuration surface under "production concerns" so long
as it is honestly described, which this entry is the act of doing.

---

## Open questions

Recorded here as they arise, with the resolution and its date.

- ~~**R7a, does isolating a leaf site count as splitting the network?**~~ Resolved by the
  panel on 2026-10-20. Yes. See D12.
- ~~**R2 for the XML input.**~~ Resolved in P5 on 2026-10-20. The requirement says "names the
  file and the row", but XML has no rows, so the loader reports the file and the line. An
  element with an id is located at its own line, one without at its position among its
  siblings, and a missing section at the parent that should have held it. See D19 for the
  cases with no line at all.
