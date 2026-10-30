#!/usr/bin/env bash
# Build sunxi-fel into build/tools/sunxi-fel, for talking to an Allwinner box in FEL.
#
# Usage: ./build.sh tool sunxi-fel
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$(cd "$HERE/../.." && pwd)/build/tools/sunxi-fel"
BUILD="$OUT/src"   # scratch clone

SUNXI_TOOLS_REPO="https://github.com/linux-sunxi/sunxi-tools.git"
SUNXI_TOOLS_SHA="a08a24a2aa5804bde7fa6ea8cdb08135d018da33"   # master @ 2026-10-20

make_args=()
if command -v brew >/dev/null; then
  # Homebrew keeps libusb and dtc's libfdt out of the default search paths
  PKG_CONFIG_PATH="$(brew --prefix libusb)/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
  export PKG_CONFIG_PATH
  fdt=$(brew --prefix dtc)
  make_args=(LIBFDT_CFLAGS="-I$fdt/include" LIBFDT_LIBS="-L$fdt/lib -lfdt")
fi
pkg-config --exists libusb-1.0 zlib ||
  { echo "missing: libusb-1.0, zlib — brew install libusb dtc, or apt install libusb-1.0-0-dev zlib1g-dev libfdt-dev" >&2; exit 1; }

mkdir -p "$OUT"
if [ -d "$BUILD/.git" ]; then
  git -C "$BUILD" fetch --quiet "$SUNXI_TOOLS_REPO" "$SUNXI_TOOLS_SHA" || true
else
  rm -rf "$BUILD"
  git clone --quiet "$SUNXI_TOOLS_REPO" "$BUILD"
fi
git -C "$BUILD" checkout --quiet --force "$SUNXI_TOOLS_SHA"
git -C "$BUILD" clean -qfd

make -C "$BUILD" -s ${make_args[@]+"${make_args[@]}"} sunxi-fel
install -m 755 "$BUILD/sunxi-fel" "$OUT/sunxi-fel"
echo "built: build/tools/sunxi-fel/sunxi-fel"
