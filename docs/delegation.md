# Briefing a subagent

The rule is in `CLAUDE.md`. This is the template that satisfies it, and the evidence for why
it is shaped this way.

Work on this project was done by subagents running in parallel git worktrees, with every
branch reviewed before it was pushed. That worked, but only because the briefs were written
to be executed cold. The failures that did happen were failures of the brief, not of the
agent.

## The template

Copy this, fill every section, delete nothing. A section you have nothing to put in is a
section you have not thought about yet.

```markdown
You are implementing task **P<n>** of the plan in `docs/IMPLEMENTATION_PLAN.md`. You are
working in your own git worktree. <Say which other agents are running and what they own.>

**Files you may create or edit:** <exact paths>
**Do not edit** <exact paths, especially the ones another agent owns>. If you believe one of
them needs a change, report it instead of making it.

## Read first
1. `CLAUDE.md`. Binding. <Name the rules most likely to bite: no invented numbers, no
   em-dashes, the layering, `make check` must pass.>
2. `docs/IMPLEMENTATION_PLAN.md`, the P<n> entry.
3. `docs/DECISIONS.md`, entries <the ones that bind this task>.
4. <The modules it builds on, and what each already provides. Say "use them, do not
   reimplement".>

## What to build
<The interface, as a signature or a schema. Then the rules it must honour, each tied to its
requirement id.>

## Facts you may rely on, measured against the real data
<A table of values. Every one measured, none described.>

If any figure above is false against the data, **say so plainly rather than adjusting a test
to agree with me.** Previous briefs have contained errors that agents caught this way, and
that is the behaviour I want.

## Tests
<The specific assertions that prove the task is done, with the expected values. Say where
each value came from: the brief, a hand calculation, or an independent oracle.>

## Quality gates
```
make install
make check
```
<The traps: `make install` not `make install-backend`, or the gates fail at
`eslint: command not found`. mypy is strict with `disallow_any_explicit`: no `Any`, no
blanket ignores. ruff enforces `UP`. Run `.venv/bin/ruff format backend` first.>

## Git
Branch `<name>`. One commit, explaining **why** not only what, matching the existing history
style. End with the Co-Authored-By line.

**Do not push. Do not open a pull request. Do not merge. Do not touch `main`.**

## Report back
Branch, files, exact `make check` output, <the specific numbers you want to see>, every
judgement call not already in `docs/DECISIONS.md` with the alternative you rejected, and
anything you could not do.
```

## Why each part is there

**Read-first list.** An agent that has not read the decision log will re-litigate a settled
question, and its reasoning will look sound because it never saw the argument against it.

**File ownership, stated both ways.** Two agents created `loaders/__init__.py` independently,
with different contents, which would have handed whoever merged second a conflict in a file
neither task was about. Naming the forbidden files is cheap insurance.

**Measured facts, not descriptions.** An agent given "the peak is 390.5" asserted it and then
found the real value is 390.5468671679198: the brief had repeated a display rounding as a
fact. An agent given "there are some overloaded links" would have had nothing to check.

**Permission to contradict.** See `CLAUDE.md`. Three briefs contained a false claim and an
agent caught each one. This is the highest-value sentence in the template.

**The exact acceptance assertion.** "Make sure the merge is right" produces a test that
agrees with the code. "Assert 37 nodes, 55 links, 391 demands and 2068 units as literals"
produces a test that can fail.

**Gate commands with their traps.** Several agents lost time to `make check` failing at
`eslint: command not found` because they ran `make install-backend` alone. One line in the
brief prevents it.

**No push, no pull request, no merge.** Non-negotiable. Review happens before anything is
published, and the one time a pull request was merged without it the history took two
recovery pull requests to repair.

**Judgement calls and limitations in the report.** This is what makes delegation safe. Agents
on this project reported, rather than hid: that a documented setting did nothing, that a
cluster marker lost its members' criticality, that a branch name was already taken, and that
a fixture could not distinguish two readings of a filter. Each was a real defect or gap, and
each was cheaper to fix because it arrived in a report rather than being discovered later.

## Choosing a model

Write the brief so a smaller model can execute it. That is a test of the brief, not a
statement about the model: if a task needs a larger model to interpret it, the brief is
underspecified.

Reserve the larger model for the work that genuinely needs judgement, which on this project
was reviewing the output, deciding the interface and writing the briefs themselves. Several
defects in merged work were found by reading and running the result, not by any gate, and
that review is where the effort belongs.

## What a brief cannot delegate

Do not delegate a decision that belongs to the reviewer, the design of the interface every
other task builds against, or anything that would be hard to reverse. On this project the
foundation, the domain model and the wire contract were written directly for that reason:
getting one of them wrong would have propagated into every task that followed.
