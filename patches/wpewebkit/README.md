# wpewebkit — Rockchip's MPP in the sandbox, and what qtwpewebkit needs

WebKit runs its web process in a bubblewrap sandbox that binds the GPU and V4L2 devices but not
Rockchip's MPP. GStreamer's VA decoders on `rk35xx` reach the engine through MPP, so in the sandbox
they are not registered and video plays in software. `extras/wpewebkit` rebuilds Debian's
`wpewebkit` with the patch.

| Patch  | Fixes                                                                    | Upstream                |
| ------ | ------------------------------------------------------------------------ | ----------------------- |
| `0001` | hardware video in WPE's sandbox on Rockchip: three paths in              | not sent                |
| `0002` | a navigation's frame: `webkit_navigation_action_get_target_frame_info()` | WebKit 2.56, backported |
| `0003` | a DOM node returned by a script: an empty object, not an error           | not sent                |
| `0004` | a popup told in `create`: `webkit_navigation_action_is_popup()`          | not sent                |
| `0005` | a served scheme is secure only when registered secure                    | not sent                |
| `0006` | `fetch()` reaches a served scheme only when registered CORS-enabled      | not sent                |
| `0007` | a click opens one window, not one for each `window.open()` it calls      | not sent                |
| `0008` | an application's script does not use up the user's click                 | not sent                |
| `0009` | a media download pauses no lower than 32 MiB, so a resume does not stall | not sent                |

Each path is measured as needed: without `/dev/mpp_service` or the device tree no VA decoder is
registered; without `/dev/dma_heap` the pipeline does not start. They must be device binds:
`webkit_web_context_add_path_to_sandbox()` binds `nodev`, and `/dev/mpp_service` then fails to open
with `EACCES`.

`0003` to `0008` give WPE QtWebEngine's behaviour (Chromium's), which qtwpewebkit's tests compare
against. `0001` and `0003` to `0009` go upstream; once Debian ships a WebKit with all of them, the
extra retires.
