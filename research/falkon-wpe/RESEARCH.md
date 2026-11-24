# Falkon on WPE WebKit: a GLES2 browser with VA-API video

Research only, 2026-11-16. Goal: a good browser on every TVBian board, Mali-450 (GLES 2.0) included,
playing video through GStreamer and our VA-API driver, by giving KDE Falkon an optional WPE WebKit
backend behind a reusable QtWebEngine-like library. QtWebEngine stays Falkon's default.

Inspected: Falkon master `bf75426ad15f671be3b30b03c2195ba1264d719c` (2026-11-16); WPE WebKit 2.54.2
release tarball (sha256 `f3284e19…f56`, Skia milestone 154 bundled); Debian's WPE 2.48.3 (trixie)
for comparison. Live probes on h96max-m2-plus (RK3528, lima) and h96max-h313 (H616, panfrost), both
Debian 13, Mesa 25.0.7, GStreamer 1.26.2. Paths: Falkon's are from its repo root; WebKit's are under
`Source/WebKit/` unless they start with `Source/`. "Inference" marks what was not read in source or
measured.

## Verdict

**Conditional go, for a proof of concept; no-go for porting Falkon yet.**

- WPE 2.54 has no GLES 3 requirement; on lima it should run GPU raster, GL compositing and zero-copy
  linear-NV12 video. Ganesh (Skia's GPU backend) ran on lima under WPE 2.48.3. 2.54 on lima is
  untested.
- Embedding WPE in Qt Widgets needs no WebKit patches: WPEPlatform's display, toplevel and view
  classes are public and derivable, and frames arrive as dma-bufs a `QOpenGLWidget` imports without
  copying.
- Falkon has no engine boundary: 120 of its 635 source files name QtWebEngine types, and its plugin
  API exposes them. A runtime-switchable backend is out of reach; a build-time backend
  (`falkon-wpe`) over a QtWebEngine-compatible library is feasible, with features dropped where WPE
  has no equivalent (printing, request interception in the UI process, download pause).

Three blockers come first, all outside Falkon:

| Blocker                                       | Why                                                                                                                                                                                     | Way out                                                                                                                                                                      |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No prebuilt WPE 2.54 for trixie               | trixie has 2.48.3; sid's 2.54.2 needs glibc 2.43, ICU 78, GStreamer ≥ 1.27.50; no Ubuntu, Flathub or upstream binaries                                                                  | Rebuild Debian's **unmodified** 2.54 source against trixie, as Debian does for WebKitGTK 2.54.0 in trixie-security. This breaks "no rebuilding"; needs the owner's decision. |
| WebKit's bubblewrap sandbox hides the decoder | On rk35xx MPP needs `/dev/mpp_service`, `/dev/rga`, `/dev/dma_heap` and the device-tree `compatible`; measured: VA decoders vanish, playback falls back to `openh264dec` and a CPU copy | A WebKit patch adding them to its `--dev-bind-try` list: `add_path_to_sandbox()` binds `nodev`, measured: `open` is `EACCES`                                                 |
| `gstreamer1.0-gl` not installed               | WebKit's zero-copy sink (`webkitglvideosink`) needs GStreamer's `opengl` plugin; without it every frame is mapped and uploaded                                                          | Depend on the package                                                                                                                                                        |

## 1. Falkon's dependency on QtWebEngine

Full inventory: [`falkon-inventory.md`](falkon-inventory.md). The shape that decides the design:

- **Build**: `Qt6WebEngineCore` and `Qt6WebEngineWidgets` are hard requirements
  (`CMakeLists.txt:63-64`); `FalkonPrivate` links them with no PUBLIC/PRIVATE keyword
  (`src/lib/CMakeLists.txt:606-616`), so every plugin inherits them. Speed-dial thumbnails need
  QtWebEngineQuick at run time through QML (`src/lib/data/data/thumbnailer.qml:2`).
- **Spread**: 743 lines name `QWebEngine*`/`QWebChannel` (plus 128 includes) across 120 files,
  29,133 of 89,513 LOC. `src/lib/webengine/` (3,838 LOC) wraps the engine but abstracts nothing.
- **Plugin API exposes the engine**: `WebView : QWebEngineView` and `WebPage : QWebEnginePage` are
  exported; `PluginInterface` takes `QWebEnginePage::NavigationType` and
  `QWebEngineNewWindowRequest&` (`src/lib/plugins/plugininterface.h:65-66`); PyFalkon binds PySide's
  WebEngine typesystems (`src/plugins/PyFalkon/typesystem_pyfalkon.xml:3-4`).
- **Hard spots**: synchronous JavaScript and printing built on nested event loops
  (`src/lib/webengine/webpage.cpp:145-175`); a `QWebChannel` in an isolated world bootstrapping
  `window.external` for the `falkon:` pages, autofill and GreaseMonkey
  (`src/lib/tools/scripts.cpp:26-71`, `src/lib/webengine/webpage.cpp:88-90`); sessions serialize
  `QWebEngineHistory` as an opaque Chromium blob (`src/lib/webtab/webtab.cpp:373,590`); `WebView`
  filters input on QtWebEngine's internal render widget (`src/lib/webengine/webview.cpp:1280-1370`);
  AdBlock, Do Not Track and per-site user agents run in `QWebEngineUrlRequestInterceptor`
  (`src/lib/network/networkurlinterceptor.cpp:32-57`,
  `src/lib/adblock/adblockurlinterceptor.cpp:32-62`).
- **History**: QupZilla moved from QtWebKit to QtWebEngine in place in 2015 (`60b2386a`, 107 files);
  Falkon never had two backends side by side.

## 2. WPE WebKit 2.54: what a host gets

- **WPEPlatform is the API to target.** In 2.54 it is on by default and declared stable; libwpe and
  WPEBackend-fdo are deprecated (`WPEPlatform/docs/overview.md:158-163`;
  <https://wpewebkit.org/blog/2026-09-16-wpewebkit-2.54.html>). Arch already builds without libwpe.
  Cog, libwpe-only, gets no stable releases past 0.18.
- **A host implements three GObject subclasses**: `WPEDisplay`, `WPEToplevel`, `WPEView`
  (`WPEPlatform/wpe/WPEDisplay.h:60-81`, `WPEToplevel.h:46-61`, `WPEView.h:41,51-81`), optionally an
  input-method context, clipboard and screen. `WebKitWebView` is a plain GObject created with its
  `display` (`UIProcess/API/glib/WebKitWebView.h.in:95-100,456-492`).
- **Frames**: the view's `render_buffer` vfunc receives a `WPEBuffer` (dma-buf: per-plane fd,
  offset, stride, modifier; or SHM in non-composited mode). The host imports it with
  `wpe_buffer_import_to_egl_image()` (one EGLImage cached per buffer,
  `WPEPlatform/wpe/WPEBufferDMABuf.cpp:115-135`), samples it, then calls
  `wpe_view_buffer_rendered()` (frame throttle) and `wpe_view_buffer_released()`
  (`UIProcess/wpe/AcceleratedBackingStore.cpp:194-317`). Unless the display opts into explicit sync,
  WebKit waits on the render fence itself.
- **Input** is built as `WPEEvent`s and fed with `wpe_view_event()`
  (`WPEPlatform/wpe/WPEEvent.h:213-219`). Focus, resize, scale and visibility have direct calls; a
  hidden view (`wpe_view_set_visible(FALSE)`) is throttled by WebKit (`WPEView.cpp:745-830`).
- **Processes**: per app a NetworkProcess and a mostly idle GPUProcess; WebProcesses roughly one per
  tab. Media stays in the WebProcess with GStreamer. The UI side runs on the default GLib main
  context, which Qt on Linux already drives (`QPAEventDispatcherGlib` unless `QT_NO_GLIB`).
- **WebKit's own Qt 6 binding** (`UIProcess/API/wpe/qt6/`, QML `org.wpewebkit.qtwpe`) is a
  WPEPlatform implementation rendering zero-copy into Qt Quick (`WPEViewQtQuick.cpp:188-250`). Not
  shipped: built only in developer mode (`Source/cmake/OptionsWPE.cmake:110`), Debian builds with
  `-DENABLE_WPE_QT_API=OFF`. It covers about 1% of the API, has no IME, scaling, visibility or
  popups, and passes `QKeyEvent::key()` as the hardware keycode (`WPEViewQtQuick.cpp:398-399`). Its
  ~600 lines of BSD-2 platform glue are the template to rewrite against the public API; a GTK host,
  [wpe-platform-gtk](https://github.com/Igalia/wpe-platform-gtk) (MIT), shows damage regions and
  graphics offload. QtWebView has no WPE backend.
- **Licence**: WebKit's UI API is LGPL-2+, WPEPlatform headers BSD-2. QtWPEEngine as
  LGPL-2.1-or-later keeps it usable by Falkon (GPL-3.0+) and absorbs the binding's LGPL files.

### Embedding into Qt Widgets on Wayland

| Option                                    | Verdict                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **(a) Own WPEPlatform + `QOpenGLWidget`** | **Recommended.** dma-buf → EGLImage → texture: no copy on import, one GPU draw into the widget's framebuffer, then Qt composites the window (one more blit, inference). Input, IME, focus, scale, visibility, cursors, clipboard and fullscreen are all host-side. One display per app, one toplevel per `QWindow`, one view per tab.                                                                                   |
| (b) Wayland subsurface                    | Lowest GPU cost (the compositor can scan out), but WPEPlatform-wayland opens its own `wl_display`, makes only `xdg_toplevel`s and cannot be parented (`WPEPlatform/wpe/wayland/WPEDisplayWayland.cpp:712-731`). Feasible only as our own `WPEView` attaching buffers to a `wl_subsurface` on Qt's connection, through Qt's native interfaces. Keep the renderer behind an interface so this can follow (a) on Mali-450. |
| (c) `QQuickWidget` + WebKit's `WPEQtView` | Not shipped; highest cost (Qt Quick renders offscreen, then composites).                                                                                                                                                                                                                                                                                                                                                |

The host must draw what WebKit leaves to it on WPE: context menus
(`UIProcess/wpe/WebContextMenuProxyWPE.cpp` is `notImplemented()`), `<select>` popups
(`show-option-menu`), dialogs, the file chooser. Tooltips have no hook
(`UIProcess/API/wpe/PageClientImpl.cpp:165-167`); drag and drop stays inside the view
(`UIProcess/API/wpe/WPEWebView.cpp:173-197`).

## 3. GLES 2.0 on Mali-450

| Question                 | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GLES 3 required?         | No. WebKit asks for an ES2 context (`Source/WebCore/platform/graphics/egl/GLContext.cpp:89,487`); its version checks gate only optional features (debug output, GL sync, packed depth-stencil). Skia's Ganesh accepts ES 2.0 and drops features per version (`GrGLCaps.cpp:238-245,444,650-663`).                                                                                                                                                                                                                                        |
| What 2.54 changed        | The compositor is now Skia (`UseSkiaForComposition` defaults on, `Source/WTF/Scripts/Preferences/UnifiedWebPreferences.yaml:9343-9353`), and raster defaults to GPU on WPE (2.48 defaulted to CPU). `WEBKIT_SKIA_ENABLE_CPU_RENDERING=1` paints tiles on the CPU, but compositing stays Ganesh: there is no pure-CPU path in compositing mode.                                                                                                                                                                                           |
| No fallback              | If Ganesh fails to initialise, `skiaGrContext()` is null and the web process crashes (`ThreadedCompositor.cpp:116-131`, `PlatformDisplaySkia.cpp:354,409-413`). `WEBKIT_USE_SKIA_FOR_COMPOSITION=0` returns to TextureMapper, which is GLES2-clean (`TextureMapperShaderProgram.cpp:170-196`), but Igalia is removing TextureMapper after 2.54.                                                                                                                                                                                          |
| lima, measured           | `Mali450`, OpenGL ES 2.0 (an ES3 context fails); max texture 4096; `MAX_SAMPLES` 4; EGL surfaceless, dma-buf import with modifiers, fence and wait sync; `OES_EGL_image_external`, `OES_vertex_array_object`, `EXT_texture_rg`, BGRA8888, NPOT. NV12 imports externally only; R8/GR88 per-plane import works for LINEAR and `ARM_16X16_BLOCK_U_INTERLEAVED`. No AFBC or Allwinner-tiled import.                                                                                                                                          |
| panfrost, measured       | Mali-G31, OpenGL ES 3.1; max texture 16384; the same dma-buf and sync support; LINEAR, ARM 16x16 and MTK modifiers.                                                                                                                                                                                                                                                                                                                                                                                                                      |
| Ganesh on lima, measured | Under WPE 2.48.3 with GPU raster forced, lima compiled Skia's GLSL 100 shaders and the web process ran its GPU workers without crashing. Frame rate and visual correctness were not measured (the session was locked).                                                                                                                                                                                                                                                                                                                   |
| lima risks               | lima computes fragments in FP16 and ignores `highp` (<https://docs.mesa3d.org/drivers/lima.html>) while reporting fp32, and Skia's Mali-4xx detection looks for `Mali-%d` (`GrGLUtil.cpp:395-399`), not `Mali450`, so Skia's low-precision workarounds stay off (inference: artefacts on large rounded rects and gradients). Skia enables 4× MSAA on ARM (`PlatformDisplaySkia.cpp:67-80`): try `WEBKIT_SKIA_MSAA_SAMPLE_COUNT=0`. Fill rate on Mali-450 MP2 is small; CPU raster on four A53s may compete for static pages (inference). |
| WebKitGTK as a proxy     | Not usable: WebKitGTK 2.54 on lima logs that GTK failed to initialise GL and drops acceleration. WPE has no GTK dependency.                                                                                                                                                                                                                                                                                                                                                                                                              |

Tuning knobs, all read by 2.54.2: `WEBKIT_SKIA_ENABLE_CPU_RENDERING`,
`WEBKIT_SKIA_CPU_PAINTING_THREADS`, `WEBKIT_SKIA_GPU_PAINTING_THREADS`,
`WEBKIT_SKIA_MSAA_SAMPLE_COUNT`, `WEBKIT_USE_SKIA_FOR_COMPOSITION`, `WEBKIT_DISABLE_DMABUF_ATLAS`,
`WEBKIT_WEB_RENDER_DEVICE_FILE`, `WEBKIT_SHOW_FPS`. WebKitGTK's `WEBKIT_DISABLE_COMPOSITING_MODE`
and `WEBKIT_DISABLE_DMABUF_RENDERER` do not exist on WPE.

## 4. Video: GStreamer and VA-API

- Regular playback uses `playbin`; MSE, blob and MediaStream use `playbin3`
  (`Source/WebCore/platform/graphics/gstreamer/MediaPlayerPrivateGStreamer.cpp:3557-3561`). The
  stateless `va` plugin is the intended path; the old `gstreamer-vaapi` is hidden unless
  `WEBKIT_GST_ENABLE_LEGACY_VAAPI=1` (`GStreamerCommon.cpp:627-633`). Decoders are picked by
  GStreamer rank; YouTube picks AV1 unless the software AV1 decoders are ranked NONE, and
  `GST_VA_ALL_DRIVERS=1` must be set (the VA-API session's findings).
- The zero-copy sink `webkitglvideosink` offers `video/x-raw(memory:DMABuf), format=DMA_DRM` with
  the drm-formats EGL can import (`GStreamerCommon.cpp:2174-2225`, `GLDisplay.cpp:296-313`). NV12
  becomes R8 + GR88 `GL_TEXTURE_2D` EGLImages, and Skia converts YUV to RGB
  (`CoordinatedPlatformLayerBufferDMABuf.cpp:69-258`): no `samplerExternalOES`, so lima qualifies.
- On the M2 Plus `vah264dec` negotiated linear NV12 as dma-buf, which lima imports: zero-copy is
  expected (inference; no GL sink was installed to prove it). Every engine must offer linear (or ARM
  16x16) NV12: AFBC and Allwinner-tiled frames import on neither GPU.
- Measured under WPE 2.48.3 in the sandbox: MPP failed to read the device tree, VA decoders were
  missing, playback fell back to `openh264dec` and a CPU copy. Cedrus and meson presumably need only
  `/dev/video*` and `/dev/media*` (not checked).

## 5. QtWebEngine → WPE compatibility matrix

| QtWebEngine                                 | WPE 2.54                                                                                                            | Gap                                                                                                                                      |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| `QWebEngineView`                            | our widget + `WPEViewQt` + `WebKitWebView`                                                                          | all widget glue is ours                                                                                                                  |
| `QWebEnginePage` load, title, url, progress | `WebKitWebView` (`load-changed`, `estimated-load-progress`, `title`, `uri`)                                         | one object, no page/view split                                                                                                           |
| `acceptNavigationRequest`                   | `decide-policy` (navigation)                                                                                        | answerable asynchronously (more flexible)                                                                                                |
| `newWindowRequested` / `createWindow`       | `decide-policy` (new window) + `create` returning a related view                                                    | destination inferred from window properties and modifiers                                                                                |
| `runJavaScript(src, worldId, cb)`           | `webkit_web_view_evaluate_javascript(src, world_name, …)` → `JSCValue`                                              | int world IDs map to names; convert results via JSON                                                                                     |
| `QWebEngineProfile`                         | `WebKitNetworkSession` + `WebKitWebContext` + shared `WebKitSettings` and `WebKitUserContentManager`                | split over four objects                                                                                                                  |
| `QWebEngineSettings`                        | `WebKitSettings` (66 setters)                                                                                       | Chromium-only attributes (`ForceDarkMode`, `ReadingFromCanvasEnabled`…) absent                                                           |
| `QWebEngineScript` / `ScriptCollection`     | `WebKitUserScript` in `WebKitUserContentManager`                                                                    | only document start and end; `Deferred` emulated; lookup by name is ours                                                                 |
| `QWebEngineUrlRequestInterceptor`           | none in the UI process; content-blocker JSON (`WebKitUserContentFilterStore`); web-process extension `send-request` | **architectural**: AdBlock needs an ABP → content-blocker converter or a C extension; header edits (DNT, per-site UA) need the extension |
| `QWebEngineUrlSchemeHandler` / `UrlScheme`  | `webkit_web_context_register_uri_scheme` + `WebKitSecurityManager` flags                                            | asynchronous finish; fine                                                                                                                |
| `QWebChannel`                               | script message handlers (with reply) + `evaluate_javascript`                                                        | a `QWebChannelAbstractTransport` over them plus an injected `qwebchannel.js` keeps Falkon's `external` objects                           |
| `QWebEngineDownloadRequest`                 | `download-started` → `WebKitDownload`                                                                               | **no pause/resume, no save-page (MHTML)**                                                                                                |
| `QWebEngineCookieStore`                     | `WebKitCookieManager` (async)                                                                                       | `changed` carries no details (diff to emit added/removed); no per-request filter                                                         |
| `QWebEngineHistory`                         | `WebKitBackForwardList` + session-state (de)serialisation                                                           | read-only; sessions in a new format                                                                                                      |
| `QWebEngineContextMenuRequest`              | `context-menu` + `WebKitHitTestResult` + `WebKitContextMenu`                                                        | menu drawn by us; selected text via JS                                                                                                   |
| `QWebEngineFullScreenRequest`               | `enter-fullscreen` / `leave-fullscreen` + toplevel state                                                            | fine                                                                                                                                     |
| `QWebEngineCertificateError`                | `load-failed-with-tls-errors` → `allow_tls_certificate_for_host` + reload                                           | only after the main load fails; no defer-and-continue                                                                                    |
| client certificates                         | `authenticate` (client-certificate request) → `webkit_credential_new_for_certificate`                               | fine                                                                                                                                     |
| `QWebEngineNotification`                    | `show-notification` + `WebKitNotification`                                                                          | no icon accessor                                                                                                                         |
| permissions (`Feature`)                     | `permission-request` (typed) + `query-permission-state`                                                             | screen capture and mouse lock map partially                                                                                              |
| `findText` / `QWebEngineFindTextResult`     | `WebKitFindController`                                                                                              | no active-match index                                                                                                                    |
| printing, `printToPdf`                      | **none on WPE** (GTK-only API; `window.print()` does nothing)                                                       | **hard gap**; only a full-page snapshot to PDF as an image                                                                               |
| PDF viewer                                  | PDF.js, on by default (`Source/cmake/OptionsWPE.cmake:53`)                                                          | check the package keeps it                                                                                                               |
| spell checking                              | Enchant; `set_spell_checking_enabled` / `_languages`                                                                | fine                                                                                                                                     |
| DevTools, `setInspectedPage`                | `webkit_web_view_toggle_inspector()` (opens a toplevel through our display) or the remote inspector                 | cannot dock into an arbitrary view                                                                                                       |
| favicons, `icon()`                          | `webkit_web_view_get_page_icons` → `WebKitImage`                                                                    | fine                                                                                                                                     |
| audio mute, `recentlyAudible`               | `is-muted`, `is-playing-audio`                                                                                      | fine                                                                                                                                     |
| `contentsSize`, `scrollPosition`            | none                                                                                                                | via JS                                                                                                                                   |
| colour chooser, OS drag and drop, tooltips  | none on WPE                                                                                                         | tooltips via `mouse-target-changed`; colour picker and OS DnD missing                                                                    |

## 6. Proposed architecture

**QtWPEEngine** (LGPL-2.1-or-later), two layers:

1. **QtWPEPlatform**: `WPEDisplayQt`, `WPEToplevelQt`, `WPEViewQt`, `WPEInputMethodContextQt`,
   `WPEClipboardQt`, `WPEScreenQt`, plus `QWPEWidget`, a `QOpenGLWidget` drawing the view's buffer.
   One display per app returning Qt's EGLDisplay and the render node; one toplevel per `QWindow`;
   one view per tab, unmapped when its tab is hidden. Renderer behind an interface so a
   `wl_subsurface` backend can follow. Startup check that Qt runs the GLib event dispatcher.
2. **Compatibility API**: classes mirroring the QtWebEngine subset Falkon uses, in namespace
   `QtWPE`, installed with `<QWebEnginePage>`-style compatibility headers that alias them
   (`using QWebEnginePage = QtWPE::Page`). Includes a `QWebChannel` transport over script messages,
   user scripts per world, a scheme-handler adapter, the sandbox paths for each VA engine, and a
   small web-process extension (C) for request interception: block, redirect, header edits, fed with
   rules from the UI process.

**Falkon**: a build-time choice, not a runtime switch. `option(FALKON_ENGINE "QtWebEngine|WPE")`,
QtWebEngine by default; the WPE build is a separate package (`falkon-wpe`) because plugins and
PyFalkon are compiled against one engine's types.

### File-level Falkon changes

| File                                                                         | Change                                                                                                                                              |
| ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CMakeLists.txt:58-64`, `src/lib/CMakeLists.txt:600-616`                     | `FALKON_ENGINE` option; find and link QtWPEEngine instead of Qt6WebEngine*; `FALKON_ENGINE_WPE` define                                              |
| `src/lib/app/mainapplication.cpp:305-347,459-485,1043-1136,1239-1327`        | profile, settings and script set-up through the shim; skip Chromium flags and the thumbnailer QML; sandbox paths and GStreamer environment at start |
| `src/lib/webengine/webview.cpp:1280-1370`, `webview.h`                       | replace the render-widget event filter with `QWPEWidget`'s events                                                                                   |
| `src/lib/webengine/webpage.cpp:145-175`                                      | printing disabled or snapshot-to-PDF under `FALKON_ENGINE_WPE`; `execJavaScript` kept (nested loop over the async call)                             |
| `src/lib/webengine/webinspector.cpp`                                         | inspector as a separate window (`toggle_inspector`)                                                                                                 |
| `src/lib/webtab/webtab.cpp:91,113,373,590`                                   | version the session blob; WPE session state in the new version                                                                                      |
| `src/lib/network/networkurlinterceptor.cpp`, `src/lib/adblock/*`             | feed the web-process extension; AdBlock rules converted to content-blocker JSON plus extension rules                                                |
| `src/lib/network/networkmanager.cpp:328-378`                                 | certificate errors after load failure: show the error page, allow the host, reload                                                                  |
| `src/lib/downloads/downloadmanager.cpp`, `downloaditem.cpp`                  | hide pause/resume and save-page formats                                                                                                             |
| `src/lib/other/sitesettingsmanager.*`, `src/lib/preferences/preferences.cpp` | hide attributes WPE lacks                                                                                                                           |
| `src/lib/tools/pagethumbnailer.cpp`                                          | thumbnails from `webkit_web_view_get_snapshot` instead of QML                                                                                       |
| `src/lib/webengine/webview.cpp:681-726`, new popup code                      | context menu from `WebKitContextMenu`; `<select>` popup; tooltips from `mouse-target-changed`                                                       |
| `src/plugins/PyFalkon/*`                                                     | off for WPE builds (PySide's typesystems are QtWebEngine's)                                                                                         |

## 7. Effort

One experienced engineer, weeks; risk is the chance the estimate slips by half or more.

| Component                                                                                                                           |  Weeks | Risk   | Depends on     |
| ----------------------------------------------------------------------------------------------------------------------------------- | -----: | ------ | -------------- |
| WPE 2.54 for trixie (unmodified Debian source rebuild, package, CI)                                                                 |      1 | medium | owner decision |
| QtWPEPlatform: display, toplevel, view, `QOpenGLWidget` rendering, sync                                                             |      3 | medium | WPE 2.54       |
| Input, IME, focus, scale, cursors, clipboard, visibility                                                                            |      2 | medium | platform       |
| Popups: context menu, `<select>`, dialogs, file chooser, tooltips                                                                   |      2 | low    | platform       |
| Compatibility API: page, view, profile, settings, scripts, history, downloads, cookies, permissions, find, fullscreen, certificates |      5 | medium | platform       |
| `QWebChannel` transport and scheme handlers                                                                                         |      1 | low    | API            |
| Request interception: web-process extension and AdBlock conversion                                                                  |      3 | high   | API            |
| Media integration: sandbox paths per engine, GStreamer environment, AV1 ranking, zero-copy check per engine                         |      2 | high   | VA-API session |
| Falkon patches (table above)                                                                                                        |      4 | medium | API            |
| Mali-450 tuning: Skia precision artefacts, MSAA, CPU vs GPU raster, subsurface backend if needed                                    |      3 | high   | PoC results    |
| Tests: library unit tests, Falkon autotests on WPE, a browser suite in `tools/validate` on every board                              |      3 | medium | all            |
| **Total**                                                                                                                           | **29** |        |                |

Upstreaming the Falkon option to KDE is extra, as is printing beyond snapshots.

## 8. Proof of concept

A two-to-three-week spike that decides go or no-go before any Falkon work:

1. WPE 2.54.2 for trixie on the M2 Plus (lima) and H313 (panfrost), plus `gstreamer1.0-gl`.
2. QtWPEPlatform's minimum: display, toplevel, view, `QOpenGLWidget` import of dma-buf buffers;
   mouse, wheel, keyboard and focus; resize and scale; two tabs with visibility.
3. A 300-line Qt Widgets shell: URL bar, tabs, back, forward, reload.
4. Sandbox paths for MPP; `GST_VA_ALL_DRIVERS=1`; AV1 ranked NONE.

It passes if, on both boards in the labwc session:

- pages render correctly (no FP16 artefacts) and scroll smoothly with GPU raster or CPU raster plus
  GL compositing;
- `WEBKIT_SHOW_FPS` stays near 60 on a static page and near 30 when scrolling;
- YouTube and local H.264 1080p play through `vah264dec` into `webkitglvideosink` as dma-buf
  (checked with `GST_DEBUG`), without dropped frames and with low CPU use;
- typing, IME commit and tab switching work.

If lima fails on precision or speed, retry with CPU raster, then `WEBKIT_USE_SKIA_FOR_COMPOSITION=0`
(2.54 only). If neither holds, Mali-450 boards are no-go for WPE and keep a lighter browser;
panfrost boards can still proceed.

## 9. Blockers and open questions

| #   | Item                                                                                     | Type           |
| --- | ---------------------------------------------------------------------------------------- | -------------- |
| 1   | No prebuilt WPE 2.54 for trixie; rebuilding Debian's unmodified source is the only route | owner decision |
| 2   | Ganesh on lima under 2.54 (Skia 154) untested; no fallback if it fails to initialise     | PoC            |
| 3   | lima's FP16 fragments with Skia's Mali-4xx workarounds off                               | PoC            |
| 4   | TextureMapper, the GLES2-clean fallback, is removed after 2.54                           | future         |
| 5   | Zero-copy video unproven until `gstreamer1.0-gl` is in and the sandbox paths are set     | PoC            |
| 6   | Request interception needs a web-process extension; AdBlock parity uncertain             | design         |
| 7   | No printing on WPE                                                                       | accepted gap   |
| 8   | Plugins and PyFalkon tied to one engine per build                                        | accepted       |
| 9   | Each WebProcess costs RAM; H313 boxes have 2 GB                                          | PoC            |

## Sources

- Falkon: <https://invent.kde.org/network/falkon> at `bf75426a`; inventory in
  [`falkon-inventory.md`](falkon-inventory.md).
- WPE WebKit 2.54.2: <https://wpewebkit.org/releases/>; 2.54 highlights
  <https://wpewebkit.org/blog/2026-09-16-wpewebkit-2.54.html>; Igalia periodical
  <https://blogs.igalia.com/webkit/blog/2026/wip-79/>; Skia compositor
  <https://blogs.igalia.com/carlosgc/tag/skia/>.
- Packaging: <https://sources.debian.org/data/main/w/wpewebkit/2.54.2-1/debian/rules>; Arch PKGBUILD
  <https://gitlab.archlinux.org/archlinux/packaging/packages/wpewebkit/-/raw/main/PKGBUILD>.
- wpe-platform-gtk: <https://github.com/Igalia/wpe-platform-gtk>; Qt event dispatcher
  <https://raw.githubusercontent.com/qt/qtbase/6.8/src/gui/platform/unix/qgenericunixeventdispatcher.cpp>.
- Mesa lima: <https://docs.mesa3d.org/drivers/lima.html>. WebKit bugs 261870, 219739,
  314719, 314892.
