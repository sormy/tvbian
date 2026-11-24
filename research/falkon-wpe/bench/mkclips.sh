#!/bin/bash
# 10 s test clips with a silent audio track: VP9, H.264 and HEVC at 4K60, 4K30 and 1080p60
set -e
cd "$1"
enc() {
  local size=$1 rate=$2 codec=$3 out=$4 v a
  case $codec in
    vp9) v="-c:v libvpx-vp9 -b:v 20M -deadline realtime -cpu-used 8 -row-mt 1 -g 120"; a="-c:a libopus";;
    h264) v="-c:v libx264 -preset ultrafast -b:v 30M -pix_fmt yuv420p -g 120"; a="-c:a aac";;
    hevc) v="-c:v libx265 -preset ultrafast -b:v 30M -tag:v hvc1 -g 120 -x265-params log-level=error"; a="-c:a aac";;
  esac
  ffmpeg -v error -y -f lavfi -i "testsrc2=size=$size:rate=$rate" -f lavfi -i anullsrc=r=48000:cl=stereo \
    -t 10 $v $a -shortest -movflags +faststart "$out"
}
for spec in "3840x2160 60 4k60" "3840x2160 30 4k30" "1920x1080 60 1080p60"; do
  read -r size rate tag <<< "$spec"
  enc "$size" "$rate" vp9 "vp9-$tag.webm"
  enc "$size" "$rate" h264 "h264-$tag.mp4"
  enc "$size" "$rate" hevc "hevc-$tag.mp4"
done
