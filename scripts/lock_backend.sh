#!/usr/bin/env bash
# Regenerate the hashed backend lock files from backend/*.in with uv.
#
# The locks are universal (one file for Linux and Windows, platform-specific
# packages carry environment markers) and target Python 3.12, the version CI
# and the Windows bundle use. Existing pins are kept unless an upgrade is
# requested, so rerunning without .in changes reproduces the same files.
#
# Usage: scripts/lock_backend.sh [extra uv pip compile args]
#   e.g. scripts/lock_backend.sh --upgrade-package fastapi
set -euo pipefail
cd "$(dirname "$0")/.."

compile() {
  uv pip compile "$@" \
    --universal \
    --python-version 3.12 \
    --generate-hashes \
    --quiet \
    --custom-compile-command "scripts/lock_backend.sh"
}

compile backend/requirements.in -o backend/requirements.txt "$@"
compile backend/requirements-test.in -c backend/requirements.txt -o backend/requirements-test.txt "$@"
compile backend/requirements-build.in -c backend/requirements.txt -o backend/requirements-build.txt "$@"
