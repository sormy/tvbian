# gst-plugins-bad — the va decoders on a driver that narrows 10-bit streams

GStreamer's va decoders pick their output format by the stream's chroma type alone: a 10-bit stream
takes a 10-bit format or fails with "Failed to negotiate with downstream". `0001` lets GStreamer
decode to NV12 where a driver lists no 10-bit format. `tvb-va-driver` lists P010 for every 10-bit
config, so it needs no `0001`. `extras/gst-plugins-bad` rebuilds Debian's `gst-plugins-bad1.0` with
it.

| Patch  | Fixes                                                         | Upstream |
| ------ | ------------------------------------------------------------- | -------- |
| `0001` | HEVC Main 10 and VP9 profile 2 through `vah265dec`/`vavp9dec` | not sent |

A driver that lists a 10-bit format still gets it: the 8-bit lookup runs only when the 10-bit one
finds nothing.
