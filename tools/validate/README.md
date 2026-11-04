# validate — a running box against the bring-up criteria

One script a component, each run from the host or on the box as its header says.

| Script        | Checks                                                                            |
| ------------- | --------------------------------------------------------------------------------- |
| `validate.sh` | boot, watchdog, Wi-Fi, decode, audio: one regression pass                         |
| `video.py`    | the hardware video matrix: decode, scale, encode                                  |
| `display.py`  | the display: planes, composition, pacing, colour stages, HDMI HDR out, unattended |

## video.py

Every codec the box's video engine offers, at every size of a fixed ladder, decoded in hardware and
compared with FFmpeg's software decoder; the decoder's own downscaling; each hardware encoder,
decoded back. The same run is the hardware video tables, a board's measured matrix, and the
regression check after a kernel or FFmpeg change.

### Run

All from the host, in the repo checkout. The clips, 3 frames each, come from the host's FFmpeg,
which has the software encoders the boxes' builds lack; `build/validate/video/clips/manifest.json`
records its version, each clip's hash and its software decode's per-frame checksums: the reference a
hardware decode must match, checked again with the box's own software decoder before a mismatch
counts.

```sh
python3 tools/validate/video.py clips
python3 tools/validate/video.py run --box root@<box> --engine sunxi --ffmpeg /root/ffmpeg
python3 tools/validate/video.py report build/validate/video/<box>-<kernel>.json
python3 tools/validate/video.py matrix build/validate/video/<box>-<kernel>.json
python3 tools/validate/video.py compare <before>.json <after>.json
```

`--engine` is `sunxi` (Cedrus through `v4l2request`), `rkmpp` (Rockchip's MPP) or `meson`
(`meson_vdec` through `v4l2m2m`); `--ffmpeg` an FFmpeg built with `patches/ffmpeg/`. `--only` takes
a regex over `<codec>-<size>`, `--suite` any of `decode,scale,encode`. `--skip` takes a regex over
`<suite>:<codec>-<size>` for the cases known to hang a box its watchdog does not reset: recorded as
skipped, never run, so the pass finishes.

`report` gives the largest passing size per codec, its frame rate, the largest that runs at 24 fps,
and what failed past it; `matrix` the whole grid, the table a board's `board.md` publishes with its
kernel and date; `compare` lists every case that got worse and exits 1 if any did.

### What passes

- **Planes:** every plane listed; a YUV video plane and an interface plane that can sit above it.
- **Compose:** the interface, opaque over the top half and transparent below, over a scaled video
  plane, by writeback.
- **LUT:** malformed blobs refused; tables applied while active and held over 60 flips; HDR10 to
  SDR, HLG to SDR, SDR to PQ and HLG to PQ on 64 YUV patches, within two 8-bit codes of the same
  table on the host. It checks that the hardware applies a table, not how good the table is.
- **SDR to HDR:** a short `HDR_EXT_DATA` refused; seven colours to PQ and HLG within two codes of
  BT.2408 (gamma 2.2, BT.709 to BT.2020, white at 203 nits).
- **Scope:** which planes each stage maps: the interface left alone, or the whole output, recorded.
- **Pacing:** 60 s of player-paced nonblocking commits, an idle plane in each: none refused.
- **HDMI:** SDR, PQ and HLG at each `max bpc` the connector allows: the DRM InfoFrame with HDR only,
  its EOTF as asked, BT.2020 colorimetry where the connector has `Colorspace`. On a synthetic screen
  the output is cycled after each change, since Rockchip sets InfoFrames only as it comes up.
- **HDR10+:** malformed payloads refused; payloads switched in place, none giving the slot back to
  HDMI's VSIF; kept across a mode set.
- **Underruns:** the count holds still over a static picture for 3 s.
- **Rating:** each mode the driver keeps, from 8K60 to 720p60 at 24 to 120 Hz, 10 s at a player's
  pace with the video at the mode's size: sustained with every flip on time, no underrun and no new
  kernel warning. Underruns count from sun4i's counter or Rockchip's `POST_BUF_EMPTY`; elsewhere
  they are marked unmeasured. The verdicts: `RATING display: largest 4K60, fastest 1080p120`.
- **Sinks:** each synthetic screen gets HDR for every EOTF it lists; what the box sends for the rest
  is recorded (Rockchip nothing, mainline everything), as are the mappings left to the GPU.
