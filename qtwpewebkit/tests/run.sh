#!/bin/bash
# Runs every test function once against QtWebEngine and once against qtwpewebkit, each in its own process,
# prints both results side by side and fails when qtwpewebkit fails where QtWebEngine passes, unless known-gaps.txt expects it.
#
# usage: run.sh [BUILD_DIR] [TEST...]     e.g. run.sh /d/qtwpewebkit-tests-build navigation widget
# env:   QTWPEWEBKIT_TEST_TIMEOUT (seconds per function, default 300), QTWPEWEBKIT_TEST_OUT (result directory)
set -u

here=$(cd "$(dirname "$0")" && pwd)
timeout_s=${QTWPEWEBKIT_TEST_TIMEOUT:-300}

# Inside the compositor (or directly for QtWebEngine): run the functions of each test binary of one backend
if [ "${1:-}" = --backend ]; then
    backend=$2 bin_dir=$3 out=$4
    shift 4
    for name in "$@"; do
        binary=$bin_dir/tst_${name}_$backend
        [ -x "$binary" ] || continue
        for function in $("$binary" -functions 2>/dev/null | sed -n 's/()$//p'); do
            log=$out/$name.$function.$backend
            timeout -k 5 "$timeout_s" "$binary" "$function" -o "$log.txt,txt" >"$log.stderr" 2>&1
            echo $? >"$log.status"
        done
    done
    exit 0
fi

build=$(cd "${1:-.}" && pwd)
shift $(($# > 0 ? 1 : 0))
bin_dir=$build
[ -d "$build/tests" ] && bin_dir=$build/tests
names=("$@")
if [ ${#names[@]} -eq 0 ]; then
    for binary in "$bin_dir"/tst_*_qtwpewebkit; do
        name=${binary##*/tst_}
        names+=("${name%_qtwpewebkit}")
    done
fi
out=${QTWPEWEBKIT_TEST_OUT:-$(mktemp -d /tmp/qtwpewebkit-tests.XXXXXX)}
mkdir -p "$out"
export LANG=C.UTF-8

echo "QtWebEngine: offscreen QPA"
# QtWebEngine spellchecks with its own format of the Hunspell dictionaries WebKit reads
convert=/usr/lib/qt6/libexec/qwebengine_convert_dict
export QTWEBENGINE_DICTIONARIES_PATH="$out/qtwebengine_dictionaries"
mkdir -p "$QTWEBENGINE_DICTIONARIES_PATH"
for dic in /usr/share/hunspell/*.dic; do
    [ -x "$convert" ] && [ -f "$dic" ] || continue
    name=$(basename "$dic" .dic)
    "$convert" "$dic" "$QTWEBENGINE_DICTIONARIES_PATH/${name/_/-}.bdic" >/dev/null 2>&1
done
QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu ${QTWEBENGINE_CHROMIUM_FLAGS:-}" \
    "$0" --backend qtwebengine "$bin_dir" "$out" "${names[@]}"

# qtwpewebkit needs a Wayland compositor with EGL: a headless cage, rendering with the GPU when there is one
if [ -z "${XDG_RUNTIME_DIR:-}" ] || [ ! -w "$XDG_RUNTIME_DIR" ]; then
    export XDG_RUNTIME_DIR=$(mktemp -d /tmp/qtwpewebkit-runtime.XXXXXX)
fi
renderer=pixman
ls /dev/dri/renderD* >/dev/null 2>&1 && renderer=gles2
sandbox=on
# WebKit's sandbox also forbids user namespaces inside it
if ! bwrap --unshare-all --unshare-user --disable-userns --bind / / true 2>/dev/null; then
    sandbox="off (bubblewrap cannot create namespaces here)"
    export WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1
fi
echo "qtwpewebkit: headless cage, $renderer renderer, WebKit sandbox $sandbox"
WLR_BACKENDS=headless WLR_RENDERER=$renderer WLR_LIBINPUT_NO_DEVICES=1 \
    cage -- env QT_QPA_PLATFORM=wayland "$0" --backend qtwpewebkit "$bin_dir" "$out" "${names[@]}" >"$out/cage.log" 2>&1

# PASS, FAIL, SKIP, CRASH or TIMEOUT, plus the failing data rows
result()
{
    local log=$1
    [ -f "$log.status" ] || { echo "-"; return; }
    if ! grep -q '^Totals:' "$log.txt" 2>/dev/null; then
        [ "$(cat "$log.status")" = 124 ] && echo TIMEOUT || echo CRASH
    elif grep -q -E '^(FAIL!|XPASS)' "$log.txt"; then
        echo "FAIL $(sed -n -E 's/^(FAIL!|XPASS) *: [^(]*\(([^)]*)\).*/\2/p' "$log.txt" | sort -u | paste -sd, -)"
    elif grep -q '^SKIP' "$log.txt" && ! grep '^PASS' "$log.txt" | grep -q -v -E '::(init|cleanup)TestCase\('; then
        echo SKIP
    else
        echo PASS
    fi
}

known_gap()
{
    grep -E "^$1[[:space:]]" "$here/known-gaps.txt" 2>/dev/null | head -1 | sed -E 's/^[^[:space:]]+[[:space:]]+//'
}

unexpected=0 passed=0 total=0 known=0 fixed=0
printf '%-58s %-12s %-12s %s\n' "test" "QtWebEngine" "qtwpewebkit" "note"
for name in "${names[@]}"; do
    for status in "$out/$name".*.qtwpewebkit.status; do
        [ -f "$status" ] || continue
        function=${status#"$out/$name."}
        function=${function%.qtwpewebkit.status}
        [[ $function == initTestCase || $function == cleanupTestCase ]] && continue
        id="tst_$name::$function"
        reference=$(result "$out/$name.$function.qtwebengine")
        actual=$(result "$out/$name.$function.qtwpewebkit")
        gap=$(known_gap "$id")
        note=""
        total=$((total + 1))
        if [ "${actual%% *}" = PASS ] || [ "$actual" = SKIP ]; then
            passed=$((passed + 1))
            if [[ $gap == container:* ]]; then
                note="passes here, as it does with a GPU"
            elif [ -n "$gap" ]; then
                note="passes now: drop it from known-gaps.txt"
                fixed=$((fixed + 1))
            fi
        elif [ -n "$gap" ]; then
            note="known: $gap"
            known=$((known + 1))
        elif [ "${reference%% *}" = PASS ] || [ "$reference" = - ]; then
            note="UNEXPECTED ${actual#* }"
            unexpected=$((unexpected + 1))
        else
            note="fails on QtWebEngine too: test to fix"
        fi
        printf '%-58s %-12s %-12s %s\n' "$id" "${reference%% *}" "${actual%% *}" "$note"
    done
done
echo
echo "qtwpewebkit: $passed/$total pass, $known known gaps, $unexpected unexpected failures, $fixed known gaps fixed"
echo "logs: $out"
[ "$unexpected" -eq 0 ]
