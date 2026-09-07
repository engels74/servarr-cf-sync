#!/usr/bin/env bash
set -euo pipefail
uv venv --allow-existing --python 3.14 .venv
uv pip sync --require-hashes requirements-dev.txt
uv pip check
.venv/bin/ruff format --check sync_script.py tests
.venv/bin/ruff check sync_script.py tests
.venv/bin/basedpyright --warnings
.venv/bin/python -m unittest discover -s tests -v
