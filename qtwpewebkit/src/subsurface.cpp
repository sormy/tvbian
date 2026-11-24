#include "subsurface.h"

#include "linux-dmabuf-v1-client-protocol.h"
#include "videoplanes.h"
#include "videosubsurface.h"
#include "viewporter-client-protocol.h"
#include "wayland.h"

#include <QGuiApplication>
#include <QRegion>
#include <QWidget>
#include <QWindow>
#include <climits>
#include <cstring>
#include <qpa/qplatformnativeinterface.h>
#include <unistd.h>
#include <wayland-client.h>
#include <wpe/wpe-platform.h>

namespace QtWpeWebKit {

namespace {

// A WebKit buffer as the compositor knows it: made once, kept as long as the buffer
struct Frame {
    WPEView* view;
    WPEBuffer* buffer;
    wl_buffer* wayland;
};

const wl_buffer_listener bufferListener {
    .release = [](void* data, wl_buffer*) {
        auto* frame = static_cast<Frame*>(data);
        if (frame->view)
            wpe_view_buffer_released(frame->view, frame->buffer);
    },
};

void forgetFrame(gpointer data)
{
    auto* frame = static_cast<Frame*>(data);
    if (frame->view)
        g_object_remove_weak_pointer(G_OBJECT(frame->view), reinterpret_cast<gpointer*>(&frame->view));
    wl_buffer_destroy(frame->wayland);
    delete frame;
}

wl_buffer* waylandBuffer(WaylandGlobals& globals, WPEView* view, WPEBuffer* buffer)
{
    static const GQuark key = g_quark_from_static_string("qtwpewebkit-wl-buffer");
    if (auto* frame = static_cast<Frame*>(g_object_get_qdata(G_OBJECT(buffer), key)))
        return frame->wayland;
    if (!WPE_IS_BUFFER_DMA_BUF(buffer))
        return nullptr;
    auto* dmabuf = WPE_BUFFER_DMA_BUF(buffer);
    const uint32_t format = wpe_buffer_dma_buf_get_format(dmabuf);
    const uint64_t modifier = wpe_buffer_dma_buf_get_modifier(dmabuf);
    if (!globals.formats.contains({ format, modifier }))
        return nullptr;
    auto* params = zwp_linux_dmabuf_v1_create_params(globals.dmabuf);
    for (guint32 plane = 0; plane < wpe_buffer_dma_buf_get_n_planes(dmabuf); plane++) {
        zwp_linux_buffer_params_v1_add(params, wpe_buffer_dma_buf_get_fd(dmabuf, plane), plane,
            wpe_buffer_dma_buf_get_offset(dmabuf, plane), wpe_buffer_dma_buf_get_stride(dmabuf, plane),
            modifier >> 32, modifier & UINT32_MAX);
    }
    auto* wayland = zwp_linux_buffer_params_v1_create_immed(params, wpe_buffer_get_width(buffer),
        wpe_buffer_get_height(buffer), format, 0);
    zwp_linux_buffer_params_v1_destroy(params);
    auto* frame = new Frame { view, buffer, wayland };
    g_object_add_weak_pointer(G_OBJECT(view), reinterpret_cast<gpointer*>(&frame->view));
    wl_buffer_add_listener(wayland, &bufferListener, frame);
    g_object_set_qdata_full(G_OBJECT(buffer), key, frame, forgetFrame);
    return wayland;
}

const wl_callback_listener frameListener {
    .done = [](void* data, wl_callback*, uint32_t) {
        static_cast<Subsurface*>(data)->frameShown();
    },
};

} // namespace

std::unique_ptr<Subsurface> Subsurface::create(QWidget* widget, WPEView* view)
{
    if (!waylandGlobals())
        return nullptr;
    return std::unique_ptr<Subsurface>(new Subsurface(widget, view));
}

Subsurface::Subsurface(QWidget* widget, WPEView* view)
    : m_widget(widget)
    , m_view(view)
{
}

Subsurface::~Subsurface()
{
    destroy();
}

void Subsurface::destroy()
{
    // beneath the surface going away
    m_videos.clear();
    if (m_frame)
        wl_callback_destroy(m_frame);
    m_frame = nullptr;
    m_frameBuffer = nullptr;
    if (m_viewport)
        wp_viewport_destroy(m_viewport);
    if (m_subsurface)
        wl_subsurface_destroy(m_subsurface);
    if (m_surface)
        wl_surface_destroy(m_surface);
    m_viewport = nullptr;
    m_subsurface = nullptr;
    m_surface = nullptr;
    m_parent = nullptr;
    m_size = {};
}

// On the window's surface as it is now: Qt makes a new one each time the window is shown
bool Subsurface::attachToWindow()
{
    QWindow* window = m_widget->window()->windowHandle();
    auto* parent = window ? static_cast<wl_surface*>(QGuiApplication::platformNativeInterface()->nativeResourceForWindow("surface", window)) : nullptr;
    if (!parent)
        return false;
    if (parent == m_parent)
        return true;
    destroy();
    WaylandGlobals& wayland = *waylandGlobals();
    m_surface = wl_compositor_create_surface(wayland.compositor);
    m_subsurface = wl_subcompositor_get_subsurface(wayland.subcompositor, m_surface, parent);
    // its frames shown as WebKit makes them, not when Qt next draws the window
    wl_subsurface_set_desync(m_subsurface);
    m_viewport = wp_viewporter_get_viewport(wayland.viewporter, m_surface);
    // input goes to the widget beneath, as before
    wl_region* none = wl_compositor_create_region(wayland.compositor);
    wl_surface_set_input_region(m_surface, none);
    wl_region_destroy(none);
    m_parent = parent;
    return true;
}

bool Subsurface::present(WPEBuffer* buffer)
{
    wl_buffer* wayland = waylandBuffer(*waylandGlobals(), m_view, buffer);
    if (!wayland || !attachToWindow())
        return false;
    // WebKit draws its next frame once this one is shown; one not shown yet counts as shown
    if (m_frame)
        frameShown();
    m_frame = wl_surface_frame(m_surface);
    m_frameBuffer = buffer;
    m_bufferSize = QSize(wpe_buffer_get_width(buffer), wpe_buffer_get_height(buffer));
    wl_callback_add_listener(m_frame, &frameListener, this);
    wl_surface_attach(m_surface, wayland, 0, 0);
    wl_surface_damage_buffer(m_surface, 0, 0, INT32_MAX, INT32_MAX);
    place();
    return true;
}

void Subsurface::frameShown()
{
    wl_callback_destroy(m_frame);
    m_frame = nullptr;
    wpe_view_buffer_rendered(m_view, std::exchange(m_frameBuffer, nullptr));
}

void Subsurface::place()
{
    if (!m_surface)
        return;
    const QPoint origin = m_widget->mapTo(m_widget->window(), QPoint());
    // takes effect as Qt next commits the window
    wl_subsurface_set_position(m_subsurface, origin.x(), origin.y());
    if (m_widget->size() != m_size) {
        m_size = m_widget->size();
        wp_viewport_set_destination(m_viewport, m_size.width(), m_size.height());
    }
    placeVideos();
    wl_surface_commit(m_surface);
}

// Each video beneath its hole; the page is opaque elsewhere, and what lies beneath that is not drawn
void Subsurface::placeVideos()
{
    QRegion opaque(QRect(QPoint(), m_size));
    const QPoint origin = m_widget->mapTo(m_widget->window(), QPoint());
    for (auto& [key, video] : m_videos) {
        const QRect page(QPoint(), m_bufferSize);
        const QRect hole = video->hole();
        const QRect shown = hole & page;
        if (shown.isEmpty() || m_bufferSize.isEmpty() || m_size.isEmpty()) {
            video->hide();
            continue;
        }
        const double scaleX = double(m_size.width()) / m_bufferSize.width();
        const double scaleY = double(m_size.height()) / m_bufferSize.height();
        const QRect inWidget = QRectF(shown.x() * scaleX, shown.y() * scaleY, shown.width() * scaleX, shown.height() * scaleY).toAlignedRect() & QRect(QPoint(), m_size);
        if (inWidget.isEmpty()) {
            video->hide();
            continue;
        }
        const QRectF fraction(double(shown.x() - hole.x()) / hole.width(), double(shown.y() - hole.y()) / hole.height(),
            double(shown.width()) / hole.width(), double(shown.height()) / hole.height());
        video->place(inWidget.translated(origin), fraction);
        opaque -= inWidget;
    }
    wl_region* region = wl_compositor_create_region(waylandGlobals()->compositor);
    for (const QRect& rect : opaque)
        wl_region_add(region, rect.x(), rect.y(), rect.width(), rect.height());
    wl_surface_set_opaque_region(m_surface, region);
    wl_region_destroy(region);
}

void Subsurface::showVideoFrame(std::shared_ptr<VideoConnection> connection, const VideoPlaneMessage& frame, const int* fds)
{
    const VideoKey key { connection.get(), frame.stream };
    auto it = m_videos.find(key);
    if (it == m_videos.end()) {
        // off its subsurface, the page has no place for videos beneath it
        if (!m_surface) {
            qCDebug(videoPlanes, "frame %llu released unshown: the page is off its subsurface", (unsigned long long)frame.frame);
            for (uint32_t plane = 0; plane < frame.planes; plane++)
                close(fds[plane]);
            connection->release(frame.stream, frame.frame);
            return;
        }
        it = m_videos.emplace(key, std::make_unique<VideoSubsurface>(m_parent, m_surface)).first;
        qCDebug(videoPlanes, "stream %u: surface made, %zu in the page", frame.stream, m_videos.size());
    }
    VideoSubsurface& video = *it->second;
    if (video.hole() != QRect(frame.x, frame.y, frame.width, frame.height)) {
        video.setHole(QRect(frame.x, frame.y, frame.width, frame.height));
        // the new place takes effect as Qt next commits the window
        m_widget->update();
    }
    video.show(std::move(connection), frame, fds);
}

void Subsurface::moveVideo(const VideoConnection* connection, const VideoPlaneMessage& rectangle)
{
    auto it = m_videos.find({ connection, rectangle.stream });
    if (it == m_videos.end())
        return;
    it->second->setHole(QRect(rectangle.x, rectangle.y, rectangle.width, rectangle.height));
    m_widget->update();
}

void Subsurface::stopVideo(const VideoConnection* connection, uint32_t stream)
{
    qCDebug(videoPlanes, "stream %u: stopped", stream);
    if (m_videos.erase({ connection, stream }))
        m_widget->update();
}

void Subsurface::stopVideos(const VideoConnection* connection)
{
    if (std::erase_if(m_videos, [connection](const auto& entry) { return entry.first.first == connection; }))
        m_widget->update();
}

void Subsurface::hide()
{
    if (!m_surface)
        return;
    if (m_frame)
        frameShown();
    // a video shown without its page would cover what is drawn instead
    m_videos.clear();
    wl_surface_attach(m_surface, nullptr, 0, 0);
    wl_surface_commit(m_surface);
}

} // namespace QtWpeWebKit
