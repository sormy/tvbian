#!/bin/bash
# Build deqp: VK-GL-CTS opengl-es-cts-<VERSION> built surfaceless, and deqp-runner, as Mesa 25.0.7's
# CI runs them.
#   build.sh <version>, from extras/build.sh
set -euo pipefail
# shellcheck source=/dev/null
. /repo/extras/deqp/extra.conf

PACKAGE_VERSION=$1
CTS_REPO=https://github.com/KhronosGroup/VK-GL-CTS.git
CTS_TAG=opengl-es-cts-$VERSION
RUNNER_VERSION=0.20.3
GLES_MODULES="gles2 gles3 gles31"
INSTALL_DIR=/usr/lib/deqp
BUILD_DEPENDS="cmake ninja-build pkg-config python3 python3-lxml libegl-dev libgles-dev libgbm-dev
  libpng-dev zlib1g-dev cargo git ca-certificates"
# the surfaceless target loads the unversioned libEGL.so and libGLESv2.so
RUN_DEPENDS="libegl-dev, libgles-dev, libgbm1, libpng16-16t64"

WORK=/work/deqp
CTS_SRC=$WORK/VK-GL-CTS
CTS_BUILD=$WORK/build
CARGO=$WORK/cargo
MUSTPASS=$CTS_SRC/external/openglcts/data/gl_cts/data/mustpass/gles
ROOT=$WORK/pkg
DEB=/out/debs/deqp_${PACKAGE_VERSION}_arm64.deb

fetch_cts() {
  [ ! -d "$CTS_SRC/.git" ] || return 0
  git clone --depth 1 --branch "$CTS_TAG" "$CTS_REPO" "$CTS_SRC"
  python3 "$CTS_SRC/external/fetch_sources.py"
}

build_cts() {
  cmake -S "$CTS_SRC" -B "$CTS_BUILD" -G Ninja -DCMAKE_BUILD_TYPE=Release -DDEQP_TARGET=surfaceless
  ninja -C "$CTS_BUILD" $(for m in $GLES_MODULES; do echo "deqp-$m"; done) glcts
}

build_runner() {
  cargo install --locked --root "$CARGO" --version "$RUNNER_VERSION" deqp-runner
}

# each module beside its data: the build's copy where it made one, else the source's
install_tests() {
  local dir=$1 m
  for m in $GLES_MODULES; do
    mkdir -p "$dir/$m"
    cp "$CTS_BUILD/modules/$m/deqp-$m" "$dir/$m/"
    cp -r "$CTS_BUILD/modules/$m/$m" "$dir/$m/" 2>/dev/null || cp -r "$CTS_SRC/data/$m" "$dir/$m/"
  done
  mkdir -p "$dir/glcts" "$dir/mustpass"
  cp "$CTS_BUILD/external/openglcts/modules/glcts" "$dir/glcts/"
  cp -r "$CTS_BUILD/external/openglcts/modules/gl_cts" "$dir/glcts/" 2>/dev/null || true
  cp "$MUSTPASS"/aosp_mustpass/main/*.txt "$MUSTPASS"/khronos_mustpass/main/*.txt "$dir/mustpass/"
  cp "$CARGO/bin/deqp-runner" "$dir/"
}

package() {
  local dir=$ROOT$INSTALL_DIR
  rm -rf "$ROOT" && mkdir -p "$dir" "$ROOT/DEBIAN"
  install_tests "$dir"
  {
    git -C "$CTS_SRC" rev-parse HEAD
    "$dir/deqp-runner" --version
  } >"$dir/build.txt"
  cat >"$ROOT/DEBIAN/control" <<EOF
Package: deqp
Version: $PACKAGE_VERSION
Architecture: arm64
Maintainer: TVBian <archive@tvbian.com>
Depends: $RUN_DEPENDS
Section: misc
Priority: optional
Description: GLES conformance tests for TVBian validation
 VK-GL-CTS $CTS_TAG and deqp-runner $RUNNER_VERSION, as Mesa 25.0.7's CI runs them.
EOF
  dpkg-deb --root-owner-group -Zxz -b "$ROOT" "$DEB" >/dev/null
}

mkdir -p "$WORK"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends $BUILD_DEPENDS
fetch_cts
build_cts
build_runner
package
echo "✓ deqp: $DEB"
