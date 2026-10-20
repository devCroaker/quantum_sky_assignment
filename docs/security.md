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

Pull requests, pushes to `main`, and a weekly cron at 04:17 UTC on Mondays.

The schedule is the part that earns its keep. A pull-request trigger tells you about the code
you just wrote. It never tells you that a dependency you merged six weeks ago had an advisory
published yesterday, because nothing in the repository changed. On a project where the code
sits still between milestones, the scheduled run is the only trigger that catches that case.

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
- Because the project has no lockfile, the audited versions are whatever the resolver picked
  on the day the job ran. Two runs a week apart can audit different versions. See the gaps
  section.

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

### 3. `snyk`, optional and credential-free by default

Snyk needs an account token and this repository has none. The job therefore probes
`${{ secrets.SNYK_TOKEN }}` in its first step, writes an output, and gates every later step on
it. With no token the job prints an explanation and succeeds. It never fails, and it never
blocks the workflow.

That is not politeness. Secrets are not available to workflows triggered from a fork, and a
clone of this repository by a reviewer has no secrets at all, so a Snyk job that failed
without a token would be red on every fork and on every fresh clone. A permanently red job is
worse than no job.

**To enable it:**

1. Create a free Snyk account and copy the API token from <https://app.snyk.io/account>.
2. In this repository, go to **Settings > Secrets and variables > Actions > New repository
   secret**.
3. Name it exactly `SNYK_TOKEN`. It must be a repository secret, not an environment secret
   and not a variable, because the workflow reads `secrets.SNYK_TOKEN` with no `environment:`
   set.

Nothing else changes. The next run picks it up. `pip-audit` and `npm audit` keep working
either way, so Snyk is additive and the workflow is never dependent on it.

**What it adds over the free checks.** A second advisory database with its own curation and
its own timing, which sometimes carries a finding days before the public feeds, plus severity
scoring and fix advice. **What it does not add:** it is still dependency scanning. It does not
look at our code, and on the free tier the test count is limited.

The back end scan freezes the resolved environment to a throwaway requirements file under
`$RUNNER_TEMP` and scans that, because Snyk reads a requirements file for Python and this
project declares ranges in `pyproject.toml` with no lockfile. Nothing is committed. The front
end is scanned too, behind the same file probe.

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
- **No runtime dependency pinning beyond the lockfile, on either half.** The front end will
  have `package-lock.json` once P15 lands, which pins the tree for `npm ci` but is not
  integrity-verified against a registry mirror. The back end has **no lockfile at all**: it
  declares ranges (`fastapi>=0.115`, and so on) in `backend/pyproject.toml`, so two installs
  on different days can produce different versions. The audit result is therefore a statement
  about the day it ran, not about a reproducible artefact. The P20 plan entry asked for
  lockfiles on both halves; they are not part of this change, which is the largest known gap
  in this document.
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

1. **Lock both halves.** Commit a `uv.lock` (or a `requirements.txt` compiled with
   `uv pip compile`) for the back end, and `package-lock.json` for the front end, and make the
   audit jobs read the lockfiles. Without this, every other item on this list reports on an
   environment that is not reproducible. This is the one item that changes what the existing
   checks mean.
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
