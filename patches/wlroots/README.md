# wlroots — time for libliftoff to find a plane

libliftoff tries plane allocations by atomic test commits and gives up after 1 ms. The RK3528's VOP2
on its vendor kernel needs more for one test than that, so the search ends before the overlay plane
and every output layer is composited. `0003` takes the budget from `WLR_DRM_LIBLIFTOFF_TIMEOUT_MS`;
16 lets labwc's planes (`patches/labwc`) through, with no misses. A search runs only when the layers
change, so the budget costs little. `extras/wlroots` rebuilds Debian's `wlroots` with it.

| Patch  | Does                                                                        | Upstream                       |
| ------ | --------------------------------------------------------------------------- | ------------------------------ |
| `0001` | custom modes handled when a connector connects                              | 0.18.3, backported             |
| `0002` | an output enabled with a custom mode set                                    | 0.18.3, backported             |
| `0003` | libliftoff's allocation timeout from the environment                        | not sent                       |
| `0004` | output layers can stack under the composited output                         | not sent                       |
| `0005` | a client buffer the renderer cannot sample is kept, for a plane to scan out | not sent                       |
| `0006` | NV12 in AFBC taken as YUV420_8BIT, one plane                                | experiment                     |
| `0007` | a synchronized subsurface's damage scaled by its viewport                   | master, `fba00c4a`, backported |

`0005` lets a video decoded to AFBC, which the Mali-450 cannot sample, reach the plane that reads
it: without it wlroots drops the buffer at commit, and the surface keeps its previous one. `0006`
lets Chromium's AFBC video, which it can only call NV12, reach mainline VOP2's Cluster0, which reads
AFBC 4:2:0 only as `YUV420_8BIT`; an experiment while AFBC is tried end to end.

`0007` is Kenny Levinsen's, authorship and message kept. A synchronized subsurface's commit is
cached with only what it changed, so its damage was converted without the viewport set earlier: a
page Chromium hands over as a viewport-scaled subsurface, as it does with overlay delegation, was
repainted only over buffer size ÷ scale (⅔ at 1.5), the rest left stale and flickering.

Debian packages no 0.18.3 (sid went to 0.19 and 0.20, another ABI, which labwc 0.8 does not build
against), so its DRM fixes are backported onto Debian's 0.18.2.
