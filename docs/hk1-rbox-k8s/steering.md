# Steering

## 2026-11-26

- The serial pads' voltage was put to the owner as a hand check. The level and baud are the
  family's, 3.3 V and 1500000 on Rockchip, unless a separate chip drives the pads:
  `docs/bring-up/identity.md`'s serial step now says so, its meter only finding the pads.
- The factory restore over OTG was put to the owner as a hand check, though the bring-up had already
  entered the Loader and Maskrom over OTG and read the eMMC whole with the family's tool, whose
  restore the family proves once. `docs/bring-up/regression.md`'s hand row now says so.
- Analog sound was reported broken from a playback by card number, `hw:1,0`; between boots the codec
  and HDMI cards had swapped numbers. A sound card is named in a test, `CARD=<id>`, never numbered,
  as `mmcblk` numbers are never trusted.
