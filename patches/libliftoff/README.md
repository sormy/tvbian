# libliftoff — upstream's fixes since 0.5.0

libliftoff maps a compositor's layers to a CRTC's planes by trying allocations as atomic test
commits. Debian's 0.5.0 is its newest release; upstream's branch since adds faster allocation that
stops at the best possible score and tests fewer combinations, the composition layer no longer
counted as needing composition, and leak fixes. The RK3528's VOP2 needs more than libliftoff's 1 ms
budget for its tests (`patches/wlroots` `0003`), so fewer tests matter there. The public header and
exported symbols are those of 0.5.0, soname `libliftoff.so.0`: a drop-in for Debian's.
`extras/libliftoff` rebuilds Debian's `libliftoff` with them.

| Patches       | Are                                                         | Upstream                 |
| ------------- | ----------------------------------------------------------- | ------------------------ |
| `0001`–`0013` | every commit on upstream's branch since 0.5.0, in its order | merged, not yet released |

Dropped when Debian packages a release that has them.
