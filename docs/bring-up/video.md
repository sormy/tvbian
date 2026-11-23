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
4. **Played in a player**, video with its audio, judged by eye and ear: the human's one step.

## Bites

- **Memory bandwidth can be the bottleneck**: decode, scaling and scanout share one bus. A rate that
  falls with resolution, or 8K that decodes but will not play, is checked against the board's Memory
  row before the codec is blamed.
- **Capability by doing.** A plane's formats are proven by `drmModeAddFB2WithModifiers` and a
  TEST_ONLY atomic commit, never a tool's listing: `modetest`'s list misdecodes here.

- **Real time is per codec, through the player's path**: on the H616, scaled 4K H.264 dropped a
  quarter of its pictures while HEVC kept up. An engine busy between pictures is memory-bound: check
  the reference layout before the clock.
- **At 4K60 memory is the limit**: the handover to the display must keep up, not only the decoder.
  On LPDDR3 or a 32-bit bus a 4K60 claim stands on AFBC.
- **A fault must leave the engine usable**: every clip past each limit is followed by a supported
  clip checked against the software decode. A job that hangs, a corrupt stream or one the engine
  times out on, resets the engine and its IOMMU, and the next clip decodes with no reboot. A size is
  tested on a freshly booted engine before it is called a limit.
- **A cap is the hardware's, measured**: a size or rate limit holds only where the engine fails past
  it; the limit passes and one step past fails, both run, and the patch names the test. A cap copied
  from another driver or a datasheet is a question.
- **Interlaced streams are their own codecs**: field-coded and MBAFF H.264, interlaced MPEG-2 and
  VC-1 take paths progressive clips never touch; an MBAFF regression here passed every progressive
  test. MPEG-2, MPEG-4 Part 2, H.263 and VC-1 are compared by PSNR: their IDCT is not bit-exact, and
  FFmpeg's own IDCTs disagree on one clip.
- **A picture read back on the CPU runs at memory speed**: a converter, a scaler or a thumbnailer
  maps decoded pictures, and an uncached buffer took 99 ms a 4K picture here against 24 ms cached.
- **Test as a normal user**: the nodes ship `0600`, and root hides a missing udev rule.
- **Ancient and regional codecs** (RealVideo, AVS) are worth little effort. ffmpeg patches that
  validate or fix a codec live in `patches/ffmpeg/`.

## Check

- [ ] **C1** `video.py` decode passes every codec the vendor's matrix lists, at its largest size
- [ ] **C2** Every encoder's output decodes back
- [ ] **C3** The decoder's downscale, where it has one
- [ ] **C4** 👤 A 4K film plays smooth in a player, its audio with it
- [ ] **C5** Where the decoder writes AFBC: 8- and 10-bit frames, decoder to plane
- [ ] **C6** The decoder's scaled picture, decoder to plane
- [ ] **C7** A clip past each limit, then a supported one, decodes right
- [ ] **C8** The board's matrix is in `board.md`, its chip's column in `docs/video-support.md`
- [ ] **C9** A job forced to time out, on each engine, is followed by a clip that decodes right, no
      reboot
- [ ] **C10** Each size or rate cap: the limit decodes, one step past is refused, both recorded
- [ ] **C11** Interlaced clips, field and MBAFF H.264 and interlaced MPEG-2 and VC-1, against the
      software decode, by PSNR where the IDCT is not bit-exact
- [ ] **C12** A decoded 4K picture read back on the CPU at memory speed, cached and uncached timed
