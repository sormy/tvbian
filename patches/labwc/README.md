# labwc — a client's large buffer on a hardware plane

On the Mali-450 at 2256×1504, compositing a browser's page costs labwc 17 ms of a frame's GPU time,
and the page scrolls at 29 fps. The display hardware can show that buffer on an overlay plane and
scale it there; with `0001`, Falkon scrolls a plain page at 57 fps and a rich one at 42 fps on the
H96 Max M2 Plus. `extras/labwc` rebuilds Debian's `labwc` with it.

| Patch  | Does                                                              | Upstream |
| ------ | ----------------------------------------------------------------- | -------- |
| `0001` | the largest opaque dmabuf that nothing covers, on an output layer | not sent |

It needs wlroots' libliftoff interface, `WLR_DRM_FORCE_LIBLIFTOFF=1`, the only DRM interface that
takes output layers, and on the RK3528 a plane search with time to finish (`patches/wlroots`).
Without the variable labwc behaves as before. A buffer the hardware refuses is composited again from
the next frame.
