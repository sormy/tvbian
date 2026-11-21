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
# a board with a tree for the mainline next2 kernel ships it beside its own: each kernel's menu
# entry boots the tree it was translated for, through a per-kernel link the kernel hooks below keep
NEXT2=$BOARDS_DIR/$BOARD/next2
FDT_LINKS=/usr/lib/tvb/fdt
if [ -f "$NEXT2/board.dtb" ]; then
  cp "$NEXT2/board.dtb" "$LIB/board-next2.dtb"
  # one command line for every kernel: next2's UART console, which the vendor kernels, their UART0
  # the FIQ debugger's, skip
  BOARD_CMDLINE="$BOARD_CMDLINE console=ttyS0,1500000n8"
fi
echo "$BOARD_ID" >"$LIB/board-id"
echo "$BOARD_NAME" >"$LIB/board-name"
[ -z "${BOARD_PCB:-}" ] || echo "$BOARD_PCB" >"$LIB/board-pcb"

# loader files only: nothing in this package writes a sector
[ -z "${BOARD_UBOOT:-}" ] || cp "/out/uboot/$BOARD/u-boot.bin" "$LIB/u-boot.bin"
[ ! -f "$BOARDS_DIR/$BOARD/factory_idbloader.bin" ] || cp "$BOARDS_DIR/$BOARD/factory_idbloader.bin" "$LIB/idbloader.bin"

bash /repo/package/install-list.sh "$BOARDS_DIR/$BOARD/package.list" "$BOARDS_DIR" "$ROOT"

mkdir -p "$ROOT/usr/share/u-boot-menu/conf.d"
if [ -f "$LIB/board-next2.dtb" ]; then
  FDT="U_BOOT_FDT_DIR=$FDT_LINKS/
U_BOOT_FDT=board.dtb"
  for hook in postinst postrm; do
    mkdir -p "$ROOT/etc/kernel/$hook.d"
    cp "/repo/package/board-fdt.$hook" "$ROOT/etc/kernel/$hook.d/tvb-board-fdt"
  done
else
  FDT=U_BOOT_FDT=/usr/lib/tvb/board.dtb
fi
cat >"$ROOT/usr/share/u-boot-menu/conf.d/tvb.conf" <<CONF
$FDT
U_BOOT_MENU_LABEL=TVBian
U_BOOT_TIMEOUT=10
U_BOOT_PARAMETERS="$BOARD_CMDLINE $TVB_CMDLINE"
CONF

cat >"$ROOT/DEBIAN/postinst" <<'SCRIPT'
#!/bin/sh
set -e
[ "$1" = configure ] || exit 0
# the kernels installed before this package each take their tree's link; one this board has no
# tree for is left without, as the hook says
if [ -x /etc/kernel/postinst.d/tvb-board-fdt ]; then
  for version in $(linux-version list); do
    /etc/kernel/postinst.d/tvb-board-fdt "$version" || true
  done
fi
# extlinux.conf names the tree, which the kernel's own hook cannot see before this package exists
[ ! -x /usr/sbin/u-boot-update ] || u-boot-update
SCRIPT
chmod 0755 "$ROOT/DEBIAN/postinst"
cat >"$ROOT/DEBIAN/postrm" <<SCRIPT
#!/bin/sh
set -e
[ "\$1" != purge ] || rm -rf $FDT_LINKS
SCRIPT
chmod 0755 "$ROOT/DEBIAN/postrm"

{
  printf 'Package: tvb-%s\nVersion: %s\nArchitecture: arm64\n' "$BOARD" "$VERSION"
  printf 'Maintainer: TVBian <archive@tvbian.com>\n'
  printf 'Depends: tvb-base, linux-image-tvb-%s, u-boot-menu%s\n' \
    "$BOARD_KERNEL" "${BOARD_DEPENDS:+, ${BOARD_DEPENDS// /, }}"
  printf 'Provides: tvb-board\nConflicts: tvb-board\n'
  printf 'Section: admin\nPriority: optional\nX-Tvb-Family: %s\n' "$BOARD_FAMILY"
  printf 'X-Tvb-Inputs: %s\n' "$(bash /repo/release/inputs.sh board "$BOARD")"
  printf 'Description: TVBian board support for the %s\n' "$BOARD_NAME"
  printf ' The board'\''s device tree, its firmware and settings, and its loader files.\n'
} >"$ROOT/DEBIAN/control"
FILE=tvb-${BOARD}_${VERSION}_arm64.deb
dpkg-deb --root-owner-group -Zxz -b "$ROOT" "/out/debs/$FILE" >/dev/null
echo "✓ $FILE"
