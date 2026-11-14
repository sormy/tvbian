#!/usr/bin/env bash
# Regenerate a board's tree from its factory DTB: kernel -> factory_board.dts, board.dts and
# board.dtb; uboot -> factory_uboot.dts and uboot.dts.
#
# Stages, each auditable on its own:
#   1. mechanical — dtcx decompiles the blob as its vendor wrote it, named from the headers of
#      BOARD_<KIND>_DTB_SOURCE, and refuses a tree that does not decompile back to the blob's own.
#   2. mechanical, where BOARD_<KIND>_DTB_SOURCE has a bases/<source>.translate.conf — translate.py
#      writes that tree in the target's dialect: factory_<name>_translated.dts.
#   3. judgement — apply the patch: what we change, and whatever the translation left, the result
#      naming and compiling against the target's headers.
#
# Usage: tools/board/build-dtb.sh <kernel|uboot> [board...]   # default: every board with the patch
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
BOARDS_DIR="$REPO/boards"
BASES="$REPO/tools/dtcx/bases"
DTC="$REPO/build/bin/dtc"
DTCX="$REPO/tools/dtcx/dtcx.py"
TRANSLATE="$REPO/tools/dtcx/translate.py"
UPSTREAM="$REPO/tools/dtcx/upstream.py"
CANONICAL="$REPO/tools/dtcx/canonical.py"
# an explicit phandle as dtc and dtcx write one, a trailing comment allowed
EXPLICIT_PHANDLE='^\s*(linux,)?phandle\s*=\s*<[^<>]*>;\s*(/\*.*\*/)?\s*$'

case "${1:-}" in
	kernel) NAME=board; KEY=BOARD_KERNEL; DTCX_FLAGS=-n; DTC_FLAGS=-@ ;;
	# the factory U-Boot blob has no __symbols__ to drop or rebuild
	uboot) NAME=uboot; KEY=BOARD_UBOOT; DTCX_FLAGS=--strict; DTC_FLAGS= ;;
	*) echo "usage: $0 <kernel|uboot> [board...]"; exit 1 ;;
esac
shift

boards() { for c in "$BOARDS_DIR"/*/board.conf; do d=$(dirname "$c"); [ ! -f "$d/$NAME.patch" ] || basename "$d"; done; }
BOARDS="${*:-$(boards)}"
[ -n "$BOARDS" ] || { echo "no boards/<board>/$NAME.patch found — name a board"; exit 1; }
[ -x "$DTC" ] || { echo "Need the patched dtc. Run: ./build.sh tool dtc"; exit 1; }
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

# <stem>.dts, preprocessed against the target's headers, into <stem>.dtb
compile() {
	# || return: called as `compile … || …`, where bash does not stop on a failing command
	cc -E -nostdinc -undef -D__DTS__ -x assembler-with-cpp -P -I "$TARGET_INCLUDE" -o "$1.pp" "$1.dts" ||
		return
	# shellcheck disable=SC2086  # DTC_FLAGS is empty or one flag
	"$DTC" -q $DTC_FLAGS -I dts -O dtb -o "$1.dtb" "$1.pp"
}

for BOARD in $BOARDS; do
	DIR="$BOARDS_DIR/$BOARD"
	if [ ! -f "$DIR/factory_$NAME.dtb" ] || [ ! -f "$DIR/$NAME.patch" ]; then
		echo "$BOARD has no factory_$NAME.dtb and $NAME.patch"; exit 1
	fi
	SOURCE=$(sed -n "s/^${KEY}_DTB_SOURCE=//p" "$DIR/board.conf")
	TARGET=$(sed -n "s/^${KEY}_DTB_TARGET=//p" "$DIR/board.conf")
	VIEW_BASE=$(sed -n "s/^${KEY}_DTB_UPSTREAM=//p" "$DIR/board.conf")
	for base in "$SOURCE" "$TARGET"; do
		[ -f "$BASES/$base.conf" ] ||
			{ echo "boards/$BOARD/board.conf: ${KEY}_DTB_SOURCE/_TARGET names no base in tools/dtcx/bases/: '$base'"; exit 1; }
	done
	TARGET_SOURCE=$(sed -n 's/^source //p' "$BASES/$TARGET.conf")
	TARGET_INCLUDE=$(python3 "$DTCX" --include "$TARGET")

	printf '  %s %s:' "$BOARD" "$NAME" >&2
	# everything is written to $tmp first and published only when every check has passed
	python3 "$DTCX" "$DTCX_FLAGS" "$SOURCE" "$DIR/factory_$NAME.dtb" > "$tmp/factory_$NAME.dts"
	PATCH_BASE="$tmp/factory_$NAME.dts"
	if [ -f "$BASES/$SOURCE.translate.conf" ]; then
		PATCH_BASE="$tmp/factory_${NAME}_translated.dts"
		python3 "$TRANSLATE" "$SOURCE" "$TARGET" "$tmp/factory_$NAME.dts" > "$PATCH_BASE"
	fi

	# -F0: a hunk that only applies with fuzz has landed on the wrong node, and the result still
	# compiles — refuse it rather than ship a mis-grafted tree
	patch -s -F0 -p0 --no-backup-if-mismatch -o "$tmp/$NAME.dts" "$PATCH_BASE" < "$DIR/$NAME.patch"
	grep -qF "/* dt-bindings from $TARGET_SOURCE */" "$tmp/$NAME.dts" ||
		{ echo "$BOARD: $NAME.patch names another source than $TARGET's"; exit 1; }
	compile "$tmp/$NAME" || { echo "$BOARD: $NAME.dts does not compile against $TARGET"; exit 1; }
	# the factory's explicit phandles keep its numbering, noise in a tree people read: the kernel
	# tree drops them, dtc numbers its own, and canonical.py proves only the numbering moved
	if [ "$NAME" = board ]; then
		grep -vE "$EXPLICIT_PHANDLE" "$tmp/$NAME.dts" > "$tmp/free.dts"
		! grep -nE '^\s*(linux,)?phandle\s*=' "$tmp/free.dts" ||
			{ echo "$BOARD: an explicit phandle the build cannot drop, above"; exit 1; }
		compile "$tmp/free" || { echo "$BOARD: board.dts without its explicit phandles does not compile"; exit 1; }
		python3 "$CANONICAL" --base "$TARGET" "$tmp/$NAME.dtb" "$tmp/free.dtb" ||
			{ echo "$BOARD: board.dts without its explicit phandles is another tree"; exit 1; }
		mv "$tmp/free.dts" "$tmp/$NAME.dts"
		mv "$tmp/free.dtb" "$tmp/$NAME.dtb"
	fi
	# a kernel tree's upstream view, on the board's own base or the one its bases name (a
	# translation's, or the target's), proven to describe the dtb it was written from
	VIEW=
	if [ "$NAME" = board ] && { [ -n "$VIEW_BASE" ] || grep -qs '^soc ' "$BASES/$SOURCE.translate.conf" "$BASES/$TARGET.conf"; }; then
		python3 "$UPSTREAM" --prove "$tmp/$NAME.dtb" ${VIEW_BASE:+--soc "$VIEW_BASE"} "$SOURCE" "$TARGET" "$tmp/$NAME.dts" > "$tmp/upstream.dts" ||
			{ echo "$BOARD: board-upstream.dts does not describe board.dtb"; exit 1; }
		VIEW=1
	fi

	mv "$tmp/factory_$NAME.dts" "$DIR/factory_$NAME.dts"
	[ "$PATCH_BASE" = "$tmp/factory_$NAME.dts" ] || mv "$PATCH_BASE" "$DIR/$(basename "$PATCH_BASE")"
	cp "$tmp/$NAME.dts" "$DIR/$NAME.dts"
	# U-Boot's build compiles uboot.dts itself; the kernel's board.dtb is what the package ships
	[ "$NAME" = uboot ] || cp "$tmp/$NAME.dtb" "$DIR/board.dtb"
	echo "-> boards/$BOARD/$NAME.dts"
	if [ -n "$VIEW" ]; then
		mv "$tmp/upstream.dts" "$DIR/board-upstream.dts"
		echo "-> boards/$BOARD/board-upstream.dts"
	fi
done
