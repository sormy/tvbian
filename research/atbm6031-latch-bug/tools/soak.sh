#!/bin/bash
# Throughput over time: every 5 min, iperf3 10 s each way to the peer, the link, the SoC temperature
# and the station counters. Run detached. Usage: soak.sh <iperf3 server> <minutes> <log>
set -u
PEER=$1 MIN=$2 OUT=$3
log() { echo "$(date +%T) $*" >> "$OUT"; }
bw() { iperf3 -c "$PEER" -t 10 ${1:-} 2>/dev/null | awk '/receiver/ {printf "%.0f", $7}'; }
link() { iw dev wlan0 link | awk '/tx bitrate|rx bitrate/ {sub(/^\t/, ""); printf "%s; ", $0}'; }
sta() { iw dev wlan0 station dump | awk '/tx retries|tx failed|connected time/ {sub(/^\t/, ""); printf "%s; ", $0}'; }
: > "$OUT"
for i in $(seq 0 5 "$MIN"); do
	log "t+${i}m up $(bw) down $(bw -R) temp $(( $(cat /sys/class/thermal/thermal_zone0/temp) / 1000 ))C [$(link)] $(sta)"
	sleep 280
done
log done
