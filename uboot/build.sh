#!/bin/bash
# Build one board's U-Boot, inside the build container, from the uboot/<conf>.conf its board.conf
# names as BOARD_UBOOT: /out/uboot/<board>/u-boot.bin, on the board's control tree where it has one
# (BOARD_UBOOT_DTB, else uboot). BL31 is rkbin's blob in binman's FIT, or TF-A built from source; an
# Allwinner board's DRAM settings are its factory boot0's.
set -euo pipefail
BOARD=$1
# shellcheck source=/dev/null
. "/repo/boards/$BOARD/board.conf"
# shellcheck source=/dev/null  # the conf: REPO, TAG, DEFCONFIG; CONFIGS, PATCHES, SOC, RKBIN, TFA_*, BOOT_PREBOOT...
. "/repo/uboot/${BOARD_UBOOT:?boards/$BOARD/board.conf names no BOARD_UBOOT}.conf"
TREE=/work/uboot/$BOARD
OUT=/out/uboot/$BOARD
DTS=/repo/boards/$BOARD/${BOARD_UBOOT_DTB:-uboot}.dts
BOOT0=/repo/boards/$BOARD/factory_boot0.bin
NAME=u-boot.bin

configs=${CONFIGS:-}
if [ -f "$BOOT0" ]; then
  [ "$(head -c 12 "$BOOT0" | tail -c 8)" = eGON.BT0 ] || { echo "✗ $BOOT0: no boot0 header" >&2; exit 1; }
  # the parameters boot0 trained and wrote back, 32 words from byte 56: clk, type, dx_odt, dx_dri,
  # ca_dri, odt_en, para1, para2, 14 mode registers, tpr0-3, tpr6, tpr10-14
  dram() { echo "0x$(od -An -tx4 -j $((56 + $1 * 4)) -N 4 "$BOOT0" | tr -d ' ')"; }
  case $(($(dram 1))) in
    3) type=DDR3_1333 ;;
    7) type=LPDDR3 ;;
    8) type=LPDDR4 ;;
    *) echo "✗ $BOARD: boot0 DRAM type $(($(dram 1))) has no mainline driver" >&2; exit 1 ;;
  esac
  configs="$configs SUNXI_DRAM_H616_$type=y DRAM_CLK=$(($(dram 0)))
    DRAM_SUNXI_DX_ODT=$(dram 2) DRAM_SUNXI_DX_DRI=$(dram 3) DRAM_SUNXI_CA_DRI=$(dram 4)
    DRAM_SUNXI_ODT_EN=$(dram 5) DRAM_SUNXI_TPR0=$(dram 22) DRAM_SUNXI_TPR6=$(dram 26)
    DRAM_SUNXI_TPR10=$(dram 27) DRAM_SUNXI_TPR11=$(dram 28) DRAM_SUNXI_TPR12=$(dram 29)"
fi

fetch() {  # repo, ref, dir
  mkdir -p "$3" && git -C "$3" init -q && git -C "$3" fetch -q --depth=1 "$1" "$2" &&
    git -C "$3" checkout -q FETCH_HEAD
}
rm -rf "$TREE" && mkdir -p "$OUT"
fetch "$REPO" "refs/tags/$TAG" "$TREE/u-boot"
SOURCE_DATE_EPOCH=$(git -C "$TREE/u-boot" log -1 --format=%ct)
export SOURCE_DATE_EPOCH
rm -rf "$TREE/u-boot/.git"   # a git checkout suffixes the version: 2026.10+, or -g<hash>
cd "$TREE/u-boot"
for p in ${PATCHES:-}; do patch -s -p1 -F0 <"/repo/$p"; done

if [ -f "$DTS" ]; then
  if [ -n "${SOC:-}" ]; then
    DT=$SOC-$BOARD
    cp "$DTS" "arch/arm/dts/$DT.dts"
    # the name upstream's Makefile globs for: binman's nodes, and what the factory tree lacks
    cp "/repo/uboot/$SOC-u-boot.dtsi" "arch/arm/dts/$DT-u-boot.dtsi"
    # the defconfig's own tree renamed throughout, before Kconfig derives OF_LIST and the FDT file
    generic=$(sed -n 's/^CONFIG_DEFAULT_DEVICE_TREE="\(.*\)"$/\1/p' "configs/$DEFCONFIG")
    sed "s|$generic|$DT|g" "configs/$DEFCONFIG" >"configs/tvb-${BOARD}_defconfig"
    DEFCONFIG=tvb-${BOARD}_defconfig
    configs="$configs DEFAULT_DEVICE_TREE=\"$DT\""
  else
    # an upstream tree's place, and the list binman packs, which the defconfig filled with its own
    DT=allwinner/tvb-$BOARD
    cp "$DTS" "dts/upstream/src/arm64/$DT.dts"
    configs="$configs DEFAULT_DEVICE_TREE=\"$DT\" OF_LIST=\"$DT\""
  fi
fi
make -s "$DEFCONFIG"
for c in $configs; do scripts/config --set-val "${c%%=*}" "${c#*=}"; done
[ -z "${BOOT_PREBOOT:-}" ] || scripts/config --set-str PREBOOT "$BOOT_PREBOOT"
make -s olddefconfig
# a symbol Kconfig drops, through a renamed or unmet dependency, would ship a quietly different build
for c in $configs; do
  grep -qx "CONFIG_$c" .config || { echo "✗ $BOARD: CONFIG_$c did not stick" >&2; exit 1; }
done

jobs=-j${TVB_BUILD_CPUS:-$(nproc)}
if [ -n "${RKBIN:-}" ]; then
  RK=/work/rkbin/$RKBIN_COMMIT
  [ -f "$RK/$BL31" ] || { rm -rf "$RK" && fetch "$RKBIN" "$RKBIN_COMMIT" "$RK"; }
  make -s "$jobs" BL31="$RK/$BL31" ROCKCHIP_TPL="$RK/$TPL"
  cp u-boot.itb "$OUT/$NAME"
elif [ -n "${TFA_REPO:-}" ]; then
  fetch "$TFA_REPO" "refs/tags/$TFA_TAG" "$TREE/tf-a"
  rm -rf "$TREE/tf-a/.git"
  for p in ${TFA_PATCHES:-}; do patch -s -p1 -F0 -d "$TREE/tf-a" <"/repo/$p"; done
  make -s -C "$TREE/tf-a" "$jobs" PLAT="$TFA_PLAT" DEBUG=0 \
    BUILD_MESSAGE_TIMESTAMP="\"$(date -u -d "@$SOURCE_DATE_EPOCH" '+%H:%M:%S, %b %d %Y')\"" bl31
  make -s "$jobs" BL31="$TREE/tf-a/build/$TFA_PLAT/release/bl31.bin" SCP=/dev/null
  cp u-boot-sunxi-with-spl.bin "$OUT/$NAME"
else
  make -s "$jobs" u-boot.bin
  cp u-boot.bin "$OUT/$NAME"
fi
echo "✓ $BOARD: $NAME, U-Boot $TAG${TFA_TAG:+ + TF-A $TFA_TAG}${type:+, $type at $(($(dram 0))) MHz}," \
  "$(stat -c %s "$OUT/$NAME") bytes"
