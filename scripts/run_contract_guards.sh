#!/usr/bin/env bash
set -euo pipefail

pytest -q tests/test_import_style_guard.py tests/test_std_logging_contract.py
