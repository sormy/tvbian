#!/bin/bash
# Build a session package, inside the build container: Debian's programs as its depends and our
# defaults for them, from session/<name>/package.list and its session.conf.
#   session.sh <name>   -> /out/debs/tvb-<name>_<revision>_all.deb
set -euo pipefail
NAME=$1
SRC=/repo/session/$NAME
PACKAGE=tvb-$NAME
VERSION=${TVB_BUILD_REVISION:-0~local}
ROOT=/work/package/session/$NAME
# shellcheck source=/dev/null
. "$SRC/session.conf"
rm -rf "$ROOT" && mkdir -p "$ROOT/DEBIAN"
bash /repo/package/install-list.sh "$SRC/package.list" "$SRC" "$ROOT"
# under /etc, the owner's edits survive an upgrade
(cd "$ROOT" && find etc -type f | sed 's|^|/|' | sort) >"$ROOT/DEBIAN/conffiles"

cat >"$ROOT/DEBIAN/postinst" <<'SCRIPT'
#!/bin/sh
set -e
# the drop-ins this package adds: a running box sees them now
[ ! -d /run/systemd/system ] || systemctl daemon-reload
SCRIPT
chmod 0755 "$ROOT/DEBIAN/postinst"

# one line each: a conf may wrap its lists
oneline() { tr '\n' ' ' <<<"$1" | tr -s ' ' | sed 's/^ //; s/ $//'; }
cat >"$ROOT/DEBIAN/control" <<CONTROL
Package: $PACKAGE
Version: $VERSION
Architecture: all
Maintainer: TVBian <archive@tvbian.com>
Depends: $(oneline "$DEPENDS")
Recommends: $(oneline "$RECOMMENDS")
Section: x11
Priority: optional
X-Tvb-Inputs: $(bash /repo/release/inputs.sh session "$NAME")
Description: $DESCRIPTION
 Its programs are Debian's own; this package adds their system-wide defaults, which a user's own
 configuration overrides.
CONTROL
dpkg-deb --root-owner-group -Zxz -b "$ROOT" "/out/debs/${PACKAGE}_${VERSION}_all.deb" >/dev/null
echo "✓ ${PACKAGE}_${VERSION}_all.deb"
