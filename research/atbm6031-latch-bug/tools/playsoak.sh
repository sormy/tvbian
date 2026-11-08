#!/bin/bash
# What latched it in the wild: a 4K HDR10 stream from the media server, decoded on the engine, for an
# hour; every 5 min the stream pauses for a 10 s probe each way.
# Usage: CLIP=<4K HDR10 clip> playsoak.sh <peer> <min> <log>
set -u
PEER=$1 MIN=$2 OUT=$3
log() { echo "$(date +%T) $*" >> "$OUT"; }
bw() { iperf3 -c "$PEER" -t 10 ${1:-} 2>/dev/null | awk '/receiver/ {printf "%.0f", $7}'; }
link() { iw dev wlan0 link | awk '/rx bitrate/ {sub(/^\t/, ""); printf "%s; ", $0}'; }
: > "$OUT"
while :; do /root/ffmpeg-scale -loglevel quiet -hwaccel v4l2request -hwaccel_output_format drm_prime \
	-i "${CLIP:?a 4K HEVC Main10 HDR10 clip on the box}" -f null -; done &
dec=$!
for i in $(seq 0 5 "$MIN"); do
	log "t+${i}m up $(bw) down $(bw -R) [$(link)] ampdu $(dmesg | grep -c 'AMPDU\[wlan0\]') tokfail $(dmesg | grep -c 'aggr token not enough')"
	iperf3 -c "$PEER" -R -b 50M -t 270 >/dev/null 2>&1
done
kill $dec; pkill -x ffmpeg-scale
log done
