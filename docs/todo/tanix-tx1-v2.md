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

## Parked

- [ ] Check on stock whether PH9, or the remote's Menu, held at power-on reaches Android's recovery.
- [ ] Bring up the AV port: picture and sound. The last try drove the DAC, the converter's audio
      hissing, with no picture: through a 3.5 mm cable grounded on ring 2, where TV-box jacks ground
      on the sleeve. Next: the jack's ground by meter, a CTIA-to-OMTP adapter, then the vendor's
      composite enable (TVE `0x004` bit 16) into the driver.
