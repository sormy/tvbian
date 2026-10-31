#!/bin/bash
# Exit 0 when Debian's source already carries an extra's fixes: every patch applies in reverse.
#   carried.sh <name> <Debian's version>, after version.sh enabled the source archives
set -euo pipefail
# shellcheck source=/dev/null
. "/repo/extras/$1/extra.conf"
cd "$(mktemp -d)"
apt-get source -qq --only-source "$SOURCE=$2" >/dev/null
cd "$SOURCE"-*/
for p in $PATCHES; do
  patch -R -p1 -s -f --dry-run <"/repo/$p" >/dev/null || exit 1
done
