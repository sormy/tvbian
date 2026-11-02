#!/bin/sh
# bootlog.sh <minutes>: temps, signal, rx/tx rate, a 5 s iperf3 -R, every ~28 s
mountpoint -q /sys/kernel/debug || mount -t debugfs none /sys/kernel/debug
end=$(( $(cut -d. -f1 /proc/uptime) + $1 * 60 ))
while [ $(cut -d. -f1 /proc/uptime) -lt $end ]; do
  t=$(cat /sys/class/thermal/thermal_zone*/temp | awk "{printf \"%d \", \$1/1000}")
  s=$(iw dev wlan0 station dump)
  rx=$(echo "$s" | sed -n "s/.*rx bitrate:\t*//p"); tx=$(echo "$s" | sed -n "s/.*tx bitrate:\t*//p"); sig=$(echo "$s" | awk "/signal avg/{print \$3}")
  d=$(iperf3 -c plex -R -t 5 2>&1 | awk "/receiver/{print \$7}")
  echo "$(cut -d. -f1 /proc/uptime) temps[$t] sig $sig rx[$rx] tx[$tx] down $d mode $(grep -o "mode: \"[0-9x]*\", [0-9]*" /sys/kernel/debug/dri/0/state | head -1 | cut -d\" -f2)"
  sleep 22
done
echo DONE
