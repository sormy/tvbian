#!/bin/bash
# Build whitesur-theme: WhiteSur's prebuilt GTK themes and its icon theme at their <VERSION> tag,
# and its cursors at a pinned commit, the repository having no tags.
#   build.sh <version> <inputs>, from extras/build.sh
set -euo pipefail
# shellcheck source=/dev/null
. /repo/extras/whitesur/extra.conf

PACKAGE_VERSION=$1
INPUTS=$2
TAG=${VERSION//./-}
GTK_URL=https://github.com/vinceliuice/WhiteSur-gtk-theme/archive/refs/tags/$TAG.tar.gz
ICONS_URL=https://github.com/vinceliuice/WhiteSur-icon-theme/archive/refs/tags/$TAG.tar.gz
CURSORS_COMMIT=e190baf618ed95ee217d2fd45589bd309b37672b
CURSORS_URL=https://github.com/vinceliuice/WhiteSur-cursors/archive/$CURSORS_COMMIT.tar.gz
GTK_VARIANTS="WhiteSur-Dark WhiteSur-Light"
BUILD_DEPENDS="curl ca-certificates xz-utils libgtk-3-bin"

WORK=/work/whitesur
ROOT=$WORK/pkg
DEB=/out/debs/whitesur-theme_${PACKAGE_VERSION}_all.deb

fetch() {  # fetch <url> <dir>
  mkdir -p "$2"
  curl -fsSL "$1" | tar -xz -C "$2" --strip-components=1
}

install_gtk() {
  local v
  mkdir -p "$ROOT/usr/share/themes"
  for v in $GTK_VARIANTS; do
    tar -xJf "$WORK/gtk/release/$v.tar.xz" -C "$ROOT/usr/share/themes"
  done
}

# the blue default, plain, light and dark
install_icons() {
  mkdir -p "$ROOT/usr/share/icons"
  (cd "$WORK/icons" && bash ./install.sh -d "$ROOT/usr/share/icons" -t default >/dev/null)
}

install_cursors() {
  cp -R "$WORK/cursors/dist" "$ROOT/usr/share/icons/WhiteSur-cursors"
}

install_licences() {
  local doc=$ROOT/usr/share/doc/whitesur-theme
  mkdir -p "$doc"
  cp "$WORK/gtk/COPYING" "$doc/COPYING.gtk"
  cp "$WORK/icons/COPYING" "$doc/COPYING.icons"
  cp "$WORK/cursors/LICENSE" "$doc/COPYING.cursors"
}

package() {
  mkdir -p "$ROOT/DEBIAN"
  cat >"$ROOT/DEBIAN/control" <<CONTROL
Package: whitesur-theme
Version: $PACKAGE_VERSION
Architecture: all
Maintainer: TVBian <archive@tvbian.com>
Section: x11
Priority: optional
X-Tvb-Inputs: $INPUTS
Description: WhiteSur GTK, icon and cursor themes, light and dark
 vinceliuice's WhiteSur $TAG: GTK 2, 3 and 4 themes, icons and cursors.
CONTROL
  dpkg-deb --root-owner-group -Zxz -b "$ROOT" "$DEB" >/dev/null
}

rm -rf "$WORK" && mkdir -p "$WORK"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends $BUILD_DEPENDS
fetch "$GTK_URL" "$WORK/gtk"
fetch "$ICONS_URL" "$WORK/icons"
fetch "$CURSORS_URL" "$WORK/cursors"
install_gtk
install_icons
install_cursors
install_licences
package
echo "✓ whitesur-theme: $DEB"
