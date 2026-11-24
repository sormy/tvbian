# Chromium on GLES 2 (Mali-450, lima), video on Wayland overlays

Debian's Chromium draws in software on the Mali-450 and puts no video on a hardware plane.
`patch.py` rewrites a copy of the binary in six places:

1. **The GPU probe allows no ES 2.0 fallback**: `gpu/config/gpu_info_collector.cc`'s
   `InitializeGLContext` sets `attribs.allow_es_version_fallback = false`, the one place in Chromium
   that does. Its attributes are loaded from an 8-byte constant; the patch loads them from another
   constant identical but for the fallback's byte.
2. **ANGLE's per-stage sampler limit** (`UniformLinker::flattenUniformsAndCheckCapsForShader` in
   `src/libANGLE/ProgramLinkedResources.cpp`) rejects every Skia program with "VERTEX shader texture
   image units count exceeds MAX_VERTEX_TEXTURE_IMAGE_UNITS(0)", though the vertex shaders sample
   nothing. The patch removes that branch; Mesa still enforces the driver's own limit.
3. **`WaylandOverlayManager::CanHandleCandidate` refuses any candidate with a `clip_rect`**, and web
   content always carries its window's clip, so no video reaches a plane. A code cave refuses the
   candidate only when the clip does not hold its display rect, the clip grown by 0.01 px so that
   float rounding at a fractional scale does not count as clipping.
   `0001-viz-drop-an-overlay-candidate-s-clip-that-clips-nothing.patch` is the upstream form.
4. **No AV1 unless the hardware decodes it.** `RenderMediaClient` asks
   `IsDefaultDecoderSupportedVideoType` once the GPU's decoders have declined a type; its codec
   switch now answers false for AV1, so YouTube serves VP9, which the RK3528 decodes. A box whose VA
   driver offers AV1 still gets it.
5. **Overlays with fractional scaling**: `WaylandConnection::ShouldUseOverlayDelegation`, inlined in
   four places, refuses delegation when `wp_fractional_scale_manager_v1` is bound. Without
   fractional scaling Chromium renders at the next integer scale (2 on a 1.5 screen, 78% more
   pixels) and the plane scales it down. The patch drops that condition, so the page renders at the
   output's scale.
6. **Whole pixels**: `CanHandleCandidate`'s last check refuses a display rect off whole pixels, as
   most are at a fractional scale. It now accepts them; the subsurface lands on whole logical
   pixels, within 2/3 of a device pixel.

On the M2 Plus every Skia program compiles, Speedometer 3.1 scores 1.04 (1.02 in software), and 4K
HEVC plays on an NV12 plane at a 1.5 output scale.

## Locating the sites

`patch.py CHROMIUM PATCHED` finds each site from anchors that survive a rebuild, and writes nothing
unless every site is found exactly once:

| Patch | Anchor                                                                                                                 |
| ----- | ---------------------------------------------------------------------------------------------------------------------- |
| 1     | the trace event `gpu_info_collector::InitializeGLContext`; after its branch, the load of `0000000100010001`            |
| 2     | the function formatting `s count exceeds `; its call with `mov w1, #1`; the `b.hi` there                               |
| 3, 6  | `s0 = 0.01f` before a tail call, after an `ldrb`/`tbnz` on `x19` to `return false`                                     |
| 4     | the `base::Location` `IsDecoderSupportedVideoType` in `render_media_client.cc`; its callee comparing the codec with 10 |
| 5     | the `WaylandOverlayDelegation` feature, by its name's relocation; each `IsEnabled`, then a null check                  |

Struct offsets (the clip, the display rect) are read from the function's own loads. Patch 3's cave
goes in the longest run of zero words in `.text`, the alignment before V8's embedded blob, once no
branch is found to land in it. The `brk #0; hlt #0` runs that look like padding elsewhere are the
targets of failed `CHECK`s.

Validated offline against each build's debug symbols: 156.0.8078.79-1~deb13u1 and
156.0.8078.108-1~deb13u1 patch fully, each site in the function named above.
150.0.7871.100-1~deb12u1 locates patches 2–6 but refuses patch 1: there the attributes are built on
the stack, not loaded from a constant.

`xref.py BINARY STRING` lists the code taking a string's address and `callers.py BINARY ADDRESS` the
calls to a function, for finding the anchors of a build whose shapes differ.
