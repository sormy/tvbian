#!/bin/bash
# Build ffmpeg9 from FFmpeg's release with extras/ffmpeg9/extra.conf's patches, and Rockchip's MPP.
#   build.sh <version> <inputs>, from extras/build.sh
set -euo pipefail
# shellcheck source=/dev/null
. /repo/extras/ffmpeg9/extra.conf

PACKAGE_VERSION=$1
INPUTS=$2
FFMPEG_URL=https://ffmpeg.org/releases/ffmpeg-$VERSION.tar.xz
MPP_REPO=https://github.com/rockchip-linux/mpp.git
MPP_TAG=1.1.0
INSTALL_DIR=/usr/lib/ffmpeg9
BUILD_DEPENDS="cmake pkg-config libdrm-dev libudev-dev libva-dev"
RUN_DEPENDS="libdrm2, libudev1, libva2, libva-drm2"

WORK=/work/ffmpeg9
MPP_SRC=$WORK/mpp
PREFIX=$WORK/prefix
FFMPEG_SRC=$WORK/ffmpeg-$VERSION
ROOT=$WORK/pkg
DEB=/out/debs/ffmpeg9_${PACKAGE_VERSION}_arm64.deb

build_mpp() {
  [ -d "$MPP_SRC/.git" ] || git clone --depth 1 --branch "$MPP_TAG" "$MPP_REPO" "$MPP_SRC"
  if ! git -C "$MPP_SRC" apply --reverse --check "/repo/$MPP_PATCH" 2>/dev/null; then
    git -C "$MPP_SRC" restore -- mpp/vproc/mpp_dec_vproc.c
    git -C "$MPP_SRC" apply "/repo/$MPP_PATCH"
  fi
  cmake -S "$MPP_SRC" -B "$WORK/mpp-build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$PREFIX"
  cmake --build "$WORK/mpp-build" -j "$TVB_BUILD_CPUS"
  cmake --install "$WORK/mpp-build"
}

# the release unpacked and patched again only when a patch changed
fetch_ffmpeg() {
  local patches
  patches=$(cd /repo && cat $PATCHES | sha256sum | cut -d' ' -f1)
  [ "$(cat "$FFMPEG_SRC/.tvb-inputs" 2>/dev/null)" != "$patches" ] || return 0
  curl -fL --retry 3 --retry-all-errors --connect-timeout 20 --max-time 180 \
    -o "$WORK/ffmpeg.tar.xz" "$FFMPEG_URL"
  rm -rf "$FFMPEG_SRC"
  tar -xJf "$WORK/ffmpeg.tar.xz" -C "$WORK"
  for p in $PATCHES; do patch -d "$FFMPEG_SRC" -p1 <"/repo/$p"; done
  echo "$patches" >"$FFMPEG_SRC/.tvb-inputs"
}

# static, its codecs only; it finds MPP in its own lib/ by the rpath
build_ffmpeg() {
  cd "$FFMPEG_SRC"
  PKG_CONFIG_PATH="$PREFIX/lib/pkgconfig" ./configure --prefix="$PREFIX" \
    --disable-autodetect --disable-doc --disable-debug \
    --enable-libdrm --enable-libudev --enable-v4l2-request --enable-v4l2-m2m --enable-rkmpp \
    --enable-vaapi \
    --enable-version3 --enable-static --disable-shared \
    --extra-ldflags="-Wl,-rpath-link,$PREFIX/lib -Wl,-rpath,$INSTALL_DIR/lib"
  make -j "$TVB_BUILD_CPUS" ffmpeg ffprobe
}

package() {
  local dir=$ROOT$INSTALL_DIR
  rm -rf "$ROOT" && mkdir -p "$dir/lib" "$ROOT/usr/bin" "$ROOT/DEBIAN"
  cp "$FFMPEG_SRC/ffmpeg" "$FFMPEG_SRC/ffprobe" "$dir/"
  cp -a "$PREFIX"/lib/librockchip_mpp.so* "$dir/lib/"
  ln -s "$INSTALL_DIR/ffmpeg" "$ROOT/usr/bin/ffmpeg9"
  ln -s "$INSTALL_DIR/ffprobe" "$ROOT/usr/bin/ffprobe9"
  {
    LD_LIBRARY_PATH="$dir/lib" "$dir/ffmpeg" -version
    echo "mpp $(git -C "$MPP_SRC" rev-parse HEAD)"
    echo "mpp patch $(sha256sum "/repo/$MPP_PATCH" | cut -d' ' -f1)"
    echo "patches $(cat "$FFMPEG_SRC/.tvb-inputs")"
  } >"$dir/build.txt"
  cat >"$ROOT/DEBIAN/control" <<EOF
Package: ffmpeg9
Version: $PACKAGE_VERSION
Architecture: arm64
Maintainer: TVBian <archive@tvbian.com>
Depends: $RUN_DEPENDS
Section: video
Priority: optional
X-Tvb-Inputs: $INPUTS
Description: FFmpeg 9 with V4L2 request, mem2mem and Rockchip MPP codecs
 ffmpeg9 and ffprobe9, beside Debian's ffmpeg.
EOF
  mkdir -p "$(dirname "$DEB")"
  dpkg-deb --root-owner-group -Zxz -b "$ROOT" "$DEB" >/dev/null
}

mkdir -p "$WORK" "$PREFIX"
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends $BUILD_DEPENDS
build_mpp
fetch_ffmpeg
build_ffmpeg
package
echo "✓ ffmpeg9: $DEB"
