#!/bin/sh
# In a latch: try each cure cheapest first, throughput at the peer after each; stop at the first cure.
# Run detached (reconnects drop ssh). Usage: latchdiag.sh <iperf3 server> <ko for the reload> <log>
PEER=$1 KO=$2 OUT=$3
log() { echo "$(date +%T) $*" >> "$OUT"; }
bw() { iperf3 -c "$PEER" -t 8 $1 2>/dev/null | awk '/receiver/ {printf "%.1f", $7}'; }
rx() { iw dev wlan0 link | awk '/rx bitrate/ {print $3, $5}'; }
cured() { d=$(bw -R); log "$1: down $d up $(bw) rx $(rx)"; [ "${d%.*}" -ge 25 ] 2>/dev/null; }
wait_link() { for _ in $(seq 1 30); do sleep 2; iw dev wlan0 link | grep -q "^Connected to" && break; done; sleep 5; }
: > "$OUT"
log "reg $(iw reg get | grep -m1 country); 2412 $(iw phy | grep -m1 '2412 MHz')"
log "sta $(iw dev wlan0 station dump | awk '/retries|failed|drop|connected/ {printf "%s %s; ", $(NF-1), $NF}')"
cured "latched" && exit
echo "stop_ba ifname=wlan0" > /sys/module/atbm6031/atbmfs/atbm_cmd; sleep 5
cured "stop_ba" && exit
iw dev wlan0 disconnect; wait_link
cured "reconnect" && exit
echo "halt ifname=wlan0" > /sys/module/atbm6031/atbmfs/atbm_cmd; sleep 15
iw dev wlan0 disconnect; wait_link
cured "halt+reconnect" && exit
rmmod atbm6031; insmod "$KO"; wait_link
cured "reload"
