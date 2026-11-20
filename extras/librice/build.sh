#!/bin/bash
# Build librice0 and librice-dev: librice's C libraries, rice-proto and rice-io, at its <VERSION> tag.
#   build.sh <version> <inputs>, from extras/build.sh
set -euo pipefail
# shellcheck source=/dev/null
. /repo/extras/librice/extra.conf

PACKAGE_VERSION=$1
INPUTS=$2
URL=https://github.com/ystreet/librice/archive/refs/tags/v$VERSION.tar.gz
SHA256=4671e1835f9ab0f8d87e8d9e22b6bfb06f928aeae442841ab81881dff61e3f4b
# the first to read Rust 2024's #[unsafe(no_mangle)]: Debian's cargo-c bundles 0.27, whose headers
# come out empty
CBINDGEN_VERSION=0.29.4
BUILD_DEPENDS="curl ca-certificates cargo rustc cargo-c pkg-config libssl-dev"
WORK=/work/librice
STAGE=$WORK/stage
LIB_PACKAGE=librice0
LIBDIR=usr/lib/aarch64-linux-gnu

fetch() {
  rm -rf "$WORK" && mkdir -p "$WORK/src"
  curl -fsSL -o "$WORK/src.tar.gz" "$URL"
  echo "$SHA256  $WORK/src.tar.gz" | sha256sum -c --quiet
  tar -xzf "$WORK/src.tar.gz" -C "$WORK/src" --strip-components=1
}

# the crates' versions as their Cargo.lock pins them
build() {
  local crate
  cargo install -q cbindgen --version "$CBINDGEN_VERSION" --locked --root "$WORK/tools"
  for crate in rice-proto rice-io; do
    (cd "$WORK/src" && cargo cinstall --locked --release -j "$TVB_BUILD_CPUS" -p "$crate" \
      --prefix=/usr --libdir="/$LIBDIR" --destdir="$STAGE")
    regenerate_header "$crate"
  done
}

# cbindgen's declarations under cargo-c's version macros, which WebKit checks
regenerate_header() {
  local header=$STAGE/usr/include/rice/$1.h
  (cd "$WORK/src" && "$WORK/tools/bin/cbindgen" --quiet --config "$1/cbindgen.toml" --crate "$1" \
    --output "$WORK/$1.h")
  awk -v macros="$(grep -E '^#define RICE_[A-Z]+_(MAJOR|MINOR|PATCH) ' "$header")" \
    '{ print } /^#define LIBRICE_[A-Z_]+_H$/ { print ""; print macros }' "$WORK/$1.h" >"$header"
  grep -q "^#define RICE_" "$header" && grep -q "rice_" "$header"
}

# shlibs:Depends of the files given, as dpkg-shlibdeps finds them
depends_of() {
  (cd "$WORK" && mkdir -p debian && printf 'Source: librice\n\nPackage: x\nArchitecture: any\n' >debian/control &&
    dpkg-shlibdeps -O "$@" | sed -n 's/^shlibs:Depends=//p')
}

# deb <name> <depends> <description> <paths in the stage, globs expanded there...>
deb() {
  local name=$1 depends=$2 description=$3 root=$WORK/$1 lib
  shift 3
  rm -rf "$root" && mkdir -p "$root/DEBIAN" "$root/usr/share/doc/$name"
  # shellcheck disable=SC2068  # each path a glob, expanded in the stage
  (cd "$STAGE" && cp -a --parents $@ "$root/")
  cp "$WORK/src/LICENSE-MIT" "$WORK/src/LICENSE-APACHE" "$root/usr/share/doc/$name/"
  if [ "$name" = "$LIB_PACKAGE" ]; then
    # how a package built against it depends on it; the linker's cache refreshed as it lands
    for lib in rice-proto rice-io; do
      echo "lib$lib ${LIB_PACKAGE#librice} $LIB_PACKAGE (>= $PACKAGE_VERSION)"
    done >"$root/DEBIAN/shlibs"
    echo "activate-noawait ldconfig" >"$root/DEBIAN/triggers"
  fi
  cat >"$root/DEBIAN/control" <<CONTROL
Package: $name
Version: $PACKAGE_VERSION
Architecture: arm64
Maintainer: TVBian <archive@tvbian.com>
Depends: $depends
Section: libs
Priority: optional
X-Tvb-Inputs: $INPUTS
Description: $description
CONTROL
  dpkg-deb --root-owner-group -Zxz -b "$root" "/out/debs/${name}_${PACKAGE_VERSION}_arm64.deb" >/dev/null
}

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends $BUILD_DEPENDS >/dev/null
fetch
build
deb "$LIB_PACKAGE" "$(depends_of "$STAGE/$LIBDIR"/librice-*.so.*)" \
  "ICE (RFC 8445) in Rust: the rice-proto and rice-io C libraries" "$LIBDIR/librice-*.so.*"
deb librice-dev "$LIB_PACKAGE (= $PACKAGE_VERSION)" \
  "ICE (RFC 8445) in Rust: headers and pkg-config files" \
  usr/include/rice "$LIBDIR/librice-*.so" "$LIBDIR/pkgconfig/rice-*.pc"
echo "✓ librice $PACKAGE_VERSION: 2 debs"
