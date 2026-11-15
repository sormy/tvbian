# Tanix TX1 V2.0: what is left

## Issues found

- [ ] Find the wake source if the box wakes from sleep on its own again.
- [ ] Root-cause `RCQ sync timed out` with a player on screen and at a mode set. Every logged
      occurrence came with an AFBC overload `0096` now refuses, or a mode-set run; 159 switches
      between 24 and 60 Hz did not reproduce it.
- [ ] Wi-Fi went silent after a group rekey: no traffic for 37 min, the link still up, nothing
      logged, the box running. Seen once; 27 forced rekeys at 20 s passed clean, so the cause is not
      the group-key install alone.
- [ ] A 4K stream resumed mid-file plays at once over Wi-Fi: once it waited for data four times in
      its first 33 s (1.5 to 6.3 s each, at 46–61 Mbit/s), then played smoothly.

- [ ] On 7.3, reloading the ATBM6031 driver in its other mode (`wifi_bt_comb`) resets the box, no
      pstore record; 6.18 reloads it. Skipped on 7.3 in `known.conf` until fixed.
- [ ] On 7.3, under the soak's load, `ccu_helper_wait_for_lock` warns: a PLL does not lock.
- [ ] Bluetooth in the driver's combo mode (`wifi_bt_comb=1`): no `hci0` on 6.18.

- [ ] The ATBM6031 driver logs its scans at info, not warning: `[atbm_log]` lines fill
      `dmesg -l warn`.

## Parked

- [ ] Check on stock whether PH9, or the remote's Menu, held at power-on reaches Android's recovery.
- [ ] Bring up the AV port: picture and sound, through the CTIA-to-OMTP adapter, as the H96 Max H313
      does on the same encoder.
