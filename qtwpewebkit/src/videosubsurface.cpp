#include "videosubsurface.h"

#include "linux-dmabuf-v1-client-protocol.h"
#include "videoplanes.h"
#include "viewporter-client-protocol.h"
#include "wayland.h"

#include <climits>
#include <cstring>
#include <sys/stat.h>
#include <unistd.h>
#include <utility>
#include <wayland-client.h>

namespace QtWpeWebKit {

// A decoder buffer as the compositor knows it; while shown, the frame it holds stays the web process's
struct VideoSubsurface::Frame {
    wl_buffer* buffer;
    // the dma-buf's identity: the descriptors differ each time it comes back
    dev_t device;
    ino_t inode;
    VideoPlaneMessage layout;
    std::shared_ptr<VideoConnection> connection;
    bool attached = false;

    void release()
    {
        if (std::exchange(attached, false)) {
            qCDebug(videoPlanes, "frame %llu released by the compositor", (unsigned long long)layout.frame);
            connection->release(layout.stream, layout.frame);
        }
    }
};

namespace {

// The decoder allocates a pool of buffers once: more than this would be a new pool
constexpr size_t maxFrames = 32;

const wl_buffer_listener bufferListener {
    .release = [](void* data, wl_buffer*) {
        static_cast<VideoSubsurface::Frame*>(data)->release();
    },
};

bool sameLayout(const VideoPlaneMessage& a, const VideoPlaneMessage& b)
{
    return a.frameWidth == b.frameWidth && a.frameHeight == b.frameHeight && a.fourcc == b.fourcc
        && a.modifier == b.modifier && a.planes == b.planes && !memcmp(a.offsets, b.offsets, sizeof a.offsets)
        && !memcmp(a.strides, b.strides, sizeof a.strides);
}

} // namespace

VideoSubsurface::VideoSubsurface(wl_surface* parent, wl_surface* page)
{
    WaylandGlobals& wayland = *waylandGlobals();
    m_surface = wl_compositor_create_surface(wayland.compositor);
    m_subsurface = wl_subcompositor_get_subsurface(wayland.subcompositor, m_surface, parent);
    wl_subsurface_place_below(m_subsurface, page);
    // its frames shown as they come, not when Qt next draws the window
    wl_subsurface_set_desync(m_subsurface);
    m_viewport = wp_viewporter_get_viewport(wayland.viewporter, m_surface);
    // input goes to the widget, as before
    wl_region* none = wl_compositor_create_region(wayland.compositor);
    wl_surface_set_input_region(m_surface, none);
    wl_region_destroy(none);
}

VideoSubsurface::~VideoSubsurface()
{
    wp_viewport_destroy(m_viewport);
    wl_subsurface_destroy(m_subsurface);
    wl_surface_destroy(m_surface);
    // the compositor no longer reads any of them
    for (auto& frame : m_frames) {
        frame->release();
        wl_buffer_destroy(frame->buffer);
    }
}

// The buffer the compositor already has for this dma-buf, or a new one; null where it cannot import it
VideoSubsurface::Frame* VideoSubsurface::frameFor(const VideoPlaneMessage& message, const int* fds)
{
    struct stat file;
    if (fstat(fds[0], &file))
        return nullptr;
    for (auto& frame : m_frames) {
        if (frame->device == file.st_dev && frame->inode == file.st_ino && sameLayout(frame->layout, message) && !frame->attached)
            return frame.get();
    }
    WaylandGlobals& wayland = *waylandGlobals();
    if (!wayland.formats.contains({ message.fourcc, message.modifier }))
        return nullptr;
    // a new pool: the old one's buffers come no more
    if (m_frames.size() >= maxFrames || (!m_frames.empty() && !sameLayout(m_frames.front()->layout, message))) {
        std::erase_if(m_frames, [](const auto& frame) {
            if (frame->attached)
                return false;
            wl_buffer_destroy(frame->buffer);
            return true;
        });
    }
    auto* params = zwp_linux_dmabuf_v1_create_params(wayland.dmabuf);
    for (uint32_t plane = 0; plane < message.planes; plane++)
        zwp_linux_buffer_params_v1_add(params, fds[plane], plane, message.offsets[plane], message.strides[plane],
            message.modifier >> 32, message.modifier & UINT32_MAX);
    auto* buffer = zwp_linux_buffer_params_v1_create_immed(params, message.frameWidth, message.frameHeight, message.fourcc, 0);
    zwp_linux_buffer_params_v1_destroy(params);
    auto& frame = m_frames.emplace_back(new Frame { buffer, file.st_dev, file.st_ino, message, nullptr });
    wl_buffer_add_listener(buffer, &bufferListener, frame.get());
    return frame.get();
}

bool VideoSubsurface::show(std::shared_ptr<VideoConnection> connection, const VideoPlaneMessage& message, const int* fds)
{
    // unplaced, the surface would take the frame's size
    Frame* frame = m_destination.isEmpty() ? nullptr : frameFor(message, fds);
    // a new buffer's requests carry copies
    for (uint32_t plane = 0; plane < message.planes; plane++)
        close(fds[plane]);
    if (!frame) {
        qCDebug(videoPlanes, "frame %llu released unshown: %s", (unsigned long long)message.frame, m_destination.isEmpty() ? "no place yet" : "not importable");
        connection->release(message.stream, message.frame);
        return false;
    }
    qCDebug(videoPlanes, "frame %llu shown", (unsigned long long)message.frame);
    if (const QSize size(message.frameWidth, message.frameHeight); size != m_frameSize) {
        m_frameSize = size;
        applySource();
    }
    frame->layout = message;
    frame->connection = std::move(connection);
    frame->attached = true;
    wl_surface_attach(m_surface, frame->buffer, 0, 0);
    wl_surface_damage_buffer(m_surface, 0, 0, INT32_MAX, INT32_MAX);
    wl_surface_commit(m_surface);
    return true;
}

void VideoSubsurface::place(const QRect& destination, const QRectF& source)
{
    if (destination == m_destination && source == m_source)
        return;
    m_destination = destination;
    m_source = source;
    // takes effect as Qt next commits the window
    wl_subsurface_set_position(m_subsurface, destination.x(), destination.y());
    applySource();
    wp_viewport_set_destination(m_viewport, destination.width(), destination.height());
    wl_surface_commit(m_surface);
}

// A source outside the frame would end the compositor connection: it is a fraction of the frame shown
void VideoSubsurface::applySource()
{
    const QRectF whole(0, 0, 1, 1);
    const QRectF fraction = m_source.intersected(whole);
    if (m_frameSize.isEmpty() || fraction.isEmpty() || fraction == whole) {
        const wl_fixed_t unset = wl_fixed_from_int(-1);
        wp_viewport_set_source(m_viewport, unset, unset, unset, unset);
        return;
    }
    const double width = m_frameSize.width(), height = m_frameSize.height();
    wp_viewport_set_source(m_viewport, wl_fixed_from_double(fraction.x() * width), wl_fixed_from_double(fraction.y() * height),
        wl_fixed_from_double(fraction.width() * width), wl_fixed_from_double(fraction.height() * height));
}

void VideoSubsurface::hide()
{
    m_destination = {};
    wl_surface_attach(m_surface, nullptr, 0, 0);
    wl_surface_commit(m_surface);
}

} // namespace QtWpeWebKit
