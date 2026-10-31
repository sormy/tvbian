#!/bin/bash
# A kernel column's software checks, detached: N6, N7, X4, C5, C9, S14. Log: /root/check.log
# Needs /root/cpurx.sh, /root/ffmpeg-scale and the clip. Usage: check72.sh <iperf3 server> <clip>
PEER=$1 CLIP=$2 FRAMES=1491
exec > /root/check.log 2>&1
log() { echo "$(date +%T) $*"; }
warns() { dmesg -l emerg,alert,crit,err,warn | wc -l; }
up() { iperf3 -c "$PEER" -t 10 2>/dev/null | awk '/receiver/ {print $7}'; }
decode() { /root/ffmpeg-scale -loglevel error -hwaccel v4l2request -hwaccel_output_format drm_prime -i "$CLIP" -f null -; }
since() { python3 -c "import sys; print(round(float(sys.argv[2]) - float(sys.argv[1]), 1))" "$1" "$(date +%s.%N)"; }

log "N6 idle: $(/root/cpurx.sh); up $(up)"
stress-ng --cpu 4 --iomix 2 --timeout 40s > /dev/null 2>&1 &
sleep 5
log "N7 under stress-ng: $(/root/cpurx.sh); up $(up)"
wait
for i in 1 2 3 4 5; do
	s=$(date +%s.%N)
	rmmod atbm6031 && modprobe atbm6031
	until iw dev wlan0 link 2> /dev/null | grep -q "^Connected" && ip -4 route show default | grep -q wlan0; do sleep 0.2; done
	log "X4 reload $i: back in $(since "$s") s"
done
w0=$(warns)
s=$(date +%s.%N)
decode
t=$(since "$s")
log "C5 4K: $(python3 -c "print(round($FRAMES / $t, 2))") fps in $t s, warnings +$(($(warns) - w0))"
w0=$(warns)
for i in $(seq 11); do timeout 3 /root/ffmpeg-scale -loglevel error -hwaccel v4l2request \
	-hwaccel_output_format drm_prime -i "$CLIP" -f null -; done
log "C9 eleven stops: warnings +$(($(warns) - w0))"
log "S14 start"
stress-ng --vm 1 --vm-bytes 90% --verify --timeout 300s --metrics-brief 2>&1 | tail -3
log "S14 done, warnings $(warns)"
log done
