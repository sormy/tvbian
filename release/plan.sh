#!/bin/bash
# Decide each package group's version against the published apt index, inside the build container.
#   plan.sh -> /out/release/plan: "<step> <argument> <version> new|published", one group a line
# A group whose X-Tvb-Inputs matches a published deb is not rebuilt: its debs are fetched instead.
set -euo pipefail
cd /repo
APT=${TVB_APT_URL:-https://github.com/sormy/tvbian/releases/download/apt}
REL=/out/release
mkdir -p "$REL" /out/debs
rm -f "$REL/plan"
# published <file>: the repo's own copy; none only when nothing is published. Read as empty after a
# failed fetch, the index would expire everything this run did not build, and publish.sh delete it.
published() {
  local code
  code=$(curl -sSL -w '%{http_code}' -o "$REL/$1.published" "$APT/$1") || code=000
  case $code in
    200) ;;
    404) : >"$REL/$1.published" ;;
    *) echo "✗ $APT/$1: HTTP $code, refusing to plan against a repo it cannot read" >&2; exit 1 ;;
  esac
}
published Packages
published Contents

field() {  # field <package> <name> [inputs]: that field of the package's stanza, by inputs if given
  awk -v RS= -v p="$1" -v f="$2" -v i="${3:-}" '
    $0 ~ "(^|\n)Package: " p "\n" && (i == "" || $0 ~ "\nX-Tvb-Inputs: " i "(\n|$)") {
      n = split($0, l, "\n"); for (k = 1; k <= n; k++) if (index(l[k], f ": ") == 1) print substr(l[k], length(f) + 3)
    }' "$REL/Packages.published"
}
# stanzas <awk condition> [-v <name>=<value>]...: Package, Source, Version and Filename of each
# published stanza the condition matches
stanzas() {
  local cond=$1
  shift
  awk -v RS= "$@" '{
    pkg = src = ver = file = ""
    n = split($0, l, "\n")
    for (k = 1; k <= n; k++) {
      if (index(l[k], "Package: ") == 1) pkg = substr(l[k], 10)
      else if (index(l[k], "Source: ") == 1) { src = substr(l[k], 9); sub(/ .*/, "", src) }
      else if (index(l[k], "Version: ") == 1) ver = substr(l[k], 10)
      else if (index(l[k], "Filename: ") == 1) file = substr(l[k], 11)
    }
    if (src == "") src = pkg
  } '"$cond"' { print pkg, src, ver, file }' "$REL/Packages.published"
}
fetch() {  # fetch <package> <version>: its published deb, into /out/debs
  local file
  file=$(stanzas 'pkg == p && ver == v' -v p="$1" -v v="$2" | awk '{print $4}' | sed 's|^\./||')
  curl -fsSL "$APT/$file" -o "/out/debs/$file"
}
source_packages() {  # source_packages <source> <version>: every published package built from it
  stanzas 'src == s && ver == v' -v s="$1" -v v="$2" | awk '{print $1}'
}
# plan <step> <argument> <package> <inputs> <upstream> [separator, -]: the next version counts revisions
# per upstream
plan() {
  local had next sep=${6:--}
  # the newest match: the index lists a package's versions oldest first
  had=$(field "$3" Version "$4" | tail -1)
  if [ -n "$had" ]; then
    echo "$1 $2 $had published" >>"$REL/plan"
    fetch "$3" "$had"
    if [ "$1" = kernel ]; then
      for dep in $(field "$3" Depends "$4" | tail -1 | tr ',' '\n' | sed 's/^ *//; s/ .*//'); do
        fetch "$dep" "$had"
        # the headers, which nothing depends on, are as much the kernel's
        case $dep in linux-image-*) fetch "linux-headers-${dep#linux-image-}" "$had" ;; esac
      done
    fi
    # an extra is every package its source built
    [ "$1" != extra ] || for p in $(source_packages "$7" "$had"); do [ "$p" = "$3" ] || fetch "$p" "$had"; done
    return
  fi
  next=$(field "$3" Version | sed -n "s/^${5:+$5$sep}\([0-9]*\)$/\1/p" | sort -n | tail -1)
  echo "$1 $2 ${5:+$5$sep}$((${next:-0} + 1)) new" >>"$REL/plan"
}

for conf in kernel/*.conf; do
  ref=$(bash kernel/version.sh "$conf")
  plan kernel "$conf" "linux-image-tvb-$(basename "$conf" .conf)" \
    "$(bash release/inputs.sh kernel "$conf" "${ref% *}")" "${ref#* }"
done
for c in boards/*/board.conf; do
  b=$(basename "$(dirname "$c")")
  k=$(sed -n 's/^BOARD_KERNEL=//p' "$c")
  [ -n "$k" ] && [ -f "kernel/$k.conf" ] || continue
  # the newest epoch published: a name a retired board's transition held continues above it
  e=$(field "tvb-$b" Version | sed -n 's/^\([0-9]*\):.*/\1/p' | sort -n | tail -1)
  plan board "$b" "tvb-$b" "$(bash release/inputs.sh board "$b")" "$e" "${e:+:}"
done
# a renamed board's former name: a last tvb-<old> that pulls in tvb-<new> on upgrade, so an
# installed box migrates rather than being left on the old, now-unmaintained package
for c in boards/*/board.conf; do
  b=$(basename "$(dirname "$c")")
  # shellcheck source=/dev/null
  old=$(. "$c"; echo "${BOARD_RENAMED_FROM:-}")
  # epoch 1: every version of the transition sorts above every real one of the old board
  [ -n "$old" ] && [ ! -d "boards/$old" ] && plan retire "$b" "tvb-$old" "$(bash release/inputs.sh retire "$b")" 1 :
done
for c in firmware/*/firmware.conf; do
  d=$(basename "$(dirname "$c")")
  plan firmware "$d" "tvb-firmware-$(sed -n 's/^FIRMWARE_CHIP=//p' "$c")" "$(bash release/inputs.sh firmware "$d")"
done
for c in extras/*/extra.conf; do
  [ -f "$c" ] || continue
  e=$(basename "$(dirname "$c")")
  debian=$(bash extras/version.sh "$e")
  if bash extras/carried.sh "$e" "$debian"; then
    echo "extra $e retired: Debian's $debian carries its patches; delete extras/$e/" >>"$REL/plan"
    continue
  fi
  # shellcheck source=/dev/null
  plan extra "$e" "$(. "$c"; echo "$PACKAGE")" "$(bash release/inputs.sh extra "$e" "$debian")" \
    "$debian" +tvb "$(. "$c"; echo "$SOURCE")"
done
plan base - tvb-base "$(bash release/inputs.sh base)"
plan keyring - tvb-archive-keyring "$(bash release/inputs.sh keyring)"
cat "$REL/plan"
