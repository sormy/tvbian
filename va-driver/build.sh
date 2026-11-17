#!/bin/bash
# Build the VA-API driver inside the build container: one driver, every backend.
#   build.sh            tvb-va-driver
#   build.sh check      the driver and the CPU test engine, then tests/vaapi_test.py
set -euo pipefail
TARGET=${1:-package}

SRC=/repo/va-driver
WORK=/work/va-driver
BUILD=/out/va-driver
CPUS=${TVB_BUILD_CPUS:-$(nproc)}
VERSION=${TVB_BUILD_REVISION:-0~local}
DRI_DIR=/usr/lib/aarch64-linux-gnu/dri
BUILD_DEPENDS="pkg-config cmake meson ninja-build libdrm-dev libva-dev"
RUN_DEPENDS="libva2, libstdc++6"
# every backend: each one's init declines without its hardware, and the first that finds it serves
DEFINES="-DHAVE_MPP=1 -DHAVE_REQUEST=1 -DHAVE_V4L2M2M=1"
REQUEST_BACKEND="backend_request.c request_h264.c request_hevc.c request_vp8.c request_vp9.c
  vp9_header.c request_mpeg2.c request_mpeg4.c request_vc1.c"
BACKENDS="backend_mpp.c $REQUEST_BACKEND backend_v4l2m2m.c v4l2.c"
# the GPUs' DRM drivers a client may open the driver through: libva names the file after them
GPU_DRIVERS="lima panfrost panthor etnaviv v3d msm"
MPP_REPO=https://github.com/rockchip-linux/mpp.git
# its 1.1.0 release
MPP_COMMIT=c08762ebfadeb4e986d2fed993bc7a54862d3ebe
MPP_PATCH=/repo/patches/mpp/0001-osal-run-the-singletons-init-when-called-not-at-load.patch
FRONT_END="driver picture surface pixels encode bitstream settings h264 hevc vp8 vp9 mpeg2 jpeg mpeg4 vc1"
# the host's test engine: FFmpeg's release, its H.264 decoder able to hand out in decode order
FFMPEG_VERSION=9.0.2
FFMPEG_PATCH=/repo/patches/ffmpeg/0039-avcodec-h264dec-add-a-decode_order-option.patch
FFMPEG_DECODERS=h264,hevc,vp8,vp9,mpeg2video,mjpeg,mpeg4,h263,vc1,wmv3
FFMPEG_ENCODERS=libx264,libx265,mjpeg
FFMPEG_PREFIX=$WORK/ffmpeg-prefix
CHECK_DEPENDS="libx264-dev libx265-dev nasm ffmpeg vainfo xvfb mpv gstreamer1.0-tools
  gstreamer1.0-plugins-bad"
CFLAGS="-std=gnu11 -Wall -Wextra -Wno-unused-parameter -Werror"

install_depends() {
  apt-get update -qq
  # shellcheck disable=SC2086  # one package per word
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends $BUILD_DEPENDS "$@" \
    >/dev/null
}

# fetch <repo> <commit> <dir>: the commit alone, once
fetch() {
  [ "$(git -C "$3" rev-parse HEAD 2>/dev/null)" = "$2" ] && return 0
  rm -rf "$3" && git init -q "$3"
  git -C "$3" fetch -q --depth 1 "$1" "$2"
  git -C "$3" checkout -q FETCH_HEAD
}

build_mpp() {
  local inputs
  inputs=$( (echo "$MPP_COMMIT"; cat "$MPP_PATCH") | sha256sum | cut -d' ' -f1)
  [ "$(cat "$WORK/mpp-prefix/.inputs" 2>/dev/null)" != "$inputs" ] || return 0
  fetch "$MPP_REPO" "$MPP_COMMIT" "$WORK/mpp"
  git -C "$WORK/mpp" checkout -q -- .
  patch -s -d "$WORK/mpp" -p1 <"$MPP_PATCH"
  rm -rf "$WORK/mpp-build" "$WORK/mpp-prefix"
  cmake -S "$WORK/mpp" -B "$WORK/mpp-build" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$WORK/mpp-prefix" >/dev/null
  cmake --build "$WORK/mpp-build" -j "$CPUS" >/dev/null
  cmake --install "$WORK/mpp-build" >/dev/null
  echo "$inputs" >"$WORK/mpp-prefix/.inputs"
}

# the flags each library linked into the driver adds to its compile and link
mpp_flags() {
  echo "-I$WORK/mpp-prefix/include -I$WORK/mpp/inc -I$WORK/mpp/osal/inc" \
    "$WORK/mpp-prefix/lib/librockchip_mpp.a -lstdc++"
}

build_test_ffmpeg() {
  local inputs
  inputs=$( (cat "$FFMPEG_PATCH"; echo "$FFMPEG_DECODERS $FFMPEG_ENCODERS") | sha256sum | cut -d' ' -f1)
  [ "$(cat "$FFMPEG_PREFIX/.inputs" 2>/dev/null)" != "$inputs" ] || return 0
  [ -s "$WORK/ffmpeg.tar.xz" ] ||
    curl -fsSL -o "$WORK/ffmpeg.tar.xz" "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz"
  rm -rf "$WORK/ffmpeg-$FFMPEG_VERSION" "$FFMPEG_PREFIX"
  tar -xJf "$WORK/ffmpeg.tar.xz" -C "$WORK"
  patch -s -d "$WORK/ffmpeg-$FFMPEG_VERSION" -p1 <"$FFMPEG_PATCH"
  (cd "$WORK/ffmpeg-$FFMPEG_VERSION" &&
    ./configure --prefix="$FFMPEG_PREFIX" --disable-autodetect --disable-doc --disable-programs \
      --disable-everything --enable-pic --enable-static --disable-shared --enable-gpl \
      --enable-libx264 --enable-libx265 \
      --enable-decoder="$FFMPEG_DECODERS" --enable-encoder="$FFMPEG_ENCODERS" >/dev/null &&
    make -j "$CPUS" >/dev/null 2>&1 && make install >/dev/null)
  echo "$inputs" >"$FFMPEG_PREFIX/.inputs"
}

# compile <out> <defines> <sources> <flags>: the front end and the backends, nothing exported but
# the init symbol
# shellcheck disable=SC2046,SC2086  # word lists
compile() {
  cc $CFLAGS -O2 -fPIC -shared -fvisibility=hidden $2 $(pkg-config --cflags libva libdrm) \
    $(for f in $FRONT_END backend; do echo "$SRC/src/$f.c"; done) $(for f in $3; do echo "$SRC/src/$f"; done) \
    $4 $(pkg-config --libs libva libdrm) -lm -lpthread \
    -Wl,--exclude-libs,ALL -Wl,-Bsymbolic -Wl,--no-undefined -Wl,-z,defs -o "$1"
}

# shellcheck disable=SC2046  # word lists
build_probe() {
  cc $CFLAGS -O2 "$SRC/tests/va_probe.c" $(pkg-config --cflags --libs libva libva-drm libdrm) -ldl \
    -o "$1/va_probe"
}

# the driver, under each GPU's name, and the probe, in $BUILD/driver/
build_driver() {
  local dir=$BUILD/driver name
  build_mpp
  rm -rf "$dir" && mkdir -p "$dir"
  compile "$dir/tvb_drv_video.so" "$DEFINES" "$BACKENDS" "$(mpp_flags)"
  for name in $GPU_DRIVERS; do ln -s tvb_drv_video.so "$dir/${name}_drv_video.so"; done
  build_probe "$dir"
  echo "✓ $dir"
}

# /dev/dri/va: the GPU's render node, for a program that opens only the node it is named, as
# Chromium does. udev sees a node's platform driver, which a GPU's DRM driver shares. The system
# heap for the video group: a surface's own memory, which the driver exports to the compositor.
write_udev_rule() {
  local rules=$1/usr/lib/udev/rules.d/70-tvb-va-driver.rules name
  mkdir -p "$(dirname "$rules")"
  {
    for name in $GPU_DRIVERS; do
      echo "SUBSYSTEM==\"drm\", KERNEL==\"renderD*\", DRIVERS==\"$name\", SYMLINK+=\"dri/va\""
    done
    echo 'SUBSYSTEM=="dma_heap", KERNEL=="system", GROUP="video", MODE="0660"'
  } >"$rules"
}

package() {
  local dir=$BUILD/driver root=$WORK/pkg deb name
  deb=/out/debs/tvb-va-driver_${VERSION}_arm64.deb
  rm -rf "$root" && mkdir -p "$root$DRI_DIR" "$root/DEBIAN"
  # libva names the driver after the DRM driver of the node a client opens
  cp "$dir/tvb_drv_video.so" "$root$DRI_DIR/"
  for name in $GPU_DRIVERS; do ln -s tvb_drv_video.so "$root$DRI_DIR/${name}_drv_video.so"; done
  # GStreamer's va plugin passes over an unknown driver: told for the user manager and login shells
  install -D -m 0644 "$SRC/deb/gst-va.conf" "$root/usr/lib/environment.d/50-tvb-va-driver.conf"
  install -D -m 0644 "$SRC/deb/gst-va.sh" "$root/etc/profile.d/tvb-va-driver.sh"
  echo /etc/profile.d/tvb-va-driver.sh >"$root/DEBIAN/conffiles"
  write_udev_rule "$root"
  install -m 0755 "$SRC/deb/postinst" "$root/DEBIAN/postinst"
  cat >"$root/DEBIAN/control" <<CONTROL
Package: tvb-va-driver
Version: $VERSION
Architecture: arm64
Maintainer: TVBian <archive@tvbian.com>
Depends: $RUN_DEPENDS
Section: video
Priority: optional
X-Tvb-Inputs: $(bash /repo/release/inputs.sh va-driver)
Description: VA-API driver for V4L2 and Rockchip MPP video engines
 Hardware decode and encode for VA-API programs on a stateless or stateful V4L2 decoder, or
 Rockchip's MPP, under the names libva looks for on the GPU's render node.
CONTROL
  mkdir -p "$(dirname "$deb")"
  dpkg-deb --root-owner-group -Zxz -b "$root" "$deb" >/dev/null
  echo "✓ $deb"
}

# the CPU test engine, with the Cedrus backend writing its controls out for the mapping test
build_host() {
  local dir=$BUILD/host
  build_test_ffmpeg
  rm -rf "$dir" && mkdir -p "$dir"
  compile "$dir/tvb_drv_video.so" "-DHAVE_LAVC=1 -DHAVE_REQUEST=1 -I$FFMPEG_PREFIX/include" \
    "backend_lavc.c $REQUEST_BACKEND backend_v4l2m2m.c v4l2.c" \
    "$FFMPEG_PREFIX/lib/libavcodec.a $FFMPEG_PREFIX/lib/libavutil.a $(pkg-config --libs x264 x265)"
  build_probe "$dir"
}

# the unit tests and the rebuilds' replay, under the sanitizers
# shellcheck disable=SC2046,SC2086  # word lists
build_unit() {
  local dir=$BUILD/host/unit test
  mkdir -p "$dir"
  for test in "$SRC"/tests/unit/test_*.c "$SRC/tests/unit/replay.c"; do
    cc $CFLAGS -g -O1 -fsanitize=address,undefined -fno-sanitize-recover=all \
      $(pkg-config --cflags libva libdrm) "$test" \
      $(for f in $FRONT_END vp9_header; do echo "$SRC/src/$f.c"; done) "$SRC/tests/unit/no_backend.c" \
      $(pkg-config --libs libva libdrm) -lm -lpthread -o "$dir/$(basename "$test" .c)"
  done
}

check() {
  local unit=0 clips=(--clips "$BUILD/clips")
  python3 "$SRC/tests/vaapi_test.py" unit --driver-dir "$BUILD/host" "${clips[@]}" || unit=$?
  python3 "$SRC/tests/vaapi_test.py" host --driver-dir "$BUILD/host" "${clips[@]}"
  return "$unit"
}

mkdir -p "$WORK"
case $TARGET in
  check)
    # shellcheck disable=SC2086
    install_depends $CHECK_DEPENDS
    build_driver
    build_host
    build_unit
    check
    ;;
  package)
    install_depends
    build_driver
    package
    ;;
  *) echo "usage: build.sh [check]" >&2; exit 1 ;;
esac
