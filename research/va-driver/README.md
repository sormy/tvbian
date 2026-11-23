# VA driver — AFBC by the decoder's own layout

`tvb-va-driver` offers Cedrus's AFBC alone (16x16, sparse, split). `rkvdec` on `rk35xx-next2` writes
another: `AN68` and `AN6a`, 16x16 sparse, not split, which VOP2 scans out on Cluster0.
`afbc-detect.patch` asks the HEVC decoder at init which of the two its CAPTURE lists and offers that
modifier, so a client that lists it at surface creation decodes AFBC on either.

| Check                   | Result                         |
| ----------------------- | ------------------------------ |
| Build, host suite       | ✅ 133 pass, against `3cf706d` |
| Cedrus, `rkvdec` on box | ❓ no client asks VA for AFBC  |

## Why it waits

A client asks for AFBC by listing the modifier at `vaCreateSurfaces`. None here does:

- GStreamer's `va` offers downstream the modifier a surface created with no list exports
  (`sys/va/gstvacaps.c`), which is linear; a sink asking AFBC fails to negotiate.
- FFmpeg and mpv list no modifier; an application can, through `AVVAAPIFramesContext`'s attributes.

The client in view is Falkon's video, through GStreamer: its own sink hands the decoder's dma-buf to
a subsurface, which labwc puts on a VOP2 plane by `libliftoff`, Cluster0 on the RK3528.

| Step                                       | Needs                                         |
| ------------------------------------------ | --------------------------------------------- |
| the decoder writes AFBC                    | done: `rkvdec`, Cedrus                        |
| the driver offers the decoder's own layout | this patch                                    |
| GStreamer's `va` offers it downstream      | a probe with the AFBC modifier listed         |
| the sink takes `DMA_DRM` caps with it      | Falkon's video-plane sink                     |
| a reader on screen                         | VOP2's Cluster0 by labwc; Panfrost samples it |

## Applying it

On the host, in the repo: `git apply research/va-driver/afbc-detect.patch`, then
`./build.sh va-driver check`.
