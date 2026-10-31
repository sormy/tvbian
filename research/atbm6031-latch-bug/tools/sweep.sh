#!/bin/bash
# One stressor mix at a time, 120 s each with sparse traffic, then the link and throughput at the peer:
# a latch is a link still slow or at 20 MHz after the stress stops. Mixes from Seekwave's starve-sweep.sh.
# Run detached; an ssh session's traffic suppresses a latch. Usage: sweep.sh <iperf3 server> <log>
set -u
PEER=$1 OUT=$2 T=120
GW=$(ip -4 route show default | awk '{print $3; exit}')
# ~2.5 packets a second for N s; the box has no ping
sparse() { for _ in $(seq $(( $1 * 5 / 2 ))); do echo > "/dev/udp/$GW/9"; sleep 0.4; done; }
log() { echo "$(date +%T) $*" >> "$OUT"; }
link() { iw dev wlan0 link | awk '/tx bitrate|rx bitrate/ {sub(/^\t/, ""); printf "%s; ", $0}'; }
bw() { iperf3 -c "$PEER" -t 5 ${1:-} 2>/dev/null | awk '/receiver/ {printf "%.0f", $7}'; }
# a latch: record its state, try the firmware-only reset, else a module reload; log which cured it
latched() {
	log "LATCHED after $1: $(iw reg get | grep -m1 country); 2412 $(iw phy | grep -m1 '2412 MHz')"
	dmesg | grep -E 'chatype\(|20M channel|40M channel' | tail -3 >> "$OUT"
	echo "halt ifname=wlan0" > /sys/module/atbm6031/atbmfs/atbm_cmd
	sleep 15
	iw dev wlan0 disconnect; sleep 15
	down=$(bw -R)
	log "after halt: down $down [$(link)]"
	if [ "${down:-0}" -ge 40 ]; then
		log "halt cured it: firmware state"
	else
		rmmod atbm6031; modprobe atbm6031; sleep 20; log "after reload: down $(bw -R) [$(link)]"
	fi
}
# what was playing when it latched in the wild: a 4K HDR10 stream from Jellyfin, decoded on the engine
player() {
	while :; do /root/ffmpeg-scale -loglevel quiet -hwaccel v4l2request -hwaccel_output_format drm_prime \
		-i /root/clips/aquaman-60s-video.mkv -f null -; done &
	iperf3 -c "$PEER" -R -b 50M -t $T >/dev/null 2>&1
	kill %1; pkill -x ffmpeg-scale
}
mixes=(
	"player"
	"--cpu 4"
	"--cpu 16"
	"--cpu 16 --vm 4 --vm-bytes 128M"
	"--iomix 4"
	"--hdd 2 --hdd-bytes 64M"
	"--sock 8"
	"--cpu 8 --iomix 2"
	"--switch 8"
	"--cpu 16 --vm 4 --vm-bytes 128M --iomix 4"
)
: > "$OUT"
log "baseline up $(bw) down $(bw -R) [$(link)]"
for m in "${mixes[@]}"; do
	if [ "$m" = player ]; then
		player
	else
		stress-ng $m --temp-path /tmp --timeout ${T}s >/dev/null 2>&1 &
		sparse $T
		wait
	fi
	sleep 5
	l=$(link); up=$(bw); down=$(bw -R)
	log "$m: up $up down $down [$l]"
	if [ "${down:-0}" -lt 20 ]; then
		latched "$m"
	elif [[ "$l" != *40MHz* ]]; then
		log "20 MHz, no reload: $(dmesg | grep -E 'chatype\(|20M channel|40M channel' | tail -1)"
	fi
done
log done
