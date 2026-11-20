#!/bin/bash
# Build libqtwpewebkit0 and libqtwpewebkit-dev from the repo's qtwpewebkit/ against our WPE WebKit.
#   build.sh <version> <inputs>, from extras/build.sh
set -euo pipefail

PACKAGE_VERSION=$1
INPUTS=$2
BUILD_DEPENDS="cmake ninja-build pkg-config g++ qt6-base-dev qt6-webchannel-dev libegl-dev libgles-dev"
WORK=/work/qtwpewebkit
STAGE=$WORK/stage
# the library's package, named for its soname
LIB_PACKAGE=libqtwpewebkit0
LIBDIR=usr/lib/aarch64-linux-gnu

build() {
  cmake -S /repo/qtwpewebkit -B "$WORK/build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX=/usr -DCMAKE_INSTALL_LIBDIR=lib/aarch64-linux-gnu
  cmake --build "$WORK/build" -j "$TVB_BUILD_CPUS"
  rm -rf "$STAGE"
  DESTDIR=$STAGE cmake --install "$WORK/build" >/dev/null
}

# shlibs:Depends of the files given, as dpkg-shlibdeps finds them
depends_of() {
  (cd "$WORK" && mkdir -p debian && printf 'Source: qtwpewebkit\n\nPackage: x\nArchitecture: any\n' >debian/control &&
    dpkg-shlibdeps -O "$@" | sed -n 's/^shlibs:Depends=//p')
}

# deb <name> <depends> <description> <paths in the stage, globs expanded there...>
deb() {
  local name=$1 depends=$2 description=$3 root=$WORK/$1
  shift 3
  rm -rf "$root" && mkdir -p "$root/DEBIAN"
  # shellcheck disable=SC2068  # each path a glob, expanded in the stage
  (cd "$STAGE" && cp -a --parents $@ "$root/")
  if [ "$name" = "$LIB_PACKAGE" ]; then
    # how a package built against it depends on it; the linker's cache refreshed as it lands
    echo "libqtwpewebkit ${LIB_PACKAGE#libqtwpewebkit} $LIB_PACKAGE (>= $PACKAGE_VERSION)" >"$root/DEBIAN/shlibs"
    echo "activate-noawait ldconfig" >"$root/DEBIAN/triggers"
  fi
  cat >"$root/DEBIAN/control" <<EOF
Package: $name
Version: $PACKAGE_VERSION
Architecture: arm64
Maintainer: TVBian <archive@tvbian.com>
Depends: $depends
Section: libs
Priority: optional
X-Tvb-Inputs: $INPUTS
Description: $description
EOF
  dpkg-deb --root-owner-group -Zxz -b "$root" "/out/debs/${name}_${PACKAGE_VERSION}_arm64.deb" >/dev/null
}

mkdir -p "$WORK"
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends $BUILD_DEPENDS >/dev/null
build
deb "$LIB_PACKAGE" "$(depends_of "$STAGE/$LIBDIR"/libqtwpewebkit.so.* \
  "$STAGE/$LIBDIR"/qtwpewebkit/web-process-extensions/*.so)" \
  "QtWebEngine's API over WPE WebKit" \
  "$LIBDIR/libqtwpewebkit.so.*" "$LIBDIR/qtwpewebkit"
deb libqtwpewebkit-dev "$LIB_PACKAGE (= $PACKAGE_VERSION), libwpewebkit-2.0-dev, qt6-base-dev" \
  "QtWebEngine's API over WPE WebKit: headers and CMake package" \
  usr/include/qtwpewebkit "$LIBDIR/libqtwpewebkit.so" "$LIBDIR/cmake/QtWpeWebKit"
echo "✓ qtwpewebkit $PACKAGE_VERSION: 2 debs"
