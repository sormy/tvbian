#!/bin/sh
# usage: yt4k.sh URL SECONDS: the demo on a 3840x2160 headless output; logs title and decoder irq rate.
# env DEMO_UA: the user agent pages see; DEMO_SCRIPT: a script run in each page; MODE: the output's size, default 3840x2160
export XDG_RUNTIME_DIR=/tmp/qtwpe-rt; mkdir -p $XDG_RUNTIME_DIR; chmod 700 $XDG_RUNTIME_DIR
export WLR_BACKENDS=headless WLR_RENDERER=gles2 WLR_HEADLESS_OUTPUTS=1 WLR_LIBINPUT_NO_DEVICES=1
export QT_QPA_PLATFORM=wayland LD_LIBRARY_PATH=/var/tmp/qtwpe GST_VA_ALL_DRIVERS=1
export WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1 PULSE_SERVER=unix:/run/user/1000/pulse/native
export GST_DEBUG="${GST_DEBUG:-vavp9dec:5,vp9decoder:4}" GST_DEBUG_FILE=/var/tmp/qtwpe/gst.log GST_DEBUG_NO_COLOR=1
export DEMO_UA DEMO_SCRIPT
cd /var/tmp/qtwpe
export MODE=${MODE:-3840x2160}
cage -s -- sh -c 'wlr-randr --output HEADLESS-1 --custom-mode $MODE && exec ./qtwpe-demo -qwindowgeometry $MODE+0+0 ${DEMO_UA:+"--user-agent=$DEMO_UA"} ${DEMO_SCRIPT:+"--user-script=$DEMO_SCRIPT"} "$0"' "$1" > run.log 2>&1 &
pid=$!
irqs() { grep -E "rkvdec|vdpu" /proc/interrupts | awk '{s+=$2+$3+$4+$5} END {print s+0}'; }
prev=$(irqs)
for i in $(seq $2); do sleep 1; now=$(irqs); echo "$i s: decoder irqs/s $((now-prev)) | $(grep "^title:" run.log | tail -1)"; prev=$now; done
WAYLAND_DISPLAY=wayland-0 grim -s 0.33 yt4k.png 2>>run.log
kill $pid; sleep 1; kill -9 $pid 2>/dev/null
grep "Negotiated caps" gst.log | grep -oE "width=\(int\)[0-9]+|height=\(int\)[0-9]+|framerate=\(fraction\)[0-9/]+" | paste -sd" " -
echo "lima errors: $(dmesg | grep -ciE "lima.*(error|timeout)")"
