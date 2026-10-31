#!/bin/bash
# Seekwave's latch recipe on the ATBM6031: continuous CPU load and sparse traffic for 300 s, then
# throughput at the peer. Run detached; an ssh session's traffic suppresses a latch.
# Usage: repro.sh <iperf3 server> <arms> <log>
set -u
PEER=$1 ARMS=$2 OUT=$3
GW=$(ip -4 route show default | awk '{print $3; exit}')
# ~2.5 packets a second for N s; the box has no ping
sparse() { for _ in $(seq $(( $1 * 5 / 2 ))); do echo > "/dev/udp/$GW/9"; sleep 0.4; done; }
log() { echo "$(date +%T) $*" >> "$OUT"; }
link() { iw dev wlan0 link | awk '/tx bitrate|rx bitrate/ {sub(/^\t/, ""); printf "%s; ", $0}'; }
bw() { iperf3 -c "$PEER" -t "$1" ${2:-} 2>/dev/null | awk '/receiver/ {print $7}'; }
: > "$OUT"
for arm in $(seq 1 "$ARMS"); do
	log "arm $arm baseline up $(bw 5) [$(link)]"
	stress-ng --cpu 4 --timeout 300s >/dev/null 2>&1 &
	sparse 300
	wait
	l=$(link); up=$(bw 10); down=$(bw 10 -R)
	log "arm $arm after up $up down $down [$l]"
	case "$l" in
	*40MHz*) ;;
	*) log "arm $arm LATCHED: reload"; rmmod atbm6031; modprobe atbm6031; sleep 20 ;;
	esac
done
log done
