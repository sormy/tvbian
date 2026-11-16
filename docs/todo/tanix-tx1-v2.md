# Tanix TX1 V2.0: what is left

## Issues found

- [ ] Root-cause `RCQ sync timed out` at 720p120 on 7.3: `display-full` logged it in two of the
      day's 7.3 runs, at 720p120 alone; 1080p60, 1080p24 and 6.18 stay clean.
- [ ] The ATBM6031 driver keeps its own regulatory domain: `iw reg set` DE, US or JP is not taken.

## Parked

- [ ] Check on stock whether PH9, or the remote's Menu, held at power-on reaches Android's recovery.
