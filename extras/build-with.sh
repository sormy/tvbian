#!/bin/bash
# Print the extras whose packages an extra builds against, from its BUILD_WITH; or, with --order,
# every extra, each after those it builds against.
#   build-with.sh <name> | --order
set -euo pipefail
EXTRAS=$(dirname "$0")

deps() {
  # shellcheck source=/dev/null
  (. "$EXTRAS/$1/extra.conf"; for entry in ${BUILD_WITH:-}; do echo "${entry%%:*}"; done) | sort -u
}

ordered=()
visit() {
  local dep
  [[ " ${ordered[*]} " != *" $1 "* ]] || return 0
  for dep in $(deps "$1"); do visit "$dep"; done
  ordered+=("$1")
}

if [ "$1" = --order ]; then
  for c in "$EXTRAS"/*/extra.conf; do [ ! -f "$c" ] || visit "$(basename "$(dirname "$c")")"; done
  printf '%s\n' "${ordered[@]}"
else
  deps "$1"
fi
