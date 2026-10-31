#!/bin/bash
# Hammer one suspected trigger per arm under a steady RX stream, counting the latch module's
# detections. Run detached. Usage: force.sh <iperf3 server> <minutes per arm> <log> <arm>...
# Arms: scan (back-to-back scans), reassoc (disconnect every 20 s), heat (stress-ng), idle.
set -u
PEER=$1 MIN=$2 OUT=$3
shift 3
log() { echo "$(date +%T) $*" >> "$OUT"; }
rx() { iw dev wlan0 link | awk '/rx bitrate/ {sub(/^\t/, ""); print}'; }
latches() { dmesg | grep -c "RX latched at DSSS/CCK"; }
bw() { iperf3 -c "$PEER" -t 10 ${1:-} 2>/dev/null | awk '/receiver/ {print $7}'; }
stimulus() {
	case $1 in
	scan) while :; do iw dev wlan0 scan > /dev/null 2>&1; done ;;
	reassoc) while :; do sleep 20; iw dev wlan0 disconnect; done ;;
	heat) exec stress-ng --cpu 4 --timeout 0 > /dev/null 2>&1 ;;
	idle) exec sleep infinity ;;
	esac
}
: > "$OUT"
for arm in "$@"; do
	before=$(latches)
	log "$arm: start, down $(bw -R) [$(rx)]"
	iperf3 -c "$PEER" -R -b 50M -t $((MIN * 60)) > /dev/null 2>&1 &
	stream=$!
	stimulus "$arm" &
	stim=$!
	end=$((SECONDS + MIN * 60))
	while [ $SECONDS -lt $end ]; do
		sleep 30
		log "$arm: [$(rx)] latches $(($(latches) - before))"
	done
	pkill -P $stim; kill $stim $stream 2> /dev/null
	wait 2> /dev/null
	sleep 15
	log "$arm: end, latches $(($(latches) - before)), down $(bw -R) up $(bw) [$(rx)]"
done
log done
