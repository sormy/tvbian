# gstreamer — a plugin registry that stays valid while devices are used

GStreamer caches what its plugins offer and rescans a plugin when what it depends on changes.
Plugins that probe hardware (`va` on `/dev/dri/renderD*`, `v4l2codecs` on `/dev/video*` and
`/dev/media*`) depend on device nodes, which GStreamer hashes by their size and times. The kernel
updates a node's times as the device is used, so any program opening the GPU makes `va` stale: the
next process to start GStreamer rescans it and rewrites the whole registry, about 0.5 s of every WPE
WebKit and Falkon start on the M2 Plus. `0001` hashes a device node by its device number, which
names the device. `extras/gstreamer` rebuilds Debian's `gstreamer1.0` with it.

| Patch  | Fixes                                                 | Upstream |
| ------ | ----------------------------------------------------- | -------- |
| `0001` | the registry rewritten on starts after any device use | not sent |

A device added or removed still changes the hash: the directory's entries are matched by name.
