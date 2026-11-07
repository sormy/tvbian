#!/bin/bash
# Build tvb-<board>, inside the build container: the board's tree, loader files and package.list.
#   board.sh <board>   -> /out/debs/tvb-<board>_<revision>_arm64.deb
set -euo pipefail
BOARD=$1
BOARDS_DIR=/repo/boards
# shellcheck source=/dev/null
. "$BOARDS_DIR/$BOARD/board.conf"
: "${BOARD_FAMILY:?boards/$BOARD/board.conf names no BOARD_FAMILY}" "${BOARD_NAME:?boards/$BOARD/board.conf names no BOARD_NAME}"
: "${BOARD_CMDLINE:?boards/$BOARD/board.conf names no BOARD_CMDLINE}"
[ "${BOARD_ID:-}" = "$BOARD" ] || { echo "boards/$BOARD/board.conf: BOARD_ID=${BOARD_ID:-} is not its directory" >&2; exit 1; }
# shellcheck source=/dev/null
. "$BOARDS_DIR/common/cmdline.conf"
VERSION=${TVB_BUILD_REVISION:-0~local}
ROOT=/work/package/$BOARD
LIB=$ROOT/usr/lib/tvb
rm -rf "$ROOT" && mkdir -p "$ROOT/DEBIAN" "$LIB"

cp "$BOARDS_DIR/$BOARD/board.dtb" "$LIB/board.dtb"
echo "$BOARD_ID" >"$LIB/board-id"
echo "$BOARD_NAME" >"$LIB/board-name"
[ -z "${BOARD_PCB:-}" ] || echo "$BOARD_PCB" >"$LIB/board-pcb"

# loader files only: nothing in this package writes a sector
[ -z "${BOARD_UBOOT:-}" ] || cp "/out/uboot/$BOARD/u-boot.bin" "$LIB/u-boot.bin"
[ ! -f "$BOARDS_DIR/$BOARD/factory_idbloader.bin" ] || cp "$BOARDS_DIR/$BOARD/factory_idbloader.bin" "$LIB/idbloader.bin"

bash /repo/package/install-list.sh "$BOARDS_DIR/$BOARD/package.list" "$BOARDS_DIR" "$ROOT"

mkdir -p "$ROOT/usr/share/u-boot-menu/conf.d"
cat >"$ROOT/usr/share/u-boot-menu/conf.d/tvb.conf" <<CONF
U_BOOT_FDT=/usr/lib/tvb/board.dtb
U_BOOT_TIMEOUT=10
U_BOOT_PARAMETERS="$BOARD_CMDLINE $TVB_CMDLINE"
CONF

cat >"$ROOT/DEBIAN/postinst" <<'SCRIPT'
#!/bin/sh
set -e
# extlinux.conf names the tree, which the kernel's own hook cannot see before this package exists
[ "$1" != configure ] || [ ! -x /usr/sbin/u-boot-update ] || u-boot-update
SCRIPT
chmod 0755 "$ROOT/DEBIAN/postinst"

# a renamed board supersedes its former package: Replaces lets apt overwrite the old box's files,
# and a last tvb-<old>, in epoch 1, Depends on this one and pulls it in on upgrade. Unversioned,
# Breaks would match that transition too, and apt would keep the old package back.
{
  printf 'Package: tvb-%s\nVersion: %s\nArchitecture: arm64\n' "$BOARD" "$VERSION"
  printf 'Maintainer: TVBian <archive@tvbian.com>\n'
  printf 'Depends: tvb-base, linux-image-tvb-%s, u-boot-menu%s\n' \
    "$BOARD_KERNEL" "${BOARD_DEPENDS:+, ${BOARD_DEPENDS// /, }}"
  printf 'Provides: tvb-board\nConflicts: tvb-board\n'
  [ -n "${BOARD_RENAMED_FROM:-}" ] &&
    printf 'Replaces: tvb-%s (<< 1:0)\nBreaks: tvb-%s (<< 1:0)\n' "$BOARD_RENAMED_FROM" "$BOARD_RENAMED_FROM"
  printf 'Section: admin\nPriority: optional\nX-Tvb-Family: %s\n' "$BOARD_FAMILY"
  printf 'X-Tvb-Inputs: %s\n' "$(bash /repo/release/inputs.sh board "$BOARD")"
  printf 'Description: TVBian board support for the %s\n' "$BOARD_NAME"
  printf ' The board'\''s device tree, its firmware and settings, and its loader files.\n'
} >"$ROOT/DEBIAN/control"
dpkg-deb --root-owner-group -Zxz -b "$ROOT" "/out/debs/tvb-${BOARD}_${VERSION}_arm64.deb" >/dev/null
echo "✓ tvb-${BOARD}_${VERSION}_arm64.deb"
