#!/bin/bash
# usage: browser-bench.sh BROWSER CLIP [SECONDS]: plays CLIP in BROWSER (firefox|chromium|wpe|falkon) in a
# headless cage; prints the page's result, the decoder's interrupts a second and the CPU's busy share
browser=$1 clip=$2
run=$browser-$$
export XDG_RUNTIME_DIR=/tmp/bench-rt WLR_BACKENDS=headless WLR_RENDERER=gles2 WLR_HEADLESS_OUTPUTS=1
export WLR_LIBINPUT_NO_DEVICES=1
# the GStreamer environment a login gets from the VA driver's package
. /etc/profile.d/tvb-va-driver.sh
mkdir -p $XDG_RUNTIME_DIR && chmod 700 $XDG_RUNTIME_DIR
# a session bus of its own: root's, inherited through su, refuses this user; no X, no a11y bridge
unset DBUS_SESSION_BUS_ADDRESS DISPLAY
export NO_AT_BRIDGE=1
# kept between runs: a browser starts a fresh profile slowly
profile=/tmp/bench-profile-$browser; mkdir -p "$profile"
url="http://127.0.0.1:8088/bench.html?tag=$run&src=$clip"
case $browser in
  firefox)
    cat > "$profile/user.js" <<'PREFS'
user_pref("media.ffmpeg.vaapi.enabled", true);
user_pref("media.hardware-video-decoding.force-enabled", true);
user_pref("media.autoplay.default", 0);
user_pref("media.autoplay.blocking_policy", 0);
user_pref("gfx.webrender.all", true);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("toolkit.telemetry.reportingpolicy.firstRun", false);
user_pref("browser.aboutwelcome.enabled", false);
PREFS
    export MOZ_ENABLE_WAYLAND=1 MOZ_DISABLE_RDD_SANDBOX=1
    cmd=(firefox-esr --kiosk --no-remote --profile "$profile" "$url");;
  chromium)
    cmd=(chromium --ozone-platform=wayland --kiosk --no-first-run --user-data-dir="$profile"
      --autoplay-policy=no-user-gesture-required --ignore-gpu-blocklist --use-gl=angle --use-angle=gles
      --disable-features=UseChromeOSDirectVideoDecoder,Vulkan,VulkanFromANGLE,DefaultANGLEVulkan
      --enable-features=VaapiVideoDecoder,VaapiVideoDecodeLinuxGL,AcceleratedVideoDecodeLinuxGL,AcceleratedVideoDecodeLinuxZeroCopyGL
      "$url");;
  wpe)
    export QT_QPA_PLATFORM=wayland LD_LIBRARY_PATH=/var/tmp/qtwpe
    cmd=(/var/tmp/qtwpe/qtwpe-demo "$url");;
  falkon)
    export QT_QPA_PLATFORM=wayland R=/var/tmp/falkon-wpe/root/usr/local
    export LD_LIBRARY_PATH=$R/lib:$R/lib/aarch64-linux-gnu FALKON_PLUGIN_PATH=$R/lib/aarch64-linux-gnu/plugins/falkon
    export XDG_DATA_DIRS=$R/share:/usr/share XDG_CONFIG_HOME=$profile/config XDG_DATA_HOME=$profile/data XDG_CACHE_HOME=$profile/cache
    cmd=($R/bin/falkon --no-remote "$url");;
esac
irqs() { awk '/cedrus/ {s=0; for (i=2; i<=5; i++) s+=$i; print s}' /proc/interrupts; }
busy() { awk '/^cpu / {print $2+$3+$4+$7+$8, $2+$3+$4+$5+$6+$7+$8}' /proc/stat; }
log=/tmp/bench-$browser.log
setsid dbus-run-session -- cage -s -- "${cmd[@]}" > "$log" 2>&1 &
pid=$!
served() { grep -c "$1" /var/tmp/qtwpe/http.log; }
result() {
  grep -oE "report\?[^ ]+" /var/tmp/qtwpe/http.log | python3 -c "import sys,urllib.parse; [print(urllib.parse.unquote(l.strip())[7:]) for l in sys.stdin]" | grep -F "$run $clip " | tail -1
}
# timed from the page's load, which takes a browser 5 to 30 s: it measures from 5 s after for 10 s
for i in $(seq 90); do [ "$(served "tag=$run")" -gt 0 ] && break; sleep 1; done
loaded=$i
sleep 7
i0=$(irqs); read b0 t0 <<< "$(busy)"
sleep 6
WAYLAND_DISPLAY=wayland-0 grim -s 0.5 /tmp/bench-$browser.png 2>/dev/null
i1=$(irqs); read b1 t1 <<< "$(busy)"
for i in $(seq 60); do [ -n "$(result | grep -E "result|error|rejected")" ] && break; sleep 1; done
# the browser's whole session, not only the bus that started it
kill -- -$pid 2>/dev/null; sleep 2; kill -9 -- -$pid 2>/dev/null
line=$(result)
echo "$browser $clip | ${line#"$run $clip "} | page after ${loaded}s, cedrus $(( (i1 - i0) / 6 ))/s cpu $(( 100 * (b1 - b0) / (t1 - t0) ))%"
