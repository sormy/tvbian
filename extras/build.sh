#!/bin/bash
# Build an extra: Debian's own source package with our patches over it, every binary it makes,
# versioned <Debian's version>+tvb<revision> so apt prefers it over the version it rebuilds; or an
# upstream release beside Debian's, by the extra's own build.sh, at <VERSION>+tvb<revision>.
#   build.sh <name>, from extras/<name>/extra.conf
set -euo pipefail

NAME=$1
EXTRA=/repo/extras/$NAME
# shellcheck source=/dev/null
. "$EXTRA/extra.conf"

UPSTREAM_VERSION=$(bash /repo/extras/version.sh "$NAME")
PACKAGE_VERSION=$UPSTREAM_VERSION+tvb$TVB_BUILD_REVISION
OUT=/out/debs
# shellcheck source=/dev/null
. /repo/build-env/ccache.sh

[ ! -f "$EXTRA/build.sh" ] || exec bash "$EXTRA/build.sh" "$PACKAGE_VERSION"

WORK=/work/extras/$SOURCE
LOG=$WORK/build.log

fetch_source() {
  rm -rf "$WORK" && mkdir -p "$WORK" && cd "$WORK"
  apt-get source -qq --only-source "$SOURCE=$UPSTREAM_VERSION" >/dev/null
  cd "$SOURCE"-*/
  DEBIAN_FRONTEND=noninteractive apt-get build-dep -y -qq ./ >/dev/null
}

add_patches() {
  mkdir -p debian/patches
  for p in $PATCHES; do
    cp "/repo/$p" debian/patches/
    basename "$p" >>debian/patches/series
  done
}

# into the template too where the package regenerates its control from one, as mesa does
stamp_inputs() {
  local inputs f
  inputs=$(bash /repo/release/inputs.sh extra "$NAME" "$UPSTREAM_VERSION")
  for f in debian/control debian/control.in; do
    [ ! -f "$f" ] || sed -i "/^Package: $PACKAGE\$/a XB-X-Tvb-Inputs: $inputs" "$f"
  done
  grep -q "^XB-X-Tvb-Inputs: " debian/control ||
    { echo "✗ $PACKAGE: no such package in $SOURCE" >&2; exit 1; }
}

# dated as Debian's newest entry, so the same inputs build the same bytes
add_changelog_entry() {
  local p
  {
    printf '%s (%s) %s; urgency=medium\n\n' "$SOURCE" "$PACKAGE_VERSION" "$TVB_BUILD_SUITE"
    for p in $PATCHES; do printf '  * %s\n' "$(basename "$p" .patch)"; done
    printf '\n -- TVBian <archive@tvbian.com>  %s\n\n' "$(dpkg-parsechangelog -S Date)"
    cat debian/changelog
  } >debian/changelog.tvb
  mv debian/changelog.tvb debian/changelog
}

build() {
  DEB_BUILD_OPTIONS="nocheck parallel=$TVB_BUILD_CPUS" dpkg-buildpackage -b -uc -us >"$LOG" 2>&1 ||
    { tail -30 "$LOG"; exit 1; }
}

collect_debs() {
  local debs
  debs=$(find .. -maxdepth 1 -name '*.deb' ! -name '*-dbgsym_*')
  cp $debs "$OUT/"
  echo "✓ $SOURCE $PACKAGE_VERSION: $(echo "$debs" | wc -l) debs"
}

fetch_source
add_patches
stamp_inputs
add_changelog_entry
build
collect_debs
