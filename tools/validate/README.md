# validate — a running box against the bring-up criteria

One script a component, each run from the host or on the box as its header says.

| Script        | Checks                                                    |
| ------------- | --------------------------------------------------------- |
| `validate.sh` | boot, watchdog, Wi-Fi, decode, audio: one regression pass |
| `video.py`    | the hardware video matrix: decode, scale, encode          |
| `display.py`  | the display's colour: the video plane's LUT, HDMI HDR out |

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

Each size once, smallest first; a codec stops after two failing sizes in a row, and its largest pass
and first failure run again: a case that differs between them is flaky. A case gets 60 s.

- **Decode:** as many frames as software, and every frame identical, or for MPEG-1/2/4, H.263 and
  JPEG within 50 dB luma: their IDCT is the decoder's to round. A stream the decoder turns away, for
  FFmpeg to play in software, is refused, not broken. Where frames cannot be read back (the RK3518's
  10-bit NV15), frames decoded only, marked so.
- **Scale:** a 3840×2160 clip asked for at most 1080 lines: the size given, within 30 dB of software
  scaled to it; full size is a decoder that does not shrink that codec.
- **Encode:** `testsrc2` at each size, every frame back at that size, 30 dB against the source.
  Timed against the CPU's fastest encoder for the codec, sizes up to the first the hardware wins: 🟠
  where the CPU is faster.
- **Frame rate:** each pass timed again over 3 frames and over 12, or 60 where 12 end within a
  second, the difference divided out so setup cancels; decoded frames stay in the engine's buffers,
  encoded ones come from memory. The decoder's rate alone, on a synthetic clip, with nothing shown:
  a ceiling, not playback. A pass under 24 fps cannot play a film: 🟠 in the grid.

## display.py

The display path's colour on a box with nothing else on the screen: a video plane's 3D LUT
(`SUNXI_CDC_LUT3D`) applied as written, the HDMI output's InfoFrames and pixel format for SDR, PQ
and HLG, and the TCON's underrun count. A case the box lacks the means for is skipped.

### Run

On the box, as root, the player stopped:

```sh
python3 display.py   # box
```

### What passes

- **LUT:** malformed blobs refused; identity, a channel mix and an inversion, switched while active,
  on RGB; the table held over 60 flips; HDR10 to SDR, HLG to SDR, SDR to PQ and HLG to PQ on 64 YUV
  patches. Every capture, by writeback, within two 8-bit codes of the same table interpolated
  trilinearly. The tables are the script's own colour science: what is checked is that the hardware
  applies a table, not how good the table is.
- **HDMI:** SDR, PQ and HLG at `max bpc` 8 and 10: the DRM InfoFrame sent with HDR alone, its EOTF
  as asked, BT.2020 colorimetry with HDR, RGB for SDR and for HDR at 8 bits.
- **Underruns:** the count holds still over a static picture for 3 s.
