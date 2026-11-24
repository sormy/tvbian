#pragma once

#include <cstdint>
#include <set>
#include <utility>

struct wl_compositor;
struct wl_display;
struct wl_subcompositor;
struct wp_viewporter;
struct zwp_linux_dmabuf_v1;

namespace QtWpeWebKit {

// The compositor's globals the surfaces need, bound once a process
struct WaylandGlobals {
    wl_display* display;
    wl_compositor* compositor;
    wl_subcompositor* subcompositor = nullptr;
    wp_viewporter* viewporter = nullptr;
    zwp_linux_dmabuf_v1* dmabuf = nullptr;
    // the DRM format and modifier pairs it imports: anything else would end the connection
    std::set<std::pair<uint32_t, uint64_t>> formats;
};

// null where the compositor lacks one of them
WaylandGlobals* waylandGlobals();

} // namespace QtWpeWebKit
