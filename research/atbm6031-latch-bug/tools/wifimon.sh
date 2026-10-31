#!/bin/sh
# once a minute: link rates and width, signal, station counters, new driver warnings
while true; do
	l=$(iw dev wlan0 link | awk '/tx bitrate|rx bitrate|signal/ {sub(/^\t/, ""); printf "%s; ", $0}')
	s=$(iw dev wlan0 station dump | awk '/tx retries|tx failed|rx drop misc|connected time/ {sub(/^\t/, ""); printf "%s; ", $0}')
	w=$(dmesg | grep -c atbm_log)
	echo "$(date +%T) $l$s atbm_log=$w"
	sleep 60
done
