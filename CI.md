# Development CI and controlled live synchronization

Every PR, default-branch push and manual dispatch runs `ci`, using the shared
Python 3.14 workflow and required `ci / required` aggregate. Missing, skipped,
failed or cancelled jobs cannot satisfy the gate. Generated PR dispatches verify
the exact live PR head before and after validation. Require this GitHub Actions
check with strict up-to-date branches, administrator enforcement, no bypasses and
zero mandatory approvals.

Run `bash .github/scripts/check.sh` locally. It creates an isolated environment,
installs hashed development dependencies, checks package compatibility, runs Ruff
format/lint and basedpyright basic mode (zero diagnostics), then nine offline tests.
Tests cover instance targeting/discovery, payload filtering/field conversion,
unchanged-format no-op, score updates, template exclusion, version persistence and
cleanup, real Requests transport against a loopback HTTP server, and all repository
format JSON/semver contracts. All fixture state is temporary; unexpected external
HTTP fails. The only source edits are AST-equivalent formatting and explicit JSON
serialization type boundaries; synchronization behavior and format data are preserved.

`requirements.in` pins the tested application dependencies;
`requirements-dev.in` adds validation tools. Both `.txt` lockfiles are generated
by `uv pip compile --python-version=3.14 --generate-hashes`, maintained by Renovate's
pip-compile manager and consumed with `--require-hashes`. The shared versioned
preset supplies common grouping; automerge is off pending the pre-1.0 preset
correction and activation. Full action version tags and uv versions are bot-managed.
Use the full option names with equals signs so Renovate can parse the generated headers:

```sh
uv pip compile --python-version=3.14 --generate-hashes requirements.in --output-file=requirements.txt
uv pip compile --python-version=3.14 --generate-hashes requirements-dev.in --output-file=requirements-dev.txt
```

Direct pins let Renovate classify each upgrade; weekly lockfile maintenance does not
silently upgrade unconstrained direct dependencies across major versions.

The existing live sync keeps its scheduled, manual and format-change triggers,
default-branch restriction, configured instance secrets and skip-ci escape hatch.
It runs offline validation first, then the live script, and proposes only generated
`version.json` on `fix/update-sync-checkpoint`. Explicit full CI dispatch ensures
GITHUB_TOKEN-generated commits receive checks. Enable **Allow GitHub Actions to
create and approve pull requests** before activation. Generated checkpoint commits
have Conventional Commit titles and sign-off; merging them does not retrigger the
format-path-filtered live workflow. Dispatch failures print manual recovery inputs.

Live instance compatibility is not established by offline tests. Existing behavior
still records a version after a per-instance request failure, re-synchronizes files
below the highest version, and updates scores only in existing profile entries.
A checkpoint PR is therefore not proof of complete delivery. Review live sync logs;
transactional success tracking/retry semantics need a separate application change.
Until a checkpoint PR merges, the next scheduled run can repeat an otherwise
completed update; updates are matched by format name and preserve the existing
no-op behavior. No live sync or credentialed instance request was run during this
implementation. The upstream template alone has no active format payload.
