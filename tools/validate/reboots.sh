#!/bin/bash
# Warm reboots of a running box, from the host: one line a boot, the boot proven new by its boot_id.
#   tools/validate/reboots.sh root@<box> [count]
# Each line: the kernel, the tree, the Wi-Fi network and when it associated, Bluetooth controllers,
# MMC errors, uptime at the check. A box not back in SETTLE seconds stops the run.
set -u
BOX=$1
COUNT=${2:-5}
SETTLE=400     # seconds a boot may take before the box counts as lost
SETTLED=30     # seconds after the box answers, before its line is read

read -ra OPTIONS <<< "${SSH_OPTIONS:-}"   # more ssh options, a jump host or a known_hosts file
ssh_box() { ssh -o BatchMode=yes -o ConnectTimeout=8 "${OPTIONS[@]}" "$BOX" "$@" 2>/dev/null; }
boot_id() { ssh_box cat /proc/sys/kernel/random/boot_id; }

for i in $(seq "$COUNT"); do
  old=$(boot_id)
  ssh_box sudo -n systemctl reboot
  new=$old
  for _ in $(seq $((SETTLE / 10))); do
    sleep 10
    new=$(boot_id)
    [ -n "$new" ] && [ "$new" != "$old" ] && break
  done
  if [ -z "$new" ] || [ "$new" = "$old" ]; then echo "boot $i: not back in $SETTLE s"; exit 1; fi
  sleep "$SETTLED"
  # shellcheck disable=SC2016  # expanded on the box
  echo "boot $i: $(ssh_box 'echo "$(uname -r) tree=$(md5sum /usr/lib/tvb/board.dtb | cut -c1-8)" \
    "$(iw dev wlan0 link | grep -o "SSID: .*")" \
    "assoc=$(dmesg | grep -m1 -oE "\[ *[0-9.]+\].*(wlan0: associated|connect to)" | grep -oE "[0-9.]+" | head -1)s" \
    "bt=$(ls /sys/class/bluetooth | wc -l)" \
    "mmc.errors=$(dmesg | grep -ciE "mmc[0-9].*(error|timeout|fail)")" \
    "up=$(cut -d. -f1 /proc/uptime)s"')"
done
