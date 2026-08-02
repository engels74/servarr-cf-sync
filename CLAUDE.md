# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

A GitHub Actions-driven syncer that pushes Radarr/Sonarr custom formats (JSON files in `custom_formats/`) to multiple live *arr instances. Almost all logic lives in a single script, `sync_script.py`. There is no test suite, and no lint, format, type-check, or coverage configuration is committed — do not invent commands for those.

## Essential Commands

Run everything from the repository root; `sync_script.py:365` resolves `custom_formats` as a relative path.

```bash
# Install dependencies (matches CI exactly)
uv pip install --system -r requirements.txt

# Run the sync (requires live instance credentials in the environment)
python sync_script.py
```

There is no offline validation harness. With no `RADARR_*`/`SONARR_*` env pair set, the script logs an error and exits 1 at `sync_script.py:393-395` — before any custom format is read — so a bare run only proves the module imports. Custom format JSON is parsed only once at least one instance is configured, and `load_custom_formats` reads every file up front before the first network call, so a malformed file fails the whole run rather than one format.

CI installs Python 3.14 (`.github/workflows/sync-custom-formats.yml`). The code requires 3.11+ (`typing.NotRequired`, PEP 604 unions).

## Architecture Overview

`sync_script.py` has three collaborating classes plus `main()`:

- **`main()`** — discovers instances from the environment. It reads `RADARR_{n:03d}_URL` / `RADARR_{n:03d}_API_KEY` starting at `001` and **stops at the first missing pair** (`sync_script.py:370-377`); same loop for Sonarr. Instances become tuples of `(name, url, api_key)` where name is e.g. `Radarr_003`.
- **`CustomFormatSyncer`** — loads every `*.json` in `custom_formats/`, decides what to sync, and drives the per-instance work.
- **`APIClient`** — a `requests.Session` per instance with the `X-Api-Key` header, talking to `/api/v3/customformat` and `/api/v3/qualityprofile`.
- **`VersionManager`** — owns `version.json`, the persisted map of `filename -> last synced semver`.

Data flow for one format file: parse JSON → `should_sync_to_instance` filters per instance → `prepare_format_for_sync` builds the API payload → `sync_format` matches an existing format **by `name`** and PUTs or POSTs → `sync_format_score` walks every quality profile and rewrites matching `formatItems` scores.

`prepare_format_for_sync` (`sync_script.py:278-288`) forwards **only** `name`, `includeCustomFormatWhenRenaming`, and `specifications`. Every `cfSync_*` key is repository-local control metadata and never reaches the *arr API.

## Custom Format Files

`custom_formats/` is the only content directory. `custom_formats/_template.json` is the canonical starting point and is skipped by exact filename in both the version scan and the sync loop (`sync_script.py:200`, `sync_script.py:214`). Any other `.json` file added there is picked up automatically — there is no registry to update.

Control fields (see `custom_formats/README.md` for full descriptions):

| Field | Effect |
| --- | --- |
| `cfSync_version` | Semver gate for whether the file syncs. Required. |
| `cfSync_score` | Score written into every quality profile that already lists this format. |
| `cfSync_radarr` / `cfSync_sonarr` | Per-type opt-out. Both default to `true`. |
| `cfSync_instances` | Explicit allowlist that **overrides** the two booleans (`sync_script.py:267-271`). |

`cfSync_instances` accepts full names (`"Radarr_003"`) or bare 3-digit strings (`"003"`). A bare number matches *both* `Radarr_003` and `Sonarr_003` — use full names when you need one and not the other.

### Adding a custom format

1. Copy `custom_formats/_template.json` to a new kebab-case name. Historical files used a target suffix: `block-german-dl-both.json`, `scenegroups-movies.json`, `scenegroups-tvseries.json`.
2. Set `name` to the string that should appear in Radarr/Sonarr — this is the match key against existing formats, so renaming it creates a second format instead of updating the first.
3. Set `cfSync_version`, `cfSync_score`, and the targeting fields.
4. Leave `version.json` alone; CI writes it.

Prefer the template's dict form for `specifications[].fields`:

```json
"fields": {
  "value": "(?i)german(?:\\.[\\w-]+)*\\.dl\\."
}
```

`sync_format` also accepts a list of `{"name", "value"}` objects and normalizes the dict form into it (`sync_script.py:304-317`), but the dict form is what the template and every historical format used.

## Version and CI Interaction

`version.json` is machine-managed state, committed back by the workflow as `Update version after sync [skip ci]`. To make a change sync, bump `cfSync_version` in the format file — editing `version.json` by hand will just be overwritten.

Two conditions trigger a sync (`sync_script.py:225`): the file's version is newer than the stored version, **or** the file's version is lower than the highest version across all format files. The second condition means a file left behind the fleet's highest version re-syncs and logs a warning on every run. Keep versions moving together rather than bumping one file far ahead.

The workflow (`.github/workflows/sync-custom-formats.yml`) runs on push to `main` touching `custom_formats/**`, on a daily cron, and via `workflow_dispatch`. It is skipped entirely when the head commit message contains `[skip ci]` — that is how the bot's own version commit avoids a loop, and how the repository's history marks work-in-progress commits that should not hit live instances.

## Critical Gotchas

- **Adding a 4th instance needs two edits.** The discovery loop stops at the first gap, and the workflow only passes secrets for `001`–`003`. Add the new `RADARR_004_URL` / `RADARR_004_API_KEY` pair to the `env:` block in `.github/workflows/sync-custom-formats.yml`; setting the repository secret alone does nothing. Never hardcode a URL or key in `sync_script.py` — every credential arrives through the environment.
- **Version state advances even after partial failure.** Per-instance `requests` errors are logged and skipped (`sync_script.py:245-247`), then `update_version` runs unconditionally (`sync_script.py:249`). A format that failed on one instance will not be retried on the next run unless you bump `cfSync_version` again.
- **Score sync only updates existing profile entries.** `sync_format_score` rewrites `formatItems` whose `format` id already matches (`sync_script.py:349`); it never appends a new entry. A profile that has not yet picked up the format is left untouched.
- **Instance type is inferred from the name string**, via `'radarr' if 'Radarr' in instance_name else 'sonarr'` (`sync_script.py:274`). If you change the naming scheme in `main()`, this check and the `cfSync_instances` number-suffix parsing both break.
- **Dependencies are unpinned and Renovate-managed.** `requirements.txt` lists bare `requests` and `semver`; `renovate.json` groups non-major updates. Do not pin versions by hand — that fights the configured update flow.

## Additional Documentation

- `custom_formats/README.md` — read before authoring or editing a custom format; documents each `cfSync_*` field and carries a complete worked example.
- `custom_formats/_template.json` — copy this rather than writing a format from scratch.
- `.github/workflows/sync-custom-formats.yml` — read when changing sync triggers, the Python version, or the set of wired instance secrets.
- `README.md` — user-facing setup and links to the project wiki; read when changing anything that affects how forkers configure the repository.
