#!/bin/bash
# Build an extra: Debian's own source package with our patches over it, every binary it makes,
# versioned <Debian's version>+tvb<revision> so apt prefers it over the version it rebuilds.
#   build.sh <name>, from extras/<name>/extra.conf
set -euo pipefail
# shellcheck source=/dev/null
. "/repo/extras/$1/extra.conf"
debian=$(bash /repo/extras/version.sh "$1")
version=$debian+tvb$TVB_BUILD_REVISION
src=/work/extras/$SOURCE
rm -rf "$src" && mkdir -p "$src" && cd "$src"
apt-get source -qq --only-source "$SOURCE=$debian" >/dev/null
cd "$SOURCE"-*/
DEBIAN_FRONTEND=noninteractive apt-get build-dep -y -qq ./ >/dev/null
mkdir -p debian/patches
for p in $PATCHES; do
  cp "/repo/$p" debian/patches/
  basename "$p" >>debian/patches/series
done
# into the template too where the package regenerates its control from one, as mesa does
inputs=$(bash /repo/release/inputs.sh extra "$1" "$debian")
for f in debian/control debian/control.in; do
  [ ! -f "$f" ] || sed -i "/^Package: $PACKAGE\$/a XB-X-Tvb-Inputs: $inputs" "$f"
done
grep -q "^XB-X-Tvb-Inputs: " debian/control || { echo "✗ $PACKAGE: no such package in $SOURCE" >&2; exit 1; }
# the entry dated as Debian's newest, so the same inputs build the same bytes
{
  printf '%s (%s) %s; urgency=medium\n\n' "$SOURCE" "$version" "$TVB_BUILD_SUITE"
  for p in $PATCHES; do printf '  * %s\n' "$(basename "$p" .patch)"; done
  printf '\n -- TVBian <archive@tvbian.com>  %s\n\n' "$(dpkg-parsechangelog -S Date)"
  cat debian/changelog
} >debian/changelog.tvb && mv debian/changelog.tvb debian/changelog
DEB_BUILD_OPTIONS="nocheck parallel=$TVB_BUILD_CPUS" dpkg-buildpackage -b -uc -us >"$src/build.log" 2>&1 ||
  { tail -30 "$src/build.log"; exit 1; }
find .. -maxdepth 1 -name '*.deb' ! -name '*-dbgsym_*' -exec cp {} /out/debs/ \;
echo "✓ $SOURCE $version: $(find .. -maxdepth 1 -name '*.deb' ! -name '*-dbgsym_*' | wc -l) debs"
