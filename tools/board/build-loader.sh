#!/usr/bin/env bash
# Build each board's USB service-mode loader into its board directory, byte-identical on a rebuild:
#   Rockchip:  maskrom_loader.bin, Rockchip's usbplug with that board's own DDR init, carved from its
#              factory idbloader; stamped with the time of the commit that last changed the idbloader.
#   Allwinner: fel_loader.bin, the U-Boot step's FEL loader, which serves the eMMC over USB, on
#              the DRAM settings of its factory boot0; stamped with its U-Boot tag's commit time.
#   Amlogic:   none; its factory U-Boot's burning mode serves the eMMC itself, through amlcmd.
#
# Usage: tools/board/build-loader.sh [board...]   # default: every board with a factory loader input
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
BOARDS_DIR="$REPO/boards"
RKDEV="$REPO/build/bin/rkdeveloptool"
RKBIN="$REPO/build/rkbin"

# --- pinned dependency (bump deliberately, never float) ---
RKBIN_REPO="https://github.com/rockchip-linux/rkbin.git"
RKBIN_SHA="ecb4fcbe954edf38b3ae037d5de6d9f5bccf81f4"
IDB_DDR_ENTRY=$((0x78))      # the idbloader header's CODE471 entry
RK3528_CHIP_TAG=8253          # "3528", as the loader header stores it, byte-reversed
RKBOOT_INI="RKBOOT/RK3528MINIALL.ini"             # declares NEWIDB + RC4_OFF; also names the usbplug and SPL
USBPLUG="bin/rk35/rk3528_usbplug_v1.04.bin"       # presence of this marks rkbin as fetched

boards() {
	for c in "$BOARDS_DIR"/*/board.conf; do
		d=$(dirname "$c")
		[ ! -f "$d/factory_idbloader.bin" ] && [ ! -f "$d/factory_boot0.bin" ] || basename "$d"
	done
}
BOARDS="${*:-$(boards)}"
[ -n "$BOARDS" ] || { echo "no boards/*/factory_idbloader.bin or factory_boot0.bin to build a loader from"; exit 1; }

rkbin() {
	[ -x "$RKDEV" ] || { echo "Need the patched rkdeveloptool. Run: ./build.sh tool rkdeveloptool"; exit 1; }
	[ ! -e "$RKBIN/$USBPLUG" ] || return 0
	rm -rf "$RKBIN" && mkdir -p "$RKBIN" && ( cd "$RKBIN"
		git init -q
		git fetch -q --depth 1 "$RKBIN_REPO" "$RKBIN_SHA" && git checkout -q FETCH_HEAD )
}

for BOARD in $BOARDS; do
	if [ -f "$BOARDS_DIR/$BOARD/factory_boot0.bin" ]; then
		"$REPO/build.sh" uboot "$BOARD" loader
		cp "$REPO/build/out/uboot/$BOARD/fel_loader.bin" "$BOARDS_DIR/$BOARD/fel_loader.bin"
		echo "-> boards/$BOARD/fel_loader.bin"
		continue
	fi
	IDB="$BOARDS_DIR/$BOARD/factory_idbloader.bin"
	[ -f "$IDB" ] || { echo "$BOARD has no factory_idbloader.bin or factory_boot0.bin: no loader"; exit 1; }
	rkbin
	OUT="$BOARDS_DIR/$BOARD/maskrom_loader.bin"

	# CODE471 is the box's own DDR init, carved from its factory idbloader rather than guessed from
	# rkbin's variants — its IDB entry is a u16 start sector, then a u16 sector count.
	DDR=board_ddr.bin
	SEC=$(od -An -tu2 -j "$IDB_DDR_ENTRY" -N 2 "$IDB" | tr -d ' ')
	CNT=$(od -An -tu2 -j "$((IDB_DDR_ENTRY + 2))" -N 2 "$IDB" | tr -d ' ')
	dd if="$IDB" of="$RKBIN/$DDR" bs=512 skip="$SEC" count="$CNT" status=none
	strings "$RKBIN/$DDR" | grep -q "^ddr-v" || { echo "no DDR blob at sector $SEC of $IDB"; exit 1; }

	# Rockchip's own ini with this board's DDR swapped in, so NEWIDB and RC4_OFF come from their file
	# rather than from ours. Paths in it are relative to the rkbin root, so pack from there.
	LOADER="loader-$BOARD.bin"
	sed -e "s|bin/rk35/rk3528_ddr_[^ ]*\.bin|$DDR|g" -e "s|^PATH=.*|PATH=$LOADER|" \
		"$RKBIN/$RKBOOT_INI" > "$RKBIN/config.ini"
	# the last commit that changed its content: a move alone must not restamp the loader
	epoch=$(git -C "$REPO" log -1 --follow --diff-filter=AM --format=%ct -- "$IDB")
	packed=0
	if ( cd "$RKBIN" && SOURCE_DATE_EPOCH="${epoch:-$(date +%s)}" "$RKDEV" pack > /dev/null ); then
		mv -f "$RKBIN/$LOADER" "$OUT"; packed=1
	fi
	rm -f "$RKBIN/$DDR" "$RKBIN/config.ini"   # never leave scratch in the pinned checkout
	[ "$packed" = 1 ] || { echo "pack failed for $BOARD"; exit 1; }

	# "LDR " is new-IDB, RC4 off — the only format this BootROM answers; the old "BOOT" format packs
	# fine and is then ignored in silence
	[ "$(head -c 4 "$OUT")" = "LDR " ] && head -c 64 "$OUT" | strings | grep -q "$RK3528_CHIP_TAG" ||
		{ echo "$BOARD: not an RK3528 new-IDB loader"; exit 1; }
	echo "-> boards/$BOARD/maskrom_loader.bin ($((CNT * 512)) B of DDR init)"
done
