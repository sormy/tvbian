#!/bin/bash
# Print what joins an extra's version to our revision: +tvb, after the version it rebuilds; ~tvb for
# a backport from SOURCE_SUITE, below that suite's own build of the same version, which replaces it.
#   separator.sh <name>, from extras/<name>/extra.conf
set -euo pipefail
# shellcheck source=/dev/null
. "$(dirname "$0")/$1/extra.conf"
if [ -n "${SOURCE_SUITE:-}" ]; then echo "~tvb"; else echo "+tvb"; fi
