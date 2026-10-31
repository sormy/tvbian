#!/bin/sh
# Load a test atbm6031.ko in place of the packaged one, guarded: an oops reboots the box in 10 s, and
# without an association and a default route in 120 s the packaged module comes back.
# Run detached (Wi-Fi drops). Usage: tryko.sh <module.ko> [params...] ; log in /root/tryko.log
KO=$1; shift
exec > /root/tryko.log 2>&1
sysctl -w kernel.panic_on_oops=1 kernel.panic=10
sleep 1
rmmod atbm6031
insmod "$KO" "$@" || { echo "insmod failed"; modprobe atbm6031; exit 1; }
for i in $(seq 1 24); do
	sleep 5
	iw dev wlan0 link | grep -q "^Connected to" && ip -4 route show default | grep -q wlan0 &&
		{ echo "up after $((i * 5)) s"; exit 0; }
done
echo "no link in 120 s: back to the packaged module"
rmmod atbm6031; modprobe atbm6031
