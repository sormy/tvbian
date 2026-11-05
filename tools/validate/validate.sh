#!/bin/bash
# One regression pass on a running box, every line "name value"; run on each kernel and join:
#   scp tools/validate/validate.sh root@<box>:
#   ssh root@<box> 'IPERF=<host> CLIPS=<dir> FFMPEG=<path> SLEEP=120 setsid -f bash validate.sh > <kernel>.txt'
#   join -a1 -a2 <(sort 6.18.txt) <(sort 7.2.txt) | column -t
# IPERF: an iperf3 server on the wire; CLIPS: clips to decode, each also decoded in software;
# FFMPEG: an ffmpeg with v4l2-request; SLEEP: seconds of s2idle, past the watchdog's window.
set -u
out() { printf '%s %s\n' "$1" "${2:-none}"; }
first() { head -1 | tr -s ' \t' ' ' | sed 's/^ //; s/ $//'; }

hot() { sort -n /sys/class/thermal/thermal_zone*/temp | tail -1 | awk '{print $1 / 1000}'; }
busy() { awk '/^cpu / {print $2 + $3 + $4 + $6 + $7 + $8, $5}' /proc/stat; }
# a box still busy from boot or another session's player skews every number below
for i in $(seq 60); do
  a=$(busy); sleep 2; b=$(busy)
  echo "$a $b" | awk '{x = $3 - $1; y = $4 - $2; exit !(100 * x / (x + y) < 8)}' && break
done
out kernel "$(uname -r)"
out settled.after.s $((i * 2))
out temp.idle.c "$(hot)"
out boot.seconds "$(systemd-analyze 2>/dev/null | grep -oE '= [0-9.]+s' | tr -d '= s')"
out boot.slowest "$(systemd-analyze blame 2>/dev/null | first)"
out units.failed "$(systemctl --failed --no-legend | wc -l)"
out dmesg.warnings "$(dmesg -l err,warn | wc -l), most from $(dmesg -l err,warn | sed -E 's/^\[ *[0-9.]+\] //' |
  grep -oE '^[^ :]+' | sort | uniq -c | sort -rn | awk 'NR == 1 {print $2}')"
out iommu.faults "$(dmesg | grep -c 'Page fault')"
out ram.mib "$(free -m | awk '/^Mem/ {print $2}')"
out watchdog.seconds "$(wdctl 2>/dev/null | awk '/^Timeout:/ {print $2}')"
out cpu.khz "$(tr ' ' ',' < /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies | sed 's/,$//')"
out rtc "$(cat /sys/class/rtc/rtc0/name 2>/dev/null | first)"
out modules.missing "$(for m in $(dpkg -L $(dpkg-query -W -f '${Package}\n' 'tvb-*-modules-*' 2>/dev/null) 2>/dev/null |
  grep '\.ko$' | xargs -rn1 basename | sed 's/\.ko$//'); do lsmod | grep -q "^$m " || echo "$m"; done | xargs)"
out input.unnamed "$(for e in /dev/input/event*; do
  find /dev/input -maxdepth 1 -type l -lname "${e##*/}" | grep -q . || cat "/sys/class/input/${e##*/}/device/name"; done | xargs)"

for n in /sys/class/net/*; do
  [ -e "$n/device" ] && out "addr.${n##*/}" "$(cat "$n/address") type $(cat "$n/addr_assign_type")"
done
for h in /sys/class/bluetooth/hci*; do
  [ -e "$h" ] && out "addr.${h##*/}" "$(hciconfig "${h##*/}" 2>/dev/null | grep -oE 'BD Address: [0-9A-F:]+' | cut -d' ' -f3)"
done
country() { iw reg get 2>/dev/null | grep -m1 -oE 'country [A-Z0-9]+' | cut -d' ' -f2; }
out wifi.country "$(country)"
iw reg set DE 2>/dev/null; sleep 2
out wifi.country.set.de "$(country)"
iw reg set 00 2>/dev/null
if [ -n "${IPERF:-}" ]; then
  # the access point narrows its channel at will: the median of three, with the rate the link ran at
  for dir in up down; do
    flag=; [ $dir = down ] && flag=-R
    m=$(for r in 1 2 3; do iperf3 -c "$IPERF" -t 8 $flag 2>/dev/null | awk '/receiver/ {print $7}'; done | sort -n | sed -n 2p)
    out "wifi.$dir.mbits" "$m, tx $(iw dev wlan0 link | awk '/tx bitrate/ {print $3, $5, $6}')"
  done
fi

out cec.address "$(cec-ctl -d /dev/cec0 2>/dev/null | awk -F: '/Physical Address/ {gsub(/ /, "", $2); print $2}')"
for c in /sys/class/drm/card*-*; do out "connector.${c#*card*-}" "$(cat "$c/status")"; done
out planes.formats "$(drm_info 2>/dev/null | grep -oE '(NV12|P010|YUV420_8BIT|YUV420_10BIT|XR30) ' | sort -u | xargs)"
out video.devices "$(cat /sys/class/video4linux/video*/name 2>/dev/null | sort | xargs)"

if [ -n "${CLIPS:-}" ] && [ -n "${FFMPEG:-}" ]; then
  for clip in "$CLIPS"/*; do
    name=${clip##*/}
    start=$(date +%s.%N)
    "$FFMPEG" -v error -hwaccel v4l2request -hwaccel_output_format drm_prime -i "$clip" -f null - 2>/dev/null
    end=$(date +%s.%N)
    "$FFMPEG" -v error -y -hwaccel v4l2request -i "$clip" -pix_fmt yuv420p10le -f framemd5 /tmp/hw.md5 2>/dev/null
    "$FFMPEG" -v error -y -i "$clip" -pix_fmt yuv420p10le -f framemd5 /tmp/sw.md5 2>/dev/null
    frames=$(grep -vc '^#' /tmp/hw.md5)
    differ=$(diff <(grep -v '^#' /tmp/hw.md5 | cut -d, -f6) <(grep -v '^#' /tmp/sw.md5 | cut -d, -f6) | grep -c '^<')
    out "decode.$name" "$frames frames, $differ differ, $(awk -v f="$frames" -v a="$start" -v b="$end" 'BEGIN {printf "%.0f", f / (b - a)}') fps"
  done
fi

for c in /proc/asound/card[0-9]*; do
  n=${c##*card}
  for r in 44100 48000; do
    a=$(date +%s.%N)
    aplay -q -D "plughw:$n,0" -r $r -f S16_LE -c 2 -d 3 /dev/zero 2>/dev/null
    out "audio.$(cat "$c/id").$r.3s" "$(awk -v a="$a" -v b="$(date +%s.%N)" 'BEGIN {printf "%.2f", b - a}')"
  done
  # a route left DISABLED plays at full rate into silence
  out "audio.$(cat "$c/id").disabled" "$(amixer -c "$n" contents | awk -F"'" '
    /^numid=/ {name = $2} /; Item #/ {split($1, a, "#"); item[a[2] + 0] = $2}
    /: values=/ {split($0, v, "="); if (item[v[2] + 0] == "DISABLED") print name; delete item}' | xargs)"
done
out gpu.offscreen "$(glmark2-es2-drm --off-screen -b build -b texture -b shading 2>/dev/null | awk '/glmark2 Score/ {print $3}')"
out emmc.write.mbs "$(fio --name=w --filename=/var/tmp/validate.fio --size=256M --rw=write --bs=1M --direct=1 \
  --output-format=terse 2>/dev/null | awk -F';' '{printf "%.1f", $48 / 1024}')"
out emmc.4k.fsync.iops "$(fio --name=f --filename=/var/tmp/validate.fio --size=64M --rw=randwrite --bs=4k --fsync=1 \
  --runtime=15 --time_based --output-format=terse 2>/dev/null | awk -F';' '{print $49}')"
rm -f /var/tmp/validate.fio

stress-ng --cpu "$(nproc)" --timeout 60s -q &
sleep 55
out temp.load.c "$(hot)"
out cpu.load.khz "$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq)"
wait

if [ "${SLEEP:-0}" -gt 0 ]; then
  boot=$(cat /proc/sys/kernel/random/boot_id)
  rtcwake -m freeze -s "$SLEEP" >/dev/null 2>&1
  out suspend.same_boot "$([ "$boot" = "$(cat /proc/sys/kernel/random/boot_id)" ] && echo yes || echo no)"
fi
