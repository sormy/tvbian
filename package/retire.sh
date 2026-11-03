#!/bin/bash
# Build the last tvb-<old>: a transition that only Depends on a renamed board's package, so a box
# still on the old name pulls tvb-<new> on upgrade. It ships no files; the new package takes them
# over with its Replaces and Breaks, versioned below this package's epoch 1.
#   retire.sh <board>   -> /out/debs/tvb-<old>_<revision>_all.deb, for a board that names
#                          BOARD_RENAMED_FROM in its board.conf
set -euo pipefail
BOARD=$1
BOARDS_DIR=/repo/boards
# shellcheck source=/dev/null
. "$BOARDS_DIR/$BOARD/board.conf"
: "${BOARD_RENAMED_FROM:?boards/$BOARD/board.conf names no BOARD_RENAMED_FROM}" "${BOARD_NAME:?}"
OLD=tvb-$BOARD_RENAMED_FROM
NEW=tvb-$BOARD
VERSION=${TVB_BUILD_REVISION:-1:0~local}
FILE=${OLD}_${VERSION#*:}_all.deb  # a file name never carries the epoch
ROOT=/work/package/retire-$OLD
rm -rf "$ROOT" && mkdir -p "$ROOT/DEBIAN"
{
  printf 'Package: %s\nVersion: %s\nArchitecture: all\n' "$OLD" "$VERSION"
  printf 'Maintainer: TVBian <archive@tvbian.com>\n'
  printf 'Depends: %s\n' "$NEW"
  printf 'X-Tvb-Inputs: %s\n' "$(bash /repo/release/inputs.sh retire "$BOARD")"
  printf 'Description: TVBian board support for the %s\n' "$BOARD_NAME"
  printf ' Retired in favour of %s, which now ships the same files.\n' "$NEW"
} >"$ROOT/DEBIAN/control"
dpkg-deb --root-owner-group -Zxz -b "$ROOT" "/out/debs/$FILE" >/dev/null
echo "✓ $FILE (transition to $NEW)"
