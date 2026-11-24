# mesa — upstream fixes on Mesa 25.0.7

Debian trixie ships `25.0.7-2+deb13u1`. Each patch applies to it with `git am`; each but `0003` and
`0004` is an upstream commit backported, so the shadow ends when Debian ships the release that
carries it.

| Patch  | Fixes                                                 | Upstream                 |
| ------ | ----------------------------------------------------- | ------------------------ |
| `0001` | tiler hierarchy on GPUs with < 8 levels               | in 25.2.0, `548f652d101` |
| `0002` | exported buffers mappable for write                   | in 25.3.0, `4531b8ace44` |
| `0003` | YUV dma-bufs importable through GBM                   | ours, to propose         |
| `0004` | AFBC dma-bufs importable on Lima, for a display plane | ours, experiment         |

`0001` is Eric R. Smith's, authorship and message kept, moved to `pan_util.h`, where 25.0 keeps the
function. With too few levels to cover the framebuffer, 25.0 keeps only the coarsest: on a two-level
Mali-G31 at 2256×1504, 1024- and 2048-pixel bins, so every tile walks nearly every primitive and
long frames end at Panfrost's 500 ms job limit, the previous frame left on screen. The commit
spreads the levels: 32 and 2048 pixels on two. `glmark2-es2-drm`, full suite on screen, H313: 42
→ 121.

`0002` is Emma Anholt's, its renderonly, Lima and Panfrost hunks: 25.0 exports a scanout buffer's
dumb object with `O_CLOEXEC` alone, so the dma-buf is read-only and every later export of that GEM
object, `DRM_RDWR` or not, returns the same file. A CPU writing a GBM buffer through its fd got
`EACCES`.

`0003` is ours. GBM's format query answers only for its RGB visuals table, so it reports NV12
unsupported even where the driver imports NV12 dma-bufs, as EGL does. Chromium on Wayland asks it
before importing a VA-API frame for a hardware overlay, so no decoded frame becomes an overlay: the
import is refused, the swap fails and the GPU process restarts. A format without a visual is now
answered from the driver's dma-buf list unless the use includes rendering or the cursor.

`0004` is ours, an experiment while AFBC video is tried end to end. Chromium wraps each VA-API frame
in a GBM buffer before handing it to Wayland, and Lima refuses an AFBC modifier, so a decoder's AFBC
picture never reaches the plane that reads it. Lima now imports Arm AFBC, external only and untiled;
the Mali-450 cannot decode it, so a composited frame shows compressed bytes, not the picture.
