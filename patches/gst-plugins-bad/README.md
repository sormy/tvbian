# gst-plugins-bad — the va decoders on a driver that narrows 10-bit streams

GStreamer's va decoders pick their output format by the stream's chroma type alone: a 10-bit stream
takes a 10-bit format or fails with "Failed to negotiate with downstream". `tvb-va-driver` on
`rk35xx` lists only NV12 for a 10-bit config, as MPP's 10-bit output is NV15, which no display path
there takes; FFmpeg and mpv decode those streams to NV12. `0001` lets GStreamer do the same.
`extras/gst-plugins-bad` rebuilds Debian's `gst-plugins-bad1.0` with it.

| Patch  | Fixes                                                         | Upstream |
| ------ | ------------------------------------------------------------- | -------- |
| `0001` | HEVC Main 10 and VP9 profile 2 through `vah265dec`/`vavp9dec` | not sent |

A driver that lists a 10-bit format still gets it: the 8-bit lookup runs only when the 10-bit one
finds nothing.
