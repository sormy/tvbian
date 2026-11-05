# mesa — upstream fixes on Mesa 25.0.7

Debian trixie ships `25.0.7-2+deb13u1`. Each patch applies to it with `git am`, and each is an
upstream commit backported, so the shadow ends when Debian ships the release that carries it.

| Patch  | Fixes                                   | Upstream                 |
| ------ | --------------------------------------- | ------------------------ |
| `0001` | tiler hierarchy on GPUs with < 8 levels | in 25.2.0, `548f652d101` |
| `0002` | exported buffers mappable for write     | in 25.3.0, `4531b8ace44` |

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
