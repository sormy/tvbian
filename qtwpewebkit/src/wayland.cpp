#include "wayland.h"

#include "linux-dmabuf-v1-client-protocol.h"
#include "viewporter-client-protocol.h"

#include <QGuiApplication>
#include <cstring>
#include <wayland-client.h>

namespace QtWpeWebKit {

namespace {

// the first that announces each format's modifiers and takes one a plane
constexpr uint32_t dmabufVersion = 3;

const zwp_linux_dmabuf_v1_listener dmabufListener {
    .format = [](void*, zwp_linux_dmabuf_v1*, uint32_t) {},
    .modifier = [](void* data, zwp_linux_dmabuf_v1*, uint32_t format, uint32_t high, uint32_t low) {
        static_cast<WaylandGlobals*>(data)->formats.emplace(format, uint64_t(high) << 32 | low);
    },
};

const wl_registry_listener registryListener {
    .global = [](void* data, wl_registry* registry, uint32_t name, const char* interface, uint32_t version) {
        auto* globals = static_cast<WaylandGlobals*>(data);
        if (!strcmp(interface, wl_subcompositor_interface.name))
            globals->subcompositor = static_cast<wl_subcompositor*>(wl_registry_bind(registry, name, &wl_subcompositor_interface, 1));
        else if (!strcmp(interface, wp_viewporter_interface.name))
            globals->viewporter = static_cast<wp_viewporter*>(wl_registry_bind(registry, name, &wp_viewporter_interface, 1));
        else if (!strcmp(interface, zwp_linux_dmabuf_v1_interface.name) && version >= dmabufVersion) {
            globals->dmabuf = static_cast<zwp_linux_dmabuf_v1*>(wl_registry_bind(registry, name, &zwp_linux_dmabuf_v1_interface, dmabufVersion));
            zwp_linux_dmabuf_v1_add_listener(globals->dmabuf, &dmabufListener, globals);
        }
    },
    .global_remove = [](void*, wl_registry*, uint32_t) {},
};

WaylandGlobals* bind()
{
    auto* wayland = qGuiApp->nativeInterface<QNativeInterface::QWaylandApplication>();
    if (!wayland || !wayland->display() || !wayland->compositor())
        return nullptr;
    auto* globals = new WaylandGlobals { wayland->display(), wayland->compositor() };
    // bound on a queue of its own, so Qt dispatches none of it half-done
    wl_event_queue* queue = wl_display_create_queue(globals->display);
    auto* display = static_cast<wl_display*>(wl_proxy_create_wrapper(globals->display));
    wl_proxy_set_queue(reinterpret_cast<wl_proxy*>(display), queue);
    wl_registry* registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &registryListener, globals);
    wl_display_roundtrip_queue(globals->display, queue); // the globals
    wl_display_roundtrip_queue(globals->display, queue); // dma-buf's formats
    wl_registry_destroy(registry);
    wl_proxy_wrapper_destroy(display);
    // what is made from them then comes with Qt's own events, on Qt's queue
    wl_event_queue* qtQueue = wl_proxy_get_queue(reinterpret_cast<wl_proxy*>(globals->compositor));
    for (void* proxy : { static_cast<void*>(globals->subcompositor), static_cast<void*>(globals->viewporter), static_cast<void*>(globals->dmabuf) }) {
        if (proxy)
            wl_proxy_set_queue(static_cast<wl_proxy*>(proxy), qtQueue);
    }
    wl_event_queue_destroy(queue);
    if (!globals->subcompositor || !globals->viewporter || !globals->dmabuf) {
        delete globals;
        return nullptr;
    }
    return globals;
}

} // namespace

WaylandGlobals* waylandGlobals()
{
    static WaylandGlobals* bound = bind();
    return bound;
}

} // namespace QtWpeWebKit
