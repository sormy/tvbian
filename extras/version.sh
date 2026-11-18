#!/bin/bash
# Print the version of an extra's source Debian has today: the newest of the suite, its updates and
# its security archive, and of SOURCE_SUITE for a backport; --suite leaves SOURCE_SUITE out.
#   version.sh [--suite] <name>, from extras/<name>/extra.conf
set -euo pipefail
own=false
[ "$1" != --suite ] || { own=true; shift; }
# shellcheck source=/dev/null
. "/repo/extras/$1/extra.conf"
# an extra from upstream names its own version
[ -z "${VERSION:-}" ] || { echo "$VERSION"; exit 0; }
sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/debian.sources
# an extra newer than its suite takes its source, not its binaries, from SOURCE_SUITE; one call's
# suite never lingers into the next
rm -f /etc/apt/sources.list.d/source-suite.sources
[ -z "${SOURCE_SUITE:-}" ] || $own ||
  printf 'Types: deb-src\nURIs: http://deb.debian.org/debian\nSuites: %s\nComponents: main\n' \
    "$SOURCE_SUITE" >/etc/apt/sources.list.d/source-suite.sources
apt-get update -qq >/dev/null
newest=""
for v in $(apt-cache showsrc --only-source "$SOURCE" | sed -n 's/^Version: //p'); do
  if [ -z "$newest" ] || dpkg --compare-versions "$v" gt "$newest"; then newest=$v; fi
done
[ -n "$newest" ] || { echo "✗ $SOURCE: no source in Debian's $TVB_BUILD_SUITE" >&2; exit 1; }
echo "$newest"
