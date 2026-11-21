#!/bin/bash
# Print the X-Tvb-Inputs hash of one package group: what the plan compares with the published deb.
#   inputs.sh kernel <kernel/*.conf> <ref> | board <board> | firmware <dir> | base | keyring |
#             extra <name> <Debian's version> | va-driver | session <name>
# Beside the files, the versions of the tools that shape the group's bytes: none for copied files,
# so a build image changed for another step rebuilds nothing it does not touch.
set -euo pipefail
cd /repo
files() {
  case $1 in
    kernel)
      # shellcheck source=/dev/null
      . "$2"
      # shellcheck disable=SC2086  # FRAGMENT lists its files
      echo "$2" "$CONFIG" $FRAGMENT kernel/build.sh kernel/version.sh modules/build.sh
      sed -n 's/^\. //p' "$2"   # a conf it builds on
      for entry in $PATCHES; do echo "${entry#*:}"; done
      family=$(basename "$2" .conf)
      for m in modules/*.conf; do
        # shellcheck source=/dev/null
        (. "$m"; for k in $KERNELS; do [ "$k" = "$family" ] && exit 0; done; exit 1) || continue
        echo "$m"
        # shellcheck source=/dev/null
        (. "$m"; for entry in ${PATCHES:-}; do echo "${entry#*:}"; done)
      done ;;
    board)
      # shellcheck source=/dev/null
      . "boards/$2/board.conf"
      echo "boards/$2/board.dtb" "boards/$2/package.list" package/board.sh package/install-list.sh
      sed -E 's/#.*//' "boards/$2/package.list" | awk 'NF && $1 != "link" {print "boards/" $2}'
      if [ -n "${BOARD_UBOOT:-}" ]; then
        echo "uboot/$BOARD_UBOOT.conf" uboot/build.sh
        [ ! -f "boards/$2/${BOARD_UBOOT_DTB:-uboot}.dts" ] || echo "boards/$2/${BOARD_UBOOT_DTB:-uboot}.dts"
        # shellcheck source=/dev/null
        (. "uboot/$BOARD_UBOOT.conf"; echo ${PATCHES:-} ${TFA_PATCHES:-}; [ -z "${SOC:-}" ] || echo "uboot/$SOC-u-boot.dtsi")
      fi
      [ ! -f "boards/$2/factory_idbloader.bin" ] || echo "boards/$2/factory_idbloader.bin"
      [ ! -f "boards/$2/factory_boot0.bin" ] || echo "boards/$2/factory_boot0.bin"
      [ ! -f "boards/$2/next2/board.dtb" ] ||
        echo "boards/$2/next2/board.dtb" "boards/$2/next2/board.conf" package/board-fdt.postinst package/board-fdt.postrm ;;
    firmware)
      echo "firmware/$2/firmware.conf" "firmware/$2/package.list" package/firmware.sh package/install-list.sh
      sed -E 's/#.*//' "firmware/$2/package.list" | awk 'NF && $1 != "link" {print "firmware/" $2}' ;;
    base)
      echo base/package.list package/base.sh package/install-list.sh
      sed -E 's/#.*//' base/package.list | awk 'NF && $1 != "link" {print "base/" $2}' ;;
    keyring) echo keyring/tvb-archive-keyring.gpg package/keyring.sh ;;
    extra)
      echo "extras/$2/extra.conf" extras/build.sh extras/version.sh extras/carried.sh
      for f in build.sh debian.sh; do [ ! -f "extras/$2/$f" ] || echo "extras/$2/$f"; done
      # shellcheck source=/dev/null
      (. "extras/$2/extra.conf"; echo ${PATCHES:-}; [ -z "${SOURCES:-}" ] || find $SOURCES -type f | sort) ;;
    va-driver) echo va-driver/build.sh va-driver/src/* va-driver/deb/* patches/mpp/* ;;
    session)
      echo "session/$2/session.conf" "session/$2/package.list" package/session.sh \
        package/install-list.sh
      sed -E 's/#.*//' "session/$2/package.list" | awk -v d="session/$2/" 'NF && $1 != "link" {print d $2}' ;;
  esac
}
# settings <group> <arg>: what a conf sets, sorted, so a comment or a reordering moves nothing
settings() {
  case $1 in
    board) (
      # shellcheck source=/dev/null
      . "boards/$2/board.conf"
      for v in ${!BOARD_@}; do
        if [ "$v" = BOARD_DEPENDS ]; then echo "$v=$(tr ',' ' ' <<<"${!v}" | xargs -n1 | sort | xargs)"; else echo "$v=${!v}"; fi
      done
    ) ;;
  esac
}
tools() {
  case $1 in
    kernel | va-driver) gcc -dumpfullversion; ld --version | head -1 ;;
    board)
      # shellcheck source=/dev/null
      (. "boards/$2/board.conf"; [ -z "${BOARD_UBOOT:-}" ] || { gcc -dumpfullversion; ld --version | head -1; }) ;;
  esac
}
# shellcheck disable=SC2046  # one path per word
{ sha256sum $(files "$@" | tr ' ' '\n' | sort -u); echo "${3:-}"; settings "$@"; tools "$@"; } | sha256sum | cut -c1-16
