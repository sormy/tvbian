# Video

What the box is sold for (4K60, HDR, 8K) names the pipeline that must work end to end, decoder to
screen in a player, before any one stage is judged.

## Do

1. **The vendor's matrix first** (`dump.md`): every codec, profile, depth and largest size, decode
   and encode, and HDR (HDR10, HLG, HDR10+, Dolby Vision) as a stream decoded and as a signal sent.
2. **The engine**, measured by `tools/validate/video.py` through FFmpeg, as Kodi uses it: every
   codec at every size of its ladder, compared with FFmpeg's software decode, the decoder's own
   downscale, every encoder decoded back. Its `matrix` is the board's table in `board.md`, and the
   chip's column in `docs/video-support.md`.
3. **The vendor's stack read before ours is written**: its display driver and its player's decoder
   setup, the format it sends, who scales, the clocks, the limits it checks. Ours mirrors it unless
   a measurement says better.
4. **The cases written down before the first test**, one `board.md` row each:

   | Axis   | Cases                                     |
   | ------ | ----------------------------------------- |
   | Depth  | 8-bit, 10-bit                             |
   | Layout | linear, AFBC                              |
   | Scale  | 1:1, shrink under 2×, over 2×, enlarge    |
   | Width  | within the display's line buffer, past it |
   | Codec  | one with AFBC output, one without         |
   | Kernel | each the board ships                      |

5. **Each case proven on the screen**: the whole picture by eye or the camera, the player's dropped
   and late frames, and the display engine's log clean during it (no `RCQ sync timed out`, no
   underrun), at the display's own mode.

## Bites

- **Capability by doing.** A plane's formats are proven by `drmModeAddFB2WithModifiers` and a
  TEST_ONLY atomic commit, never a tool's listing: `modetest`'s list misdecodes here.

- **At 4K60 memory is the limit**: the handover to the display must keep up, not only the decoder.
  On LPDDR3 or a 32-bit bus a 4K60 claim stands on AFBC.
- **A fault must leave the engine usable**: every clip past each limit is followed by a supported
  clip checked against the software decode. A size is tested on a freshly booted engine before it is
  called a limit.
- **Test as a normal user**: the nodes ship `0600`, and root hides a missing udev rule.
- **Ancient and regional codecs** (RealVideo, AVS) are worth little effort. ffmpeg patches that
  validate or fix a codec live in `patches/ffmpeg/`.

## Check

- [ ] **C1** `video.py` decode passes every codec the vendor's matrix lists, at its largest size
- [ ] **C2** Every encoder's output decodes back
- [ ] **C3** The decoder's downscale, where it has one
- [ ] **C4** A real 4K HEVC film plays smooth, the CPU near idle
- [ ] **C5** 4K60 on screen, zero copy, at the claimed frame rate
- [ ] **C6** On LPDDR3 or a 32-bit bus: AFBC, 8- and 10-bit, decoder to plane, seen
- [ ] **C7** Every case in the table above seen, the display engine's log clean
- [ ] **C8** Stopping and restarting a stream leaves no stale buffers or warnings
- [ ] **C9** A clip past each limit, then a supported one, decodes right
- [ ] **C10** The board's matrix is in `board.md`, its chip's column in `docs/video-support.md`
