# Dependency and security checks

What is in place, what each check would catch, what it would miss, and what is not covered at
all. The implementing task is P20. Nothing here needs a credential to run, and no credential
is committed anywhere in this repository.

Files involved:

- `.github/workflows/security.yml`, the checks themselves
- `.github/dependabot.yml`, the update pull requests
- `backend/pyproject.toml`, which carries `pip-audit` in the `dev` extra
- `.pre-commit-config.yaml`, which carries the one local secret check

The workflow is separate from `.github/workflows/ci.yml` on purpose. It answers a different
question, it needs a schedule that CI does not want, and keeping it apart let three parallel
branches work without colliding in one file.

## Triggers

Pull requests, pushes to `main`, and manual dispatch. The scheduled trigger is **written and
commented out**.

Every check, Snyk included, runs on every pull request. That is the trigger that matters
day to day, because it blocks a dependency change at the point of review.

The schedule is the one trigger that catches something the others cannot. A pull-request run
tells you about the code you just wrote. It never tells you that a dependency merged six weeks
ago had an advisory published yesterday, because nothing in the repository changed. On a
long-lived service that case is the main reason to have these checks at all, and the schedule
should be on.

It is off here on purpose. This repository is short-lived, and a weekly cron on a quiet
repository produces runs nobody reads, which is precisely how a failing security job comes to
be ignored. The cron line is left in place, commented, with the reasoning next to it, so
enabling it is uncommenting two lines rather than rediscovering the decision.

Until then the same sweep is available on demand, from the Actions tab or with:

```bash
gh workflow run Security
```

`permissions: contents: read` and a `concurrency` group match `ci.yml`. The workflow needs no
write token: nothing it does writes to the repository.

## The three checks

### 1. `python-audit`, pip-audit

Installs the back end exactly as CI does (`uv pip install -e "backend[dev]"`) and runs
`pip-audit --skip-editable` against the resolved environment.

**Catches.** Any direct or transitive Python dependency whose installed version appears in the
PyPI advisory database or OSV, including the dependencies pulled in by FastAPI, Pydantic,
Uvicorn and the dev tooling. Because it audits the installed environment rather than the
version ranges in `pyproject.toml`, it sees the full transitive tree at the versions a fresh
install would actually get.

**Misses.**

- Anything with no published advisory. A real vulnerability that nobody has reported yet is
  invisible here, and so is a malicious package that has not been flagged.
- Vulnerabilities in our own code. `pip-audit` reads a dependency list; it never looks at
  `backend/src`.
- Reachability. A finding in a package we import but never call on a vulnerable code path
  still fails the job. That is the right default, but it means some failures will be noise
  that a human has to triage.
- The specific environment a human has locally, unless they run `make install` first. The
  gate is CI's resolution, not theirs.
- Nothing about a version that is not in `backend/uv.lock`. Since the install uses
  `uv sync --locked`, the audited versions are exactly the pinned ones, and a lockfile that
  disagrees with `pyproject.toml` fails the job before the audit runs. Two runs a week apart
  audit the same versions, so a change in result means a newly published advisory rather than
  a different resolution.

`--skip-editable` drops `netscope` itself, which is installed from the working tree and has no
PyPI release to look up. `--strict` is deliberately not used, because it would turn that one
expected skip into a failure. There are no `--ignore-vuln` entries, so a finding fails the
job and a human decides what to do about it.

Current state at the time of writing, from the real run: no known vulnerabilities, with
`netscope` listed as the only skip.

### 2. `node-audit`, npm audit

`frontend/package.json` does not exist on `main` yet; the front end lands in P15. The job
copies the probe pattern from `ci.yml`: a first step checks for the file and sets an output,
and every later step is gated on it, so the job passes with an explanatory line in the log
until the front end arrives. No edit is needed when it does.

Once the front end exists, the job runs `npm audit --audit-level=high` in `frontend/`, then a
second non-failing `npm audit` that prints every severity for the reader.

**Catches.** High and critical advisories anywhere in the npm tree, production and
development alike, resolved from `package-lock.json`.

**Misses.**

- Low and moderate advisories do not fail the run. They are printed, not enforced.
- Same structural blind spots as `pip-audit`: no advisory, no finding; no reachability
  analysis; nothing about our own TypeScript.
- `npm audit` reports against the lockfile, so a lockfile that is behind the manifest audits
  the old tree.

### Why `high` and not `moderate` or `low`

A front end tree for a Vite and React application is mostly build and test tooling, and the
low and moderate end of the npm advisory feed is dominated by findings that are not reachable
from shipped code: a regular expression denial of service in a dev-only transitive package, a
prototype pollution issue in something that only ever sees our own config. Failing the build
on those produces a red job most weeks for reasons nobody can act on, and the predictable
result is that people stop reading the job, which costs more than the advisories it caught.
`high` makes a failure mean something.

The cost is explicit: **a moderate-severity vulnerability that is genuinely reachable from
shipped front end code will not fail this build.** It will appear in the informational step's
output, where it depends on somebody reading the log. If this project went to production, the
threshold for the production dependency tree should drop to `moderate`, with the `high`
threshold kept only for `devDependencies` (`npm audit --omit=dev --audit-level=moderate` as a
second gate).

### 3. `snyk`, enabled, and still safe without a token

`SNYK_TOKEN` is configured as a repository secret, so this job **runs for real on every pull
request and push to `main`**, scanning both halves and failing on high severity and above.

The job still probes for the token in its first step and gates every later step on the result,
because a secret is not always present even when it is configured. GitHub does not pass
secrets to workflows triggered from a fork, and a reviewer's fresh clone has none at all. A
Snyk job that failed in those cases would be red on every fork and every clone, and a
permanently red job is worse than no job. With no token it prints an explanation naming the
secret to add, succeeds, and does not block the workflow.

The probe reads the secret into an environment variable rather than testing the expression in
an `if:`, because a secret is not available to a job-level condition.

`pip-audit` and `npm audit` need no credential and run regardless, so Snyk is additive and the
workflow never depends on it.

**What it adds over the free checks.** A second advisory database with its own curation and
its own timing, which sometimes carries a finding days before the public feeds, plus severity
scoring and fix advice. **What it does not add:** it is still dependency scanning. It does not
look at our code, and on the free tier the test count is limited.

The back end scan exports `backend/uv.lock` to a throwaway requirements file under
`$RUNNER_TEMP` and scans that, because Snyk reads a requirements file for Python.
`--no-emit-project` drops `netscope` itself, which has no PyPI release. Nothing is committed,
and the exported versions are the pinned ones rather than a fresh resolution. The front end
is scanned too, behind the same file probe.

Snyk's pip scanner needed three accommodations, each of which cost a failed run to find.
Hashes are suppressed, because `uv export` writes them and Snyk's parser does not want them.
The environment is installed and `--command` points at its interpreter, because Snyk resolves
the dependency tree through a real interpreter rather than from the file alone, and without
one it fails with `SNYK-OS-PYTHON-0013`, "Missing required packages", even when every version
is pinned. And `--skip-unresolved` is set, which is Snyk's own documented remedy for that
error, so a package it cannot resolve is skipped rather than failing the run.

That last flag is a caveat worth stating plainly: a silently skipped package is not scanned by
Snyk. It is not a hole, because `pip-audit` covers the same tree with no such limitation and
fails on any finding. Snyk's value here is a second curated advisory database on top, not the
only line of defence.

The Snyk CLI is installed with `npm install --global snyk@1` rather than through
`snyk/actions/*`, because those actions are published only from a branch and offer no version
tag to pin to, which would be a looser pin than everything else in the file.

## Dependabot

Weekly, Mondays: `pip` on `/backend`, `npm` on `/frontend`, `github-actions` on `/`.

Patch and minor updates are grouped into one pull request per ecosystem, with a limit of three
open pull requests each. The git history here is a graded deliverable, and twenty single-bump
pull requests would bury the real work. Major bumps stay ungrouped, because a major version is
a behaviour change that deserves its own review.

Dependabot opens pull requests. It does not fail anything. The audit jobs are the gate.

## Action pinning

Third-party actions are pinned to a major version tag: `actions/checkout@v4`,
`actions/setup-node@v4`, `astral-sh/setup-uv@v5`. This matches `ci.yml`.

**What that exposes.** A tag is a mutable pointer. Whoever controls the action's repository,
or anyone who compromises it, can move `v4` to different code, and the next run of this
workflow executes that code with this workflow's token and its access to the checkout. Pinning
to a full commit SHA removes that: a SHA cannot be moved, so a published version is the
version that runs, forever.

**Why it was not done.** The blast radius here is small and bounded: `permissions: contents:
read`, a public repository with no deployment credentials, and one optional third-party token
whose worst case is a leaked free-tier Snyk account. Against that, SHA pins need a renovation
tool to stay current or they silently rot on an old version with its own bugs, and the
assignment's own history is meant to be readable. For anything holding a deployment
credential, or any repository with a write token or a release pipeline, SHA pinning is the
correct choice and this trade would go the other way.

## What this does not cover

Stated plainly, because a green workflow is easy to over-read. All of the following are absent:

- **No static analysis of our own code for security bugs.** Nothing runs Bandit, Semgrep,
  CodeQL, or `ruff`'s `S` (flake8-bandit) rules. `ruff` runs in CI, but the selected rule set
  (`E F W I N UP B A C4 SIM RET ARG PTH RUF`) is correctness and style, not security. An
  injection, a path traversal in a loader, or an unsafe deserialisation in our own source
  would not be flagged by anything in this repository.
- **No secret scanning beyond `detect-private-key`.** The pre-commit hook in
  `.pre-commit-config.yaml` catches a PEM-format private key and nothing else. An API key, a
  bearer token, a password in a fixture, or a connection string would pass. There is no
  gitleaks or trufflehog, no server-side push protection, and no history scan. The pre-commit
  hook also only protects people who ran `pre-commit install`; it is not enforced in CI.
- **No container or image scanning.** There is no Dockerfile yet, so nothing scans a base
  image. The moment one is added, the OS packages in that base image become a large
  unexamined surface that neither `pip-audit` nor `npm audit` can see.
- **No software bill of materials.** Nothing emits CycloneDX or SPDX, so there is no artefact
  that answers "which versions were in the build we shipped" after the fact. Today that
  question can only be answered by re-resolving, which may give a different answer.
- **No license compliance check.** Nothing checks the license of any dependency. A copyleft
  license arriving through a transitive dependency would go unnoticed.
- **No verification that a lockfile matches an upstream registry.** Both halves are now
  locked: `backend/uv.lock` is committed and installed with `uv sync --locked`, and the front
  end has `package-lock.json` for `npm ci` once P15 lands. Both carry hashes, so a package
  whose contents changed under a fixed version is detected. Neither is checked against a
  registry mirror or a signing authority, so a compromised package published under a new
  version and then legitimately locked by Dependabot would pass. That is what dependency
  review on pull requests, item 4 below, partly addresses.
- **No CI hardening.** Actions are tag-pinned (see above), `GITHUB_TOKEN` permissions are
  read-only at the workflow level, and there is no `pull_request_target` anywhere, but there
  is no OIDC, no egress restriction on runners, and no artefact signing or provenance
  attestation.
- **No dependency review on pull requests.** Nothing blocks a pull request that introduces a
  brand new dependency with a known advisory at the moment it is introduced; it is caught on
  the next audit run rather than at the point of change.
- **No runtime protection of any kind.** No rate limiting, no authentication, no
  authorisation. The API is local and stateless by design, and that is a design boundary, not
  a security control.

## First internal release

The smallest set of additions that would make this adequate for an internal deployment, in
priority order. Each line is a day of work or less.

1. ~~**Lock both halves.**~~ **Done**, and it was the item that changed what the other
   checks mean. `backend/uv.lock` is committed, `make install` and both workflows use
   `uv sync --locked`, `make check` runs `uv lock --check` so a dependency change cannot land
   without its lockfile, and the Snyk scan exports the lock rather than re-resolving. The
   front end half arrives as `package-lock.json` with P15.
2. **Real secret scanning in CI.** Add gitleaks as a job and turn on GitHub push protection.
   `detect-private-key` covers one key format for people who installed the hook. A leaked
   token is the most likely real incident for a repository like this.
3. **Static analysis of our own code.** Turn on `ruff`'s `S` rules in `backend/pyproject.toml`
   for the cheapest version, then add CodeQL (free for public repositories) for Python and
   TypeScript. This closes the largest category gap above: today nothing looks at our source.
4. **Dependency review on pull requests.** Add `actions/dependency-review-action` so a new
   dependency with a known advisory is blocked at the point of introduction instead of on the
   next scheduled run.
5. **Drop the npm threshold for production dependencies.** A second gate,
   `npm audit --omit=dev --audit-level=moderate`, keeping `high` for dev tooling.
6. **Container scanning, once there is a container.** Trivy or Grype on the built image, in
   the same workflow, failing on high and critical in the OS layer.
7. **An SBOM per build.** CycloneDX from both halves, uploaded as a workflow artefact, so the
   contents of a shipped build can be answered later without re-resolving.

License compliance sits below all of these for an internal tool that is not distributed, and
would move up sharply if it ever shipped to a customer.
